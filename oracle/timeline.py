"""Dashboard timeline: per-URL change history as HTML or console text."""

from __future__ import annotations

import html as html_lib
from datetime import datetime

from .rules import AlertSink
from .snapshot import SnapshotStore


def console_timeline(store: SnapshotStore, sink: AlertSink) -> str:
    lines = ["ORACLE timeline", "=" * 60]
    for url in store.urls():
        lines.append(f"\n{url}")
        for snap in store.history(url):
            dup = " (duplicate, no change)" if snap.is_duplicate else ""
            lines.append(
                f"  [{snap.observed_at}] status={snap.status} "
                f"norm_hash={snap.normalized_hash[:12]}{dup}"
            )
            fields = snap.fields
            if fields.get("price"):
                lines.append(f"    price: {fields['price']}")
            if fields.get("headlines"):
                lines.append(f"    headline: {fields['headlines'][0]}")
        for alert in sink.by_url(url):
            lines.append(
                f"  ALERT [{alert.status}] {alert.rule}: "
                f"{alert.old!r} -> {alert.new!r} (observed {alert.observed_at})"
            )
    return "\n".join(lines)


def render_html(store: SnapshotStore, sink: AlertSink, path: str) -> str:
    """Render a self-contained HTML timeline. No external assets."""
    esc = html_lib.escape
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>ORACLE — Change Timeline</title><style>"
        "body{font-family:system-ui,sans-serif;max-width:900px;margin:2em auto;"
        "padding:0 1em;color:#111}h1{font-size:1.4em}.url{border:1px solid #ddd;"
        "border-radius:8px;padding:1em;margin:1em 0}.alert{background:#fff4e5;"
        "border-left:4px solid #e67e22;padding:.5em;margin:.5em 0}"
        ".possible{background:#eef4ff;border-left-color:#3b82f6}"
        "code{background:#f4f4f4;padding:1px 4px;border-radius:3px}"
        "time{color:#666}</style></head><body><h1>ORACLE — Change Timeline</h1>",
        "<p>Snapshots record when a difference was <em>observed</em>, not a "
        "claim about when the site changed.</p>",
    ]
    for url in store.urls():
        parts.append(f"<div class='url'><h2>{esc(url)}</h2>")
        for snap in store.history(url):
            dup = " <em>(duplicate snapshot, no change)</em>" if snap.is_duplicate else ""
            parts.append(
                f"<p><time>{esc(snap.observed_at)}</time> status={snap.status} "
                f"normalized hash <code>{esc(snap.normalized_hash[:16])}</code>{dup}</p>"
            )
            if snap.fields.get("price"):
                parts.append(f"<p>Price: <strong>{esc(str(snap.fields['price']))}</strong></p>")
            if snap.fields.get("headlines"):
                parts.append(f"<p>Headline: {esc(snap.fields['headlines'][0])}</p>")
        for alert in sink.by_url(url):
            cls = "alert possible" if alert.status == "possible" else "alert"
            parts.append(
                f"<div class='{cls}'><strong>{esc(alert.rule)}</strong> "
                f"({esc(alert.status)})<br>Old: <code>{esc(str(alert.old))}</code>"
                f"<br>New: <code>{esc(str(alert.new))}</code>"
                f"<br>Evidence: <a href='{esc(alert.evidence_url)}'>{esc(alert.evidence_url)}</a> "
                f"observed {esc(alert.observed_at)}</div>"
            )
        parts.append("</div>")
    parts.append("</body></html>")
    text = "\n".join(parts)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
