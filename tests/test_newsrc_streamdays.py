"""Streamdays enumerator tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_streamdays.py   -> PASS lines; exit 0.

Fixtures under ``tests/fixtures/newsrc/streamdays/`` are trimmed REAL payloads
(fetched 2026-10-06) with every authorization/token/key value replaced by
``FIXTURE-*`` placeholders (see the generator notes in the module docstring
history): zoo hub + 6 cam page fragments, the Derby embedder page, the
Len Pick Trust page (YouTube — no streamdays code), the penguin loader script,
the penguin iframe HTML, the takeoff master + chunklist playlists, and the
first 564 real bytes of a live .ts segment. No network: ``polite_get`` /
``fetch_cache`` are monkeypatched in-process (always restored) and everything
is served from the fixtures.

The fake net models the two live facts the module relies on: the vendor 403s
script fetches without a Referer, and both vendor "bespoke-hosting" pages
404 (drift the module must record and work around via the embedder pages).
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest.newsrc import base as nb
from wfd.ingest.newsrc import streamdays as sd

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "newsrc" / "streamdays"

ZOO = sd.ZOO_SITE
PAGES = {
    sd.ZOO_HUB_URL: "zoo-hub.html",
    ZOO + "/animals/webcams/penguin-cam": "zoo-penguin-cam.html",
    ZOO + "/animals/webcams/koala-cam": "zoo-koala-cam.html",
    ZOO + "/animals/webcams/lion-cam": "zoo-lion-cam.html",
    ZOO + "/animals/webcams/giraffe-cam": "zoo-giraffe-cam.html",
    ZOO + "/animals/webcams/tiger-cam": "zoo-tiger-cam.html",
    ZOO + "/webcams/rockhopper-cam": "zoo-rockhopper-cam.html",
    "https://derbyperegrines.blogspot.com/p/our-webcams.html": "derby-webcams.html",
    "https://www.lenpicktrust.org.uk/live-video-stream/": "lenpick-stream.html",
}


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class OfflineNet:
    """Fixture-backed polite_get + FetchCache wiring for one offline run."""

    def __init__(self, cache_dir, *, fail_codes=(), extra_pages=None, fail_first_ts=False):
        self.cache_dir = pathlib.Path(cache_dir)
        self.fail_codes = set(fail_codes)
        self.fail_first_ts = fail_first_ts
        self._ts_calls = 0
        self.extra_paths: list = []
        self.extra_pages: dict = {}
        for k, v in (extra_pages or {}).items():
            path = k if k.startswith("/") else "/" + k.split("://", 1)[-1].split("/", 1)[-1]
            self.extra_paths.append(path)
            full = k if "://" in k else ZOO + k
            self.extra_pages[full] = v.encode() if isinstance(v, str) else v
        self.calls: list = []

    def fake_get(self, url, *, headers=None, **kw):
        self.calls.append(url)
        referer = (headers or {}).get("Referer")
        if "/bespoke-hosting/" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if url == sd.ZOO_HUB_URL and self.extra_paths:
            html = fixture("zoo-hub.html").decode("utf-8")
            for path in self.extra_paths:
                html = html.replace("</body>", f'<a href="{path}"><span class="label">New</span></a></body>')
            return html.encode()
        if url in self.extra_pages:
            return self.extra_pages[url]
        if url in PAGES:
            return fixture(PAGES[url])
        if url.startswith("https://live.streamdays.com/"):
            code = url.split("/")[3].split("?")[0]
            if "/iframe?authorization=" in url:
                if not referer:
                    raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
                return fixture("streamdays-iframe-penguin.html")
            if not referer:      # the live Referer gate: bare fetch -> 403
                raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
            if code in self.fail_codes:
                raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
            script = fixture("streamdays-script-penguin.js").decode("utf-8")
            return script.replace("xb1u3eln", code).encode()
        if "takeoff.jetstre.am" in url:
            return fixture("takeoff-master.m3u8")
        if "cdn.jetstre.am" in url and ".m3u8" in url:
            return fixture("takeoff-chunklist.m3u8")
        if "cdn.jetstre.am" in url and ".ts" in url:
            self._ts_calls += 1
            if self.fail_first_ts and self._ts_calls == 1:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # purged segment
            return fixture("segment-head.bin")
        raise AssertionError(f"unexpected fetch: {url}")

    def __enter__(self):
        self.orig_nb_get = nb.polite_get
        self.orig_sd_get = sd.polite_get
        self.orig_cache = sd.fetch_cache
        net = self
        nb.polite_get = net.fake_get
        sd.polite_get = net.fake_get
        sd.fetch_cache = lambda family, refresh=False: nb.FetchCache(net.cache_dir, refresh=refresh)
        return self

    def __exit__(self, *exc):
        nb.polite_get = self.orig_nb_get
        sd.polite_get = self.orig_sd_get
        sd.fetch_cache = self.orig_cache
        return False


def run_offline(extra_pages=None, **attrs):
    """One offline enumerate() on a fresh enumerator -> (result, net)."""
    with tempfile.TemporaryDirectory() as td, OfflineNet(td, extra_pages=extra_pages) as net:
        en = sd.StreamdaysEnumerator()
        for k, v in attrs.items():
            setattr(en, k, v)
        res = en.enumerate()
    return res, net


def run_offline_with(td, **attrs):
    """One offline enumerate() reusing an existing temp dir (cache reuse tests)."""
    with OfflineNet(td) as net:
        en = sd.StreamdaysEnumerator()
        for k, v in attrs.items():
            setattr(en, k, v)
        return en.enumerate(), net


# --- module shape ---------------------------------------------------------------

def test_module_shape():
    assert isinstance(sd.ENUMERATOR, nb.Enumerator)
    assert sd.ENUMERATOR.name == "streamdays"
    assert sd.ENUMERATOR.provenance == "public_by_design"
    assert sd.ENUMERATOR.source_ref == "https://www.edinburghzoo.org.uk/animals/webcams"
    assert sd.ENUMERATOR.attribution == "RZSS Edinburgh Zoo / Streamdays — live.streamdays.com"
    assert callable(sd.ENUMERATOR.enumerate)


def test_module_never_uses_urllib_directly():
    # hard rule: network only via fetch_cache / polite_get helpers
    src = pathlib.Path(sd.__file__).read_text(encoding="utf-8")
    assert "import urllib" not in src and "urllib.request" not in src


def test_player_url_and_chain_note():
    assert sd.player_url("xb1u3eln") == "https://live.streamdays.com/xb1u3eln"
    assert "tokens short-lived" in sd.CHAIN_NOTE
    assert "never store" in sd.CHAIN_NOTE


# --- pure parsers ---------------------------------------------------------------

def test_extract_codes_zoo_page():
    codes = sd.extract_codes(fixture("zoo-penguin-cam.html").decode("utf-8"))
    assert codes == [{"code": "xb1u3eln", "label": ""}], codes


def test_extract_codes_derby_labels_and_entities():
    codes = sd.extract_codes(fixture("derby-webcams.html").decode("utf-8"))
    assert [c["code"] for c in codes] == ["j5bs1zx3", "tjg7lunh"]
    assert codes[0]["label"] == "Derby Peregrines – Cam 1"
    assert codes[1]["label"] == "Derby Peregrines – Cam 2"


def test_extract_codes_skips_reserved_words_and_dedupes():
    html = (
        '<a href="https://live.streamdays.com/bespoke-hosting/x/y.html">x</a>'
        '<iframe src="https://live.streamdays.com/abcdef/iframe?authorization=X"></iframe>'
        '<script src="https://live.streamdays.com/abcdef"></script>'
    )
    assert [c["code"] for c in sd.extract_codes(html)] == ["abcdef"]
    assert sd.extract_codes(fixture("lenpick-stream.html").decode("utf-8")) == []


def test_harvest_hub_links():
    paths = sd.harvest_hub_links(fixture("zoo-hub.html").decode("utf-8"))
    assert paths == [
        "/animals/webcams/penguin-cam", "/animals/webcams/tiger-cam",
        "/animals/webcams/koala-cam", "/animals/webcams/lion-cam",
        "/animals/webcams/giraffe-cam", "/webcams/rockhopper-cam",
    ], paths


def test_playlists_parse_and_crlf_hardening():
    master = fixture("takeoff-master.m3u8").decode("utf-8")
    variant = sd.parse_master_playlist(master)
    assert variant.startswith("https://n2.cdn.jetstre.am/") and variant.endswith("chunklist.m3u8")
    chunklist = fixture("takeoff-chunklist.m3u8").decode("utf-8")
    parsed = sd.parse_chunklist(chunklist)
    assert parsed["media_sequence"] == 298560193
    assert parsed["segment"] == "media_298560193.ts"        # oldest listed
    assert parsed["last_segment"] == "media_298560195.ts"   # newest listed (fresh)
    # same parse on a CRLF copy (servers vary) — hardening for the line-split parser
    assert sd.parse_chunklist(chunklist.replace("\n", "\r\n")) == parsed
    assert sd.parse_master_playlist(master.replace("\n", "\r\n")) == variant
    assert sd.parse_master_playlist("") == ""
    assert sd.parse_chunklist("") == {"media_sequence": None, "segment": "", "last_segment": ""}


def test_page_title_suffix_strip():
    assert sd.page_title(fixture("zoo-penguin-cam.html").decode("utf-8")) == "Watch the penguins live!"
    assert sd.page_title("<title>No suffix</title>") == "No suffix"


# --- the full offline enumeration ----------------------------------------------

def test_offline_full_run_rows():
    res, net = run_offline()
    nb.check_no_liveness(res)                      # raises if any row claims liveness
    rows = res.rows
    assert len(rows) == 7, [r.url for r in rows]
    assert all(r.status == "unknown" for r in rows)
    assert all(r.source_family == "streamdays" and r.provenance == "public_by_design" for r in rows)
    assert all(r.country == "GB" and r.protocol == "hls" for r in rows)
    assert all(r.url.startswith("https://live.streamdays.com/") for r in rows)
    assert all(not r.was_redacted and not r.credential_present for r in rows)
    assert all(set(r.meta) == {"code", "embedder", "embedder_page", "chain", "verified_chain"}
               for r in rows)
    assert all(r.meta["chain"] == sd.CHAIN_NOTE for r in rows)

    by_code = {r.meta["code"]: r for r in rows}
    assert set(by_code) == {"xb1u3eln", "2ej7o9e5", "mlhwz7bt", "y4trtxbp", "67u7il21",
                            "j5bs1zx3", "tjg7lunh"}
    penguin = by_code["xb1u3eln"]
    assert penguin.name == "Penguin Cam — Edinburgh Zoo"
    assert penguin.tags == ["animal", "zoo"]
    assert penguin.meta["embedder"] == "edinburgh-zoo"
    assert penguin.meta["embedder_page"] == ZOO + "/animals/webcams/penguin-cam"
    assert penguin.meta["verified_chain"] is True          # the one proof cam
    assert all(not by_code[c].meta["verified_chain"] for c in by_code if c != "xb1u3eln")
    derby = by_code["j5bs1zx3"]
    assert derby.name == "Derby Peregrines – Cam 1"        # label scraped from the page
    assert derby.tags == ["animal", "wildlife"]
    assert derby.meta["embedder"] == "derby-cathedral"
    assert derby.attribution.startswith("Derby Cathedral Peregrine Project")

    st = res.stats
    assert st["cams"] == 7 and st["zoo_cams"] == 5 and st["extras_rows"] == 2
    assert st["offline_skipped"] == 1 and st["dupes_dropped"] == 0
    assert st["chain_verified"] == 1 and st["codes_resolved"] == 7
    assert st["offline"] == [{"page": ZOO + "/animals/webcams/koala-cam",
                              "name": "Koala Cam — Edinburgh Zoo"}]
    assert st["resolve_failures"] == [] and st["page_failed"] == [] and st["code_drift"] == []
    assert st["hub_new_pages"] == []
    assert st["cache_hits"] == 0 and st["cache_misses"] == 9   # hub + 6 pages + 2 embedder pages
    assert "chain_proof_failures" not in st                    # nothing failed this run


def test_offline_proof_chain_observables():
    res, net = run_offline()
    proof = res.stats["chain_proof"]
    assert proof["verified"] is True and proof["code"] == "xb1u3eln"
    stages = proof["stages"]
    assert stages["bare_script"]["http"] == 403           # referer gate recorded
    assert stages["script"]["bytes"] == len(fixture("streamdays-script-penguin.js"))
    assert stages["iframe"]["bytes"] == len(fixture("streamdays-iframe-penguin.html"))
    assert stages["chunklist"]["media_sequence"] == 298560193
    seg = fixture("segment-head.bin")
    assert stages["segment"]["sync_0x47"] is True
    assert stages["segment"]["bytes"] == len(seg)
    assert stages["segment"]["head_hex"] == seg[:4].hex()
    assert stages["segment"]["attempt"] == 1
    assert sd.player_url("xb1u3eln") in net.calls        # proof actually fetched it


def test_proof_segment_repoll_retry():
    """A purged first segment must not break the proof — one fresh re-poll wins."""
    with tempfile.TemporaryDirectory() as td, OfflineNet(td, fail_first_ts=True) as net:
        res = sd.StreamdaysEnumerator().enumerate()
    proof = res.stats["chain_proof"]
    assert proof["verified"] is True
    assert proof["stages"]["segment"]["attempt"] == 2     # first .ts 404 → re-polled
    assert "chain_proof_failures" not in res.stats


def test_offline_extras_drift_recorded():
    res, _ = run_offline()
    probe = {p["embedder"]: p for p in res.stats["extras_probe"]}
    assert "HTTPError" in probe["derby-cathedral"]["bespoke"]           # bespoke 404 recorded
    assert probe["derby-cathedral"]["embedder_page"] == "ok (2 codes)"  # drift fallback used
    assert "HTTPError" in probe["len-pick-trust"]["bespoke"]
    assert probe["len-pick-trust"]["embedder_page"] == "no streamdays code"
    assert res.stats["extras_skipped"] == [{"embedder": "len-pick-trust",
                                            "reason": "no resolvable streamdays code"}]


def test_token_values_never_persisted_or_emitted():
    """The whole point of the drift rule: tokens live in memory only."""
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res = sd.StreamdaysEnumerator().enumerate()
        for f in pathlib.Path(td).rglob("*"):        # fetch cache must be token-free
            if f.is_file():
                raw = f.read_bytes()
                assert b"authorization=" not in raw and b"FIXTURE-TOKEN" not in raw, f
                assert b"jetstre" not in raw, f
        dumped = json.dumps({"rows": [r.as_dict() for r in res.rows],
                             "stats": res.stats}, default=str)
        for needle in ("authorization=", "token=", "FIXTURE-TOKEN", "session/",
                       "jetstre.am/", '"token":', "refreshAuthorization"):
            assert needle not in dumped, needle
        assert "takeoff.jetstre.am" in dumped          # …only the documented note text
    assert any("xb1u3eln" in u for u in net.calls)     # sanity: net was exercised


def test_resolve_failures_recorded_zoo_row_kept():
    with tempfile.TemporaryDirectory() as td, OfflineNet(td, fail_codes={"2ej7o9e5"}) as net:
        res = sd.StreamdaysEnumerator().enumerate()
    assert "2ej7o9e5" in {r.meta["code"] for r in res.rows}      # zoo row kept despite failure
    assert res.stats["codes_resolved"] == 6
    assert [f["code"] for f in res.stats["resolve_failures"]] == ["2ej7o9e5"]
    assert res.stats["chain_verified"] == 1                      # penguin proof unaffected


def test_extras_row_only_when_code_resolves():
    with tempfile.TemporaryDirectory() as td, OfflineNet(td, fail_codes={"tjg7lunh"}) as net:
        res = sd.StreamdaysEnumerator().enumerate()
    codes = {r.meta["code"] for r in res.rows}
    assert "j5bs1zx3" in codes and "tjg7lunh" not in codes       # add rows if codes resolve
    assert res.stats["extras_rows"] == 1
    assert {"embedder": "derby-cathedral", "code": "tjg7lunh",
            "reason": "code did not resolve", "stage": "embedder-page fallback"} \
        in res.stats["extras_skipped"]


def test_limit_caps_zoo_candidates():
    res, net = run_offline(limit=2)                  # penguin + koala pages only
    assert res.stats["zoo_cams"] == 1 and res.stats["offline_skipped"] == 1
    assert res.stats["extras_rows"] == 2             # extras are their own lane
    assert res.stats["cams"] == 3
    assert [r.name for r in res.rows if r.meta["embedder"] == "edinburgh-zoo"] \
        == ["Penguin Cam — Edinburgh Zoo"]
    zoo_page_calls = [u for u in net.calls
                      if u.startswith(ZOO + "/animals/webcams/") or u.startswith(ZOO + "/webcams/")]
    assert len(zoo_page_calls) == 2                  # capped before fetching pages


def test_hub_discovers_new_cam_page():
    new_html = ('<title>Watch the pandas live! | Edinburgh Zoo</title>'
                '<div class="video"><script src="https://live.streamdays.com/pandacam1"'
                ' type="text/javascript"></script></div>')
    res, _ = run_offline(extra_pages={"/animals/webcams/panda-cam": new_html})
    assert res.stats["hub_new_pages"] == ["/animals/webcams/panda-cam"]
    panda = [r for r in res.rows if r.meta["code"] == "pandacam1"]
    assert len(panda) == 1
    assert panda[0].name == "Watch the pandas live!"             # title-derived (new page)
    assert panda[0].meta["embedder_page"] == ZOO + "/animals/webcams/panda-cam"
    assert res.stats["zoo_cams"] == 6 and res.stats["codes_resolved"] == 8


def test_code_drift_reported_but_live_wins():
    drift_html = fixture("zoo-penguin-cam.html").decode("utf-8").replace("xb1u3eln", "newcode1")
    res, _ = run_offline(extra_pages={"/animals/webcams/penguin-cam": drift_html})
    assert res.stats["code_drift"] == [{"page": ZOO + "/animals/webcams/penguin-cam",
                                        "expected": "xb1u3eln", "found": ["newcode1"]}]
    penguin = [r for r in res.rows
               if r.meta["embedder_page"] == ZOO + "/animals/webcams/penguin-cam"]
    assert len(penguin) == 1
    assert penguin[0].meta["code"] == "newcode1"       # the live code wins over expected_code
    assert penguin[0].meta["verified_chain"] is True   # proof re-resolves on the live code


def test_cache_reuse_second_run():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res1 = sd.StreamdaysEnumerator().enumerate()
            pages_after_1 = len([u for u in net.calls if u in PAGES])
            res2 = sd.StreamdaysEnumerator().enumerate()
            pages_after_2 = len([u for u in net.calls if u in PAGES])
    assert pages_after_1 == pages_after_2 == 9     # second run: zero new page fetches
    assert res1.stats["cache_hits"] == 0 and res1.stats["cache_misses"] == 9
    assert res2.stats["cache_misses"] == 0 and res2.stats["cache_hits"] == 9
    assert [r.url for r in res2.rows] == [r.url for r in res1.rows]
    assert res2.stats["chain_verified"] == 1               # proof re-runs live every time


def test_run_one_writes_jsonl_offline():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            res = nb.run_one(sd.StreamdaysEnumerator(), save=True, out_dir=td)
            path = pathlib.Path(td) / "newsrc-streamdays.jsonl"
            assert path.exists(), list(pathlib.Path(td).iterdir())
            raw = path.read_bytes()
            lines = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
            recomputed = hashlib.sha256(raw).hexdigest()
    assert len(lines) == 7
    assert all(l["status"] == "unknown" and l["camera_id"] for l in lines)
    assert res.stats["written"] == 7 and len(res.stats["sha256"]) == 64
    assert recomputed == res.stats["sha256"]
    assert res.stats["output"].endswith("newsrc-streamdays.jsonl")
    # the deliverable file itself carries no token values
    for needle in (b"authorization=", b"token=", b"FIXTURE-TOKEN", b"jetstre.am/"):
        assert needle not in raw, needle


def test_run_cli_smoke():
    with tempfile.TemporaryDirectory() as td:
        with OfflineNet(td) as net:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = sd.run_cli(sd.StreamdaysEnumerator(), ["--no-save"])
    out = buf.getvalue()
    assert code == 0, out
    assert "[streamdays]" in out and "rows=7" in out, out


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
