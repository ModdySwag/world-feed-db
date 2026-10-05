# livetrafficcam-mcp

MCP (Model Context Protocol) server for
[LiveTrafficCam](https://livetrafficcam.com/), a directory of live US
traffic cameras built on official state DOT feeds. Every camera is checked
on a rolling schedule with real HTTP requests, so "live" means a verified
current image, not a listing.

The server wraps the site's public JSON API. It sends one request per tool
call, caches responses for 60 seconds, and returns compact JSON with a
`source_url` you can cite.

## Install

Requires Node 20 or newer.

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "livetrafficcam": {
      "command": "npx",
      "args": ["-y", "livetrafficcam-mcp"]
    }
  }
}
```

Claude Code:

```bash
claude mcp add livetrafficcam -- npx -y livetrafficcam-mcp
```

Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "livetrafficcam": {
      "command": "npx",
      "args": ["-y", "livetrafficcam-mcp"]
    }
  }
}
```

## Tools

- `list_states` — states covered, camera counts, and a liveness summary
  per state. Example: "Which states have traffic camera coverage?"
- `cameras_by_state` — cameras for a two-letter state code, with an
  optional route filter. Example: "Show live cameras on I-90 in Washington."
- `cameras_for_entity` — cameras for a named pass, corridor, bridge or
  tunnel slug. Example: "What do the Donner Pass cameras show?" uses
  `donner-pass`.
- `camera_status` — one camera's verified-live status, last live time,
  and official DOT source. Example: "Is the I-90 floating bridge camera up?"
- `state_uptime` — measured uptime for a state's camera fleet: live,
  stale and dead counts plus the 14-day check success rate. Example:
  "How reliable are Washington's traffic cameras?"

The camera API returns at most 200 cameras per query; tool output says so
when a state has more. Fleet counts come from the
[camera uptime report](https://livetrafficcam.com/reports/camera-uptime/).

## Data source and attribution

All data comes from livetrafficcam.com's public API, which aggregates
official state DOT camera feeds (WSDOT, Caltrans, UDOT, and others). Every
camera result carries the attribution line for its agency; keep it when
you display the data. Uptime numbers should cite the
[uptime report](https://livetrafficcam.com/reports/camera-uptime/).

More from the same data:

- [Camera uptime report](https://livetrafficcam.com/reports/camera-uptime/)
  — measured per-state uptime of official DOT cameras.
- [Traffic camera statistics](https://livetrafficcam.com/reports/traffic-camera-statistics/)
  — how many official DOT traffic cameras exist, per state and agency.
- [Donner Pass cameras](https://livetrafficcam.com/traffic-cameras/california/donner-pass/)
  — an example of the pass pages the entity tool points at.

## Also available

A [Home Assistant integration](https://github.com/bzsasson/livetrafficcam-homeassistant) puts a pass, bridge, tunnel, airport or highway on a dashboard: one camera entity per camera, a verified-live sensor each, and reported disruptions. No API keys.

## License

MIT
