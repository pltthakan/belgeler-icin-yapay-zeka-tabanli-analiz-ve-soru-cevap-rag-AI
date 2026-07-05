from __future__ import annotations


class EmbeddingModelMixin:
    def _get_embedding_model(self):
        if self._embedding_model is not None:
            return self._embedding_model
        try:
            from sentence_transformers import SentenceTransformer
            self._embedding_model = SentenceTransformer(self.embedding_model_name)
            return self._embedding_model
        except Exception as exc:
            print(f"Embedding modeli yüklenemedi, HashingVectorizer fallback kullanılacak: {exc}")
            self._embedding_model = None
            return None
