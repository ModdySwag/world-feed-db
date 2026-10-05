"""wfd.creds — the secure credential store for world-feed-db (build task A).

One API, three backends; the active backend is resolved on every call (so
tests can flip it with an environment variable):

1. ``keyring`` — the OS keychain. On this Windows host: the *Windows
   Credential Locker* (WinVaultKeyring). Entries use keyring service
   ``world-feed-db`` and username ``<NAME>``.
2. ``dpapi`` — a Windows-DPAPI-encrypted JSON blob at
   ``profiles/<active>/secrets.dpapi`` (ctypes CryptProtectData /
   CryptUnprotectData — stdlib only, no shell-outs). Decryptable only by the
   current Windows user on this machine.
3. ``file`` — PLAINTEXT JSON at ``profiles/<active>/secrets.json``. Last
   resort only: it prints a loud ``WARNING`` to stderr on every load, and on
   this host it is never selected automatically.

Selection: ``WFD_CREDS_BACKEND=keyring|dpapi|file`` forces a backend (intended
for tests); otherwise the first *available* backend wins in the order above.

Test hook (documented): ``WFD_CREDS_DIR`` redirects the two file backends to
another directory, so tests never touch a real profile store.

Hard rules: a secret value is never printed, logged, or embedded in an
exception. Every function is safe when nothing is configured (``get`` returns
None). ``set(name, "")`` means "clear" — the entry is deleted, never stored as
an empty string (see :func:`set`).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
from typing import Optional

from . import profile

STORE_SERVICE = "world-feed-db"       # keyring service name
STORE_PREFIX = "world-feed-db:"       # file-store key prefix (see store_name)
_BACKEND_ENV = "WFD_CREDS_BACKEND"    # keyring | dpapi | file
_DIR_ENV = "WFD_CREDS_DIR"            # test hook: redirect the file backends
_DPAPI_FILE = "secrets.dpapi"
_PLAINTEXT_FILE = "secrets.json"
_DPAPI_ENTROPY = b"world-feed-db"     # app-bound DPAPI entropy
_CRYPTPROTECT_UI_FORBIDDEN = 0x01
_KNOWN_BACKENDS = ("keyring", "dpapi", "file")

_LOCK = threading.Lock()              # serializes file-backed read-modify-write


class CredsError(RuntimeError):
    """Credential-store failure. Never carries a secret value."""


def store_name(name: str) -> str:
    """Qualified store entry name, e.g. ``world-feed-db:WINDY_API_KEY``."""
    return f"{STORE_PREFIX}{name}"


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

def _store_dir() -> pathlib.Path:
    override = os.environ.get(_DIR_ENV, "").strip()
    if override:
        return pathlib.Path(override)
    return profile.profile_dir()


def _dpapi_path() -> pathlib.Path:
    return _store_dir() / _DPAPI_FILE


def _file_path() -> pathlib.Path:
    return _store_dir() / _PLAINTEXT_FILE


def _display_path(path: pathlib.Path) -> str:
    try:
        return path.resolve().relative_to(profile.REPO_ROOT).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


# ---------------------------------------------------------------------------
# backend availability / selection
# ---------------------------------------------------------------------------

def _keyring_mod():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def _keyring_usable() -> bool:
    kr_mod = _keyring_mod()
    if kr_mod is None:
        return False
    try:
        kr = kr_mod.get_keyring()
    except Exception:
        return False
    if kr is None:
        return False
    module = getattr(type(kr), "__module__", "") or ""
    if module.endswith(".fail") or module.endswith(".null"):
        return False
    return True


def _keyring_kind() -> str:
    kr_mod = _keyring_mod()
    if kr_mod is None:
        return "unavailable"
    try:
        kr = kr_mod.get_keyring()
    except Exception:
        return "unavailable"
    cls = type(kr).__name__
    return {
        "WinVaultKeyring": "Windows Credential Locker",
        "macOSKeyring": "macOS Keychain",
        "SecretServiceKeyring": "Secret Service",
        "KWalletKeyring": "KWallet",
    }.get(cls, cls or "unknown")


def _dpapi_available() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        return hasattr(ctypes, "windll")
    except Exception:
        return False


def _forced_backend() -> Optional[str]:
    value = os.environ.get(_BACKEND_ENV, "").strip().lower()
    if not value:
        return None
    if value not in _KNOWN_BACKENDS:
        print(
            f"wfd.creds warning: unknown {_BACKEND_ENV}={value!r} "
            f"(expected one of {', '.join(_KNOWN_BACKENDS)}) — using automatic selection",
            file=sys.stderr,
        )
        return None
    return value


def _active_backend_name() -> str:
    forced = _forced_backend()
    if forced:
        return forced
    if _keyring_usable():
        return "keyring"
    if _dpapi_available():
        return "dpapi"
    return "file"


def backend_info() -> str:
    """Human-readable description of the backend that is live right now."""
    backend = _active_backend_name()
    if backend == "keyring":
        return f"keyring ({_keyring_kind()})"
    if backend == "dpapi":
        return f"dpapi-file ({_display_path(_dpapi_path())})"
    return f"plaintext-file (WARNING) — {_display_path(_file_path())}"


# ---------------------------------------------------------------------------
# keyring backend
# ---------------------------------------------------------------------------

def _keyring_get(name: str) -> Optional[str]:
    kr_mod = _keyring_mod()
    if kr_mod is None:
        return None
    try:
        return kr_mod.get_password(STORE_SERVICE, name) or None
    except Exception:
        return None


def _keyring_set(name: str, value: str) -> None:
    kr_mod = _keyring_mod()
    if kr_mod is None:
        raise CredsError("keyring backend is not available")
    try:
        kr_mod.set_password(STORE_SERVICE, name, value)
    except Exception:
        raise CredsError(f"keyring write failed for {name}") from None


def _keyring_delete(name: str) -> bool:
    kr_mod = _keyring_mod()
    if kr_mod is None:
        raise CredsError("keyring backend is not available")
    try:
        kr_mod.delete_password(STORE_SERVICE, name)
        return True
    except Exception as exc:
        try:
            from keyring import errors as kr_errors  # type: ignore
            if isinstance(exc, kr_errors.PasswordDeleteError):
                return False
        except Exception:
            pass
        raise CredsError(f"keyring delete failed for {name}") from None


# ---------------------------------------------------------------------------
# DPAPI (ctypes, stdlib only)
# ---------------------------------------------------------------------------

def _dpapi_crypt(data: bytes, decrypt: bool = False) -> bytes:
    """Run bytes through CryptProtectData[] / CryptUnprotectData[]. No shell-outs."""
    if not _dpapi_available():
        raise CredsError("DPAPI is not available on this host")
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = (("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char)))

    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
    except Exception:
        raise CredsError("DPAPI is not available on this host") from None

    payload = bytes(data)
    in_buf = ctypes.create_string_buffer(payload)  # + NUL; cbData below is exact
    in_blob = _Blob(len(payload), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    ent_buf = ctypes.create_string_buffer(_DPAPI_ENTROPY)
    ent_blob = _Blob(len(_DPAPI_ENTROPY),
                     ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _Blob()

    func = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    func.argtypes = (ctypes.POINTER(_Blob),    # pDataIn
                     ctypes.c_void_p,          # szDataDescr / ppszDataDescr (out)
                     ctypes.POINTER(_Blob),    # pOptionalEntropy
                     ctypes.c_void_p,          # pvReserved
                     ctypes.c_void_p,          # pPromptStruct
                     wintypes.DWORD,           # dwFlags
                     ctypes.POINTER(_Blob))    # pDataOut
    func.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel32.LocalFree.restype = ctypes.c_void_p

    ok = func(ctypes.byref(in_blob), None, ctypes.byref(ent_blob), None, None,
              _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob))
    if not ok:
        raise CredsError("DPAPI %s failed" % ("decrypt" if decrypt else "encrypt"))
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


# ---------------------------------------------------------------------------
# file-backed stores (dpapi blob / plaintext JSON)
# ---------------------------------------------------------------------------

def _atomic_write(path: pathlib.Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)


def _dpapi_load() -> dict:
    path = _dpapi_path()
    if not path.exists():
        return {}
    try:
        plain = _dpapi_crypt(path.read_bytes(), decrypt=True)
        data = json.loads(plain.decode("utf-8"))
    except CredsError:
        raise
    except Exception:
        raise CredsError(f"credential store unreadable: {_display_path(path)}") from None
    return data if isinstance(data, dict) else {}


def _dpapi_save(data: dict) -> None:
    blob = _dpapi_crypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    _atomic_write(_dpapi_path(), blob)


def _warn_plaintext(action: str) -> None:
    print(
        f"wfd.creds WARNING: using the PLAINTEXT file backend "
        f"({_display_path(_file_path())}) for {action} — secrets are NOT encrypted.",
        file=sys.stderr,
    )


def _file_load() -> dict:
    _warn_plaintext("load")
    path = _file_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise CredsError(f"credential store unreadable: {_display_path(path)}") from None
    return data if isinstance(data, dict) else {}


def _file_save(data: dict) -> None:
    _warn_plaintext("save")
    path = _file_path()
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def get(name: str) -> Optional[str]:
    """Return the stored value for ``name``, or None if it is not set.

    Never raises for store problems (including "nothing is configured") — a
    caller just sees None, which is exactly how :func:`wfd.profile.secret`
    treats an absent credential.
    """
    try:
        backend = _active_backend_name()
        if backend == "keyring":
            return _keyring_get(name)
        data = _dpapi_load() if backend == "dpapi" else _file_load()
    except Exception:
        return None
    value = data.get(store_name(name))
    return value if value else None


def set(name: str, value: str) -> None:
    """Store ``value`` under ``name`` (replacing any previous value).

    ``set(name, "")`` means **clear**: the entry is deleted (empty strings are
    never stored). Raises TypeError for non-string values and CredsError if
    the active backend fails. Values never appear in exception messages.
    """
    if not isinstance(value, str):
        raise TypeError(
            "credential value must be a string (got %s)" % type(value).__name__
        )
    if value == "":
        delete(name)
        return
    backend = _active_backend_name()
    if backend == "keyring":
        _keyring_set(name, value)
        return
    with _LOCK:
        data = _dpapi_load() if backend == "dpapi" else _file_load()
        data[store_name(name)] = value
        (_dpapi_save if backend == "dpapi" else _file_save)(data)


def delete(name: str) -> bool:
    """Remove ``name``. True if something was stored, False if it was not."""
    backend = _active_backend_name()
    if backend == "keyring":
        return _keyring_delete(name)
    with _LOCK:
        data = _dpapi_load() if backend == "dpapi" else _file_load()
        if store_name(name) not in data:
            return False
        del data[store_name(name)]
        (_dpapi_save if backend == "dpapi" else _file_save)(data)
    return True


def list_stored() -> Optional[list]:
    """Names currently stored, or None when the active backend cannot enumerate.

    The OS keyring has no portable enumeration API, so ``keyring`` returns
    None; the file backends list their keys (status-only — never values).
    """
    backend = _active_backend_name()
    if backend == "keyring":
        return None
    data = _dpapi_load() if backend == "dpapi" else _file_load()
    return sorted(k[len(STORE_PREFIX):] for k in data if k.startswith(STORE_PREFIX))


# ---------------------------------------------------------------------------
# CLI extension (registered by wfd.cli)
# ---------------------------------------------------------------------------

def _known_key_names() -> list:
    """Best-effort: the CLI's known key names (lazy import to avoid cycles)."""
    try:
        from .cli import KNOWN_KEYS  # type: ignore
        return [n for n, _ in KNOWN_KEYS]
    except Exception:
        return []


def _cmd_creds(args) -> int:
    action = getattr(args, "creds_action", None)
    if action is None:
        print("usage: wfd creds {list|status|get|set|delete} ...")
        print("  values are NEVER printed; `set` reads the value hidden "
              "(or via --from-env VAR)")
        return 2

    if action in ("status", "get"):
        stored = get(args.name) is not None
        print(f"{args.name}: {'stored' if stored else 'not set'} "
              f"(backend: {backend_info()})")
        return 0

    if action == "set":
        if getattr(args, "from_env", None):
            value = os.environ.get(args.from_env)
            if value is None:
                print(f"environment variable {args.from_env!r} is not set",
                      file=sys.stderr)
                return 2
        else:
            try:
                if sys.stdin is not None and sys.stdin.isatty():
                    import getpass
                    value = getpass.getpass(f"value for {args.name} (hidden): ")
                elif sys.stdin is not None:
                    value = sys.stdin.readline().rstrip("\r\n")
                else:
                    value = ""
            except Exception:
                print("failed to read the value from input", file=sys.stderr)
                return 2
        if not value:
            existed = delete(args.name)
            print(f"empty value supplied — {args.name}: "
                  f"{'cleared' if existed else 'nothing stored'}")
            return 0
        try:
            set(args.name, value)
        except CredsError as exc:
            print(f"store error: {exc}", file=sys.stderr)
            return 1
        print(f"{args.name}: stored via {backend_info()}")
        return 0

    if action == "delete":
        try:
            ok = delete(args.name)
        except CredsError as exc:
            print(f"store error: {exc}", file=sys.stderr)
            return 1
        print(f"{args.name}: {'deleted' if ok else 'not found'}")
        return 0

    # list
    names = list(getattr(args, "names", None) or [])
    if not names:
        names = _known_key_names()
        try:
            extra = list_stored() or []
        except CredsError:
            extra = []
        for n in extra:
            if n not in names:
                names.append(n)
    print(f"backend: {backend_info()}")
    if not names:
        print("  (nothing to list — pass explicit names: wfd creds list NAME ...)")
        return 0
    print("  status only — values are never printed:")
    for n in names:
        print(f"  {n:<24} {'stored' if get(n) is not None else 'not set'}")
    return 0


def _add_creds_arguments(parser) -> None:
    sub = parser.add_subparsers(dest="creds_action")
    p = sub.add_parser("list", help="backend + stored/not-set status (values never printed)")
    p.add_argument("names", nargs="*",
                   help="secret names to check (default: known keys + store entries)")
    p = sub.add_parser("status", help="status of one secret (values never printed)")
    p.add_argument("name")
    p = sub.add_parser("get", help="alias of status — values are NEVER printed")
    p.add_argument("name")
    p = sub.add_parser("set", help="store a secret (input hidden; empty input clears)")
    p.add_argument("name")
    p.add_argument("--from-env", dest="from_env", metavar="VAR",
                   help="read the value from environment variable VAR instead of stdin")
    p = sub.add_parser("delete", help="remove a stored secret")
    p.add_argument("name")


_cmd_creds.add_arguments = _add_creds_arguments


def cli_commands() -> dict:
    """CLI extension hook (see wfd.cli): registers ``wfd creds``."""
    return {"creds": ("secure credential store (values are never printed)", _cmd_creds)}
