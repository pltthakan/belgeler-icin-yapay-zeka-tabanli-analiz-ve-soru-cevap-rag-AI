from __future__ import annotations

import re
import time
from typing import Any, Dict, List


class QueryAnalysisMixin:
    def _normalize_question_for_retrieval(self, question: str) -> str:
        corrected_question = self._correct_question_typos(question)
        normalized = self._normalize_for_matching(corrected_question)
        expansions = []
        for group in self._question_alias_groups():
            if any(self._contains_question_marker(normalized, marker) for marker in group["triggers"]):
                expansions.extend(group["aliases"])

        if self._classify_response_mode(corrected_question) == "summary":
            expansions.extend((
                "ozet", "konu", "ana konu", "amac", "kapsam", "icerik",
                "ne anlatiliyor", "ne hakkinda",
            ))

        query_parts = [corrected_question]
        if expansions:
            query_parts.append(" ".join(dict.fromkeys(expansions)))
        return self._normalize_whitespace(" ".join(query_parts))

    def _correct_question_typos(self, question: str) -> str:
        normalized = self._normalize_for_matching(question)
        typo_corrections = {
            "bulegede": "belgede",
            "bulgede": "belgede",
            "belgee": "belge",
            "belgdee": "belgede",
            "dokumanda": "dokumanda",
            "pdfde": "pdfde",
            "egitmler": "egitmenler",
            "egitimler": "egitmenler",
            "egitmnler": "egitmenler",
            "egitmenlr": "egitmenler",
            "egitmn": "egitmen",
            "egitmen kimdr": "egitmen kimdir",
            "kimdr": "kimdir",
            "kmdir": "kimdir",
            "anlatiliyo": "anlatiliyor",
            "anlatiliyr": "anlatiliyor",
            "anlatilyor": "anlatiliyor",
            "hazirliyan": "hazirlayan",
            "hazirlayanlar": "hazirlayanlar",
            "sorumlusu kimdr": "sorumlusu kimdir",
            "nerde": "nerede",
            "nerden": "nereden",
            "tarihi ne": "tarih nedir",
            "onemlimi": "onemli mi",
        }
        corrected = normalized
        for wrong, right in typo_corrections.items():
            corrected = re.sub(rf"\b{re.escape(wrong)}\b", right, corrected)
        return corrected

    def _question_alias_groups(self) -> List[Dict[str, tuple[str, ...]]]:
        return [
            {
                "triggers": (
                    "ozet", "konu", "hakkinda", "ne anlatiliyor", "ne anlatiyor",
                    "icerik", "icerigi", "neler var", "neler yer aliyor", "nedir",
                ),
                "aliases": (
                    "ozet", "konu", "ana konu", "icerik", "amac", "kapsam",
                    "ne anlatiliyor", "ne hakkinda", "belge", "dokuman",
                ),
            },
            {
                "triggers": (
                    "yazar", "yazarlar", "sahip", "sahibi", "hazirlayan",
                    "hazirlayanlar", "sorumlu", "sorumlusu", "egitmen",
                    "egitmenler", "egitimci", "egitimciler", "egitimi veren",
                    "ders sorumlusu", "hoca", "hocasi", "veren kim", "kim verdi",
                ),
                "aliases": (
                    "egitmen", "egitmenler", "egitimci", "egitimciler",
                    "hazirlayan", "hazirlayanlar", "yazar", "yazarlar",
                    "sorumlu", "sorumlusu", "ders sorumlusu", "hoca",
                    "gorevli", "kisi", "kisiler",
                ),
            },
            {
                "triggers": (
                    "tarih", "tarihi", "ne zaman", "baslangic", "baslama",
                    "bitis", "sure", "kac gun", "hangi gun", "hangi tarihte",
                ),
                "aliases": (
                    "tarih", "baslangic tarihi", "bitis tarihi", "sure",
                    "zaman", "gun", "ay", "yil", "donem",
                ),
            },
            {
                "triggers": (
                    "nerede", "nereden", "nereye", "neresi", "hangi sehir",
                    "sehir", "il", "adres", "konum", "lokasyon", "yer",
                ),
                "aliases": (
                    "yer", "konum", "adres", "sehir", "il", "lokasyon",
                    "nerede", "nereden", "nereye",
                ),
            },
            {
                "triggers": (
                    "amac", "amaci", "hedef", "hedefi", "neden", "ne icin",
                    "kapsam", "kapsami", "ne ise yarar",
                ),
                "aliases": (
                    "amac", "hedef", "kapsam", "gerekce", "ne icin",
                    "ne ise yarar", "fayda",
                ),
            },
            {
                "triggers": (
                    "katilimci", "katilimcilar", "kimler katilabilir",
                    "hedef kitle", "ogrenci", "ogrenciler", "kursiyer",
                    "kursiyerler", "kime yonelik",
                ),
                "aliases": (
                    "katilimci", "katilimcilar", "hedef kitle", "ogrenci",
                    "ogrenciler", "kursiyer", "kursiyerler", "kime yonelik",
                ),
            },
            {
                "triggers": (
                    "ucret", "fiyat", "bedel", "maliyet", "tutar", "odeme",
                    "kac tl", "kac lira", "para",
                ),
                "aliases": (
                    "ucret", "fiyat", "bedel", "maliyet", "tutar", "odeme",
                    "tl", "lira", "para",
                ),
            },
            {
                "triggers": (
                    "gano", "not ortalamasi", "genel not ortalamasi", "ortalama",
                    "universiteye giris sirasi",
                ),
                "aliases": (
                    "gano", "not ortalamasi", "genel not ortalamasi",
                    "universiteye giris sirasi", "basvuru kriterleri",
                    "teknik uzmanlik sinavi", "teknik mulakat", "basari puani",
                ),
            },
        ]

    def _contains_question_marker(self, normalized_question: str, marker: str) -> bool:
        normalized_marker = self._normalize_for_matching(marker)
        if " " in normalized_marker:
            return normalized_marker in normalized_question
        return re.search(rf"\b{re.escape(normalized_marker)}\b", normalized_question) is not None

    def _classify_response_mode(self, question: str) -> str:
        normalized = self._normalize_for_matching(question)
        critique_markers = (
            "ne dusunuyorsun",
            "sence",
            "degerlendir",
            "degerlendirme",
            "negatif",
            "olumsuz",
            "zayif",
            "eksik",
            "gelistir",
            "iyilestir",
            "guclu yon",
            "risk",
        )
        if any(marker in normalized for marker in critique_markers):
            return "critique"

        summary_markers = (
            "ana konusu",
            "ana konu",
            "belgenin konusu",
            "dokumanin konusu",
            "dokuman konusu",
            "bu belge nedir",
            "bu dokuman nedir",
            "bu nasil bir belge",
            "nasil bir belge",
            "bu nasil bir dokuman",
            "nasil bir dokuman",
            "belgenin icerigi ne",
            "belge icerigi ne",
            "dokumanin icerigi ne",
            "dokuman icerigi ne",
            "bu belgede neler var",
            "belgede neler var",
            "bu dokumanda neler var",
            "dokumanda neler var",
            "bu belgede ne anlatiliyor",
            "bu belge ne anlatiyor",
            "belgede ne anlatiliyor",
            "belge ne anlatiyor",
            "bu belgede neler yer aliyor",
            "belgede neler yer aliyor",
            "bu dokumanda neler yer aliyor",
            "dokumanda neler yer aliyor",
            "hangi bilgiler var",
            "hangi bilgiler yer aliyor",
            "ne iceriyor",
            "neler iceriyor",
            "icerisinde neler var",
            "icinde neler var",
            "belgenin amaci",
            "dokumanin amaci",
            "amac ne",
            "amaci ne",
            "ne ise yarar",
            "neye yarar",
            "bu belge ne ise yarar",
            "bu dokuman ne ise yarar",
            "belgeyi ozetle",
            "bu belgeyi ozetle",
            "kisa ozet",
            "genel ozet",
            "ne hakkinda",
            "konusu nedir",
            "genel konusu",
        )
        if any(marker in normalized for marker in summary_markers):
            return "summary"
        return "factual"

    def _is_document_overview_question(self, question: str) -> bool:
        return self._classify_response_mode(question) == "summary"


class OrderSensitiveAnswerMixin:
    def _answer_order_sensitive_question(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
        document_profile: Dict[str, str],
        top_k: int,
        started_at: float,
    ) -> Dict[str, Any] | None:
        direction = self._order_sensitive_direction(question)
        if direction is None:
            return None

        structured_result = self._answer_latest_course_question(question, chunks, started_at)
        if structured_result is not None:
            return structured_result

        sources = self._ordered_sources(chunks, direction, top_k)
        if not sources:
            return None

        answer, generation = self._build_answer_result(question, sources, document_profile)
        generation = {**generation, "retrievalStrategy": f"document-order-{direction}"}
        return {
            "answer": answer,
            "sources": sources,
            "trace": self._build_trace(
                generation=generation,
                selected_sources=sources,
                duration_ms=(time.perf_counter() - started_at) * 1000,
            ),
        }

    def _answer_latest_course_question(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
        started_at: float,
    ) -> Dict[str, Any] | None:
        if not self._is_latest_course_question(question):
            return None

        latest_course = self._extract_latest_course(chunks)
        if latest_course is None:
            return None

        answer = (
            f"Belgeye göre en son dönem {latest_course['term']}; "
            f"bu dönemde görünen ders {latest_course['code']} {latest_course['name']} dersidir."
        )
        sources = [latest_course["source"]]

        return {
            "answer": answer,
            "sources": sources,
            "trace": self._build_trace(
                generation={
                    "provider": "transcript-structure",
                    "model": None,
                    "responseMode": "factual",
                    "prompt": None,
                },
                selected_sources=sources,
                duration_ms=(time.perf_counter() - started_at) * 1000,
            ),
        }

    def _order_sensitive_direction(self, question: str) -> str | None:
        normalized = self._normalize_for_matching(question)
        if re.search(r"\b(?:en\s+son|son|sonuncu|en\s+yeni|guncel|latest)\b", normalized):
            return "last"
        if re.search(r"\b(?:ilk|birinci|baslangic|en\s+eski|oldest)\b", normalized):
            return "first"
        return None

    def _ordered_sources(
        self,
        chunks: List[Dict[str, Any]],
        direction: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        ordered = sorted(
            chunks,
            key=lambda source: int(source.get("chunkIndex") or 0),
        )
        limit = max(top_k, 1)
        if direction == "first":
            return ordered[:limit]
        if direction == "last":
            return ordered[-limit:]
        return []

    def _is_latest_course_question(self, question: str) -> bool:
        normalized = self._normalize_for_matching(question)
        return "ders" in normalized and any(marker in normalized for marker in (
            "aldigi son",
            "en son aldigi",
            "son aldigi",
            "son ders",
            "en son ders",
        ))

    def _extract_latest_course(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any] | None:
        latest = None
        current_term = None
        term_pattern = re.compile(r"(\d{4}-\d{4})\s*(Güz|Bahar|Yaz)", re.IGNORECASE)
        course_pattern = re.compile(
            r"\b([A-ZÇĞİÖŞÜ]{2,}\d{3}-\d{4})\s+(.+?)\s+"
            r"(\d+)\s+(A1|A2|A3|B1|B2|B3|C1|C2|C3|D1|D2|D3|F1|F2|F3|FF|DZ|YT|YZ)\s+"
            r"[\d,]+\s+\d+\b"
        )

        for chunk in chunks:
            for raw_line in chunk.get("text", "").splitlines():
                line = self._normalize_whitespace(raw_line)
                if not line:
                    continue

                term_match = term_pattern.search(line)
                if term_match:
                    current_term = {
                        "label": f"{term_match.group(1)} {term_match.group(2)}",
                        "sort": self._term_sort_key(term_match.group(1), term_match.group(2)),
                    }

                if current_term is None:
                    continue

                course_match = course_pattern.search(line)
                if not course_match:
                    continue

                candidate = {
                    "term": current_term["label"],
                    "termSort": current_term["sort"],
                    "code": course_match.group(1),
                    "name": self._normalize_whitespace(course_match.group(2)),
                    "source": {
                        "pageNumber": chunk.get("pageNumber"),
                        "chunkIndex": chunk.get("chunkIndex"),
                        "score": chunk.get("score", 1.0),
                        "text": line,
                    },
                }
                if latest is None or candidate["termSort"] >= latest["termSort"]:
                    latest = candidate

        return latest

    def _term_sort_key(self, academic_year: str, term_name: str) -> tuple[int, int]:
        start_year = int(academic_year.split("-", 1)[0])
        term_order = {
            "guz": 1,
            "bahar": 2,
            "yaz": 3,
        }
        return (start_year, term_order.get(self._normalize_for_matching(term_name), 0))
