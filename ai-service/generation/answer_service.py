from __future__ import annotations

import re
from typing import Any, Dict, List


class AnswerServiceMixin:
    def _build_answer(
        self,
        question: str,
        sources: List[Dict[str, Any]],
        document_profile: Dict[str, str],
    ) -> str:
        answer, _ = self._build_answer_result(question, sources, document_profile)
        return answer

    def _build_answer_result(
        self,
        question: str,
        sources: List[Dict[str, Any]],
        document_profile: Dict[str, str],
    ) -> tuple[str, Dict[str, Any]]:
        if not sources:
            return "Bu belge içinde soruyla ilişkili bir bölüm bulunamadı.", {
                "provider": "retrieval",
                "model": None,
                "responseMode": self._classify_response_mode(question),
                "prompt": None,
            }

        response_mode = self._classify_response_mode(question)
        generated_result = self._answer_with_ollama(
            question=question,
            sources=sources,
            document_profile=document_profile,
            response_mode=response_mode,
        )
        if generated_result:
            answer, generation = generated_result
            if not self._is_grounded_answer(question, answer, sources, response_mode):
                return self._out_of_scope_answer(), {
                    **generation,
                    "provider": "answer-grounding-guard",
                    "guardReason": "unsupported-generated-answer",
                }
            return answer, generation

        # Yerel LLM kapalıysa belge-genel sorular için QA modelinin rastgele bir
        # span seçmesine izin verme. Belge profili tüm ifade biçimlerinde aynı
        # güvenilir özeti sağlar.
        if response_mode == "summary" and document_profile.get("summary"):
            return document_profile["summary"], {
                "provider": "document-profile",
                "model": None,
                "responseMode": response_mode,
                "prompt": None,
            }

        if response_mode == "critique":
            return (
                "Belgeye dayalı değerlendirme üretmek için yerel LLM yanıt üretimi etkin olmalıdır. "
                "İlgili kaynak parçaları aşağıda gösterilmiştir.",
                {
                    "provider": "critique-fallback",
                    "model": None,
                    "responseMode": response_mode,
                    "prompt": None,
                },
            )

        qa_pipeline = self._get_qa_pipeline()
        if qa_pipeline is not None:
            best_answer = None
            best_score = -1.0
            for source in sources:
                try:
                    result = qa_pipeline(question=question, context=source["text"])
                    score = float(result.get("score", 0.0))
                    answer = str(result.get("answer", "")).strip()
                    if answer and score > best_score:
                        best_score = score
                        best_answer = answer
                except Exception:
                    continue

            if best_answer and best_score >= 0.02 and self._is_usable_qa_answer(best_answer):
                return f"Belgeye göre: {best_answer}", {
                    "provider": "huggingface-qa",
                    "model": self.qa_model_name,
                    "responseMode": response_mode,
                    "prompt": None,
                }

        # Model kullanılamadığında ham 900 karakterlik chunk döndürmek yerine,
        # soruyla en fazla kesişen kısa cümleleri seç.
        short_text = self._extract_relevant_passage(question, sources[0]["text"])
        return f"Belgeye göre: {short_text}", {
            "provider": "extractive-fallback",
            "model": None,
            "responseMode": response_mode,
            "prompt": None,
        }

    def _sanitize_generated_answer(self, answer: str) -> str:
        """Modelin kullanıcı arayüzünde zaten bulunan cevap/kaynak etiketlerini temizler."""
        cleaned = self._repair_text_artifacts(answer.strip())
        cleaned = re.sub(r"(?im)^\s*(?:cevap|yanıt)\s*:\s*", "", cleaned)
        cleaned = re.sub(
            r"(?is)(?:\s|\n)*(?:kaynak|source)\s*(?:parçası?|chunk)?\s*\d+"
            r"(?:\s*(?:ve|,|-)\s*(?:(?:kaynak|source)\s*)?\d+)*[^.!?\n]*(?:[.!?]|$)",
            "",
            cleaned,
        )
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()
