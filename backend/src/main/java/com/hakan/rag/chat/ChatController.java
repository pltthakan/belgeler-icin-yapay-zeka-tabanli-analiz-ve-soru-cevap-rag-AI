package com.hakan.rag.chat;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hakan.rag.chat.dto.*;
import com.hakan.rag.document.DocumentFile;
import com.hakan.rag.document.DocumentRepository;
import com.hakan.rag.document.DocumentStatus;
import com.hakan.rag.user.User;
import com.hakan.rag.util.CurrentUserService;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

import java.util.Collections;
import java.util.List;

@RestController
@RequestMapping("/api/chat")
public class ChatController {

    private final ChatMessageRepository chatMessageRepository;
    private final DocumentRepository documentRepository;
    private final CurrentUserService currentUserService;
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;

    @Value("${app.ai.base-url}")
    private String aiBaseUrl;

    public ChatController(ChatMessageRepository chatMessageRepository,
                          DocumentRepository documentRepository,
                          CurrentUserService currentUserService,
                          RestTemplate restTemplate,
                          ObjectMapper objectMapper) {
        this.chatMessageRepository = chatMessageRepository;
        this.documentRepository = documentRepository;
        this.currentUserService = currentUserService;
        this.restTemplate = restTemplate;
        this.objectMapper = objectMapper;
    }

    @PostMapping("/documents/{documentId}/ask")
    public ResponseEntity<ChatMessageResponse> ask(@PathVariable Long documentId,
                                                   @Valid @RequestBody AskRequest request) throws Exception {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentRepository.findByIdAndOwner(documentId, user)
                .orElseThrow(() -> new IllegalArgumentException("Belge bulunamadı."));

        if (document.getStatus() != DocumentStatus.READY) {
            throw new IllegalArgumentException("Belge henüz soru sormaya hazır değil. Durum: " + document.getStatus());
        }

        AiAskRequest aiRequest = new AiAskRequest(document.getId().toString(), request.question(), 4);
        AiAskResponse aiResponse = restTemplate.postForObject(aiBaseUrl + "/api/ask", aiRequest, AiAskResponse.class);

        if (aiResponse == null) {
            throw new IllegalStateException("AI servisinden cevap alınamadı.");
        }

        ChatMessage message = new ChatMessage();
        message.setOwner(user);
        message.setDocument(document);
        message.setQuestion(request.question());
        message.setAnswer(aiResponse.answer());
        message.setSourcesJson(objectMapper.writeValueAsString(aiResponse.sources()));
        chatMessageRepository.save(message);

        return ResponseEntity.ok(toResponse(message));
    }

    @GetMapping("/documents/{documentId}/history")
    public ResponseEntity<List<ChatMessageResponse>> history(@PathVariable Long documentId) {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentRepository.findByIdAndOwner(documentId, user)
                .orElseThrow(() -> new IllegalArgumentException("Belge bulunamadı."));

        List<ChatMessageResponse> history = chatMessageRepository.findByOwnerAndDocumentOrderByCreatedAtAsc(user, document)
                .stream()
                .map(this::toResponse)
                .toList();
        return ResponseEntity.ok(history);
    }

    private ChatMessageResponse toResponse(ChatMessage message) {
        List<SourceResponse> sources = Collections.emptyList();
        try {
            if (message.getSourcesJson() != null && !message.getSourcesJson().isBlank()) {
                sources = objectMapper.readValue(message.getSourcesJson(), new TypeReference<List<SourceResponse>>() {});
            }
        } catch (Exception ignored) {
        }
        return new ChatMessageResponse(
                message.getId(),
                message.getQuestion(),
                message.getAnswer(),
                sources,
                message.getCreatedAt()
        );
    }
}
