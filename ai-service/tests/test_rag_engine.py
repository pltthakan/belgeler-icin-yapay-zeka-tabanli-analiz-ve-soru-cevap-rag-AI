import tempfile
import unittest

from rag_engine import RagEngine


class RagEngineAnswerTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.engine = RagEngine(self.data_dir.name)

    def tearDown(self):
        self.data_dir.cleanup()

    def test_main_topic_uses_the_document_title_not_the_retrieved_question(self):
        chunks = [{
            "text": (
                "İNÖNÜ ÜNİVERSİTESİ MÜHENDİSLİK FAKÜLTESİ BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ\n"
                "İŞLETMEDE MESLEKİ EĞİTİM DERSİ\n"
                "ÖĞRENCİLERİN İŞLETME DEĞERLENDİRME ANKETİ\n"
                "20- Eğitim bittikten sonra çalışmak ister misiniz?"
            )
        }]
        sources = [{"text": "20- Eğitim bittikten sonra çalışmak ister misiniz?"}]

        answer = self.engine._build_answer("Bu belgenin ana konusu nedir?", sources, chunks)

        self.assertEqual(
            answer,
            "Bu belgenin ana konusu: İŞLETMEDE MESLEKİ EĞİTİM DERSİ — "
            "ÖĞRENCİLERİN İŞLETME DEĞERLENDİRME ANKETİ.",
        )

    def test_topic_question_detects_turkish_dotted_and_dotless_i(self):
        self.assertTrue(self.engine._is_topic_question("Bu belgenin ana konusu nedir?"))
        self.assertTrue(self.engine._is_topic_question("Belge ne hakkında?"))

    def test_extractive_fallback_returns_relevant_sentences_only(self):
        passage = self.engine._extract_relevant_passage(
            "Ödenen ücrette memnun musunuz?",
            "Program sonunda çalışmak ister misiniz? Ödenen ücrette memnun musunuz? EVET HAYIR.",
        )

        self.assertEqual(passage, "Ödenen ücrette memnun musunuz?")


if __name__ == "__main__":
    unittest.main()
