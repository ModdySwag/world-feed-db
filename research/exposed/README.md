# research/exposed — insecam-class corpus (owner decision D6: INCLUDED)

## Dataset in hand
- `totalynothackedijokeyounot__190221dump_alphabetical.csv` — 17398 parsed rows (17398 lines incl. bad), format: `ip:port \t country \t city \t image-feed-url`. Header: "ip:port	country	city	image feed link".
- Datestamp: filename 190221 → **2019-02-21 — historical corpus**. Expect very low liveness today; value = schema example, country coverage view, and pipeline test material. Fresh harvesting (insecam.org mechanics) is a build-stage job (→W5).
- Unique IPs: 14736; unique countries: 121; top: United States 5159, Japan 2062, Italy 995, France 936, United Kingdom 577, Germany 507, Turkey 476, Netherlands 438, Czech Republic 404, "Korea, Republic Of" 388, "Taiwan, Province Of " 359, Russian Federation 346
- URL keyword counts (first 4000 rows): {'snapshot.cgi': 676, 'cgi-bin': 1887, '.jpg': 1297, 'image': 285, 'mjpg': 980, '/video': 1580, 'GetData': 49}

## GitHub 'insecam' repo inventory (2026-10-05, 41 total; follow-ups for W5)
- GeorgePatsias/OpenEyes S32 — "Open IP cameras from Insecam.org, in a nice dashboard collection and streaming"
- apockill/InsecamScraper S21 — scraper + ML (people/object detection)
- matiasraisanen/insecrawl S18 — automated still-image downloading
- vicalejuri/insecam-feedtv S9 — public cams worldwide viewer
- OEUG99/InsecamPy S3 — scraping library (python)
- L3-X/Insecam-IP-Scraper / 8133/camera-scraper / HadiAssadDiab/Insecam-Scraper / dzfocus/InsecamScraper / n0stal6ic/Insecam-Scraper — scraper variants
- mvarhola/insecam-live S4 — cycling live view; jonasled2/Insecam-Map (moved); saulocatharino/rackcams (BR crawler)
- (tools side, documentation only: Y0oshi/Project-Eyes-On S244, Whomrx666/God-eyes, Cam-HackBSK etc. — NOT run)

## insecam.org direct probe (2026-10-05)
- `https://www.insecam.org/` and `/en/bycountry/US/` via curl: **HTTP 000 / 0 bytes** (connection failed — likely bot protection requiring browser lane). Raw responses saved (`insecam-probe-*.html` = empty). Mechanics →W5 child (browser-lane likely needed; maybe Cloudflare).
