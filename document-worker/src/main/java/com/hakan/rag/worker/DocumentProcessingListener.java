package com.hakan.rag.worker;

import com.hakan.rag.document.DocumentStatus;
import com.hakan.rag.document.queue.DocumentProcessingJob;
import com.hakan.rag.document.queue.DocumentProcessingOperation;
import com.hakan.rag.worker.dto.AiIngestResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.ImmediateRequeueAmqpException;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.CannotGetJdbcConnectionException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

import java.nio.file.Files;
import java.nio.file.Path;

@Component
public class DocumentProcessingListener {
    static final String RETRY_COUNT_HEADER = "x-retry-count";
    static final String LAST_ERROR_HEADER = "x-last-error";

    private static final Logger log = LoggerFactory.getLogger(DocumentProcessingListener.class);

    private final JdbcTemplate jdbcTemplate;
    private final RestTemplate restTemplate;
    private final RabbitTemplate rabbitTemplate;
    private final String aiBaseUrl;
    private final String retryExchange;
    private final String retryRoutingKey;
    private final int maxRetries;

    public DocumentProcessingListener(
            JdbcTemplate jdbcTemplate,
            RestTemplate restTemplate,
            RabbitTemplate rabbitTemplate,
            @Value("${app.ai.base-url}") String aiBaseUrl,
            @Value("${app.rabbitmq.document-processing.retry-exchange}") String retryExchange,
            @Value("${app.rabbitmq.document-processing.retry-routing-key}") String retryRoutingKey,
            @Value("${app.rabbitmq.document-processing.max-retries}") int maxRetries
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.restTemplate = restTemplate;
        this.rabbitTemplate = rabbitTemplate;
        this.aiBaseUrl = aiBaseUrl;
        this.retryExchange = retryExchange;
        this.retryRoutingKey = retryRoutingKey;
        this.maxRetries = Math.max(0, maxRetries);
    }

    @RabbitListener(queues = "${app.rabbitmq.document-processing.queue}")
    public void process(
            DocumentProcessingJob job,
            @Header(name = RETRY_COUNT_HEADER, required = false) Integer retryCount
    ) {
        if (job == null || job.documentId() == null) {
            throw new AmqpRejectAndDontRequeueException("Geçersiz belge işleme mesajı.");
        }

        try {
            if (!documentExists(job.documentId())) {
                return;
            }
            AiIngestResponse response = sendStoredFileToAiService(job);
            if (documentExists(job.documentId())) {
                markReady(job.documentId(), response.chunkCount());
            } else {
                deleteAiIndex(job.documentId());
            }
        } catch (Exception exception) {
            handleFailure(job, normalizedRetryCount(retryCount), exception);
        }
    }

    private void handleFailure(DocumentProcessingJob job, int retryCount, Exception exception) {
        if (isRetryable(exception) && retryCount < maxRetries) {
            int nextRetryCount = retryCount + 1;
            try {
                publishRetry(job, nextRetryCount, exception);
            } catch (AmqpException publishException) {
                throw new ImmediateRequeueAmqpException(
                        "Belge retry kuyruğuna gönderilemedi; mevcut mesaj yeniden kuyruğa alınıyor.",
                        publishException
                );
            }
            log.warn(
                    "Belge işleme yeniden denenecek. documentId={}, retry={}/{}, error={}",
                    job.documentId(),
                    nextRetryCount,
                    maxRetries,
                    rootErrorMessage(exception)
            );
            return;
        }

        try {
            markFailed(job, exception);
        } catch (Exception statusUpdateException) {
            throw new ImmediateRequeueAmqpException(
                    "Belgenin kalıcı hata durumu kaydedilemedi; mevcut mesaj yeniden kuyruğa alınıyor.",
                    statusUpdateException
            );
        }

        log.error(
                "Belge işleme kalıcı olarak başarısız. documentId={}, retryCount={}, error={}",
                job.documentId(),
                retryCount,
                rootErrorMessage(exception)
        );
        throw new AmqpRejectAndDontRequeueException(
                "Belge işleme kalıcı olarak başarısız; mesaj DLQ'ya yönlendiriliyor.",
                exception
        );
    }

    private void publishRetry(DocumentProcessingJob job, int retryCount, Exception exception) {
        rabbitTemplate.convertAndSend(retryExchange, retryRoutingKey, job, message -> {
            message.getMessageProperties().setDeliveryMode(MessageDeliveryMode.PERSISTENT);
            message.getMessageProperties().setHeader(RETRY_COUNT_HEADER, retryCount);
            message.getMessageProperties().setHeader(
                    LAST_ERROR_HEADER,
                    truncate(rootErrorMessage(exception), 1000)
            );
            return message;
        });
    }

    private int normalizedRetryCount(Integer retryCount) {
        return retryCount == null ? 0 : Math.max(0, retryCount);
    }

    private boolean isRetryable(Exception exception) {
        Throwable current = exception;
        while (current != null) {
            if (current instanceof ResourceAccessException
                    || current instanceof CannotGetJdbcConnectionException
                    || current instanceof QueryTimeoutException
                    || current instanceof TransientDataAccessException) {
                return true;
            }
            if (current instanceof HttpStatusCodeException httpException) {
                int status = httpException.getStatusCode().value();
                return status >= 500 || status == 408 || status == 425 || status == 429;
            }
            current = current.getCause();
        }
        return false;
    }

    private String rootErrorMessage(Exception exception) {
        Throwable current = exception;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current.getMessage() == null ? current.getClass().getSimpleName() : current.getMessage();
    }

    private boolean documentExists(Long documentId) {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM documents WHERE id = ?",
                Integer.class,
                documentId
        );
        return count != null && count > 0;
    }

    private AiIngestResponse sendStoredFileToAiService(DocumentProcessingJob job) throws Exception {
        if (job.storedPath() == null || job.storedPath().isBlank()) {
            throw new IllegalStateException("Belgenin saklanan dosya yolu bulunamadı.");
        }

        Path path = Path.of(job.storedPath());
        if (!Files.isRegularFile(path)) {
            throw new IllegalStateException("Belgenin saklanan dosyası bulunamadı: " + job.storedPath());
        }

        byte[] bytes = Files.readAllBytes(path);
        String filename = job.originalFilename() == null || job.originalFilename().isBlank()
                ? path.getFileName().toString()
                : job.originalFilename();

        ByteArrayResource fileResource = new ByteArrayResource(bytes) {
            @Override
            public String getFilename() {
                return filename;
            }
        };

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("documentId", job.documentId().toString());
        if (job.ownerId() != null) {
            body.add("ownerId", job.ownerId().toString());
        }
        if (job.departmentId() != null) {
            body.add("departmentId", job.departmentId().toString());
        }
        body.add("file", fileResource);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        ResponseEntity<AiIngestResponse> response = restTemplate.postForEntity(
                aiBaseUrl + "/api/ingest",
                new HttpEntity<>(body, headers),
                AiIngestResponse.class
        );

        if (!response.getStatusCode().is2xxSuccessful() || response.getBody() == null) {
            throw new IllegalStateException("AI servisi belgeyi işleyemedi.");
        }
        return response.getBody();
    }

    private void deleteAiIndex(Long documentId) {
        try {
            restTemplate.delete(aiBaseUrl + "/api/index/{documentId}", documentId.toString());
        } catch (Exception exception) {
            System.err.println("Silinmiş belge için AI indeksi temizlenemedi: " + exception.getMessage());
        }
    }

    private void markReady(Long documentId, Integer chunkCount) {
        jdbcTemplate.update(
                """
                UPDATE documents
                SET status = ?, chunk_count = ?, error_message = NULL, updated_at = NOW()
                WHERE id = ?
                """,
                DocumentStatus.READY.name(),
                chunkCount,
                documentId
        );
    }

    private void markFailed(DocumentProcessingJob job, Exception exception) {
        DocumentStatus failedStatus = failedStatusFor(job);
        String message = errorMessageFor(job, exception);
        jdbcTemplate.update(
                """
                UPDATE documents
                SET status = ?, error_message = ?, updated_at = NOW()
                WHERE id = ?
                """,
                failedStatus.name(),
                truncate(message, 2000),
                job.documentId()
        );
    }

    private DocumentStatus failedStatusFor(DocumentProcessingJob job) {
        if (job.operation() == DocumentProcessingOperation.REINDEX && job.previousStatus() == DocumentStatus.READY) {
            return DocumentStatus.READY;
        }
        return DocumentStatus.FAILED;
    }

    private String errorMessageFor(DocumentProcessingJob job, Exception exception) {
        String message = exception.getMessage() == null ? exception.getClass().getSimpleName() : exception.getMessage();
        if (job.operation() == DocumentProcessingOperation.REINDEX) {
            return "Yeniden indeksleme başarısız: " + message;
        }
        return "Belge işleme başarısız: " + message;
    }

    private String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }
}
