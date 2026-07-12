from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List


class ClaimValidatorMixin:
    """Üretilen cevaptaki atomik iddiaları kaynak parçalarıyla doğrular."""

    def _validate_answer_claims(
        self,
        answer: str,
        sources: List[Dict[str, Any]],
        response_mode: str,
        question: str | None = None,
    ) -> Dict[str, Any]:
        claims = self._split_answer_claims(answer)
        if not claims:
            return {
                "supported": False,
                "reason": "answer-has-no-verifiable-claims",
                "claims": [],
            }

        evidence_windows = self._source_evidence_windows(sources)
        decisions = [
            self._validate_single_claim(claim, evidence_windows, response_mode)
            for claim in claims
        ]
        unsupported_claims = [decision for decision in decisions if not decision["supported"]]
        question_alignment = self._validate_question_fact_alignment(question, answer)
        supported = not unsupported_claims and question_alignment["supported"]
        return {
            "supported": supported,
            "reason": (
                "all-claims-supported"
                if supported
                else question_alignment["reason"]
                if not question_alignment["supported"]
                else "unsupported-answer-claims"
            ),
            "claimCount": len(decisions),
            "unsupportedClaimCount": len(unsupported_claims),
            "claims": decisions,
            "questionAlignment": question_alignment,
        }

    def _validate_question_fact_alignment(self, question: str | None, answer: str) -> Dict[str, Any]:
        if not question:
            return {"supported": True, "reason": "question-not-provided", "mismatches": {}}

        question_facts = self._extract_claim_facts(question)
        answer_facts = self._extract_claim_facts(answer)
        mismatches = {}
        for fact_type in ("percentages", "money", "durations", "dates"):
            expected_values = set(question_facts.get(fact_type, []))
            if expected_values and not expected_values.issubset(set(answer_facts.get(fact_type, []))):
                mismatches[fact_type] = {
                    "question": sorted(expected_values),
                    "answer": answer_facts.get(fact_type, []),
                }
        return {
            "supported": not mismatches,
            "reason": "question-facts-preserved" if not mismatches else "question-fact-mismatch",
            "mismatches": mismatches,
        }

    def _split_answer_claims(self, answer: str) -> List[str]:
        cleaned = self._normalize_whitespace(answer)
        cleaned = re.sub(r"(?i)^belgeye\s+göre\s*:\s*", "", cleaned)
        cleaned = re.sub(r"(?i)^belgeye\s+göre\s+", "", cleaned)
        return [
            self._normalize_whitespace(claim).strip(" -")
            for claim in re.split(
                r"(?<!\d[.!?])(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ])|\s*;\s+",
                cleaned,
            )
            if self._normalize_whitespace(claim).strip(" -")
        ]

    def _source_evidence_windows(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        windows = []
        for source_index, source in enumerate(sources):
            raw_source_text = str(source.get("text", ""))
            if not self._normalize_whitespace(raw_source_text):
                continue

            unwrapped_source_text = re.sub(r"(?<!\n)\n(?!\n)", " ", raw_source_text)
            units = [
                self._normalize_whitespace(unit)
                for unit in re.split(
                    r"(?<!\d[.!?])(?<=[.!?])\s+|\s+(?=\([0-9]+\)\s)|\n{2,}",
                    unwrapped_source_text,
                )
                if self._normalize_whitespace(unit)
            ]
            candidates = [(unit, 1) for unit in units]
            candidates.extend(
                (f"{units[index]} {units[index + 1]}", 2)
                for index in range(len(units) - 1)
            )
            candidates.extend(
                (f"{units[index]} {units[index + 1]} {units[index + 2]}", 3)
                for index in range(len(units) - 2)
            )

            seen = set()
            for candidate_text, unit_count in candidates:
                if candidate_text in seen:
                    continue
                seen.add(candidate_text)
                windows.append({
                    "sourceIndex": source_index,
                    "chunkIndex": source.get("chunkIndex"),
                    "text": candidate_text,
                    "unitCount": unit_count,
                })
        return windows

    def _validate_single_claim(
        self,
        claim: str,
        evidence_windows: List[Dict[str, Any]],
        response_mode: str,
    ) -> Dict[str, Any]:
        claim_terms = self._claim_content_terms(claim)
        claim_facts = self._extract_claim_facts(claim)
        claim_relations = self._relation_concepts(claim)
        claim_acronyms = self._extract_acronyms(claim)
        claim_negative = self._has_negative_polarity(claim)
        has_critical_facts = any(claim_facts.values())
        best_match = None
        best_score = -1.0

        for window in evidence_windows:
            if has_critical_facts and int(window.get("unitCount", 1)) > 1:
                continue
            source_text = window["text"]
            source_terms = self._claim_content_terms(source_text)
            matched_terms = sorted(
                term for term in claim_terms
                if self._has_evidence_entity_match(term, source_terms)
            )
            coverage = len(matched_terms) / max(len(claim_terms), 1)
            source_facts = self._extract_claim_facts(source_text)
            facts_match = self._claim_facts_are_supported(claim_facts, source_facts)
            source_relations = self._relation_concepts(source_text)
            matched_relations = sorted(claim_relations & source_relations)
            relations_match = not claim_relations or bool(matched_relations)
            normalized_source_text = self._normalize_for_matching(source_text)
            acronyms_match = all(acronym in normalized_source_text for acronym in claim_acronyms)
            polarity_match = claim_negative == self._has_negative_polarity(source_text)

            minimum_coverage = 0.35 if has_critical_facts else 0.65
            if response_mode == "summary":
                minimum_coverage = 0.35
            minimum_term_count = 1 if len(claim_terms) <= 2 else 2
            supported = (
                facts_match
                and relations_match
                and acronyms_match
                and polarity_match
                and len(matched_terms) >= minimum_term_count
                and coverage >= minimum_coverage
            )
            score = (
                coverage
                + (0.35 if facts_match and has_critical_facts else 0.0)
                + (0.15 if matched_relations else 0.0)
                + (0.10 if acronyms_match and claim_acronyms else 0.0)
                + (0.10 if polarity_match else 0.0)
            )
            if supported:
                score += 10.0

            if score > best_score:
                best_score = score
                best_match = {
                    "claim": claim,
                    "supported": supported,
                    "reason": "claim-supported" if supported else self._claim_failure_reason(
                        facts_match=facts_match,
                        relations_match=relations_match,
                        acronyms_match=acronyms_match,
                        polarity_match=polarity_match,
                        coverage=coverage,
                        minimum_coverage=minimum_coverage,
                    ),
                    "sourceIndex": window["sourceIndex"],
                    "chunkIndex": window.get("chunkIndex"),
                    "coverage": round(coverage, 4),
                    "matchedTerms": matched_terms,
                    "matchedRelations": matched_relations,
                    "facts": claim_facts,
                }

        if best_match is not None:
            return best_match
        return {
            "claim": claim,
            "supported": False,
            "reason": "no-source-evidence-window",
            "sourceIndex": None,
            "chunkIndex": None,
            "coverage": 0.0,
            "matchedTerms": [],
            "matchedRelations": [],
            "facts": claim_facts,
        }

    def _claim_content_terms(self, text: str) -> set[str]:
        generic_terms = {
            "belgeye", "gore", "kaynak", "kaynakta", "kaynaklara", "cevap",
            "bilgi", "bilgiler", "ilgili", "olarak", "sekilde",
        }
        return self._meaningful_terms(text) - generic_terms

    def _extract_claim_facts(self, text: str) -> Dict[str, List[str]]:
        normalized = self._normalize_for_matching(text)
        normalized = re.sub(r"(?<!\d)\.(\d)(?=\s+ve\b)", r"\1", normalized)
        normalized = re.sub(r"(?<!\d)\.(\d)s?\s+inif\b", r"\1 sinif", normalized)
        percentages = sorted(self._extract_percentages(text))
        money = {
            f"{self._canonical_number(match.group(1))}:{self._canonical_money_unit(match.group(2))}"
            for match in re.finditer(
                r"\b([0-9][0-9.,]*)\s*(tl|lira|usd|eur|dolar|euro)[a-z']*\b",
                normalized,
            )
        }
        money.update({
            f"{self._canonical_number(match.group(1))}:try"
            for match in re.finditer(r"\b([0-9][0-9.,]*)\s*₺", normalized)
        })
        durations = sorted({
            f"{self._canonical_number(match.group(1))}:{match.group(2)}"
            for match in re.finditer(
                r"\b([0-9][0-9.,]*)\s*(gun|hafta|ay|yil|saat|dakika)[a-z']*\b",
                normalized,
            )
        })
        dates = sorted(self._extract_dates(normalized))

        month_names = "ocak|subat|mart|nisan|mayis|haziran|temmuz|agustos|eylul|ekim|kasim|aralik"
        number_text = normalized
        number_text = re.sub(
            r"\b(?:[0-3]?\d[./-][01]?\d[./-](?:19|20)?\d{2}|(?:19|20)\d{2}-[01]\d-[0-3]\d)\b",
            " ",
            number_text,
        )
        number_text = re.sub(
            rf"\b[0-3]?\d\s+(?:{month_names})\s+(?:19|20)\d{{2}}\b",
            " ",
            number_text,
        )
        number_text = re.sub(r"(?:%\s*|\byuzde\s+)\d+(?:[.,]\d+)?", " ", number_text)
        number_text = re.sub(
            r"\b[0-9][0-9.,]*\s*(?:tl|lira|usd|eur|dolar|euro)[a-z']*\b|\b[0-9][0-9.,]*\s*₺",
            " ",
            number_text,
        )
        number_text = re.sub(
            r"\b[0-9][0-9.,]*\s*(?:gun|hafta|ay|yil|saat|dakika)[a-z']*\b",
            " ",
            number_text,
        )
        numbers = sorted({
            self._canonical_number(raw_number)
            for raw_number in re.findall(r"(?<![a-z])\d+(?:[.,]\d+)*(?![a-z])", number_text)
        })
        return {
            "percentages": percentages,
            "money": sorted(money),
            "durations": durations,
            "dates": dates,
            "numbers": numbers,
        }

    def _canonical_money_unit(self, unit: str) -> str:
        normalized_unit = self._normalize_for_matching(unit)
        if normalized_unit in {"tl", "lira"}:
            return "try"
        if normalized_unit in {"usd", "dolar"}:
            return "usd"
        if normalized_unit in {"eur", "euro"}:
            return "eur"
        return normalized_unit

    def _extract_dates(self, normalized_text: str) -> set[str]:
        dates = set()
        for match in re.finditer(r"\b([0-3]?\d)[./-]([01]?\d)[./-]((?:19|20)?\d{2})\b", normalized_text):
            day, month, year = match.groups()
            if len(year) == 2:
                year = f"20{year}"
            dates.add(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")

        for match in re.finditer(r"\b((?:19|20)\d{2})-([01]\d)-([0-3]\d)\b", normalized_text):
            year, month, day = match.groups()
            dates.add(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")

        month_numbers = {
            "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
            "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12,
        }
        month_pattern = "|".join(month_numbers)
        for match in re.finditer(
            rf"\b([0-3]?\d)\s+({month_pattern})\s+((?:19|20)\d{{2}})\b",
            normalized_text,
        ):
            day, month_name, year = match.groups()
            dates.add(f"{int(year):04d}-{month_numbers[month_name]:02d}-{int(day):02d}")
        return dates

    def _canonical_number(self, raw_number: str) -> str:
        value = raw_number.strip()
        if "," in value and "." in value:
            if value.rfind(",") > value.rfind("."):
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", "")
        elif "," in value:
            value = value.replace(",", ".")
        elif value.count(".") == 1:
            integer_part, fraction_part = value.split(".")
            if len(fraction_part) == 3 and len(integer_part) <= 3:
                value = integer_part + fraction_part
        elif value.count(".") > 1:
            value = value.replace(".", "")

        try:
            decimal_value = Decimal(value)
        except InvalidOperation:
            return value
        normalized = format(decimal_value.normalize(), "f")
        return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized

    def _claim_facts_are_supported(
        self,
        claim_facts: Dict[str, List[str]],
        source_facts: Dict[str, List[str]],
    ) -> bool:
        return all(
            set(values).issubset(set(source_facts.get(fact_type, [])))
            for fact_type, values in claim_facts.items()
            if values
        )

    def _extract_acronyms(self, text: str) -> set[str]:
        return {
            self._normalize_for_matching(acronym)
            for acronym in re.findall(r"\b[A-ZÇĞİÖŞÜ]{2,}(?:/[A-ZÇĞİÖŞÜ]{2,})*\b", text)
        }

    def _has_negative_polarity(self, text: str) -> bool:
        normalized = self._normalize_for_matching(text)
        negative_markers = (
            " degil", " yok", "bulunmuyor", "bulunmaz", "haric", "kapsamaz",
            "odenmez", "odemez", "uygulanmaz", "alamaz", "verilmez",
            "gerekmiyor", "gerekmez", "zorunlu degil", "mumkun degil",
        )
        if any(marker in f" {normalized}" for marker in negative_markers):
            return True
        return re.search(r"\b[a-z]+(?:maz|mez|miyor|miyorlar)\b", normalized) is not None

    def _claim_failure_reason(
        self,
        facts_match: bool,
        relations_match: bool,
        acronyms_match: bool,
        polarity_match: bool,
        coverage: float,
        minimum_coverage: float,
    ) -> str:
        if not facts_match:
            return "critical-fact-mismatch"
        if not polarity_match:
            return "claim-polarity-mismatch"
        if not acronyms_match:
            return "named-entity-mismatch"
        if not relations_match:
            return "claim-relation-mismatch"
        if coverage < minimum_coverage:
            return "insufficient-claim-coverage"
        return "insufficient-claim-evidence"
