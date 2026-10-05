<h1 align="center">CamForge</h1>

<p align="center">
  <b>A self-hosted, global public-camera intelligence platform.</b><br/>
  Aggregate <b>public-by-design</b> camera feeds worldwide on a live map, relay them through your own
  media server, and analyze frames with a <b>local-first AI vision relay</b> (Ollama) --
  plus authorized-only OSINT exposure monitoring.
</p>

<p align="center">
  <img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-5.9-3178c6?logo=typescript&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-000?logo=nextdotjs&logoColor=white">
  <img alt="PostGIS" src="https://img.shields.io/badge/PostGIS-16-336791?logo=postgresql&logoColor=white">
  <img alt="Ollama" src="https://img.shields.io/badge/AI-Ollama%20%7C%20Claude-6f4cff">
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
  <img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg">
</p>

---

CamForge maps thousands of **public traffic, weather, tourism, marine and aviation cameras** into one
searchable, geospatial catalog, plays them **live from your own relay** (audio stripped), and runs a
**structured AI vision relay** over any frame -- captions, object counts, scene, alert level, and
natural-language Q&A -- **locally on your own GPU** by default. It also ships a **defensive OSINT**
module (Shodan, metadata-only) scoped to assets you are authorized to test, with a coordinated
disclosure workflow.

> Think "a live map of the world's public cameras" + "a local AI that can watch any of them" +
> "an exposure monitor for your own network" -- all self-hosted, no cloud key required.

<p align="center">
  <img alt="CamForge multiview -- a live wall of public traffic cameras" src="docs/screenshots/multiview.png" width="100%">
  <br/><em>Multiview: a live wall of the filtered camera set, refreshed in place.</em>
</p>

<table>
<tr>
<td width="50%"><img alt="CamForge map -- global public cameras on a dark MapLibre map with geo search and filters" src="docs/screenshots/map.png"></td>
<td width="50%"><img alt="CamForge AI relay and observation history" src="docs/screenshots/guide.png"></td>
</tr>
<tr>
<td align="center"><em>Map: geo-targeted search + live panel + AI relay</em></td>
<td align="center"><em>In-app guide: every source, endpoint & feature</em></td>
</tr>
</table>

<p align="center">
  <img alt="CamForge exposure OSINT dashboard with coordinated-disclosure workflow" src="docs/screenshots/osint.png" width="80%">
  <br/><em>Exposure OSINT: authorized-only, metadata-only, with a coordinated-disclosure state machine.</em>
</p>

---

## ⚖️ Ethical use -- the bright line, wired into the code

CamForge only touches feeds that are **public by design**. The difference between aggregating an
operator-published stream (legal) and accessing a private camera exposed by default credentials or a
vuln (unauthorized access under CFAA / EU Directive 2013/40) is enforced **structurally**, not by docs:

- **Public-by-design ingest gate** ([`src/lib/policy.ts`](src/lib/policy.ts)) -- every camera must carry a valid publish signal (platform API, operator page, gov open-data, or opt-in). A credential in a source URL → rejected, logged to `audit_log`.
- **No credential store, no brute-force module ships.** The codebase structurally cannot log into a device.
- **OSINT scope gate** -- exposure discovery is refused for any scope not in `OSINT_AUTHORIZED_SCOPES`. **Metadata only** -- it never authenticates to, streams from, or screenshots a third-party device.
- **Audio kill-switch** -- ffmpeg `-an` at the relay boundary (audio has no safe global legal posture).
- **Detection, not recognition** -- the AI relay describes scenes and counts object classes; it never identifies individuals or reads license plates, and raw third-party imagery is not persisted.

Use it on feeds that are public by design and on networks you own or are authorized to assess. Nothing else.

---

## ✨ Features

- 🗺️ **Global camera map** -- MapLibre dark map, 7,000+ public cameras across 100+ countries, colored by type, with geo-targeted search (place · country · city · bbox · radius) and type/source/name filters.
- 🧱 **Multiview wall** -- a live-refreshing grid of the filtered set; click any tile to focus.
- 🎥 **Live video from your own relay** -- MediaMTX on-demand HLS (reliable for any H.264) with an opt-in sub-second **WebRTC/WHEP** tier; audio stripped; snapshot sources refresh in place; YouTube plays as official embeds.
- 🤖 **Local-first AI vision relay** -- **Ollama-first** (runs on your GPU, no cloud key) with a **Claude** vision fallback. Same structured JSON either way: `caption`, `alert_level`, `objects[]`, `scene`, `answer`. Observation history per camera.
- 🛰️ **Defensive OSINT** -- scope-gated Shodan exposure discovery (metadata only), exposure scoring + CVE matching, and a coordinated-disclosure dashboard (`discovered → reported → acknowledged → remediated → disclosed`).
- 🔌 **Pluggable connectors** -- one file per source; 7 built in (Caltrans, TfL, Windy, YouTube, WSDOT, US 511, Norway Vegvesen). Add your own in minutes.
- 🧭 **In-app guide** at `/guide` documenting every tool, endpoint, source and command.
- 🔒 **Guardrails in code** -- ingest gate, OSINT scope gate, SSRF-safe fetches, audio kill-switch, detection-not-recognition.

---

## 🏗️ How it works

```
connectors/*  ──ingest gate (policy.ts)──▶  cameras (PostGIS catalog)  ──▶  /api/cameras/search  ──▶  MapLibre UI + /multiview
   (public sources)                              │                                                        │
osint/scan (authorized) ──▶ exposure_findings    │                          MediaMTX relay (HLS/WebRTC, audio stripped)
                                                  ▼
                                     AI relay (Ollama-first / Claude) ──▶ observations
```

- **Datastore** -- PostgreSQL 16 + **PostGIS** (isolated Docker container). `GEOGRAPHY` + GiST for bbox / radius / nearest queries.
- **App** -- Next.js 15 (App Router) + React 19 + TypeScript, ESM. Route handlers are the API; the map is a client component.
- **Media** -- MediaMTX (`latest-ffmpeg`) on-demand relay paths; copy-mode remux + `-an`. `<LiveVideo>` is HLS-first with WHEP opt-in.
- **AI** -- Ollama vision (default `qwen2.5vl:3b`) via grammar-constrained JSON, or `@anthropic-ai/sdk` Claude vision as fallback.

---

## 🤖 AI relay -- local-first (Ollama)

The relay analyzes a camera's current public frame and returns **strict structured JSON**. It is
**Ollama-first**: no cloud key needed, everything stays on your machine/GPU.

```bash
ollama pull qwen2.5vl:3b          # strong structured-output vision model, fits a 12GB GPU
# CAMFORGE_AI_BACKEND=auto  -> Ollama first, Claude only as fallback if configured
```

```jsonc
// POST /api/relay/<camera-id>  {"question":"how busy is this scene?"}
{
  "caption": "A busy highway with multiple lanes of traffic, cars and trucks in both directions...",
  "alert_level": "info",
  "objects": [{ "label": "car", "count": 10 }, { "label": "truck", "count": 3 }],
  "scene": { "weather": "clear", "lighting": "day" },
  "answer": "The scene is busy with multiple lanes of traffic."
}
```

Swap the model with `OLLAMA_VISION_MODEL` (`llama3.2-vision`, `moondream`, ...), or set
`CAMFORGE_AI_BACKEND=claude` + `ANTHROPIC_API_KEY` for the cloud path.

---

## 🚀 Quickstart

**Requirements:** Node 22, Docker, and (optional) [Ollama](https://ollama.com) for the local AI relay.

```bash
git clone https://github.com/SoCloseSociety/camforge.git
cd camforge
cp .env.example .env            # everything is optional except DATABASE_URL (defaults to the Docker DB)
npm install

npm run db:up                   # isolated PostGIS on :5443 (+ MediaMTX media relay)
npm run db:migrate
npm run ingest                  # pull public cameras through the ingest gate (Caltrans needs no key)
npm run relay:sync              # pre-register stream cams as on-demand relay paths

# optional: local AI relay
ollama pull qwen2.5vl:3b

npm run dev                     # http://localhost:3939
```

Open **http://localhost:3939** -- map, `/multiview`, `/osint`, and `/guide`.

Ingest one source: `npm run ingest caltrans` · `npm run ingest windy` · etc.

### Environment keys (all optional except `DATABASE_URL`)

| Var | Enables |
|---|---|
| `DATABASE_URL` | everything (defaults to the Docker DB) |
| `CAMFORGE_AI_BACKEND` / `OLLAMA_VISION_MODEL` | local AI relay (`auto` \| `ollama` \| `claude`) |
| `ANTHROPIC_API_KEY` | Claude vision fallback |
| `TFL_APP_KEY`, `WINDY_WEBCAMS_API_KEY`, `YOUTUBE_API_KEY`, `WSDOT_ACCESS_CODE`, `FIVE11`, `VEGVESEN_DATEX_USER`/`PASS` | more camera sources |
| `SHODAN_API_KEY` + `OSINT_AUTHORIZED_SCOPES` | **required** to run any exposure scan |

---

## 🔌 Connectors (sources)

Public-by-design only. Add new ones in [`src/connectors/`](src/connectors/) and register in `registry.ts`.

| Connector | Coverage | Key | Type |
|---|---|---|---|
| `caltrans` | California DOT CCTV | none | snapshot |
| `tfl-jamcams` | London (TfL JamCams) | optional | snapshot + MP4 |
| `windy` | **Global** webcam directory | required | snapshot (display-only) |
| `youtube-live` | Famous public livecams | required | embed |
| `wsdot` | Washington State DOT | free code | snapshot |
| `five11` | US 511 / state DOTs | per-state | snapshot |
| `vegvesen` | Norway (Statens Vegvesen) | free creds | snapshot |

---

## 🌐 API

| Endpoint | Purpose |
|---|---|
| `GET /api/cameras/search` | geo/attribute search (`bbox` · `type` · `source` · `q` · `region` · `city` · `limit`) |
| `GET /api/cameras/:id` | camera detail + recent AI observations |
| `GET /api/stats` | catalog totals + breakdown by source / type / country |
| `GET /api/geocode?q=` | place → bounding box (OSM Nominatim) |
| `GET /api/thumb/:id` | SSRF-safe thumbnail proxy (re-resolves expired previews) |
| `POST /api/relay/:id` | AI relay analysis of the current frame (`{question?}`) |
| `POST /api/relay-stream/:id` | register/resolve the MediaMTX relay path (HLS + WHEP) |
| `POST /api/osint/scan` | scope-gated Shodan exposure discovery (`{scope}`) -- 403 if not authorized |
| `GET /api/osint/findings` | list exposure findings (ranked by score) |
| `POST /api/osint/findings/:id` | advance the coordinated-disclosure state |

---

## 🧰 Tech stack

Next.js 15 · React 19 · TypeScript 5.9 (ESM) · PostgreSQL 16 + PostGIS · postgres.js ·
MediaMTX · ffmpeg · MapLibre GL · hls.js · Ollama (qwen2.5vl / llama3.2-vision) ·
Anthropic Claude vision · Zod · Docker.

## 🗺️ Roadmap

- [x] Aggregator + geo search + map UI (7,000+ cams)
- [x] Live relay (HLS-first + WebRTC/WHEP, audio stripped)
- [x] Local-first AI vision relay (Ollama) + Claude fallback
- [x] Defensive OSINT + coordinated-disclosure workflow
- [ ] Continuous analysis + alert feed
- [ ] More connectors (FAA / NOAA / more national DOTs)
- [ ] GPU CV tier (detection + tracking)

## 🤝 Contributing

PRs welcome -- especially new **public-by-design** connectors. Keep the guardrails intact
(`npm run typecheck` must pass; connectors must pass the ingest gate). See [`CLAUDE.md`](CLAUDE.md)
for the architecture and conventions.

## 📄 License

[MIT](LICENSE) © SoCloseSociety. Provided for lawful, authorized use only -- see **Ethical use** above.
