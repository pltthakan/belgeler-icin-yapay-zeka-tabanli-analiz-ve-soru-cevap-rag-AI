from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


class CitationServiceMixin:
    """Builds inline citations only for claims supported by retrieved evidence."""

    def _build_answer_payload(
        self,
        question: str,
        answer: str,
        sources: List[Dict[str, Any]],
        generation: Dict[str, Any],
        duration_ms: float,
    ) -> Dict[str, Any]:
        cited_answer, citations = self._attach_claim_citations(
            question=question,
            answer=answer,
            sources=sources,
            generation=generation,
        )
        citation_trace = {
            **generation,
            "citationCount": len(citations),
            "citationMode": "claim-level" if citations else "none",
        }
        return {
            "answer": cited_answer,
            "sources": sources,
            "citations": citations,
            "trace": self._build_trace(
                generation=citation_trace,
                selected_sources=sources,
                duration_ms=duration_ms,
            ),
        }

    def _attach_claim_citations(
        self,
        question: str,
        answer: str,
        sources: List[Dict[str, Any]],
        generation: Dict[str, Any],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        if not sources or self._is_no_answer_response(answer):
            return answer, []

        verification = generation.get("verificationDecision")
        if not isinstance(verification, dict) or not isinstance(verification.get("claims"), list):
            verification = self._validate_answer_claims(
                answer,
                sources,
                str(generation.get("responseMode") or self._classify_response_mode(question)),
                question=question,
            )
        if not verification.get("supported"):
            return answer, []

        citations = []
        insertions = []
        occupied_ranges = []
        search_start = 0

        for decision in verification.get("claims", []):
            if not isinstance(decision, dict) or not decision.get("supported"):
                continue
            source_index = decision.get("sourceIndex")
            if not isinstance(source_index, int) or not 0 <= source_index < len(sources):
                continue
            claim = str(decision.get("claim") or "").strip()
            if not claim:
                continue

            claim_start = answer.find(claim, search_start)
            if claim_start < 0:
                claim_start = answer.find(claim)
            if claim_start < 0:
                match = re.search(re.escape(claim), answer[search_start:], flags=re.IGNORECASE)
                claim_start = search_start + match.start() if match else -1
            if claim_start < 0:
                continue
            claim_end = claim_start + len(claim)
            if any(claim_start < used_end and claim_end > used_start for used_start, used_end in occupied_ranges):
                continue

            source = sources[source_index]
            source_text = str(source.get("text", ""))
            quote = self._citation_quote(claim, source_text, max_chars=320)
            citation_id = len(citations) + 1
            citations.append({
                "id": citation_id,
                "claim": claim,
                "sourceIndex": source_index,
                "pageNumber": source.get("pageNumber"),
                "chunkIndex": source.get("chunkIndex"),
                "quote": quote,
                "coverage": decision.get("coverage"),
            })
            marker_position = claim_end - 1 if answer[claim_end - 1:claim_end] in ".!?" else claim_end
            insertions.append((marker_position, f" [{citation_id}]"))
            occupied_ranges.append((claim_start, claim_end))
            search_start = claim_end

        cited_answer = answer
        for position, marker in sorted(insertions, reverse=True):
            cited_answer = f"{cited_answer[:position]}{marker}{cited_answer[position:]}"
        return cited_answer, citations

    def _citation_quote(self, claim: str, source_text: str, max_chars: int) -> str:
        cleaned_source = self._normalize_whitespace(source_text)
        if len(cleaned_source) <= max_chars:
            return cleaned_source

        claim_terms = self._claim_content_terms(claim)
        raw_claim_terms = {
            token for token in re.findall(r"[\wÇĞİÖŞÜçğıöşü-]+", claim, flags=re.UNICODE)
            if len(token) >= 4
        }
        candidates = []
        for raw_term in sorted(raw_claim_terms, key=len, reverse=True):
            for match in re.finditer(re.escape(raw_term), cleaned_source, flags=re.IGNORECASE):
                start = max(0, match.start() - max_chars // 2)
                end = min(len(cleaned_source), start + max_chars)
                start = max(0, end - max_chars)
                window = cleaned_source[start:end]
                window_terms = self._claim_content_terms(window)
                overlap = sum(
                    1 for term in claim_terms
                    if self._has_evidence_entity_match(term, window_terms)
                )
                candidates.append((overlap, len(raw_term), start, end, match.start(), match.end()))

        if not candidates:
            return self._shorten(cleaned_source, max_chars=max_chars)

        _, _, start, end, anchor_start, anchor_end = max(candidates)
        if start > 0:
            boundary = max(
                cleaned_source.rfind(". ", start, anchor_start),
                cleaned_source.rfind("; ", start, anchor_start),
            )
            if boundary >= start:
                start = boundary + 2
        if end < len(cleaned_source):
            boundary_candidates = [
                position for position in (
                    cleaned_source.find(". ", anchor_end, end),
                    cleaned_source.find("; ", anchor_end, end),
                )
                if position >= 0
            ]
            if boundary_candidates:
                end = min(boundary_candidates) + 1

        quote = cleaned_source[start:end].strip()
        if start > 0:
            quote = f"...{quote}"
        if end < len(cleaned_source):
            quote = f"{quote}..."
        return quote
