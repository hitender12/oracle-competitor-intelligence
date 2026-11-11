# ORACLE — Benchmark

Measured 2026-11-11 against the local fixture server on loopback
(`python benchmark.py`). The reference fetcher is synchronous
(urllib) with a thread pool; the production path is Rust + Tokio.

## Hardware

Shared Linux VM, 1.5 vCPU, 6 GiB RAM, Python 3.12. Figures measure
the reference fetcher + rate limiter, not internet performance.

## Results

| Run | URLs | Concurrency | Max req/min/host | Elapsed | Req/s | Mean latency | p95 latency | Errors | Error rate |
|---|---|---|---|---|---|---|---|---|---|
| Throughput | 50 | 8 | 600 | 2.5 s | 15.34 | 503 ms | 792 ms | 0 | 0.0000 |
| Limiter check | 50 | 8 | 30 | 61.5 s | 0.81 | 9769 ms | 58964 ms | 0 | 0.0000 |

## Reading the numbers

- The **throughput run** (600 req/min cap) measures the fetcher:
  ~15 req/s with 8 workers against a loopback fixture server, zero
  errors. Mean latency includes thread-pool scheduling on a small VM.
- The **limiter run** (30 req/min cap, the spec's polite default)
  shows the rate limiter working as designed: 50 requests against
  one host take ~60 s because the per-host cap is a hard limit.
  Latency there is dominated by waiting for tokens, not by fetching.
  This is intentional — ORACLE is not a firehose.
- No run produced an error against the fixture server.

## How to reproduce

```bash
python benchmark.py --urls 50 --concurrency 8 --rpm 600
python benchmark.py --urls 50 --concurrency 8 --rpm 30
```
