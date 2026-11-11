"""Benchmark: fetch throughput, latency, and error rate against the
local fixture server under a fixed per-host policy.

Run:  python benchmark.py [--urls 50] [--concurrency 8] [--rpm 30]

Published baseline (this repo, local fixtures, 2026-11-11):
see evaluation/BENCHMARK.md after running. Hardware, URL count,
concurrency, per-host limits, and error rate are always reported
together — a bare requests/sec number is not a benchmark.
"""

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from fixtures.fixture_server import start_fixture_server
from oracle import DomainPolicy, RateLimiter, fetch


def run(urls: list[str], concurrency: int, policy: DomainPolicy) -> dict:
    limiter = RateLimiter()
    latencies: list[float] = []
    errors = 0
    started = time.monotonic()

    def one(url: str):
        nonlocal errors
        t0 = time.monotonic()
        try:
            fetch(url, policy, limiter)
            latencies.append(time.monotonic() - t0)
        except Exception:
            errors += 1
            latencies.append(time.monotonic() - t0)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(one, urls))
    elapsed = time.monotonic() - started
    return {
        "urls": len(urls),
        "concurrency": concurrency,
        "max_requests_per_minute_per_host": policy.max_requests_per_minute,
        "elapsed_seconds": round(elapsed, 3),
        "requests_per_second": round(len(urls) / elapsed, 2) if elapsed else 0,
        "mean_latency_ms": round(statistics.mean(latencies) * 1000, 2) if latencies else 0,
        "p95_latency_ms": round(sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)] * 1000, 2) if latencies else 0,
        "errors": errors,
        "error_rate": round(errors / len(urls), 4) if urls else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=8)
    # Default 600/min: high enough that the limiter does not dominate, so
    # the benchmark measures fetcher throughput. Use a low --rpm to
    # measure the limiter itself (see evaluation/BENCHMARK.md).
    parser.add_argument("--rpm", type=int, default=600)
    args = parser.parse_args()

    server, base = start_fixture_server()
    policy = DomainPolicy(max_requests_per_minute=args.rpm)
    pages = [f"{base}/acme/pricing", f"{base}/beta/products"]
    urls = [pages[i % len(pages)] for i in range(args.urls)]
    result = run(urls, args.concurrency, policy)
    result["note"] = (
        "Local fixture server on loopback; figures measure the reference "
        "fetcher + rate limiter, not internet performance."
    )
    print(json.dumps(result, indent=2))
    server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
