from __future__ import annotations

from typing import Any, Dict, List


class RerankerMixin:
    def _rerank_sources(
        self,
        question: str,
        sources: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        limit = max(top_k, 1)
        if len(sources) <= limit:
            return sources[:limit]

        reranker = self._get_reranker_model()
        if reranker is None:
            return sources[:limit]

        try:
            pairs = [
                (question, self._source_text_for_reranking(source))
                for source in sources
            ]
            scores = reranker.predict(pairs, show_progress_bar=False)
            ranked_sources = []
            for source, score in zip(sources, scores):
                ranked_sources.append({
                    **source,
                    "rerankerScore": float(score),
                    "reranked": True,
                })
            return sorted(
                ranked_sources,
                key=lambda source: float(source.get("rerankerScore", 0.0)),
                reverse=True,
            )[:limit]
        except Exception as exc:
            self._log_reranker_error_once(f"Reranker sıralama hatası, mevcut retrieval sırası kullanılacak: {exc}")
            return sources[:limit]

    def _source_text_for_reranking(self, source: Dict[str, Any]) -> str:
        text = str(source.get("text", ""))
        return text[:3000]

    def _get_reranker_model(self):
        if not self.reranker_enabled:
            return None
        if self._reranker_model is not None:
            return self._reranker_model
        try:
            from sentence_transformers import CrossEncoder

            self._reranker_model = CrossEncoder(self.reranker_model_name)
            return self._reranker_model
        except Exception as exc:
            self._log_reranker_error_once(f"Reranker modeli yüklenemedi, mevcut retrieval sırası kullanılacak: {exc}")
            self._reranker_model = None
            return None

    def _log_reranker_error_once(self, message: str) -> None:
        if self._reranker_error_logged:
            return
        print(message)
        self._reranker_error_logged = True
