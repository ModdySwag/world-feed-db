"""Regenerate tests/fixtures/newsrc/au-nsw-marine/* from the real NSW payloads.

Fixtures captured 2026-10-06 from the live NSW webcams hub + sub-pages +
coastalcoms widget pages; this script replays the exact trimming from the warm
fetch cache:

- ``hub-webcams.html``: contiguous real slice of the hub covering the sub-page
  link list — all 22 slugs, each listed twice by the live page (~20 KB slice).
- ``hub-subset.html``: real ``<head>`` slice + the three full real anchors for
  ballina / coffs-harbour / iluka/yamba (the subset most offline runs use).
- ``page-<slug>.html``: real slice of each sub-page around its camera + weather
  iframes (~5 KB each).
- ``widget-<slug>.html``: the REAL widget pages verbatim (~4 KB each; covers
  both the streaming-au.coastalcoms and cloudfront HLS variants).
- ``synthetic-stub.html``: SYNTHETIC short JS-shell — no live stub was
  observable on 2026-10-06 (both UAs received full pages); this file exists to
  exercise the two-stage browser-UA retry path.

Prereq: a warm fetch cache under ``data/ingest/cache/au-nsw-marine/`` as left
by a prior live run of ``py -3.11 -m wfd.ingest.newsrc.au_nsw_marine``.
Run from the repo root:

    py -3.11 tests/fixtures/newsrc/au-nsw-marine/_build_fixtures.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from wfd.ingest.newsrc import au_nsw_marine as nm

FIX = pathlib.Path(__file__).resolve().parent
SUBSET = ("ballina", "coffs-harbour", "iluka/yamba")


def anchor_snippet(hub: str, slug: str) -> str:
    """The full real ``<a ...>...</a>`` element for one sub-page slug."""
    j = hub.find(f"/webcams/{slug}\"")
    if j < 0:
        raise SystemExit(f"slug {slug!r} not found in hub fixture source")
    start = hub.rfind("<a ", 0, j)
    end = hub.find("</a>", j) + 4
    return hub[start:end]


def main() -> int:
    cache = nm.fetch_cache(nm.ENUMERATOR.name)
    hub = cache.get(nm.HUB_URL, suffix=".html").decode("utf-8", errors="replace")

    # 1) hub slice covering the full link list (each slug appears twice)
    offs = [m.start() for m in nm._SUBPAGE_RE.finditer(hub)]
    if len(offs) < 2:
        raise SystemExit("hub cache has no sub-page links — rerun the live module")
    (FIX / "hub-webcams.html").write_text(
        "<!-- trimmed slice of the live hub (links region) -->\n"
        + hub[offs[0] - 1500: offs[-1] + 1500],
        encoding="utf-8")

    # 2) subset hub: real head + three real anchors
    subset = ["<!-- trimmed: real head slice + three full real anchors -->",
              hub[:4000], '<ul class="nsw-list">']
    for slug in SUBSET:
        subset.append(anchor_snippet(hub, slug))
    subset += ["</ul>", "</main></body></html>"]
    (FIX / "hub-subset.html").write_text("\n".join(subset), encoding="utf-8")

    # 3) page slices + 4) widget pages verbatim
    pages = dict(nm.extract_pages(hub))
    for slug in SUBSET:
        page_url = nm.SUBPAGE_ORIGIN + pages[slug]
        page = cache.get(page_url, suffix=".html").decode("utf-8", errors="replace")
        i = page.find(nm.SUBPAGE_WIDGET_MARKER)
        if i < 0:
            raise SystemExit(f"no webcam widget marker in cached page {slug}")
        start = max(0, page.rfind("<iframe", 0, i) - 1200)
        j = page.find("widget.coastalcoms.com/weather/")
        end = page.find("</iframe>", j) + len("</iframe>") + 2500
        name = slug.replace("/", "-")
        (FIX / f"page-{name}.html").write_text(page[start:end], encoding="utf-8")

        widget = nm.parse_webcam_iframe(page)
        widget_url = f"{nm.WIDGET_BASE}/{widget['widget_uuid']}"
        (FIX / f"widget-{name}.html").write_bytes(
            cache.get(widget_url, suffix=".html"))

    # 5) synthetic stub (documented; no live stub observable at build time)
    (FIX / "synthetic-stub.html").write_text(
        "<!doctype html>\n<!-- SYNTHETIC stub: no live NSW stub was observable "
        "2026-10-06; exercises the two-stage UA retry -->\n"
        "<html><head><title>Loading…</title></head>\n"
        "<body><div id=\"app\"></div>\n"
        "<script>/* this shell only renders for browser user agents */</script>\n"
        "</body></html>\n", encoding="utf-8")

    print("fixtures written to", FIX)
    for p in sorted(FIX.glob("*.html")):
        print(f"  {p.name:28} {p.stat().st_size:>7} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
