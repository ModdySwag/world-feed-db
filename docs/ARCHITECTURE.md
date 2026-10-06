# world-feed-db — architecture & build contracts (v0.1 · 2026-10-05)

The contract layer for the build phase. Read this before writing any module here.
PLAN.md holds the program decisions; this file holds the engineering contracts.

## Layout

| Path | What | Git |
|---|---|---|
| `wfd/` | the package (clean template — publishable) | committed |
| `wfd/schema.py` | CameraRow, Provenance/Health/Protocol enums, URL redaction | committed |
| `wfd/profile.py` | profile resolution + settings + secret access | committed |
| `wfd/creds.py` | secure credential store (build task A) | committed |
| `wfd/onboarding.py` | account checklist from ACCOUNTS-AND-KEYS.md (task A) | committed |
| `wfd/db.py` | SQLite + FTS5 registry | committed |
| `wfd/ingest/base.py` | IngestResult + polite HTTP helpers | committed |
| `wfd/ingest/exposure.py` | insecam-class dataset ingesters (task B) | committed |
| `wfd/ingest/les.py` | Live-Environment-Streams ingester (task C) | committed |
| `wfd/ingest/gov/` | government enumerator scaffold + exemplars (task C) | committed |
| `wfd/cli.py` | `py -3.11 -m wfd <cmd>` entry point | committed |
| `wfd/registry.py` | registry DB build + stats/search CLI (`wfd db ...`) | committed |
| `docs/` | this file | committed |
| `tests/` | plain-python test runners (+ fixtures) | committed |
| `profiles/clean/` | keyless default profile | committed |
| `profiles/<overlay>/` | private overlay (keys, curation) | **gitignored** |
| `profiles/ACTIVE` | active-profile pointer (personal) | **gitignored** |
| `data/` | registry DB + ingest outputs | **gitignored** |
| `research/exposed/raw/` | raw third-party dataset downloads | **gitignored** |
| `research/` | wave evidence + corpora (as committed) | mixed |

## Vocabulary — hard rules

- `provenance`: `public_by_design` | `aggregator_directory` (third-party directory
  of public feeds — owner decision 2026-10-06) | `exposure_aggregator` | `unknown`.
- `status`: `live` | `stale` | `dead` | `unknown` (+ `unverified` for exposure rows;
  `quarantined`/`retired` for lifecycle). **Enumeration NEVER claims liveness** —
  rows enter as `unknown`; only health checks may produce `live`/`stale`/`dead`.
- Exposure laws (D6, S5 §B): `snapshot_date` required; `status="unverified"`;
  `geo_confidence="low"`; credentials redacted at parse time (via
  `wfd.schema.redact_url`, counted in `was_redacted`); **never probe listed devices**;
  never fetch `/en/view/` pages or device URLs — datasets are static files only.

## Module contracts

### wfd.schema
- `CameraRow` dataclass — the ONE row shape; add data via `meta`/`tags`, never new ad-hoc dicts.
- `stable_id(source_family, url)` → 16-hex id; same family+url ⇒ same id (upsert-safe).
- `redact_url(url) -> (redacted_url, was_redacted)` — strips `user:pass@` userinfo and
  scrubs sensitive query params (`u`, `p`, `pass`, `password`, `token`, `key`, `sig`, …).
  Only rebuilds the URL when something changed. `redact_and_flag()` returns the third
  value `credential_present`.

### wfd.profile
- `active_profile()` — `WFD_PROFILE` env → `profiles/ACTIVE` → `"clean"`.
- `settings()` — defaults + `clean/settings.json` + `<active>/settings.json`.
  Keys: `private_exposure_surface` (bool), `min_request_interval_s`, `http_timeout_s`, `user_agent`.
- `secret(name)` — store → `<active>/.env` → environment. **Never print/log the value.**
- `secret_status(name)` → `{name, set, source}` — the ONLY display-safe view.
- `key_required_state(service)` → `"UNAVAILABLE · KEY REQUIRED · <service>"`.

### wfd.creds (build task A)
- `get(name) -> str | None`, `set(name, value)`, `delete(name) -> bool` (store-only operations).
- `backend_info() -> str` (which backend is live), `store_name(name) -> str`.
- Backends in order: OS keyring (`keyring` 25.x installed) → Windows DPAPI file
  (`profiles/<active>/secrets.dpapi`, ctypes client) → last-resort plaintext JSON with a
  loud warning (never the default on this host).
- Optional `cli_commands() -> {name: (help, func)}` for `wfd` CLI registration.
- Every function must be safe to call when nothing is configured.

### wfd.onboarding (build task A)
- `checklist() -> list[dict]` — parse `ACCOUNTS-AND-KEYS.md` service rows (n, service,
  unlocks, signup) + live status via `profile.secret_status` for the mapped secret names.
- `cli_commands()` — e.g. a `keys` command that prints the checklist with
  `OK (source)` / `MISSING — KEY REQUIRED` states.

### wfd.db
- `connect(path=None)` (default `data/worldfeed.db`, WAL) · `init_db(conn)` ·
  `upsert(conn, row)` / `upsert_many(conn, rows)` (idempotent via `camera_id`, FTS kept in sync) ·
  `counts(conn)` · `get(conn, camera_id)` · `search(conn, q, limit)` (FTS5).

### wfd.ingest.base
- `IngestResult(family, provenance, snapshot_date, source_ref)` with `.add(row)`,
  `.finalize()` (fills `stats`: rows, redacted, by_status, by_country).
- `polite_get(url, headers=…)` — UA + per-host spacing (default ≥1 s) + bounded retries
  (network errors / 5xx retried; 4xx raised immediately). `polite_json()` on top.
- `write_jsonl(path, rows)`, `tally(values)`, `today_iso()`, `clean_str`, `clean_float`.

### wfd.ingest.exposure (build task B)
- One parser per dataset era; all produce `provenance="exposure_aggregator"` rows.
- Redaction BEFORE anything is stored/logged; count `was_redacted`.
- Datasets: jrw TSV (2019-02-21, local), GODEYE JSON (2026-05-27), rafasapiens
  JSON/CSV (2026-10). Era-chain diff helper for added/removed analysis.
- Outputs: `data/ingest/exposure-<era>.jsonl` + `data/ingest/manifest.json`.

### wfd.ingest.les + wfd.ingest.gov (build task C)
- `les.py` — parse `research/seed-tabs/data/LES-streams.geojson` → rows
  (`source_family="les"`). L-E-S "active" = HTTP-200 CI only → do NOT carry it as
  `live`; map conservatively (status `unknown`, original flags into `meta`).
- `gov/base.py` — `Enumerator` interface (`name`, `provenance`, `enumerate() -> IngestResult`)
  + registry of implemented enumerators. Exemplars: `caltrans.py`, `deldot.py` (keyless
  JSON), `nsw.py` (key-gated: key from `profile.secret("NSW_API_KEY")`; missing ⇒ honest
  `key_required_state` result, no crash), `qld.py` (key-gated, key **in the URL**
  query per QLDTraffic spec v1.10; token scrubbed from any error text).

### wfd.ingest.newsrc (build unit NS — new-source families)
- One module per family under `wfd/ingest/newsrc/`, each exposing a module-level
  `ENUMERATOR` and runnable directly: `py -3.11 -m wfd.ingest.newsrc.<family>`
  (package runner `<family|all|list>` — modules auto-register on import).
- Provenance by family: `explore-omega` / `jungfrau-roundshot` /
  `vailresorts-brownrice` = `public_by_design`; `openwebcamdb` (third-party
  directory) = `aggregator_directory` (operator/credit preserved in `meta`).
- `newsrc/base.py` mirrors `gov/base.py` (`Enumerator`, liveness guard, `run_one`
  → `data/ingest/newsrc-<name>.jsonl` + sha256 stats) and adds `FetchCache`
  (per-family cache under `data/ingest/cache/<family>/`; re-runs skip cached
  fetches, `--refresh` refetches) + `run_cli` for module `__main__`s — long
  enumerations are resumable. Optional `--limit` caps items (tests/debug).
- Enumeration never claims liveness (rows enter `status="unknown"`; published
  flags stay in `meta`). Health sweeps are probe-eligible for
  `public_by_design` + `aggregator_directory` rows.

### wfd.cli
- `py -3.11 -m wfd status` — profile + key statuses + db summary.
- Extension pattern: modules `wfd.creds`, `wfd.onboarding` — `cli_commands()` dict;
  funcs may declare `add_arguments(parser)`.

### wfd.registry
- `load_jsonl_file(conn, path)` / `load_dir(conn, dir)` — idempotent load of `data/ingest/*.jsonl`
  (upsert by `camera_id`; tolerant of bad lines and unknown keys).
- `stats(conn)` — totals + family split + top countries + cross-family URL overlaps.
- `search(conn, q, limit)` — FTS hits enriched with provenance/status/protocol.
- CLI: `wfd db load [--reset] | stats | search <q>`.

## Conventions

- Python: `py -3.11` (3.11.9 on this host). **Stdlib-first**; installed extras
  available when useful: `keyring`, `requests`, `beautifulsoup4`, `lxml`, `pillow`,
  `numpy`, `cryptography`, `pywin32`. **No pytest** — tests are plain runners:
  each `tests/test_*.py` runs standalone, prints `PASS`/`FAIL` lines, exits non-zero
  on failure, and stays pytest-compatible (functions named `test_*`).
- Shell: MSYS bash (`cd <repo>` …); native tools get
  `C:/forward/slash` paths. Run everything from the repo root.
- Polite fetch: ≥1 s spacing per host by default; identifiable UA; bounded retries;
  respect 429/Retry-After. Agency/directory lanes only — **no device contact, ever**
  (exposure rows especially).
- Datasets: raw downloads → `research/exposed/raw/` (gitignored); normalized
  outputs → `data/ingest/` (gitignored); record source URL + sha256 + counts in
  `data/ingest/manifest.json` and note them in `research/exposed/README.md`.
- Secrets: never in code, chat, logs, tests, or fixtures. In code use
  `wfd.profile.secret()`; in reports use `secret_status()` only. Fixtures must not
  contain real credentials (synthesize redaction test inputs).
- **Subagent build tasks never run git** — the parent commits.
- If a shared contract seems wrong/missing: do NOT edit core files; work around it
  and note it in your report.
