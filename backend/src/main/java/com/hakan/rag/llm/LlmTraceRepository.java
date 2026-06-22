package com.hakan.rag.llm;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface LlmTraceRepository extends JpaRepository<LlmTrace, Long> {
    List<LlmTrace> findTop100ByOrderByCreatedAtDesc();
    List<LlmTrace> findTop100ByDocumentIdOrderByCreatedAtDesc(Long documentId);

    @Query("""
            SELECT COUNT(t),
                   COALESCE(SUM(CASE WHEN t.error IS NULL OR TRIM(t.error) = '' THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN t.error IS NOT NULL AND TRIM(t.error) <> '' THEN 1 ELSE 0 END), 0),
                   COALESCE(AVG(t.durationMs), 0),
                   COALESCE(SUM(CASE WHEN (t.error IS NULL OR TRIM(t.error) = '')
                                      AND t.provider LIKE 'ollama%' THEN 1 ELSE 0 END), 0)
            FROM LlmTrace t
            """)
    List<Object[]> qualityMetrics();
}
