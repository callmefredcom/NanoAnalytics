# OpenAPI 3.1.0 specification — served at /openapi.json
# Machine-readable for MCP clients, Claude Desktop, Cursor, GPT Actions, etc.

_COMMON_PARAMS = [
    {
        "name": "site",
        "in": "query",
        "required": True,
        "schema": {"type": "string"},
        "description": "Root domain or any subdomain, e.g. example.com — www and all subdomains are matched automatically",
    },
    {
        "name": "start",
        "in": "query",
        "required": False,
        "schema": {"type": "integer"},
        "description": "Range start as Unix timestamp (seconds)",
    },
    {
        "name": "end",
        "in": "query",
        "required": False,
        "schema": {"type": "integer"},
        "description": "Range end as Unix timestamp (seconds)",
    },
]

_LIMIT_PARAM = {
    "name": "limit",
    "in": "query",
    "required": False,
    "schema": {"type": "integer", "default": 10, "maximum": 500},
    "description": "Maximum rows to return",
}


def _stats_path(summary: str, has_limit: bool = False, response_schema: dict | None = None):
    params = list(_COMMON_PARAMS)
    if has_limit:
        params.append(_LIMIT_PARAM)
    return {
        "get": {
            "summary": summary,
            "security": [{"BearerAuth": []}],
            "parameters": params,
            "responses": {
                "200": {
                    "description": "OK",
                    **({"content": {"application/json": {"schema": response_schema}}} if response_schema else {}),
                },
                "401": {"description": "Unauthorized — missing or invalid API token"},
            },
        }
    }


SPEC = {
    "openapi": "3.1.0",
    "info": {
        "title": "NanoAnalytics API",
        "version": "0.1.0",
        "description": (
            "Self-hostable, lightweight web analytics. "
            "All /api/* endpoints require a Bearer token. "
            "Use ?site=, ?start= and ?end= (Unix seconds) to filter results."
        ),
    },
    "servers": [{"url": "/", "description": "This instance"}],
    "components": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "description": "Set the API_TOKEN environment variable on your instance. Find it in your hosting platform's Environment Variables panel.",
            }
        }
    },
    "paths": {
        "/hit": {
            "get": {
                "summary": "Record a pageview (beacon)",
                "description": "Called by the JS beacon. Returns a 1×1 transparent GIF.",
                "parameters": [
                    {"name": "site",  "in": "query", "required": True,  "schema": {"type": "string"}},
                    {"name": "path",  "in": "query", "required": False, "schema": {"type": "string"}},
                    {"name": "ref",   "in": "query", "required": False, "schema": {"type": "string"}},
                    {"name": "lang",  "in": "query", "required": False, "schema": {"type": "string"}},
                    {"name": "w",     "in": "query", "required": False, "schema": {"type": "integer"}},
                    {"name": "s",     "in": "query", "required": False, "schema": {"type": "string"}, "description": "Session ID"},
                ],
                "responses": {"200": {"description": "1×1 transparent GIF"}},
            }
        },
        "/health": {
            "get": {
                "summary": "Health check",
                "responses": {"200": {"description": '{"status":"ok"}'}},
            }
        },
        "/api/pageviews": _stats_path(
            "Total pageviews and unique sessions",
            response_schema={
                "type": "object",
                "properties": {
                    "views":    {"type": "integer"},
                    "sessions": {"type": "integer"},
                },
            },
        ),
        "/api/pages": _stats_path(
            "Top pages by view count",
            has_limit=True,
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path":  {"type": "string"},
                        "views": {"type": "integer"},
                    },
                },
            },
        ),
        "/api/referrers": _stats_path(
            "Top external referrer domains (internal self-referrals from the tracked domain are automatically excluded)",
            has_limit=True,
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ref":   {"type": "string"},
                        "views": {"type": "integer"},
                    },
                },
            },
        ),
        "/api/timeseries": _stats_path(
            "Daily pageviews (grouped by UTC date)",
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "day":   {"type": "string", "format": "date"},
                        "views": {"type": "integer"},
                    },
                },
            },
        ),
        "/api/devices": _stats_path(
            "Pageview breakdown by device type (mobile / tablet / desktop / unknown)",
            response_schema={
                "type": "object",
                "properties": {
                    "mobile":  {"type": "integer"},
                    "tablet":  {"type": "integer"},
                    "desktop": {"type": "integer"},
                    "unknown": {"type": "integer"},
                },
            },
        ),
        "/api/languages": _stats_path(
            "Top browser languages",
            has_limit=True,
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "lang":  {"type": "string"},
                        "views": {"type": "integer"},
                    },
                },
            },
        ),
        "/api/countries": _stats_path(
            "Top countries by pageview count (ISO 3166-1 alpha-2 codes). Detected from visitor IP at collection time.",
            has_limit=True,
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "country": {"type": "string", "example": "GB"},
                        "views":   {"type": "integer"},
                    },
                },
            },
        ),
        "/api/active": {
            "get": {
                "summary": "Active unique sessions in the last N seconds (default 300 = 5 min), with per-country breakdown. Use for real-time visitor map.",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {"name": "site",   "in": "query", "required": True,  "schema": {"type": "string"}},
                    {"name": "window", "in": "query", "required": False, "schema": {"type": "integer", "default": 300, "maximum": 3600}, "description": "Lookback window in seconds"},
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "active":         {"type": "integer", "description": "Total unique active sessions"},
                                "window_seconds": {"type": "integer"},
                                "countries":      {"type": "array", "items": {"type": "object", "properties": {
                                    "country":  {"type": "string"},
                                    "sessions": {"type": "integer"},
                                }}},
                            },
                        }}},
                    },
                    "401": {"description": "Unauthorized"},
                },
            }
        },
        "/api/hostnames": _stats_path(
            "Pageview breakdown by exact hostname (subdomain breakdown). Accepts root domain or any subdomain — all subdomains are matched automatically.",
            has_limit=True,
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "site":  {"type": "string"},
                        "views": {"type": "integer"},
                    },
                },
            },
        ),
        "/api/entry-pages": _stats_path(
            "Top entry pages — the first page seen in each session, ranked by how often sessions begin there. Distinct from top pages by total views.",
            has_limit=True,
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path":    {"type": "string"},
                        "entries": {"type": "integer", "description": "Number of sessions that started on this page"},
                    },
                },
            },
        ),
        "/api/peak-hours": _stats_path(
            "Top 10 busiest hours of day (UTC, 0–23) by pageview count. Useful for scheduling content or launches at peak audience times.",
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "hour":  {"type": "integer", "minimum": 0, "maximum": 23, "description": "Hour of day in UTC (0 = midnight, 12 = noon)"},
                        "views": {"type": "integer"},
                    },
                },
            },
        ),
        "/api/bounce-rates": _stats_path(
            "Bounce rate per page — percentage of sessions that visited only that one page and nothing else. Ordered highest to lowest. Only pages with 3+ sessions are included. /static/ paths are excluded.",
            has_limit=True,
            response_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path":             {"type": "string"},
                        "total_sessions":   {"type": "integer", "description": "Total sessions that included this page"},
                        "bounce_rate":      {"type": "number",  "description": "Bounce rate as a percentage (0–100)"},
                    },
                },
            },
        ),
    },
}
