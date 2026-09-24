#!/usr/bin/env bash
# One-time GCP setup for the Cloud Run demo. Idempotent: safe to re-run.
#
#   export PROJECT_ID=my-project REGION=us-central1 GITHUB_REPO=LikhithV02/Customer-Support-Agent
#   ./deploy/cloudrun/bootstrap.sh
#
# Creates: Artifact Registry repo, runtime + deployer service accounts,
# Secret Manager secrets (you're prompted for values), Workload Identity
# Federation for GitHub Actions (no JSON keys), and the hourly cleanup trigger.
# Prints the GitHub repository variables to set at the end.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${GITHUB_REPO:?set GITHUB_REPO (owner/repo)}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-acme-support-api}"
AR_REPO="${AR_REPO:-acme}"
RUNTIME_SA="acme-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_SA="acme-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
POOL="github"
PROVIDER="github-oidc"

gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

echo "==> Enabling APIs"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  cloudscheduler.googleapis.com cloudbuild.googleapis.com

echo "==> Artifact Registry"
gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$AR_REPO" --repository-format docker --location "$REGION"

echo "==> Service accounts"
for sa in acme-runtime acme-deployer; do
  gcloud iam service-accounts describe "${sa}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$sa" --display-name "$sa"
done
for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:${DEPLOY_SA}" \
    --role "$role" --condition None >/dev/null
done

echo "==> Secrets (leave blank to keep an existing value)"
put_secret() {
  local name="$1" prompt="$2" value
  read -r -s -p "$prompt: " value; echo
  if ! gcloud secrets describe "$name" >/dev/null 2>&1; then
    gcloud secrets create "$name" --replication-policy automatic >/dev/null
    [ -z "$value" ] && { echo "   $name is new, so a value is required"; exit 1; }
  fi
  [ -n "$value" ] && printf '%s' "$value" | gcloud secrets versions add "$name" --data-file - >/dev/null
  gcloud secrets add-iam-policy-binding "$name" --member "serviceAccount:${RUNTIME_SA}" \
    --role roles/secretmanager.secretAccessor >/dev/null
}
put_secret acme-database-url "Neon DATABASE_URL (postgresql://…?sslmode=require, the DIRECT host)"
put_secret acme-redis-url "Upstash REDIS_URL (rediss://default:…@….upstash.io:6379)"
put_secret acme-anthropic-api-key "ANTHROPIC_API_KEY"
if ! gcloud secrets describe acme-jwt-secret >/dev/null 2>&1; then
  gcloud secrets create acme-jwt-secret --replication-policy automatic >/dev/null
  openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add acme-jwt-secret --data-file - >/dev/null
  echo "   generated acme-jwt-secret"
fi
gcloud secrets add-iam-policy-binding acme-jwt-secret --member "serviceAccount:${RUNTIME_SA}" \
  --role roles/secretmanager.secretAccessor >/dev/null

echo "==> Workload Identity Federation for ${GITHUB_REPO}"
gcloud iam workload-identity-pools describe "$POOL" --location global >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools create "$POOL" --location global --display-name "GitHub Actions"
gcloud iam workload-identity-pools providers describe "$PROVIDER" --location global \
  --workload-identity-pool "$POOL" >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --location global \
    --workload-identity-pool "$POOL" --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository == '${GITHUB_REPO}' && assertion.ref == 'refs/heads/main'"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${GITHUB_REPO}" >/dev/null

echo "==> Hourly sandbox cleanup (Cloud Scheduler → Cloud Run job)"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:${RUNTIME_SA}" \
  --role roles/run.invoker --condition None >/dev/null
if ! gcloud scheduler jobs describe "${SERVICE}-cleanup" --location "$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs create http "${SERVICE}-cleanup" --location "$REGION" --schedule "17 * * * *" \
    --http-method POST \
    --uri "https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${SERVICE}-cleanup:run" \
    --oauth-service-account-email "$RUNTIME_SA"
fi

cat <<EOT

Done. Set these GitHub repository *variables* (Settings → Secrets and variables → Actions → Variables):

  GCP_PROJECT_ID     = ${PROJECT_ID}
  GCP_REGION         = ${REGION}
  GCP_WIF_PROVIDER   = projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}
  GCP_DEPLOY_SA      = ${DEPLOY_SA}
  DEMO_CORS_ORIGINS  = https://<your-app>.vercel.app,https://<you>.github.io

Then push to main (or run the "Deploy backend (Cloud Run)" workflow) to deploy.
The cleanup scheduler starts working after the first deploy creates the job.
EOT
