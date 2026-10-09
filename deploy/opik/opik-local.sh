#!/usr/bin/env bash
# Self-hosted Opik for local development, pinned to the SDK version in
# backend/requirements.txt. Wraps Opik's own launcher (opik.sh), so the stack
# (ClickHouse, MySQL, Redis, MinIO, ZooKeeper, backend, UI) matches upstream.
#
#   deploy/opik/opik-local.sh            # start; UI at http://localhost:5173
#   deploy/opik/opik-local.sh --stop     # stop
#   deploy/opik/opik-local.sh --help     # all opik.sh options
#
# Then point the app at it in .env:
#   OPIK_URL_OVERRIDE=http://host.docker.internal:5173/api   # docker compose backend
#   OPIK_URL_OVERRIDE=http://localhost:5173/api              # bare uvicorn
set -euo pipefail

OPIK_VERSION="${OPIK_VERSION:-2.2.95}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIR="${OPIK_DIR:-$ROOT/.opik}"

if [ ! -d "$DIR/.git" ]; then
  # Only the launcher and its compose files, not the whole monorepo.
  git -c advice.detachedHead=false clone --quiet --depth 1 --filter=blob:none --sparse --branch "$OPIK_VERSION" \
    https://github.com/comet-ml/opik.git "$DIR"
  git -C "$DIR" sparse-checkout set deployment/docker-compose scripts
fi

current="$(git -C "$DIR" describe --tags --exact-match 2>/dev/null || true)"
if [ "$current" != "$OPIK_VERSION" ]; then
  echo "$DIR is at '${current:-unknown}', expected $OPIK_VERSION. Delete it and re-run." >&2
  exit 1
fi

# Pin the container images too (they default to :latest), and don't send
# Opik's install report.
export OPIK_VERSION
export OPIK_USAGE_REPORT_ENABLED="${OPIK_USAGE_REPORT_ENABLED:-false}"
exec "$DIR/opik.sh" "$@"
