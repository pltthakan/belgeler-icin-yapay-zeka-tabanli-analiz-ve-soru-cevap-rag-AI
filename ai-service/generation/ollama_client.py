from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

from prompts.prompt_builder import build_ollama_prompt


class OllamaClientMixin:
    def _answer_with_ollama(
        self,
        question: str,
        sources: List[Dict[str, Any]],
        document_profile: Dict[str, str],
        response_mode: str,
    ) -> tuple[str, Dict[str, Any]] | None:
        """Yapılandırılmışsa kaynaklarla sınırlı bir Ollama cevabı üretir."""
        if not self.ollama_base_url or not self.ollama_model:
            return None

        prompt = build_ollama_prompt(
            question=question,
            sources=sources,
            document_profile=document_profile,
            response_mode=response_mode,
            shorten=self._shorten,
        )
        payload = json.dumps({
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            # Qwen3 thinking modunda önce iç muhakemeyi üretir. Kısa RAG
            # cevaplarında bu, çıktı bütçesini tüketip response alanını boş
            # bırakabildiği için kapatılır.
            "think": False,
            "options": {"temperature": 0, "num_predict": 256},
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.ollama_base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.ollama_timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
            answer = self._sanitize_generated_answer(str(result.get("response", "")))
            if response_mode == "critique" and not self._is_grounded_critique(answer, sources):
                return self._safe_critique_answer(), {
                    "provider": "ollama-safety-guard",
                    "model": self.ollama_model,
                    "responseMode": response_mode,
                    "prompt": prompt,
                }
            if answer:
                return answer, {
                    "provider": "ollama",
                    "model": self.ollama_model,
                    "responseMode": response_mode,
                    "prompt": prompt,
                }
            return None
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"Ollama cevabı alınamadı, QA fallback kullanılacak: {exc}")
            return None
