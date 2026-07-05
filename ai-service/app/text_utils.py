from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List


class TextUtilitiesMixin:
    def _source_from_chunk(self, chunk: Dict[str, Any], score: float) -> Dict[str, Any]:
        return {
            "pageNumber": chunk.get("pageNumber"),
            "chunkIndex": chunk.get("chunkIndex"),
            "score": score,
            "text": self._repair_text_artifacts(chunk.get("text", "")),
        }

    def _meaningful_terms(self, text: str) -> set[str]:
        stop_words = {
            "acaba", "ama", "bir", "bu", "bunu", "da", "de", "gibi", "icin", "ile",
            "mi", "mu", "nasil", "ne", "nedir", "olan", "olarak", "soru", "su", "ve",
            "veya", "ya", "belge", "belgede", "belgenin", "dokuman", "dokumanda",
            "ben", "bana", "beni", "benim", "sen", "sana", "seni", "senin", "la", "lan",
            "get", "git", "hadi",
        }
        return {
            term for term in re.findall(r"[a-z0-9]+", self._normalize_for_matching(text))
            if len(term) > 2 and term not in stop_words
        }

    def _normalize_for_matching(self, text: str) -> str:
        # Kullanıcı Türkçe karakterleri yazmasa da aynı soru sınıfına düşsün.
        turkish_to_ascii = str.maketrans("çğıöşü", "cgiosu")
        return text.replace("I", "ı").replace("İ", "i").lower().translate(turkish_to_ascii)

    def _normalize_whitespace(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _contains_letters(self, text: str) -> bool:
        return bool(re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", text))

    def _looks_like_heading(self, text: str) -> bool:
        letters = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]", text)
        if not letters or "?" in text:
            return False
        uppercase_letters = [letter for letter in letters if letter.isupper()]
        return len(uppercase_letters) / len(letters) >= 0.7

    def _load_index(self, document_id: str) -> Dict[str, Any]:
        index_path = self._index_path(document_id)
        if not index_path.exists():
            raise FileNotFoundError(index_path)
        return json.loads(index_path.read_text(encoding="utf-8"))

    def _index_path(self, document_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(document_id))
        return self.index_dir / f"{safe_id}.json"

    def _clean_text(self, text: str) -> str:
        text = self._repair_text_artifacts(text)
        text = text.replace("\x00", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _repair_text_artifacts(self, text: str) -> str:
        if not text:
            return ""

        def replace_unicode_match(match) -> str:
            try:
                return chr(int(match.group(1), 16))
            except ValueError:
                return match.group(0)

        repaired = re.sub(r"/uni([0-9A-Fa-f]{4})", replace_unicode_match, text)
        repaired = repaired.replace("/idotaccent", "i").replace("/Idotaccent", "İ")
        repaired = unicodedata.normalize("NFC", repaired)
        return repaired

    def _repair_sources_text(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {**source, "text": self._repair_text_artifacts(str(source.get("text", "")))}
            for source in sources
        ]

    def _trim_to_sentence(self, text: str) -> str:
        text = text.strip()
        if len(text) < 300:
            return text
        candidates = [text.rfind(". "), text.rfind("? "), text.rfind("! "), text.rfind("\n")]
        cut = max(candidates)
        if cut > int(len(text) * 0.55):
            return text[:cut + 1]
        return text

    def _shorten(self, text: str, max_chars: int) -> str:
        text = text.strip()
        if len(text) <= max_chars:
            return text
        shortened = text[:max_chars]
        cut = max(shortened.rfind(". "), shortened.rfind("\n"))
        if cut > 300:
            shortened = shortened[:cut + 1]
        return shortened.strip() + "..."
