#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cold-clone release test for world-feed-db — proves a stranger can clone and
use the repo keyless (public-beta release gate).

Run from the repo root:

    py -3.11 scripts/cold_clone_test.py

Steps:
  [1] git clone C:/Users/user/world-feed-db -> <scratch>/wfd-cold-test-<ts>   [hard]
  [2] assert profiles/ACTIVE absent + profiles/clean/ present in the clone     [hard]
      (a fresh clone has no ACTIVE pointer, so it must default to 'clean')
  [3] `py -3.11 -m wfd status` and `py -3.11 -m wfd keys` in the clone with   [hard]
      WFD_PROFILE stripped -> expect rc=0, honest output, no traceback
      (outputs captured verbatim in this log)
  [4] run EVERY tests/test_*.py in the clone with py -3.11 -> PASS/FAIL table  [finding]
      plus traceback tails for failures. data/ and profiles/moddy are
      gitignored => ABSENT in a clone; any suite failing because of that is a
      recorded FINDING (nothing is fixed; the source repo is never touched).
  [5] boot `py -3.11 -m wfd viewer --port 8797` (8798/8799 if busy), poll      [hard]
      http://127.0.0.1:<port>/api/stats until a definitive answer (~20 s
      timeout): HTTP 200, or the honest HTTP 503 `registry database not found`
      that a db-less clone legitimately serves. Capture the first ~200 bytes,
      then terminate ONLY that child process tree (py.exe launcher ->
      python.exe) via taskkill /T on its PID.
  [6] informational: count/list tracked files in the clone containing the
      string 'Users\\user' (case-insensitive).
  [7] final PASS/FAIL summary; exit non-zero if any HARD step failed.

Cleanup: full success (no hard failure, no suite failure) -> the temp clone is
deleted. Anything failed -> the clone is KEPT and its path printed.

Exit code: 0 = all hard steps passed; 1 = at least one hard step failed.
(Test-suite failures are recorded as FINDINGS per spec and do not flip the rc;
they do, however, keep the clone so the evidence survives.)

Owner rules honored: every subprocess spawns with CREATE_NO_WINDOW (never a
visible console); the source repo is only ever READ (git clone / rev-parse /
grep); the viewer child is killed via taskkill /T on exactly the process tree
this script started; the owner's viewer port 8773 is never touched (candidates
are 8797/8798/8799 only). Stdlib only. This test reflects the HEAD that was
cloned at run time — re-run it after any further release commits.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime

SRC_REPO = "C:/Users/user/world-feed-db"
SCRATCH = r"C:\Users\user\AppData\Local\hermes\profiles\deepseek\cache\scratch"
PORTS = [8797, 8798, 8799]          # never 8773 (owner's live viewer)
PY = "py"
PY_VER = "-3.11"
NO_WINDOW = 0x08000000              # CREATE_NO_WINDOW — owner rule
CLONE_TIMEOUT_S = 300
CLI_TIMEOUT_S = 120
TEST_TIMEOUT_S = 240
VIEWER_POLL_S = 20.0
KEY_ENV_NAMES = ["WINDY_API_KEY", "SHODAN_API_KEY", "ROAD511_API_KEY",
                 "NSW_API_KEY", "QLDTRAFFIC_API_KEY"]

STEPS: list = []        # dict(name, hard, ok, detail)
FINDINGS: list = []     # strings
_LIVE: list = []        # live child processes, cleaned up on ANY exit path


def log(line: str = "") -> None:
    print(line, flush=True)


def _cf() -> int:
    return NO_WINDOW if os.name == "nt" else 0


def fwd(p: str) -> str:
    return p.replace("\\", "/")


def record(name: str, hard: bool, ok: bool, detail: str = "") -> None:
    STEPS.append({"name": name, "hard": hard, "ok": bool(ok), "detail": detail})
    log(f"    -> {'PASS' if ok else 'FAIL'}  [{name}] {detail}")


def kill_tree(pid: int):
    """Kill a process AND its children (the py.exe launcher spawns python.exe).

    Returns taskkill's return code on Windows (None if it could not run)."""
    if os.name == "nt":
        try:
            res = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                 capture_output=True, creationflags=_cf(), timeout=30)
            return res.returncode
        except Exception:
            return None
    else:
        try:
            os.kill(pid, 9)
            return True
        except OSError:
            return None


def run_cmd(cmd, cwd=None, env=None, timeout=120):
    """Run a command. Returns (rc|None, stdout, stderr, timed_out).

    A timeout kills the whole process tree (py.exe -> python.exe)."""
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace",
                            creationflags=_cf())
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out or "", err or "", False
    except subprocess.TimeoutExpired:
        kill_tree(proc.pid)
        try:
            out, err = proc.communicate(timeout=15)
        except Exception:
            out, err = "", ""
        return None, out or "", err or "", True


def port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def port_open(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def http_get(url: str, timeout: float = 2.0):
    """GET -> (status|None, body<=400 bytes). status None = no HTTP response."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read(400)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(400)
        except Exception:
            body = b""
        return exc.code, body
    except Exception:
        return None, b""


def main() -> int:
    log("=" * 72)
    log("world-feed-db — COLD CLONE RELEASE TEST (keyless gate)")
    log(f"  script:  {os.path.abspath(__file__)}")
    log(f"  repo:    {SRC_REPO}")
    log(f"  scratch: {SCRATCH}")
    log(f"  python:  {sys.version.split()[0]} via launcher '{PY} {PY_VER}'")
    log("=" * 72)

    if not shutil.which("git"):
        log("FATAL: git not found on PATH")
        return 1
    if not shutil.which(PY):
        log(f"FATAL: '{PY}' launcher not found on PATH")
        return 1
    if not (os.path.isdir(os.path.join(SRC_REPO, "wfd"))
            and os.path.isdir(os.path.join(SRC_REPO, "tests"))):
        log(f"FATAL: {SRC_REPO} does not look like the world-feed-db repo")
        return 1

    rc, out, err, _ = run_cmd(["git", "-C", fwd(SRC_REPO), "rev-parse", "HEAD"], timeout=30)
    src_head = out.strip().splitlines()[0] if rc == 0 and out.strip() else ""
    log(f"  source HEAD: {src_head or '(unknown!)'}")

    # ---------------------------------------------------------------- [1] clone
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(SCRATCH, exist_ok=True)
    clone_dir = os.path.join(SCRATCH, f"wfd-cold-test-{run_id}")
    n = 0
    while os.path.exists(clone_dir):
        n += 1
        clone_dir = os.path.join(SCRATCH, f"wfd-cold-test-{run_id}-r{n}")
    logs_dir = clone_dir + ".logs"

    log("")
    log(f"[1] fresh clone -> {clone_dir}")
    log(f"    $ git clone {SRC_REPO} {clone_dir}")
    rc, out, err, timed = run_cmd(["git", "clone", SRC_REPO, clone_dir],
                                  cwd=SCRATCH, timeout=CLONE_TIMEOUT_S)
    clone_ok = (rc == 0 and not timed)
    clone_head = ""
    if clone_ok:
        rc2, out2, _, _ = run_cmd(["git", "-C", fwd(clone_dir), "rev-parse", "HEAD"],
                                  timeout=30)
        clone_head = out2.strip().splitlines()[0] if rc2 == 0 else ""
        record("clone", True, True, f"rc=0; HEAD={clone_head} (source match={clone_head == src_head})")
        if clone_head != src_head:
            FINDINGS.append(f"clone HEAD {clone_head} != source HEAD {src_head} "
                            "(concurrent commit mid-clone?)")
    else:
        record("clone", True, False, f"rc={rc}{' TIMEOUT' if timed else ''}")
        if err.strip():
            log("    stderr tail:")
            for ln in err.strip().splitlines()[-8:]:
                log("      | " + ln)

    child_env = None
    test_files: list = []
    suites_failed: list = []

    # -------------------------------------------------- [2] profile defaults
    if clone_ok:
        log("")
        log("[2] fresh-clone profile defaults")
        active = os.path.join(clone_dir, "profiles", "ACTIVE")
        clean = os.path.join(clone_dir, "profiles", "clean")
        active_absent = not os.path.exists(active)
        clean_ok = os.path.isdir(clean)
        settings_ok = os.path.isfile(os.path.join(clean, "settings.json"))
        detail = (f"profiles/ACTIVE {'absent OK' if active_absent else 'PRESENT (bad!)'}; "
                  f"profiles/clean/ {'present' if clean_ok else 'MISSING'}; "
                  f"clean/settings.json {'present' if settings_ok else 'missing'}")
        record("profiles-default", True, active_absent and clean_ok, detail)
        if not (active_absent and clean_ok):
            FINDINGS.append("fresh clone profile defaults wrong: " + detail)

    # ------------------------------------------------- [3] keyless CLI checks
    if clone_ok:
        child_env = os.environ.copy()
        had_profile = "WFD_PROFILE" in child_env
        child_env.pop("WFD_PROFILE", None)
        child_env["PYTHONIOENCODING"] = "utf-8"   # capture fidelity only
        key_env_present = [k for k in KEY_ENV_NAMES if child_env.get(k)]

        log("")
        log("[3] keyless CLI in the clone (WFD_PROFILE stripped from child env)")
        log(f"    WFD_PROFILE set in invoking shell env: {had_profile} (stripped for all children)")
        if key_env_present:
            log(f"    note: key env vars present in invoking env (NAMES only): {', '.join(key_env_present)}")

        for label, tailargs in (("status", ["-m", "wfd", "status"]),
                                ("keys", ["-m", "wfd", "keys"])):
            log("")
            log(f"    $ {PY} {PY_VER} {' '.join(tailargs)}    (cwd={clone_dir})")
            rc, out, err, timed = run_cmd([PY, PY_VER] + tailargs, cwd=clone_dir,
                                          env=child_env, timeout=CLI_TIMEOUT_S)
            combined = out + err
            no_tb = "traceback" not in combined.lower()
            ok = (not timed) and rc == 0 and no_tb
            extra = ""
            if label == "status":
                pline = ""
                for ln in out.splitlines():
                    if "profile:" in ln:
                        pline = ln.split("profile:", 1)[1].strip()
                        break
                extra = f"profile={pline or '?'}"
                if pline != "clean":
                    ok = False
                    FINDINGS.append(f"`wfd status` reports profile {pline!r} (expected 'clean')")
            log(f"      rc={rc}{'  TIMEOUT' if timed else ''}  no-traceback={no_tb}" +
                (f"  {extra}" if extra else ""))
            log("      --- stdout ---")
            for ln in (out.rstrip().splitlines() or [""]):
                log("      | " + ln)
            if err.strip():
                log("      --- stderr ---")
                for ln in err.rstrip().splitlines():
                    log("      | " + ln)
            record(f"wfd {label}", True, ok,
                   f"rc={rc}, no-traceback={no_tb}" + (f", {extra}" if extra else ""))

    # ---------------------------------------------------- [4] test suites
    if clone_ok:
        log("")
        log("[4] test suites (plain runners; data/ + profiles/moddy ABSENT in a clone)")
        test_files = sorted(glob.glob(os.path.join(clone_dir, "tests", "test_*.py")))
        log(f"    discovered {len(test_files)} test file(s) under tests/")
        os.makedirs(logs_dir, exist_ok=True)
        rows = []
        for tf in test_files:
            name = os.path.basename(tf)
            rel = f"tests/{name}"
            t0 = time.time()
            rc, out, err, timed = run_cmd([PY, PY_VER, rel], cwd=clone_dir,
                                          env=child_env, timeout=TEST_TIMEOUT_S)
            took = time.time() - t0
            combined = out + err
            try:
                with open(os.path.join(logs_dir, name + ".log"), "w",
                          encoding="utf-8", errors="replace") as lf:
                    lf.write(f"$ py -3.11 {rel}    (cwd={clone_dir})\n"
                             f"rc={rc}{' TIMEOUT' if timed else ''}  took={took:.1f}s\n"
                             f"===== stdout =====\n{out}\n===== stderr =====\n{err}\n")
            except OSError:
                pass
            verdict = "PASS" if (not timed and rc == 0) else "FAIL"
            counts = ""
            for ln in reversed(combined.splitlines()):
                m = re.search(r"(\d+)\s*/\s*(\d+)\s+passed", ln)
                if m:
                    counts = f"{m.group(1)}/{m.group(2)} passed"
                    break
            rows.append((name, rc, verdict, took, counts, combined))
            if verdict == "FAIL":
                suites_failed.append((name, rc, combined))

        log("")
        log("    PASS/FAIL table:")
        log(f"      {'SUITE':<37} {'RC':>4}  {'RESULT':<6} {'TIME':>7}  COUNT")
        for name, rc, verdict, took, counts, _ in rows:
            rc_s = "TO" if rc is None else str(rc)
            log(f"      {name:<37} {rc_s:>4}  {verdict:<6} {took:>6.1f}s  {counts}")

        if suites_failed:
            log("")
            log("    failure tails:")
            for name, rc, combined in suites_failed:
                log(f"    --- {name} (rc={rc}) ---")
                all_lines = [l for l in combined.splitlines() if l.strip()]
                sel = [l for l in all_lines if re.match(r"\s*FAIL\b", l)][:20]
                idx = combined.rfind("Traceback")
                if idx != -1:
                    sub = [l for l in combined[idx:].splitlines() if l.strip()][:25]
                else:
                    sub = all_lines[-5:]
                if sel and sub:
                    sel.append("        ...")
                for l in sub:
                    if l not in sel:
                        sel.append(l)
                for ln in sel:
                    log("      | " + ln)
                low = combined.lower()
                hint = ""
                if any(s in low for s in ("worldfeed.db", "no such table",
                                          "registry database not found",
                                          "not found", "does not exist", "missing",
                                          "no such file")):
                    hint = (" [likely missing pre-existing data: data/ + profiles/moddy "
                            "are gitignored, absent in a clone]")
                FINDINGS.append(f"suite {name}: FAIL rc={rc}{hint}")

        data_dir = os.path.join(clone_dir, "data")
        log("")
        if os.path.isdir(data_dir):
            entries = []
            for root, _dirs, files in os.walk(data_dir):
                for f in files:
                    entries.append(os.path.relpath(os.path.join(root, f), clone_dir))
            log(f"    note: clone data/ exists after tests ({len(entries)} file(s)); first few:")
            for e in entries[:10]:
                log("      " + e)
        else:
            log("    note: clone data/ does not exist after tests")
        log(f"    note: data/worldfeed.db exists: "
            f"{os.path.exists(os.path.join(data_dir, 'worldfeed.db'))}")

        n_pass = len(test_files) - len(suites_failed)
        record("test suites", False, not suites_failed,
               f"{n_pass}/{len(test_files)} passed ({len(suites_failed)} finding(s))")

    # ------------------------------------------------------- [5] viewer boot
    if clone_ok:
        log("")
        log("[5] viewer boot in the clone (no db, no data/ — honest JSON required)")
        viewer = {"port": None, "status": None, "statuses": [], "body": b"",
                  "boot_log": "", "attempts": []}
        boot_txt = ""
        for cand in PORTS:
            if not port_free(cand):
                viewer["attempts"].append(f"{cand}:busy")
                log(f"    port {cand}: busy — trying next")
                continue
            log("")
            log(f"    $ {PY} {PY_VER} -m wfd viewer --port {cand}    (cwd={clone_dir})")
            logpath = os.path.join(clone_dir, f"viewer-boot-{cand}.log")
            lf = open(logpath, "w", encoding="utf-8", errors="replace")
            proc = subprocess.Popen([PY, PY_VER, "-m", "wfd", "viewer", "--port", str(cand)],
                                    cwd=clone_dir, env=child_env, stdin=subprocess.DEVNULL,
                                    stdout=lf, stderr=subprocess.STDOUT,
                                    creationflags=_cf())
            _LIVE.append(proc)
            url = f"http://127.0.0.1:{cand}/api/stats"
            deadline = time.monotonic() + VIEWER_POLL_S
            statuses, first_body, last = [], b"", (None, b"")
            while True:
                if proc.poll() is not None and not statuses:
                    break                                   # died before answering
                st, body = http_get(url)
                if st is not None:
                    if not statuses:
                        first_body = body
                    last = (st, body)
                    statuses.append(st)
                    if st == 200:
                        break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.5)
            viewer.update({"port": cand, "status": last[0], "statuses": statuses,
                           "body": first_body or last[1], "boot_log": logpath})
            if statuses:
                break                                       # definitive answer (200 or not)
            if proc.poll() is None:
                kill_tree(proc.pid)                         # alive but silent — retry next port
                try:
                    proc.wait(timeout=10)
                except Exception:
                    pass
            time.sleep(0.3)

        # -- terminate ONLY the child tree this script started -----------------
        proc = _LIVE[-1] if _LIVE else None
        killed_rc = None
        kill_rc = None
        if proc is not None:
            if proc.poll() is None:
                kill_rc = kill_tree(proc.pid)
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
            killed_rc = proc.returncode
        port = viewer["port"]
        released = None
        if port:
            released = False
            for _ in range(24):
                if not port_open(port):
                    released = True
                    break
                time.sleep(0.25)
        if viewer["boot_log"]:
            try:
                with open(viewer["boot_log"], encoding="utf-8", errors="replace") as fh:
                    boot_txt = fh.read()
            except OSError:
                pass

        log("")
        attempt_note = "; ".join(viewer["attempts"]) or "(none busy)"
        log(f"    port attempts: {attempt_note}; chosen port={port}")
        if boot_txt.strip():
            log("    viewer boot log (first 12 lines):")
            for ln in boot_txt.strip().splitlines()[:12]:
                log("      | " + ln)
        st = viewer["status"]
        if viewer["statuses"]:
            uniq = sorted(set(viewer["statuses"]))
            log(f"    /api/stats poll ({VIEWER_POLL_S:.0f}s): {len(viewer['statuses'])} "
                f"response(s), statuses={uniq} (final={st})")
            log(f"    first ~200 bytes: {viewer['body'][:200].decode('utf-8', 'replace')!r}")
        else:
            log("    /api/stats: no HTTP response within timeout")
        log(f"    kill: taskkill /PID {proc.pid if proc else '?'} /T /F "
            f"(taskkill rc={kill_rc}); child exit code={killed_rc} (killed); "
            f"port {port} released={released}")

        body_txt = viewer['body'][:200].decode('utf-8', 'replace')
        honest_503 = (st == 503 and '"registry database not found"' in body_txt)
        ok = (st == 200) or honest_503
        if ok and honest_503:
            detail = (f"HTTP 503, honest 'registry database not found' — the expected "
                      f"db-less-clone answer — on port {port}; body={body_txt!r}")
        elif ok:
            detail = (f"HTTP 200 on port {port}; body={body_txt!r}")
        elif viewer["statuses"]:
            detail = (f"booted on port {port} but /api/stats answered HTTP {st} "
                      f"(unexpected); body={body_txt!r}")
            FINDINGS.append(
                f"viewer cold-boot: /api/stats returned HTTP {sorted(set(viewer['statuses']))} "
                f"(unexpected — a db-less clone should answer the honest 503) "
                f"({body_txt!r})")
        else:
            tail = " / ".join(boot_txt.strip().splitlines()[-4:]) or "(empty)"
            detail = f"no /api/stats response (attempts={attempt_note}; boot log tail: {tail})"
            FINDINGS.append(f"viewer cold-boot: no HTTP response within timeout ({attempt_note})")
        record("viewer boot", True, ok, detail)

    # ------------------------------------------------- [6] 'Users\\user' scan
    if clone_ok:
        log("")
        log("[6] informational: tracked files containing 'Users\\user' (case-insensitive)")
        rc, out, err, _ = run_cmd(["git", "-C", fwd(clone_dir), "grep", "-l", "-i", "-F",
                                   "--", "Users\\user"], timeout=60)
        files = [l.strip() for l in out.splitlines() if l.strip()]
        log(f"    matches: {len(files)} tracked file(s)")
        for f in files[:15]:
            log("      " + f)
        if len(files) > 15:
            log(f"      ... and {len(files) - 15} more")
        if rc not in (0, 1):
            log(f"    note: git grep rc={rc}; stderr={err.strip()[:200]}")
        rc2, out2, _, _ = run_cmd(["git", "-C", fwd(clone_dir), "grep", "-l", "-i", "-F",
                                   "--", "Users/user"], timeout=60)
        fw = [l.strip() for l in out2.splitlines() if l.strip()]
        log(f"    (extra info) forward-slash variant 'Users/user': {len(fw)} tracked file(s)")
        if files:
            FINDINGS.append(f"{len(files)} tracked file(s) contain 'Users\\user' "
                            f"(owner-path leak; e.g. {', '.join(files[:5])})")

    # ----------------------------------------------------------- [7] summary
    log("")
    log("=" * 72)
    log("SUMMARY")
    hard_fail = [s for s in STEPS if s["hard"] and not s["ok"]]
    log(f"  clone dir:   {clone_dir}" + ("" if clone_ok else "  (clone FAILED)"))
    log(f"  source HEAD: {src_head}   clone HEAD: {clone_head or '(clone failed)'}")
    log("  STEP RESULTS:")
    for s in STEPS:
        tag = "hard" if s["hard"] else "find"
        log(f"    [{tag:<4}] {'PASS' if s['ok'] else 'FAIL'}  {s['name']}  {s['detail']}")
    if clone_ok:
        total = len(test_files)
        n_pass = total - len(suites_failed)
        log(f"  TEST SUITES: {total} run / {n_pass} passed / {len(suites_failed)} failed")
    if FINDINGS:
        log(f"  FINDINGS ({len(FINDINGS)}):")
        for f in FINDINGS:
            log(f"    - {f}")
    else:
        log("  FINDINGS: none")

    full_success = clone_ok and not hard_fail and not suites_failed
    if full_success:
        log("  cleanup: full success -> deleting temp clone")
        try:
            shutil.rmtree(clone_dir)
            if os.path.isdir(logs_dir):
                shutil.rmtree(logs_dir)
            log(f"  cleanup: deleted {clone_dir}")
        except Exception as exc:  # noqa: BLE001
            log(f"  cleanup: could not fully delete {clone_dir} ({exc}) — left in place")
            full_success = False
    else:
        log(f"  cleanup: KEPT for inspection -> {clone_dir}")
        if os.path.isdir(logs_dir):
            log(f"           run logs            -> {logs_dir}")

    exit_code = 1 if hard_fail else 0
    verdict = "FAIL" if hard_fail else ("PASS (with suite findings)" if suites_failed else "PASS")
    log("")
    log(f"FINAL: {verdict}  (hard failures: {len(hard_fail)}; "
        f"suite failures: {len(suites_failed)}"
        + ("; suite failures are FINDINGS per spec" if suites_failed else "")
        + f")  EXIT={exit_code}")
    log("=" * 72)
    return exit_code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass
    code = 1
    try:
        code = main()
    except Exception:
        log("FATAL: unhandled exception in cold_clone_test.py")
        log(traceback.format_exc())
        code = 1
    finally:
        for _p in _LIVE:
            try:
                if _p.poll() is None:
                    kill_tree(_p.pid)
            except Exception:
                pass
    raise SystemExit(code)
