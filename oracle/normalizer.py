"""HTML parsing, volatile-content normalization, structured extraction.

Normalization removes volatile content (timestamps, rotating IDs,
session tokens, whitespace) WITHOUT deleting meaningful differences.
It is deliberately conservative: only patterns that are volatile by
construction are stripped. Anything else is a real change.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Volatile by construction: ISO/RFC timestamps, UUIDs, long hex tokens,
# session/token-looking query values, and elements whose only text is a
# timestamp. Deliberately NOT stripped: prices, numbers in prose, dates
# that are part of content (e.g. "Sale ends Friday").
_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?\b"
)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
_LONG_HEX_RE = re.compile(r"\b[0-9a-f]{24,}\b", re.I)
_EPOCH_RE = re.compile(r"\b1[67]\d{8}\b")  # 10-digit epoch seconds
_PRICE_RE = re.compile(r"[$€£¥]\s?\d[\d,]*(\.\d{2})?")

VOLATILE_ATTR_NAMES = {"data-session", "data-token", "data-request-id", "data-nonce"}
VOLATILE_CLASS_HINTS = ("timestamp", "session-id", "request-id", "live-clock")


class Node:
    def __init__(self, tag: str, attrs: dict):
        self.tag = tag
        self.attrs = attrs
        self.children: list[Node] = []
        self.text_parts: list[str] = []

    def text(self) -> str:
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.text())
        return "".join(parts)

    def find_all(self, tag: str | None = None, class_hint: str | None = None):
        out = []
        if (tag is None or self.tag == tag) and (
            class_hint is None
            or class_hint.lower() in self.attrs.get("class", "").lower()
        ):
            out.append(self)
        for child in self.children:
            out.extend(child.find_all(tag, class_hint))
        return out


class _TreeBuilder(HTMLParser):
    VOID = {"meta", "link", "img", "br", "hr", "input", "source"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self._stack = [self.root]
        self._skip = 0  # depth inside script/style/noscript

    def handle_starttag(self, tag, attrs):
        # RCDATA elements (title/textarea): a new start tag inside one is
        # malformed markup. Recovery: implicitly close the RCDATA element
        # and process the tag normally, so the rest of the document does
        # not leak into the title.
        if self._stack and self._stack[-1].tag in ("title", "textarea"):
            self._stack.pop()
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            return
        if self._skip:
            return
        node = Node(tag, dict(attrs))
        self._stack[-1].children.append(node)
        if tag not in self.VOID:
            self._stack.append(node)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._skip:
            return
        # CPython's HTMLParser treats <title>/<textarea> as CDATA: nested
        # markup arrives here as raw text, never as start tags. A literal
        # "<" inside such text can only start a (malformed) tag, so drop
        # everything from the first "<" onward.
        if self._stack and self._stack[-1].tag in ("title", "textarea"):
            data = data.split("<", 1)[0]
        self._stack[-1].text_parts.append(data)

    def handle_comment(self, data):
        return  # comments are volatile noise


def parse_html(html: str) -> Node:
    """Parse (possibly malformed) HTML into a small tolerant DOM."""
    builder = _TreeBuilder()
    try:
        builder.feed(html)
        builder.close()
    except Exception:
        # html.parser is forgiving; a partial tree is still usable.
        pass
    return builder.root


def _is_volatile_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if _TIMESTAMP_RE.search(stripped) and len(stripped) < 40:
        return True
    return False


def normalize_text(html: str) -> str:
    """Normalized visible text: volatile tokens removed, whitespace collapsed."""
    root = parse_html(html)
    chunks: list[str] = []

    def walk(node: Node) -> None:
        classes = node.attrs.get("class", "").lower()
        if any(h in classes for h in VOLATILE_CLASS_HINTS):
            return
        for part in node.text_parts:
            chunks.append(part)
        for child in node.children:
            walk(child)

    walk(root)
    text = " ".join(chunks)
    text = _TIMESTAMP_RE.sub(" ", text)
    text = _UUID_RE.sub(" ", text)
    text = _LONG_HEX_RE.sub(" ", text)
    text = _EPOCH_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_fields(html: str, hints: dict | None = None) -> dict:
    """Extract title, meta description, price, headlines, and item lists."""
    hints = hints or {}
    root = parse_html(html)
    fields: dict = {}

    titles = root.find_all("title")
    if titles:
        fields["title"] = titles[0].text().strip()
    for meta in root.find_all("meta"):
        if meta.attrs.get("name", "").lower() == "description":
            fields["meta_description"] = meta.attrs.get("content", "").strip()

    price_hint = hints.get("price", "price")
    price_nodes = root.find_all(class_hint=price_hint)
    price = None
    if price_nodes:
        price = price_nodes[0].text().strip()
    else:
        m = _PRICE_RE.search(root.text())
        price = m.group(0) if m else None
    if price:
        fields["price"] = price

    fields["headlines"] = [
        n.text().strip() for n in root.find_all("h1") if n.text().strip()
    ]
    sub = [n.text().strip() for n in root.find_all("h2") if n.text().strip()]
    if sub:
        fields["subheadlines"] = sub

    item_hint = hints.get("items", "product")
    items = [
        n.text().strip()
        for n in root.find_all(class_hint=item_hint)
        if n.text().strip() and len(n.text().strip()) < 120
    ]
    # De-duplicate while preserving order.
    seen, deduped = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    if deduped:
        fields["items"] = deduped
    return fields
