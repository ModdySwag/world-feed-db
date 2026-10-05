"""au-goldcoast-beach enumerator tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_au_goldcoast_beach.py   -> PASS lines; exit 0.

Fixtures under ``tests/fixtures/newsrc/au-goldcoast-beach/`` are a trimmed REAL
payload (discover API, fetched 2026-10-06; heavy unused fields dropped, all 27
items kept — see that dir's ``_build_fixtures.py``). No network: the newsrc
FetchCache + polite_get are monkeypatched in-process (always restored) and
everything is served from the fixtures / synthetic payloads. Live runs happen
via ``py -3.11 -m wfd.ingest.newsrc.au_goldcoast_beach``, not from this file.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest.newsrc import au_goldcoast_beach as gc
from wfd.ingest.newsrc import base as nb

FIXTURES = (pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc"
            / "au-goldcoast-beach")

META_KEYS = {"shareId", "cam_index", "api_url", "title", "shared_by", "drift_note"}


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class OfflineNet:
    """Fixture-backed polite_get + FetchCache wiring for one offline run."""

    def __init__(self, cache_dir, payload_bytes=None):
        self.cache_dir = cache_dir
        self.payload = (payload_bytes if payload_bytes is not None
                        else (FIXTURES / "discover-beaches.json").read_bytes())
        self.calls: list = []

    def fake_get(self, url, **kw):
        self.calls.append(url)
        if url == gc.API_URL:
            return self.payload
        raise AssertionError(f"unexpected fetch: {url}")

    def __enter__(self):
        self.orig_get = nb.polite_get
        self.orig_cache = gc.fetch_cache
        net = self
        nb.polite_get = net.fake_get
        gc.fetch_cache = lambda family, refresh=False: nb.FetchCache(net.cache_dir, refresh=refresh)
        return self

    def __exit__(self, *exc):
        nb.polite_get = self.orig_get
        gc.fetch_cache = self.orig_cache
        return False


def run_offline(payload_bytes=None, **attrs):
    """One offline enumerate() on a fresh enumerator -> (result, net)."""
    with tempfile.TemporaryDirectory() as td, OfflineNet(td, payload_bytes) as net:
        en = gc.GoldCoastBeachEnumerator()
        for k, v in attrs.items():
            setattr(en, k, v)
        res = en.enumerate()
    return res, net


# --- module shape --------------------------------------------------------------

def test_module_shape():
    assert isinstance(gc.ENUMERATOR, nb.Enumerator)
    assert gc.ENUMERATOR.name == "au-goldcoast-beach"
    assert gc.ENUMERATOR.provenance == "public_by_design"
    assert gc.ENUMERATOR.source_ref == gc.API_URL == (
        "https://mobileapp.goldcoast.qld.gov.au/v2/discover?categories=beaches")
    assert gc.ENUMERATOR.attribution == "City of Gold Coast — goldcoast.qld.gov.au beach cameras"
    assert callable(gc.ENUMERATOR.enumerate)


def test_module_never_uses_urllib_directly():
    # hard rule: network only via fetch_cache / polite_get helpers
    src = pathlib.Path(gc.__file__).read_text(encoding="utf-8")
    assert "urllib" not in src


# --- parsers -------------------------------------------------------------------

def test_fixture_payload_shape_and_parsers():
    payload = load("discover-beaches.json")
    entries = gc.parse_discover(payload)
    assert len(entries) == 27, len(entries)
    pairs = [(e["title"], c) for e in entries for c in gc.cam_urls(e)]
    assert len(pairs) == 32, len(pairs)
    assert len(dict.fromkeys(c for _, c in pairs)) == 21
    assert [e["title"] for e in entries if not gc.cam_urls(e)] == [
        "Broadbeach", "Mermaid", "Nobby Beach", "North Kirra"]

    # defensive payload shapes
    assert gc.parse_discover({"data": entries}) == entries
    assert gc.parse_discover({"items": entries}) == entries
    assert gc.parse_discover({"results": entries}) == entries
    assert gc.parse_discover([]) == []
    assert gc.parse_discover({}) == []
    assert gc.parse_discover([{"title": "a"}, "junk", 3]) == [{"title": "a"}]
    for bad in ("nope", 3, None):
        try:
            gc.parse_discover(bad)
            raised = False
        except ValueError:
            raised = True
        assert raised, f"non-list/dict payload {bad!r} must raise"


def test_cam_urls_shapes():
    assert gc.cam_urls({"cams": ["a", "b"]}) == ["a", "b"]
    assert gc.cam_urls({"cams": "a"}) == ["a"]                    # string form
    assert gc.cam_urls({}) == [] and gc.cam_urls({"cams": None}) == []
    assert gc.cam_urls({"cams": ["a", "", None, "b"]}) == ["a", "b"]
    assert gc.cam_urls({"cams": {"x": 1}}) == []                  # odd shape: drop


# --- the full offline enumeration ----------------------------------------------

def test_offline_full_run_rows():
    res, net = run_offline()
    nb.check_no_liveness(res)                     # raises if any row claims liveness
    rows = res.rows
    assert len(rows) == 21, len(rows)
    assert len({r.url for r in rows}) == 21        # deduped by URL
    assert all(r.status == "unknown" for r in rows)
    assert all(r.source_family == "au-goldcoast-beach" for r in rows)
    assert all(r.provenance == "public_by_design" for r in rows)
    assert all(r.country == "AU" and r.city == "Gold Coast" for r in rows)
    assert all(r.protocol == "hls" for r in rows)
    assert all(r.url.startswith("https://d1nm4r8e5x1rwd.cloudfront.net/cw/") for r in rows)
    assert all(not r.was_redacted and not r.credential_present for r in rows)
    assert all(set(r.meta) == META_KEYS for r in rows)
    assert all(r.meta["api_url"] == gc.API_URL and "re-resolve" in r.meta["drift_note"]
               for r in rows)

    by_url = {r.url.split("/")[-2]: r for r in rows}
    # shared stream: first listing kept; shared_by records who else lists it in order
    tug = by_url["tuguncamera.stream"]
    assert tug.name == "Bilinga" and tug.meta["title"] == "Bilinga"
    assert tug.meta["shareId"] == "/app/discover/beaches/bilinga"
    assert tug.meta["cam_index"] == 1
    assert tug.meta["shared_by"] == ["Bilinga", "Tugun"]
    curr = by_url["currumbincamera.stream"]
    assert curr.name == "Currumbin"
    assert curr.meta["shared_by"] == ["Currumbin", "Currumbin Alley", "Palm Beach", "Palm Beach South"]
    assert by_url["rainbowbaycamera.stream"].meta["shared_by"] == [
        "Coolangatta", "Greenmount", "Rainbow Bay"]
    assert by_url["surfersparadisehighcamera.stream"].name == "Northcliffe"
    assert by_url["narrowneckhighcamera.stream"].name == "Narrowneck cam 1"  # multi-cam item

    # multi-cam items: one row per cam, ' cam N' suffix, 1-based cam_index
    spit = [r for r in rows if r.meta["title"] == "Spit North"]
    assert [r.name for r in spit] == ["Spit North cam 1", "Spit North cam 2", "Spit North cam 3"]
    assert [r.meta["cam_index"] for r in spit] == [1, 2, 3]
    assert all(r.meta["shared_by"] == ["Spit North"] for r in spit)
    # both Burleigh North cams are shared with (and kept under) Burleigh Heads
    assert not any(r.meta["title"] == "Burleigh North" for r in rows)
    assert by_url["burleighhighcamera.stream"].meta["shared_by"] == [
        "Burleigh Heads", "Burleigh North"]

    # stats contract (live 2026-10-06 snapshot: 27 items / 32 pairs / 21 unique)
    st = res.stats
    assert st["items"] == 27 and st["items_total"] == 27
    assert st["unique_streams"] == 21 and st["rows"] == 21
    assert st["dupes_dropped"] == 11
    assert st["items_without_stream"] == 4
    assert st["cache_misses"] == 1 and st["cache_hits"] == 0
    assert "limit" not in st
    assert net.calls == [gc.API_URL]               # exactly one fetch


def test_dedupe_by_url_synthetic():
    payload = [
        {"title": "Beach A", "shareId": "/app/discover/beaches/a",
         "cams": ["https://cdn.example/cw/one.stream/playlist.m3u8"]},
        {"title": "Beach B", "shareId": "/app/discover/beaches/b",
         "cams": ["https://cdn.example/cw/one.stream/playlist.m3u8",
                  "https://cdn.example/cw/two.stream/playlist.m3u8"]},
    ]
    res, _ = run_offline(payload_bytes=json.dumps(payload).encode())
    assert len(res.rows) == 2 and res.stats["dupes_dropped"] == 1
    assert res.stats["unique_streams"] == 2 and res.stats["items"] == 2
    kept = [r for r in res.rows if r.meta["title"] == "Beach A"][0]
    assert kept.meta["shared_by"] == ["Beach A", "Beach B"]
    b = [r for r in res.rows if r.meta["title"] == "Beach B"][0]
    assert b.name == "Beach B cam 2"               # multi-cam item numbering is per-item
    assert b.meta["cam_index"] == 2
    assert all(r.status == "unknown" for r in res.rows)


def test_redaction_before_store_and_dedupe_key():
    payload = [
        {"title": "Cred Beach", "shareId": "/app/discover/beaches/cred",
         "cams": ["https://cdn.example/cw/x.stream/playlist.m3u8?token=SECRETVALUE"]},
        {"title": "Cred Beach 2", "shareId": "/app/discover/beaches/cred2",
         "cams": ["https://cdn.example/cw/x.stream/playlist.m3u8?token=SECRETVALUE"]},
    ]
    res, _ = run_offline(payload_bytes=json.dumps(payload).encode())
    assert len(res.rows) == 1 and res.stats["dupes_dropped"] == 1
    row = res.rows[0]
    assert "SECRETVALUE" not in row.url and "<redacted>" in row.url
    assert row.was_redacted is True and row.credential_present is True
    assert res.stats["redacted"] == 1


def test_limit_caps_items_not_rows():
    res, net = run_offline(limit=2)                # Bilinga (1 cam) + Broadbeach (0 cams)
    assert res.stats["items_total"] == 27 and res.stats["items"] == 2
    assert res.stats["limit"] == 2
    assert len(res.rows) == 1 and res.stats["items_without_stream"] == 1
    assert res.rows[0].name == "Bilinga"
    assert len(net.calls) == 1


def test_cache_reuse_second_run():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res1 = gc.GoldCoastBeachEnumerator().enumerate()
            calls_after_first = len(net.calls)
            res2 = gc.GoldCoastBeachEnumerator().enumerate()
    assert calls_after_first == 1                  # one API fetch
    assert len(net.calls) == calls_after_first     # second run: zero new fetches
    assert res1.stats["cache_misses"] == 1 and res1.stats["cache_hits"] == 0
    assert res2.stats["cache_hits"] == 1 and res2.stats["cache_misses"] == 0
    assert [r.url for r in res2.rows] == [r.url for r in res1.rows]


def test_run_one_writes_jsonl_offline():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res = nb.run_one(gc.GoldCoastBeachEnumerator(), save=True, out_dir=td)
            path = pathlib.Path(td) / "newsrc-au-goldcoast-beach.jsonl"
            assert path.exists(), list(pathlib.Path(td).iterdir())
            lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            recomputed = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(lines) == 21
    assert all(l["status"] == "unknown" and l["camera_id"] for l in lines)
    assert all(l["city"] == "Gold Coast" for l in lines)
    assert res.stats["written"] == 21 and len(res.stats["sha256"]) == 64
    assert recomputed == res.stats["sha256"]
    assert res.stats["output"].endswith("newsrc-au-goldcoast-beach.jsonl")


def test_run_cli_smoke():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = gc.run_cli(gc.GoldCoastBeachEnumerator(), ["--no-save", "--limit", "3"])
    out = buf.getvalue()
    assert code == 0, out
    assert "[au-goldcoast-beach]" in out and "rows=3" in out, out


def test_retry_wrapper_429_transient_and_hard_4xx():
    import urllib.error

    sleeps = []
    orig = gc._sleep
    gc._sleep = lambda s: sleeps.append(s)

    class Flaky:
        def __init__(self, codes):
            self.codes, self.calls = list(codes), []

        def get(self, url, **kw):
            self.calls.append(url)
            if self.codes:
                code = self.codes.pop(0)
                if code == "oserr":
                    raise OSError("boom")
                hdrs = {"Retry-After": "7"} if code == 429 else {}
                raise urllib.error.HTTPError(url, code, "e", hdrs, None)
            return b"ok"

    try:
        flaky = Flaky([429])
        assert gc._retry_get(flaky, "https://x/") == b"ok"
        assert len(flaky.calls) == 2 and sleeps == [7.0]     # Retry-After honored

        flaky = Flaky([404])
        try:
            gc._retry_get(flaky, "https://x/")
            raised = False
        except urllib.error.HTTPError:
            raised = True
        assert raised and len(flaky.calls) == 1              # hard 4xx: no retry
        assert sleeps == [7.0]                               # ...and no extra sleep

        flaky = Flaky(["oserr", "oserr", "oserr"])
        try:
            gc._retry_get(flaky, "https://x/")
            raised = False
        except OSError:
            raised = True
        assert raised and len(flaky.calls) == 3              # transient retried
        assert len(sleeps) == 3                              # 2 backoff sleeps + the 7.0
    finally:
        gc._sleep = orig


# --- runner ---------------------------------------------------------------------

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
