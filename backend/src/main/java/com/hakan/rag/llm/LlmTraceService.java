package com.hakan.rag.llm;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hakan.rag.chat.dto.AiAskResponse;
import com.hakan.rag.document.DocumentFile;
import com.hakan.rag.user.User;
import org.springframework.stereotype.Service;

import java.util.Map;

@Service
public class LlmTraceService {
    private final LlmTraceRepository llmTraceRepository;
    private final ObjectMapper objectMapper;

    public LlmTraceService(LlmTraceRepository llmTraceRepository, ObjectMapper objectMapper) {
        this.llmTraceRepository = llmTraceRepository;
        this.objectMapper = objectMapper;
    }

    public void recordSuccess(User actor, DocumentFile document, AiAskResponse response) {
        Map<String, Object> trace = response.trace() == null ? Map.of() : response.trace();
        LlmTrace entry = newEntry(actor, document);
        entry.setProvider(stringValue(trace.get("provider")));
        entry.setModel(stringValue(trace.get("model")));
        entry.setResponseMode(stringValue(trace.get("responseMode")));
        entry.setDurationMs(longValue(trace.get("durationMs")));
        entry.setPrompt(stringValue(trace.get("prompt")));
        entry.setRetrievedChunksJson(toJson(trace.getOrDefault("retrievedChunks", response.sources())));
        entry.setAnswer(response.answer());
        llmTraceRepository.save(entry);
    }

    public void recordFailure(User actor, DocumentFile document, long durationMs, Exception exception) {
        LlmTrace entry = newEntry(actor, document);
        entry.setProvider("ai-service-error");
        entry.setDurationMs(Math.max(0, durationMs));
        entry.setError(exception.getClass().getSimpleName() + ": " + exception.getMessage());
        llmTraceRepository.save(entry);
    }

    private LlmTrace newEntry(User actor, DocumentFile document) {
        LlmTrace entry = new LlmTrace();
        entry.setActorId(actor.getId());
        entry.setActorEmail(actor.getEmail());
        entry.setDocumentId(document.getId());
        return entry;
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            return "[]";
        }
    }

    private String stringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private Long longValue(Object value) {
        if (value instanceof Number number) {
            return number.longValue();
        }
        try {
            return value == null ? null : Long.valueOf(String.valueOf(value));
        } catch (NumberFormatException exception) {
            return null;
        }
    }
}
