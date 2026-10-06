# New-sources research wave NS1–NS4 — SYNTHESIS (START HERE for the next build)

- **When:** 2026-10-06 02:55–03:25 (4 subagents, 2 delegation units; parent-verified).
- **What:** camera sites collected in a Brave browser session (14 sites + leads), researched for programmatically enumerable public feeds.
- **Method:** every feed claim live-fetched by the child (HTTP status + content-type + bytes; HLS via playlist + TS-segment proofs); the parent re-fetched a sample from every dossier (all pass). Children wrote their dossier BEFORE their final calls; two children were flagged "failed" on trailing DeepSeek 429s — their files were complete (files are the truth, not status flags).
- **Dossiers:** `NS1-directories.md` · `NS2-au-institutional.md` · `NS3-resorts.md` · `NS4-nature-misc.md` (this directory).

## Verdict table (ranked build menu)

| # | Family (suggested) | Site | Scale | Feeds | Enumeration path | Verdict |
|---|---|---|---|---|---|---|
| 1 | `explore-omega` | explore.org/livecams | 101 groups / ≈239 feeds | YouTube lives + stills | `omega.explore.org/api/initial?contenttype=livecams` + per-group snapshots JSON | ADD NOW |
| 2 | `openwebcamdb` | openwebcamdb.com | ≈1,882 cams | YouTube embeds | `/sitemap.xml` → per-page JSON-LD (`contentUrl`) | ADD NOW |
| 3 | `jungfrau-roundshot` | jungfrau.ch/en-gb/live/webcams | 10 cams | Roundshot JPEGs | `cp-api/webcams/?site=en` → `backend.roundshot.com/cams/<id>/full` (302→storage2) + `/status` batch API | ADD NOW |
| 4 | `vailresorts-brownrice` | Whistler Blackcomb (+Vail) | 8 + 5 verified | Brownrice snapshot JPEG (+HLS) | `player.brownrice.com/snapshot/<station>`; stations from rendered cams pages | ADD NOW |
| 5 | `aus-airservices` | weathercams.airservicesaustralia.com | 39 airports | JPEG | `admin-ajax.php` action=get_airports_list → per-airport `wp-content/uploads/airports/<icao>/<icao>_<angle>.jpg` | ADD NOW |
| 6 | `streamdays` | Edinburgh Zoo (+other zoos) | 6 cams (5 live) | HLS (token chain) | `live.streamdays.com/<code>` w/ Referer → iframe → `takeoff.jetstre.am` → jetstre CDN chunklist → .ts | ADD NOW |
| 7 | `skaping` | Grouse Mountain (+877 vendor pages) | 9 cams (4 Skaping + 5 Ozolio→LATER) | S3 JPEG + live thumbnails | `skaping.com/sitemap.players.xml`; latest = page `og:image` → `skaping.s3.gra.io.cloud.ovh.net/<group>/<slug>/YYYY/MM/DD/large/HH-MM.jpg` | ADD NOW |
| 8 | `youtube-live-cams` | Steamboat + South Padre Island | 13 | YouTube lives | Channel/embed video_ids; `oembed` for existence, channel live-tab for liveness | ADD NOW |
| 9 | `au-goldcoast-beach` | goldcoast.qld.gov.au | 27 beaches / 21 streams | HLS | `mobileapp.goldcoast.qld.gov.au/v2/discover?categories=beaches` (JSON) | ADD NOW* |
| 10 | `au-nsw-marine` | nsw.gov.au marine webcams | 21 | HLS widgets | hub → `widget.coastalcoms.com/video/<uuid>` → m3u8 | ADD NOW* |
| 11 | `webcamtaxi` | webcamtaxi.com | ≈2,230 cams | YouTube embeds | all-cams listing `/en/webcams.html` → detail pages → embed + `Source:` attribution | ADD NOW |
| 12 | `camsecure-webcams` | camsecure.co.uk demo index | 30 feeds | HLS + 2 YouTube | index → wrapper (Referer) → `/HLS/<name>.m3u8` (30-row map in NS4) | ADD NOW |
| 13 | `au-tas-traffic` | transport.tas.gov.au | 5 | JPEG (Referer-gated) | sub-page `<img>` → `__traffic_updates/<NNN>_<Location>.jpeg` | LATER |
| 14 | `ozolio` | (Grouse Ozolio embeds) | 5 | HLS + poster JPEG | `relay.ozolio.com/pub.api?cmd=poster&oid=<OID>` | LATER — robots `Disallow: /`, review first |

*NSW/GC: low live-rate at check time (2/21, 1/21) — API list is the stable enumeration; streams drift and must be re-resolved per sweep; 404s recorded `unknown`, never `dead`.

## Cross-cutting insights

- **YouTube-live is the dominant feed type:** OpenWebcamDB + WebcamTaxi + Explore.org + Steamboat + SPI ≈ 4,300 of the enumerated feeds. ONE adapter (extract `video_id` → `oembed` for existence → `yt-dlp --simulate --break-match-filter is_live` for liveness) services them all.
- **Vendor multipliers** (one adapter → many operators): Brownrice (all Vail Resorts properties), Skaping (877 player pages vendor-wide), Roundshot (CH/AT resort cams; `backend.roundshot.com/cams/<id>/<size>` generalizes), Streamdays (other zoos), CoastalComs (AU marine/beach platform).
- **Provenance decision (OWNER CONFIRMED 2026-10-06):** third-party directories (OpenWebcamDB, WebcamTaxi) get provenance `aggregator_directory` — underlying operators are public-by-design but the list is a third-party page; operator URL preserved in `meta.source`. NOT `public_by_design`.
- **Drift rule:** cloudfront/widget/token URLs (NSW, Gold Coast, Streamdays, Camsecure live-edge) rotate — ingesters must re-resolve from the stable list endpoint at every sweep; never hardcode resolved stream URLs.
- **Rate-limit note:** wave ran during a heavy night; children leaned on the fallback chain (some calls on OpenRouter/free Nous). Two trailing-call 429s did not lose any work.

## Dead-ends registry (cross-wave)

- whistlerblackcomb.com / vail.com / steamboat.com plain curl → bot-walled (Akamai/Incapsula); browser needed for DISCOVERY only; steamboat `sitemap.xml` fetchable.
- Wayback Machine 429 during the wave (retry later if ever needed).
- Jungfrau `/api/live-data/webcams` bare list → 404; the real list is `cp-api/webcams`.
- OpenWebcamDB `/api/v1` needs a key; the sitemap path is better (no auth).
- WebcamTaxi slug guesses 404 → only the all-cams listing is reliable.
- `snapshots.explore.org` DNS-unreachable from this host (use `media.explore.org` stillframes / snapshot-API flags).
- `relay.ozolio.com` robots = `Disallow: /` → held for review.
- Tasmania JPEGs 403 without `Referer`; exact published URLs only.
- Camsecure wrapper without Referer serves a placeholder PNG (anti-hotlink), not a feed; `.ts` segments purge fast (always refetch playlist).

## Next moves

1. **Build order CONFIRMED (owner, 2026-10-06):** `explore-omega` → `openwebcamdb` → `jungfrau-roundshot` → `vailresorts-brownrice` first; remaining ADD NOW families after.
2. Build per-family ingesters under `wfd/ingest/` (program convention: children build to `docs/ARCHITECTURE.md`, parent verifies + commits; then per-family health sweeps via `wfd health run`).
3. Re-check live counts at build time (streams drift; the dossiers carry exact commands to re-verify).
4. Decided: directories → `aggregator_directory` (owner, 2026-10-06). Open: `vendor_demo` (Camsecure) viewer badge — default to normal display until decided.
