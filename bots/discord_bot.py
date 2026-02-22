"""
NanoAnalytics — Discord Bot
============================

Required environment variables:
  DISCORD_BOT_TOKEN    — from the Discord Developer Portal
  ANALYTICS_URL        — your NanoAnalytics instance URL, e.g. https://abc.railway.app
  ANALYTICS_API_TOKEN  — your API_TOKEN env var value from the hosting platform
  ANALYTICS_SITE       — default site to query, e.g. mysite.com

Discord Developer Portal setup:
  1. Create a new application at https://discord.com/developers/applications
  2. Go to Bot → add a bot → copy the token
  3. Under Privileged Gateway Intents, enable "Message Content Intent"
  4. Invite the bot: OAuth2 → URL Generator → scopes: bot → permissions: Send Messages, Read Messages

Install dependencies:
  pip install "nano-analytics[bots]"
  # or: pip install discord.py httpx

Run:
  python bots/discord_bot.py

Commands (prefix !):
  !stats, !pages, !referrers, !devices, !trend, !languages
"""

import os
from datetime import datetime, timedelta, timezone

import discord
import httpx

# ── Config ──────────────────────────────────────────────────────────────────

ANALYTICS_URL   = os.environ["ANALYTICS_URL"].rstrip("/")
ANALYTICS_TOKEN = os.environ["ANALYTICS_API_TOKEN"]
DEFAULT_SITE    = os.environ.get("ANALYTICS_SITE", "")
BOT_TOKEN       = os.environ["DISCORD_BOT_TOKEN"]

HEADERS = {"Authorization": f"Bearer {ANALYTICS_TOKEN}"}

PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# ── API helper ───────────────────────────────────────────────────────────────

def _range_7d():
    now   = int(datetime.now(timezone.utc).timestamp())
    start = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    return start, now


async def fetch(path: str, **params) -> dict | list:
    params.setdefault("site", DEFAULT_SITE)
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{ANALYTICS_URL}{path}", headers=HEADERS, params=params)
        r.raise_for_status()
        return r.json()


def _fmt(n: int) -> str:
    return f"{n:,}"


# ── Embed builder ────────────────────────────────────────────────────────────

def embed(title: str, description: str = "", color: int = 0x6366F1) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    e.set_footer(text=f"NanoAnalytics · {DEFAULT_SITE}")
    return e


# ── Command dispatcher ───────────────────────────────────────────────────────

@client.event
async def on_ready():
    print(f"🤖 NanoAnalytics Discord bot connected as {client.user} (site: {DEFAULT_SITE})")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    content = message.content.strip()
    if not content.startswith(PREFIX):
        return

    cmd = content[len(PREFIX):].split()[0].lower()

    try:
        if cmd == "stats":
            await handle_stats(message)
        elif cmd == "pages":
            await handle_pages(message)
        elif cmd == "referrers":
            await handle_referrers(message)
        elif cmd == "devices":
            await handle_devices(message)
        elif cmd == "trend":
            await handle_trend(message)
        elif cmd == "languages":
            await handle_languages(message)
        elif cmd == "countries":
            await handle_countries(message)
        elif cmd == "active":
            await handle_active(message)
        elif cmd == "entrypages":
            await handle_entry_pages(message)
        elif cmd == "peakhours":
            await handle_peak_hours(message)
        elif cmd == "bouncerates":
            await handle_bounce_rates(message)
        elif cmd == "help":
            await handle_help(message)
    except Exception as e:
        await message.channel.send(f"⚠️ Error fetching analytics: `{e}`")


# ── Handlers ─────────────────────────────────────────────────────────────────

async def handle_help(message: discord.Message):
    e = embed("📊 NanoAnalytics Bot")
    e.add_field(name="Commands", value=(
        "`!stats` — Pageviews & sessions (last 7 days)\n"
        "`!pages` — Top 10 pages\n"
        "`!referrers` — Top traffic sources\n"
        "`!devices` — Device breakdown\n"
        "`!trend` — Daily traffic (last 7 days)\n"
        "`!languages` — Top browser languages\n"
        "`!countries` — Top countries\n"
        "`!active` — Active visitors right now\n"
        "`!entrypages` — Top entry pages\n"
        "`!peakhours` — Busiest hours of the day\n"
        "`!bouncerates` — Bounce rate by page"
    ), inline=False)
    await message.channel.send(embed=e)


async def handle_stats(message: discord.Message):
    start, end = _range_7d()
    data = await fetch("/api/pageviews", start=start, end=end)
    e = embed("📈 Last 7 Days")
    e.add_field(name="Page Views", value=_fmt(data["views"]),    inline=True)
    e.add_field(name="Sessions",   value=_fmt(data["sessions"]), inline=True)
    await message.channel.send(embed=e)


async def handle_pages(message: discord.Message):
    start, end = _range_7d()
    rows = await fetch("/api/pages", start=start, end=end, limit=10)
    if not rows:
        await message.channel.send("No page data yet.")
        return
    lines = "\n".join(f"`{r['path']}` — **{_fmt(r['views'])}**" for r in rows)
    e = embed("📄 Top Pages", lines)
    await message.channel.send(embed=e)


async def handle_referrers(message: discord.Message):
    start, end = _range_7d()
    rows = await fetch("/api/referrers", start=start, end=end, limit=10)
    if not rows:
        await message.channel.send("No referrer data yet.")
        return
    lines = "\n".join(f"`{r['ref']}` — **{_fmt(r['views'])}**" for r in rows)
    e = embed("🔗 Top Referrers", lines)
    await message.channel.send(embed=e)


async def handle_devices(message: discord.Message):
    start, end = _range_7d()
    data = await fetch("/api/devices", start=start, end=end)
    total = sum(data.values()) or 1
    e = embed("📱 Device Breakdown")
    e.add_field(name="🖥 Desktop", value=f"{_fmt(data['desktop'])} ({data['desktop']*100//total}%)", inline=True)
    e.add_field(name="📱 Mobile",  value=f"{_fmt(data['mobile'])} ({data['mobile']*100//total}%)",  inline=True)
    e.add_field(name="📟 Tablet",  value=f"{_fmt(data['tablet'])} ({data['tablet']*100//total}%)",  inline=True)
    await message.channel.send(embed=e)


async def handle_trend(message: discord.Message):
    start, end = _range_7d()
    rows = await fetch("/api/timeseries", start=start, end=end)
    if not rows:
        await message.channel.send("No trend data yet.")
        return
    lines = "\n".join(f"`{r['day']}` — **{_fmt(r['views'])}** views" for r in rows)
    e = embed("📅 Daily Trend (Last 7 Days)", lines)
    await message.channel.send(embed=e)


async def handle_languages(message: discord.Message):
    start, end = _range_7d()
    rows = await fetch("/api/languages", start=start, end=end, limit=10)
    if not rows:
        await message.channel.send("No language data yet.")
        return
    lines = "\n".join(f"`{r['lang']}` — **{_fmt(r['views'])}**" for r in rows)
    e = embed("🌐 Top Languages", lines)
    await message.channel.send(embed=e)


async def handle_countries(message: discord.Message):
    start, end = _range_7d()
    rows = await fetch("/api/countries", start=start, end=end, limit=10)
    if not rows:
        await message.channel.send("No country data yet.")
        return
    lines = "\n".join(f"`{r['country']}` — **{_fmt(r['views'])}**" for r in rows)
    e = embed("🌍 Top Countries", lines)
    await message.channel.send(embed=e)


async def handle_active(message: discord.Message):
    data = await fetch("/api/active")
    breakdown = "\n".join(f"`{r['country']}` — **{r['sessions']}** session(s)" for r in (data.get("countries") or []))
    desc = (breakdown or "No country breakdown available.") + f"\n\n🟢 **{data['active']} active** (last {data['window_seconds']//60} min)"
    e = embed("🟢 Active Visitors", desc)
    await message.channel.send(embed=e)


async def handle_entry_pages(message: discord.Message):
    start, end = _range_7d()
    rows = await fetch("/api/entry-pages", start=start, end=end, limit=10)
    if not rows:
        await message.channel.send("No entry page data yet.")
        return
    lines = "\n".join(f"`{r['path']}` — **{_fmt(r['entries'])}** entries" for r in rows)
    e = embed("🚪 Entry Pages", lines)
    await message.channel.send(embed=e)


async def handle_peak_hours(message: discord.Message):
    start, end = _range_7d()
    rows = await fetch("/api/peak-hours", start=start, end=end)
    if not rows:
        await message.channel.send("No hour data yet.")
        return
    lines = "\n".join(f"`{r['hour']:02d}:00` — **{_fmt(r['views'])}** views" for r in rows)
    e = embed("⏰ Peak Hours", lines)
    await message.channel.send(embed=e)


async def handle_bounce_rates(message: discord.Message):
    start, end = _range_7d()
    rows = await fetch("/api/bounce-rates", start=start, end=end, limit=10)
    if not rows:
        await message.channel.send("Not enough data yet.")
        return
    lines = "\n".join(f"`{r['path']}` — **{r['bounce_rate']}%**" for r in rows)
    e = embed("↩️ Bounce Rates", lines)
    await message.channel.send(embed=e)


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    client.run(BOT_TOKEN)
