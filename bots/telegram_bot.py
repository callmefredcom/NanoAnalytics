"""
NanoAnalytics — Telegram Bot
============================

Required environment variables:
  TELEGRAM_BOT_TOKEN   — from @BotFather
  ANALYTICS_URL        — your NanoAnalytics instance URL, e.g. https://abc.railway.app
  ANALYTICS_API_TOKEN  — your API_TOKEN env var value from the hosting platform
  ANALYTICS_SITE       — default site to query, e.g. mysite.com

Install dependencies:
  pip install "nano-analytics[bots]"
  # or: pip install python-telegram-bot httpx

Run:
  python bots/telegram_bot.py
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ── Config ──────────────────────────────────────────────────────────────────

ANALYTICS_URL   = os.environ["ANALYTICS_URL"].rstrip("/")
ANALYTICS_TOKEN = os.environ["ANALYTICS_API_TOKEN"]
DEFAULT_SITE    = os.environ.get("ANALYTICS_SITE", "")
BOT_TOKEN       = os.environ["TELEGRAM_BOT_TOKEN"]

HEADERS = {"Authorization": f"Bearer {ANALYTICS_TOKEN}"}


# ── API helper ───────────────────────────────────────────────────────────────

def _range_7d():
    now   = int(datetime.now(timezone.utc).timestamp())
    start = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    return start, now


async def fetch(path: str, **params) -> dict | list:
    params.setdefault("site", DEFAULT_SITE)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{ANALYTICS_URL}{path}", headers=HEADERS, params=params)
        r.raise_for_status()
        return r.json()


def _fmt(n: int) -> str:
    return f"{n:,}"


# ── Command handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📊 *NanoAnalytics Bot*\n\n"
        "Available commands:\n"
        "/stats — Pageviews & sessions (last 7 days)\n"
        "/pages — Top 10 pages\n"
        "/referrers — Top traffic sources\n"
        "/devices — Device breakdown\n"
        "/trend — Daily traffic (last 7 days)\n"
        "/languages — Top browser languages",
        parse_mode="Markdown",
    )


async def cmd_stats(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    start, end = _range_7d()
    data = await fetch("/api/pageviews", start=start, end=end)
    await update.message.reply_text(
        f"📈 *Last 7 days — {DEFAULT_SITE}*\n\n"
        f"👁 Page Views: `{_fmt(data['views'])}`\n"
        f"👤 Sessions:   `{_fmt(data['sessions'])}`",
        parse_mode="Markdown",
    )


async def cmd_pages(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    start, end = _range_7d()
    rows = await fetch("/api/pages", start=start, end=end, limit=10)
    if not rows:
        await update.message.reply_text("No page data yet.")
        return
    lines = [f"`{r['path']}` — {_fmt(r['views'])} views" for r in rows]
    await update.message.reply_text(
        f"📄 *Top Pages — {DEFAULT_SITE}*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def cmd_referrers(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    start, end = _range_7d()
    rows = await fetch("/api/referrers", start=start, end=end, limit=10)
    if not rows:
        await update.message.reply_text("No referrer data yet.")
        return
    lines = [f"`{r['ref']}` — {_fmt(r['views'])}" for r in rows]
    await update.message.reply_text(
        f"🔗 *Top Referrers — {DEFAULT_SITE}*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def cmd_devices(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    start, end = _range_7d()
    data = await fetch("/api/devices", start=start, end=end)
    total = sum(data.values()) or 1
    lines = [
        f"🖥 Desktop: `{_fmt(data['desktop'])}` ({data['desktop']*100//total}%)",
        f"📱 Mobile:  `{_fmt(data['mobile'])}` ({data['mobile']*100//total}%)",
        f"📟 Tablet:  `{_fmt(data['tablet'])}` ({data['tablet']*100//total}%)",
    ]
    await update.message.reply_text(
        f"📱 *Devices — {DEFAULT_SITE}*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def cmd_trend(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    start, end = _range_7d()
    rows = await fetch("/api/timeseries", start=start, end=end)
    if not rows:
        await update.message.reply_text("No trend data yet.")
        return
    lines = [f"`{r['day']}` — {_fmt(r['views'])} views" for r in rows]
    await update.message.reply_text(
        f"📅 *Daily Trend — {DEFAULT_SITE}*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def cmd_languages(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    start, end = _range_7d()
    rows = await fetch("/api/languages", start=start, end=end, limit=10)
    if not rows:
        await update.message.reply_text("No language data yet.")
        return
    lines = [f"`{r['lang']}` — {_fmt(r['views'])}" for r in rows]
    await update.message.reply_text(
        f"🌐 *Top Languages — {DEFAULT_SITE}*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("pages",     cmd_pages))
    app.add_handler(CommandHandler("referrers", cmd_referrers))
    app.add_handler(CommandHandler("devices",   cmd_devices))
    app.add_handler(CommandHandler("trend",     cmd_trend))
    app.add_handler(CommandHandler("languages", cmd_languages))

    print(f"🤖 NanoAnalytics Telegram bot started (site: {DEFAULT_SITE})")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
