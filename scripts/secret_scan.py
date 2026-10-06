#!/usr/bin/env python3
"""secret_scan.py - release-gate secret scanner for the world-feed-db repository.

Default: scan every tracked working-tree file ("git ls-files -z"), line-numbered.
--history: additionally scan every blob reachable from any ref ("git rev-list
--objects --all" streamed through one long-lived "git cat-file --batch" process,
deduplicated by blob sha).  Files/blobs larger than --max-bytes (default
8000000) are skipped and counted.  Values are NEVER printed in full: first 4
characters + ellipsis + last 2, or "LEN=N" when too short to mask safely.

Exit codes: 0 = clean, 1 = findings, 2 = operational error.  Stdlib only.

Usage (from the repo root):
    py -3.11 scripts/secret_scan.py [--history] [--json] [--max-bytes N] [--root DIR]

--root DIR scans a plain directory instead of a git repo (test mode; cannot be
combined with --history).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading

VERSION = "1.0.1"
DEFAULT_MAX_BYTES = 8_000_000
_CREATE_NO_WINDOW = 0x08000000  # Windows: never flash a console for git children
_MIN_MASKABLE_LEN = 12          # shorter values print as "LEN=N"
_ELLIPSIS = "\u2026"


def _no_window():
    """subprocess kwargs that keep child processes invisible on Windows."""
    if os.name == "nt":
        return {"creationflags": _CREATE_NO_WINDOW}
    return {}


# Detection patterns: name -> regex source.  Assignment-style patterns capture
# just the secret in a group named "secret"; all other patterns mask the whole
# match.  (generic_assignment is left untuned: no noise observed on real data.)
_PATTERN_SOURCES = [
    ("google_api_key", r"AIza[0-9A-Za-z_\-]{35}"),
    ("aws_access_key_id", r"AKIA[0-9A-Z]{16}"),
    ("aws_secret_access_key",
     r"(?i)aws_secret[a-z_]*\s*[:=]\s*['\"]?(?P<secret>[A-Za-z0-9/+=]{40})"),
    ("github_token", r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    ("slack_token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("slack_webhook", r"https://hooks\.slack\.com/services/[A-Za-z0-9/]{20,}"),
    ("stripe_key", r"[rs]k_(live|test)_[A-Za-z0-9]{20,}"),
    ("twilio_sid", r"SK[0-9a-fA-F]{32}"),
    ("sendgrid_key", r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}"),
    ("discord_webhook",
     r"https://discord(app)?\.com/api/webhooks/[0-9]{15,}/[A-Za-z0-9_\-]{50,}"),
    ("telegram_bot_token", r"[0-9]{8,10}:[A-Za-z0-9_\-]{35}"),
    ("openai_key", r"sk-[A-Za-z0-9]{32,}"),
    ("private_key_block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("jwt", r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"),
    ("generic_assignment",
     r"(?i)\b(api[_-]?key|apikey|secret|token|password|passwd|pwd)\b['\"]?\s*[:=]\s*"
     r"['\"](?P<secret>[A-Za-z0-9_\-+/=.]{20,})['\"]"),
]
PATTERNS = [(name, re.compile(src)) for name, src in _PATTERN_SOURCES]


def mask(value):
    """Mask a secret for display: first 4 + ellipsis + last 2, or LEN=N."""
    if len(value) < _MIN_MASKABLE_LEN:
        return "LEN=%d" % len(value)
    return value[:4] + _ELLIPSIS + value[-2:]


def scan_text(text):
    """Scan decoded text; returns a list of (lineno, name, masked, length)."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line:
            continue
        for name, rx in PATTERNS:
            for m in rx.finditer(line):
                captured = m.groupdict().get("secret")
                raw = captured if captured is not None else m.group(0)
                hits.append((lineno, name, mask(raw), len(raw)))
    return hits


def _scan_file(full_path, rel_path, max_bytes, stats, mode):
    """Scan one file; updates stats and returns finding dicts."""
    findings = []
    try:
        if os.path.getsize(full_path) > max_bytes:
            stats["skipped"] += 1
            return findings
        with open(full_path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        stats["unreadable"] += 1
        print("warning: cannot read %s: %s" % (rel_path, exc), file=sys.stderr)
        return findings
    stats["scanned"] += 1
    for lineno, name, masked, length in scan_text(raw.decode("utf-8", "replace")):
        findings.append({"mode": mode, "path": rel_path, "line": lineno,
                         "pattern": name, "masked": masked, "length": length})
    return findings


def _git(args, cwd):
    """Run a read-only git command and capture its output."""
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          **_no_window())


def find_repo_root(cwd):
    """Return the git toplevel containing cwd, or None."""
    proc = _git(["rev-parse", "--show-toplevel"], cwd)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip() or None


def scan_tree(repo_root, max_bytes):
    """Scan every tracked working-tree file (git ls-files)."""
    proc = _git(["ls-files", "-z"], repo_root)
    if proc.returncode != 0:
        raise RuntimeError("git ls-files failed: "
                           + proc.stderr.decode("utf-8", "replace").strip())
    stats = {"total": 0, "scanned": 0, "skipped": 0, "unreadable": 0}
    findings = []
    entries = [e for e in proc.stdout.split(b"\0") if e]
    stats["total"] = len(entries)
    for raw_path in entries:
        rel = raw_path.decode("utf-8", "replace")
        findings.extend(_scan_file(os.path.join(repo_root, rel), rel,
                                   max_bytes, stats, "tree"))
    return findings, stats


def scan_directory(root, max_bytes):
    """Scan an arbitrary directory (test mode; skips VCS/cache dirs)."""
    skip_dirs = {".git", ".hg", ".svn", "__pycache__", ".venv", "node_modules"}
    stats = {"total": 0, "scanned": 0, "skipped": 0, "unreadable": 0}
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            stats["total"] += 1
            findings.extend(_scan_file(full, rel, max_bytes, stats, "dir"))
    return findings, stats


def _discard(stream, n, chunk=1 << 20):
    """Read and drop n bytes so the cat-file stream stays in sync."""
    while n > 0:
        block = stream.read(min(chunk, n))
        if not block:
            return
        n -= len(block)


def scan_history(repo_root, max_bytes):
    """Scan every blob reachable from any ref, deduplicated by blob sha."""
    proc = _git(["rev-list", "--objects", "--all"], repo_root)
    if proc.returncode != 0:
        raise RuntimeError("git rev-list failed: "
                           + proc.stderr.decode("utf-8", "replace").strip())

    # Map each unique object id to one representative path (first seen).
    sha_path, order = {}, []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(b" ", 1)
        sha = parts[0].decode("ascii", "replace")
        if sha in sha_path:
            continue
        sha_path[sha] = (parts[1].decode("utf-8", "replace")
                         if len(parts) == 2 else None)
        order.append(sha)

    stats = {"objects": len(order), "blobs": 0, "skipped": 0, "missing": 0}
    findings = []

    # One long-lived cat-file process: a feeder thread writes object ids to
    # its stdin while the main thread drains stdout (no pipe deadlock).
    child = subprocess.Popen(["git", "cat-file", "--batch"], cwd=repo_root,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, **_no_window())

    def _feed():
        try:
            for sha in order:
                child.stdin.write(sha.encode("ascii") + b"\n")
            child.stdin.flush()
        except OSError:
            pass
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

    feeder = threading.Thread(target=_feed, name="cat-file-feeder", daemon=True)
    feeder.start()

    out = child.stdout
    while True:
        header = out.readline()
        if not header:
            break
        parts = header.split()
        if len(parts) < 3:
            if len(parts) == 2 and parts[-1] == b"missing":
                stats["missing"] += 1
            continue
        sha = parts[0].decode("ascii", "replace")
        obj_type = parts[1].decode("ascii", "replace")
        try:
            size = int(parts[2])
        except ValueError:
            continue
        # Non-blobs and oversize blobs: consume and discard their content to
        # keep the stream position correct.
        if obj_type != "blob" or size > max_bytes:
            if obj_type == "blob":
                stats["skipped"] += 1
            _discard(out, size)
            out.read(1)  # objects are followed by a single LF
            continue
        raw = out.read(size)
        out.read(1)
        stats["blobs"] += 1
        rep_path = sha_path.get(sha) or "(unknown)"
        for lineno, name, masked, length in scan_text(raw.decode("utf-8", "replace")):
            findings.append({"mode": "history", "sha": sha, "path": rep_path,
                             "line": lineno, "pattern": name, "masked": masked,
                             "length": length})

    feeder.join(timeout=10)
    child.wait()
    return findings, stats


def _finding_line(f):
    if f["mode"] == "history":
        return "history %s %s:%d: %s: %s" % (
            f["sha"], f["path"], f["line"], f["pattern"], f["masked"])
    return "%s:%d: %s: %s" % (f["path"], f["line"], f["pattern"], f["masked"])


def render_text(target, modes, max_bytes, findings, counts, tree_stats, hist_stats):
    lines = ["secret_scan v%s | target: %s" % (VERSION, target),
             "modes: %s | max-bytes: %d" % (", ".join(modes), max_bytes), ""]
    lines.extend(_finding_line(f) for f in findings)
    lines.append("")
    lines.append("summary:")
    hit_counts = sorted(((n, c) for n, c in counts.items() if c),
                        key=lambda kv: (-kv[1], kv[0]))
    if hit_counts:
        for name, n in hit_counts:
            lines.append("  %s: %d" % (name, n))
    else:
        lines.append("  hits by pattern: none (%d patterns checked)" % len(counts))
    tree_n = sum(1 for f in findings if f["mode"] != "history")
    lines.append("  total findings: %d (tree/dir=%d, history=%d)"
                 % (len(findings), tree_n, len(findings) - tree_n))
    lines.append("  files: %d listed, %d scanned, %d skipped (>%d B), %d unreadable"
                 % (tree_stats["total"], tree_stats["scanned"], tree_stats["skipped"],
                    max_bytes, tree_stats["unreadable"]))
    if "history" in modes:
        lines.append("  history: %d objects walked, %d blobs scanned, "
                     "%d blobs skipped (>%d B), %d missing"
                     % (hist_stats["objects"], hist_stats["blobs"],
                        hist_stats["skipped"], max_bytes, hist_stats["missing"]))
    lines.append("  result: %s" % ("CLEAN" if not findings
                                   else "%d FINDING(S)" % len(findings)))
    return "\n".join(lines)


def render_json(target, modes, max_bytes, findings, counts, tree_stats, hist_stats):
    tree_n = sum(1 for f in findings if f["mode"] != "history")
    payload = {
        "tool": "secret_scan", "version": VERSION, "target": target,
        "modes": modes, "max_bytes": max_bytes, "findings": findings,
        "counts_by_pattern": counts,
        "totals": {
            "findings": len(findings), "tree_findings": tree_n,
            "history_findings": len(findings) - tree_n,
            "files_total": tree_stats["total"],
            "files_scanned": tree_stats["scanned"],
            "files_skipped": tree_stats["skipped"],
            "files_unreadable": tree_stats["unreadable"],
            "objects_walked": hist_stats["objects"],
            "blobs_scanned": hist_stats["blobs"],
            "blobs_skipped": hist_stats["skipped"],
            "blobs_missing": hist_stats["missing"],
        },
        "clean": len(findings) == 0,
    }
    return json.dumps(payload, indent=2, ensure_ascii=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="secret_scan.py",
        description="Release-gate secret scanner: tracked tree by default, "
                    "--history for all blobs across every ref.")
    ap.add_argument("--history", action="store_true",
                    help="also scan every blob reachable from any ref "
                         "(git rev-list --objects --all)")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="print machine-readable JSON instead of text")
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES,
                    metavar="N",
                    help="skip files/blobs larger than N bytes "
                         "(default: %(default)s)")
    ap.add_argument("--root", metavar="DIR", default=None,
                    help="scan a plain directory instead of a git repo "
                         "(test mode; no --history)")
    args = ap.parse_args(argv)

    # Emit UTF-8 regardless of console codepage (the mask uses an ellipsis).
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if args.max_bytes < 0:
        print("error: --max-bytes must be >= 0", file=sys.stderr)
        return 2
    if args.root and args.history:
        print("error: --root cannot be combined with --history", file=sys.stderr)
        return 2

    hist_empty = {"objects": 0, "blobs": 0, "skipped": 0, "missing": 0}
    try:
        if args.root:
            target = os.path.abspath(args.root)
            if not os.path.isdir(target):
                print("error: not a directory: %s" % target, file=sys.stderr)
                return 2
            modes = ["dir"]
            tree_findings, tree_stats = scan_directory(target, args.max_bytes)
            hist_findings, hist_stats = [], dict(hist_empty)
        else:
            repo_root = find_repo_root(os.getcwd())
            if repo_root is None:
                print("error: not inside a git repository "
                      "(run from the repo root)", file=sys.stderr)
                return 2
            target = repo_root
            modes = ["tree"]
            tree_findings, tree_stats = scan_tree(repo_root, args.max_bytes)
            hist_findings, hist_stats = [], dict(hist_empty)
            if args.history:
                modes.append("history")
                hist_findings, hist_stats = scan_history(repo_root, args.max_bytes)
    except FileNotFoundError as exc:
        print("error: git not found on PATH: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    findings = tree_findings + hist_findings
    counts = {name: 0 for name, _ in PATTERNS}
    for f in findings:
        counts[f["pattern"]] += 1

    if args.as_json:
        print(render_json(target, modes, args.max_bytes, findings, counts,
                          tree_stats, hist_stats))
    else:
        print(render_text(target, modes, args.max_bytes, findings, counts,
                          tree_stats, hist_stats))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
