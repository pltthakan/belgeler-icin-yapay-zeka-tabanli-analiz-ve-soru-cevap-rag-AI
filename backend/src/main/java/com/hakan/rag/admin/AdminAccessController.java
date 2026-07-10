package com.hakan.rag.admin;

import com.hakan.rag.audit.AuditLog;
import com.hakan.rag.audit.AuditLogRepository;
import com.hakan.rag.department.Department;
import com.hakan.rag.department.DepartmentRepository;
import com.hakan.rag.llm.LlmTrace;
import com.hakan.rag.llm.LlmTraceRepository;
import com.hakan.rag.user.User;
import com.hakan.rag.user.UserRepository;
import com.hakan.rag.user.UserRole;
import com.hakan.rag.util.CurrentUserService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin")
public class AdminAccessController {
    private final CurrentUserService currentUserService;
    private final DepartmentRepository departmentRepository;
    private final UserRepository userRepository;
    private final AuditLogRepository auditLogRepository;
    private final LlmTraceRepository llmTraceRepository;
    private final RestTemplate restTemplate;
    private final String aiBaseUrl;

    public AdminAccessController(
            CurrentUserService currentUserService,
            DepartmentRepository departmentRepository,
            UserRepository userRepository,
            AuditLogRepository auditLogRepository,
            LlmTraceRepository llmTraceRepository,
            RestTemplate restTemplate,
            @Value("${app.ai.base-url}") String aiBaseUrl
    ) {
        this.currentUserService = currentUserService;
        this.departmentRepository = departmentRepository;
        this.userRepository = userRepository;
        this.auditLogRepository = auditLogRepository;
        this.llmTraceRepository = llmTraceRepository;
        this.restTemplate = restTemplate;
        this.aiBaseUrl = aiBaseUrl;
    }

    @PostMapping("/departments")
    public ResponseEntity<DepartmentResponse> createDepartment(@Valid @RequestBody CreateDepartmentRequest request) {
        currentUserService.requireAdmin();
        String name = request.name().trim();
        if (departmentRepository.findByNameIgnoreCase(name).isPresent()) {
            throw new IllegalArgumentException("Bu departman zaten mevcut.");
        }
        Department department = new Department();
        department.setName(name);
        return ResponseEntity.ok(DepartmentResponse.from(departmentRepository.save(department)));
    }

    @GetMapping("/departments")
    public ResponseEntity<List<DepartmentResponse>> listDepartments() {
        currentUserService.requireAdmin();
        return ResponseEntity.ok(departmentRepository.findAllByOrderByNameAsc().stream()
                .map(DepartmentResponse::from)
                .toList());
    }

    @GetMapping("/users")
    public ResponseEntity<List<UserAccessResponse>> listUsers() {
        currentUserService.requireAdmin();
        return ResponseEntity.ok(userRepository.findAll().stream()
                .map(UserAccessResponse::from)
                .toList());
    }

    @PutMapping("/users/{userId}/access")
    public ResponseEntity<UserAccessResponse> updateUserAccess(
            @PathVariable Long userId,
            @Valid @RequestBody UpdateUserAccessRequest request
    ) {
        currentUserService.requireAdmin();
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("Kullanıcı bulunamadı."));
        Department department = request.departmentId() == null ? null : departmentRepository.findById(request.departmentId())
                .orElseThrow(() -> new IllegalArgumentException("Departman bulunamadı."));
        user.setRole(request.role());
        user.setDepartment(department);
        return ResponseEntity.ok(UserAccessResponse.from(userRepository.save(user)));
    }

    @GetMapping("/audit-logs")
    public ResponseEntity<List<AuditLogResponse>> auditLogs(@RequestParam(required = false) Long documentId) {
        currentUserService.requireAdmin();
        List<AuditLog> logs = documentId == null
                ? auditLogRepository.findTop100ByOrderByCreatedAtDesc()
                : auditLogRepository.findTop100ByDocumentIdOrderByCreatedAtDesc(documentId);
        return ResponseEntity.ok(logs.stream().map(AuditLogResponse::from).toList());
    }

    @GetMapping("/llm-traces")
    public ResponseEntity<List<LlmTraceResponse>> llmTraces(@RequestParam(required = false) Long documentId) {
        currentUserService.requireAdmin();
        List<LlmTrace> traces = documentId == null
                ? llmTraceRepository.findTop100ByOrderByCreatedAtDesc()
                : llmTraceRepository.findTop100ByDocumentIdOrderByCreatedAtDesc(documentId);
        return ResponseEntity.ok(traces.stream().map(LlmTraceResponse::from).toList());
    }

    @GetMapping("/quality-summary")
    public ResponseEntity<QualitySummaryResponse> qualitySummary() {
        currentUserService.requireAdmin();
        List<Object[]> metricRows = llmTraceRepository.qualityMetrics();
        Object[] metrics = metricRows.isEmpty() ? new Object[] {0, 0, 0, 0, 0} : metricRows.get(0);
        long totalRequests = longValue(metrics[0]);
        long successfulRequests = longValue(metrics[1]);
        long failedRequests = longValue(metrics[2]);
        double averageResponseTimeMs = doubleValue(metrics[3]);
        long ollamaResponses = longValue(metrics[4]);
        long fallbackResponses = successfulRequests - ollamaResponses;
        double successRate = totalRequests == 0 ? 0 : successfulRequests * 100.0 / totalRequests;

        return ResponseEntity.ok(new QualitySummaryResponse(
                totalRequests,
                successfulRequests,
                failedRequests,
                roundOneDecimal(successRate),
                roundOneDecimal(averageResponseTimeMs),
                ollamaResponses,
                fallbackResponses
        ));
    }

    @GetMapping("/cache-summary")
    public ResponseEntity<CacheSummaryResponse> cacheSummary() {
        currentUserService.requireAdmin();
        return ResponseEntity.ok(loadCacheSummary());
    }

    @SuppressWarnings("unchecked")
    private CacheSummaryResponse loadCacheSummary() {
        try {
            Map<String, Object> health = restTemplate.getForObject(aiBaseUrl + "/api/health", Map.class);
            Map<?, ?> cache = mapValue(health, "cache");
            Map<?, ?> ttlSeconds = mapValue(cache, "ttlSeconds");
            Map<?, ?> metrics = mapValue(cache, "metrics");
            return new CacheSummaryResponse(
                    "UP",
                    booleanValue(cache.get("configured")),
                    booleanValue(cache.get("enabled")),
                    stringValue(cache.get("prefix")),
                    longValue(ttlSeconds.get("answer")),
                    longValue(ttlSeconds.get("embedding")),
                    longValue(ttlSeconds.get("profile")),
                    longValue(metrics.get("hits")),
                    longValue(metrics.get("misses")),
                    longValue(metrics.get("reads")),
                    roundOneDecimal(doubleValue(metrics.get("hitRate"))),
                    longValue(metrics.get("sets")),
                    longValue(metrics.get("deletes")),
                    longValue(metrics.get("deletePatterns")),
                    longValue(metrics.get("errors")),
                    null
            );
        } catch (Exception exception) {
            return new CacheSummaryResponse(
                    "DOWN",
                    false,
                    false,
                    "",
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    exception.getMessage()
            );
        }
    }

    private static Map<?, ?> mapValue(Map<?, ?> source, String key) {
        if (source == null) {
            return Map.of();
        }
        Object value = source.get(key);
        return value instanceof Map<?, ?> map ? map : Map.of();
    }

    private static long longValue(Object value) {
        return value instanceof Number number ? number.longValue() : 0;
    }

    private static double doubleValue(Object value) {
        return value instanceof Number number ? number.doubleValue() : 0;
    }

    private static double roundOneDecimal(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    private static boolean booleanValue(Object value) {
        return value instanceof Boolean bool && bool;
    }

    private static String stringValue(Object value) {
        return value == null ? "" : value.toString();
    }

    public record CreateDepartmentRequest(@NotBlank String name) {}
    public record UpdateUserAccessRequest(@NotNull UserRole role, Long departmentId) {}
    public record DepartmentResponse(Long id, String name) {
        static DepartmentResponse from(Department department) {
            return new DepartmentResponse(department.getId(), department.getName());
        }
    }
    public record UserAccessResponse(Long id, String name, String email, UserRole role, Long departmentId) {
        static UserAccessResponse from(User user) {
            return new UserAccessResponse(user.getId(), user.getName(), user.getEmail(), user.getRole(),
                    user.getDepartment() == null ? null : user.getDepartment().getId());
        }
    }
    public record AuditLogResponse(Long id, Long actorId, String actorEmail, Long documentId, String action,
                                   String details, LocalDateTime createdAt) {
        static AuditLogResponse from(AuditLog log) {
            return new AuditLogResponse(log.getId(), log.getActorId(), log.getActorEmail(), log.getDocumentId(),
                    log.getAction().name(), log.getDetails(), log.getCreatedAt());
        }
    }
    public record LlmTraceResponse(Long id, Long actorId, String actorEmail, Long documentId, String provider,
                                   String model, String responseMode, Long durationMs, String prompt,
                                   String retrievedChunksJson, String answer, String error, LocalDateTime createdAt) {
        static LlmTraceResponse from(LlmTrace trace) {
            return new LlmTraceResponse(trace.getId(), trace.getActorId(), trace.getActorEmail(), trace.getDocumentId(),
                    trace.getProvider(), trace.getModel(), trace.getResponseMode(), trace.getDurationMs(), trace.getPrompt(),
                    trace.getRetrievedChunksJson(), trace.getAnswer(), trace.getError(), trace.getCreatedAt());
        }
    }
    public record QualitySummaryResponse(long totalRequests, long successfulRequests, long failedRequests,
                                         double successRate, double averageResponseTimeMs, long ollamaResponses,
                                         long fallbackResponses) {}
    public record CacheSummaryResponse(String status, boolean configured, boolean enabled, String prefix,
                                       long answerTtlSeconds, long embeddingTtlSeconds, long profileTtlSeconds,
                                       long hits, long misses, long reads, double hitRate, long sets, long deletes,
                                       long deletePatterns, long errors, String error) {}
}
