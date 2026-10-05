"""wfd.onboarding tests — plain-python runner (this host has no pytest).

Run:    py -3.11 tests/test_onboarding.py

Parses the real repo-root ACCOUNTS-AND-KEYS.md and checks the checklist
contract: every numbered service parses, the five key-gated services carry the
right secret names plus a live status with a valid source, and NO secret value
ever appears in the output (set/source only). Test values are fake.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd import creds, onboarding

TEST_VALUE = "test-value-123"
EXPECTED_MAP = {
    1: "WINDY_API_KEY",
    2: "ROAD511_API_KEY",
    3: "NSW_API_KEY",
    4: "QLDTRAFFIC_API_KEY",
    5: "SHODAN_API_KEY",
}
VALID_SOURCES = {"store", "env_file", "environment", "none"}


def test_document_parses():
    assert onboarding.DOC_PATH.exists(), onboarding.DOC_PATH
    rows = onboarding.checklist()
    numbers = [r["n"] for r in rows]
    assert numbers == sorted(numbers), "rows must come back sorted by service number"
    assert set(range(1, 13)) <= set(numbers), numbers   # services 1-12 all parse
    assert len(rows) == len(set(numbers)), "duplicate service numbers"
    for r in rows:
        assert isinstance(r["n"], int) and r["n"] >= 1
        assert r["service"], r
        for key in ("unlocks", "signup", "status_text"):
            assert isinstance(r[key], str) and r[key], (r["n"], key)


def test_five_mapped_services_found():
    rows = onboarding.checklist()
    mapped = {r["n"]: r["secret"] for r in rows if r["secret"]}
    assert mapped == EXPECTED_MAP, mapped
    assert onboarding.SECRET_MAP == EXPECTED_MAP
    for r in rows:
        if r["n"] > 5:
            assert r["secret"] is None, r
            assert r["set"] is None and r["source"] is None, r


def test_service_labels():
    rows = {r["n"]: r for r in onboarding.checklist()}
    assert rows[1]["service"] == "Windy Webcams API"
    assert rows[2]["service"].startswith("Road511")
    assert "NSW" in rows[3]["service"]
    assert rows[4]["service"].startswith("QLDTraffic")
    assert rows[5]["service"].startswith("Shodan")


def test_each_mapped_status_has_proper_source():
    for r in onboarding.checklist():
        if not r["secret"]:
            continue
        assert isinstance(r["set"], bool), r
        assert r["source"] in VALID_SOURCES, r
        st = r["status"]
        assert isinstance(st, dict), r
        assert st.get("name") == r["secret"] and st.get("source") == r["source"]
        assert bool(st.get("set")) == r["set"]


def test_no_secret_value_in_environment_path():
    name = "SHODAN_API_KEY"
    old = os.environ.get(name)
    os.environ[name] = TEST_VALUE
    try:
        rows = onboarding.checklist()
        blob = json.dumps(rows, ensure_ascii=False, default=str)
        assert TEST_VALUE not in blob, "a secret value leaked into the checklist output"
        row5 = next(r for r in rows if r["n"] == 5)
        assert row5["set"] is True
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


def test_no_secret_value_in_store_path():
    if not creds._dpapi_available():
        print("note  DPAPI unavailable — skipping store-leak check")
        return
    name = "QLDTRAFFIC_API_KEY"
    old = {k: os.environ.get(k) for k in ("WFD_CREDS_BACKEND", "WFD_CREDS_DIR")}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        os.environ["WFD_CREDS_BACKEND"] = "dpapi"
        os.environ["WFD_CREDS_DIR"] = td
        try:
            creds.set(name, TEST_VALUE)
            rows = onboarding.checklist()
            blob = json.dumps(rows, ensure_ascii=False, default=str)
            assert TEST_VALUE not in blob, "a secret value leaked into the checklist output"
            row4 = next(r for r in rows if r["n"] == 4)
            assert row4["set"] is True and row4["source"] == "store", row4
        finally:
            try:
                creds.delete(name)
            except Exception:
                pass
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def test_cli_keys_registration_and_output():
    import argparse
    import contextlib
    import io

    reg = onboarding.cli_commands()
    assert "keys" in reg, reg
    help_text, func = reg["keys"]
    assert isinstance(help_text, str) and help_text and callable(func)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    sp = sub.add_parser("keys")
    extra = getattr(func, "add_arguments", None)
    if callable(extra):
        extra(sp)

    args = parser.parse_args(["keys"])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = func(args)
    out = buf.getvalue()
    assert rc == 0, rc
    assert "Windy" in out, out
    assert "OK (" in out or "KEY REQUIRED" in out, out
    assert "Censys" not in out, "unmapped services are only shown with --all"

    args = parser.parse_args(["keys", "--all"])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = func(args)
    out_all = buf.getvalue()
    assert rc == 0 and "Censys" in out_all, out_all


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
