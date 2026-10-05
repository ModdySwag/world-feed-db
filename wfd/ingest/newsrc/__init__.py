"""wfd.ingest.newsrc — new-source family enumerators (build unit NS).

Each family module exposes a module-level ``ENUMERATOR``; this package
auto-discovers them (``_``-prefixed files are skipped), so a new family module
registers itself by landing in this directory.

Usage::

    py -3.11 -m wfd.ingest.newsrc            # list registered families
    py -3.11 -m wfd.ingest.newsrc <family>   # run one family
    py -3.11 -m wfd.ingest.newsrc all        # run all registered families

Conventions + output contract: see docs/ARCHITECTURE.md ("wfd.ingest.newsrc").
"""
from __future__ import annotations

import importlib
import pkgutil
import sys

from .base import Enumerator, format_result, register, registry, run_one

_FAILED: dict = {}


def _discover() -> None:
    for mod in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if mod.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"{__name__}.{mod.name}")
        except Exception as exc:  # noqa: BLE001 — one broken module must not kill the package
            _FAILED[mod.name] = f"{type(exc).__name__}: {exc}"
            continue
        enumerator = getattr(module, "ENUMERATOR", None)
        if enumerator is not None and getattr(enumerator, "name", ""):
            register(enumerator)


_discover()

ENUMERATORS = registry()


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    target = args[0] if args else ""

    for name, err in sorted(_FAILED.items()):
        print(f"WARN  module {name} failed to import: {err}")

    if not target or target == "list":
        print("registered families:")
        for name, enum in sorted(ENUMERATORS.items()):
            print(f"  {name:24s} provenance={enum.provenance}  source={enum.source_ref[:80]}")
        if not ENUMERATORS:
            print("  (none)")
        return 0 if not _FAILED else 1

    if target == "all":
        names = sorted(ENUMERATORS)
    elif target in ENUMERATORS:
        names = [target]
    else:
        print(f"unknown family {target!r}; registered: {', '.join(sorted(ENUMERATORS))} "
              f"(or 'all'/'list')")
        return 2

    exit_code = 0
    for name in names:
        try:
            result = run_one(ENUMERATORS[name], save=True)
        except Exception as exc:  # noqa: BLE001 — report the failure, keep going
            print(f"[{name}] FAIL: {type(exc).__name__}: {exc}")
            exit_code = 1
            continue
        print(format_result(result))
        print()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
