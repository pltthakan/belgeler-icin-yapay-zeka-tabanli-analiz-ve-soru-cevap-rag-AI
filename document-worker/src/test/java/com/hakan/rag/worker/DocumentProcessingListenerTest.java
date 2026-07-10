package com.hakan.rag.worker;

import com.hakan.rag.document.DocumentStatus;
import com.hakan.rag.document.queue.DocumentProcessingJob;
import com.hakan.rag.document.queue.DocumentProcessingOperation;
import com.hakan.rag.worker.dto.AiIngestResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessagePostProcessor;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DocumentProcessingListenerTest {
    private static final String RETRY_EXCHANGE = "document-processing.retry.exchange";
    private static final String RETRY_ROUTING_KEY = "document-processing.retry";

    @TempDir
    Path tempDir;

    private RecordingJdbcTemplate jdbcTemplate;
    private RestTemplate restTemplate;
    private RabbitTemplate rabbitTemplate;
    private DocumentProcessingListener listener;

    @BeforeEach
    void setUp() {
        jdbcTemplate = new RecordingJdbcTemplate();
        restTemplate = mock(RestTemplate.class);
        rabbitTemplate = mock(RabbitTemplate.class);
        listener = new DocumentProcessingListener(
                jdbcTemplate,
                restTemplate,
                rabbitTemplate,
                "http://ai-service:5000",
                RETRY_EXCHANGE,
                RETRY_ROUTING_KEY,
                3
        );
    }

    @Test
    void marksDocumentReadyAfterSuccessfulIngestion() throws Exception {
        DocumentProcessingJob job = ingestJob(createDocument());
        when(restTemplate.postForEntity(anyString(), any(HttpEntity.class), eq(AiIngestResponse.class)))
                .thenReturn(ResponseEntity.ok(new AiIngestResponse("1", 7, "ok")));

        listener.process(job, null);

        assertEquals(DocumentStatus.READY.name(), jdbcTemplate.lastUpdateArguments[0]);
        assertEquals(7, jdbcTemplate.lastUpdateArguments[1]);
        assertEquals(1L, jdbcTemplate.lastUpdateArguments[2]);
        verify(rabbitTemplate, never()).convertAndSend(anyString(), anyString(), any(), any(MessagePostProcessor.class));
    }

    @Test
    void publishesTransientFailureToRetryQueueWithIncrementedHeaders() throws Exception {
        DocumentProcessingJob job = ingestJob(createDocument());
        when(restTemplate.postForEntity(anyString(), any(HttpEntity.class), eq(AiIngestResponse.class)))
                .thenThrow(new ResourceAccessException("connection timeout"));

        listener.process(job, null);

        var postProcessorCaptor = org.mockito.ArgumentCaptor.forClass(MessagePostProcessor.class);
        verify(rabbitTemplate).convertAndSend(
                eq(RETRY_EXCHANGE),
                eq(RETRY_ROUTING_KEY),
                same(job),
                postProcessorCaptor.capture()
        );

        MessageProperties properties = new MessageProperties();
        postProcessorCaptor.getValue().postProcessMessage(new Message(new byte[0], properties));
        assertEquals(1, ((Number) properties.getHeader(DocumentProcessingListener.RETRY_COUNT_HEADER)).intValue());
        assertEquals("connection timeout", properties.getHeader(DocumentProcessingListener.LAST_ERROR_HEADER));
        assertEquals(MessageDeliveryMode.PERSISTENT, properties.getDeliveryMode());
        assertNull(jdbcTemplate.lastUpdateArguments);
    }

    @Test
    void marksDocumentFailedAndRejectsMessageWhenRetryLimitIsReached() throws Exception {
        DocumentProcessingJob job = ingestJob(createDocument());
        when(restTemplate.postForEntity(anyString(), any(HttpEntity.class), eq(AiIngestResponse.class)))
                .thenThrow(new ResourceAccessException("AI service unavailable"));

        assertThrows(AmqpRejectAndDontRequeueException.class, () -> listener.process(job, 3));

        assertEquals(DocumentStatus.FAILED.name(), jdbcTemplate.lastUpdateArguments[0]);
        assertEquals("Belge işleme başarısız: AI service unavailable", jdbcTemplate.lastUpdateArguments[1]);
        assertEquals(1L, jdbcTemplate.lastUpdateArguments[2]);
        verify(rabbitTemplate, never()).convertAndSend(anyString(), anyString(), any(), any(MessagePostProcessor.class));
    }

    @Test
    void sendsPermanentFailureDirectlyToDlqWithoutRetry() {
        DocumentProcessingJob job = ingestJob(tempDir.resolve("missing.pdf"));

        assertThrows(AmqpRejectAndDontRequeueException.class, () -> listener.process(job, null));

        assertEquals(DocumentStatus.FAILED.name(), jdbcTemplate.lastUpdateArguments[0]);
        verify(rabbitTemplate, never()).convertAndSend(anyString(), anyString(), any(), any(MessagePostProcessor.class));
    }

    @Test
    void preservesReadyStatusWhenReindexRetriesAreExhausted() throws Exception {
        DocumentProcessingJob job = new DocumentProcessingJob(
                1L,
                2L,
                3L,
                createDocument().toString(),
                "document.pdf",
                DocumentProcessingOperation.REINDEX,
                DocumentStatus.READY
        );
        when(restTemplate.postForEntity(anyString(), any(HttpEntity.class), eq(AiIngestResponse.class)))
                .thenThrow(new ResourceAccessException("connection timeout"));

        assertThrows(AmqpRejectAndDontRequeueException.class, () -> listener.process(job, 3));

        assertEquals(DocumentStatus.READY.name(), jdbcTemplate.lastUpdateArguments[0]);
        assertEquals("Yeniden indeksleme başarısız: connection timeout", jdbcTemplate.lastUpdateArguments[1]);
    }

    private Path createDocument() throws Exception {
        Path document = tempDir.resolve("document-" + System.nanoTime() + ".pdf");
        Files.writeString(document, "test document");
        return document;
    }

    private DocumentProcessingJob ingestJob(Path storedPath) {
        return new DocumentProcessingJob(
                1L,
                2L,
                3L,
                storedPath.toString(),
                "document.pdf",
                DocumentProcessingOperation.INGEST,
                null
        );
    }

    private static final class RecordingJdbcTemplate extends JdbcTemplate {
        private boolean documentExists = true;
        private Object[] lastUpdateArguments;

        @Override
        public <T> T queryForObject(String sql, Class<T> requiredType, Object... args) {
            return requiredType.cast(documentExists ? 1 : 0);
        }

        @Override
        public int update(String sql, Object... args) {
            lastUpdateArguments = args;
            return 1;
        }
    }
}
