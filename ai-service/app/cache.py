import hashlib
import json
import os
import threading
from typing import Any


class RagCache:
    """Small Redis wrapper that keeps cache failures out of the RAG path."""

    def __init__(self) -> None:
        self.redis_url = os.getenv("REDIS_URL", "").strip()
        self.prefix = os.getenv("RAG_CACHE_PREFIX", "rag").strip() or "rag"
        self.answer_ttl_seconds = self._read_ttl("RAG_ANSWER_CACHE_TTL_SECONDS", 3600)
        self.embedding_ttl_seconds = self._read_ttl("RAG_EMBEDDING_CACHE_TTL_SECONDS", 604800)
        self.profile_ttl_seconds = self._read_ttl("RAG_PROFILE_CACHE_TTL_SECONDS", 21600)
        self.log_events = os.getenv("RAG_CACHE_LOG_EVENTS", "true").lower() == "true"
        self._client = None
        self._error_logged = False
        self._metrics_lock = threading.Lock()
        self._metrics = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "deletePatterns": 0,
            "errors": 0,
        }

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
            "ttlSeconds": {
                "answer": self.answer_ttl_seconds,
                "embedding": self.embedding_ttl_seconds,
                "profile": self.profile_ttl_seconds,
            },
            "metrics": self._metrics_snapshot(),
        }

    def get_json(self, key: str) -> Any | None:
        if self._client is None:
            return None
        try:
            namespaced_key = self._key(key)
            raw_value = self._client.get(namespaced_key)
            if raw_value is None:
                self._record("misses")
                self._log_cache_event("miss", namespaced_key)
                return None
            self._record("hits")
            self._log_cache_event("hit", namespaced_key)
            return json.loads(raw_value)
        except Exception as exc:
            self._record("errors")
            self._log_error_once(f"Redis cache okuma hatası: {exc}")
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        if self._client is None or ttl_seconds <= 0:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            self._client.setex(self._key(key), ttl_seconds, payload)
            self._record("sets")
        except Exception as exc:
            self._record("errors")
            self._log_error_once(f"Redis cache yazma hatası: {exc}")

    def delete(self, key: str) -> None:
        if self._client is None:
            return
        try:
            deleted_count = self._client.delete(self._key(key))
            self._record("deletes", int(deleted_count or 0))
        except Exception as exc:
            self._record("errors")
            self._log_error_once(f"Redis cache silme hatası: {exc}")

    def delete_pattern(self, pattern: str) -> None:
        if self._client is None:
            return
        try:
            namespaced_pattern = self._key(pattern)
            batch = []
            deleted_count = 0
            for key in self._client.scan_iter(match=namespaced_pattern, count=100):
                batch.append(key)
                if len(batch) >= 100:
                    deleted_count += int(self._client.delete(*batch) or 0)
                    batch = []
            if batch:
                deleted_count += int(self._client.delete(*batch) or 0)
            self._record("deletePatterns")
            self._record("deletes", deleted_count)
        except Exception as exc:
            self._record("errors")
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

    def _log_cache_event(self, event: str, key: str) -> None:
        if self.log_events:
            print(f"Redis cache {event}: key={key}")

    def _record(self, name: str, amount: int = 1) -> None:
        if amount <= 0:
            return
        with self._metrics_lock:
            self._metrics[name] = self._metrics.get(name, 0) + amount

    def _metrics_snapshot(self) -> dict[str, Any]:
        with self._metrics_lock:
            metrics = dict(self._metrics)
        hits = int(metrics.get("hits", 0))
        misses = int(metrics.get("misses", 0))
        total_reads = hits + misses
        hit_rate = 0 if total_reads == 0 else round(hits * 100.0 / total_reads, 1)
        metrics["reads"] = total_reads
        metrics["hitRate"] = hit_rate
        return metrics


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
