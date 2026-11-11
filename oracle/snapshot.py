"""Snapshot store: normalized text, metadata, raw + normalized hashes.

Raw and normalized hashes are saved separately so a content change can
be distinguished from volatile noise. A snapshot whose normalized hash
matches the previous one is a duplicate: stored for the timeline, but it
never produces an alert.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .normalizer import extract_fields, normalize_text


@dataclass
class Snapshot:
    url: str
    observed_at: str  # ISO 8601 UTC
    status: int
    raw_hash: str
    normalized_hash: str
    normalized_text: str
    fields: dict
    is_duplicate: bool = False
    raw_html: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        return cls(**data)


def build_snapshot(url: str, status: int, body: bytes, observed_at: datetime,
                   hints: dict | None = None, keep_raw: bool = False) -> Snapshot:
    try:
        html = body.decode("utf-8", errors="replace")
    except Exception:
        html = ""
    normalized = normalize_text(html)
    fields = extract_fields(html, hints)
    return Snapshot(
        url=url,
        observed_at=observed_at.astimezone(timezone.utc).isoformat(),
        status=status,
        raw_hash=hashlib.sha256(body).hexdigest(),
        normalized_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        normalized_text=normalized,
        fields=fields,
        raw_html=html if keep_raw else "",
    )


class SnapshotStore:
    """Per-URL ordered snapshot history, JSON-persistable."""

    def __init__(self) -> None:
        self._history: dict[str, list[Snapshot]] = {}

    def add(self, snapshot: Snapshot) -> Snapshot:
        history = self._history.setdefault(snapshot.url, [])
        snapshot.is_duplicate = bool(
            history and history[-1].normalized_hash == snapshot.normalized_hash
        )
        history.append(snapshot)
        return snapshot

    def latest(self, url: str) -> Snapshot | None:
        history = self._history.get(url, [])
        return history[-1] if history else None

    def previous(self, url: str) -> Snapshot | None:
        history = self._history.get(url, [])
        return history[-2] if len(history) >= 2 else None

    def history(self, url: str) -> list[Snapshot]:
        return list(self._history.get(url, []))

    def urls(self) -> list[str]:
        return sorted(self._history)

    def to_json(self) -> str:
        return json.dumps(
            {u: [s.to_dict() for s in snaps] for u, snaps in self._history.items()},
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "SnapshotStore":
        store = cls()
        for url, snaps in json.loads(text).items():
            store._history[url] = [Snapshot.from_dict(s) for s in snaps]
        return store
