from __future__ import annotations

import re
from typing import Any, Dict, List


class OutputGuardMixin:
    def _is_grounded_critique(self, answer: str, sources: List[Dict[str, Any]]) -> bool:
        """Kaynak metinle çelişen yaygın CV eleştirilerini kullanıcıya ulaştırmaz."""
        normalized_answer = self._normalize_for_matching(answer)
        normalized_context = self._normalize_for_matching(
            "\n".join(source.get("text", "") for source in sources)
        )

        has_dates = bool(re.search(r"\b(?:19|20)\d{2}\b", normalized_context))
        has_skill_evidence = any(
            marker in normalized_context
            for marker in ("skills", "beceri", "react", "java", "python", "flask", "spring")
        )
        has_project_evidence = any(
            marker in normalized_context
            for marker in ("projects", "proje", "implemented", "built", "gelistirdi")
        )

        if has_dates and any(marker in normalized_answer for marker in ("tarihlendirilmemis", "tarih yok")):
            return False
        if has_skill_evidence and re.search(r"(?:teknik )?becer\w*.{0,30}eksik", normalized_answer):
            return False
        if has_project_evidence and re.search(r"proje.{0,40}tamamlanmamis", normalized_answer):
            return False
        return True

    def _safe_critique_answer(self) -> str:
        return (
            "Belgeye dayalı değerlendirme: İncelenen kaynaklarda doğrulanabilir belirgin bir olumsuz "
            "tespit bulunmuyor. Daha güçlü bir sunum için hedeflenen pozisyona en uygun proje, teknoloji "
            "ve ölçülebilir sonuçlar özet bölümünde önceliklendirilebilir."
        )

    def _is_grounded_answer(
        self,
        question: str,
        answer: str,
        sources: List[Dict[str, Any]],
        response_mode: str,
    ) -> bool:
        """Ollama cevabının kaynak dışı yeni bilgi eklemesini engeller."""
        normalized_answer = self._normalize_for_matching(answer)
        if not normalized_answer:
            return False
        if any(marker in normalized_answer for marker in (
            "belgede yer almiyor",
            "belge iceriginde yer almiyor",
            "bu bilgi belgede yok",
            "bu bilgi belgede yer almiyor",
        )):
            return True
        if response_mode == "summary":
            return True
        if response_mode == "critique":
            return self._is_grounded_critique(answer, sources)

        answer_terms = self._meaningful_terms(answer)
        if not answer_terms:
            return True

        allowed_terms = (
            self._source_terms(sources)
            | self._meaningful_terms(question)
            | self._generic_answer_terms()
        )
        unsupported_terms = {
            term for term in answer_terms
            if not self._has_matching_term(term, allowed_terms)
        }
        allowed_unsupported_count = max(2, int(len(answer_terms) * 0.25))
        return len(unsupported_terms) <= allowed_unsupported_count

    def _generic_answer_terms(self) -> set[str]:
        return {
            "bilgi", "bilgiler", "icerik", "icerir", "iceriyor", "hakkinda",
            "ilgili", "belirtir", "gosterir", "amac", "amaci", "kullanilir",
            "resmi", "kayit", "detay", "detaylari", "toplam", "tutar",
            "degerlendirme", "kaynaklarda", "dogrulanabilir",
        }
