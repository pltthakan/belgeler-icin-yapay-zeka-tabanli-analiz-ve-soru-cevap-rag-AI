from __future__ import annotations

import os

DATA_DIR = os.getenv("DATA_DIR", "./data")


class SettingsMixin:
    def _read_retrieval_score_threshold(self) -> float:
        try:
            value = float(os.getenv("RAG_MIN_RETRIEVAL_SCORE", "0.10"))
        except ValueError:
            value = 0.10
        return min(max(value, 0.0), 1.0)

    def _read_int_env(self, name: str, default_value: int, minimum: int, maximum: int) -> int:
        try:
            value = int(os.getenv(name, str(default_value)))
        except ValueError:
            value = default_value
        return min(max(value, minimum), maximum)
