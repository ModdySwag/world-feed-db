"""wfd.ingest.gov — government enumerator scaffold + exemplars (build task C).

Usage::

    py -3.11 -m wfd.ingest.gov <caltrans|deldot|nsw|all>

Runs the named enumerator(s), writes ``data/ingest/gov-<name>.jsonl``
(gitignored) and prints a report. Enumeration never claims liveness — see
``wfd/ingest/gov/base.py``.

Registry: ``ENUMERATORS`` maps name -> singleton Enumerator instance.
"""
from __future__ import annotations

import sys

from .base import Enumerator, format_result, get, register, registry, run_one
from .caltrans import CaltransEnumerator
from .deldot import DeldotEnumerator
from .nsw import NswEnumerator

ENUMERATORS: dict = {}
for _enumerator in (CaltransEnumerator(), DeldotEnumerator(), NswEnumerator()):
    register(_enumerator)
    ENUMERATORS[_enumerator.name] = _enumerator


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    target = args[0] if args else "all"

    if target == "all":
        names = list(ENUMERATORS)
    elif target in ENUMERATORS:
        names = [target]
    else:
        print(f"unknown enumerator {target!r}; known: {', '.join(ENUMERATORS)} (or 'all')")
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
