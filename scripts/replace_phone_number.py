#!/usr/bin/env python3
"""
Replace the old VITA Host phone / WhatsApp number with the new one.

Old: 611 947 592   (Spain mobile)
New: 674 497 938

Covers every common surface form found in the static export:
  - display          "611 947 592"          → "674 497 938"
  - compact          "611947592"            → "674497938"

Together these handle all combinations:
  - "+34 611 947 592"                  (header display)
  - "+34611947592"                     (compact international)
  - "tel:+34611947592"                 (clickable phone link)
  - "https://wa.me/34611947592"        (WhatsApp link)
  - "https://wa.me/34611947592?text=…" (with prefilled message)

Run from repo root:
    python3 scripts/replace_phone_number.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

REPLACEMENTS = [
    # Order matters: do the spaced form first, then the compact form, so the
    # space-stripping doesn't accidentally match inside the already-rewritten
    # display variant.
    ("611 947 592", "674 497 938"),
    ("611947592", "674497938"),
]

# Files we scan: every text-like file under public/, the assets folder, the
# README, and any top-level scripts. We skip binary blobs (images, fonts).
TEXT_EXTENSIONS = {
    ".html", ".htm", ".css", ".js", ".json", ".xml",
    ".txt", ".md", ".svg", ".webmanifest",
}


def iter_text_files() -> list[Path]:
    candidates: list[Path] = []
    for p in PUBLIC.rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS:
            candidates.append(p)
    # Top-level files too (README, vercel.json, etc.)
    for p in ROOT.iterdir():
        if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS:
            candidates.append(p)
    return candidates


def process_file(path: Path, dry_run: bool) -> dict[str, int]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {}

    hits: dict[str, int] = {}
    new_text = text
    for old, new in REPLACEMENTS:
        count = new_text.count(old)
        if count:
            hits[old] = count
            new_text = new_text.replace(old, new)

    if hits and not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    files = iter_text_files()
    touched = 0
    grand_total: dict[str, int] = {old: 0 for old, _ in REPLACEMENTS}

    for path in sorted(files):
        hits = process_file(path, args.dry_run)
        if not hits:
            continue
        touched += 1
        rel = path.relative_to(ROOT)
        summary = ", ".join(f"{old}×{n}" for old, n in hits.items())
        print(f"  {rel}: {summary}")
        for old, n in hits.items():
            grand_total[old] += n

    mode = "DRY RUN" if args.dry_run else "WROTE"
    totals = ", ".join(f"{old}×{n}" for old, n in grand_total.items())
    print(f"\n[{mode}] touched={touched} totals: {totals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
