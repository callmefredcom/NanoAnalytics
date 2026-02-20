import time
import ipaddress
from flask import Blueprint, request, jsonify, current_app, render_template, send_from_directory

from .db import get_db
from .auth import require_token
from .ua_parser import device_type
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
    """Daily pageviews grouped by UTC date."""
    site, start, end, _ = _query_params()
    where, params = _where(site, start, end)
    rows = get_db().execute(
        f"SELECT date(ts, 'unixepoch') AS day, COUNT(*) AS views "
        f"FROM hits WHERE {where} GROUP BY day ORDER BY day",
        params,
    ).fetchall()
    return jsonify([dict(r) for r in rows])


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
