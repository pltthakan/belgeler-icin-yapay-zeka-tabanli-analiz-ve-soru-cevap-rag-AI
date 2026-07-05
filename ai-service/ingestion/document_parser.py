from __future__ import annotations

from typing import Any, Dict, List


class DocumentParserMixin:
    def _extract_pages(self, filename: str, raw_bytes: bytes) -> List[Dict[str, Any]]:
        lower = filename.lower()
        if lower.endswith(".pdf"):
            return self._extract_pdf_pages(raw_bytes)
        if lower.endswith(".docx"):
            return self._extract_docx_pages(raw_bytes)
        if lower.endswith(".txt"):
            return self._extract_text_pages(raw_bytes)
        raise ValueError("Desteklenmeyen dosya tipi. PDF, DOCX veya TXT yükleyin.")
