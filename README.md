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
> ⚙️ **Railway:** After deploy:
> 1. **Right-click** your NanoAnalytics service on the Railway canvas → **Attach volume** → set mount path to `/data`
> 2. Go to **Variables** → add `API_TOKEN` with any random string
> 3. ⚠️ **Critical — check `DB_PATH`:** In **Variables**, make sure `DB_PATH` is set to `/data/analytics.db`. Railway sometimes auto-populates it as `/tmp/analytics.db` — `/tmp` is ephemeral and gets wiped on every redeploy, losing all your data. If you see `/tmp/...`, change it to `/data/analytics.db` and redeploy.
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

Your NanoAnalytics instance exposes a live OpenAPI spec at `/openapi.json`. Any AI agent that speaks OpenAPI can query your analytics in natural language.

> **Interactive guide:** visit **`https://YOUR-DEPLOY-URL/mcp`** for a page that auto-fills your instance URL and has one-click copy buttons for every config block below.

---

### Claude Desktop

**Prerequisites:** [Node.js](https://nodejs.org) must be installed on your computer (the config uses `npx` to run the MCP bridge automatically — no manual install needed beyond Node.js itself).

**Config file location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Open the file and add the `nano-analytics` block inside `mcpServers`:

```json
{
  "mcpServers": {
    "nano-analytics": {
      "command": "npx",
      "args": ["-y", "@ivotoby/openapi-mcp-server"],
      "env": {
        "API_BASE_URL": "https://YOUR-DEPLOY-URL",
        "OPENAPI_SPEC_PATH": "https://YOUR-DEPLOY-URL/openapi.json",
        "API_HEADERS": "Authorization:Bearer YOUR_API_TOKEN"
      }
    }
  }
}
```

Save the file and restart Claude Desktop. You can now ask:

> *"What were my top pages last week on mysite.com?"*
> *"Is mobile traffic growing this month?"*
> *"Show me the daily trend for the past 30 days."*

---

### Cursor

**Option A — Project scope** (analytics context only in this repo):

Create `.cursor/mcp.json` at the root of your project:

```json
{
  "mcpServers": {
    "nano-analytics": {
      "url": "https://YOUR-DEPLOY-URL/openapi.json",
      "headers": {
        "Authorization": "Bearer YOUR_API_TOKEN"
      }
    }
  }
}
```

**Option B — Global** (available in all Cursor workspaces):

Go to **Cursor Settings → MCP → Add Server** and paste:

```json
{
  "nano-analytics": {
    "url": "https://YOUR-DEPLOY-URL/openapi.json",
    "headers": {
      "Authorization": "Bearer YOUR_API_TOKEN"
    }
  }
}
```

---

### Windsurf (Codeium)

Go to **Windsurf Settings → Cascade → MCP Servers → Add**:

```json
{
  "mcpServers": {
    "nano-analytics": {
      "serverUrl": "https://YOUR-DEPLOY-URL/openapi.json",
      "headers": {
        "Authorization": "Bearer YOUR_API_TOKEN"
      }
    }
  }
}
```

---

### GPT Actions (ChatGPT / custom GPTs)

1. Go to **My GPTs → Create → Configure → Add Action**
2. Set **Authentication** → API Key → Header: `Authorization`, Value: `Bearer YOUR_API_TOKEN`
3. Import schema from URL: `https://YOUR-DEPLOY-URL/openapi.json`
4. Save — your GPT can now answer analytics questions

---

### Any other OpenAPI-compatible client

```
Spec URL:  https://YOUR-DEPLOY-URL/openapi.json
Auth type: Bearer Token
Token:     YOUR_API_TOKEN
```

Works with LangChain tools, LlamaIndex, n8n AI nodes, Make.com HTTP modules, or any tool that accepts an OpenAPI 3.1 spec.

---

### Example queries your agent can answer

| Question | Endpoint used |
|---|---|
| "How many visitors did I get this week?" | `/api/pageviews` |
| "What are my top 5 pages?" | `/api/pages?limit=5` |
| "Where is my traffic coming from?" | `/api/referrers` |
| "Is traffic growing or dropping?" | `/api/timeseries` |
| "What's my mobile vs desktop split?" | `/api/devices` |
| "What languages do my visitors use?" | `/api/languages` |

---

## Telegram & Discord Bots

The bots query your NanoAnalytics API and reply with formatted stats. The recommended approach is to deploy each bot as a **separate lightweight service** — its own private repo, its own Railway service. No volume needed (bots store nothing on disk).

---

### Recommended: Deploy as a standalone Railway service

**Step 1 — Create a bot repo**

Create a new private GitHub repository with these 4 files:

**`bot.py`** — copy from [`bots/telegram_bot.py`](bots/telegram_bot.py) (Telegram) or [`bots/discord_bot.py`](bots/discord_bot.py) (Discord)

**`requirements.txt`**
```
# Telegram
python-telegram-bot==21.*
httpx>=0.27

# Discord (use this instead)
# discord.py>=2.4
# httpx>=0.27
```

**`Dockerfile`**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
CMD ["python", "bot.py"]
```

**`.env.example`**
```
TELEGRAM_BOT_TOKEN=your-token-from-botfather
ANALYTICS_URL=https://your-nanoanalytics-instance.up.railway.app
ANALYTICS_API_TOKEN=your-api-token
ANALYTICS_SITE=mysite.com
```

**Step 2 — Deploy on Railway**

1. Railway → **New Service** → **GitHub** → select your bot repo
2. Go to **Variables** → add the 4 variables from `.env.example` with real values
3. No volume needed — the bot has no disk storage

Railway will build the Docker image and keep the bot running 24/7.

---

### Telegram setup

1. Message [@BotFather](https://t.me/botfather) on Telegram → `/newbot` → copy the token → use it as `TELEGRAM_BOT_TOKEN`
2. Open your bot in Telegram and send `/start`

**Commands:** `/stats` `/pages` `/referrers` `/countries` `/devices` `/trend` `/languages`

---

### Discord setup

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application** → **Bot**
2. Enable **Message Content Intent** under Privileged Gateway Intents
3. Copy the bot token → use it as `DISCORD_BOT_TOKEN`
4. Invite the bot to your server with **Send Messages** + **Read Messages** permissions

**Commands:** `!stats` `!pages` `!referrers` `!devices` `!trend` `!languages`

---

### Quick local test (no hosting needed)

Run directly in your terminal — the bot stays alive as long as the window is open:

```bash
pip install python-telegram-bot httpx   # or: discord.py httpx

TELEGRAM_BOT_TOKEN="..." \
ANALYTICS_URL="https://your-instance.up.railway.app" \
ANALYTICS_API_TOKEN="..." \
ANALYTICS_SITE="mysite.com" \
python bots/telegram_bot.py
```

---

## Docker

```bash
# Clone and run
git clone https://github.com/callmefredcom/NanoAnalytics.git
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
  gunicorn wsgi:app --bind 0.0.0.0:8000 --workers 2
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
