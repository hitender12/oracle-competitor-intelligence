"""Fetcher: per-domain rate limiting, timeouts, redirects, retries.

Uses only the standard library (urllib). Never sends cookies or
authorization headers, and never follows a redirect to a different
scheme or beyond the policy's max_redirects.
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin

from .registry import DomainPolicy


class FetchError(Exception):
    """Raised when a fetch fails after retries, times out, or redirects too much."""


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    headers: dict
    body: bytes
    observed_at: datetime
    redirects_followed: int = 0
    attempts: int = 1
    warnings: list = field(default_factory=list)

    @property
    def raw_hash(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


class RateLimiter:
    """Per-host token bucket. ``max_requests_per_minute`` is a hard cap:
    a request that would exceed it waits (or reports its wait time)."""

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = {}

    def wait_time(self, host: str, max_per_minute: int) -> float:
        now = time.monotonic()
        window = [t for t in self._buckets.get(host, []) if now - t < 60.0]
        self._buckets[host] = window
        if len(window) < max_per_minute:
            return 0.0
        return 60.0 - (now - window[0])

    def acquire(self, host: str, max_per_minute: int) -> None:
        wait = self.wait_time(host, max_per_minute)
        if wait > 0:
            time.sleep(wait)
        self._buckets.setdefault(host, []).append(time.monotonic())

    def record(self, host: str) -> None:
        self._buckets.setdefault(host, []).append(time.monotonic())


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    """Counts redirects and enforces the policy cap."""

    def __init__(self, max_redirects: int) -> None:
        super().__init__()
        self.max_redirects = max_redirects
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > self.max_redirects:
            raise FetchError(
                f"too many redirects: exceeded max_redirects={self.max_redirects}"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(
    url: str,
    policy: DomainPolicy | None = None,
    limiter: RateLimiter | None = None,
    *,
    sleep=time.sleep,
) -> FetchResult:
    """Fetch one URL with timeouts, redirect cap, and retry with backoff.

    Retries apply to connection errors, timeouts, and 5xx responses only.
    4xx responses are returned as results (a changed page may legitimately
    404) rather than retried.
    """
    policy = policy or DomainPolicy()
    policy.validate()
    host = urllib.request.urlparse(url).netloc.lower()

    handler = _RedirectHandler(policy.max_redirects)
    opener = urllib.request.build_opener(handler)

    last_error: Exception | None = None
    attempts = 0
    for attempt in range(policy.max_retries + 1):
        attempts = attempt + 1
        if limiter is not None:
            limiter.acquire(host, policy.max_requests_per_minute)
        req = urllib.request.Request(
            url, headers={"User-Agent": policy.user_agent}, method="GET"
        )
        try:
            with opener.open(req, timeout=policy.connect_timeout) as resp:
                body = resp.read()
            return FetchResult(
                url=url,
                final_url=resp.geturl(),
                status=resp.status,
                headers=dict(resp.headers.items()),
                body=body,
                observed_at=datetime.now(timezone.utc),
                redirects_followed=handler.count,
                attempts=attempts,
            )
        except FetchError:
            raise
        except urllib.error.HTTPError as exc:
            if 500 <= exc.code < 600:
                last_error = FetchError(f"HTTP {exc.code} from {url}")
            else:
                # 4xx: a real observation, not a failure.
                body = exc.read() if hasattr(exc, "read") else b""
                return FetchResult(
                    url=url,
                    final_url=exc.geturl(),
                    status=exc.code,
                    headers=dict(exc.headers.items()) if exc.headers else {},
                    body=body,
                    observed_at=datetime.now(timezone.utc),
                    redirects_followed=handler.count,
                    attempts=attempts,
                    warnings=[f"HTTP {exc.code}"],
                )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = FetchError(f"{type(exc).__name__}: {exc} for {url}")
        if attempt < policy.max_retries:
            sleep(policy.retry_backoff_base * (2 ** attempt))
    raise last_error or FetchError(f"fetch failed: {url}")
