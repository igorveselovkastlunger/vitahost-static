#!/usr/bin/env python3
"""
Replace CF7 forms with Web3Forms in vitahost-static HTML pages.

Why: vitahost.es runs as a static export on Vercel now — no WordPress backend
exists, so CF7 POST endpoints return 405. The /contact-airbnb-... page already
uses Web3Forms (third-party SaaS) and works. This script applies the same
swap to every other page that still has CF7 forms.

What it changes per form:
  1. <form action="/#wpcf7-..." method="post"  →  action="https://api.web3forms.com/submit" method="POST"
  2. <fieldset class="hidden-fields-container">…CF7 hidden inputs… → Web3Forms hidden inputs + honeypot
  3. Drops the inline <script src="…wp-includes/js/jquery/jquery…">-style CF7 init script (none on this repo)

What it does NOT touch:
  - Visible fields (Name / Location / Email / Phone / Type / Bedrooms / Subject / etc.)
  - CSS classes on inputs (wpcf7-form-control, etc.) — harmless, kept for styling
  - Submit button
  - Any non-form HTML

Run from repo root:
    python3 scripts/replace_cf7_with_web3forms.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

# Same access_key already used and verified on /contact-airbnb-... page.
ACCESS_KEY = "b15ad8b3-f5dd-4d93-951e-7f70f90cfdba"
FROM_NAME = "VITA Host — Contact Form"
SUBJECT = "VITA Host: New contact form submission"
REDIRECT = "https://vitahost.es/thank-you/"

WEB3FORMS_FIELDSET = f"""<fieldset class="hidden-fields-container">
<input type="hidden" name="access_key" value="{ACCESS_KEY}" />
<input type="hidden" name="from_name" value="{FROM_NAME}" />
<input type="hidden" name="subject" value="{SUBJECT}" />
<input type="hidden" name="redirect" value="{REDIRECT}" />
<input type="checkbox" name="botcheck" style="display:none" tabindex="-1" autocomplete="off" />
</fieldset>"""


# Matches the <form …> opening tag where action is a CF7 anchor like
# action="/#wpcf7-f495-p489-o1" or action="#wpcf7-…". method may be "post" or "POST".
FORM_TAG_RE = re.compile(
    r'<form\s+([^>]*?)action="[^"]*#wpcf7-[^"]+"\s*([^>]*?)method="[^"]+"\s*([^>]*)>',
    re.IGNORECASE,
)

# Matches the entire CF7 hidden-fields fieldset block. The CF7 fieldset only
# contains inputs named _wpcf7* — we replace the whole block.
HIDDEN_FIELDSET_RE = re.compile(
    r'<fieldset class="hidden-fields-container">\s*'
    r'(?:<input[^>]*name="_wpcf7[^"]*"[^>]*/?>\s*)+'
    r'</fieldset>',
    re.IGNORECASE,
)


def rewrite_form_tags(html: str) -> tuple[str, int]:
    """Rewrite <form action="…#wpcf7-…" method="post" …>."""
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        before = match.group(1).strip()
        between = match.group(2).strip()
        after = match.group(3).strip()
        # Reassemble keeping any other attributes (class, aria-label, novalidate, data-status, …)
        rest = " ".join(part for part in (before, between, after) if part)
        return f'<form action="https://api.web3forms.com/submit" method="POST" {rest}>'

    new_html = FORM_TAG_RE.sub(repl, html)
    return new_html, count


def rewrite_hidden_fields(html: str) -> tuple[str, int]:
    new_html, n = HIDDEN_FIELDSET_RE.subn(WEB3FORMS_FIELDSET, html)
    return new_html, n


def process_file(path: Path, dry_run: bool) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8")
    new_text, form_count = rewrite_form_tags(text)
    new_text, fs_count = rewrite_hidden_fields(new_text)

    if new_text == text:
        return 0, 0

    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return form_count, fs_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't write files, just report"
    )
    args = parser.parse_args()

    if not PUBLIC.is_dir():
        print(f"!! public/ not found at {PUBLIC}", file=sys.stderr)
        return 1

    # Skip cached wpo-minify assets — those are CSS/JS, not HTML pages.
    html_files = [
        p
        for p in PUBLIC.rglob("*.html")
        if "wp-content/cache/wpo-minify" not in p.as_posix()
    ]

    total_forms = 0
    total_fieldsets = 0
    touched = 0
    for path in html_files:
        # Skip the already-Web3Forms page (no CF7 left there).
        forms, fieldsets = process_file(path, args.dry_run)
        if forms or fieldsets:
            touched += 1
            total_forms += forms
            total_fieldsets += fieldsets
            rel = path.relative_to(ROOT)
            print(f"  {rel}: {forms} form tag(s), {fieldsets} fieldset(s)")

    mode = "DRY RUN" if args.dry_run else "WROTE"
    print(f"\n[{mode}] Touched {touched} file(s) · {total_forms} form tag(s) · {total_fieldsets} hidden fieldset(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
