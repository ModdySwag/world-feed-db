"""wfd.cli — command line entry point.

Run from the repo root:   py -3.11 -m wfd <command>
(or:                      py -3.11 -m wfd status)

Commands register here plus any optional extension module that exposes
``cli_commands() -> {name: (help_text, func)}`` (e.g. wfd.creds, wfd.onboarding).
An extension command's func may carry an ``add_arguments(parser)`` attribute
to declare its own flags.
"""
from __future__ import annotations

import argparse
import importlib

from . import profile

KNOWN_KEYS = (
    ("WINDY_API_KEY", "Windy Webcams API"),
    ("SHODAN_API_KEY", "Shodan (search-only)"),
    ("ROAD511_API_KEY", "Road511"),
    ("NSW_API_KEY", "Transport for NSW Open Data"),
    ("QLDTRAFFIC_API_KEY", "QLDTraffic"),
)


def cmd_status(args: argparse.Namespace) -> int:
    print("world-feed-db — status")
    print(f"  repo:    {profile.REPO_ROOT}")
    print(f"  profile: {profile.active_profile()}")
    conf = profile.settings()
    surface = "ON (private build)" if conf.get("private_exposure_surface") else "off"
    print(f"  exposure surface: {surface}")
    print("  keys (status only — values are never printed):")
    for name, service in KNOWN_KEYS:
        st = profile.secret_status(name)
        state = f"OK ({st['source']})" if st["set"] else "MISSING"
        print(f"    {name:<22} {state:<20} [{service}]")
    db_path = profile.REPO_ROOT / "data" / "worldfeed.db"
    if db_path.exists():
        from . import db as dbmod
        conn = dbmod.connect(db_path)
        print(f"  db:      {db_path}")
        print(f"           {dbmod.counts(conn)}")
    else:
        print(f"  db:      {db_path} (not created yet)")
    return 0


def main(argv=None) -> int:
    commands = {
        "status": ("profile, key statuses, and db summary", cmd_status),
    }
    for modname in ("wfd.creds", "wfd.onboarding", "wfd.registry", "wfd.health"):
        try:
            mod = importlib.import_module(modname)
        except ImportError:
            continue
        reg = getattr(mod, "cli_commands", None)
        if callable(reg):
            commands.update(reg())

    parser = argparse.ArgumentParser(prog="wfd", description="world-feed-db")
    sub = parser.add_subparsers(dest="command")
    for name, (help_text, func) in commands.items():
        sp = sub.add_parser(name, help=help_text)
        extra = getattr(func, "add_arguments", None)
        if callable(extra):
            extra(sp)
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    return commands[args.command][1](args)


if __name__ == "__main__":
    raise SystemExit(main())
