from __future__ import annotations

import re
from typing import Any, Dict, List


class HeadingChunkerMixin:
    def _chunk_pages_by_headings(self, pages: List[Dict[str, Any]], chunk_size: int) -> List[Dict[str, Any]]:
        sections = self._heading_sections(pages)
        if len([section for section in sections if section.get("heading")]) < 3:
            return []

        chunks = []
        chunk_index = 0
        for section in sections:
            text = section["text"]
            heading = section.get("heading") or ""
            page_number = section["pageNumber"]

            if len(text) <= chunk_size:
                chunk_index = self._append_chunk(chunks, chunk_index, page_number, text)
                continue

            body = text[len(heading):].strip() if heading and text.startswith(heading) else text
            available_size = max(300, chunk_size - len(heading) - 2) if heading else chunk_size
            for piece in self._split_oversized_block(body, available_size):
                chunk_text = f"{heading}\n{piece}".strip() if heading else piece
                chunk_index = self._append_chunk(chunks, chunk_index, page_number, chunk_text)

        return chunks

    def _heading_sections(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sections = []
        current = None
        for page in pages:
            page_number = page["pageNumber"]
            for line in self._page_lines(page.get("text", "")):
                if self._is_section_heading(line):
                    if current is not None:
                        sections.append(current)
                    current = {
                        "pageNumber": page_number,
                        "heading": line,
                        "lines": [line],
                    }
                    continue

                if current is None:
                    current = {
                        "pageNumber": page_number,
                        "heading": "",
                        "lines": [],
                    }
                current["lines"].append(line)

        if current is not None:
            sections.append(current)

        return [
            {
                "pageNumber": section["pageNumber"],
                "heading": section["heading"],
                "text": "\n".join(section["lines"]).strip(),
            }
            for section in sections
            if "\n".join(section["lines"]).strip()
        ]

    def _page_lines(self, text: str) -> List[str]:
        return [
            self._normalize_whitespace(line)
            for line in text.splitlines()
            if self._normalize_whitespace(line)
        ]

    def _is_section_heading(self, line: str) -> bool:
        normalized = self._normalize_for_matching(line).strip()
        if not normalized or len(line) > 180 or line.endswith("."):
            return False
        if re.match(r"^(?:madde|bolum|chapter|section)\s+[0-9ivxlcdm]+(?:\b|[.)-])", normalized):
            return True
        if re.match(r"^[0-9]+(?:\.[0-9]+){0,4}[.)-]?\s+\S+", normalized):
            return True
        if re.match(r"^[a-z]\)\s+\S+", normalized):
            return True
        if normalized in {
            "amac", "kapsam", "dayanak", "tanimlar", "giris", "sonuc",
            "egitmenler", "egitimciler", "program icerigi", "icerik",
            "basvuru kosullari", "katilim sartlari", "degerlendirme",
            "genel hukumler", "yururluk", "yurutme",
        }:
            return True
        if len(line) <= 140 and line.rstrip().endswith(":"):
            return True
        return len(line) <= 140 and self._looks_like_heading(line)
