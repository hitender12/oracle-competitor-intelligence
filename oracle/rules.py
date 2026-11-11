"""Alert rules, ignore/suppression list, and alert sinks.

An alert carries old value, new value, observation timestamp, and an
evidence link (source URL + observed time). Low-confidence changes are
emitted as "possible change" alerts for human review, never asserted
as facts. The ignore list suppresses recurring noise.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .diff import Change


@dataclass
class Alert:
    rule: str
    url: str
    old: object
    new: object
    observed_at: str
    evidence_url: str
    confidence: str  # "high" or "low"
    status: str = "new"  # new | possible | ignored | reviewed
    detail: str = ""  # e.g. unified diff for text changes

    def evidence_link(self) -> str:
        return f"{self.evidence_url} (observed {self.observed_at})"

    def to_dict(self) -> dict:
        return asdict(self)


class IgnoreList:
    """Suppression rules: (field regex, value regex). A change is
    suppressed when both match. Used for recurring noise."""

    def __init__(self) -> None:
        self._rules: list[tuple[re.Pattern, re.Pattern]] = []

    def add(self, field_pattern: str, value_pattern: str = ".*") -> None:
        self._rules.append(
            (re.compile(field_pattern, re.I), re.compile(value_pattern, re.I))
        )

    def suppressed(self, change: Change) -> bool:
        haystack = f"{change.kind} {change.field} {change.old} {change.new}"
        for field_pat, value_pat in self._rules:
            if field_pat.search(change.field) and value_pat.search(haystack):
                return True
        return False

    def __len__(self) -> int:
        return len(self._rules)


class RuleEngine:
    """Maps deterministic changes onto named alert rules."""

    RULES = {
        "price": "pricing_changed",
        "headline": "headline_changed",
        "item_added": "new_item",
        "item_removed": "removed_item",
        "title": "title_changed",
        "meta_description": "meta_description_changed",
        "text": "text_changed",
    }

    def __init__(self, ignore: IgnoreList | None = None) -> None:
        self.ignore = ignore or IgnoreList()

    def evaluate(self, changes: list[Change]) -> list[Alert]:
        alerts: list[Alert] = []
        for change in changes:
            rule = self.RULES.get(change.kind, "change_detected")
            if self.ignore.suppressed(change):
                continue
            alerts.append(
                Alert(
                    rule=rule,
                    url=change.evidence_url,
                    old=change.old,
                    new=change.new,
                    observed_at=change.observed_at,
                    evidence_url=change.evidence_url,
                    confidence=change.confidence,
                    status="possible" if change.is_possible else "new",
                    detail=change.detail,
                )
            )
        return alerts


class AlertSink:
    """Records alerts. The webhook/email sinks record payloads to a local
    outbox (JSON) instead of sending live messages; wiring a real webhook
    URL or SMTP sender is a one-line change in production."""

    def __init__(self) -> None:
        self.alerts: list[Alert] = []
        self.webhook_outbox: list[dict] = []
        self.email_outbox: list[dict] = []

    def emit(self, alert: Alert, webhook_url: str | None = None,
             email_to: str | None = None) -> Alert:
        self.alerts.append(alert)
        if webhook_url:
            self.webhook_outbox.append(
                {"webhook_url": webhook_url, **alert.to_dict()}
            )
        if email_to:
            self.email_outbox.append(
                {
                    "to": email_to,
                    "subject": f"[ORACLE] {alert.rule} on {alert.url}",
                    **alert.to_dict(),
                }
            )
        return alert

    def by_url(self, url: str) -> list[Alert]:
        return [a for a in self.alerts if a.url == url]
