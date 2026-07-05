import hashlib
import json
import os
from typing import Any


class RagCache:
    """Small Redis wrapper that keeps cache failures out of the RAG path."""

    def __init__(self) -> None:
        self.redis_url = os.getenv("REDIS_URL", "").strip()
        self.prefix = os.getenv("RAG_CACHE_PREFIX", "rag").strip() or "rag"
        self.answer_ttl_seconds = self._read_ttl("RAG_ANSWER_CACHE_TTL_SECONDS", 3600)
        self.embedding_ttl_seconds = self._read_ttl("RAG_EMBEDDING_CACHE_TTL_SECONDS", 604800)
        self.profile_ttl_seconds = self._read_ttl("RAG_PROFILE_CACHE_TTL_SECONDS", 21600)
        self._client = None
        self._error_logged = False

        if os.getenv("RAG_CACHE_ENABLED", "true").lower() == "false" or not self.redis_url:
            return

        try:
            import redis

            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        except Exception as exc:
            self._log_error_once(f"Redis cache başlatılamadı: {exc}")
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(self.redis_url),
            "enabled": self.enabled,
            "prefix": self.prefix,
        }

    def get_json(self, key: str) -> Any | None:
        if self._client is None:
            return None
        try:
            raw_value = self._client.get(self._key(key))
            if raw_value is None:
                return None
            return json.loads(raw_value)
        except Exception as exc:
            self._log_error_once(f"Redis cache okuma hatası: {exc}")
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        if self._client is None or ttl_seconds <= 0:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            self._client.setex(self._key(key), ttl_seconds, payload)
        except Exception as exc:
            self._log_error_once(f"Redis cache yazma hatası: {exc}")

    def delete(self, key: str) -> None:
        if self._client is None:
            return
        try:
            self._client.delete(self._key(key))
        except Exception as exc:
            self._log_error_once(f"Redis cache silme hatası: {exc}")

    def delete_pattern(self, pattern: str) -> None:
        if self._client is None:
            return
        try:
            namespaced_pattern = self._key(pattern)
            batch = []
            for key in self._client.scan_iter(match=namespaced_pattern, count=100):
                batch.append(key)
                if len(batch) >= 100:
                    self._client.delete(*batch)
                    batch = []
            if batch:
                self._client.delete(*batch)
        except Exception as exc:
            self._log_error_once(f"Redis cache pattern silme hatası: {exc}")

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def _read_ttl(self, name: str, default_value: int) -> int:
        try:
            return int(os.getenv(name, str(default_value)))
        except ValueError:
            return default_value

    def _log_error_once(self, message: str) -> None:
        if self._error_logged:
            return
        print(message)
        self._error_logged = True


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
