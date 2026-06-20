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
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.List;

@RestController
@RequestMapping("/api/admin")
public class AdminAccessController {
    private final CurrentUserService currentUserService;
    private final DepartmentRepository departmentRepository;
    private final UserRepository userRepository;
    private final AuditLogRepository auditLogRepository;
    private final LlmTraceRepository llmTraceRepository;

    public AdminAccessController(
            CurrentUserService currentUserService,
            DepartmentRepository departmentRepository,
            UserRepository userRepository,
            AuditLogRepository auditLogRepository,
            LlmTraceRepository llmTraceRepository
    ) {
        this.currentUserService = currentUserService;
        this.departmentRepository = departmentRepository;
        this.userRepository = userRepository;
        this.auditLogRepository = auditLogRepository;
        this.llmTraceRepository = llmTraceRepository;
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
}
