# 📊 NanoAnalytics

> Lightweight, self-hostable web analytics. One line of JS. Privacy-friendly. AI-ready API.

No cookies · No GDPR banner · No third-party services · ~90 MB/year at 1k daily visitors

---

## Deploy in 2 minutes

Click a button → fill in your app name → get a live URL with your own private database.
Each user gets a completely independent instance. Your data never touches anyone else's server.

| Platform | Cost | Storage | One-click deploy |
|---|---|---|---|
| **Render** | Free tier | 1 GB Disk (auto) | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/callmefredcom/NanoAnalytics) |
| **Railway** | Free tier | Volume | [![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/callmefredcom/NanoAnalytics) |
| **Fly.io** | Free tier | Volume | see [Fly.io deploy](#flyio-manual-deploy) below |
| **Docker** | Self-host | Bind mount | `docker compose up -d` |

> ✅ **Render is the easiest path:** `API_TOKEN` is auto-generated for you. After deploy, find it in your Render dashboard → **Settings → Environment Variables**.
>
> ⚙️ **Railway:** After deploy, go to your service → **Volumes** → add a volume at `/data`. Then go to **Variables** → add `API_TOKEN` with any random string.
>
> 💡 **How the deploy buttons work:** They pull the source code from this public repository and deploy it as *your own private instance* on your chosen platform. You own the deployment, the URL, and the data — there is no shared server.

---

## After Deploy

### 1. Add the tracker to your site

Paste this before `</body>` on every page you want to track:

```html
<script async src="https://YOUR-DEPLOY-URL/a.js"></script>
```

That's it. No configuration. Sessions are tracked via `sessionStorage` — no cookies, no consent banner needed.

### 2. Open your dashboard

Visit **`https://YOUR-DEPLOY-URL/dashboard`**

Enter your site hostname (e.g. `mysite.com`) and your `API_TOKEN` → charts and stats appear immediately.

---

## What you get

| Route | Description |
|---|---|
| `/dashboard` | Visual analytics dashboard (Chart.js) |
| `/docs` | Interactive Swagger API explorer |
| `/mcp` | MCP setup guide for Claude / Cursor |
| `/openapi.json` | Machine-readable OpenAPI 3.1 spec |
| `/a.js` | The beacon script |

---

## API Reference

All `/api/*` endpoints require `Authorization: Bearer YOUR_API_TOKEN`.

Common query parameters: `?site=example.com&start=1735689600&end=1738368000`
(`start` and `end` are Unix timestamps in seconds — optional, defaults to all time)

| Endpoint | Description | Extra params |
|---|---|---|
| `GET /api/pageviews` | Total views + unique sessions | — |
| `GET /api/pages` | Top pages by view count | `&limit=10` |
| `GET /api/referrers` | Top referrer domains | `&limit=10` |
| `GET /api/timeseries` | Daily pageviews (UTC) | — |
| `GET /api/devices` | mobile / tablet / desktop breakdown | — |
| `GET /api/languages` | Top browser languages | `&limit=10` |

### Example with curl

```bash
# Replace with your actual URL and token
URL="https://your-instance.railway.app"
TOKEN="your-api-token"

# Total views this month
curl -H "Authorization: Bearer $TOKEN" \
  "$URL/api/pageviews?site=mysite.com&start=$(date -v-30d +%s)"

# Top 5 pages
curl -H "Authorization: Bearer $TOKEN" \
  "$URL/api/pages?site=mysite.com&limit=5"
```

---

## MCP / AI Agent Setup

Your NanoAnalytics instance exposes a live OpenAPI spec at `/openapi.json`. Any AI agent that speaks OpenAPI can query your analytics directly.

**Visit `/mcp` on your instance** for copy-paste config blocks for:
- **Claude Desktop** — answers questions like *"What were my top pages last week?"*
- **Cursor** — analytics context inside your IDE
- Any other OpenAPI-compatible AI client

---

## Telegram & Discord Bots

Both bots live in the `bots/` folder. They query your analytics API and reply with formatted stats.

### Setup

```bash
# Install bot dependencies
pip install "nano-analytics[bots]"
# or: pip install python-telegram-bot httpx discord.py
```

### Telegram

1. Message [@BotFather](https://t.me/botfather) → `/newbot` → copy the token
2. Run:

```bash
export TELEGRAM_BOT_TOKEN="your-bot-token"
export ANALYTICS_URL="https://your-instance.railway.app"
export ANALYTICS_API_TOKEN="your-api-token"
export ANALYTICS_SITE="mysite.com"

python bots/telegram_bot.py
```

**Commands:** `/stats` `/pages` `/referrers` `/devices` `/trend` `/languages`

### Discord

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) → New Application → Bot
2. Enable **Message Content Intent** under Privileged Gateway Intents
3. Invite the bot with `Send Messages` + `Read Messages` permissions
4. Run:

```bash
export DISCORD_BOT_TOKEN="your-bot-token"
export ANALYTICS_URL="https://your-instance.railway.app"
export ANALYTICS_API_TOKEN="your-api-token"
export ANALYTICS_SITE="mysite.com"

python bots/discord_bot.py
```

**Commands:** `!stats` `!pages` `!referrers` `!devices` `!trend` `!languages`

---

## Docker

```bash
# Clone and run
git clone https://github.com/YOUR_USERNAME/NanoAnalytics.git
cd NanoAnalytics

# Set your token
echo "API_TOKEN=your-secret-token" > .env

# Start (data persists in a named volume)
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

Your instance is at **http://localhost:8000**

---

## pip (local / VPS)

```bash
pip install nano-analytics

# Run (adjust DB_PATH to a writable location)
API_TOKEN=secret DB_PATH=/tmp/analytics.db \
  flask --app "nano_analytics:create_app()" run --host 0.0.0.0
```

For production with gunicorn:

```bash
API_TOKEN=secret DB_PATH=/data/analytics.db \
  gunicorn 'nano_analytics:create_app()' \
  --bind 0.0.0.0:8000 --workers 2
```

---

## Fly.io manual deploy

```bash
# Install flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth login

# Create the app and volume
fly apps create nano-analytics
fly volumes create analytics_data --region iad --size 1

# Set your token
fly secrets set API_TOKEN=your-secret-token
fly secrets set BASE_URL=https://nano-analytics.fly.dev

# Deploy
fly deploy
```

---

## Storage sizing

SQLite on a persistent volume. Each hit row is ~200 bytes.

| Daily visitors | 1 year |
|---|---|
| 1,000 | ~90 MB |
| 10,000 | ~900 MB |
| 100,000 | ~9 GB |

At >50k visitors/day, consider adding a periodic job to aggregate old rows into daily summaries.

---

## Security model

- **No setup page.** Your `API_TOKEN` lives behind your hosting platform's own login. Find it in the Environment Variables panel.
- The dashboard is a static HTML shell — no sensitive data is served without the token.
- The beacon (`/hit`, `/a.js`) is public and sets `Access-Control-Allow-Origin: *` so it works from any domain.
- All stats endpoints require `Authorization: Bearer YOUR_TOKEN`.

---

## License

MIT
