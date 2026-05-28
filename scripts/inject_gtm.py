#!/usr/bin/env python3
"""
Inject Google Tag Manager snippet (GTM-NVS6P82J) into every static HTML page.

Google's official two-snippet pattern:
  - <head> snippet: as high as possible inside <head>, immediately after <meta charset>
  - <body> snippet: immediately after the opening <body …> tag (noscript iframe fallback)

This script:
  - Is idempotent — if "GTM-NVS6P82J" is already on the page, it skips.
  - Skips cached wpo-minify CSS/JS assets and any non-page HTML (no <body>, no <head>).
  - Inserts after <meta charset="…"> in <head> when found, otherwise immediately after <head>.

Usage from repo root:
    python3 scripts/inject_gtm.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
GTM_ID = "GTM-NVS6P82J"

HEAD_SNIPPET = f"""<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
}})(window,document,'script','dataLayer','{GTM_ID}');</script>
<!-- End Google Tag Manager -->
"""

BODY_SNIPPET = f"""<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={GTM_ID}"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->
"""

# Prefer placement right after <meta charset="…" /> for the head snippet, which
# Google recommends so the script loads before other resources.
META_CHARSET_RE = re.compile(r'(<meta[^>]+charset=[^>]+>\s*)', re.IGNORECASE)
HEAD_OPEN_RE = re.compile(r'(<head[^>]*>\s*)', re.IGNORECASE)
BODY_OPEN_RE = re.compile(r'(<body[^>]*>)', re.IGNORECASE)


def inject(html: str) -> tuple[str, bool, bool]:
    """Return (new_html, head_injected, body_injected)."""
    if GTM_ID in html:
        return html, False, False

    head_done = False
    body_done = False

    # ── <head> snippet ────────────────────────────────────────────────────
    if "<head" in html.lower():
        # Try after <meta charset> first; fall back to <head>.
        if META_CHARSET_RE.search(html):
            html = META_CHARSET_RE.sub(
                lambda m: m.group(1) + HEAD_SNIPPET, html, count=1
            )
            head_done = True
        elif HEAD_OPEN_RE.search(html):
            html = HEAD_OPEN_RE.sub(
                lambda m: m.group(1) + HEAD_SNIPPET, html, count=1
            )
            head_done = True

    # ── <body> snippet ────────────────────────────────────────────────────
    if BODY_OPEN_RE.search(html):
        html = BODY_OPEN_RE.sub(
            lambda m: m.group(1) + "\n" + BODY_SNIPPET, html, count=1
        )
        body_done = True

    return html, head_done, body_done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    args = parser.parse_args()

    if not PUBLIC.is_dir():
        print(f"!! public/ not found at {PUBLIC}", file=sys.stderr)
        return 1

    html_files = [
        p
        for p in PUBLIC.rglob("*.html")
        if "wp-content/cache/wpo-minify" not in p.as_posix()
    ]

    touched = 0
    skipped = 0
    head_only = 0
    body_only = 0
    both = 0

    for path in html_files:
        text = path.read_text(encoding="utf-8")
        new_text, h, b = inject(text)

        if new_text == text:
            skipped += 1
            continue

        if not args.dry_run:
            path.write_text(new_text, encoding="utf-8")

        rel = path.relative_to(ROOT)
        if h and b:
            both += 1
            tag = "head+body"
        elif h:
            head_only += 1
            tag = "head only (no <body>?)"
        elif b:
            body_only += 1
            tag = "body only (no <head>?)"
        else:
            tag = "??"
        print(f"  {rel}: {tag}")
        touched += 1

    mode = "DRY RUN" if args.dry_run else "WROTE"
    print(
        f"\n[{mode}] touched={touched} skipped(already-have-GTM)={skipped} "
        f"head+body={both} head_only={head_only} body_only={body_only}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
