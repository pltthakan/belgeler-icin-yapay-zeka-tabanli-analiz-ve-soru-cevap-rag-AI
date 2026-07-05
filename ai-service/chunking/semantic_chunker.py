from __future__ import annotations

import re
from typing import Any, Dict, List


class SemanticChunkerMixin:
    def _chunk_pages(self, pages: List[Dict[str, Any]], chunk_size: int = 1200, overlap: int = 200) -> List[Dict[str, Any]]:
        heading_chunks = self._chunk_pages_by_headings(pages, chunk_size)
        if heading_chunks:
            return heading_chunks

        chunks = []
        chunk_index = 0
        for page in pages:
            current_blocks = []
            current_length = 0
            for block in self._semantic_blocks(page["text"]):
                for piece in self._split_oversized_block(block, chunk_size):
                    separator_length = 2 if current_blocks else 0
                    if current_blocks and current_length + separator_length + len(piece) > chunk_size:
                        chunk_index = self._append_chunk(
                            chunks=chunks,
                            chunk_index=chunk_index,
                            page_number=page["pageNumber"],
                            text="\n\n".join(current_blocks),
                        )
                        current_blocks = self._semantic_overlap_blocks(current_blocks, overlap)
                        current_length = len("\n\n".join(current_blocks))
                        if current_blocks and current_length + 2 + len(piece) > chunk_size:
                            current_blocks = []
                            current_length = 0

                    current_blocks.append(piece)
                    current_length = len("\n\n".join(current_blocks))

            if current_blocks:
                chunk_index = self._append_chunk(
                    chunks=chunks,
                    chunk_index=chunk_index,
                    page_number=page["pageNumber"],
                    text="\n\n".join(current_blocks),
                )
        return chunks

    def _append_chunk(
        self,
        chunks: List[Dict[str, Any]],
        chunk_index: int,
        page_number: int,
        text: str,
    ) -> int:
        cleaned = text.strip()
        if len(cleaned) < 80:
            return chunk_index
        chunks.append({
            "chunkIndex": chunk_index,
            "pageNumber": page_number,
            "text": cleaned,
        })
        return chunk_index + 1

    def _semantic_blocks(self, text: str) -> List[str]:
        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n+", text.strip())
            if paragraph.strip()
        ]
        blocks = []
        for paragraph in paragraphs:
            lines = [
                self._normalize_whitespace(line)
                for line in paragraph.splitlines()
                if self._normalize_whitespace(line)
            ]
            if not lines:
                continue
            if len(lines) == 1:
                blocks.append(lines[0])
                continue

            current = []
            for line in lines:
                if current and self._starts_semantic_block(line):
                    blocks.append("\n".join(current))
                    current = [line]
                else:
                    current.append(line)
            if current:
                blocks.append("\n".join(current))

        return [block for block in blocks if block.strip()]

    def _starts_semantic_block(self, line: str) -> bool:
        normalized = self._normalize_for_matching(line)
        known_headings = {
            "abstract", "summary", "ozet", "giris", "sonuc", "conclusion",
            "experience", "education", "skills", "projects", "certifications",
            "deneyim", "egitim", "beceriler", "projeler", "sertifikalar",
            "ders kodu ders adi", "harf notu akts",
        }
        if any(normalized.startswith(heading) for heading in known_headings):
            return True
        if re.match(r"^\d+(?:\.\d+)*[.)-]\s+\S+", line):
            return True
        if len(line) <= 140 and line.rstrip().endswith(":"):
            return True
        return len(line) <= 140 and self._looks_like_heading(line)

    def _split_oversized_block(self, block: str, chunk_size: int) -> List[str]:
        if len(block) <= chunk_size:
            return [block]

        sentences = [
            self._normalize_whitespace(sentence)
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", block)
            if self._normalize_whitespace(sentence)
        ]
        if len(sentences) <= 1:
            return self._split_text_by_words(block, chunk_size)

        pieces = []
        current = []
        current_length = 0
        for sentence in sentences:
            if len(sentence) > chunk_size:
                if current:
                    pieces.append(" ".join(current))
                    current = []
                    current_length = 0
                pieces.extend(self._split_text_by_words(sentence, chunk_size))
                continue

            separator_length = 1 if current else 0
            if current and current_length + separator_length + len(sentence) > chunk_size:
                pieces.append(" ".join(current))
                current = [sentence]
                current_length = len(sentence)
            else:
                current.append(sentence)
                current_length += separator_length + len(sentence)

        if current:
            pieces.append(" ".join(current))
        return pieces

    def _split_text_by_words(self, text: str, chunk_size: int) -> List[str]:
        words = text.split()
        pieces = []
        current = []
        current_length = 0
        for word in words:
            if len(word) > chunk_size:
                if current:
                    pieces.append(" ".join(current))
                    current = []
                    current_length = 0
                for start in range(0, len(word), chunk_size):
                    pieces.append(word[start:start + chunk_size])
                continue

            separator_length = 1 if current else 0
            if current and current_length + separator_length + len(word) > chunk_size:
                pieces.append(" ".join(current))
                current = [word]
                current_length = len(word)
            else:
                current.append(word)
                current_length += separator_length + len(word)

        if current:
            pieces.append(" ".join(current))
        return pieces

    def _semantic_overlap_blocks(self, blocks: List[str], overlap: int) -> List[str]:
        if overlap <= 0 or not blocks:
            return []
        selected = []
        selected_length = 0
        for block in reversed(blocks):
            separator_length = 2 if selected else 0
            if selected and selected_length + separator_length + len(block) > overlap:
                break
            if len(block) > overlap:
                break
            selected.insert(0, block)
            selected_length = len("\n\n".join(selected))
        return selected
