"""wfd.onboarding — account/key checklist parsed from ACCOUNTS-AND-KEYS.md (build task A).

The repo-root document is the living owner checklist: numbered services with
Unlocks / Signup / Status cells. :func:`checklist` parses it and merges live
secret status for the services that map to a secret name, using
:func:`wfd.profile.secret_status` — status-only, so a value can never leak
into the checklist (``set`` + ``source`` only).

Mapping (services 6-12 are informational only, no secret):
  1 -> WINDY_API_KEY       2 -> ROAD511_API_KEY
  3 -> NSW_API_KEY         4 -> QLDTRAFFIC_API_KEY
  5 -> SHODAN_API_KEY
"""
from __future__ import annotations

import pathlib
import re

from . import profile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "ACCOUNTS-AND-KEYS.md"

# service number -> secret name (6-12 intentionally unmapped)
SECRET_MAP = {
    1: "WINDY_API_KEY",
    2: "ROAD511_API_KEY",
    3: "NSW_API_KEY",
    4: "QLDTRAFFIC_API_KEY",
    5: "SHODAN_API_KEY",
}

_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _clean(text: str) -> str:
    return " ".join(text.split())


def _service_label(cell: str) -> str:
    """Bold name when present ('**Windy Webcams API** (free tier)'), otherwise
    the cell text up to its first parenthesis ('Shodan (free API plan)' ->
    'Shodan')."""
    cell = _clean(cell)
    match = _BOLD_RE.search(cell)
    if match:
        return match.group(1).strip()
    head = cell.split("(", 1)[0].strip(" *")
    return head or cell


def _parse_doc(path=None) -> list:
    """Parse every ``| N |`` service row from the checklist document."""
    doc = pathlib.Path(path) if path else DOC_PATH
    rows = []
    for line in doc.read_text(encoding="utf-8").splitlines():
        match = _ROW_RE.match(line)
        if not match:
            continue
        cells = _cells(line)
        rows.append({
            "n": int(match.group(1)),
            "service": _service_label(cells[1]) if len(cells) > 1 else "",
            "unlocks": _clean(cells[2]) if len(cells) > 2 else "",
            "signup": _clean(cells[3]) if len(cells) > 3 else "",
            "status_text": _clean(cells[4]) if len(cells) > 4 else "",
        })
    rows.sort(key=lambda r: r["n"])
    return rows


def checklist() -> list:
    """Rows for every service in ACCOUNTS-AND-KEYS.md.

    Shape: ``{n, service, unlocks, signup, status_text, secret, set, source,
    status}``. Mapped services (1-5) carry live status — ``set``/``source``
    flattened from :func:`wfd.profile.secret_status` plus the full status dict
    under ``status`` — never a value. Unmapped services get ``secret=None``,
    ``set=None``, ``source=None``.
    """
    out = []
    for row in _parse_doc():
        item = dict(row)
        secret_name = SECRET_MAP.get(row["n"])
        item["secret"] = secret_name
        if secret_name:
            st = profile.secret_status(secret_name)
            item["status"] = st
            item["set"] = bool(st.get("set"))
            item["source"] = st.get("source") or "none"
        else:
            item["status"] = None
            item["set"] = None
            item["source"] = None
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# CLI extension (registered by wfd.cli)
# ---------------------------------------------------------------------------

def _cmd_keys(args) -> int:
    show_all = bool(getattr(args, "all", False))
    print("world-feed-db — accounts & keys (status only; values are never printed)")
    for r in checklist():
        if r["secret"]:
            if r["set"]:
                print(f"  {r['n']}. {r['service']} — OK ({r['source']})")
            else:
                print(f"  {r['n']}. {r['service']} — MISSING — "
                      f"{profile.key_required_state(r['service'])}")
        elif show_all:
            print(f"  {r['n']}. {r['service']} — optional / not used by the build")
    return 0


def _add_keys_arguments(parser) -> None:
    parser.add_argument("--all", action="store_true",
                        help="also list unmapped/optional services (6-12)")


_cmd_keys.add_arguments = _add_keys_arguments


def cli_commands() -> dict:
    """CLI extension hook (see wfd.cli): registers ``wfd keys``."""
    return {"keys": ("accounts & key checklist from ACCOUNTS-AND-KEYS.md", _cmd_keys)}
