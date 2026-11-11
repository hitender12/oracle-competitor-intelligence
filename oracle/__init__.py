"""ORACLE — Competitor Change Intelligence (reference implementation).

ORACLE records authorized website snapshots and detects meaningful
competitor changes with reproducible before/after evidence.
"""

from .diff import Change, diff_snapshots
from .fetcher import FetchError, FetchResult, RateLimiter, fetch
from .normalizer import extract_fields, normalize_text
from .registry import AUTHORIZATION_POLICY, DomainPolicy, Registry, WatchedURL
from .rules import Alert, AlertSink, IgnoreList, RuleEngine
from .scheduler import CycleReport, Scheduler
from .snapshot import Snapshot, SnapshotStore, build_snapshot
from .timeline import console_timeline, render_html

__version__ = "0.1.0"

__all__ = [
    "AUTHORIZATION_POLICY", "Alert", "AlertSink", "Change", "CycleReport",
    "DomainPolicy", "FetchError", "FetchResult", "IgnoreList", "RateLimiter",
    "Registry", "RuleEngine", "Scheduler", "Snapshot", "SnapshotStore",
    "WatchedURL", "build_snapshot", "console_timeline", "diff_snapshots",
    "extract_fields", "fetch", "normalize_text", "render_html",
]
