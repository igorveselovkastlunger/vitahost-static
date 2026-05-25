#!/usr/bin/env python3
"""
Static mirror of vitahost.es for Vercel deployment.

Strategy:
1. Seed URLs come from /sitemap.xml (so all HTML pages we visit are explicit).
2. Each seed page is fetched, parsed for assets (CSS/JS/img/srcset/url(...)).
3. Assets are downloaded recursively (CSS also discovers @import / url(...)).
4. We do NOT follow new HTML pages discovered in markup — that route always
   pulled in WordPress shortlinks (/?p=123), comment feeds, pagination, etc.
5. Absolute https://vitahost.es/ links are rewritten to root-relative.
"""
from __future__ import annotations

import gzip
import os
import re
import socket
import ssl
import sys
import time
from html import unescape
from pathlib import Path
from urllib.parse import urlparse, urljoin, unquote, quote
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET

BASE_URL = "https://vitahost.es"
BASE_HOST = "vitahost.es"
# Hit the origin WordPress directly — DNS for vitahost.es is now pointed at
# Vercel (this very mirror), so the canonical resolver would loop us back to
# our own snapshot. Override at the socket layer.
ORIGIN_IP = "217.160.0.225"
OUT_DIR = Path(__file__).parent / "public"

_real_getaddrinfo = socket.getaddrinfo
def _patched_getaddrinfo(host, *args, **kwargs):
    if host in (BASE_HOST, f"www.{BASE_HOST}"):
        return _real_getaddrinfo(ORIGIN_IP, *args, **kwargs)
    return _real_getaddrinfo(host, *args, **kwargs)
socket.getaddrinfo = _patched_getaddrinfo

# Some shared SSL hosting setups don't have a matching cert for the bare IP —
# skip cert hostname checking; we already trust the IP source.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "vitahost-static-mirror"
)
SLEEP_BETWEEN = 0.15

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

# Only these attributes can legitimately carry a URL — `content` is meta-data,
# `action` is a form endpoint (handled separately).
ATTR_RE = re.compile(
    r'''(href|src|data-src|poster)\s*=\s*("([^"]*)"|'([^']*)')''',
    re.IGNORECASE,
)
SRCSET_RE = re.compile(
    r'''(srcset|data-srcset|imagesrcset)\s*=\s*("([^"]*)"|'([^']*)')''',
    re.IGNORECASE,
)
CSS_URL_RE = re.compile(r'url\(\s*(["\']?)([^)"\']+)\1\s*\)')
CSS_IMPORT_RE = re.compile(r'@import\s+(?:url\()?["\']([^"\')]+)["\']?\)?', re.IGNORECASE)

SKIP_PATH_RE = re.compile(
    r'(/wp-admin|/wp-login\.php|/xmlrpc\.php|/wp-json|'
    r'/comments/feed|/comment-page-)',
    re.IGNORECASE,
)
# HTML pages we'll follow even though they aren't in the sitemap:
# blog/category pagination, taxonomy archives, classic contact aliases.
ALLOW_DISCOVERY_RE = re.compile(
    r'(/page/\d+/?$|/category/[^/]+/?$|/tag/[^/]+/?$|'
    r'/author/[^/]+/?$|^/contact/?$|^/contact-us/?$)',
    re.IGNORECASE,
)
SKIP_QUERY_RE = re.compile(
    r'(\bp=\d|\breplytocom=|\battachment_id=|\bs=|\bcat=|\btag=|\bpaged=)',
    re.IGNORECASE,
)
ASSET_EXT_RE = re.compile(
    r'\.(css|js|jpe?g|png|gif|webp|svg|ico|woff2?|ttf|otf|eot|mp4|webm|'
    r'pdf|xml|txt|json|map)(\?|$)',
    re.IGNORECASE,
)


def is_same_host(url: str) -> bool:
    p = urlparse(url)
    return p.netloc in ("", BASE_HOST, f"www.{BASE_HOST}")


def absolutize(url: str, page_url: str) -> str:
    return urljoin(page_url, url)


def should_skip(url: str) -> bool:
    p = urlparse(url)
    if SKIP_PATH_RE.search(p.path):
        return True
    if p.query and SKIP_QUERY_RE.search(p.query):
        return True
    return False


def looks_like_asset(url: str) -> bool:
    p = urlparse(url)
    return bool(ASSET_EXT_RE.search(p.path))


def to_local_path(url: str) -> Path:
    p = urlparse(url)
    path = unquote(p.path)  # query is intentionally dropped
    if path == "" or path == "/":
        path = "/index.html"
    elif path.endswith("/"):
        path = path + "index.html"
    else:
        last = path.rsplit("/", 1)[-1]
        if "." not in last:
            path = path + "/index.html"
    return OUT_DIR / path.lstrip("/")


# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

def fetch(url: str) -> tuple[bytes, str]:
    # Percent-encode any non-ASCII chars in the path (urllib only accepts ASCII)
    p = urlparse(url)
    safe_path = quote(p.path, safe="/%")
    safe_query = quote(p.query, safe="=&%")
    safe_url = p._replace(path=safe_path, query=safe_query).geturl()
    req = Request(safe_url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
    })
    with urlopen(req, timeout=30, context=_SSL_CTX) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data, r.headers.get("Content-Type", "")


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

def parse_sitemap(url: str) -> list[str]:
    print(f"~ sitemap: {url}")
    body, _ = fetch(url)
    root = ET.fromstring(body)
    urls: list[str] = []
    for sm in root.findall("sm:sitemap", NS):
        loc = sm.find("sm:loc", NS)
        if loc is not None and loc.text:
            urls += parse_sitemap(loc.text.strip())
    for u in root.findall("sm:url", NS):
        loc = u.find("sm:loc", NS)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _consider(raw: str, page_url: str, found: set[str]) -> None:
    raw = unescape(raw).strip()
    if not raw or raw.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
        return
    abs_url = absolutize(raw, page_url)
    if not is_same_host(abs_url):
        return
    if should_skip(abs_url):
        return
    found.add(abs_url)


def extract_html_assets(html: str, page_url: str) -> set[str]:
    found: set[str] = set()
    for m in ATTR_RE.finditer(html):
        _consider(m.group(3) or m.group(4) or "", page_url, found)
    for m in SRCSET_RE.finditer(html):
        raw = m.group(3) or m.group(4) or ""
        for entry in raw.split(","):
            url_part = entry.strip().split()[0] if entry.strip() else ""
            _consider(url_part, page_url, found)
    for m in CSS_URL_RE.finditer(html):
        _consider(m.group(2), page_url, found)
    return found


def extract_css_assets(css: str, css_url: str) -> set[str]:
    found: set[str] = set()
    for m in CSS_URL_RE.finditer(css):
        _consider(m.group(2), css_url, found)
    for m in CSS_IMPORT_RE.finditer(css):
        _consider(m.group(1), css_url, found)
    return found


# ---------------------------------------------------------------------------
# Link rewriting
# ---------------------------------------------------------------------------

REWRITE_RE = re.compile(r'https?://(?:www\.)?vitahost\.es', re.IGNORECASE)
PROTO_REL_RE = re.compile(r'(?<![:/])//(?:www\.)?vitahost\.es', re.IGNORECASE)

def rewrite(text: str) -> str:
    return PROTO_REL_RE.sub("", REWRITE_RE.sub("", text))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    sitemap_urls = parse_sitemap(f"{BASE_URL}/sitemap.xml")
    extras = [
        f"{BASE_URL}/",
        f"{BASE_URL}/robots.txt",
        f"{BASE_URL}/favicon.ico",
        f"{BASE_URL}/sitemap.xml",
    ]
    seed = [u for u in sitemap_urls + extras]
    # Deduplicate, preserve order
    seen = set()
    seed_urls: list[str] = []
    for u in seed:
        if u not in seen and is_same_host(u) and not should_skip(u):
            seen.add(u)
            seed_urls.append(u)
    seed_set = set(seed_urls)

    print(f"~ seed URLs: {len(seed_urls)}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    processed: set[str] = set()
    queue: list[str] = list(seed_urls)

    stats = {"html": 0, "css": 0, "asset": 0, "skip": 0, "error": 0}

    while queue:
        url = queue.pop(0)
        if url in processed:
            continue
        processed.add(url)

        if not is_same_host(url) or should_skip(url):
            stats["skip"] += 1
            continue

        try:
            body, ct = fetch(url)
        except HTTPError as e:
            print(f"  ! HTTP {e.code} for {url}")
            stats["error"] += 1
            continue
        except Exception as e:
            print(f"  ! err for {url}: {e}")
            stats["error"] += 1
            continue

        local = to_local_path(url)
        local.parent.mkdir(parents=True, exist_ok=True)

        ct_lower = ct.lower()
        is_html = "html" in ct_lower
        is_css = "css" in ct_lower or local.suffix == ".css"

        if is_html:
            text = body.decode("utf-8", errors="replace")
            assets = extract_html_assets(text, url)
            local.write_text(rewrite(text), encoding="utf-8")
            new_assets = 0
            for a in assets:
                if a in processed:
                    continue
                # Follow brand-new HTML pages only if (a) they're in the seed,
                # or (b) their path matches a discovery pattern we trust
                # (pagination, category, tag archives, contact aliases).
                if not looks_like_asset(a) and a not in seed_set:
                    if not ALLOW_DISCOVERY_RE.search(urlparse(a).path):
                        continue
                queue.append(a)
                new_assets += 1
            stats["html"] += 1
            print(f"+ html  {url}  → {local.relative_to(OUT_DIR)}  ({new_assets} new refs)")
        elif is_css:
            text = body.decode("utf-8", errors="replace")
            assets = extract_css_assets(text, url)
            local.write_text(rewrite(text), encoding="utf-8")
            new_assets = 0
            for a in assets:
                if a in processed:
                    continue
                queue.append(a)
                new_assets += 1
            stats["css"] += 1
            print(f"+ css   {url}  → {local.relative_to(OUT_DIR)}  ({new_assets} new refs)")
        else:
            local.write_bytes(body)
            stats["asset"] += 1
            print(f"+ asset {url}  → {local.relative_to(OUT_DIR)}  ({len(body)} B)")

        time.sleep(SLEEP_BETWEEN)

    print(f"\n=== Done.  html={stats['html']}  css={stats['css']}  "
          f"asset={stats['asset']}  skipped={stats['skip']}  err={stats['error']}")
    print(f"=== Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
