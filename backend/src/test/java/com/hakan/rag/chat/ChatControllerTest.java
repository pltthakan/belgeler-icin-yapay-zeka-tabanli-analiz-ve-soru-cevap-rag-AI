package com.hakan.rag.chat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hakan.rag.audit.AuditLogService;
import com.hakan.rag.chat.dto.*;
import com.hakan.rag.document.DocumentAccessService;
import com.hakan.rag.document.DocumentFile;
import com.hakan.rag.document.DocumentStatus;
import com.hakan.rag.llm.LlmTraceService;
import com.hakan.rag.user.User;
import com.hakan.rag.util.CurrentUserService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.ResponseEntity;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ChatControllerTest {
    private ChatMessageRepository chatMessageRepository;
    private CurrentUserService currentUserService;
    private DocumentAccessService documentAccessService;
    private AuditLogService auditLogService;
    private LlmTraceService llmTraceService;
    private RestTemplate restTemplate;
    private ChatController controller;
    private User user;
    private DocumentFile document;

    @BeforeEach
    void setUp() {
        chatMessageRepository = mock(ChatMessageRepository.class);
        currentUserService = mock(CurrentUserService.class);
        documentAccessService = mock(DocumentAccessService.class);
        auditLogService = mock(AuditLogService.class);
        llmTraceService = mock(LlmTraceService.class);
        restTemplate = mock(RestTemplate.class);
        controller = new ChatController(
                chatMessageRepository,
                currentUserService,
                documentAccessService,
                auditLogService,
                llmTraceService,
                restTemplate,
                new ObjectMapper()
        );
        ReflectionTestUtils.setField(controller, "aiBaseUrl", "http://ai-service:5000");

        user = new User();
        user.setId(7L);
        user.setEmail("user@example.com");
        document = new DocumentFile();
        document.setId(11L);
        document.setOwner(user);
        document.setStatus(DocumentStatus.READY);

        when(currentUserService.getCurrentUser()).thenReturn(user);
        when(documentAccessService.getAccessibleDocument(11L, user)).thenReturn(document);
    }

    @Test
    void askPersistsAndReturnsClaimLevelCitations() throws Exception {
        SourceResponse source = new SourceResponse(2, 6, 0.91, "Fesih için 30 gün önce bildirim yapılır.");
        CitationResponse citation = new CitationResponse(
                1,
                "Fesih bildirim süresi 30 gündür.",
                0,
                2,
                6,
                "Fesih için 30 gün önce bildirim yapılır.",
                0.8
        );
        AiAskResponse aiResponse = new AiAskResponse(
                "Fesih bildirim süresi 30 gündür [1].",
                List.of(source),
                List.of(citation),
                Map.of("provider", "ollama")
        );
        when(restTemplate.postForObject(anyString(), any(AiAskRequest.class), eq(AiAskResponse.class)))
                .thenReturn(aiResponse);

        ResponseEntity<ChatMessageResponse> response = controller.ask(11L, new AskRequest("Süre kaç gündür?"));

        assertNotNull(response.getBody());
        assertEquals(1, response.getBody().citations().size());
        assertEquals(6, response.getBody().citations().get(0).chunkIndex());
        ArgumentCaptor<ChatMessage> messageCaptor = ArgumentCaptor.forClass(ChatMessage.class);
        verify(chatMessageRepository).save(messageCaptor.capture());
        assertTrue(messageCaptor.getValue().getCitationsJson().contains("\"chunkIndex\":6"));
    }

    @Test
    void historyReturnsEmptyCitationsForMessagesCreatedBeforeCitationSupport() {
        ChatMessage oldMessage = new ChatMessage();
        oldMessage.setOwner(user);
        oldMessage.setDocument(document);
        oldMessage.setQuestion("Eski soru");
        oldMessage.setAnswer("Eski cevap");
        oldMessage.setSourcesJson("[]");
        oldMessage.setCitationsJson(null);
        when(chatMessageRepository.findByOwnerAndDocumentOrderByCreatedAtAsc(user, document))
                .thenReturn(List.of(oldMessage));

        ResponseEntity<List<ChatMessageResponse>> response = controller.history(11L);

        assertNotNull(response.getBody());
        assertEquals(1, response.getBody().size());
        assertEquals(List.of(), response.getBody().get(0).citations());
    }
}
