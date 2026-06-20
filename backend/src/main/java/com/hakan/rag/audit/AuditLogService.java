package com.hakan.rag.audit;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hakan.rag.user.User;
import org.springframework.stereotype.Service;

import java.util.Map;

@Service
public class AuditLogService {
    private final AuditLogRepository auditLogRepository;
    private final ObjectMapper objectMapper;

    public AuditLogService(AuditLogRepository auditLogRepository, ObjectMapper objectMapper) {
        this.auditLogRepository = auditLogRepository;
        this.objectMapper = objectMapper;
    }

    public void record(User actor, AuditAction action, Long documentId, Map<String, Object> details) {
        AuditLog log = new AuditLog();
        log.setActorId(actor.getId());
        log.setActorEmail(actor.getEmail());
        log.setDocumentId(documentId);
        log.setAction(action);
        log.setDetails(toJson(details));
        auditLogRepository.save(log);
    }

    private String toJson(Map<String, Object> details) {
        try {
            return objectMapper.writeValueAsString(details == null ? Map.of() : details);
        } catch (JsonProcessingException exception) {
            return "{\"serializationError\":true}";
        }
    }
}
