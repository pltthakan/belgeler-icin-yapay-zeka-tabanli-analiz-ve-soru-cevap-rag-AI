from __future__ import annotations

import io
from typing import Any, Dict, List

from pypdf import PdfReader


class PdfParserMixin:
    def _extract_pdf_pages(self, raw_bytes: bytes) -> List[Dict[str, Any]]:
        reader = PdfReader(io.BytesIO(raw_bytes))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            text = self._extract_pdf_page_text(page, raw_bytes, i)
            cleaned = self._clean_text(text)
            if cleaned:
                pages.append({"pageNumber": i, "text": cleaned})
        return pages

    def _extract_pdf_page_text(self, page, raw_bytes: bytes, page_number: int) -> str:
        try:
            return page.extract_text() or ""
        except Exception as exc:
            print(f"pypdf sayfa {page_number} metin çıkarımı başarısız, PyMuPDF deneniyor: {exc}")
            return self._extract_pdf_page_text_with_pymupdf(raw_bytes, page_number)

    def _extract_pdf_page_text_with_pymupdf(self, raw_bytes: bytes, page_number: int) -> str:
        try:
            import fitz

            with fitz.open(stream=raw_bytes, filetype="pdf") as document:
                if page_number < 1 or page_number > document.page_count:
                    return ""
                page = document.load_page(page_number - 1)
                return page.get_text("text") or ""
        except Exception as exc:
            print(f"PyMuPDF sayfa {page_number} metin çıkarımı başarısız: {exc}")
            return ""
