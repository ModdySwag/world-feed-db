# VIEWER-SPEC - world-feed-db showpiece (build v0.3) - 2026-10-06

Mission: the local viewer at http://127.0.0.1:8773 becomes a top-tier showpiece: effortless discovery,
honest states, multiple intelligent ways to watch many feed formats, favourites, full help.
Everything must WORK - no dead menu items. Ease of use is paramount.

## Laws (must hold)
1. Honest states only: live/stale/dead/unknown/unverified shown as-is; never imply liveness for unknown rows.
2. Exposure law: exposure_aggregator rows are metadata-only + warning; NEVER url/preview/autoplay; only appear
   when /api/stats exposure_enabled=true; while off they are absent from every endpoint.
3. No runtime CDN: vendored libs only (wfd/web/vendor/leaflet, wfd/web/vendor/hls) + local API + feed hosts
   (YouTube thumbnails/embeds; tile.openstreetmap.org only when map tiles setting is ON).
4. Bandwidth-preserving: posters/thumbnails by default; players only on demand; pause/destroy offscreen
   players; cap concurrent live tiles (default 4, setting 1-9).
5. Every core action reachable in <=2 clicks; keyboard for everything important.

## Files (allowlist; ES modules; served by the local http server)
- wfd/web/index.html          app shell: top menu bar, views container, sidebar, status bar, modal+toast layers.
- wfd/web/css/app.css         design tokens + layout + components (single stylesheet).
- wfd/web/js/app.js           state store, hash router, API client (GET + POST with header X-WFD-Viewer: 1),
                              menu bar wiring, command palette, settings, toasts, keyboard.
- wfd/web/js/views.js         view renderers: overview, map, wall, watch, search, personal, help.
- wfd/web/js/player.js        universal player component + per-format logic.
- wfd/web/js/sound.js         WebAudio synth (no assets).
Vendored: wfd/web/vendor/leaflet/{leaflet.js,leaflet.css,leaflet.markercluster.js,MarkerCluster.css,
MarkerCluster.Default.css,images/} + wfd/web/vendor/hls/hls.min.js.

## API (contract; full docstring in wfd/viewer.py)
GET /api/stats | /api/overview | /api/facets?<filters> | /api/cameras?<filters>&limit&offset&sort&order&geo |
    /api/camera/<id> | /api/prefs
POST /api/prefs/favourite {camera_id, action: add|remove|label, label?} | /api/prefs/reorder {order:[ids]} |
     /api/prefs/settings {settings:{...}}   -- ALL POSTs require header X-WFD-Viewer: 1
Filters: provenance(csv public|directory|exposure|all) status(csv) family(csv) protocol(csv) country(csv)
 tag(csv) q(FTS) bbox favourites=1 geo=only|any sort=<col> order=asc|desc limit(<=5000) offset.
Feature props: camera_id,name,city,country,source_family,provenance,status,protocol,last_verified,
 snapshot_date,tags,display_policy, url (displayable rows only).

## Design language (teal is the owner's colour)
Dark charcoal base #0b0e13 / panels #11151c; teal accent #2dd4bf (+#14b8a6); text #e6edf3; muted #8892a0.
Statuses: live #3ddc84, stale #f5a524, dead #ef5350, unknown #8892a0; exposure #a78bfa; directory chip #7fd6c6.
8-10px radii; hairline borders rgba(255,255,255,.07); glass only on floating layers; system-ui fonts.
Inline SVG icons only (search heart play map grid star settings help close expand refresh link download info).
Accent setting: teal (default) / violet / amber. Dense but breathable; scannable.

## Layout
- Top bar (~40px): brand "World Feed DB" + live total; menus [View | Filters | Tools | Help]; global search
  input; favourites button (count badge); sound toggle; settings gear.
- Sidebar (collapsible; persisted): active filter chips on top; facet sections with live counts from
  /api/facets under the CURRENT filter context: Status, Provenance, Family (top ~15 + more), Country
  (top ~20 + search), Protocol, Tags (top ~20). Clicking toggles filters (instant re-query).
- Main region: active view (hash router #/overview, #/map, #/wall, #/watch, #/search, #/personal, #/help).
- Status bar (~26px): total rows, exposure gate state, API health dot, filter summary, prefs-saved dot, version.
- Overlays: right drawer (row detail + meta + actions), player modal (focus), settings modal, help modal,
  command palette (centre), toasts (bottom-right stack).

## Menu bar (every item functional)
- View: each view (radio-checked) - sidebar toggle - tile size S/M/L - accent - fullscreen.
- Filters: provenance radio (Public (default) / Directory / Exposure [only when enabled] / All),
  status multi-toggle, family/country/protocol/tag submenus (top entries + "manage in sidebar"), Reset all.
- Tools: Command palette (Ctrl+K), Refresh data, Sound on/off + volume, Settings..., Copy view link,
  Export CSV / Export JSON (current results, client-side download).
- Help: Help & guide..., Keyboard shortcuts, About (version, data summary, policies).

## Views
1. Overview: hero stats with count-up (total + by status), top-families bars (total + live share),
   top countries, favourites count, quick-start cards (Search / Map / Watch / Help). Data: /api/overview.
2. Map: leaflet + markercluster; status-coloured circle markers; popup mini-card (name/status/family +
   [Open][Stage][heart]); "Search this area" (bbox from bounds); respects filters; renders <=2500 markers
   (show "refine filters" note above); tile layer toggleable in settings.
3. Wall: responsive card grid, poster-first. Poster: youtube -> https://i.ytimg.com/vi/<id>/hqdefault.jpg;
   jpeg -> still url; others -> styled placeholder chip. Card: poster, name, status chip, family, country;
   hover quick actions (play, stage, heart, info); click -> drawer; dblclick -> player modal.
   "Load more" pagination (results_per_page, default 60). Skeleton shimmer while loading.
4. Watch (multi-watch stage): layouts 1x1 / 2x2 / 3x3 (buttons + setting). Slots hold cameras
   (persist: settings.watch_stage list + watch_layout). Each slot: universal player + controls
   (heart, info, refresh-still, expand->modal, remove X). "Play all" respects max_live_tiles (pause oldest).
   Empty slot: guidance to add from any card's [Stage] action, from Personal, or Search multi-select.
   MIXED FORMATS side-by-side must work (youtube + hls + jpeg + mjpeg + unknown placeholder). Stage survives reload.
5. Search (the heart): big input (debounced ~250ms -> q=); results as cards or compact rows (toggle);
   sort dropdown (name/country/family/status/last_verified/fetch_date); load-more; result count;
   filter chips; multi-select boxes -> "Send N to Watch"; empty-state examples ("falcon", "beach", "traffic").
6. Personal (favourites): managed list - inline label edit (favourite action=label), drag-handle reorder
   (POST reorder), remove, [Open][Stage], "Send all to Watch", export JSON (client-side); empty state explains heart.
7. Help: Getting started; Views & navigation; Finding cameras; Watching formats (table: format -> play ->
   fallback); Favourites & Personal; Watch stage; Settings & sound; Keyboard shortcuts; Honest states; About
   & policy (incl. exposure policy + YouTube note). Help text must match the actual UI.

## Universal player (core component)
- youtube: poster i.ytimg.com hqdefault (extract id from url/meta); play -> iframe
  https://www.youtube-nocookie.com/embed/<id>?autoplay=1 (allowfullscreen).
- hls: placeholder poster; play -> hls.js; on fatal error -> fallback panel "[Open original] [Copy URL]"
  with honest message (browser/CORS).
- mjpeg: <img src> (native); error -> fallback panel.
- jpeg: <img> + refresh timer (settings.still_refresh_s, default 30s; pause offscreen; manual refresh;
  "updated HH:MM:SS" caption).
- iframe/unknown: placeholder + [Open original] (no embed guessing).
All: status chip, format badge, name, meta line, actions (heart/stage/info/open/copy). Never bluff in fallbacks.

## Sounds (subtle, synthesized)
click, navigate (soft whoosh), fav-add (two-note up), fav-remove (down), success chime, error blip,
palette open/close. Default ON at 35% volume; master toggle (menu, settings, `m`). AudioContext only after a
user gesture; never autoplay before interaction.

## Animations (fast, tasteful, transform/opacity only)
View transition 160ms fade+slide; card stagger (cap 24, 12ms); live-dot pulse; count-up 600ms; skeleton shimmer;
toast slide (auto-dismiss 3.5s, hover pause); palette 120ms scale; drawer 180ms slide.
Honour prefers-reduced-motion AND settings.reduced_motion (stagger/pulse/count-up/whoosh off).

## Keyboard
Ctrl+K palette; / focus search; 1-7 views; Esc close overlays; f favourite selected; m mute; [ ] tile size;
? shortcuts. Arrows in palette/lists.

## Settings (persist via POST /api/prefs/settings; restore on load)
sound_on true; sound_volume 0.35; reduced_motion auto; default_view last; tile_size md; still_refresh_s 30;
live_previews false; max_live_tiles 4; map_tiles true; results_per_page 60; accent teal; sidebar_open true;
watch_stage []; watch_layout "2x2".

## Performance laws
First paint fast on the current 31k-row registry; wall scrolls smoothly; max N live players (cap, pause oldest);
IntersectionObserver pause/destroy offscreen players; images lazy; debounce scroll/resize; small per-card DOM.

## Acceptance self-check (must do before reporting)
- Run the server (`py -3.11 -m wfd viewer`); curl each endpoint the UI uses against the real db.
- All 7 views render via real API data; every menu item works; no dead links.
- Facets update under filters; q search works; pagination works; filters combine.
- Favourites: add/label/reorder/remove work via real POSTs (header X-WFD-Viewer: 1) and persist across reload.
- Watch: add 4 mixed-format cams; stage+layout persist across reload; fallbacks honest.
- Sounds toggle; keyboard shortcuts work; help matches UI; exposure law spot-checked.
- Report: files + sizes, how to run, exact commands + observed results, known gaps, anything unverified.
