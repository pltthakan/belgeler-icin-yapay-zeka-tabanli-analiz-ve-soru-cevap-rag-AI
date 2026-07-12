from __future__ import annotations

import time
from typing import Any, Dict, List

import numpy as np


class HybridRetrieverMixin:
    def _answer_question_from_pgvector(
        self,
        document_id: str,
        question: str,
        retrieval_question: str,
        top_k: int,
        document_profile: Dict[str, Any],
        started_at: float,
    ) -> Dict[str, Any]:
        response_mode = self._classify_response_mode(question)
        ordered_result = self._answer_order_sensitive_question(
            question=question,
            chunks=self._vector_store.all_chunks(document_id),
            document_profile=document_profile,
            top_k=top_k,
            started_at=started_at,
        )
        if ordered_result is not None:
            return ordered_result

        if response_mode == "summary":
            selected_sources = self._vector_store.initial_chunks(document_id, top_k)
        else:
            question_embedding = self._embed_question(retrieval_question)
            selected_sources = self._vector_store.hybrid_search(
                document_id,
                retrieval_question,
                question_embedding,
                self._retrieval_candidate_count(top_k),
            )
            selected_sources = self._rerank_sources(retrieval_question, selected_sources, top_k)
        selected_sources = self._repair_sources_text(selected_sources)

        guard_result = self._relevance_guard_result(retrieval_question, selected_sources)
        if guard_result is not None:
            return self._answer_result_from_guard(guard_result, started_at)

        answer, generation = self._build_answer_result(question, selected_sources, document_profile)
        return self._build_answer_payload(
            question=question,
            answer=answer,
            sources=selected_sources,
            generation=generation,
            duration_ms=(time.perf_counter() - started_at) * 1000,
        )

    def _hybrid_sources_from_memory(
        self,
        chunks: List[Dict[str, Any]],
        dense_scores,
        question: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        dense_candidates = []
        dense_indices = np.argsort(dense_scores)[::-1][:max(top_k * 5, top_k, 1)]
        for rank, index in enumerate(dense_indices, start=1):
            chunk = chunks[int(index)]
            dense_candidates.append({
                **self._source_from_chunk(chunk, float(dense_scores[int(index)])),
                "denseScore": float(dense_scores[int(index)]),
                "denseRank": rank,
            })

        question_terms = self._meaningful_terms(question)
        sparse_candidates = []
        if question_terms:
            for chunk in chunks:
                sparse_score = self._lexical_retrieval_score(question_terms, chunk.get("text", ""))
                if sparse_score > 0:
                    sparse_candidates.append({
                        **self._source_from_chunk(chunk, sparse_score),
                        "sparseScore": sparse_score,
                    })
            sparse_candidates.sort(key=lambda source: source["sparseScore"], reverse=True)
            for rank, source in enumerate(sparse_candidates, start=1):
                source["sparseRank"] = rank

        return self._merge_retrieval_candidates(dense_candidates, sparse_candidates, top_k)

    def _merge_retrieval_candidates(
        self,
        dense_candidates: List[Dict[str, Any]],
        sparse_candidates: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        merged: Dict[int, Dict[str, Any]] = {}
        for source in dense_candidates:
            key = int(source.get("chunkIndex", 0))
            merged[key] = {
                **source,
                "denseScore": float(source.get("denseScore", source.get("score", 0.0))),
                "denseRank": int(source.get("denseRank", len(dense_candidates) + 1)),
                "sparseScore": 0.0,
                "sparseRank": None,
            }

        for source in sparse_candidates:
            key = int(source.get("chunkIndex", 0))
            existing = merged.get(key)
            if existing is None:
                merged[key] = {
                    **source,
                    "denseScore": 0.0,
                    "denseRank": None,
                    "sparseScore": float(source.get("sparseScore", source.get("score", 0.0))),
                    "sparseRank": int(source.get("sparseRank", len(sparse_candidates) + 1)),
                }
            else:
                existing["sparseScore"] = float(source.get("sparseScore", source.get("score", 0.0)))
                existing["sparseRank"] = int(source.get("sparseRank", len(sparse_candidates) + 1))

        for source in merged.values():
            dense_rank = source.get("denseRank")
            sparse_rank = source.get("sparseRank")
            hybrid_score = 0.0
            if dense_rank is not None:
                hybrid_score += 1.0 / (60 + int(dense_rank))
            if sparse_rank is not None:
                hybrid_score += 1.0 / (60 + int(sparse_rank))
            source["hybridScore"] = hybrid_score
            source["score"] = max(float(source.get("denseScore", 0.0)), float(source.get("sparseScore", 0.0)))
            source["retrievalStrategy"] = "hybrid"

        return sorted(
            merged.values(),
            key=lambda source: (source["hybridScore"], source["score"]),
            reverse=True,
        )[:max(top_k, 1)]

    def _lexical_retrieval_score(self, question_terms: set[str], text: str) -> float:
        source_terms = self._meaningful_terms(text)
        if not question_terms or not source_terms:
            return 0.0
        matches = sum(1 for term in question_terms if self._has_matching_term(term, source_terms))
        return matches / len(question_terms)

    def _has_matching_term(self, question_term: str, source_terms: set[str]) -> bool:
        for source_term in source_terms:
            shortest = min(len(question_term), len(source_term))
            if question_term == source_term:
                return True
            if shortest >= 3 and (
                question_term in source_term
                or source_term in question_term
            ):
                return True
            if shortest >= 5 and (
                question_term.startswith(source_term[:shortest])
                or source_term.startswith(question_term[:shortest])
            ):
                return True
        return False

    def _retrieval_candidate_count(self, top_k: int) -> int:
        if not self.reranker_enabled:
            return max(top_k, 1)
        return max(top_k, self.reranker_candidate_count, 1)
