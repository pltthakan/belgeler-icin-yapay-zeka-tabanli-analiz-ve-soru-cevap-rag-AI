import io
import os
import tempfile
import unittest
from unittest.mock import patch

from docx import Document

from rag_engine import RagEngine


class RagEngineAnswerTests(unittest.TestCase):
    def setUp(self):
        self.previous_ollama_base_url = os.environ.get("OLLAMA_BASE_URL")
        self.previous_ollama_model = os.environ.get("OLLAMA_MODEL")
        os.environ["OLLAMA_BASE_URL"] = ""
        os.environ["OLLAMA_MODEL"] = ""
        self.data_dir = tempfile.TemporaryDirectory()
        self.engine = RagEngine(self.data_dir.name)

    def tearDown(self):
        self.data_dir.cleanup()
        self._restore_environment_variable("OLLAMA_BASE_URL", self.previous_ollama_base_url)
        self._restore_environment_variable("OLLAMA_MODEL", self.previous_ollama_model)

    def _restore_environment_variable(self, name, value):
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    def test_document_overview_questions_use_the_same_document_profile(self):
        chunks = [{
            "text": (
                "İNÖNÜ ÜNİVERSİTESİ MÜHENDİSLİK FAKÜLTESİ BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ\n"
                "İŞLETMEDE MESLEKİ EĞİTİM DERSİ\n"
                "ÖĞRENCİLERİN İŞLETME DEĞERLENDİRME ANKETİ\n"
                "20- Eğitim bittikten sonra çalışmak ister misiniz?"
            )
        }]
        sources = [{"text": "20- Eğitim bittikten sonra çalışmak ister misiniz?"}]
        document_profile = self.engine._build_document_profile(chunks)

        answers = [
            self.engine._build_answer(question, sources, document_profile)
            for question in (
                "Bu belgenin ana konusu nedir?",
                "Bu belge nedir?",
                "Bu belgede ne anlatılıyor?",
                "Belgeyi özetle.",
            )
        ]

        expected_answer = (
            "Bu belge, “İŞLETMEDE MESLEKİ EĞİTİM DERSİ — "
            "ÖĞRENCİLERİN İŞLETME DEĞERLENDİRME ANKETİ” başlıklı bir ankettir."
        )
        self.assertEqual(answers, [expected_answer] * 4)

    def test_topic_question_detects_turkish_dotted_and_dotless_i(self):
        self.assertTrue(self.engine._is_document_overview_question("Bu belgenin ana konusu nedir?"))
        self.assertTrue(self.engine._is_document_overview_question("Belge ne hakkında?"))
        self.assertTrue(self.engine._is_document_overview_question("Bu belgede ne anlatılıyor?"))
        self.assertTrue(self.engine._is_document_overview_question("Bu nasıl bir belge?"))
        self.assertTrue(self.engine._is_document_overview_question("Belgenin içeriği ne?"))
        self.assertTrue(self.engine._is_document_overview_question("Bu belgede neler var?"))

    def test_response_mode_distinguishes_summary_critique_and_factual_questions(self):
        self.assertEqual(self.engine._classify_response_mode("Bu belgeyi özetle."), "summary")
        self.assertEqual(self.engine._classify_response_mode("Bu CV'nin eksikleri neler?"), "critique")
        self.assertEqual(self.engine._classify_response_mode("Ödeme süresi kaç gün?"), "factual")

    def test_critique_fallback_does_not_present_an_inference_as_a_fact(self):
        answer = self.engine._build_answer(
            "Bu CV'nin eksikleri neler?",
            [{"text": "Adayın Java ve React projeleri bulunuyor."}],
            {"title": "Aday CV'si", "summary": "Adayın teknik projelerini içeren CV."},
        )

        self.assertIn("yerel LLM", answer)
        self.assertNotIn("negatif taraf", answer.lower())

    def test_extractive_fallback_returns_relevant_sentences_only(self):
        passage = self.engine._extract_relevant_passage(
            "Ödenen ücrette memnun musunuz?",
            "Program sonunda çalışmak ister misiniz? Ödenen ücrette memnun musunuz? EVET HAYIR.",
        )

        self.assertEqual(passage, "Ödenen ücrette memnun musunuz?")

    def test_latest_course_question_uses_transcript_term_order(self):
        chunks = [
            {
                "chunkIndex": 0,
                "pageNumber": 1,
                "score": 1.0,
                "text": (
                    "Ders Kodu Ders Adı Krd2024-2025 Güz\n"
                    "BİLM289-2022 Veri Organizasyonu 3 B1 16,25 5\n"
                    "Ders Kodu Ders Adı Krd2025-2026 Bahar\n"
                    "BİLM468-2022 İşletmede Mesleki Eğitim 5 A1 120 30"
                ),
            }
        ]

        result = self.engine._answer_latest_course_question("Aldığı son ders nedir?", chunks, 0)

        self.assertIsNotNone(result)
        self.assertIn("2025-2026 Bahar", result["answer"])
        self.assertIn("BİLM468-2022 İşletmede Mesleki Eğitim", result["answer"])
        self.assertEqual(result["trace"]["provider"], "transcript-structure")

    def test_order_sensitive_questions_use_document_order_for_any_document_type(self):
        chunks = [
            {"chunkIndex": 0, "text": "İlk bölüm: başvuru koşulları."},
            {"chunkIndex": 1, "text": "Orta bölüm: değerlendirme süreci."},
            {"chunkIndex": 2, "text": "Son bölüm: kararın tebliği."},
        ]

        self.assertEqual(self.engine._order_sensitive_direction("Son bölüm nedir?"), "last")
        self.assertEqual(self.engine._order_sensitive_direction("İlk bölüm nedir?"), "first")
        self.assertEqual(
            [source["chunkIndex"] for source in self.engine._ordered_sources(chunks, "last", 2)],
            [1, 2],
        )
        self.assertEqual(
            [source["chunkIndex"] for source in self.engine._ordered_sources(chunks, "first", 2)],
            [0, 1],
        )

    def test_qa_quality_gate_rejects_single_character_spans(self):
        self.assertFalse(self.engine._is_usable_qa_answer("I"))
        self.assertFalse(self.engine._is_usable_qa_answer(" "))
        self.assertTrue(self.engine._is_usable_qa_answer("30"))
        self.assertTrue(self.engine._is_usable_qa_answer("Öğrencilerin hakları"))

    def test_generated_answer_sanitizer_removes_answer_and_source_labels(self):
        answer = self.engine._sanitize_generated_answer(
            "Cevap: Adayın backend deneyimi öne çıkıyor. Kaynak 1 ve 2'de projeler yer alıyor."
        )

        self.assertEqual(answer, "Adayın backend deneyimi öne çıkıyor.")

    def test_critique_guard_rejects_claims_contradicted_by_sources(self):
        sources = [{
            "text": (
                "EXPERIENCE\nSoftware Developer Intern\nFeb 2026 – Jun 2026\n"
                "SKILLS\nJava, Spring Boot, Python, Flask, React\n"
                "PROJECTS\nBuilt a financial dashboard and implemented REST APIs."
            )
        }]
        unsupported = (
            "Belgeye dayalı değerlendirme: deneyimlerin tarihlendirilmemiş olması, "
            "teknik becerilerin eksik belirtilmesi ve proje açıklamalarının tamamlanmamış olması."
        )

        self.assertFalse(self.engine._is_grounded_critique(unsupported, sources))
        self.assertTrue(self.engine._is_grounded_critique(self.engine._safe_critique_answer(), sources))

    def test_docx_extraction_includes_table_cells_in_document_order(self):
        document = Document()
        document.add_paragraph("Başlık")
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Ödeme süresi"
        table.cell(0, 1).text = "30 gün"
        document.add_paragraph("Son not")
        raw_bytes = io.BytesIO()
        document.save(raw_bytes)

        pages = self.engine._extract_docx_pages(raw_bytes.getvalue())

        self.assertEqual(pages[0]["text"], "Başlık\nÖdeme süresi | 30 gün\nSon not")

    def test_pdf_page_extraction_falls_back_when_pypdf_fails(self):
        class BrokenPage:
            def extract_text(self):
                raise ValueError("Odd-length string")

        with patch.object(
            self.engine,
            "_extract_pdf_page_text_with_pymupdf",
            return_value="Fallback PDF metni",
        ) as fallback:
            text = self.engine._extract_pdf_page_text(BrokenPage(), b"%PDF", 1)

        self.assertEqual(text, "Fallback PDF metni")
        fallback.assert_called_once_with(b"%PDF", 1)

    def test_relevance_guard_rejects_low_score_without_calling_a_model(self):
        result = self.engine._relevance_guard_result(
            "Sözleşme hangi şehirde imzalandı?",
            [{"score": 0.04, "text": "Öğrencinin ders notları listelenmiştir."}],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["provider"], "retrieval-guard")
        self.assertEqual(result["guardReason"], "low-retrieval-score")

    def test_relevance_guard_rejects_obvious_gibberish_even_with_an_accidental_match(self):
        result = self.engine._relevance_guard_result(
            "sjdhfsahjd",
            [{"score": 0.72, "text": "Öğrencinin ders notları listelenmiştir."}],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["guardReason"], "gibberish-question")

    def test_relevance_guard_rejects_low_information_chat_noise(self):
        sources = [{"score": 0.72, "text": "Hakan Polat'ın 2022-2023 Bahar dönemi not ortalaması 0,70."}]

        for question in ("la get", "ne bileyim ben"):
            with self.subTest(question=question):
                result = self.engine._relevance_guard_result(question, sources)

                self.assertIsNotNone(result)
                self.assertEqual(result["guardReason"], "low-information-question")

    def test_relevance_guard_keeps_short_queries_that_match_document_terms(self):
        result = self.engine._relevance_guard_result(
            "ortalama",
            [{"score": 0.72, "text": "Hakan Polat'ın 2022-2023 Bahar dönemi not ortalaması 0,70."}],
        )

        self.assertIsNone(result)

    def test_relevance_guard_keeps_document_overview_questions(self):
        for question in (
            "Bu belgenin ana konusu nedir?",
            "Bu nasıl bir belge?",
            "Belgenin içeriği ne?",
            "Bu belgede neler var?",
        ):
            with self.subTest(question=question):
                result = self.engine._relevance_guard_result(
                    question,
                    [{"score": 0.01, "text": "Öğrencinin ders notları listelenmiştir."}],
                )

                self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
