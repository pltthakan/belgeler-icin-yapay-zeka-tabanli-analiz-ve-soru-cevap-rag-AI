from __future__ import annotations

import re


class ExtractiveFallbackMixin:
    def _extract_relevant_passage(self, question: str, text: str) -> str:
        # PDF metin çıkarımındaki tek satır sonları çoğunlukla görsel satır
        # kaydırmasıdır; bunları cümle sınırı saymak eksik pasajlar üretir.
        normalized_text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
        sentences = [
            self._normalize_whitespace(sentence)
            for sentence in re.split(r"(?<=[.!?])\s+|\n{2,}", normalized_text)
            if self._normalize_whitespace(sentence)
        ]
        if not sentences:
            return self._shorten(normalized_text, max_chars=450)

        question_terms = self._meaningful_terms(question)
        scored = []
        for index, sentence in enumerate(sentences):
            sentence_terms = set(self._meaningful_terms(sentence))
            overlap = len(question_terms & sentence_terms)
            scored.append((overlap, -index, sentence))

        matching = [item for item in scored if item[0] > 0]
        if not matching:
            return self._shorten(sentences[0], max_chars=450)

        best = sorted(matching, reverse=True)[:2]
        selected = sorted(best, key=lambda item: -item[1])
        return self._shorten(" ".join(item[2] for item in selected), max_chars=550)
