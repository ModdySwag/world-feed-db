"""Regenerate tests/fixtures/newsrc/au-goldcoast-beach/* from the real discover payload.

Fixtures captured 2026-10-06 from the live City of Gold Coast discover API
(``GET .../v2/discover?categories=beaches``, 27 items, ~164 KB). This script
replays the exact trimming: the top-level 27-item array with heavy fields the
ingester never reads dropped (description, facilities, keywords, links,
polygons, imageUrl, subcategory), keeping
``id/title/category/shareId/suburb/coordinates/cams`` verbatim.

Prereq: a warm fetch cache under ``data/ingest/cache/au-goldcoast-beach/`` as
left by a prior live run of ``py -3.11 -m wfd.ingest.newsrc.au_goldcoast_beach``.
Run from the repo root:

    py -3.11 tests/fixtures/newsrc/au-goldcoast-beach/_build_fixtures.py
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from wfd.ingest.newsrc import au_goldcoast_beach as gc

KEEP = ("id", "title", "category", "shareId", "suburb", "coordinates", "cams")


def main() -> int:
    cache = gc.fetch_cache(gc.ENUMERATOR.name)
    payload = json.loads(cache.get(gc.API_URL, suffix=".json").decode("utf-8-sig"))
    items = [{k: it.get(k) for k in KEEP} for it in payload]
    out = pathlib.Path(__file__).resolve().parent / "discover-beaches.json"
    out.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cams = [c for it in items for c in (it.get("cams") or [])]
    print(f"wrote {out}")
    print(f"  items={len(items)} pairs={len(cams)} unique={len(dict.fromkeys(cams))} "
          f"bytes={out.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
