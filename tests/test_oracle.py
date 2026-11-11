"""ORACLE tests — all against the local fixture server (no internet)."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "fixtures"))

from fixtures.fixture_server import _flaky_hits, set_version, start_fixture_server
from oracle import (
    DomainPolicy, IgnoreList, Registry, RuleEngine, Scheduler, SnapshotStore,
    WatchedURL, build_snapshot, diff_snapshots, extract_fields, fetch,
    normalize_text,
)
from oracle.fetcher import FetchError
from oracle.scheduler import CycleReport

SERVER = None
BASE = ""


def setUpModule():
    global SERVER, BASE
    SERVER, BASE = start_fixture_server()
    set_version("acme", 1)
    set_version("beta", 1)


def tearDownModule():
    SERVER.shutdown()


def policy(**kw):
    kw.setdefault("max_requests_per_minute", 60)
    kw.setdefault("max_retries", 2)
    kw.setdefault("retry_backoff_base", 0.01)
    return DomainPolicy(**kw)


class TestFetcher(unittest.TestCase):
    def test_redirect_chain_followed(self):
        r = fetch(f"{BASE}/redirect", policy(max_redirects=5))
        self.assertEqual(r.status, 200)
        self.assertEqual(r.redirects_followed, 2)
        self.assertIn("Arrived", r.body.decode())

    def test_redirect_loop_exceeds_cap(self):
        with self.assertRaises(FetchError) as ctx:
            fetch(f"{BASE}/redirect-loop", policy(max_redirects=3, max_retries=0))
        self.assertIn("too many redirects", str(ctx.exception))

    def test_timeout(self):
        with self.assertRaises(FetchError):
            fetch(f"{BASE}/slow", policy(connect_timeout=0.3, max_retries=0))

    def test_retries_then_succeeds(self):
        _flaky_hits["count"] = 0
        r = fetch(f"{BASE}/flaky", policy())
        self.assertEqual(r.status, 200)
        self.assertEqual(r.attempts, 3)
        self.assertIn("Recovered", r.body.decode())

    def test_retries_exhausted_raises(self):
        _flaky_hits["count"] = 0
        with self.assertRaises(FetchError):
            fetch(f"{BASE}/flaky", policy(max_retries=0))
        # only the first (failing) attempt ran
        self.assertEqual(_flaky_hits["count"], 1)

    def test_404_is_observation_not_error(self):
        r = fetch(f"{BASE}/nope", policy())
        self.assertEqual(r.status, 404)

    def test_rate_limiter_waits(self):
        from oracle.fetcher import RateLimiter
        limiter = RateLimiter()
        self.assertEqual(limiter.wait_time("h", 2), 0.0)
        limiter.record("h")
        limiter.record("h")
        self.assertGreater(limiter.wait_time("h", 2), 0)


class TestRegistry(unittest.TestCase):
    def test_requires_authorization(self):
        reg = Registry()
        with self.assertRaises(ValueError):
            reg.add(WatchedURL(url=f"{BASE}/acme/pricing"))
        with self.assertRaises(ValueError):
            reg.add(WatchedURL(url=f"{BASE}/acme/pricing", authorized=True))
        entry = reg.add(WatchedURL(
            url=f"{BASE}/acme/pricing", authorized=True,
            authorization_note="own site"))
        self.assertEqual(entry.host, "127.0.0.1:" + BASE.rsplit(":", 1)[1])

    def test_rejects_non_http(self):
        reg = Registry()
        with self.assertRaises(ValueError):
            reg.add(WatchedURL(url="ftp://example.com/x", authorized=True,
                               authorization_note="n"))


class TestNormalizer(unittest.TestCase):
    def test_malformed_html_parses(self):
        fields = extract_fields("<html><head><title>Broken<title><body><h1>Unclosed")
        self.assertEqual(fields.get("title"), "Broken")

    def test_volatile_noise_normalized_away(self):
        a = '<div class="timestamp">2026-11-11T15:00:00Z</div><h1>Same</h1><p>$49</p>'
        b = '<div class="timestamp">2026-11-11T15:05:00Z</div><h1>Same</h1><p>$49</p>'
        self.assertEqual(normalize_text(a), normalize_text(b))

    def test_uuid_and_session_tokens_normalized_away(self):
        a = '<p>id 9f2c41aa-77d1-4e9a-b123-0123456789ab and 1700000000</p>'
        b = '<p>id 51bd90e2-88aa-4c77-a999-abcdef012345 and 1700000999</p>'
        self.assertEqual(normalize_text(a), normalize_text(b))

    def test_meaningful_difference_survives(self):
        a = normalize_text("<h1>Price $49</h1>")
        b = normalize_text("<h1>Price $59</h1>")
        self.assertNotEqual(a, b)

    def test_extract_fields(self):
        html = (Path(__file__).parent.parent / "fixtures" / "acme_v1.html").read_text()
        fields = extract_fields(html)
        self.assertEqual(fields["title"], "Acme Pricing")
        self.assertEqual(fields["price"], "$49/mo")
        self.assertEqual(fields["headlines"], ["The fastest widget ever"])
        self.assertIn("Acme Widget Pro", fields["items"])


class TestDiffAndRules(unittest.TestCase):
    def _snap(self, url, html, when="2026-11-11T15:00:00+00:00"):
        from datetime import datetime
        return build_snapshot(url, 200, html.encode(), datetime.fromisoformat(when))

    def test_price_change_alert_with_before_after(self):
        old = self._snap("http://x/p", "<h1>H</h1><span class='price'>$49/mo</span>")
        new = self._snap("http://x/p", "<h1>H</h1><span class='price'>$59/mo</span>",
                         "2026-11-11T15:05:00+00:00")
        changes = diff_snapshots(old, new)
        alerts = RuleEngine().evaluate(changes)
        price_alerts = [a for a in alerts if a.rule == "pricing_changed"]
        self.assertEqual(len(price_alerts), 1)
        self.assertEqual(price_alerts[0].old, "$49/mo")
        self.assertEqual(price_alerts[0].new, "$59/mo")
        self.assertEqual(price_alerts[0].observed_at, "2026-11-11T15:05:00+00:00")

    def test_headline_and_items(self):
        old = self._snap("http://x/p", "<h1>Old</h1><li class='product'>A</li>")
        new = self._snap("http://x/p", "<h1>New</h1><li class='product'>A</li>"
                                       "<li class='product'>B</li>")
        rules = [a.rule for a in RuleEngine().evaluate(diff_snapshots(old, new))]
        self.assertIn("headline_changed", rules)
        self.assertIn("new_item", rules)

    def test_removed_item(self):
        old = self._snap("http://x/p", "<li class='product'>A</li><li class='product'>B</li>")
        new = self._snap("http://x/p", "<li class='product'>A</li>")
        rules = [a.rule for a in RuleEngine().evaluate(diff_snapshots(old, new))]
        self.assertIn("removed_item", rules)

    def test_tiny_text_only_change_is_possible(self):
        old = self._snap("http://x/p", "<p>" + "word " * 100 + "alpha</p>")
        new = self._snap("http://x/p", "<p>" + "word " * 100 + "beta</p>")
        alerts = RuleEngine().evaluate(diff_snapshots(old, new))
        text_alerts = [a for a in alerts if a.rule == "text_changed"]
        self.assertEqual(len(text_alerts), 1)
        self.assertEqual(text_alerts[0].status, "possible")
        self.assertEqual(text_alerts[0].confidence, "low")

    def test_ignore_list_suppresses_noise(self):
        old = self._snap("http://x/p", "<h1>H</h1><span class='price'>$49</span>")
        new = self._snap("http://x/p", "<h1>H</h1><span class='price'>$59</span>")
        ignore = IgnoreList()
        ignore.add("price", ".*")
        alerts = RuleEngine(ignore).evaluate(diff_snapshots(old, new))
        self.assertFalse([a for a in alerts if a.rule == "pricing_changed"])

    def test_duplicate_snapshot_no_alert(self):
        store = SnapshotStore()
        html = "<h1>H</h1><span class='price'>$49</span>"
        s1 = store.add(self._snap("http://x/p", html))
        s2 = store.add(self._snap("http://x/p", html, "2026-11-11T15:05:00+00:00"))
        self.assertFalse(s1.is_duplicate)
        self.assertTrue(s2.is_duplicate)
        # A scheduler cycle over duplicates must not alert: diff of
        # identical normalized content yields no changes.
        self.assertEqual(diff_snapshots(s1, s2), [])


class TestSchedulerEndToEnd(unittest.TestCase):
    def test_full_cycle_detects_change_then_duplicates(self):
        set_version("acme", 1)
        reg = Registry()
        reg.add(WatchedURL(url=f"{BASE}/acme/pricing", authorized=True,
                           authorization_note="local fixture",
                           policy=policy()))
        store = SnapshotStore()
        sched = Scheduler(reg, store)
        r1 = sched.run_cycle()
        self.assertEqual(len(r1.alerts), 0)
        set_version("acme", 2)
        r2 = sched.run_cycle()
        rules = {a.rule for a in r2.alerts}
        self.assertIn("pricing_changed", rules)
        self.assertIn("headline_changed", rules)
        self.assertIn("new_item", rules)
        pa = [a for a in r2.alerts if a.rule == "pricing_changed"][0]
        self.assertEqual((pa.old, pa.new), ("$49/mo", "$59/mo"))
        r3 = sched.run_cycle()
        self.assertEqual(len(r3.alerts), 0)
        self.assertEqual(len(r3.duplicates), 1)
        set_version("acme", 1)

    def test_fetch_error_recorded_not_fatal(self):
        reg = Registry()
        reg.add(WatchedURL(url="http://127.0.0.1:1/unreachable", authorized=True,
                           authorization_note="test",
                           policy=policy(max_retries=0)))
        sched = Scheduler(reg, SnapshotStore())
        report = sched.run_cycle()
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(len(report.alerts), 0)


if __name__ == "__main__":
    unittest.main()
