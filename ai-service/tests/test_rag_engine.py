import io
import tempfile
import unittest

from docx import Document

from rag_engine import RagEngine


class RagEngineAnswerTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.engine = RagEngine(self.data_dir.name)

    def tearDown(self):
        self.data_dir.cleanup()

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

    def test_extractive_fallback_returns_relevant_sentences_only(self):
        passage = self.engine._extract_relevant_passage(
            "Ödenen ücrette memnun musunuz?",
            "Program sonunda çalışmak ister misiniz? Ödenen ücrette memnun musunuz? EVET HAYIR.",
        )

        self.assertEqual(passage, "Ödenen ücrette memnun musunuz?")

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
