package com.hakan.rag.worker;

import com.hakan.rag.document.DocumentStatus;
import com.hakan.rag.document.queue.DocumentProcessingJob;
import com.hakan.rag.document.queue.DocumentProcessingOperation;
import com.hakan.rag.worker.dto.AiIngestResponse;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;

import java.nio.file.Files;
import java.nio.file.Path;

@Component
public class DocumentProcessingListener {
    private final JdbcTemplate jdbcTemplate;
    private final RestTemplate restTemplate;
    private final String aiBaseUrl;

    public DocumentProcessingListener(
            JdbcTemplate jdbcTemplate,
            RestTemplate restTemplate,
            @Value("${app.ai.base-url}") String aiBaseUrl
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.restTemplate = restTemplate;
        this.aiBaseUrl = aiBaseUrl;
    }

    @RabbitListener(queues = "${app.rabbitmq.document-processing.queue}")
    public void process(DocumentProcessingJob job) {
        if (job == null || job.documentId() == null) {
            return;
        }
        if (!documentExists(job.documentId())) {
            return;
        }

        try {
            AiIngestResponse response = sendStoredFileToAiService(job);
            if (documentExists(job.documentId())) {
                markReady(job.documentId(), response.chunkCount());
            } else {
                deleteAiIndex(job.documentId());
            }
        } catch (Exception exception) {
            markFailed(job, exception);
        }
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
