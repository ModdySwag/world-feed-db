# streamdays fixtures

Trimmed REAL payloads captured 2026-10-06 while building
`wfd/ingest/newsrc/streamdays.py`. Every authorization, token, key and session
value is replaced with `FIXTURE-*` placeholders; the fixture generator's leak
scan (authorization patterns, token patterns, session ids, base64 blobs, CF
beacon payloads) must stay CLEAN. The playlist fixtures are byte-faithful
apart from the scrubbed values (they must start with `#EXTM3U`).

| file | provenance |
|---|---|
| zoo-hub.html | edinburghzoo.org.uk/animals/webcams — `div.allcams` link block |
| zoo-<x>-cam.html | the six zoo cam pages' `.video` + script tag (koala shows the offline placeholder, no code) |
| derby-webcams.html | derbyperegrines.blogspot.com/p/our-webcams.html — Cam 1/2 labels + codes |
| lenpick-stream.html | lenpicktrust.org.uk/live-video-stream — YouTube embed (no streamdays code; platform drift) |
| streamdays-script-penguin.js | live.streamdays.com/xb1u3eln loader script; iframe authorization scrubbed |
| streamdays-iframe-penguin.html | the penguin iframe HTML (flowplayer cfg); token/refreshAuthorization/key/asset-hash scrubbed |
| takeoff-master.m3u8 | takeoff.jetstre.am master playlist; session id scrubbed |
| takeoff-chunklist.m3u8 | jetstre CDN media playlist; session id scrubbed |
| segment-head.bin | first 564 REAL bytes of a live media segment (TS sync 0x47) |
