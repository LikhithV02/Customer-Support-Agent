# Production Guide

How the refund agent is built to serve thousands of concurrent users, and how
to deploy and operate it. For the load-testing methodology and results see
[LOADTESTING.md](LOADTESTING.md); for the security guardrails see
[HARDENING.md](HARDENING.md).

---

## Architecture

```
                 ┌──────────────── Kubernetes ────────────────┐
 browser ──TLS──▶│ Ingress (ingress-nginx, SSE-safe)           │
                 │   ├─ /      → acme-frontend (nginx, static) │
                 │   └─ /api   → acme-backend  (N pods, HPA)   │──▶ LLM provider
                 └───────────────────┬────────────┬────────────┘   (cached client,
                                     │            │                 timeouts, retries,
                              Postgres (managed)  Redis (managed)    fallback)
```

The backend is **stateless**: everything that must agree across pods lives in
Postgres or Redis, so any pod can serve any request or SSE stream and the
Deployment scales horizontally.

| Concern | Where it lives | Why |
|---|---|---|
| Customers, orders, refunds, transcripts | Postgres (async SQLAlchemy + asyncpg) | Durable, transactional |
| At most one approved refund per order | Postgres row lock (`SELECT … FOR UPDATE`) **and** a partial unique index | Correct under any concurrency |
| Event ordering per conversation | Atomic `UPDATE … RETURNING event_seq` | No duplicate/misordered steps |
| Rate limits (per customer) | Redis fixed-window counters | Shared across pods |
| One turn at a time per conversation | Redis lock (`SET NX PX`), 409 otherwise | Prevents interleaved turns |
| Global in-flight turn cap | Redis sorted-set semaphore, 503 + `Retry-After` | Sheds load before the LLM provider starts 429ing |
| Per-customer daily token budget | Redis counter with TTL | Cost control across conversations |
| Live admin reasoning stream | Redis pub/sub (`conv:{id}`) | Admin and chat can be on different pods |

### Request lifecycle (`POST /api/chat`)

1. Middleware assigns/propagates `X-Request-ID`, enforces the body-size cap.
2. Rate limit (Redis) keyed on the JWT subject, falling back to client IP.
3. JWT verified → `customer_id`. Admin tokens can't chat; customers can't
   read admin endpoints.
4. Conversation ownership check (404 for unknown **or** foreign ids), turn cap.
5. Acquire the per-conversation lock (409) and a global turn slot (503).
6. Stream the agent turn over SSE. Every step is persisted with a short-lived
   DB session and published to Redis. **No DB connection is held while the
   model is thinking.**
7. Release the slot and lock (both also expire on their own if a pod dies).

### Identity

The agent never establishes identity from chat text. The host site (which
already knows who is logged in) issues a short-lived JWT; the widget sends it
as `Authorization: Bearer …`.

- `sub` = customer id, `role` = `customer` (default) or `admin`, `exp` required.
- Verify with a shared secret (`JWT_SECRET`, HS256) **or** your IdP's JWKS
  (`JWT_JWKS_URL`, RS256/ES256). Set `JWT_ISSUER` / `JWT_AUDIENCE` if your
  tokens carry them.
- Hand the token to the widget via `window.ACME_SUPPORT_TOKEN` or
  `postMessage({type: "acme-support-token", token})` from a parent origin listed
  in `VITE_TRUSTED_PARENT_ORIGINS` (see `frontend/src/auth.ts`).
- `AUTH_MODE=dev` enables `POST /api/dev/token` for local use. With `ENV=prod`
  the app refuses to start unless `AUTH_MODE` is `jwt` (or `demo`), a real
  verification key, Postgres and Redis are configured.
- `AUTH_MODE=demo` is for a public showcase: anonymous visitors get a sandbox
  customer and a scoped admin token, with cost caps. See [DEPLOY.md](DEPLOY.md).

---

## Configuration

All settings are environment variables (`backend/app/config.py`). The
important production ones:

| Variable | Default | Notes |
|---|---|---|
| `ENV` | `dev` | `prod` turns on startup validation |
| `AUTH_MODE` | `dev` | `jwt` in production |
| `JWT_SECRET` / `JWT_JWKS_URL` | – | one is required in prod |
| `DATABASE_URL` | SQLite file | `postgresql://…` (async driver is added automatically) |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 10 / 20 | per process; size so `pods × (pool+overflow)` < Postgres `max_connections` (or use PgBouncer) |
| `REDIS_URL` | – (in-process fake) | required in prod |
| `LLM_PROVIDER` | `anthropic` | `anthropic`, `openai`, or `fake` (load tests) |
| `LLM_FALLBACK_PROVIDER` | – | e.g. `openai`; used when the primary errors |
| `LLM_TIMEOUT_S` / `LLM_MAX_RETRIES` | 60 / 2 | |
| `MAX_CONCURRENT_TURNS` | 200 | global cap on in-flight agent turns — set from your provider's rate limits (see below) |
| `CHAT_RATE_LIMIT` | `10/minute` | per customer |
| `CUSTOMER_DAILY_TOKEN_BUDGET` | 300000 | per customer per UTC day |
| `TURN_TIMEOUT_S` | 120 | wall-clock cap per turn |
| `CORS_ORIGINS` | – | comma-separated; only needed when embedding cross-origin |
| `RETENTION_DAYS` | 90 | transcript retention (CronJob) |
| `SENTRY_DSN` | – | optional error reporting |
| `WEB_CONCURRENCY` | 1 | processes per container — keep 1 and scale pods |

---

## Deploying to Kubernetes

Manifests are Kustomize (`deploy/k8s/`):

- `base/` — backend Deployment (+ migration initContainer), Service, HPA, PDB,
  NetworkPolicy, frontend Deployment/Service/PDB, Ingress, retention CronJob.
- `overlays/prod/` — namespace `acme`, TLS via cert-manager. Expects **managed
  Postgres and Redis** and a pre-created `acme-backend-secrets` Secret
  (template: `base/secret.example.yaml`; use External Secrets / Sealed Secrets).
- `overlays/dev/` — self-contained (in-cluster Postgres + Redis, fake LLM,
  dev auth) for kind/minikube and as a load-test target.
- `loadtest/` — distributed Locust (see LOADTESTING.md).

```bash
# images are built and pushed to GHCR by CI on every push to main
kubectl create namespace acme
kubectl -n acme create secret generic acme-backend-secrets --from-env-file=prod.env
kubectl apply -k deploy/k8s/overlays/prod
kubectl -n acme rollout status deploy/acme-backend
```

**Migrations.** Each backend pod runs `alembic upgrade head` in an
initContainer. Concurrent pods serialise on a Postgres advisory lock
(`alembic/env.py`), so the first pod migrates and the rest find the schema at
head. Keep migrations backwards-compatible (expand → deploy → contract) so old
pods keep working during a rolling update.

**Graceful shutdown.** `preStop: sleep 10` keeps a terminating pod serving
while it's removed from endpoints; uvicorn then drains in-flight SSE turns for
up to 60 s (`terminationGracePeriodSeconds: 90`). `maxUnavailable: 0` rolling
updates plus a PDB keep capacity during deploys and node drains.

**Autoscaling.** The HPA targets 60 % CPU (min 3, max 30). The load test shows
per-turn CPU is the backend's bottleneck, so CPU tracks load well. If your
traffic is dominated by slow LLM calls (low CPU, many open streams), add a
custom metric on `agent_turns_in_flight` via prometheus-adapter.

---

## Capacity planning

Two separate ceilings:

1. **Our infrastructure** — measured with the load test (fake LLM). See
   LOADTESTING.md for the per-pod turn rate; size `maxReplicas` from it.
2. **The LLM provider** — usually the real limit. Each turn makes ~2–4 model
   calls of ~1–4 k input tokens. With the provider's tokens-per-minute (TPM)
   and requests-per-minute (RPM) limits for your tier:

   ```
   max_turns_per_min ≈ min(TPM / tokens_per_turn, RPM / calls_per_turn)
   MAX_CONCURRENT_TURNS ≈ max_turns_per_min × avg_turn_seconds / 60 × 0.8
   ```

   Setting `MAX_CONCURRENT_TURNS` from this makes overload degrade to a clean
   503 + `Retry-After` (which the UI shows) instead of cascading provider 429s.
   Anthropic prompt caching is enabled on the system prompt + tools, which cuts
   input-token cost and TPM usage for repeat turns.

---

## Observability

- **Logs** — one JSON object per line with `request_id`, `conversation_id`,
  `customer_id`. Provider errors are logged in full but never returned to users.
- **Metrics** — `GET /metrics` (Prometheus; pods are annotated for scraping):
  `http_requests_total`, `http_request_duration_seconds`, `agent_turns_total{outcome}`,
  `agent_turn_duration_seconds`, `agent_turns_in_flight`, `llm_tokens_total`,
  `agent_tool_calls_total`, `refund_decisions_total{decision}`,
  `injection_flags_total`, `chat_rejections_total{reason}`, `sse_streams_open`.
- **Probes** — `/api/health/live` (process up), `/api/health/ready` (DB + Redis).
- **Errors** — set `SENTRY_DSN`. For distributed tracing, run under
  `opentelemetry-instrument` with `OTEL_EXPORTER_OTLP_ENDPOINT` set.

Suggested alerts:

| Alert | Expression (sketch) |
|---|---|
| Error turns | `rate(agent_turns_total{outcome="error"}[5m]) / rate(agent_turns_total[5m]) > 0.02` |
| Shedding load | `rate(chat_rejections_total{reason="overloaded"}[5m]) > 0` |
| Slow turns | `histogram_quantile(0.95, rate(agent_turn_duration_seconds_bucket[5m])) > 20` |
| 5xx | `rate(http_requests_total{status=~"5.."}[5m]) > 0` |
| Readiness flapping | pods not ready > 2 min |

---

## Runbook

| Symptom | Likely cause | Action |
|---|---|---|
| Many 503 "high demand" | `MAX_CONCURRENT_TURNS` reached | Check provider limits; raise the cap only if the provider has headroom; confirm HPA is scaling |
| Many 429 for one customer | Abuse or a retry loop in an integration | Check logs by `customer_id`; tune `CHAT_RATE_LIMIT` |
| Turns slow, CPU high | Under-provisioned | HPA max reached? raise `maxReplicas` / node pool |
| Turns slow, CPU low | LLM latency | Check provider status; fallback provider kicks in on errors, not slowness |
| `/ready` failing | DB or Redis unreachable | Check managed service status and pool exhaustion (`DB_POOL_SIZE`) |
| Admin live view silent | Redis pub/sub | Check Redis connectivity; chat still works (events are persisted) |

Data retention: the `acme-retention` CronJob deletes transcripts older than
`RETENTION_DAYS` nightly (refund records are kept). Run ad hoc with
`python -m app.maintenance.retention --dry-run`.
