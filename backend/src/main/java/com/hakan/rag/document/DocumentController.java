package com.hakan.rag.document;

import com.hakan.rag.chat.ChatMessageRepository;
import com.hakan.rag.audit.AuditAction;
import com.hakan.rag.audit.AuditLogService;
import com.hakan.rag.document.dto.DocumentResponse;
import com.hakan.rag.document.dto.DocumentSharingRequest;
import com.hakan.rag.document.queue.DocumentProcessingJob;
import com.hakan.rag.document.queue.DocumentProcessingJobPublisher;
import com.hakan.rag.document.queue.DocumentProcessingOperation;
import com.hakan.rag.user.User;
import com.hakan.rag.util.CurrentUserService;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Map;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentRepository documentRepository;
    private final ChatMessageRepository chatMessageRepository;
    private final CurrentUserService currentUserService;
    private final DocumentAccessService documentAccessService;
    private final AuditLogService auditLogService;
    private final DocumentProcessingJobPublisher documentProcessingJobPublisher;
    private final RestTemplate restTemplate;

    @Value("${app.upload-dir}")
    private String uploadDir;

    @Value("${app.ai.base-url}")
    private String aiBaseUrl;

    public DocumentController(DocumentRepository documentRepository,
                              ChatMessageRepository chatMessageRepository,
                              CurrentUserService currentUserService,
                              DocumentAccessService documentAccessService,
                              AuditLogService auditLogService,
                              DocumentProcessingJobPublisher documentProcessingJobPublisher,
                              RestTemplate restTemplate) {
        this.documentRepository = documentRepository;
        this.chatMessageRepository = chatMessageRepository;
        this.currentUserService = currentUserService;
        this.documentAccessService = documentAccessService;
        this.auditLogService = auditLogService;
        this.documentProcessingJobPublisher = documentProcessingJobPublisher;
        this.restTemplate = restTemplate;
    }

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<DocumentResponse> upload(@RequestPart("file") MultipartFile file) throws Exception {
        User user = currentUserService.getCurrentUser();

        validateFile(file);

        Path userDir = Paths.get(uploadDir, "user-" + user.getId());
        Files.createDirectories(userDir);

        String safeName = sanitizeFilename(file.getOriginalFilename());
        Path targetPath = userDir.resolve(Instant.now().toEpochMilli() + "_" + safeName);
        Files.copy(file.getInputStream(), targetPath);

        DocumentFile document = new DocumentFile();
        document.setOwner(user);
        document.setDepartment(user.getDepartment());
        document.setSharingScope(DocumentSharingScope.PRIVATE);
        document.setOriginalFilename(file.getOriginalFilename());
        document.setContentType(file.getContentType());
        document.setFileSize(file.getSize());
        document.setStoredPath(targetPath.toString());
        document.setStatus(DocumentStatus.PROCESSING);
        document.setErrorMessage(null);
        documentRepository.save(document);

        try {
            documentProcessingJobPublisher.publish(toProcessingJob(document, DocumentProcessingOperation.INGEST, null));
        } catch (Exception ex) {
            document.setStatus(DocumentStatus.FAILED);
            document.setErrorMessage("Belge işleme kuyruğuna alınamadı: " + ex.getMessage());
            documentRepository.save(document);
            throw new IllegalStateException(document.getErrorMessage());
        }

        auditLogService.record(user, AuditAction.DOCUMENT_UPLOADED, document.getId(), Map.of(
                "status", document.getStatus().name(),
                "filename", document.getOriginalFilename()
        ));
        return ResponseEntity.ok(DocumentResponse.from(document));
    }

    @GetMapping
    public ResponseEntity<List<DocumentResponse>> list() {
        User user = currentUserService.getCurrentUser();
        List<DocumentResponse> documents = documentAccessService.listAccessibleDocuments(user)
                .stream()
                .map(DocumentResponse::from)
                .toList();
        auditLogService.record(user, AuditAction.DOCUMENT_LISTED, null, Map.of("count", documents.size()));
        return ResponseEntity.ok(documents);
    }

    @GetMapping("/{id}")
    public ResponseEntity<DocumentResponse> get(@PathVariable Long id) {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentAccessService.getAccessibleDocument(id, user);
        auditLogService.record(user, AuditAction.DOCUMENT_VIEWED, document.getId(), Map.of());
        return ResponseEntity.ok(DocumentResponse.from(document));
    }

    @PostMapping("/{id}/reindex")
    public ResponseEntity<DocumentResponse> reindex(@PathVariable Long id) throws Exception {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentAccessService.getReindexableDocument(id, user);

        DocumentStatus previousStatus = document.getStatus();
        document.setStatus(DocumentStatus.PROCESSING);
        document.setErrorMessage(null);
        documentRepository.save(document);

        try {
            documentProcessingJobPublisher.publish(toProcessingJob(document, DocumentProcessingOperation.REINDEX, previousStatus));
        } catch (Exception ex) {
            document.setStatus(previousStatus == DocumentStatus.READY ? DocumentStatus.READY : DocumentStatus.FAILED);
            document.setErrorMessage("Yeniden indeksleme kuyruğa alınamadı: " + ex.getMessage());
            documentRepository.save(document);
            throw new IllegalStateException(document.getErrorMessage());
        }

        auditLogService.record(user, AuditAction.DOCUMENT_REINDEXED, document.getId(), Map.of(
                "status", document.getStatus().name(),
                "chunkCount", String.valueOf(document.getChunkCount())
        ));
        return ResponseEntity.ok(DocumentResponse.from(document));
    }

    @DeleteMapping("/{id}")
    @Transactional
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentAccessService.getManageableDocument(id, user);
        deleteAiIndex(document.getId());
        auditLogService.record(user, AuditAction.DOCUMENT_DELETED, document.getId(), Map.of(
                "filename", document.getOriginalFilename()
        ));
        chatMessageRepository.deleteByDocument(document);
        documentRepository.delete(document);
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/{id}/sharing")
    public ResponseEntity<DocumentResponse> updateSharing(
            @PathVariable Long id,
            @Valid @RequestBody DocumentSharingRequest request
    ) {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentAccessService.getManageableDocument(id, user);
        if (request.sharingScope() == DocumentSharingScope.DEPARTMENT && document.getDepartment() == null) {
            throw new IllegalArgumentException("Departman paylaşımı için belge sahibinin bir departmanı olmalıdır.");
        }
        document.setSharingScope(request.sharingScope());
        documentRepository.save(document);
        auditLogService.record(user, AuditAction.DOCUMENT_SHARED, document.getId(), Map.of(
                "sharingScope", document.getSharingScope().name(),
                "departmentId", String.valueOf(document.getDepartment() == null ? null : document.getDepartment().getId())
        ));
        return ResponseEntity.ok(DocumentResponse.from(document));
    }

    private DocumentProcessingJob toProcessingJob(
            DocumentFile document,
            DocumentProcessingOperation operation,
            DocumentStatus previousStatus
    ) {
        if (document.getStoredPath() == null || document.getStoredPath().isBlank()) {
            throw new IllegalStateException("Belgenin saklanan dosya yolu bulunamadı.");
        }
        return new DocumentProcessingJob(
                document.getId(),
                document.getOwner().getId(),
                document.getDepartment() == null ? null : document.getDepartment().getId(),
                document.getStoredPath(),
                document.getOriginalFilename(),
                operation,
                previousStatus
        );
    }

    private void deleteAiIndex(Long documentId) {
        try {
            restTemplate.delete(aiBaseUrl + "/api/index/{documentId}", documentId.toString());
        } catch (Exception exception) {
            // Belge silme, kaynak embedding'ler de silinmeden tamamlanmaz. Bu,
            // gizli belge içeriğinin vektör deposunda yetimsiz kalmasını engeller.
            throw new IllegalStateException("Belgenin AI indeksi silinemedi: " + exception.getMessage());
        }
    }

    private void validateFile(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("Dosya boş olamaz.");
        }
        String filename = file.getOriginalFilename();
        if (filename == null) {
            throw new IllegalArgumentException("Dosya adı okunamadı.");
        }
        String lower = filename.toLowerCase(Locale.ROOT);
        if (!(lower.endsWith(".pdf") || lower.endsWith(".docx") || lower.endsWith(".txt"))) {
            throw new IllegalArgumentException("Sadece PDF, DOCX ve TXT dosyaları desteklenir.");
        }
    }

    private String sanitizeFilename(String filename) {
        if (filename == null || filename.isBlank()) {
            return "document";
        }
        return filename.replaceAll("[^a-zA-Z0-9ğüşöçıİĞÜŞÖÇ._-]", "_");
    }
}
