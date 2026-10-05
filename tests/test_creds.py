"""wfd.creds tests — plain-python runner (this host has no pytest).

Run:    py -3.11 tests/test_creds.py

Every value here is fake ("test-value-123"). The file backends are redirected
to a temp dir through the documented test hooks (``WFD_CREDS_BACKEND`` +
``WFD_CREDS_DIR``) and the process environment is restored afterwards, so the
real profile store is never touched. The DPAPI roundtrip runs for real on this
Windows host (ctypes CryptProtectData) and cleans up after itself; the keyring
probe degrades gracefully when the OS backend errors.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd import creds, profile

TEST_VALUE = "test-value-123"


@contextlib.contextmanager
def _backend(name, store_dir):
    """Force a backend + store dir for the block; restore env afterwards."""
    env = {"WFD_CREDS_BACKEND": name, "WFD_CREDS_DIR": str(store_dir)}
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def _auto_backend():
    """Clear the forcing env vars so automatic selection is exercised."""
    old = {k: os.environ.pop(k, None) for k in ("WFD_CREDS_BACKEND", "WFD_CREDS_DIR")}
    try:
        yield
    finally:
        for k, v in old.items():
            if v is not None:
                os.environ[k] = v


def _tmpdir():
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


def test_store_name_prefix():
    assert creds.store_name("WFD_TEST_X") == "world-feed-db:WFD_TEST_X"


def test_default_store_path_follows_profile_dir():
    with _auto_backend():
        assert creds._dpapi_path() == profile.profile_dir() / "secrets.dpapi"
        assert creds._file_path() == profile.profile_dir() / "secrets.json"


def test_get_missing_is_none_and_delete_missing_is_false():
    if not creds._dpapi_available():
        print("note  DPAPI unavailable on this host — skipping")
        return
    with _tmpdir() as td, _backend("dpapi", td):
        assert creds.get("WFD_TEST_MISSING") is None
        assert creds.delete("WFD_TEST_MISSING") is False


def test_dpapi_roundtrip_and_cleanup():
    if not creds._dpapi_available():
        print("note  DPAPI unavailable on this host — skipping")
        return
    name = "WFD_TEST_DPAPI_KEY"
    with _tmpdir() as td, _backend("dpapi", td):
        assert creds.get(name) is None                 # get-missing -> None
        assert creds.delete(name) is False             # delete-missing -> False
        creds.set(name, TEST_VALUE)
        assert creds.get(name) == TEST_VALUE
        blob_path = pathlib.Path(td) / "secrets.dpapi"
        assert blob_path.exists(), "DPAPI store file should exist"
        blob = blob_path.read_bytes()
        assert TEST_VALUE.encode() not in blob, "plaintext leaked into DPAPI file"
        assert TEST_VALUE.encode("utf-16-le") not in blob
        assert name.encode() not in blob
        assert creds.delete(name) is True              # set -> delete -> gone
        assert creds.get(name) is None
        assert creds.delete(name) is False             # cleaned up


def test_set_empty_value_clears():
    if not creds._dpapi_available():
        print("note  DPAPI unavailable on this host — skipping")
        return
    name = "WFD_TEST_EMPTY_KEY"
    with _tmpdir() as td, _backend("dpapi", td):
        creds.set(name, TEST_VALUE)
        assert creds.get(name) == TEST_VALUE
        creds.set(name, "")            # documented: empty means delete
        assert creds.get(name) is None


def test_file_backend_warns_loudly_and_roundtrips():
    name = "WFD_TEST_FILE_KEY"
    with _tmpdir() as td, _backend("file", td):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert creds.get(name) is None
        assert "WARNING" in err.getvalue(), "plaintext backend must warn on load"
        with contextlib.redirect_stderr(io.StringIO()):
            creds.set(name, TEST_VALUE)
            assert creds.get(name) == TEST_VALUE
            on_disk = json.loads((pathlib.Path(td) / "secrets.json").read_text(encoding="utf-8"))
            assert on_disk.get(creds.store_name(name)) == TEST_VALUE
            assert creds.delete(name) is True
            assert creds.get(name) is None
        info = creds.backend_info()
        assert "plaintext-file" in info and "WARNING" in info, info


def test_auto_backend_never_plaintext_on_windows():
    if os.name != "nt":
        print(f"note  os.name={os.name!r} — plaintext-default guard is Windows-specific")
        return
    with _auto_backend():
        picked = creds._active_backend_name()
    assert picked in ("keyring", "dpapi"), f"plaintext must never be the auto default: {picked}"


def test_auto_backend_falls_back_when_keyring_unusable():
    original = creds._keyring_usable
    creds._keyring_usable = lambda: False          # simulate a broken keyring backend
    try:
        with _auto_backend():
            picked = creds._active_backend_name()
    finally:
        creds._keyring_usable = original
    expected = "dpapi" if creds._dpapi_available() else "file"
    assert picked == expected, picked


def test_keyring_roundtrip_or_graceful_fallback():
    if not creds._keyring_usable():
        print("note  keyring backend not usable — auto-selection falls back (graceful skip)")
        return
    name = "WFD_TEST_KEYRING_KEY"
    with _tmpdir() as td, _backend("keyring", td):
        try:
            creds.delete(name)
        except Exception:
            pass
        try:
            creds.set(name, TEST_VALUE)
        except Exception as exc:  # backend came up broken mid-flight
            print(f"note  keyring backend errored on write ({type(exc).__name__}) "
                  f"— falling back (graceful skip)")
            return
        try:
            assert creds.get(name) == TEST_VALUE
            assert creds.delete(name) is True
        finally:
            try:
                creds.delete(name)
            except Exception:
                pass
        assert creds.get(name) is None


def test_backend_info_reports_active_backend():
    with _tmpdir() as td, _backend("dpapi", td):
        info = creds.backend_info()
        assert info.startswith("dpapi-file ("), info
        assert "secrets.dpapi" in info, info
    with _tmpdir() as td, _backend("file", td):
        with contextlib.redirect_stderr(io.StringIO()):
            info = creds.backend_info()
        assert "plaintext-file" in info and "WARNING" in info, info
    if creds._keyring_usable():
        with _tmpdir() as td, _backend("keyring", td):
            info = creds.backend_info()
            assert info.startswith("keyring ("), info
            if sys.platform == "win32":
                assert "Windows Credential Locker" in info, info


def test_get_safe_with_unconfigured_store():
    if not creds._dpapi_available():
        print("note  DPAPI unavailable on this host — skipping")
        return
    with _tmpdir() as td:
        fresh = os.path.join(td, "not-created-yet")
        with _backend("dpapi", fresh):
            assert creds.get("WFD_TEST_NOTHING") is None
            assert creds.delete("WFD_TEST_NOTHING") is False
            assert not pathlib.Path(fresh).exists(), "a bare lookup must not create the store"


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
