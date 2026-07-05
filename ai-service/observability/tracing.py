from __future__ import annotations

from typing import Any, Dict, List


class TracingMixin:
    def _build_trace(
        self,
        generation: Dict[str, Any],
        selected_sources: List[Dict[str, Any]],
        duration_ms: float,
    ) -> Dict[str, Any]:
        """İstek başına bağımsız, saklanabilir RAG/LLM iz verisi üretir."""
        return {
            **generation,
            "durationMs": max(0, round(duration_ms)),
            "retrievedChunks": selected_sources,
        }
