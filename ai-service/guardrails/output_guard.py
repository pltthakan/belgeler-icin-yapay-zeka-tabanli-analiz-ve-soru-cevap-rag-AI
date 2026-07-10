from __future__ import annotations

import re
from typing import Any, Dict, List


class OutputGuardMixin:
    def _is_no_answer_response(self, answer: str) -> bool:
        normalized_answer = self._normalize_for_matching(answer)
        return any(marker in normalized_answer for marker in (
            "belgede yer almiyor",
            "belge iceriginde yer almiyor",
            "bu bilgi belgede yok",
            "bu bilgi belgede yer almiyor",
            "yuklenen belgede acikca yer almiyor",
        ))

    def _evidence_support_decision(
        self,
        question: str,
        sources: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Sorunun ana iddiasını destekleyen en az bir kaynak parçası arar.

        Sayısal sorularda aynı oran tek başına kanıt değildir. Oranın yanında
        ana varlık ve ilişki de aynı chunk içinde eşleşmelidir.
        """
        question_terms = self._meaningful_terms(question)
        question_percentages = self._extract_percentages(question)
        question_relations = self._relation_concepts(question)
        question_entities = {
            term for term in question_terms - self._evidence_non_entity_terms()
            if not term.isdigit()
        }
        best_decision = {
            "supported": False,
            "reason": "no-retrieved-chunk-supports-main-claim",
            "sourceIndex": None,
            "matchedPercentages": [],
            "matchedEntities": [],
            "matchedRelations": [],
            "matchedTerms": [],
        }
        best_strength = -1

        for source_index, source in enumerate(sources):
            source_text = str(source.get("text", ""))
            source_terms = self._meaningful_terms(source_text)
            source_percentages = self._extract_percentages(source_text)
            source_relations = self._relation_concepts(source_text)
            matched_percentages = sorted(question_percentages & source_percentages)
            matched_entities = sorted(
                term for term in question_entities
                if self._has_evidence_entity_match(term, source_terms)
            )
            matched_relations = sorted(question_relations & source_relations)
            matched_terms = sorted(
                term for term in question_terms
                if self._has_matching_term(term, source_terms)
            )

            if question_percentages:
                supported = (
                    question_percentages.issubset(source_percentages)
                    and bool(matched_entities)
                    and bool(matched_relations)
                )
                reason = (
                    "exact-percentage-entity-relation-match"
                    if supported
                    else "percentage-without-entity-relation-support"
                )
            else:
                overlap_ratio = len(matched_terms) / max(len(question_terms), 1)
                supported = bool(matched_entities) and (
                    bool(matched_relations) or len(matched_terms) >= 3
                ) and overlap_ratio >= 0.4
                reason = "entity-relation-match" if supported else "insufficient-claim-overlap"

            strength = len(matched_percentages) * 4 + len(matched_entities) * 2 + len(matched_relations)
            if supported:
                strength += 100
            if strength > best_strength:
                best_strength = strength
                best_decision = {
                    "supported": supported,
                    "reason": reason,
                    "sourceIndex": source_index,
                    "chunkIndex": source.get("chunkIndex"),
                    "matchedPercentages": matched_percentages,
                    "matchedEntities": matched_entities,
                    "matchedRelations": matched_relations,
                    "matchedTerms": matched_terms,
                }

        return best_decision

    def _has_evidence_entity_match(self, question_term: str, source_terms: set[str]) -> bool:
        if self._has_matching_term(question_term, source_terms):
            return True
        for source_term in source_terms:
            common_prefix_length = 0
            for question_character, source_character in zip(question_term, source_term):
                if question_character != source_character:
                    break
                common_prefix_length += 1
            shortest_length = min(len(question_term), len(source_term))
            if common_prefix_length >= 5 and common_prefix_length / shortest_length >= 0.7:
                return True
        return False

    def _extract_percentages(self, text: str) -> set[str]:
        normalized = self._normalize_for_matching(text)
        values = set()
        for match in re.finditer(r"(?:%\s*|\byuzde\s+)(\d+(?:[.,]\d+)?)", normalized):
            value = match.group(1).replace(",", ".")
            values.add(value.rstrip("0").rstrip(".") if "." in value else value)
        return values

    def _relation_concepts(self, text: str) -> set[str]:
        normalized = self._normalize_for_matching(text)
        relation_markers = {
            "discount": ("indirim", "indirimli"),
            "scholarship": ("burs", "burslu"),
            "fee": ("ucret", "odeme", "bedel"),
            "duration": ("sure", "gun", "ay", "yil"),
            "requirement": ("sart", "kosul", "kriter", "gerekiyor"),
            "date": ("tarih", "donem", "ne zaman"),
        }
        return {
            relation
            for relation, markers in relation_markers.items()
            if any(marker in normalized for marker in markers)
        }

    def _evidence_non_entity_terms(self) -> set[str]:
        return {
            "alir", "alan", "hangi", "indirim", "indirimi", "indirimli", "kadar", "kac",
            "nedir", "oran", "orani", "ogrenci", "ogrenciler",
            "yerlesen", "uygulanir", "uygulanan", "verilir", "yuzde",
        }

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
        if self._is_no_answer_response(answer):
            return not self._evidence_support_decision(question, sources)["supported"]
        if response_mode == "summary":
            return True
        if response_mode == "critique":
            return self._is_grounded_critique(answer, sources)

        answer_terms = self._meaningful_terms(answer)
        if not answer_terms:
            return True

        answer_percentages = self._extract_percentages(answer)
        source_percentages = self._extract_percentages(
            "\n".join(str(source.get("text", "")) for source in sources)
        )
        question_percentages = self._extract_percentages(question)
        if not answer_percentages.issubset(source_percentages | question_percentages):
            return False

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
