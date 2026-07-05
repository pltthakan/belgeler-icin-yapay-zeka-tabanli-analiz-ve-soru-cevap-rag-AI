from __future__ import annotations

import re


class QaAnswererMixin:
    def _get_qa_pipeline(self):
        if self.disable_qa_model:
            return None
        if self._qa_pipeline is not None:
            return self._qa_pipeline
        try:
            from transformers import pipeline
            self._qa_pipeline = pipeline("question-answering", model=self.qa_model_name, tokenizer=self.qa_model_name)
            return self._qa_pipeline
        except Exception as exc:
            print(f"QA modeli yüklenemedi, kaynak özet fallback kullanılacak: {exc}")
            self._qa_pipeline = None
            return None

    def _is_usable_qa_answer(self, answer: str) -> bool:
        """Extractive QA'nın tek karakterli veya boş span'lerini reddeder."""
        cleaned = self._normalize_whitespace(answer)
        if not cleaned:
            return False

        if re.fullmatch(r"[0-9]+([.,][0-9]+)?", cleaned):
            return True

        letter_count = len(re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]", cleaned))
        return len(cleaned) >= 3 and letter_count >= 2
