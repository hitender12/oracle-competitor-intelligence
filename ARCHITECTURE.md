# ORACLE — Architecture

## Pipeline

```
Registry (authorized URLs + per-domain policy)
  -> Scheduler (one cycle per schedule tick)
  -> Fetcher (rate limiter, timeouts, redirects, retries)
  -> Normalizer + Parser (volatile stripping, structured fields)
  -> Snapshot Store (raw + normalized hashes, timestamps)
  -> Deterministic Diff Engine (structured fields first, text second)
  -> Rule Matcher (pricing/headline/item/title/meta rules)
  -> Alert Sink (webhook/email outbox) + Timeline (HTML/console)
```

## Modules (`oracle/`)

| Module | Responsibility |
|---|---|
| `registry.py` | URL registry, `DomainPolicy`, authorization gate |
| `fetcher.py` | `RateLimiter` (per-host token bucket), `fetch()` with redirect cap, timeouts, retry/backoff |
| `normalizer.py` | Tolerant HTML tree builder, volatile normalization, `extract_fields()` |
| `snapshot.py` | `Snapshot` dataclass, `SnapshotStore` with duplicate detection |
| `diff.py` | `diff_snapshots()`, `Change` with confidence (`high` / `low` = "possible change") |
| `rules.py` | `RuleEngine`, `IgnoreList`, `Alert`, `AlertSink` |
| `scheduler.py` | `Scheduler.run_cycle()` — fetch, snapshot, diff, alert |
| `timeline.py` | Console timeline + self-contained HTML timeline |

## Key design decisions

- **Structured fields first, text diff second.** A price change is a
  fact; a text diff is evidence. Text-only changes with high
  similarity are low confidence ("possible change").
- **Raw and normalized hashes are separate.** A raw-hash change with
  an unchanged normalized hash is volatile noise, not a change.
- **Duplicates never alert.** A snapshot whose normalized hash equals
  the previous one is stored for the timeline and skipped by the
  differ.
- **Observation time, not change time.** Alerts carry `observed_at`.
  ORACLE never claims to know when the site itself changed.
- **Politeness over throughput.** Per-host rate limits are hard caps;
  the benchmark measures the limiter working, not a firehose.
- **Failures are recorded, not fatal.** A fetch error is logged in
  the cycle report; history is never deleted by a failed fetch.

## Data model

- `Snapshot`: url, observed_at (ISO UTC), status, raw_hash,
  normalized_hash, normalized_text, fields dict, is_duplicate.
- `Change`: kind, field, old, new, confidence, evidence_url,
  observed_at, detail (unified diff for text changes).
- `Alert`: rule, url, old, new, observed_at, evidence_url,
  confidence, status (`new` | `possible` | `ignored` | `reviewed`).

## Production path (not implemented here)

Per the spec: Rust + Tokio + reqwest + scraper workers, Axum API,
PostgreSQL via SQLx, Redis/durable scheduler, object storage for
snapshots, a separate Playwright worker for JS-heavy pages, and a
Next.js + TypeScript dashboard. The Python package mirrors the spec's
worker contract (`max_requests_per_minute_per_host`, `max_redirects`,
`render_javascript`) so the port is mechanical: same policy fields,
same snapshot/diff semantics, same alert shape.
