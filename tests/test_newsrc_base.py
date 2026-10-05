"""newsrc base tests — plain-python runner, OFFLINE.

Run:    py -3.11 tests/test_newsrc_base.py    -> PASS lines; exit 0 = all good.

Covers the shared newsrc contracts: registry mechanics, the liveness guard,
run_one output naming (newsrc-<name>.jsonl + sha256), FetchCache round-trips
(fetch-once / cache-hit / refresh), format_result + run_cli smoke.
No network: polite_get is monkeypatched; temp dirs only.
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd.ingest.base import IngestResult
from wfd.ingest.newsrc import base as nb
from wfd.schema import CameraRow


class _Stub(nb.Enumerator):
    name = "stub-family"
    source_ref = "fixture://stub"
    provenance = "public_by_design"

    def __init__(self, status="unknown"):
        self.status = status

    def enumerate(self):
        res = IngestResult(family=self.name, provenance=self.provenance,
                           source_ref=self.source_ref)
        res.add(CameraRow(url="https://example.com/a", source_family=self.name,
                          status=self.status))
        return res


def test_registry_mechanics():
    en = _Stub()
    nb.register(en)
    assert nb.get("stub-family") is en
    assert nb.registry()["stub-family"] is en
    try:
        nb.get("nope")
        raised = False
    except KeyError:
        raised = True
    assert raised


def test_liveness_guard_rejects():
    bad = IngestResult(family="t")
    bad.add(CameraRow(url="https://example.com/x", source_family="t", status="live"))
    bad.finalize()
    try:
        nb.check_no_liveness(bad)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_run_one_writes_newsrc_output():
    with tempfile.TemporaryDirectory() as td:
        res = nb.run_one(_Stub(), save=True, out_dir=td)
        path = pathlib.Path(td) / "newsrc-stub-family.jsonl"
        assert path.exists(), list(pathlib.Path(td).iterdir())
        assert res.stats["written"] == 1 and res.stats["sha256"]
        line = json.loads(path.read_text(encoding="utf-8").strip())
        assert line["status"] == "unknown" and line["camera_id"]
        assert res.stats["output"].endswith("newsrc-stub-family.jsonl")


def test_run_one_guard_blocks_write():
    with tempfile.TemporaryDirectory() as td:
        try:
            nb.run_one(_Stub(status="live"), save=True, out_dir=td)
            raised = False
        except ValueError:
            raised = True
        assert raised
        assert not list(pathlib.Path(td).iterdir())    # nothing was written


def test_fetch_cache_roundtrip():
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return b"payload:" + url.encode()

    original = nb.polite_get
    nb.polite_get = fake_get
    try:
        with tempfile.TemporaryDirectory() as td:
            c1 = nb.FetchCache(td)
            assert c1.get("https://x.test/a", suffix=".json") == b"payload:https://x.test/a"
            assert c1.get("https://x.test/a", suffix=".json") == b"payload:https://x.test/a"
            assert len(calls) == 1 and c1.misses == 1 and c1.hits == 1
            c2 = nb.FetchCache(td)                      # fresh instance, same dir
            assert c2.get("https://x.test/a", suffix=".json") == b"payload:https://x.test/a"
            assert len(calls) == 1 and c2.hits == 1     # served from disk
            c3 = nb.FetchCache(td, refresh=True)
            c3.get("https://x.test/a", suffix=".json")
            assert len(calls) == 2 and c3.misses == 1
    finally:
        nb.polite_get = original


def test_format_result_and_run_cli_smoke():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = nb.run_cli(_Stub(), ["--no-save"])
    assert code == 0
    text = out.getvalue()
    assert "[stub-family]" in text and "rows=1" in text


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
