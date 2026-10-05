"""Regenerate tests/fixtures/newsrc/aus-airservices/* from the live fetch cache.

Fixtures captured 2026-10-06 from the live site (hub page, admin-ajax airport
list, airport pages); this script replays the exact trimming:

- hub-page.html      — the ``asa_airports_public_var`` JS config block, verbatim.
- ajax-airports.json — the real payload with ``airport_list`` trimmed to real
                       albany/broome/bunbury/wattsbridge/yulara entries plus ONE
                       clearly-labelled synthetic entry for the thumbnail
                       fallback path.
- page-*.html        — per-page camera "slide" fragments (verbatim windows
                       around each kept full-size JPEG) wrapped in a minimal
                       skeleton, plus verbatim ``-300x169`` grid items to
                       exercise size-variant exclusion.
- page-synthetic-foothill.html — composed (synthetic), yields no camera JPEGs.

Self-check: every written page fixture is re-parsed with the enumerator's own
``extract_camera_urls`` and must yield exactly the kept angles (0 for bunbury).

Prereq: a warm per-family fetch cache under ``data/ingest/cache/aus-airservices/``
as left by a live run of ``py -3.11 -m wfd.ingest.newsrc.aus_airservices``.
Run from the repo root:  py -3.11 tests/fixtures/newsrc/aus-airservices/_build_fixtures.py
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from wfd.ingest.newsrc.aus_airservices import (
    SITE, HUB_URL, ajax_list_url, extract_camera_urls, extract_nonce)
from wfd.ingest.newsrc.base import fetch_cache

FIX = pathlib.Path(__file__).resolve().parent

# real airports to keep in the trimmed ajax list, in the site's own order;
# value = angles kept in the page fixture ([] = page trimmed to its
# placeholder window; airports in PAGE_404 have no page fixture at all).
KEEP_ANGLES = {
    "Albany Airport": ["045"],
    "Broome Airport": ["090", "180", "270", "360"],
    "Bunbury Airport": [],
    "Watts Bridge Memorial Airfield": ["east", "north", "south", "west"],
}
PAGE_404 = {"Yulara Airport"}          # link 404s live; no page fixture

SYNTHETIC = {
    "id": 999001,
    "title": "Synthetic Fallback Aero",
    "link": f"{SITE}/asa-airports/synthetic-fallback-aero/",
    "thumbnail": f"{SITE}/wp-content/uploads/airports/123456/123456_315.jpg?v=1791222269",
    "state": "VIC",
    "state_full": "Victoria",
    "lat": "-37.5",
    "long": "144.9",
    "img_camera": f"{SITE}/wp-content/themes/asa/img/camera.png",
    "name": "synthetic-fallback-aero",
}


def slide_fragment(html: str, url: str) -> str:
    """Verbatim window around one full-size JPEG: wrapper div .. img + 2 closes."""
    i = html.find(url)
    assert i != -1, url
    start = html.rfind('<div class="col-4 col-md-4 col-lg-2 left-border top-border">', 0, i)
    if start == -1:
        start = html.rfind('<div class="camera-angle">', 0, i)
    assert start != -1, url
    end = html.find(">", i + len(url)) + 1          # close the <img> tag
    for _ in range(2):                              # main-image + col-md-12 closes
        end = html.find("</div>", end) + len("</div>")
    return html[start:end]


def grid_item(html: str, angle: str) -> str:
    """One verbatim grid item carrying a ``-300x169`` (size-variant) thumbnail."""
    for pattern in (
        r'<div class="[^"]*camera-list-item[^"]*"[^>]*>\s*'
        r'<img[^>]*src="[^"]*_' + re.escape(angle) + r'-300x169\.jpg[^"]*"[^>]*>\s*</div>',
        r'<div class="[^"]*camera-list-item[^"]*"[^>]*>\s*'
        r'<img[^>]*src="[^"]*/' + re.escape(angle) + r'-300x169\.jpg[^"]*"[^>]*>\s*</div>',
    ):
        m = re.search(pattern, html)
        if m:
            return m.group(0)
    return ""


def wrap(link: str, body: str) -> str:
    return (f"<!DOCTYPE html><html><body>\n"
            f"<!-- trimmed real fragment of {link} (weathercams.airservicesaustralia.com, "
            f"fetched 2026-10-06): camera-slide fragments + grid items -->\n"
            f"{body}\n</body></html>\n")


def main() -> int:
    cache = fetch_cache("aus-airservices")

    # --- hub: the JS config block, verbatim ------------------------------------
    hub = cache.text(HUB_URL)
    m = re.search(r"asa_airports_public_var\s*=\s*\{.*?\};", hub, re.S)
    assert m, "nonce var not found in cached hub page"
    (FIX / "hub-page.html").write_text(
        "<!DOCTYPE html><html><body>\n"
        "<!-- trimmed real hub page (fetched 2026-10-06): the enumerator reads only "
        "this JS config block -->\n<script>\n" + m.group(0) + "\n</script>\n"
        "</body></html>\n", encoding="utf-8")
    nonce = extract_nonce(hub)
    print(f"hub-page.html: JS config block ({len(m.group(0))} chars), nonce {nonce!r}")

    # --- ajax list: real entries trimmed + 1 synthetic entry -------------------
    payload = json.loads(cache.get(ajax_list_url(nonce)).decode("utf-8-sig"))
    keep = [a for a in payload["airport_list"]
            if a["title"] in KEEP_ANGLES or a["title"] in PAGE_404]
    keep.append(SYNTHETIC)
    out = {k: v for k, v in payload.items() if k != "airport_list"}
    out["airport_list"] = keep
    (FIX / "ajax-airports.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("ajax-airports.json: kept", len(keep), "of", len(payload["airport_list"]),
          "entries:", [a["title"] for a in keep])

    # --- airport pages ----------------------------------------------------------
    by_title = {a["title"]: a for a in payload["airport_list"]}
    for title, angles in KEEP_ANGLES.items():
        entry = by_title[title]
        html = cache.text(entry["link"])
        slug = entry["name"]
        if not angles:                       # bunbury: page up, no cameras
            i = html.find("Camera-Unavailable")
            body = html[max(0, i - 500): i + 500]
        else:
            found = {angle: url for url, angle, _f in extract_camera_urls(html)}
            parts = []
            for angle in angles:
                parts.append(slide_fragment(html, found[angle]))
                gi = grid_item(html, angle)
                if gi:
                    parts.append(gi)
            body = "\n".join(parts)
        text = wrap(entry["link"], body)
        (FIX / f"page-{slug}.html").write_text(text, encoding="utf-8")
        got = sorted(a for _u, a, _f in extract_camera_urls(text))
        assert got == sorted(angles), (title, got)
        print(f"page-{slug}.html: extracted angles {got}")

    # --- synthetic fallback page (no camera JPEGs at all) -----------------------
    (FIX / "page-synthetic-foothill.html").write_text(
        "<!DOCTYPE html><html><body>\n"
        "<!-- synthetic fixture: no camera JPEGs; the ajax thumbnail fallback must fire -->\n"
        f'<img class="img-fluid" src="{SITE}/wp-content/themes/asa/img/camera.png">\n'
        f'<img src="{SITE}/wp-content/uploads/2018/02/Camera-Unavailable.png">\n'
        "</body></html>\n", encoding="utf-8")
    print("page-synthetic-foothill.html: composed (extracts 0)")
    print("fixtures rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
