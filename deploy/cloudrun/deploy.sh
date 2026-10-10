#!/usr/bin/env bash
# Build the backend image and roll it out to Cloud Run:
#   1. build + push to Artifact Registry (Cloud Build, so no local Docker
#      needed; CI builds with Docker itself and sets SKIP_BUILD=1)
#   2. update the migrate/cleanup jobs and run migrations (waits)
#   3. replace the service with the new image and make it public
# Used by .github/workflows/deploy-cloudrun.yml; also runnable locally after
# `gcloud auth login`:  PROJECT_ID=… REGION=… ./deploy/cloudrun/deploy.sh
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
export REGION="${REGION:-us-central1}"
export SERVICE="${SERVICE:-acme-support-api}"
AR_REPO="${AR_REPO:-acme}"
TAG="${TAG:-$(git rev-parse --short HEAD)}"
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/backend:${TAG}"
export RUNTIME_SA="acme-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
export CORS_ORIGINS="${CORS_ORIGINS:-}"
export DEMO_GLOBAL_DAILY_TOKEN_BUDGET="${DEMO_GLOBAL_DAILY_TOKEN_BUDGET:-1500000}"
# Comet-hosted Opik workspace; tracing stays off when unset. The API key comes
# from the acme-opik-api-key secret (bootstrap.sh).
OPIK_WORKSPACE="${OPIK_WORKSPACE:-}"
OPIK_ENV=""
if [ -n "$OPIK_WORKSPACE" ]; then
  OPIK_ENV="            - { name: OPIK_WORKSPACE, value: \"${OPIK_WORKSPACE}\" }
            - { name: OPIK_API_KEY, valueFrom: { secretKeyRef: { name: acme-opik-api-key, key: latest } } }"
fi
export OPIK_ENV

# Model provider and fallback (docs/DEPLOY.md → Model provider). "fake" is the
# scripted model, so the demo keeps answering if every real provider fails.
LLM_PROVIDER="${LLM_PROVIDER:-anthropic}"
LLM_FALLBACK_PROVIDER="${LLM_FALLBACK_PROVIDER:-fake}"
case " $LLM_PROVIDER $LLM_FALLBACK_PROVIDER " in
  *" omniroute "*)
    [ -n "${OMNIROUTE_BASE_URL:-}" ] || { echo "set OMNIROUTE_BASE_URL to an HTTPS URL Cloud Run can reach" >&2; exit 1; } ;;
esac
env_line() { printf '            - { name: %s, value: "%s" }\n' "$1" "$2"; }
secret_line() {
  printf '            - { name: %s, valueFrom: { secretKeyRef: { name: %s, key: latest } } }\n' "$1" "$2"
}
llm_env() {
  env_line LLM_PROVIDER "$LLM_PROVIDER"
  env_line LLM_FALLBACK_PROVIDER "$LLM_FALLBACK_PROVIDER"
  local p
  for p in $(printf '%s\n' "$LLM_PROVIDER" "$LLM_FALLBACK_PROVIDER" | sort -u); do
    case "$p" in
      anthropic) secret_line ANTHROPIC_API_KEY acme-anthropic-api-key ;;
      gemini)
        env_line GEMINI_MODEL "${GEMINI_MODEL:-gemini-3.8-flash}"
        secret_line GEMINI_API_KEY acme-gemini-api-key ;;
      omniroute)
        env_line OMNIROUTE_BASE_URL "${OMNIROUTE_BASE_URL:-}"
        env_line OMNIROUTE_MODEL "${OMNIROUTE_MODEL:-cx/gpt-5.6-sol-medium}"
        secret_line OMNIROUTE_API_KEY acme-omniroute-api-key ;;
    esac
  done
}
LLM_ENV="$(llm_env)"
export LLM_ENV
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
RENDERED="$(mktemp -d)"
VARS='${SERVICE} ${IMAGE} ${RUNTIME_SA} ${CORS_ORIGINS} ${DEMO_GLOBAL_DAILY_TOKEN_BUDGET} ${OPIK_ENV} ${LLM_ENV}'

if [ -z "${SKIP_BUILD:-}" ]; then
  echo "==> Building ${IMAGE}"
  gcloud builds submit "$ROOT/backend" --tag "$IMAGE" --project "$PROJECT_ID" --quiet
fi

for f in service migrate-job cleanup-job; do
  envsubst "$VARS" < "$HERE/$f.yaml" > "$RENDERED/$f.yaml"
done

echo "==> Migrations"
gcloud run jobs replace "$RENDERED/migrate-job.yaml" --region "$REGION" --project "$PROJECT_ID" --quiet
gcloud run jobs execute "${SERVICE}-migrate" --region "$REGION" --project "$PROJECT_ID" --wait
gcloud run jobs replace "$RENDERED/cleanup-job.yaml" --region "$REGION" --project "$PROJECT_ID" --quiet

echo "==> Service"
gcloud run services replace "$RENDERED/service.yaml" --region "$REGION" --project "$PROJECT_ID" --quiet
gcloud run services add-iam-policy-binding "$SERVICE" --region "$REGION" --project "$PROJECT_ID" \
  --member allUsers --role roles/run.invoker --quiet >/dev/null

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" --format 'value(status.url)')"
echo "==> Smoke test ${URL}"
for i in $(seq 1 10); do
  curl -fsS "${URL}/api/health/ready" && echo && break
  sleep 3
done
curl -fsS "${URL}/api/meta" && echo
echo "Deployed ${IMAGE} → ${URL}"
[ -n "${GITHUB_OUTPUT:-}" ] && echo "url=${URL}" >> "$GITHUB_OUTPUT"
exit 0
