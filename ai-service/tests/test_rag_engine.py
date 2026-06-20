import io
import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
