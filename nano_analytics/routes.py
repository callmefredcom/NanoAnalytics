import time
import ipaddress
from flask import Blueprint, request, jsonify, current_app, render_template, send_from_directory

from .db import get_db
from .auth import require_token
from .ua_parser import device_type, browser_name, os_name
from .openapi import SPEC

# Optional offline GeoIP — bundled database, zero external calls
try:
    from geoip2fast import GeoIP2Fast as _GeoIP2Fast
    _geo = _GeoIP2Fast()
except Exception:
    _geo = None

bp = Blueprint("main", __name__)

# 1×1 transparent GIF (raw bytes)
_GIF_1x1 = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _client_ip():
    """Return the real client IP, respecting X-Forwarded-For from reverse proxies."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or ""


def _get_country(ip):
    """Return a 2-letter ISO country code, or None for private/unknown IPs."""
    if not ip or not _geo:
        return None
    try:
        if ipaddress.ip_address(ip).is_private:
            return None
        result = _geo.lookup(ip)
        return result.country_code or None
    except Exception:
        return None


def _query_params():
    site  = request.args.get("site", "")
    start = request.args.get("start", type=int)
    end   = request.args.get("end",   type=int)
    limit = request.args.get("limit", 10, type=int)
    return site, start, end, min(limit, 500)


def _root_domain(site):
    """Strip www. prefix so queries match all subdomains of the root."""
    if site.startswith("www."):
        return site[4:]
    return site


def _where(site, start, end):
    """Build a WHERE clause matching the root domain and all its subdomains.

    e.g. site='flaskvibe.com' matches flaskvibe.com, www.flaskvibe.com,
    app.flaskvibe.com, etc.  site='www.flaskvibe.com' is normalised first.
    """
    root = _root_domain(site)
    clauses = ["(site = ? OR site LIKE ?)"]
    params  = [root, f"%.{root}"]
    if start:
        clauses.append("ts >= ?")
        params.append(start)
    if end:
        clauses.append("ts <= ?")
        params.append(end)
    return " AND ".join(clauses), params


# ── Public routes ──────────────────────────────────────────────────────────────

@bp.route("/health")
def health():
    return jsonify({"status": "ok"})


@bp.route("/hit")
def hit():
    """Beacon endpoint. Inserts a hit row and returns a 1×1 GIF."""
    site    = request.args.get("site", "")
    path    = request.args.get("path", "/")
    ref     = request.args.get("ref",  "")
    lang    = request.args.get("lang", "")
    w_str   = request.args.get("w",    "")
    session = request.args.get("s",    "")
    ua      = request.headers.get("User-Agent", "")
    w       = int(w_str) if w_str.isdigit() else None
    ts      = int(time.time())
    country = _get_country(_client_ip())

    if site:
        db = get_db()
        db.execute(
            "INSERT INTO hits (ts, site, path, ref, ua, lang, w, session, country) VALUES (?,?,?,?,?,?,?,?,?)",
            (ts, site, path, ref, ua, lang, w, session, country),
        )
        db.commit()

    resp = current_app.make_response(_GIF_1x1)
    resp.headers["Content-Type"]               = "image/gif"
    resp.headers["Cache-Control"]              = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@bp.route("/a.js")
def beacon_js():
    """Serve the tracking beacon script with CORS headers."""
    resp = send_from_directory(
        current_app.static_folder, "a.js", mimetype="application/javascript"
    )
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"]               = "public, max-age=3600"
    return resp


@bp.route("/openapi.json")
def openapi():
    return jsonify(SPEC)


@bp.route("/docs")
def docs():
    return render_template("docs.html")


@bp.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@bp.route("/mcp")
def mcp():
    base_url = current_app.config.get("BASE_URL") or request.host_url.rstrip("/")
    return render_template("mcp.html", base_url=base_url)


# ── Protected stats API ────────────────────────────────────────────────────────

@bp.route("/api/pageviews")
@require_token
def pageviews():
    """Total pageviews and unique sessions."""
    site, start, end, _ = _query_params()
    where, params = _where(site, start, end)
    row = get_db().execute(
        f"SELECT COUNT(*) AS views, COUNT(DISTINCT session) AS sessions FROM hits WHERE {where}",
        params,
    ).fetchone()
    return jsonify({"views": row["views"], "sessions": row["sessions"]})


@bp.route("/api/pages")
@require_token
def pages():
    """Top pages by view count."""
    site, start, end, limit = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"SELECT path, COUNT(*) AS views FROM hits WHERE {where} "
        f"GROUP BY path ORDER BY views DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/referrers")
@require_token
def referrers():
    """Top external referrer domains (own-domain self-referrals excluded)."""
    site, start, end, limit = _query_params()
    where, params = _where(site, start, end)
    root = _root_domain(site)
    rows = get_db().execute(
        f"SELECT ref, COUNT(*) AS views FROM hits WHERE {where} "
        f"AND ref != '' AND ref NOT LIKE ? "
        f"GROUP BY ref ORDER BY views DESC LIMIT ?",
        params + [f"%{root}%", limit],
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/timeseries")
@require_token
def timeseries():
    """Daily (or hourly) pageviews and sessions. Pass ?granularity=hour for hourly breakdown."""
    site, start, end, _ = _query_params()
    granularity = request.args.get("granularity", "day")
    where, params = _where(site, start, end)
    if granularity == "hour":
        bucket_expr = "strftime('%Y-%m-%d %H:00', ts, 'unixepoch')"
        label       = "hour"
    else:
        bucket_expr = "date(ts, 'unixepoch')"
        label       = "day"
    rows = get_db().execute(
        f"SELECT {bucket_expr} AS {label}, COUNT(*) AS views, "
        f"COUNT(DISTINCT session) AS sessions "
        f"FROM hits WHERE {where} GROUP BY {label} ORDER BY {label}",
        params,
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/browsers")
@require_token
def browsers():
    """Pageview breakdown by browser (Chrome / Firefox / Safari / Edge / other)."""
    site, start, end, _ = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"SELECT ua FROM hits WHERE {where}", params
    ).fetchall()
    counts: dict[str, int] = {}
    for r in rows:
        b = browser_name(r["ua"])
        counts[b] = counts.get(b, 0) + 1
    return jsonify(counts)


@bp.route("/api/os")
@require_token
def operating_systems():
    """Pageview breakdown by OS (Windows / macOS / Linux / iOS / Android / other)."""
    site, start, end, _ = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"SELECT ua FROM hits WHERE {where}", params
    ).fetchall()
    counts: dict[str, int] = {}
    for r in rows:
        o = os_name(r["ua"])
        counts[o] = counts.get(o, 0) + 1
    return jsonify(counts)


@bp.route("/api/devices")
@require_token
def devices():
    """Pageview breakdown by device type (mobile / tablet / desktop / unknown)."""
    site, start, end, _ = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"SELECT ua FROM hits WHERE {where}", params
    ).fetchall()
    counts = {"mobile": 0, "tablet": 0, "desktop": 0, "unknown": 0}
    for r in rows:
        counts[device_type(r["ua"])] += 1
    return jsonify(counts)


@bp.route("/api/languages")
@require_token
def languages():
    """Top browser languages."""
    site, start, end, limit = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"SELECT lang, COUNT(*) AS views FROM hits WHERE {where} AND lang != '' "
        f"GROUP BY lang ORDER BY views DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/countries")
@require_token
def countries():
    """Top countries by pageview count (ISO 3166-1 alpha-2 codes)."""
    site, start, end, limit = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"SELECT country, COUNT(*) AS views FROM hits WHERE {where} "
        f"AND country IS NOT NULL AND country != '' "
        f"GROUP BY country ORDER BY views DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/active")
@require_token
def active():
    """Active unique sessions in the last N seconds (default 300 = 5 min), grouped by country."""
    site   = request.args.get("site", "")
    window = min(int(request.args.get("window", 300)), 3600)
    since  = int(time.time()) - window
    root   = _root_domain(site)

    total = get_db().execute(
        "SELECT COUNT(DISTINCT session) AS n FROM hits "
        "WHERE (site = ? OR site LIKE ?) AND ts >= ?",
        [root, f"%.{root}", since],
    ).fetchone()["n"]

    rows = get_db().execute(
        "SELECT country, COUNT(DISTINCT session) AS sessions FROM hits "
        "WHERE (site = ? OR site LIKE ?) AND ts >= ? "
        "AND country IS NOT NULL AND country != '' "
        "GROUP BY country ORDER BY sessions DESC",
        [root, f"%.{root}", since],
    ).fetchall()

    return jsonify({
        "active":          total,
        "window_seconds":  window,
        "countries":       [dict(r) for r in rows],
    })


@bp.route("/api/hostnames")
@require_token
def hostnames():
    """Pageview breakdown by exact hostname (subdomain breakdown)."""
    site, start, end, limit = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"SELECT site, COUNT(*) AS views FROM hits WHERE {where} "
        f"GROUP BY site ORDER BY views DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/entry-pages")
@require_token
def entry_pages():
    """Top entry pages — first path seen in each session."""
    site, start, end, limit = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"""WITH filtered AS (
              SELECT session, path, ts FROM hits WHERE {where}
            ),
            session_first AS (
              SELECT session, MIN(ts) AS first_ts FROM filtered GROUP BY session
            ),
            entries AS (
              SELECT f.path FROM filtered f
              JOIN session_first sf ON f.session = sf.session AND f.ts = sf.first_ts
            )
            SELECT path, COUNT(*) AS entries
            FROM entries
            GROUP BY path ORDER BY entries DESC LIMIT ?""",
        params + [limit],
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/peak-hours")
@require_token
def peak_hours():
    """Pageview count grouped by hour of day (0–23, UTC), top 10 busiest."""
    site, start, end, _ = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"SELECT CAST(strftime('%H', ts, 'unixepoch') AS INTEGER) AS hour, "
        f"COUNT(*) AS views FROM hits WHERE {where} "
        f"GROUP BY hour ORDER BY views DESC LIMIT 10",
        params,
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/bounce-rates")
@require_token
def bounce_rates():
    """Bounce rate per page — % of sessions that only ever viewed that one page."""
    site, start, end, limit = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"""WITH filtered AS (
              SELECT session, path FROM hits WHERE {where} AND path NOT LIKE '/static/%'
            ),
            session_sizes AS (
              SELECT session, COUNT(*) AS hit_count FROM filtered GROUP BY session
            ),
            page_visits AS (
              SELECT f.path,
                     COUNT(DISTINCT f.session) AS total_sessions,
                     SUM(CASE WHEN ss.hit_count = 1 THEN 1 ELSE 0 END) AS bounces
              FROM filtered f
              JOIN session_sizes ss ON f.session = ss.session
              GROUP BY f.path
            )
            SELECT path,
                   total_sessions,
                   ROUND(100.0 * bounces / total_sessions, 1) AS bounce_rate
            FROM page_visits
            WHERE total_sessions >= 3
            ORDER BY bounce_rate DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/exit-pages")
@require_token
def exit_pages():
    """Top exit pages — last path seen in each session."""
    site, start, end, limit = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"""WITH filtered AS (
              SELECT session, path, ts FROM hits WHERE {where}
            ),
            session_last AS (
              SELECT session, MAX(ts) AS last_ts FROM filtered GROUP BY session
            ),
            exits AS (
              SELECT f.path FROM filtered f
              JOIN session_last sl ON f.session = sl.session AND f.ts = sl.last_ts
            )
            SELECT path, COUNT(*) AS exits
            FROM exits
            GROUP BY path ORDER BY exits DESC LIMIT ?""",
        params + [limit],
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/screen-widths")
@require_token
def screen_widths():
    """Pageview breakdown by screen width bucket."""
    site, start, end, limit = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"SELECT w, COUNT(*) AS views FROM hits WHERE {where} AND w IS NOT NULL "
        f"GROUP BY w ORDER BY views DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/session-duration")
@require_token
def session_duration():
    """Average session duration in seconds (sessions with > 1 hit only)."""
    site, start, end, _ = _query_params()
    where, params = _where(site, start, end)
    row = get_db().execute(
        f"""WITH session_times AS (
              SELECT session, MAX(ts) - MIN(ts) AS duration_s
              FROM hits WHERE {where}
              GROUP BY session
              HAVING COUNT(*) > 1
            )
            SELECT AVG(duration_s) AS avg_seconds, COUNT(*) AS sessions
            FROM session_times""",
        params,
    ).fetchone()
    avg = round(row["avg_seconds"], 1) if row["avg_seconds"] else 0
    return jsonify({"avg_seconds": avg, "sessions": row["sessions"]})
