"""Scheduler: one monitoring cycle = fetch -> snapshot -> diff -> alert.

A duplicate snapshot (same normalized hash as the previous one) is
stored but produces no diff and no alert. A fetch failure is recorded
in the cycle report and does not delete history.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .diff import diff_snapshots
from .fetcher import FetchError, RateLimiter, fetch
from .registry import Registry
from .rules import AlertSink, RuleEngine
from .snapshot import SnapshotStore, build_snapshot


@dataclass
class CycleReport:
    fetched: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    alerts: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"fetched={len(self.fetched)} duplicates={len(self.duplicates)} "
            f"alerts={len(self.alerts)} errors={len(self.errors)}"
        )


class Scheduler:
    def __init__(self, registry: Registry, store: SnapshotStore,
                 rules: RuleEngine | None = None, sink: AlertSink | None = None):
        self.registry = registry
        self.store = store
        self.rules = rules or RuleEngine()
        self.sink = sink or AlertSink()
        self.limiter = RateLimiter()

    def run_cycle(self, webhook_url: str | None = None,
                  email_to: str | None = None) -> CycleReport:
        report = CycleReport()
        for entry in self.registry.list(enabled_only=True):
            try:
                result = fetch(entry.url, entry.policy, self.limiter)
            except FetchError as exc:
                report.errors[entry.url] = str(exc)
                continue
            previous = self.store.latest(entry.url)
            snapshot = build_snapshot(
                entry.url, result.status, result.body, result.observed_at,
                hints=entry.field_hints,
            )
            self.store.add(snapshot)
            report.fetched.append(entry.url)
            if snapshot.is_duplicate:
                report.duplicates.append(entry.url)
                continue
            if previous is not None:
                changes = diff_snapshots(previous, snapshot)
                for alert in self.rules.evaluate(changes):
                    self.sink.emit(alert, webhook_url=webhook_url, email_to=email_to)
                    report.alerts.append(alert)
        return report
