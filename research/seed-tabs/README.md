# seed-tabs — Brave tab corpus (2026-10-05)

The seed material for World Feed DB: the pages captured in Brave during the 20:43–20:50 ACST cam-research session, fetched and saved.

## Contents

- `TABS-LIST.md` — canonical list: 19 open tabs + session extras + the search queries used ("github live public webcam feed", "github live cam feed").
- `github-topics/*.json` — GitHub topic sweeps (10 queries): webcam-feed, webcams, traffic-cameras (stars + forks-asc), public-webcam, live-feed, camera-streaming, ip-camera-feed, live-streaming, cctv-cameras, traffic-camera. Raw API JSON (top 30 repos each).
- `repos/*.README.md` — full READMEs: pbkompasz/webcams, cobanov/kamera, baywolf88/seeallthethings, JettChenT/scan-for-webcams, GoSlowPoke168/Argus, william-ricchiuti/Live-Environment-Streams, ch-bas/cctv-camera-database, AidanWelch/OpenTrafficCamMap, SoCloseSociety/camforge, bzsasson/livetrafficcam-mcp.
- `repos/*.tree.json` — file trees for the high-value repos (Argus, L-E-S, cctv-camera-database, camforge, OpenTrafficCamMap, pbkompasz, scan-for-webcams).
- `repos/scan-for-webcams.cams.json` — its shodan query/capture-URL config.
- `issues/` — rtsp-camera-view#3 (public RTSP list + 42 comments), frigate#10363.
- `reddit/` — TrafficVision.Live post + site capture (`trafficvision-live-site.md` — KEY reference), r/selfhosted 24/7-webcam post. (Comments not captured: Reddit bot wall; low value, accepted gap.)
- `data/LES-streams.geojson` — Live-Environment-Streams corpus: 5,997 streams (3,754 HLS / 1,768 page / 475 YouTube; 4,226 active).
- `data/LES-sources.json` — its 67-source family index with counts.
- `data/asciinema-494164.cast` — scan-for-webcams demo recording (raw).

## Tab → evidence map (open tabs)

| Tab | Evidence |
|---|---|
| GitHub topic pages ×9 | `github-topics/*.json` (+ catalog §1/§2) |
| pbkompasz/webcams | `repos/pbkompasz__webcams.README.md` + tree |
| TrafficVision.Live thread | `reddit/sideproject-trafficvision-post.md` + `reddit/trafficvision-live-site.md` |
| r/selfhosted thread | `reddit/selfhosted-webcam247-post.md` |
| K3ysTr0K3R/Webanator (404) | catalog §6 — repo gone (account has 0 public repos) |
| rtsp-camera-view #3 | `issues/rtsp-camera-view-3.json` + comments |
| frigate #10363 | `issues/frigate-10363.json` |
| cobanov/kamera | `repos/cobanov__kamera.README.md` (local-webcam demo; low relevance) |
| cve.org / streamlabs.com | context-only; nothing extracted |
| Session extras: seeallthethings, scan-for-webcams, asciinema | `repos/baywolf88__seeallthethings.README.md`, `repos/JettChenT__scan-for-webcams.README.md`, `data/asciinema-494164.cast` |

## Notable finds from this corpus (see SOURCES-CATALOG.md)

- **Live-Environment-Streams** — 5,997 streams / 4,226 verified active; status+url_type+last_verified fields (closest thing to a ready DB).
- **Argus** — 229k camera claim; scraper pipeline with 11 real source integrations.
- **OpenTrafficCamMap** — 7,515 cams; per-state scraper library.
- **cctv-camera-database** — 28,400 hardware specs + per-brand RTSP URL patterns (CC0).
- **camforge** — the nearest self-hosted system in shape to the goal; connectors + policy module.
- **TrafficVision.Live** — largest peer aggregator (155k+ claim, liveness testing).
