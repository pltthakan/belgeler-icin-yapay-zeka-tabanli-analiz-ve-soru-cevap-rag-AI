from __future__ import annotations

import re
from typing import Any, Dict, List


class DocumentProfileMixin:
    def _build_document_profile(self, chunks: List[Dict[str, Any]]) -> Dict[str, str]:
        title = self._extract_document_title(chunks)
        return {
            "title": title or "",
            "summary": self._fallback_document_summary(title),
        }

    def _fallback_document_summary(self, title: str | None) -> str:
        if not title:
            return "Bu belge için güvenilir bir başlık veya özet çıkarılamadı."

        normalized_title = self._normalize_for_matching(title)
        document_kinds = (
            ("elektronik bilet", "elektronik bilet yolcu seyahat belgesidir"),
            ("electronic ticket", "elektronik bilet yolcu seyahat belgesidir"),
            ("passenger itinerary", "elektronik bilet yolcu seyahat belgesidir"),
            ("seyahat belgesi", "seyahat belgesidir"),
            ("bilet", "bilettir"),
            ("anket", "ankettir"),
            ("form", "formdur"),
            ("sozlesme", "sözleşmedir"),
            ("rapor", "rapordur"),
            ("kilavuz", "kılavuzdur"),
            ("yonerge", "yönergedir"),
            ("prosedur", "prosedürdür"),
        )
        for marker, description in document_kinds:
            if marker in normalized_title:
                return f"Bu belge, “{title}” başlıklı bir {description}."
        return f"Bu belge, “{title}” başlıklı bir belgedir."

    def _extract_document_title(self, chunks: List[Dict[str, Any]]) -> str | None:
        """Belge başındaki en anlamlı başlığı, ana konu soruları için döndürür."""
        if not chunks:
            return None

        opening_text = "\n".join(chunk.get("text", "") for chunk in chunks[:3])
        lines = [self._normalize_whitespace(line) for line in opening_text.splitlines()]
        candidates = [
            line for line in lines
            if 12 <= len(line) <= 280 and self._contains_letters(line)
        ]
        if not candidates and opening_text:
            first_sentence = re.split(r"(?<=[.!?])\s+", opening_text, maxsplit=1)[0]
            candidates = [self._normalize_whitespace(first_sentence)]

        # Birçok kurumsal belgede üst bilgi, ders/alan adı ve gerçek belge başlığı
        # ayrı satırlarda yazılır. Örneğin "... EĞİTİM DERSİ" + "... ANKETİ".
        # Başlık türünü içeren satırı ve gerekiyorsa hemen önceki üst başlığı birlikte
        # döndürmek, kurum adını tek başına konu diye göstermeyi engeller.
        heading_lines = []
        for candidate in candidates[:6]:
            if self._looks_like_heading(candidate):
                heading_lines.append(candidate)
            elif heading_lines:
                break

        title_markers = (
            "anket", "form", "rapor", "sozlesme", "şartname", "sartname",
            "kilavuz", "kılavuz", "yonerge", "yönerge", "prosedur", "prosedür",
            "politika", "talimat", "elektronik bilet", "electronic ticket",
            "passenger itinerary", "seyahat belgesi",
        )
        for index, candidate in enumerate(candidates):
            normalized = self._normalize_for_matching(candidate)
            if any(marker in normalized for marker in title_markers):
                if index > 0:
                    previous = candidates[index - 1]
                    normalized_previous = self._normalize_for_matching(previous)
                    if self._looks_like_heading(previous) and not any(
                        marker in normalized_previous
                        for marker in ("universitesi", "fakultesi", "bolumu")
                    ):
                        return f"{previous.rstrip('.:')} — {candidate.rstrip('.:')}"
                return candidate.rstrip(".:")

        for candidate in candidates:
            # Formlarda başlığın hemen altındaki "öğrenci bilgileri" gibi bölüm
            # adlarını değil, belgenin gerçek üst başlığını tercih et.
            if self._normalize_for_matching(candidate) not in self._metadata_heading_labels():
                return candidate.rstrip(".:")
        return None

    def _metadata_heading_labels(self) -> set[str]:
        return {
            "ogrenci bilgileri",
            "icerindekiler",
            "duzenlendigi tarih issue date",
            "duzenleyen issuance",
            "seri no serial no",
            "yolcu ismi passenger name",
            "bilet no ticket number",
            "rezervasyon no booking ref",
            "adres address",
            "firma ismi company name",
            "vergi dairesi hesap no",
            "tc kimlik numarasi",
            "kisitlama endorsmen restr",
            "odeme payment",
            "esas ucret base fare",
            "vergi tax",
            "toplam total",
        }
