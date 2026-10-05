"""wfd.prefs — viewer preference store (favourites + settings).

Backing file: ``data/viewer-prefs.json`` (gitignored with ``data/``). This is
the ONE small read-write store the viewer backend owns; the registry database
itself stays read-only for it. Favourites + settings survive restarts and are
shared across browsers pointed at the same local viewer.

Shape::

    {"favourites": [{"camera_id": "<16hex>", "added_at": "ISO-8601"}],
     "settings": {...free-form viewer settings...},
     "updated_at": "ISO-8601"}

Writes are atomic (tmp + replace) and serialized with a module lock; reads are
tolerant — a missing or corrupt file yields empty defaults, never an exception.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import threading

from . import profile

DATA_DIR = profile.REPO_ROOT / "data"
DEFAULT_PATH = DATA_DIR / "viewer-prefs.json"

MAX_FAVOURITES = 5000
MAX_SETTINGS_JSON = 20000          # serialized bytes cap for the settings dict

_LOCK = threading.Lock()


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


class PrefsStore:
    """Favourites + settings persisted as one JSON file (atomic writes)."""

    def __init__(self, path=None):
        self.path = pathlib.Path(path) if path else DEFAULT_PATH

    # -- reads ---------------------------------------------------------------

    def load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = {}
        except (OSError, ValueError):
            raw = {}
        favourites, seen = [], set()
        for item in raw.get("favourites") or []:
            cid = item.get("camera_id") if isinstance(item, dict) else None
            if isinstance(cid, str) and cid and cid not in seen:
                seen.add(cid)
                favourites.append({"camera_id": cid,
                                   "added_at": str(item.get("added_at") or ""),
                                   "label": str(item.get("label") or "")})
        settings = raw.get("settings")
        if not isinstance(settings, dict):
            settings = {}
        return {"favourites": favourites, "settings": settings,
                "updated_at": str(raw.get("updated_at") or "")}

    def favourite_ids(self) -> list:
        return [f["camera_id"] for f in self.load()["favourites"]]

    # -- writes --------------------------------------------------------------

    def _save(self, data: dict) -> dict:
        data["updated_at"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)
        return data

    def add_favourite(self, camera_id: str) -> dict:
        with _LOCK:
            data = self.load()
            if not any(f["camera_id"] == camera_id for f in data["favourites"]):
                data["favourites"].append({"camera_id": camera_id, "added_at": _now(),
                                           "label": ""})
                if len(data["favourites"]) > MAX_FAVOURITES:
                    data["favourites"] = data["favourites"][-MAX_FAVOURITES:]
                self._save(data)
            return data

    def remove_favourite(self, camera_id: str) -> dict:
        with _LOCK:
            data = self.load()
            kept = [f for f in data["favourites"] if f["camera_id"] != camera_id]
            if len(kept) != len(data["favourites"]):
                data["favourites"] = kept
                self._save(data)
            return data

    def update_label(self, camera_id: str, label: str) -> dict:
        """Set (or clear, with "") the custom label on a favourite."""
        label = str(label or "").strip()[:80]
        with _LOCK:
            data = self.load()
            for fav in data["favourites"]:
                if fav["camera_id"] == camera_id:
                    fav["label"] = label
                    self._save(data)
                    break
            return data

    def reorder_favourites(self, order: list) -> dict:
        """Reorder favourites to match ``order`` (unknown ids ignored; the
        unlisted remainder keeps its relative order after the listed ones)."""
        wanted = [str(i) for i in order if isinstance(i, str)]
        with _LOCK:
            data = self.load()
            index = {f["camera_id"]: f for f in data["favourites"]}
            reordered = [index.pop(cid) for cid in wanted if cid in index]
            reordered.extend(index.values())
            if len(reordered) == len(data["favourites"]):
                data["favourites"] = reordered
                self._save(data)
            return data

    def update_settings(self, patch: dict) -> dict:
        if not isinstance(patch, dict) or not patch:
            raise ValueError("settings patch must be a non-empty object")
        with _LOCK:
            data = self.load()
            data["settings"].update(patch)
            # cap total size by evicting oldest keys (insertion order) if needed
            while len(json.dumps(data["settings"])) > MAX_SETTINGS_JSON and data["settings"]:
                data["settings"].pop(next(iter(data["settings"])))
            self._save(data)
            return data


def default_store() -> PrefsStore:
    return PrefsStore()
