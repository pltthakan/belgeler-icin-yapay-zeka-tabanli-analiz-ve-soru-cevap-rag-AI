from __future__ import annotations

import time
from typing import Any, Dict

from .cache import stable_hash


class CacheMixin:
    def _get_cached_profile_record(self, document_id: str, index_version: str) -> Dict[str, Any] | None:
        cache_key = f"profile:{document_id}:{stable_hash(index_version)[:16]}"
        cached_record = self.cache.get_json(cache_key)
        if self._is_valid_profile_record(cached_record):
            return cached_record

        profile_record = self._vector_store.get_profile_record(document_id)
        if (
            self._is_valid_profile_record(profile_record)
            and str(profile_record["indexVersion"]) == str(index_version)
        ):
            self.cache.set_json(cache_key, profile_record, self.cache.profile_ttl_seconds)
            return profile_record
        return None

    def _get_cached_answer(
        self,
        document_id: str,
        question: str,
        top_k: int,
        index_version: str,
        started_at: float,
    ) -> Dict[str, Any] | None:
        cached_result = self.cache.get_json(self._answer_cache_key(document_id, question, top_k, index_version))
        if not isinstance(cached_result, dict) or "answer" not in cached_result:
            return None

        trace = cached_result.get("trace")
        if not isinstance(trace, dict):
            trace = {}
        cached_result["trace"] = {
            **trace,
            "cacheHit": True,
            "cacheProvider": "redis",
            "durationMs": max(0, round((time.perf_counter() - started_at) * 1000)),
        }
        return cached_result

    def _cache_answer(
        self,
        document_id: str,
        question: str,
        top_k: int,
        index_version: str,
        result: Dict[str, Any],
    ) -> None:
        if not isinstance(result, dict) or "answer" not in result:
            return
        trace = result.get("trace")
        if not isinstance(trace, dict):
            trace = {}
        result["trace"] = {
            **trace,
            "cacheHit": False,
            "cacheProvider": "redis" if self.cache.enabled else "disabled",
        }
        cache_key = self._answer_cache_key(document_id, question, top_k, index_version)
        self.cache.set_json(cache_key, result, self.cache.answer_ttl_seconds)

    def _answer_cache_key(self, document_id: str, question: str, top_k: int, index_version: str) -> str:
        question_hash = stable_hash(self._normalize_cache_text(question))
        index_hash = stable_hash(str(index_version))[:16]
        model_hash = stable_hash(self._answer_model_cache_key())[:16]
        return f"answer:{document_id}:{index_hash}:topK:{max(top_k, 1)}:model:{model_hash}:question:{question_hash}"

    def _answer_model_cache_key(self) -> str:
        llm_key = f"ollama:{self.ollama_model}" if self.ollama_base_url and self.ollama_model else "ollama:none"
        return "|".join((
            "engine-cache-v6-evidence-aware-percentage",
            f"embedding:{self.embedding_model_name}",
            f"qa:{'disabled' if self.disable_qa_model else self.qa_model_name}",
            llm_key,
            f"reranker:{self.reranker_model_name if self.reranker_enabled else 'disabled'}",
            f"rerankerCandidates:{self.reranker_candidate_count}",
            f"minScore:{self.min_retrieval_score}",
        ))

    def _invalidate_document_cache(self, document_id: str) -> None:
        self.cache.delete_pattern(f"profile:{document_id}:*")
        self.cache.delete_pattern(f"answer:{document_id}:*")

    def _json_index_version(self, document_id: str) -> str:
        index_path = self._index_path(document_id)
        try:
            return str(index_path.stat().st_mtime_ns)
        except FileNotFoundError:
            return "missing"

    def _is_valid_profile_record(self, value: Any) -> bool:
        return (
            isinstance(value, dict)
            and isinstance(value.get("profile"), dict)
            and bool(value.get("indexVersion"))
        )

    def _normalize_cache_text(self, text: str) -> str:
        return self._normalize_whitespace(text).casefold()
