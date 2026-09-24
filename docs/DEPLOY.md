# Deploying the public demo

The showcase deployment has three parts, each hosted where it fits best and all
on free tiers:

```
 GitHub Pages                   Vercel                        Google Cloud Run
┌──────────────────┐  "Try"  ┌──────────────────┐  HTTPS+SSE ┌────────────────────┐
│ landing/         │ ──────▶ │ frontend/ (SPA)  │ ─────────▶ │ backend/ (FastAPI) │──▶ Anthropic
│ project showcase │         │ chat + console   │   CORS     │ AUTH_MODE=demo     │
└──────────────────┘         └──────────────────┘            └──────┬──────┬──────┘
        │ pings /api/health/live on load (wakes a cold instance)    │      │
        └───────────────────────────────────────────────────────────┘   Neon      Upstash
                                                                      Postgres    Redis
```

| Piece | Host | Why |
|---|---|---|
| Landing page (`landing/`) | GitHub Pages | Static, lives next to the code, deployed by `.github/workflows/pages.yml` |
| App UI (`frontend/`) | Vercel | Static SPA with preview deploys per PR; talks to the API cross-origin |
| Backend (`backend/`) | Cloud Run | Container, scales to zero, allows 60-min requests so SSE streams work |
| Postgres | Neon (free) | Managed, serverless Postgres |
| Redis | Upstash (free) | Managed Redis over TLS; supports the pub/sub the admin live view uses |

Vercel's Python functions aren't used for the backend: they can't keep a turn's
SSE stream open for long, and the backend needs long-lived Postgres and Redis
pools. Cloud Run runs the same container that Kubernetes runs
([PRODUCTION.md](PRODUCTION.md)).

---

## What "demo mode" changes

`AUTH_MODE=demo` is a production mode (`ENV=prod` accepts it), designed for
anonymous visitors:

- **`POST /api/demo/session`** creates a private sandbox customer (`DM-…`) with
  one order per refund-policy branch, and returns two tokens that last 2 hours:
  - a **customer** token for chat. It uses the same JWT path as production, and
    identity still never comes from chat text.
  - a **scoped admin** token (`scope` claim) for the agent console. The console
    shows that sandbox's conversations and KPIs only; other visitors' ids
    return 404.
- **Abuse limits.** Sandbox creation is limited to `DEMO_SESSION_RATE_LIMIT` per
  client IP. The IP is read from the last `TRUSTED_PROXY_HOPS` entry of
  `X-Forwarded-For`, so a client can't spoof it. The usual per-customer chat rate
  limit, turn cap and global in-flight cap still apply.
- **Cost cap.** Each visitor has `CUSTOMER_DAILY_TOKEN_BUDGET`, and the whole
  demo has `DEMO_GLOBAL_DAILY_TOKEN_BUDGET` per UTC day. When either is spent,
  turns **run on the scripted model** instead of being refused. The UI shows a
  notice and the guardrails behave identically. `LLM_FALLBACK_PROVIDER=fake`
  does the same when Anthropic errors, so the demo keeps working.
- **Cleanup.** The retention job (`--demo-hours 24`) deletes sandboxes older than
  a day, together with their orders, refunds and transcripts.
- **Optional bot check.** Set `TURNSTILE_SECRET` and the backend requires a
  Cloudflare Turnstile token on session creation. Rendering the widget in
  `frontend/src/pages/Welcome.tsx` is left to you: add it if bots show up.

---

## Step by step

You need a GCP project with billing enabled (Cloud Run's free tier still needs a
billing account), the `gcloud` CLI, and accounts on Neon, Upstash and Vercel.

### 1. Data stores

1. **Neon.** Create a project. Copy the **direct** connection string, which is the
   host *without* `-pooler`, for example
   `postgresql://user:pass@ep-x.eu-central-1.aws.neon.tech/neondb?sslmode=require`.
   asyncpg's prepared statements don't work through PgBouncer in transaction
   mode. The backend translates `sslmode`/`channel_binding` for asyncpg itself.
2. **Upstash.** Create a Redis database in the same region as Cloud Run. Copy the
   `rediss://default:…@….upstash.io:6379` URL.

### 2. Google Cloud (one time)

```bash
export PROJECT_ID=your-project REGION=us-central1 GITHUB_REPO=LikhithV02/Customer-Support-Agent
./deploy/cloudrun/bootstrap.sh
```

The script prompts for the Neon URL, the Upstash URL and your Anthropic key, and
stores each in Secret Manager. It generates the JWT secret. It then creates:

- an Artifact Registry repository
- a runtime service account and a deploy service account
- **Workload Identity Federation** for GitHub Actions, so there are no JSON keys
  to leak; only `main` of your repo can deploy
- the hourly cleanup schedule

At the end it prints the GitHub variables for the next step.

### 3. GitHub repository variables

In **Settings → Secrets and variables → Actions → Variables**, set these. They
are variables, not secrets: none of them is sensitive.

| Variable | Example |
|---|---|
| `GCP_PROJECT_ID` | `your-project` |
| `GCP_REGION` | `us-central1` |
| `GCP_WIF_PROVIDER` | printed by bootstrap |
| `GCP_DEPLOY_SA` | printed by bootstrap |
| `DEMO_CORS_ORIGINS` | `https://acme-support.vercel.app` |
| `DEMO_GLOBAL_DAILY_TOKEN_BUDGET` | `1500000` (optional) |
| `DEMO_APP_URL` | `https://acme-support.vercel.app` (landing CTA) |
| `DEMO_API_URL` | `https://acme-support-api-xxxx.a.run.app` (landing warm-up ping) |

Run **Actions → Deploy backend (Cloud Run) → Run workflow**. Every push to
`main` that touches `backend/` also triggers it. The workflow does four things:

1. builds the image
2. runs `alembic upgrade head` as a Cloud Run job, waiting for it to finish
3. rolls out the service
4. smoke-tests `/api/health/ready` and `/api/meta`

The service URL appears on the run's `demo` environment. You can also deploy
from a laptop with `PROJECT_ID=… ./deploy/cloudrun/deploy.sh`, which builds with
Cloud Build.

### 4. App UI on Vercel

1. **Add New → Project**, then import the repo. Set **Root Directory** to
   `frontend`. `frontend/vercel.json` sets up the build, SPA routing, caching and
   security headers.
2. Environment variables:
   - `VITE_API_BASE_URL` = the Cloud Run URL
   - optionally `VITE_LANDING_URL` = your Pages URL
3. Deploy. Add the Vercel URL to `DEMO_CORS_ORIGINS` and re-run the backend
   deploy.

If you put the API on a custom domain instead of `*.run.app`, add it to
`connect-src` in the CSP in `frontend/vercel.json`.

### 5. Landing page on GitHub Pages

1. **Settings → Pages → Source: GitHub Actions.**
2. Set `DEMO_APP_URL` and `DEMO_API_URL` (step 3). Then run **Deploy landing page
   (GitHub Pages)**, or push a change under `landing/`.

The page is served at `https://<user>.github.io/<repo>/`. Edit `landing/src/config.ts`
for your name, LinkedIn and email. Refresh the screenshots in
`landing/public/screens/` when the UI changes. See "Screenshots" below.

---

## Costs

| Item | Free-tier headroom | Notes |
|---|---|---|
| Cloud Run | 2M requests, 180k vCPU-s, 360k GiB-s per month | Request-based billing; `maxScale: 3` caps spend |
| Neon | 0.5 GB storage | Sandboxes are purged daily |
| Upstash | 500k commands/month | Roughly 20 commands per chat turn |
| Vercel Hobby / GitHub Pages | Free | Static hosting |
| **Anthropic** | Pay per token | **The only real cost.** See below |

The LLM budget is the number to watch. A turn uses about 2–4 model calls of
about 1–4k input tokens each. Prompt caching covers the system prompt and tools.
With `DEMO_GLOBAL_DAILY_TOKEN_BUDGET=1500000`, the worst case is on the order of
$5/day at Sonnet-class pricing; typical recruiter traffic uses a small fraction.
Past the cap, the demo keeps running on the scripted model. As a hard backstop,
also set a **monthly spend limit** in the Anthropic console.

**Cold starts.** With `minScale: 0` the first request after idle waits a few
seconds while an instance starts. The landing page pings the API when it loads,
so the instance is usually warm by the time a visitor clicks through, and the
app shows a "waking up" screen otherwise. Set `minScale: "1"` in
`deploy/cloudrun/service.yaml` (about $10/month) to remove cold starts entirely.

---

## Operating it

- **Logs:** Cloud Run → service → Logs. The logs are structured JSON with
  `request_id`, `conversation_id` and `customer_id`.
- **Rotate the Anthropic key:**
  `printf %s "$NEW_KEY" | gcloud secrets versions add acme-anthropic-api-key --data-file -`,
  then redeploy. The secret is pinned to `latest` at revision creation.
- **Turn the real LLM off** (for example after a traffic spike): set
  `LLM_PROVIDER=fake` in `service.yaml` and redeploy, or set the global budget
  to `1`.
- **Wipe all sandboxes now:**
  `gcloud run jobs execute acme-support-api-cleanup --region $REGION --args="-m,app.maintenance.retention,--demo-hours,0"`.

## Screenshots

The landing page's screenshots are real captures of the app. To refresh them,
run the stack locally in demo mode:

```bash
AUTH_MODE=demo LLM_PROVIDER=fake docker compose up --build
```

Then capture `chat-{dark,light}.png` and `console-{dark,light}.png` at
1440×900 into `landing/public/screens/`.
