"""URL registry and per-domain policy for ORACLE.

Authorization policy (read this before registering a URL):

ORACLE only monitors public URLs the user owns or has explicit permission
to monitor. A customer must have a legitimate reason and authority to
monitor a target. The fetcher respects robots.txt where applicable, site
terms, per-domain rate limits, and access controls. ORACLE never bypasses
logins, paywalls, bot checks, or other access restrictions, and never
logs cookies or authorization headers.

Registering a URL requires an explicit ``authorized=True`` flag plus a
short note stating the basis for monitoring (e.g. "own site",
"client site, written permission 2026-11-01"). Registration without
that flag is refused.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

AUTHORIZATION_POLICY = (
    "ORACLE monitors only public URLs you own or have explicit permission "
    "to monitor. Respect robots.txt, site terms, and rate limits. Never "
    "bypass logins, paywalls, or bot checks. Never log cookies or "
    "authorization headers."
)


@dataclass
class DomainPolicy:
    """Per-domain politeness policy (mirrors the spec's worker contract)."""

    max_requests_per_minute: int = 2
    max_redirects: int = 5
    render_javascript: bool = False
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    max_retries: int = 2
    retry_backoff_base: float = 0.5
    user_agent: str = "ORACLE/0.1 (competitor-change-intelligence; authorized monitoring only)"

    def validate(self) -> None:
        if self.max_requests_per_minute < 1:
            raise ValueError("max_requests_per_minute must be >= 1")
        if not 0 <= self.max_redirects <= 10:
            raise ValueError("max_redirects must be between 0 and 10")
        if self.connect_timeout <= 0 or self.read_timeout <= 0:
            raise ValueError("timeouts must be positive")


@dataclass
class WatchedURL:
    url: str
    name: str = ""
    authorized: bool = False
    authorization_note: str = ""
    policy: DomainPolicy = field(default_factory=DomainPolicy)
    enabled: bool = True
    # CSS-class hints for structured extraction, e.g. {"price": "price", "items": "product"}
    field_hints: dict = field(default_factory=dict)

    @property
    def host(self) -> str:
        return urlparse(self.url).netloc.lower()


class RegistryError(ValueError):
    pass


class Registry:
    """In-memory registry of authorized public URLs, JSON-serializable."""

    def __init__(self) -> None:
        self._urls: dict[str, WatchedURL] = {}

    def add(self, entry: WatchedURL) -> WatchedURL:
        parsed = urlparse(entry.url)
        if parsed.scheme not in ("http", "https"):
            raise RegistryError(f"only http(s) URLs may be monitored: {entry.url!r}")
        if not parsed.netloc:
            raise RegistryError(f"URL has no host: {entry.url!r}")
        if not entry.authorized:
            raise RegistryError(
                "refused: monitoring requires authorized=True plus an "
                "authorization_note stating the basis for monitoring. "
                + AUTHORIZATION_POLICY
            )
        if not entry.authorization_note.strip():
            raise RegistryError("refused: authorization_note is required")
        entry.policy.validate()
        self._urls[entry.url] = entry
        return entry

    def remove(self, url: str) -> None:
        self._urls.pop(url, None)

    def get(self, url: str) -> WatchedURL | None:
        return self._urls.get(url)

    def list(self, enabled_only: bool = False) -> list[WatchedURL]:
        urls = list(self._urls.values())
        if enabled_only:
            urls = [u for u in urls if u.enabled]
        return sorted(urls, key=lambda u: u.url)

    def hosts(self) -> set[str]:
        return {u.host for u in self._urls.values()}

    def to_json(self) -> str:
        return json.dumps([asdict(u) for u in self.list()], indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Registry":
        reg = cls()
        for item in json.loads(text):
            item["policy"] = DomainPolicy(**item.get("policy", {}))
            reg._urls[item["url"]] = WatchedURL(**item)
        return reg
