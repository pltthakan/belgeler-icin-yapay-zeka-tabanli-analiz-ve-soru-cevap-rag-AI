from __future__ import annotations

import io
from typing import Any, Dict, Iterator, List

from docx import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph


class DocxParserMixin:
    def _extract_docx_pages(self, raw_bytes: bytes) -> List[Dict[str, Any]]:
        document = DocxDocument(io.BytesIO(raw_bytes))
        blocks = []
        for block in self._iter_docx_blocks(document):
            if isinstance(block, Paragraph):
                text = self._normalize_whitespace(block.text)
            else:
                text = self._extract_table_text(block)
            if text:
                blocks.append(text)

        text = self._clean_text("\n".join(blocks))
        return [{"pageNumber": 1, "text": text}] if text else []

    def _iter_docx_blocks(self, document: DocxDocument) -> Iterator[Paragraph | Table]:
        """Paragrafları ve tabloları DOCX gövdesindeki gerçek sırayla döndürür."""
        for child in document.element.body.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, document)
            elif isinstance(child, CT_Tbl):
                yield Table(child, document)

    def _extract_table_text(self, table: Table) -> str:
        rows = []
        for row in table.rows:
            values = []
            seen_cells = set()
            for cell in row.cells:
                # Birleştirilmiş hücreler python-docx tarafından birden çok kez
                # döndürülebilir; aynı OOXML hücresini tekrar indeksleme.
                cell_id = id(cell._tc)
                if cell_id in seen_cells:
                    continue
                seen_cells.add(cell_id)
                value = self._normalize_whitespace(cell.text)
                if value:
                    values.append(value)
            if values:
                rows.append(" | ".join(values))
        return "\n".join(rows)
