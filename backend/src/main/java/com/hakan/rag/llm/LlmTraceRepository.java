package com.hakan.rag.llm;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface LlmTraceRepository extends JpaRepository<LlmTrace, Long> {
    List<LlmTrace> findTop100ByOrderByCreatedAtDesc();
    List<LlmTrace> findTop100ByDocumentIdOrderByCreatedAtDesc(Long documentId);
}
