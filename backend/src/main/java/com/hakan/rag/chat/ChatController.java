package com.hakan.rag.chat;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hakan.rag.audit.AuditAction;
import com.hakan.rag.audit.AuditLogService;
import com.hakan.rag.chat.dto.*;
import com.hakan.rag.document.DocumentAccessService;
import com.hakan.rag.document.DocumentFile;
import com.hakan.rag.document.DocumentStatus;
import com.hakan.rag.llm.LlmTraceService;
import com.hakan.rag.user.User;
import com.hakan.rag.util.CurrentUserService;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

import java.util.Collections;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/chat")
public class ChatController {

    private final ChatMessageRepository chatMessageRepository;
    private final CurrentUserService currentUserService;
    private final DocumentAccessService documentAccessService;
    private final AuditLogService auditLogService;
    private final LlmTraceService llmTraceService;
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;

    @Value("${app.ai.base-url}")
    private String aiBaseUrl;

    public ChatController(ChatMessageRepository chatMessageRepository,
                          CurrentUserService currentUserService,
                          DocumentAccessService documentAccessService,
                          AuditLogService auditLogService,
                          LlmTraceService llmTraceService,
                          RestTemplate restTemplate,
                          ObjectMapper objectMapper) {
        this.chatMessageRepository = chatMessageRepository;
        this.currentUserService = currentUserService;
        this.documentAccessService = documentAccessService;
        this.auditLogService = auditLogService;
        this.llmTraceService = llmTraceService;
        this.restTemplate = restTemplate;
        this.objectMapper = objectMapper;
    }

    @PostMapping("/documents/{documentId}/ask")
    public ResponseEntity<ChatMessageResponse> ask(@PathVariable Long documentId,
                                                   @Valid @RequestBody AskRequest request) throws Exception {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentAccessService.getAccessibleDocument(documentId, user);

        if (document.getStatus() != DocumentStatus.READY) {
            throw new IllegalArgumentException("Belge henüz soru sormaya hazır değil. Durum: " + document.getStatus());
        }

        AiAskRequest aiRequest = new AiAskRequest(document.getId().toString(), request.question(), 4);
        long startedAt = System.nanoTime();
        AiAskResponse aiResponse;
        try {
            aiResponse = restTemplate.postForObject(aiBaseUrl + "/api/ask", aiRequest, AiAskResponse.class);
            if (aiResponse == null) {
                throw new IllegalStateException("AI servisinden cevap alınamadı.");
            }
        } catch (RuntimeException exception) {
            long durationMs = (System.nanoTime() - startedAt) / 1_000_000;
            llmTraceService.recordFailure(user, document, durationMs, exception);
            throw exception;
        }
        llmTraceService.recordSuccess(user, document, aiResponse);

        ChatMessage message = new ChatMessage();
        message.setOwner(user);
        message.setDocument(document);
        message.setQuestion(request.question());
        message.setAnswer(aiResponse.answer());
        message.setSourcesJson(objectMapper.writeValueAsString(
                aiResponse.sources() == null ? Collections.emptyList() : aiResponse.sources()
        ));
        message.setCitationsJson(objectMapper.writeValueAsString(
                aiResponse.citations() == null ? Collections.emptyList() : aiResponse.citations()
        ));
        chatMessageRepository.save(message);
        auditLogService.record(user, AuditAction.CHAT_QUESTION_ASKED, document.getId(), Map.of(
                "questionLength", request.question().length(),
                "provider", String.valueOf(aiResponse.trace() == null ? null : aiResponse.trace().get("provider"))
        ));

        return ResponseEntity.ok(toResponse(message));
    }

    @GetMapping("/documents/{documentId}/history")
    public ResponseEntity<List<ChatMessageResponse>> history(@PathVariable Long documentId) {
        User user = currentUserService.getCurrentUser();
        DocumentFile document = documentAccessService.getAccessibleDocument(documentId, user);

        List<ChatMessageResponse> history = chatMessageRepository.findByOwnerAndDocumentOrderByCreatedAtAsc(user, document)
                .stream()
                .map(this::toResponse)
                .toList();
        auditLogService.record(user, AuditAction.CHAT_HISTORY_VIEWED, document.getId(), Map.of("count", history.size()));
        return ResponseEntity.ok(history);
    }

    private ChatMessageResponse toResponse(ChatMessage message) {
        List<SourceResponse> sources = Collections.emptyList();
        List<CitationResponse> citations = Collections.emptyList();
        try {
            if (message.getSourcesJson() != null && !message.getSourcesJson().isBlank()) {
                sources = objectMapper.readValue(message.getSourcesJson(), new TypeReference<List<SourceResponse>>() {});
            }
        } catch (Exception ignored) {
        }
        try {
            if (message.getCitationsJson() != null && !message.getCitationsJson().isBlank()) {
                citations = objectMapper.readValue(
                        message.getCitationsJson(),
                        new TypeReference<List<CitationResponse>>() {}
                );
            }
        } catch (Exception ignored) {
        }
        return new ChatMessageResponse(
                message.getId(),
                message.getQuestion(),
                message.getAnswer(),
                sources,
                citations,
                message.getCreatedAt()
        );
    }
}
