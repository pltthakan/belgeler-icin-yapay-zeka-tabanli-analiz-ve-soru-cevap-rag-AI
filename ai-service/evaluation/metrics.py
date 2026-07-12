from __future__ import annotations

import math
import re
from statistics import mean
from typing import Any, Dict, Iterable, List


NO_ANSWER_MARKERS = (
    "belgede acikca yer almiyor",
    "belgede yer almiyor",
    "belge icinde bulunamadi",
    "belge icinde soruyla iliskili bir bolum bulunamadi",
)


def normalize(text: str) -> str:
    translation = str.maketrans("çğıöşü", "cgiosu")
    normalized = str(text or "").casefold().translate(translation)
    return " ".join(normalized.split())


def is_no_answer(answer: str) -> bool:
    normalized = normalize(answer)
    return any(marker in normalized for marker in NO_ANSWER_MARKERS)


def percentile(values: Iterable[float], percentile_value: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * percentile_value
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _required_term_groups(case: Dict[str, Any]) -> List[List[str]]:
    groups = [[str(term)] for term in case.get("requiredAnswerTerms", [])]
    groups.extend(
        [str(term) for term in group]
        for group in case.get("requiredAnswerTermGroups", [])
    )
    return groups


def _contains_term(normalized_answer: str, term: str) -> bool:
    normalized_term = normalize(term)
    if not normalized_term:
        return False
    if normalized_term.isdigit():
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", normalized_answer) is not None
    return normalized_term in normalized_answer


def _missing_required_terms(case: Dict[str, Any], answer: str) -> List[List[str]]:
    normalized_answer = normalize(answer)
    return [
        group for group in _required_term_groups(case)
        if not any(_contains_term(normalized_answer, term) for term in group)
    ]


def _forbidden_terms(case: Dict[str, Any], answer: str) -> List[str]:
    normalized_answer = normalize(answer)
    return [
        str(term) for term in case.get("forbiddenAnswerTerms", [])
        if _contains_term(normalized_answer, term)
    ]


def score_case(case: Dict[str, Any], result: Dict[str, Any], duration_ms: float) -> Dict[str, Any]:
    answer = str(result.get("answer", ""))
    sources = result.get("sources") if isinstance(result.get("sources"), list) else []
    citations = result.get("citations") if isinstance(result.get("citations"), list) else []
    trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
    retrieved_chunks = [
        int(source["chunkIndex"])
        for source in sources
        if isinstance(source, dict) and source.get("chunkIndex") is not None
    ]
    relevant_chunks = {int(index) for index in case.get("expectedSourceChunks", [])}
    retrieved_relevant = [index for index in retrieved_chunks if index in relevant_chunks]
    evaluation_mode = case.get("evaluationMode", "pipeline")
    should_answer = bool(case.get("shouldAnswer", True))

    retrieval_applicable = evaluation_mode == "pipeline" and bool(relevant_chunks)
    retrieval_recall = (
        len(set(retrieved_relevant)) / len(relevant_chunks)
        if retrieval_applicable else None
    )
    retrieval_precision = (
        len(retrieved_relevant) / len(retrieved_chunks)
        if retrieval_applicable and retrieved_chunks else 0.0
    ) if retrieval_applicable else None
    first_relevant_rank = next(
        (rank for rank, index in enumerate(retrieved_chunks, start=1) if index in relevant_chunks),
        None,
    )
    reciprocal_rank = (
        1.0 / first_relevant_rank
        if retrieval_applicable and first_relevant_rank is not None else 0.0
    ) if retrieval_applicable else None
    retrieval_hit = retrieval_recall == 1.0 if retrieval_applicable else True

    answer_is_no_answer = is_no_answer(answer)
    missing_terms = _missing_required_terms(case, answer)
    forbidden_terms = _forbidden_terms(case, answer)
    answer_correct = (
        not answer_is_no_answer and not missing_terms and not forbidden_terms
        if should_answer else answer_is_no_answer
    )
    guard_correct = answer_correct if evaluation_mode == "guard" else (
        answer_is_no_answer == (not should_answer)
    )

    verification = trace.get("verificationDecision")
    if not should_answer and answer_is_no_answer:
        grounded = True
    elif isinstance(verification, dict):
        grounded = bool(verification.get("supported"))
    else:
        grounded = False

    citation_applicable = evaluation_mode == "pipeline" and should_answer and bool(relevant_chunks)
    cited_chunks = {
        int(citation["chunkIndex"])
        for citation in citations
        if isinstance(citation, dict) and citation.get("chunkIndex") is not None
    }
    citation_correct = bool(cited_chunks & relevant_chunks) if citation_applicable else True
    failures = []
    if not retrieval_hit:
        failures.append("expected-source-not-retrieved")
    if not answer_correct:
        failures.append("answer-expectation-failed")
    if not grounded:
        failures.append("answer-not-grounded")
    if not citation_correct:
        failures.append("supporting-source-not-cited")
    if evaluation_mode == "guard" and not guard_correct:
        failures.append("guard-expectation-failed")

    return {
        "id": case["id"],
        "category": case.get("category", "uncategorized"),
        "evaluationMode": evaluation_mode,
        "shouldAnswer": should_answer,
        "passed": not failures,
        "failures": failures,
        "question": case["question"],
        "answer": answer,
        "provider": trace.get("provider"),
        "guardReason": trace.get("guardReason"),
        "durationMs": round(float(duration_ms), 2),
        "retrievedChunks": retrieved_chunks,
        "expectedSourceChunks": sorted(relevant_chunks),
        "retrieval": {
            "applicable": retrieval_applicable,
            "recallAtK": retrieval_recall,
            "precisionAtK": retrieval_precision,
            "reciprocalRank": reciprocal_rank,
            "firstRelevantRank": first_relevant_rank,
        },
        "answerCorrect": answer_correct,
        "answerIsNoAnswer": answer_is_no_answer,
        "missingAnswerTermGroups": missing_terms,
        "forbiddenAnswerTermsFound": forbidden_terms,
        "grounded": grounded,
        "citationApplicable": citation_applicable,
        "citationCorrect": citation_correct,
        "citationCount": len(citations),
        "citedChunks": sorted(cited_chunks),
        "guardCorrect": guard_correct,
    }


def aggregate_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    def average(key: str, applicable=lambda result: True) -> float:
        values = [float(key_get(result, key)) for result in results if applicable(result)]
        return round(mean(values), 4) if values else 0.0

    retrieval_results = [result for result in results if result["retrieval"]["applicable"]]
    answer_results = [result for result in results if result["shouldAnswer"]]
    no_answer_results = [result for result in results if not result["shouldAnswer"]]
    citation_results = [result for result in results if result["citationApplicable"]]
    guard_results = [result for result in results if result["evaluationMode"] == "guard"]
    durations = [float(result["durationMs"]) for result in results]

    return {
        "caseCount": len(results),
        "passedCases": sum(bool(result["passed"]) for result in results),
        "casePassRate": average("passed"),
        "retrieval": {
            "caseCount": len(retrieval_results),
            "hitRateAtK": round(
                mean(result["retrieval"]["recallAtK"] == 1.0 for result in retrieval_results),
                4,
            ) if retrieval_results else 0.0,
            "recallAtK": average("retrieval.recallAtK", lambda result: result in retrieval_results),
            "precisionAtK": average("retrieval.precisionAtK", lambda result: result in retrieval_results),
            "mrr": average("retrieval.reciprocalRank", lambda result: result in retrieval_results),
        },
        "answerCorrectness": average("answerCorrect"),
        "groundedness": average("grounded", lambda result: result in answer_results),
        "citationAccuracy": average("citationCorrect", lambda result: result in citation_results),
        "noAnswerAccuracy": average("answerCorrect", lambda result: result in no_answer_results),
        "guardAccuracy": average("guardCorrect", lambda result: result in guard_results),
        "latencyMs": {
            "average": round(mean(durations), 2) if durations else 0.0,
            "p50": round(percentile(durations, 0.50), 2),
            "p95": round(percentile(durations, 0.95), 2),
            "max": round(max(durations), 2) if durations else 0.0,
        },
    }
def key_get(value: Dict[str, Any], dotted_key: str) -> Any:
    current: Any = value
    for part in dotted_key.split("."):
        current = current[part]
    return current


def evaluate_quality_gates(metrics: Dict[str, Any], gates: Dict[str, float]) -> List[Dict[str, Any]]:
    decisions = []
    for metric_name, minimum in gates.items():
        actual = float(key_get(metrics, metric_name))
        decisions.append({
            "metric": metric_name,
            "minimum": float(minimum),
            "actual": actual,
            "passed": actual >= float(minimum),
        })
    return decisions
