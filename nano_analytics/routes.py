import re
import time
import threading
import ipaddress
from collections import defaultdict, deque
from functools import wraps
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


# ── Bot detection ──────────────────────────────────────────────────────────────

# Chrome dropped Windows 7 (NT 6.1) support after version 109.
_WIN7_RE       = re.compile(r"Windows NT 6\.1")
_CHROME_VER_RE = re.compile(r"Chrome/(\d+)\.")
_BOT_UA_RE     = re.compile(
    r"(bot|crawl|spider|slurp|HeadlessChrome|python-requests|curl|wget|axios|"
    r"node-fetch|Go-http-client|Java/|libwww|okhttp|Scrapy)",
    re.IGNORECASE,
)

# Per-site sliding-window rate limiter (in-process; per gunicorn worker).
# If a site exceeds this many hits/minute within a single worker, incoming
# hits are flagged as bot.  Real newsletter bursts rarely exceed ~100/min/worker.
_MAX_HITS_PER_MINUTE = 300
_hit_windows: dict[str, deque] = defaultdict(deque)
_hit_lock = threading.Lock()


def _is_bot(ua: str) -> bool:
    """Return True if the User-Agent looks like a bot."""
    if not ua:
        return True
    if _BOT_UA_RE.search(ua):
        return True
    # Chrome > 109 cannot run on Windows 7 (NT 6.1) — impossible combination.
    if _WIN7_RE.search(ua):
        m = _CHROME_VER_RE.search(ua)
        if m and int(m.group(1)) > 109:
            return True
    return False


def _is_flood(site: str) -> bool:
    """Sliding-window check: True if this site is being hit at bot-level rates."""
    now    = time.time()
    cutoff = now - 60.0
    with _hit_lock:
        dq = _hit_windows[site]
        while dq and dq[0] < cutoff:
            dq.popleft()
        dq.append(now)
        return len(dq) > _MAX_HITS_PER_MINUTE


# ── Response cache ─────────────────────────────────────────────────────────────
# Keyed by (endpoint_name, query_string).  TTL is long for purely historical
# ranges (end < today) and short for ranges that include today.

_RESP_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_LOCK = threading.Lock()


def _cache_ttl(end: int | None) -> int:
    today_start = int(time.time() // 86400 * 86400)  # UTC midnight today
    if end and end < today_start:
        return 3600   # 1 hour — past data is immutable
    return 120        # 2 min — ranges that include today


def cache_response(fn):
    """Cache jsonify'd responses; safe to stack inside @require_token."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        key = f"{fn.__name__}:{request.query_string.decode()}"
        with _CACHE_LOCK:
            entry = _RESP_CACHE.get(key)
            if entry and time.time() < entry[0]:
                return jsonify(entry[1])
            # Evict expired entries when cache grows large
            if len(_RESP_CACHE) > 1000:
                now = time.time()
                expired = [k for k, v in _RESP_CACHE.items() if now >= v[0]]
                for k in expired:
                    del _RESP_CACHE[k]
        resp = fn(*args, **kwargs)
        data = resp.get_json(silent=True)
        if data is not None:
            end = request.args.get("end", type=int)
            ttl = _cache_ttl(end)
            with _CACHE_LOCK:
                _RESP_CACHE[key] = (time.time() + ttl, data)
        return resp
    return wrapper


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


_FILTER_COLS = {
    "path":     ("path",    "LIKE"),
    "referrer": ("ref",     "LIKE"),
    "country":  ("country", "="),
    "language": ("lang",    "LIKE"),
}


def _where(site, start, end):
    """Build a WHERE clause matching the root domain and all its subdomains.

    e.g. site='flaskvibe.com' matches flaskvibe.com, www.flaskvibe.com,
    app.flaskvibe.com, etc.  site='www.flaskvibe.com' is normalised first.

    Reads additive dimension filters from the current request via
    filter_<field> params (filter_path, filter_referrer, filter_country,
    filter_language). Multiple filters are ANDed together.
    """
    root = _root_domain(site)
    clauses = ["(site = ? OR site LIKE ?)", "(bot IS NULL OR bot = 0)"]
    params  = [root, f"%.{root}"]
    if start:
        clauses.append("ts >= ?")
        params.append(start)
    if end:
        clauses.append("ts <= ?")
        params.append(end)
    for fname, (col, op) in _FILTER_COLS.items():
        fv = request.args.get(f"filter_{fname}", "").strip()
        if fv:
            if op == "LIKE":
                clauses.append(f"{col} LIKE ?")
                params.append(f"%{fv}%")
            else:
                clauses.append(f"{col} = ?")
                params.append(fv.upper())
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
    bot     = 1 if (_is_bot(ua) or _is_flood(site)) else 0

    if site:
        db = get_db()
        db.execute(
            "INSERT INTO hits (ts, site, path, ref, ua, lang, w, session, country, bot) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ts, site, path, ref, ua, lang, w, session, country, bot),
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
@cache_response
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
@cache_response
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
@cache_response
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
@cache_response
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
@cache_response
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
@cache_response
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
@cache_response
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
@cache_response
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
@cache_response
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
        "WHERE (site = ? OR site LIKE ?) AND ts >= ? AND (bot IS NULL OR bot = 0)",
        [root, f"%.{root}", since],
    ).fetchone()["n"]

    rows = get_db().execute(
        "SELECT country, COUNT(DISTINCT session) AS sessions FROM hits "
        "WHERE (site = ? OR site LIKE ?) AND ts >= ? "
        "AND country IS NOT NULL AND country != '' "
        "AND (bot IS NULL OR bot = 0) "
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
@cache_response
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
@cache_response
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
@cache_response
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
@cache_response
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
@cache_response
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
@cache_response
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
@cache_response
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
            FROM session_times
            WHERE duration_s <= 1800""",
        params,
    ).fetchone()
    avg = round(row["avg_seconds"], 1) if row["avg_seconds"] else 0
    return jsonify({"avg_seconds": avg, "sessions": row["sessions"]})


@bp.route("/api/filter-values")
@require_token
@cache_response
def filter_values():
    """Return top distinct values for a filter field, for autocomplete.

    Respects all currently-active filters (via filter_* params) so the
    suggestions reflect the already-filtered data set.
    """
    site, start, end, _ = _query_params()
    field = request.args.get("field", "").strip()
    q     = request.args.get("q",     "").strip()

    if field not in _FILTER_COLS:
        return jsonify([])

    col = _FILTER_COLS[field][0]
    where, params = _where(site, start, end)

    extra_clause = ""
    extra_params: list = []
    if q:
        extra_clause = f"AND {col} LIKE ?"
        extra_params = [f"%{q}%"]

    rows = get_db().execute(
        f"SELECT {col} AS value, COUNT(*) AS n FROM hits "
        f"WHERE {where} AND {col} IS NOT NULL AND {col} != '' "
        f"{extra_clause} GROUP BY {col} ORDER BY n DESC",
        params + extra_params,
    ).fetchall()
    return jsonify([dict(r) for r in rows])
