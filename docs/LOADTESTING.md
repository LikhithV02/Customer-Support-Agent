# Load Testing

The load test answers two questions before real users do:

1. **Does it stay fast?** Latency SLOs for thousands of concurrent customers
   holding long-lived SSE chat streams.
2. **Does it stay correct?** Under concurrency, no refund may be approved that
   the policy forbids, no order may be refunded twice, no customer may touch
   another's data, and every guardrail must still fire.

It uses [Locust](https://github.com/locustio/locust): Python user classes,
distributed master/worker mode (each worker process drives hundreds to
thousands of gevent users), CSV/HTML reports, and a process exit code that CI
can gate on.

---

## What gets simulated

| User class | Share | Behaviour | Asserts |
|---|---|---|---|
| `CustomerChatUser` | 85 % | 2–3 turn refund conversation (list orders → refund one of 5 scenario orders → status question), then reloads the conversation. 3–8 s think time. | The refund decision matches policy for that order (`chat:wrong_decision`) |
| `RaceUser` | 10 % | Two concurrent turns in one conversation; two concurrent refund conversations for the same order | Never two approvals (`race:single_approval`); the lock never rejects both (`race:turn_lock`) |
| `AbusiveUser` | 3 % | Injection attempts on a final-sale order, another customer's conversation id, no token, customer token on admin API, oversize messages, request bursts | No approval, 404, 401, 403, 400/413, 429 respectively (`abuse:*`) |
| `AdminDashboardUser` | 2 % | Lists conversations, opens one, holds its live SSE stream for 10–30 s | Stream stays up (`admin:stream`) |

Every simulated user gets **its own synthetic customer** (`LT-000001` …) with
five orders, one per policy branch (`backend/scripts/seed_synthetic.py`):

| Order | Kind | Correct outcome |
|---|---|---|
| `LT-xxxxxx-A` | refundable | approved (denied if already refunded earlier) |
| `LT-xxxxxx-B` | final sale | denied |
| `LT-xxxxxx-C` | > $500 | escalated |
| `LT-xxxxxx-D` | outside return window | denied |
| `LT-xxxxxx-E` | already refunded | denied |

Locust signs JWTs locally with the shared `JWT_SECRET`, so minting tokens adds
no load to the API.

### The fake LLM

`LLM_PROVIDER=fake` swaps in a scripted tool-calling model
(`backend/app/agent/llm_fake.py`) that behaves like a well-behaved agent and
sleeps for a log-normal latency (median `FAKE_LLM_LATENCY_MS`, default 1.5 s;
p95 ≈ 1.9× median) per call, failing with probability `FAKE_LLM_ERROR_RATE`.
This exercises **our** system — API, DB, Redis, SSE, locks, pods — at
thousands of users without spending tokens. The real provider's limits are a
separate ceiling; see *Live-LLM smoke* below.

### Metrics

Locust's built-in timing stops at the response headers, which says nothing
about an SSE turn. The locustfile reads each stream and reports custom entries
(type `SSE`):

| Name | Meaning |
|---|---|
| `chat:ttfe` | time to first SSE event — pure server overhead (auth, DB, Redis, lock) before the LLM |
| `chat:full_turn` | time until the `done` event (includes 2–4 fake LLM calls) |
| `chat:agent_error` | turn ended with an `error` event (expected ≈ fake error rate) |
| `chat:shed_503` | back-pressure rejections (expected only when over capacity) |
| `chat:wrong_decision`, `race:*`, `abuse:*` | correctness probes — **any** failure fails the run |

### Pass/fail

`loadtest/slo.py` runs when Locust quits and sets exit code 1 if:

- unexpected failure ratio > 0.5 % (`SLO_MAX_FAIL_RATIO`) — intended 409/429/503 are recorded as successes under their own names;
- p95 `chat:ttfe` > 1.5 s (`SLO_TTFE_P95_MS`);
- p95 `chat:full_turn` > 15 s (`SLO_TURN_P95_MS`);
- agent-error turns > 2 % (`SLO_MAX_AGENT_ERRORS`);
- any correctness probe failed, or any 500/502/504 was seen.

Then `loadtest/check_invariants.py` audits the database directly. These must
**never** be true, however hard the system was pushed:

- more than one approved refund for an order;
- an approved refund on a final-sale, over-$500 or out-of-window order, or on
  any synthetic `-B/-C/-D/-E` order;
- a refund recorded in a conversation owned by a different customer;
- `orders.refunded` out of sync with the refund ledger;
- a conversation with no owner, or duplicate `(conversation_id, seq)` events.

---

## Load shapes

`LOAD_SHAPE=<name>` selects a `LoadTestShape` (`loadtest/shapes.py`); scale
user counts with `LT_SCALE` and durations with `LT_TIME_SCALE`.

| Shape | Profile | Purpose |
|---|---|---|
| `smoke` | 50 users, 2 min | CI gate on every PR |
| `ramp` | 0 → 2,000 over 10 min, hold 10 min | steady-state capacity |
| `spike` | 200 → 3,000 in 30 s, hold, back to 200 | autoscaling + back-pressure |
| `soak` | 1,000 users for `SOAK_MINUTES` (60) | leaks, pool exhaustion, drift |
| `breakpoint` | +250 users every 2 min until an SLO breaks | the real limit → sets HPA max and `MAX_CONCURRENT_TURNS` |

---

## Running it

### Locally (no Docker)

```bash
# Postgres + Redis running locally; backend deps installed
cd backend
export DATABASE_URL=postgresql://postgres@localhost:5432/app REDIS_URL=redis://localhost:6379/0
alembic upgrade head && python -m app.db.seed
python -m scripts.seed_synthetic --customers 10000 --reset   # --reset between runs

ENV=dev AUTH_MODE=dev LLM_PROVIDER=fake MAX_CONCURRENT_TURNS=5000 LOG_LEVEL=WARNING \
  uvicorn app.main:app --port 8000 --workers 3 --no-access-log &

cd ../loadtest && pip install -r requirements.txt
# distributed: 1 master + N workers (set LT_WORKERS=N so customer ids don't collide)
export LT_WORKERS=2
locust -f locustfile.py --worker & locust -f locustfile.py --worker &
locust -f locustfile.py --master --expect-workers 2 --host http://localhost:8000 \
  --headless -u 1000 -r 10 -t 7m --csv results/run --html results/run.html
python check_invariants.py
```

### Docker Compose

```bash
LLM_PROVIDER=fake MAX_CONCURRENT_TURNS=5000 LOAD_SHAPE=ramp LT_WORKERS=4 \
  docker compose --profile loadtest up --build --scale backend=3 --scale locust-worker=4
# UI: http://localhost:8089 (or add LOCUST_ARGS="--headless --autostart ...")
docker compose run --rm --entrypoint python locust-master check_invariants.py
```

### Kubernetes (staging)

```bash
kubectl apply -k deploy/k8s/overlays/dev      # stack with fake LLM
kubectl apply -k deploy/k8s/loadtest          # seeds synthetic data + Locust
kubectl -n acme-dev scale deploy/locust-worker --replicas=10
kubectl -n acme-dev port-forward svc/locust-master 8089
```

Point `LOCUST_HOST` at the staging Ingress to include it in the test. **Never
aim this at production.** During `spike`/`soak`, run the chaos steps and
confirm the pass criteria still hold:

```bash
kubectl -n acme-dev delete pod -l app.kubernetes.io/name=acme-backend --wait=false  # one pod
kubectl -n acme-dev rollout restart deploy/acme-backend                              # rolling deploy
```

In-flight turns on a killed pod end with an `error` event or a dropped stream
(the client can retry — the per-conversation lock expires on its own); there
must be no 5xx storm and no invariant violations.

### Live-LLM smoke

Run a small profile (20–50 users) against the real provider to measure real
turn latency and hit your account's rate limits deliberately; the number of
concurrent turns at which provider 429s start is what `MAX_CONCURRENT_TURNS`
should sit just below (see PRODUCTION.md → Capacity planning).

---

## Results
