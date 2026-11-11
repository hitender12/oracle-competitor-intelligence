"""Deterministic diff engine.

Structured fields first, text diff second. Every change carries
before/after values, observation timestamp, source URL, and an evidence
link (the URL + the observed snapshot time). Low-confidence changes are
labelled "possible change" for human review instead of being asserted.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from .snapshot import Snapshot

HIGH = "high"
LOW = "low"


@dataclass
class Change:
    kind: str  # e.g. "price", "headline", "title", "meta_description", "item_added", "item_removed", "text"
    field: str
    old: object
    new: object
    confidence: str  # "high" or "low"
    evidence_url: str
    observed_at: str
    detail: str = ""  # e.g. the unified text diff for kind == "text"

    @property
    def is_possible(self) -> bool:
        return self.confidence == LOW

    def summary(self) -> str:
        label = "possible change" if self.is_possible else "change"
        return f"[{label}] {self.kind} {self.field}: {self.old!r} -> {self.new!r}"


def _text_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def diff_snapshots(old: Snapshot, new: Snapshot) -> list[Change]:
    """Deterministic diff between two consecutive snapshots of one URL."""
    changes: list[Change] = []
    of, nf = old.fields, new.fields

    def add(kind, field, old_v, new_v, confidence=HIGH):
        changes.append(
            Change(kind, field, old_v, new_v, confidence, new.url, new.observed_at)
        )

    if of.get("title") != nf.get("title"):
        add("title", "title", of.get("title"), nf.get("title"))
    if of.get("meta_description") != nf.get("meta_description"):
        add("meta_description", "meta_description",
            of.get("meta_description"), nf.get("meta_description"))
    if of.get("price") != nf.get("price"):
        add("price", "price", of.get("price"), nf.get("price"))

    old_heads = of.get("headlines", [])
    new_heads = nf.get("headlines", [])
    if old_heads != new_heads:
        add("headline", "headlines", old_heads, new_heads)

    old_items = of.get("items", [])
    new_items = nf.get("items", [])
    for item in new_items:
        if item not in old_items:
            add("item_added", "items", None, item)
    for item in old_items:
        if item not in new_items:
            add("item_removed", "items", item, None)

    # Text diff second, only if the normalized text actually changed.
    if old.normalized_text != new.normalized_text:
        similarity = _text_similarity(old.normalized_text, new.normalized_text)
        diff_lines = list(
            difflib.unified_diff(
                old.normalized_text.splitlines(),
                new.normalized_text.splitlines(),
                lineterm="",
            )
        )
        # A tiny text change with no structured-field change is low
        # confidence: flag it as a possible change for human review.
        structured = any(c.kind != "text" for c in changes)
        confidence = HIGH if (structured or similarity < 0.90) else LOW
        change = Change(
            "text", "normalized_text",
            old.normalized_text[:300], new.normalized_text[:300],
            confidence, new.url, new.observed_at,
            detail="\n".join(diff_lines[:40]),
        )
        changes.append(change)
    return changes
