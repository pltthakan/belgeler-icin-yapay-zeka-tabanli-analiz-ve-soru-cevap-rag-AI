import json
from typing import Any, Dict, List


class PgVectorStore:
    """PostgreSQL/pgvector backed persistent store for document chunks."""

    def __init__(self, dsn: str, embedding_dimensions: int = 384):
        self.dsn = dsn
        self.embedding_dimensions = embedding_dimensions
        self._schema_ready = False

    def replace_document(
        self,
        document_id: str,
        filename: str,
        owner_id: str | None,
        department_id: str | None,
        chunks: List[Dict[str, Any]],
        embeddings,
        profile: Dict[str, Any],
    ) -> None:
        self._ensure_schema()
        import psycopg

        document_id = str(document_id)
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM rag_document_chunks WHERE document_id = %s", (document_id,))
                cursor.execute(
                    """
                    INSERT INTO rag_document_profiles
                        (document_id, filename, owner_id, department_id, profile, updated_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (document_id) DO UPDATE SET
                        filename = EXCLUDED.filename,
                        owner_id = EXCLUDED.owner_id,
                        department_id = EXCLUDED.department_id,
                        profile = EXCLUDED.profile,
                        updated_at = NOW()
                    """,
                    (document_id, filename, self._to_int(owner_id), self._to_int(department_id), json.dumps(profile)),
                )
                rows = [
                    (
                        document_id,
                        chunk["chunkIndex"],
                        chunk.get("pageNumber"),
                        chunk["text"],
                        self._vector_literal(embedding),
                    )
                    for chunk, embedding in zip(chunks, embeddings)
                ]
                cursor.executemany(
                    """
                    INSERT INTO rag_document_chunks
                        (document_id, chunk_index, page_number, content, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    """,
                    rows,
                )
            connection.commit()

    def get_profile(self, document_id: str) -> Dict[str, Any] | None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT profile FROM rag_document_profiles WHERE document_id = %s",
                    (str(document_id),),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])

    def delete_document(self, document_id: str) -> None:
        """Belge silindiğinde ilişkili tüm embedding ve profil kaydını kaldırır."""
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM rag_document_chunks WHERE document_id = %s",
                    (str(document_id),),
                )
                cursor.execute(
                    "DELETE FROM rag_document_profiles WHERE document_id = %s",
                    (str(document_id),),
                )
            connection.commit()

    def search(self, document_id: str, embedding, top_k: int) -> List[Dict[str, Any]]:
        self._ensure_schema()
        import psycopg

        vector = self._vector_literal(embedding)
        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT chunk_index, page_number, content,
                           1 - (embedding <=> %s::vector) AS score
                    FROM rag_document_chunks
                    WHERE document_id = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (vector, str(document_id), vector, max(top_k, 1)),
                )
                rows = cursor.fetchall()
        return [
            {
                "chunkIndex": row[0],
                "pageNumber": row[1],
                "text": row[2],
                "score": float(row[3]),
            }
            for row in rows
        ]

    def initial_chunks(self, document_id: str, limit: int) -> List[Dict[str, Any]]:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT chunk_index, page_number, content
                    FROM rag_document_chunks
                    WHERE document_id = %s
                    ORDER BY chunk_index
                    LIMIT %s
                    """,
                    (str(document_id), max(limit, 1)),
                )
                rows = cursor.fetchall()
        return [
            {"chunkIndex": row[0], "pageNumber": row[1], "text": row[2], "score": 1.0}
            for row in rows
        ]

    def all_chunks(self, document_id: str) -> List[Dict[str, Any]]:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT chunk_index, page_number, content
                    FROM rag_document_chunks
                    WHERE document_id = %s
                    ORDER BY chunk_index
                    """,
                    (str(document_id),),
                )
                rows = cursor.fetchall()
        return [
            {"chunkIndex": row[0], "pageNumber": row[1], "text": row[2], "score": 1.0}
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        import psycopg

        with psycopg.connect(self.dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS rag_document_profiles (
                        document_id VARCHAR(128) PRIMARY KEY,
                        filename TEXT NOT NULL,
                        owner_id BIGINT,
                        department_id BIGINT,
                        profile JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS rag_document_chunks (
                        id BIGSERIAL PRIMARY KEY,
                        document_id VARCHAR(128) NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        page_number INTEGER,
                        content TEXT NOT NULL,
                        embedding VECTOR({self.embedding_dimensions}) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE (document_id, chunk_index)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS rag_document_chunks_document_idx
                    ON rag_document_chunks (document_id, chunk_index)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS rag_document_chunks_embedding_idx
                    ON rag_document_chunks USING hnsw (embedding vector_cosine_ops)
                    """
                )
        self._schema_ready = True

    def _vector_literal(self, embedding) -> str:
        values = list(embedding)
        if len(values) != self.embedding_dimensions:
            raise ValueError(
                f"Embedding boyutu {len(values)}; pgvector tablosu {self.embedding_dimensions} boyut bekliyor."
            )
        return "[" + ",".join(str(float(value)) for value in values) + "]"

    def _to_int(self, value: str | None) -> int | None:
        if value in (None, ""):
            return None
        return int(value)
