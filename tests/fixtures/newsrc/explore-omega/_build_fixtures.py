"""Regenerate tests/fixtures/newsrc/explore-omega/* from real omega payloads.

Fixtures captured 2026-10-06 from the live API; this script replays the exact
trimming: group selection (brown-bears id=20, honey-bees id=4), snapshot rows
minus the huge ``description`` field, and cam pages reduced to verbatim
(backslash-escaped) windows around the group's feed records.

Prereq: a warm per-family fetch cache under ``data/ingest/cache/explore-omega/``
as left by a prior live run of ``py -3.11 -m wfd.ingest.newsrc.explore_omega``.
Run from the repo root:  py -3.11 tests/fixtures/newsrc/explore-omega/_build_fixtures.py
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from wfd.ingest.newsrc.base import fetch_cache

FIX = pathlib.Path(__file__).resolve().parent
INITIAL = "https://omega.explore.org/api/initial?contenttype=livecams"
SNAPS = "https://omega.explore.org/api/get_cam_group_snapshots.json?id={id}"
REC = re.compile(
    r'\\*"slug\\*":\\*"([^"\\]+)\\*",\\*"camgroup_slug\\*":\\*"([^"\\]+)\\*",'
    r'\\*"video_id\\*":\\*"([^"\\]+)\\*"'
)


def main() -> int:
    cache = fetch_cache("explore-omega")
    init = cache.json(INITIAL)
    groups = {g["slug"]: g for g in init["data"]["camgroups"]}

    keep = [groups["brown-bears"], groups["honey-bees"]]
    payload = {"status": init.get("status"), "message": init.get("message"),
               "data": {"camgroups": keep}}
    (FIX / "initial-sample.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    for gid, name in ((20, "snapshots-20.json"), (4, "snapshots-4.json")):
        snap = cache.json(SNAPS.format(id=gid))
        rows = []
        for row in snap.get("data") or []:
            row = dict(row)
            row["description"] = ""  # trimmed: huge HTML copy, unused by the ingester
            rows.append(row)
        out = {"status": snap.get("status"), "message": snap.get("message"),
               "count": snap.get("count"), "data": rows}
        (FIX / name).write_text(json.dumps(out, indent=1, ensure_ascii=False),
                                encoding="utf-8")

    def make_page(page_url: str, slugs: set, out_name: str, margin: int = 140):
        html = cache.text(page_url)
        spans = []
        for m in REC.finditer(html):
            if m.group(1) in slugs:
                spans.append((max(0, m.start() - margin), min(len(html), m.end() + margin)))
        spans.sort()
        merged = []
        for s, e in spans:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        body = "\n...\n".join(html[s:e] for s, e in merged)
        doc = ('<!DOCTYPE html><html><body>'
               '<script>self.__next_f.push([1,"' + body + '"])</script>'
               "</body></html>")
        (FIX / out_name).write_text(doc, encoding="utf-8")
        got = {}
        for slug, _group, vid in REC.findall(doc):
            got.setdefault(slug, vid)
        print(f"{out_name}: {len(merged)} windows, covered {len(slugs & set(got))}/{len(slugs)}")
        return got

    make_page("https://explore.org/livecams/brown-bears/brown-bear-salmon-cam-brooks-falls",
              {f["slug"] for f in groups["brown-bears"]["feeds"]}, "page-brown-bears.html")
    make_page("https://explore.org/livecams/honey-bees/honey-bee-hive-cam",
              {f["slug"] for f in groups["honey-bees"]["feeds"]}, "page-honey-bees.html")
    print("fixtures rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
