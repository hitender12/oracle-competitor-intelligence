"""ORACLE demo: monitor two local fixture pages that intentionally
change pricing/headlines between snapshots, proving the diff + alert
path end to end. No real website is fetched.

Run:  python demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from fixtures.fixture_server import set_version, start_fixture_server
from oracle import (
    DomainPolicy, Registry, RuleEngine, Scheduler, SnapshotStore,
    WatchedURL, console_timeline, render_html,
)


def main() -> int:
    server, base = start_fixture_server()
    print(f"fixture server: {base}")
    registry = Registry()
    policy = DomainPolicy(max_requests_per_minute=30, max_redirects=5)
    for name, path in (("Acme Pricing", "/acme/pricing"), ("Beta Products", "/beta/products")):
        registry.add(WatchedURL(
            url=f"{base}{path}", name=name, authorized=True,
            authorization_note="local demo fixture, owned for testing",
            policy=policy,
        ))
    store = SnapshotStore()
    scheduler = Scheduler(registry, store, RuleEngine())

    print("\n--- cycle 1 (baseline snapshots) ---")
    report = scheduler.run_cycle()
    print(report.summary())

    set_version("acme", 2)
    set_version("beta", 2)
    print("\n--- cycle 2 (fixtures changed: prices, headlines, items) ---")
    report = scheduler.run_cycle()
    print(report.summary())
    for alert in report.alerts:
        print(f"  ALERT [{alert.status}] {alert.rule} on {alert.url}")
        print(f"    old: {alert.old!r}")
        print(f"    new: {alert.new!r}")
        print(f"    evidence: {alert.evidence_link()}")

    print("\n--- cycle 3 (no further changes: duplicates, no alerts) ---")
    report = scheduler.run_cycle()
    print(report.summary())

    html_path = render_html(store, scheduler.sink, "demo_timeline.html")
    print(f"\nHTML timeline written to {html_path}")
    print("\n" + console_timeline(store, scheduler.sink))
    server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
