# ORACLE — Competitor Change Intelligence

> ORACLE records authorized website snapshots and detects meaningful competitor changes with reproducible before/after evidence.

ORACLE monitors websites you are **authorized** to monitor, captures snapshots on a schedule, extracts structured facts (pricing, product names, headlines, offers), compares versions deterministically, and sends alerts when a meaningful change occurs — with the exact before/after values, the observation timestamp, the source URL, and a diff as evidence.

It never claims a site changed at an exact time: it reports when the difference was **observed**.

## Who it is for

Agencies, product marketers, founders, and small research teams tracking a defined competitor set.

## Quickstart

```bash
python demo.py          # end-to-end demo against local fixtures
python benchmark.py     # throughput / latency / error rate vs local fixtures
python -m unittest discover -s tests   # 22 tests
```

The demo starts a local fixture server, registers two fixture pages
(a pricing page and a product catalogue), snapshots them, flips the
fixtures to a new version (prices, headlines, items change), snapshots
again, and prints the alerts — then proves a third cycle with no
changes produces duplicates and **no** alerts. It also writes
`demo_timeline.html`, a self-contained change timeline.

## Usage (library)

```python
from oracle import (
    Registry, WatchedURL, DomainPolicy,
    SnapshotStore, Scheduler, RuleEngine,
)

registry = Registry()
registry.add(WatchedURL(
    url="https://example.com/pricing",
    authorized=True,
    authorization_note="own site",
    policy=DomainPolicy(max_requests_per_minute=2, max_redirects=5),
))
scheduler = Scheduler(registry, SnapshotStore(), RuleEngine())
report = scheduler.run_cycle()   # fetch -> snapshot -> diff -> alert
for alert in report.alerts:
    print(alert.rule, alert.old, "->", alert.new, alert.evidence_link())
```

## What is implemented (reference implementation, Python stdlib only)

- **Registry** — authorized public URLs with per-domain policy
  (max requests/minute/host, max redirects, render flag, timeouts,
  retries). Registration requires `authorized=True` plus a note stating
  the basis for monitoring; anything else is refused.
- **Fetcher** — per-domain token-bucket rate limiting, connect/read
  timeouts, redirect cap (default 5), retries with exponential backoff
  on 5xx/connection errors. 4xx is recorded as an observation, not an
  error. No cookies or authorization headers are ever sent or logged.
- **Snapshots** — normalized text, title, meta description, price,
  headlines, item lists; raw + normalized SHA-256 hashes saved
  separately; observation timestamp. Duplicate snapshots (same
  normalized hash) are stored but never alert.
- **Normalization** — strips script/style, comments, whitespace, and
  volatile tokens (ISO timestamps, UUIDs, long hex tokens, epoch
  seconds) without deleting meaningful differences.
- **Deterministic diff** — structured fields first, `difflib` text
  diff second. Low-confidence changes are labelled
  **"possible change"** for human review, never asserted as facts.
- **Alert rules** — pricing changed, headline changed, new item,
  removed item, title/meta changed. Each alert carries old value, new
  value, observation timestamp, and an evidence link. An ignore list
  suppresses recurring noise.
- **Timeline** — console timeline and a self-contained HTML timeline
  with per-URL change history.

## Authorization & policy

See [docs/POLICY.md](docs/POLICY.md). In short: monitor only sites
you own or have explicit permission to monitor; respect robots.txt,
site terms, and rate limits; never bypass logins, paywalls, or bot
checks. ORACLE ships with a documented takedown/contact process
placeholder in the policy doc.

## Honest status

This is a **Python reference implementation** of the spec's MVP core.
It is real, tested code — not a mock — but it is not the production
system:

- No Rust/Tokio worker, no PostgreSQL, no Redis queue, no Axum API,
  no Next.js dashboard, no Playwright renderer. The production path
  is Rust + Tokio + reqwest + scraper with PostgreSQL (see
  [ARCHITECTURE.md](ARCHITECTURE.md)).
- No real network fetching of third-party sites in the demo/tests:
  everything runs against local fixtures on loopback.
- No AI explanations: alerts are deterministic; semantic
  classification is explicitly deferred until deterministic diff
  quality is measured (per the spec).
- The webhook/email sinks record payloads to a local outbox; wiring a
  real webhook URL or SMTP sender is a one-line change.
- The fetcher is synchronous (urllib) with a thread pool in the
  benchmark; per-host politeness caps throughput by design.

## Evaluation

- 22 tests: redirects (chain + loop cap), malformed HTML, timeouts,
  retries, duplicate snapshots not double-alerting, volatile-content
  normalization, price-change alerts with correct before/after,
  ignore-list suppression, and a full end-to-end scheduler cycle.
- Benchmark: see [evaluation/BENCHMARK.md](evaluation/BENCHMARK.md)
  (hardware, URL count, concurrency, per-host limits, error rate).
- Demo fixtures intentionally change pricing/headlines between
  snapshots; the demo proves the diff + alert path end to end.

## License

MIT — see [LICENSE](LICENSE).
