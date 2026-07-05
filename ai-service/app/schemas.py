from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InMemoryUpload:
    filename: str
    content: bytes

    def read(self) -> bytes:
        return self.content
