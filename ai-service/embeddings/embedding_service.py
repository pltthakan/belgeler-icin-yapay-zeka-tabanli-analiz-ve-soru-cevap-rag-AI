from __future__ import annotations

from typing import List

import numpy as np

from app.cache import stable_hash


class EmbeddingServiceMixin:
    def _embed_question(self, question: str) -> np.ndarray:
        cache_key = (
            f"embedding:{stable_hash(self.embedding_model_name)[:16]}:"
            f"question:{stable_hash(self._normalize_cache_text(question))}"
        )
        cached_vector = self.cache.get_json(cache_key)
        if isinstance(cached_vector, list):
            try:
                vector = np.array(cached_vector, dtype=np.float32)
                if vector.shape == (384,):
                    return vector
            except Exception:
                pass

        vector = self._embed_texts([question])[0]
        # Fallback HashingVectorizer sonuçları cache'lenmez; pgvector indeksleri
        # normalde açık kaynak embedding modeliyle üretildiği için cache anahtarı
        # sadece model tabanlı soru vektörleri için kalıcı tutulur.
        if self._embedding_model is not None:
            self.cache.set_json(cache_key, vector.tolist(), self.cache.embedding_ttl_seconds)
        return vector

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        model = self._get_embedding_model()
        if model is not None:
            vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return np.array(vectors, dtype=np.float32)

        # Fallback: açık kaynak model indirilemezse hashing tabanlı vektörleme.
        vectors = self._hashing_vectorizer.transform(texts).toarray()
        return np.array(vectors, dtype=np.float32)
