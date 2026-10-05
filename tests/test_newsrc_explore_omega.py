"""explore-omega enumerator tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_explore_omega.py    -> PASS lines; exit 0 = all good.

Fixtures in ``tests/fixtures/newsrc/explore-omega/`` are trimmed REAL payloads
(captured 2026-10-06): the omega initial JSON for two camgroups (brown-bears
id=20, honey-bees id=4), their snapshot JSONs, and one cam page per group with
the verbatim (backslash-escaped) embedded feed-record windows. No network: the
module's ``fetch_cache`` is monkeypatched with an in-process ``FakeCache`` that
serves those fixtures. Live runs happen via
``py -3.11 -m wfd.ingest.newsrc.explore_omega``, not from this file.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest.base import IngestResult
from wfd.ingest.newsrc import explore_omega
from wfd.ingest.newsrc.base import check_no_liveness, run_one
from wfd.schema import CameraRow

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc" / "explore-omega"

BROWN_BEARS_VIDEOS = {
    "brown-bear-salmon-cam-brooks-falls": "J7ZrIDvqlic",
    "river-watch-brown-bear-salmon-cams": "wkVLYfU-Kew",
    "brown-bear-salmon-cam-the-riffles": "z7_GhJeFxQI",
    "brown-bear-salmon-cam-lower-river": "cTsjMtjRLCo",
    "brooks-falls-brown-bears-low": "EwTH5yY7Mks",
    "underwater-bear-cam-brown-bear-salmon-cams": "vu7I315gQpU",
    "dumpling-mountain-brown-bear-salmon-cams": "uLgdUiT9WZQ",
    "alaska-naknek-river": "mfm9cjg6Khw",
    "brown-bears-meditation": "LuImCh7wL2I",
    "brooks-live-chat": "JHg1ll0O-P0",
}
HONEY_BEES_VIDEOS = {
    "honey-bee-hive-cam": "dBzbfKXQDjI",
    "honey-bee-landing-zone-cam": "RrNiDmQYopY",
}
GROUP = {"id": 20, "slug": "brown-bears", "title": "Brown Bears"}


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeCache:
    """Offline stand-in for FetchCache (same call surface used by the enumerator)."""

    def __init__(self):
        self.requests = []
        self.hits = 0
        self.misses = 0
        self._initial = load("initial-sample.json")
        self._snapshots = {20: load("snapshots-20.json"), 4: load("snapshots-4.json")}
        self._pages = {
            "https://explore.org/livecams/brown-bears/brown-bear-salmon-cam-brooks-falls":
                load_text("page-brown-bears.html"),
            "https://explore.org/livecams/honey-bees/honey-bee-hive-cam":
                load_text("page-honey-bees.html"),
        }

    def json(self, url, **kw):
        self.requests.append(url)
        if url == explore_omega.INITIAL_URL:
            self.misses += 1
            return self._initial
        m = re.fullmatch(
            r"https://omega\.explore\.org/api/get_cam_group_snapshots\.json\?id=(\d+)", url)
        if m and int(m.group(1)) in self._snapshots:
            self.misses += 1
            return self._snapshots[int(m.group(1))]
        raise AssertionError(f"FakeCache: unexpected json url {url}")

    def text(self, url, **kw):
        self.requests.append(url)
        if url in self._pages:
            self.misses += 1
            return self._pages[url]
        raise AssertionError(f"FakeCache: unexpected text url {url}")

    def stats(self):
        return {"cache_hits": self.hits, "cache_misses": self.misses}


def _enumerate_with_fake(limit=None):
    """Run the real enumerator + run_one(save=False) against the FakeCache."""
    fake = FakeCache()
    original = explore_omega.fetch_cache
    explore_omega.fetch_cache = lambda family, refresh=False: fake
    try:
        enum = explore_omega.ExploreOmegaEnumerator()
        if limit is not None:
            enum.limit = limit
        return run_one(enum, save=False), fake
    finally:
        explore_omega.fetch_cache = original


def _feed(**over):
    base = {
        "slug": "demo-feed", "title": "Demo Feed", "stream_id": "174",
        "is_offline": False, "force_offline": False, "snapshot_enabled": True,
        "snapshot": "https://snapshots.explore.org/EXP-Demo-EDGE/x-scaled.jpg",
        "thumb": "https://files.explore.org/files/demo.jpg",
    }
    base.update(over)
    return base


# --- module shape ---------------------------------------------------------------

def test_module_shape():
    e = explore_omega.ENUMERATOR
    assert isinstance(e, explore_omega.Enumerator)
    assert e.name == "explore-omega"
    assert e.provenance == "public_by_design"
    assert e.source_ref == explore_omega.INITIAL_URL
    assert e.attribution == "Explore.org (Annenberg Foundation) — explore.org/livecams"
    assert e.refresh is False and e.limit is None


# --- parse_initial --------------------------------------------------------------

def test_parse_initial_fixture():
    groups = explore_omega.parse_initial(load("initial-sample.json"))
    assert [g["slug"] for g in groups] == ["brown-bears", "honey-bees"]
    assert groups[0]["id"] == 20 and groups[0]["feed_count"] == 10
    assert len(groups[0]["feeds"]) == 10
    assert groups[0]["feeds"][0]["slug"] == "brown-bear-salmon-cam-brooks-falls"
    assert groups[1]["feed_count"] == 2
    assert [f["slug"] for f in groups[1]["feeds"]] == ["honey-bee-hive-cam",
                                                       "honey-bee-landing-zone-cam"]


def test_parse_initial_tolerates_malformed():
    assert explore_omega.parse_initial(None) == []
    assert explore_omega.parse_initial({}) == []
    got = explore_omega.parse_initial({"data": {"camgroups": [
        None, "x", {"id": 5},  # no slug -> skipped
        {"id": 6, "slug": "ok", "feeds": [{"title": "no-slug"}, {"slug": "s1", "title": "t1"}]},
    ]}})
    assert got == [{"id": 6, "slug": "ok", "title": "", "feed_count": 1,
                    "feeds": [{"slug": "s1", "title": "t1"}]}]


# --- parse_group_snapshots ------------------------------------------------------

def test_parse_group_snapshots_fixture():
    rows = explore_omega.parse_group_snapshots(load("snapshots-20.json"))
    assert len(rows) == 10
    first = rows[0]
    assert first["slug"] == "brown-bear-salmon-cam-brooks-falls"
    assert first["stream_id"] == "174"
    assert first["snapshot"].startswith("https://snapshots.explore.org/")
    assert first["is_offline"] is False and first["force_offline"] is False
    assert first["snapshot_enabled"] is True
    meditation = [r for r in rows if r["slug"] == "brown-bears-meditation"][0]
    assert meditation["is_offline"] is True

    bees = explore_omega.parse_group_snapshots(load("snapshots-4.json"))
    assert [r["slug"] for r in bees] == ["honey-bee-hive-cam", "honey-bee-landing-zone-cam"]
    assert bees[1]["is_offline"] is True

    assert explore_omega.parse_group_snapshots({}) == []
    assert explore_omega.parse_group_snapshots({"data": None}) == []


# --- parse_page_video_ids -------------------------------------------------------

def test_parse_page_video_ids_fixture():
    html = load_text("page-brown-bears.html")
    assert explore_omega.parse_page_video_ids(html) == BROWN_BEARS_VIDEOS

    # the unfiltered harvest covers every feed of the group's snapshot list
    snap_slugs = {r["slug"] for r in explore_omega.parse_group_snapshots(load("snapshots-20.json"))}
    assert snap_slugs <= set(explore_omega.parse_page_video_ids(html))

    bees = explore_omega.parse_page_video_ids(load_text("page-honey-bees.html"))
    assert bees == HONEY_BEES_VIDEOS

    # group filter uses the record's own camgroup_slug tag (dumpling is tagged
    # zen-den on the brown-bears page — pages carry cross-group records)
    zen = explore_omega.parse_page_video_ids(html, group_slug="zen-den")
    assert zen == {"dumpling-mountain-brown-bear-salmon-cams": "uLgdUiT9WZQ"}
    bb_only = explore_omega.parse_page_video_ids(html, group_slug="brown-bears")
    assert set(bb_only) == set(BROWN_BEARS_VIDEOS) - {"dumpling-mountain-brown-bear-salmon-cams"}


def test_parse_page_video_ids_escape_tolerance():
    # raw (unescaped) record style parses too
    raw = '<script>x"slug":"raw-feed","camgroup_slug":"grp","video_id":"AbCd123"y</script>'
    assert explore_omega.parse_page_video_ids(raw) == {"raw-feed": "AbCd123"}
    # deeper escape layers (as served) parse too
    esc = 'z\\"slug\\":\\"esc-feed\\",\\"camgroup_slug\\":\\"grp\\",\\"video_id\\":\\"EfGh456\\"q'
    assert explore_omega.parse_page_video_ids(esc) == {"esc-feed": "EfGh456"}
    assert explore_omega.parse_page_video_ids("") == {}
    assert explore_omega.parse_page_video_ids("<html>no records</html>") == {}


def test_parse_page_video_ids_normalizes_trailing_slash():
    # feed 'mississippi-river-flyway-cam' serves "video_id":"feR0k8-nkWE/" live
    html = 'x\\"slug\\":\\"slashy\\",\\"camgroup_slug\\":\\"grp\\",\\"video_id\\":\\"feR0k8-nkWE/\\"y'
    assert explore_omega.parse_page_video_ids(html) == {"slashy": "feR0k8-nkWE"}
    # a value that is only a slash is not a video id at all -> skipped
    bare = 'x\\"slug\\":\\"bare\\",\\"camgroup_slug\\":\\"grp\\",\\"video_id\\":\\"/\\"y'
    assert explore_omega.parse_page_video_ids(bare) == {}


# --- row_from_feed --------------------------------------------------------------

def test_row_from_feed_youtube():
    row = explore_omega.row_from_feed(_feed(), GROUP, "J7ZrIDvqlic")
    assert row.url == "https://www.youtube.com/watch?v=J7ZrIDvqlic"
    assert row.protocol == "youtube"
    assert row.status == "unknown"
    assert row.source_family == "explore-omega"
    assert row.provenance == "public_by_design"
    assert row.country == "" and row.lat is None and row.lon is None
    assert row.tags == ["nature"]
    assert row.attribution == "Explore.org (Annenberg Foundation) — explore.org/livecams"
    assert row.was_redacted is False and row.credential_present is False
    meta = row.meta
    assert meta["camgroup_id"] == 20 and meta["camgroup_slug"] == "brown-bears"
    assert meta["feed_slug"] == "demo-feed" and meta["feed_title"] == "Demo Feed"
    assert meta["video_id"] == "J7ZrIDvqlic" and meta["stream_id"] == "174"
    assert meta["is_offline"] is False
    assert meta["force_offline"] is False
    assert meta["snapshot_enabled"] is True
    assert meta["page_url"] == "https://explore.org/livecams/brown-bears/demo-feed"


def test_row_from_feed_meta_keys_exact():
    row = explore_omega.row_from_feed(_feed(), GROUP, "abc")
    assert set(row.meta) == {
        "camgroup_id", "camgroup_slug", "feed_slug", "feed_title", "video_id",
        "is_offline", "force_offline", "snapshot_enabled", "page_url", "stream_id",
    }


def test_row_from_feed_fallbacks():
    # no video id -> stillframe/snapshot URL, protocol jpeg
    jpeg = explore_omega.row_from_feed(_feed(), GROUP, None)
    assert jpeg.url == "https://snapshots.explore.org/EXP-Demo-EDGE/x-scaled.jpg"
    assert jpeg.protocol == "jpeg" and jpeg.meta["video_id"] == ""

    # no video id, no still -> cam page URL, protocol iframe
    bare = _feed(snapshot="", thumb="", thumb_large="", thumbnail_large_url=None,
                 stillframe_imageset=None)
    iframe = explore_omega.row_from_feed(bare, GROUP, None)
    assert iframe.url == "https://explore.org/livecams/brown-bears/demo-feed"
    assert iframe.protocol == "iframe"

    # title falls back to the slug; a feed without a slug is unaddressable
    assert explore_omega.row_from_feed({"slug": "solo"}, GROUP).name == "solo"
    assert explore_omega.row_from_feed({}, GROUP) is None
    assert explore_omega.row_from_feed({"title": "no-slug"}, GROUP) is None


def test_row_from_feed_redacts_credentials():
    feed = _feed(snapshot="https://user:pass@cdn.example.com/snap.jpg?token=SYNTH-SECRET&keep=1")
    row = explore_omega.row_from_feed(feed, GROUP, None)
    assert row.was_redacted is True and row.credential_present is True
    assert "SYNTH-SECRET" not in row.url and "user:pass@" not in row.url
    assert "keep=1" in row.url and "<redacted>" in row.url


def test_row_from_feed_flag_shapes():
    # string flags ("true"/"false") are tidied to bools; junk becomes None
    feed = _feed(is_offline="false", force_offline="true", snapshot_enabled="banana")
    row = explore_omega.row_from_feed(feed, GROUP, None)
    assert row.meta["is_offline"] is False
    assert row.meta["force_offline"] is True
    assert row.meta["snapshot_enabled"] is None


# --- full enumeration (offline, fixture-driven) ---------------------------------

def test_enumerate_offline_end_to_end():
    res, fake = _enumerate_with_fake()
    stats = res.stats
    assert res.family == "explore-omega"
    assert res.provenance == "public_by_design"
    assert stats["camgroups"] == 2 and stats["camgroups_available"] == 2
    assert stats["feeds"] == 12 and stats["feed_records"] == 12
    assert stats["feeds_with_video"] == 12 and stats["feeds_without_video"] == 0
    assert stats["video_ids_found"] == 12
    assert stats["pages_fetched"] == 2 and stats["pages_without_video_ids"] == 0
    assert stats["dupes_dropped"] == 0
    assert stats["groups_snapshot_failed_count"] == 0
    assert stats["groups_page_failed_count"] == 0
    assert len(res.rows) == 12
    assert stats["cache_misses"] == fake.misses == 5
    assert stats["cache_hits"] == fake.hits == 0

    by_slug = {r.meta["feed_slug"]: r for r in res.rows}
    assert set(by_slug) == set(BROWN_BEARS_VIDEOS) | set(HONEY_BEES_VIDEOS)
    assert all(r.status == "unknown" for r in res.rows)
    assert all(r.camera_id for r in res.rows)                      # finalize() filled ids
    assert all(r.meta["page_url"].startswith("https://explore.org/livecams/")
               for r in res.rows)
    assert by_slug["brown-bear-salmon-cam-brooks-falls"].url == \
        "https://www.youtube.com/watch?v=J7ZrIDvqlic"

    # published offline flag stays in meta; the row does NOT claim liveness
    landing = by_slug["honey-bee-landing-zone-cam"]
    assert landing.meta["is_offline"] is True
    assert landing.status == "unknown"

    # exact request sequence of the happy path (initial -> group snap -> page, twice)
    assert fake.requests == [
        explore_omega.INITIAL_URL,
        explore_omega.SNAPSHOT_URL_TMPL.format(id=20),
        "https://explore.org/livecams/brown-bears/brown-bear-salmon-cam-brooks-falls",
        explore_omega.SNAPSHOT_URL_TMPL.format(id=4),
        "https://explore.org/livecams/honey-bees/honey-bee-hive-cam",
    ]


def test_limit_caps_camgroups():
    res, fake = _enumerate_with_fake(limit=1)
    assert res.stats["camgroups"] == 1
    assert res.stats["camgroups_available"] == 2
    assert res.stats["feeds"] == 10 and len(res.rows) == 10
    assert fake.requests == [
        explore_omega.INITIAL_URL,
        explore_omega.SNAPSHOT_URL_TMPL.format(id=20),
        "https://explore.org/livecams/brown-bears/brown-bear-salmon-cam-brooks-falls",
    ]


def test_enumerate_survives_group_failures():
    """A broken group snapshot/page must not kill the run; stats record it."""
    fake = FakeCache()

    def failing_json(url, **kw):
        fake.requests.append(url)
        fake.misses += 1
        if url == explore_omega.SNAPSHOT_URL_TMPL.format(id=20):
            raise OSError("simulated snapshot failure")
        return fake._snapshots[int(url.rsplit("=", 1)[1])] if "snapshots" in url else fake._initial

    def failing_text(url, **kw):
        fake.requests.append(url)
        fake.misses += 1
        raise OSError("simulated page failure")

    fake.json = failing_json
    fake.text = failing_text
    original = explore_omega.fetch_cache
    explore_omega.fetch_cache = lambda family, refresh=False: fake
    try:
        enum = explore_omega.ExploreOmegaEnumerator()
        res = run_one(enum, save=False)
    finally:
        explore_omega.fetch_cache = original

    # brown-bears snapshot failed -> records rebuilt from the initial feeds list
    # (slug/title only) -> cam-page URL fallback (iframe); honey-bees snapshot
    # succeeded, so its rows fall back to the records' still URL (jpeg)
    assert res.stats["groups_snapshot_failed_count"] == 1
    assert res.stats["groups_page_failed_count"] == 2
    assert res.stats["feeds"] == 12
    assert res.stats["feeds_with_video"] == 0
    assert len(res.rows) == 12
    bb_rows = [r for r in res.rows if r.meta["camgroup_slug"] == "brown-bears"]
    hb_rows = [r for r in res.rows if r.meta["camgroup_slug"] == "honey-bees"]
    assert all(r.protocol == "iframe" for r in bb_rows)
    assert all(r.protocol == "jpeg" for r in hb_rows)
    assert all(r.status == "unknown" for r in res.rows)
    assert res.stats["groups_snapshot_failed"][0]["camgroup_slug"] == "brown-bears"


# --- liveness guard -------------------------------------------------------------

def test_liveness_guard_rejects_claimed_status():
    bad = IngestResult(family="explore-omega", provenance="public_by_design")
    bad.add(CameraRow(url="https://example.com/x", source_family="explore-omega",
                      status="live"))
    bad.finalize()
    try:
        check_no_liveness(bad)
        raised = False
    except ValueError:
        raised = True
    assert raised, "guard did not reject a non-unknown row"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
