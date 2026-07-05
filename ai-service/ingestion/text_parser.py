from __future__ import annotations

from typing import Any, Dict, List


class TextParserMixin:
    def _extract_text_pages(self, raw_bytes: bytes) -> List[Dict[str, Any]]:
        text = raw_bytes.decode("utf-8", errors="ignore")
        cleaned = self._clean_text(text)
        return [{"pageNumber": 1, "text": cleaned}] if cleaned else []
