from __future__ import annotations

import logging
import re
from typing import Any, Dict, List


logger = logging.getLogger("uvicorn.error").getChild("rag.guard")


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
        application_answer = self._answer_application_requirement_question(question, sources)
        if application_answer is not None:
            return application_answer, {
                "provider": "application-requirements-structure",
                "model": None,
                "responseMode": response_mode,
                "prompt": None,
            }

        generated_result = self._answer_with_ollama(
            question=question,
            sources=sources,
            document_profile=document_profile,
            response_mode=response_mode,
        )
        if generated_result:
            answer, generation = generated_result
            evidence = self._evidence_support_decision(question, sources)
            if self._is_no_answer_response(answer):
                if evidence["supported"]:
                    supported_answer = self._answer_from_supported_evidence(question, sources, evidence)
                    self._log_fallback_decision(
                        reason="model-no-answer-despite-supported-evidence",
                        evidence=evidence,
                        generation=generation,
                    )
                    return supported_answer, {
                        **generation,
                        "provider": "evidence-supported-fallback",
                        "guardReason": "model-no-answer-despite-supported-evidence",
                        "evidenceDecision": evidence,
                    }
                self._log_fallback_decision(
                    reason="no-retrieved-chunk-supports-main-claim",
                    evidence=evidence,
                    generation=generation,
                )
                return answer, {
                    **generation,
                    "guardReason": "no-retrieved-chunk-supports-main-claim",
                    "evidenceDecision": evidence,
                }

            if not self._is_grounded_answer(question, answer, sources, response_mode):
                if evidence["supported"]:
                    supported_answer = self._answer_from_supported_evidence(question, sources, evidence)
                    self._log_fallback_decision(
                        reason="unsupported-generation-replaced-by-supported-evidence",
                        evidence=evidence,
                        generation=generation,
                    )
                    return supported_answer, {
                        **generation,
                        "provider": "evidence-supported-fallback",
                        "guardReason": "unsupported-generation-replaced-by-supported-evidence",
                        "evidenceDecision": evidence,
                    }
                self._log_fallback_decision(
                    reason="unsupported-generated-answer",
                    evidence=evidence,
                    generation=generation,
                )
                return self._out_of_scope_answer(), {
                    **generation,
                    "provider": "answer-grounding-guard",
                    "guardReason": "unsupported-generated-answer",
                    "evidenceDecision": evidence,
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
        combined_sources = "\n".join(str(source.get("text", "")) for source in sources[:3])
        short_text = self._extract_relevant_passage(question, combined_sources)
        return f"Belgeye göre: {short_text}", {
            "provider": "extractive-fallback",
            "model": None,
            "responseMode": response_mode,
            "prompt": None,
        }

    def _answer_application_requirement_question(
        self,
        question: str,
        sources: List[Dict[str, Any]],
    ) -> str | None:
        normalized_question = self._normalize_for_matching(question)
        if "basvur" not in normalized_question or not any(
            marker in normalized_question for marker in ("sart", "kriter", "kosul")
        ):
            return None

        context = "\n".join(str(source.get("text", "")) for source in sources)
        normalized_context = self._normalize_for_matching(context)
        if "aday muhendis" not in normalized_context:
            return None

        departments = self._extract_engineering_departments(context)
        class_requirement = self._extract_student_class_requirement(context)
        has_exam_process = all(
            marker in normalized_context
            for marker in ("genel yetenek", "ingilizce", "teknik mulakat")
        )
        has_gpa_rule = "genel not ortalamasi" in normalized_context and "universiteye giris sirasi" in normalized_context

        if not any((departments, class_requirement, has_exam_process, has_gpa_rule)):
            return None

        sentences = []
        if class_requirement:
            sentences.append(f"Belgeye göre {class_requirement} başvurabilir.")
        if departments:
            sentences.append(f"Uygun bölümler: {', '.join(departments)}.")
        process_parts = []
        if has_gpa_rule:
            process_parts.append(
                "Genel Not Ortalaması + (10.000 / Üniversiteye Giriş Sırası) kriteri teknik uzmanlık sınavı gerekliliğini belirler"
            )
        if has_exam_process:
            process_parts.append(
                "süreç Genel Yetenek ve İngilizce sınavı, teknik mülakat, kurul mülakatı ve göreve başlama onayıyla ilerler"
            )
        if process_parts:
            sentences.append("; ".join(process_parts) + ".")
        return " ".join(sentences)

    def _answer_from_supported_evidence(
        self,
        question: str,
        sources: List[Dict[str, Any]],
        evidence: Dict[str, Any],
    ) -> str:
        percentages = evidence.get("matchedPercentages") or []
        relations = set(evidence.get("matchedRelations") or [])
        normalized_question = self._normalize_for_matching(question)
        if percentages and "discount" in relations and "kontenjan" in normalized_question:
            percentage = percentages[0]
            prefix = "YKS'de " if "yks" in normalized_question else ""
            return (
                f"Belgeye göre {prefix}%{percentage} indirimli kontenjana yerleşen öğrenci "
                f"%{percentage} öğrenim ücreti indirimi alır."
            )

        source_index = evidence.get("sourceIndex")
        if isinstance(source_index, int) and 0 <= source_index < len(sources):
            source_text = str(sources[source_index].get("text", ""))
        else:
            source_text = "\n".join(str(source.get("text", "")) for source in sources[:3])
        passage = self._extract_relevant_passage(question, source_text)
        return f"Belgeye göre: {passage}"

    def _log_fallback_decision(
        self,
        reason: str,
        evidence: Dict[str, Any],
        generation: Dict[str, Any],
    ) -> None:
        logger.info(
            "RAG fallback decision reason=%s supported=%s provider=%s sourceIndex=%s "
            "chunkIndex=%s percentages=%s entities=%s relations=%s",
            reason,
            evidence.get("supported"),
            generation.get("provider"),
            evidence.get("sourceIndex"),
            evidence.get("chunkIndex"),
            evidence.get("matchedPercentages"),
            evidence.get("matchedEntities"),
            evidence.get("matchedRelations"),
        )

    def _extract_engineering_departments(self, context: str) -> List[str]:
        departments = []
        for raw_line in context.splitlines():
            line = self._normalize_whitespace(raw_line).strip(" ,-")
            if not line or len(line) > 80:
                continue
            if "Mühendisliği" not in line and "Muhendisligi" not in line:
                continue
            if line.lower().startswith(("aday ", "hangi ", "staj", "program")):
                continue
            if line not in departments:
                departments.append(line)
        return departments[:8]

    def _extract_student_class_requirement(self, context: str) -> str | None:
        normalized_context = self._normalize_for_matching(context)
        if re.search(r"(?:^|\D)3\s+ve\s+\.?4s?\s+inif", normalized_context):
            return "tüm üniversitelerin 3. ve 4. sınıf mühendislik öğrencileri"
        if re.search(r"(?:^|\D)3\s+ve\s+4\s+sinif", normalized_context):
            return "tüm üniversitelerin 3. ve 4. sınıf mühendislik öğrencileri"
        if "4 sinifta ogrenim goren muhendislik ogrencileri" in normalized_context:
            return "4. sınıfta öğrenim gören mühendislik öğrencileri"
        return None

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
