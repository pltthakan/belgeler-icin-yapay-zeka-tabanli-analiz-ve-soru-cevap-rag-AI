from __future__ import annotations

import re
import time
from typing import Any, Dict, List


class RetrievalGuardMixin:
    def _answer_result_from_guard(self, guard_result: Dict[str, Any], started_at: float) -> Dict[str, Any]:
        """Model çağrısı gerektirmeyen, düşük-alaka düzeyi yanıtını döndürür."""
        return {
            "answer": self._out_of_scope_answer(),
            # İlişkisiz kaynakları cevapla birlikte göstermemek gerekir; aksi halde
            # kullanıcıya yanlış bir kanıt ilişkisi sunulmuş olur.
            "sources": [],
            "trace": self._build_trace(
                generation=guard_result,
                selected_sources=[],
                duration_ms=(time.perf_counter() - started_at) * 1000,
            ),
        }

    def _relevance_guard_result(
        self,
        question: str,
        selected_sources: List[Dict[str, Any]],
    ) -> Dict[str, Any] | None:
        """Alakasız sorgularda LLM/QA çağrısından önce durur.

        Belge özeti soruları özel bir durumdur; ancak önce belgeye bağlanmamış
        genel dünya/varoluş sorularını ayıkla.
        """
        if self._is_general_knowledge_question(question, selected_sources):
            scores = [float(source.get("score", 0.0)) for source in selected_sources]
            max_score = max(scores, default=0.0)
            return {
                "provider": "retrieval-guard",
                "model": None,
                "responseMode": self._classify_response_mode(question),
                "prompt": None,
                "guardReason": "general-knowledge-question",
                "maxRetrievalScore": round(max_score, 4),
                "minRetrievalScore": self.min_retrieval_score,
            }

        if self._is_document_overview_question(question):
            return None

        scores = [float(source.get("score", 0.0)) for source in selected_sources]
        max_score = max(scores, default=0.0)
        if self._is_obvious_gibberish(question):
            reason = "gibberish-question"
        elif self._is_low_information_question(question, selected_sources):
            reason = "low-information-question"
        elif not selected_sources or max_score < self.min_retrieval_score:
            reason = "low-retrieval-score"
        else:
            return None

        return {
            "provider": "retrieval-guard",
            "model": None,
            "responseMode": self._classify_response_mode(question),
            "prompt": None,
            "guardReason": reason,
            "maxRetrievalScore": round(max_score, 4),
            "minRetrievalScore": self.min_retrieval_score,
        }

    def _out_of_scope_answer(self) -> str:
        return (
            "Bu bilgi yüklenen belgede açıkça yer almıyor. Belgedeki başlıklar, kavramlar, "
            "kişiler, tarihler, maddeler veya bilgiler hakkında daha açık bir soru sor."
        )

    def _is_obvious_gibberish(self, question: str) -> bool:
        """Tek, uzun ve neredeyse sesli harfsiz rastgele dizileri ayıklar.

        Bu kontrol kasıtlı olarak dardır; normal isimleri, kodları veya belge
        içeriğindeki kısa terimleri engellemez. Diğer alakasız sorular skor eşiği
        ile değerlendirilir.
        """
        tokens = re.findall(r"[a-z]+", self._normalize_for_matching(question))
        if len(tokens) != 1 or len(tokens[0]) < 7:
            return False
        token = tokens[0]
        vowel_count = sum(character in "aeiou" for character in token)
        return vowel_count / len(token) < 0.15

    def _is_low_information_question(self, question: str, selected_sources: List[Dict[str, Any]]) -> bool:
        """Kısa, bağlamsız veya sohbet dışı ifadelerde rastgele chunk cevabını engeller."""
        normalized = self._normalize_for_matching(question)
        tokens = re.findall(r"[a-z0-9]+", normalized)
        if not tokens:
            return True

        conversational_noise = (
            "ne bileyim",
            "bilmiyorum",
            "bosver",
            "rastgele",
            "sacma",
            "laf olsun",
        )
        if any(marker in normalized for marker in conversational_noise):
            return True
        if any(token in {"la", "lan", "lo", "ya"} for token in tokens) and len(tokens) <= 3:
            return True

        question_terms = self._meaningful_terms(question)
        if not question_terms:
            return True

        source_terms = set()
        for source in selected_sources:
            source_terms.update(self._meaningful_terms(source.get("text", "")))

        has_question_shape = any(marker in normalized for marker in (
            " nedir",
            " ne ",
            " nasil",
            " hangi",
            " kac",
            " kim",
            " nerede",
            " nereden",
            " nerden",
            " nereye",
            " neresi",
            " neden",
            " mi",
            " mu",
            " mii",
            "?",
        ))
        has_source_overlap = self._has_term_overlap(question_terms, source_terms)

        # Kısa sorular gerçek belge terimleriyle örtüşmüyorsa dense embedding'in
        # rastgele yakın gördüğü bir paragrafı cevaba dönüştürmesine izin verme.
        if len(question_terms) <= 2 and not has_source_overlap:
            return True
        if len(question_terms) <= 3 and not has_source_overlap and not has_question_shape:
            return True
        return False

    def _is_general_knowledge_question(self, question: str, selected_sources: List[Dict[str, Any]]) -> bool:
        """Belge alanı yerine dış dünya bilgisi isteyen soruları LLM'e göndermeden durdurur."""
        normalized = self._normalize_for_matching(question)
        if self._has_document_anchor(normalized):
            return False

        source_terms = self._source_terms(selected_sources)
        question_terms = self._meaningful_terms(question)
        has_source_overlap = self._has_term_overlap(question_terms, source_terms)

        if self._is_unanchored_existential_question(normalized, question_terms):
            return True

        generic_definition_markers = (
            "nasil bir sey",
            "nasil bisey",
            "nasil birsey",
            "ne demek",
            "nedir anlat",
        )
        if any(marker in normalized for marker in generic_definition_markers):
            return True

        procedural_markers = (
            "nasil cikilir",
            "nasil gidilir",
            "nasil yapilir",
            "nasil olunur",
            "nasil alinir",
            "nasil kullanilir",
        )
        if any(marker in normalized for marker in procedural_markers) and not has_source_overlap:
            return True

        external_topic_terms = {
            "uzay", "uzaya", "mars", "roket", "astronot", "araba", "telefon",
            "yemek", "spor", "bitcoin", "borsa", "film", "oyun", "olum",
            "hayat", "insanlik", "dunya", "tanri", "ask",
        }
        if question_terms & external_topic_terms and not has_source_overlap:
            return True

        return False

    def _is_unanchored_existential_question(self, normalized: str, question_terms: set[str]) -> bool:
        abstract_terms = {
            "olum", "hayat", "yasam", "insanlik", "insanligin", "dunya",
            "dunyadaki", "evren", "tanri", "kader", "ruh", "ask", "mutluluk",
            "varolus",
        }
        abstract_question_markers = (
            "gercek mi",
            "gercekmi",
            "gecrekmi",
            "nedir",
            "ne demek",
            "amaci nedir",
            "amaci ne",
            "neden var",
        )
        return bool(question_terms & abstract_terms) and any(
            marker in normalized for marker in abstract_question_markers
        )

    def _has_document_anchor(self, normalized_question: str) -> bool:
        anchors = (
            "belgede",
            "belgedeki",
            "belgenin",
            "bu belge",
            "dokumanda",
            "dokumandaki",
            "dokumanin",
            "bu dokuman",
            "bilette",
            "biletin",
            "bu bilet",
        )
        return any(anchor in normalized_question for anchor in anchors)

    def _source_terms(self, selected_sources: List[Dict[str, Any]]) -> set[str]:
        source_terms = set()
        for source in selected_sources:
            source_terms.update(self._meaningful_terms(source.get("text", "")))
        return source_terms

    def _has_term_overlap(self, question_terms: set[str], source_terms: set[str]) -> bool:
        if question_terms & source_terms:
            return True
        for question_term in question_terms:
            for source_term in source_terms:
                shortest = min(len(question_term), len(source_term))
                if shortest >= 5 and (
                    question_term.startswith(source_term[:shortest])
                    or source_term.startswith(question_term[:shortest])
                ):
                    return True
        return False
