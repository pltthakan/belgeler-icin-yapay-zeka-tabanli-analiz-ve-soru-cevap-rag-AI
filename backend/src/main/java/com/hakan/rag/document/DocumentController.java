package com.hakan.rag.document;

import com.hakan.rag.chat.ChatMessageRepository;
import com.hakan.rag.document.dto.AiIngestResponse;
import com.hakan.rag.document.dto.DocumentResponse;
import com.hakan.rag.user.User;
import com.hakan.rag.util.CurrentUserService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
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

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentRepository documentRepository;
    private final ChatMessageRepository chatMessageRepository;
    private final CurrentUserService currentUserService;
    private final RestTemplate restTemplate;

    @Value("${app.upload-dir}")
    private String uploadDir;

    @Value("${app.ai.base-url}")
    private String aiBaseUrl;

    public DocumentController(DocumentRepository documentRepository,
                              ChatMessageRepository chatMessageRepository,
                              CurrentUserService currentUserService,
                              RestTemplate restTemplate) {
        this.documentRepository = documentRepository;
        this.chatMessageRepository = chatMessageRepository;
        this.currentUserService = currentUserService;
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
        document.setOriginalFilename(file.getOriginalFilename());
        document.setContentType(file.getContentType());
        document.setFileSize(file.getSize());
        document.setStoredPath(targetPath.toString());
        document.setStatus(DocumentStatus.PROCESSING);
        documentRepository.save(document);

        try {
            AiIngestResponse aiResponse = sendFileToAiService(document.getId(), file);
            document.setStatus(DocumentStatus.READY);
            document.setChunkCount(aiResponse.chunkCount());
            document.setErrorMessage(null);
        } catch (Exception ex) {
            document.setStatus(DocumentStatus.FAILED);
            document.setErrorMessage(ex.getMessage());
        }

        documentRepository.save(document);
        return ResponseEntity.ok(DocumentResponse.from(document));
    }

    @GetMapping
    public ResponseEntity<List<DocumentResponse>> list() {
        User user = currentUserService.getCurrentUser();
        List<DocumentResponse> documents = documentRepository.findByOwnerOrderByCreatedAtDesc(user)
                .stream()
                .map(DocumentResponse::from)
                .toList();
        return ResponseEntity.ok(documents);
    }

    @GetMapping("/{id}")
    public ResponseEntity<DocumentResponse> get(@PathVariable Long id) {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentRepository.findByIdAndOwner(id, user)
                .orElseThrow(() -> new IllegalArgumentException("Belge bulunamadı."));
        return ResponseEntity.ok(DocumentResponse.from(document));
    }

    @PostMapping("/{id}/reindex")
    public ResponseEntity<DocumentResponse> reindex(@PathVariable Long id) throws Exception {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentRepository.findByIdAndOwner(id, user)
                .orElseThrow(() -> new IllegalArgumentException("Belge bulunamadı."));

        DocumentStatus previousStatus = document.getStatus();
        document.setStatus(DocumentStatus.PROCESSING);
        document.setErrorMessage(null);
        documentRepository.save(document);

        try {
            AiIngestResponse aiResponse = sendStoredFileToAiService(document);
            document.setStatus(DocumentStatus.READY);
            document.setChunkCount(aiResponse.chunkCount());
            document.setErrorMessage(null);
        } catch (Exception ex) {
            // AI servisi indeksi atomik güncellediği için önceki başarılı indeks
            // kullanılabilir durumda kalır. Eski READY durumunu koru.
            document.setStatus(previousStatus == DocumentStatus.READY ? DocumentStatus.READY : DocumentStatus.FAILED);
            document.setErrorMessage("Yeniden indeksleme başarısız: " + ex.getMessage());
        }

        documentRepository.save(document);
        return ResponseEntity.ok(DocumentResponse.from(document));
    }

    @DeleteMapping("/{id}")
    @Transactional
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentRepository.findByIdAndOwner(id, user)
                .orElseThrow(() -> new IllegalArgumentException("Belge bulunamadı."));
        chatMessageRepository.deleteByDocument(document);
        documentRepository.delete(document);
        return ResponseEntity.noContent().build();
    }

    private AiIngestResponse sendFileToAiService(Long documentId, MultipartFile file) throws Exception {
        return sendBytesToAiService(documentId, file.getBytes(), file.getOriginalFilename());
    }

    private AiIngestResponse sendStoredFileToAiService(DocumentFile document) throws Exception {
        if (document.getStoredPath() == null || document.getStoredPath().isBlank()) {
            throw new IllegalStateException("Belgenin saklanan dosya yolu bulunamadı.");
        }

        Path path = Paths.get(document.getStoredPath());
        if (!Files.isRegularFile(path)) {
            throw new IllegalStateException("Belgenin saklanan dosyası bulunamadı.");
        }
        return sendBytesToAiService(document.getId(), Files.readAllBytes(path), document.getOriginalFilename());
    }

    private AiIngestResponse sendBytesToAiService(Long documentId, byte[] bytes, String filename) {
        ByteArrayResource fileResource = new ByteArrayResource(bytes) {
            @Override
            public String getFilename() {
                return filename;
            }
        };

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("documentId", documentId.toString());
        body.add("file", fileResource);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);
        ResponseEntity<AiIngestResponse> response = restTemplate.postForEntity(
                aiBaseUrl + "/api/ingest",
                requestEntity,
                AiIngestResponse.class
        );

        if (!response.getStatusCode().is2xxSuccessful() || response.getBody() == null) {
            throw new IllegalStateException("AI servisi belgeyi işleyemedi.");
        }
        return response.getBody();
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
