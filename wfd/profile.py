"""wfd.profile — profile resolution + settings/secrets access (D7.1).

Two artifacts, one codebase:
- ``clean`` — the keyless template profile that ships with the repo.
- overlay profiles (e.g. ``moddy``) — private; keys + curation; gitignored.

Active profile resolution order:
  1. ``WFD_PROFILE`` environment variable
  2. ``profiles/ACTIVE`` pointer file (personal convenience; absent in a fresh clone)
  3. ``"clean"``

Secret resolution order (per name):
  1. the wfd.creds store (OS keyring / DPAPI file — the app's settings surface)
  2. ``profiles/<active>/.env`` file
  3. process environment

Secrets are returned to calling code only — NEVER print or log a secret value.
Use :func:`secret_status` for anything that gets displayed.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILES_DIR = REPO_ROOT / "profiles"
DEFAULT_PROFILE = "clean"

_SETTINGS_DEFAULTS: dict = {
    "private_exposure_surface": False,   # Q9: private build first — overlays turn this on
    "min_request_interval_s": 1.0,       # polite-fetch spacing default (per host)
    "http_timeout_s": 25,
    "user_agent": "world-feed-db/0.1 (personal research)",
}


def active_profile() -> str:
    env = os.environ.get("WFD_PROFILE", "").strip()
    if env:
        return env
    pointer = PROFILES_DIR / "ACTIVE"
    if pointer.exists():
        try:
            name = pointer.read_text(encoding="utf-8").strip()
        except OSError:
            name = ""
        if name:
            return name
    return DEFAULT_PROFILE


def profile_dir(name: Optional[str] = None) -> pathlib.Path:
    return PROFILES_DIR / (name or active_profile())


def settings() -> dict:
    """Defaults + clean overlay + active-profile overlay (later wins)."""
    out = dict(_SETTINGS_DEFAULTS)
    seen = set()
    for pname in ("clean", active_profile()):
        if pname in seen:
            continue
        seen.add(pname)
        f = PROFILES_DIR / pname / "settings.json"
        if f.exists():
            try:
                out.update(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass
    return out


def _store_get(name: str) -> Optional[str]:
    """Optional wfd.creds store lookup (module may not exist yet)."""
    try:
        from . import creds  # type: ignore
    except ImportError:
        return None
    try:
        return creds.get(name)
    except Exception:
        return None


def _env_file_get(name: str) -> Optional[str]:
    f = profile_dir() / ".env"
    if not f.exists():
        return None
    try:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == name:
                v = v.strip().strip('"').strip("'")
                return v or None
    except OSError:
        return None
    return None


def secret(name: str) -> Optional[str]:
    """Resolve a secret by name — value for CALLING CODE only; never print it."""
    v = _store_get(name)
    if v:
        return v
    v = _env_file_get(name)
    if v:
        return v
    v = os.environ.get(name)
    if v:
        return v
    return None


def secret_status(name: str) -> dict:
    """Status-only view of a secret — safe to print."""
    if _store_get(name):
        return {"name": name, "set": True, "source": "store"}
    if _env_file_get(name):
        return {"name": name, "set": True, "source": "env_file"}
    if os.environ.get(name):
        return {"name": name, "set": True, "source": "environment"}
    return {"name": name, "set": False, "source": "none"}


def key_required_state(service: str) -> str:
    """The honest display state for a key-gated source without its credential."""
    return f"UNAVAILABLE · KEY REQUIRED · {service}"
