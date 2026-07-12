import unittest

from evaluation.metrics import (
    aggregate_results,
    evaluate_quality_gates,
    is_no_answer,
    normalize,
    percentile,
    score_case,
)


class EvaluationMetricsTests(unittest.TestCase):
    def test_normalize_handles_turkish_characters_and_whitespace(self):
        self.assertEqual(normalize("  YÜZDE   Elli Çözüm  "), "yuzde elli cozum")

    def test_no_answer_detection_accepts_standard_guard_response(self):
        self.assertTrue(is_no_answer("Bu bilgi yüklenen belgede açıkça yer almıyor."))
        self.assertFalse(is_no_answer("Belgeye göre ücret 48.000 TL'dir."))

    def test_score_case_calculates_retrieval_answer_and_grounding_metrics(self):
        case = {
            "id": "duration",
            "category": "duration",
            "question": "Süre kaç gündür?",
            "expectedSourceChunks": [2],
            "requiredAnswerTerms": ["30", "gün"],
        }
        result = {
            "answer": "Belgeye göre süre 30 gündür.",
            "sources": [
                {"chunkIndex": 2, "text": "Süre 30 gündür."},
                {"chunkIndex": 1, "text": "Başka bilgi."},
            ],
            "trace": {"verificationDecision": {"supported": True}},
        }

        scored = score_case(case, result, duration_ms=12.5)

        self.assertTrue(scored["passed"])
        self.assertEqual(scored["retrieval"]["recallAtK"], 1.0)
        self.assertEqual(scored["retrieval"]["precisionAtK"], 0.5)
        self.assertEqual(scored["retrieval"]["reciprocalRank"], 1.0)
        self.assertTrue(scored["answerCorrect"])
        self.assertTrue(scored["grounded"])

    def test_score_case_marks_forbidden_fact_as_failure(self):
        case = {
            "id": "wrong-percentage",
            "question": "İndirim kaçtır?",
            "evaluationMode": "guard",
            "expectedSourceChunks": [0],
            "requiredAnswerTerms": ["50"],
            "forbiddenAnswerTerms": ["25"],
        }
        result = {
            "answer": "İndirim yüzde 25'tir.",
            "sources": [{"chunkIndex": 0, "text": "İndirim yüzde 50'dir."}],
            "trace": {"verificationDecision": {"supported": False}},
        }

        scored = score_case(case, result, duration_ms=1)

        self.assertFalse(scored["passed"])
        self.assertIn("answer-expectation-failed", scored["failures"])
        self.assertIn("25", scored["forbiddenAnswerTermsFound"])

    def test_no_answer_case_does_not_require_retrieval_source(self):
        case = {
            "id": "missing",
            "question": "Belgede olmayan bilgi nedir?",
            "shouldAnswer": False,
            "expectedSourceChunks": [],
        }
        result = {
            "answer": "Bu bilgi belgede yer almıyor.",
            "sources": [],
            "trace": {"provider": "retrieval-guard"},
        }

        scored = score_case(case, result, duration_ms=2)

        self.assertTrue(scored["passed"])
        self.assertTrue(scored["answerCorrect"])
        self.assertTrue(scored["grounded"])
        self.assertFalse(scored["retrieval"]["applicable"])

    def test_aggregate_and_quality_gate_decisions(self):
        base = {
            "passed": True,
            "shouldAnswer": True,
            "answerIsNoAnswer": False,
            "answerCorrect": True,
            "grounded": True,
            "citationApplicable": True,
            "citationCorrect": True,
            "guardCorrect": True,
            "evaluationMode": "pipeline",
            "durationMs": 10,
            "retrieval": {
                "applicable": True,
                "recallAtK": 1.0,
                "precisionAtK": 0.5,
                "reciprocalRank": 1.0,
            },
        }
        metrics = aggregate_results([base, {**base, "durationMs": 30}])
        decisions = evaluate_quality_gates(metrics, {"retrieval.recallAtK": 0.9, "casePassRate": 1.0})

        self.assertEqual(metrics["retrieval"]["recallAtK"], 1.0)
        self.assertEqual(metrics["latencyMs"]["p50"], 20.0)
        self.assertTrue(all(decision["passed"] for decision in decisions))

    def test_percentile_uses_linear_interpolation(self):
        self.assertEqual(percentile([10, 20, 30], 0.5), 20)
        self.assertEqual(percentile([], 0.95), 0.0)


if __name__ == "__main__":
    unittest.main()
