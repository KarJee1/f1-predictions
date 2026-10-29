#!/usr/bin/env bash
# Deploys the backend to Google Cloud (free tier): a storage bucket, the read API on Cloud Run,
# the prediction job as a Cloud Run job, and two Cloud Scheduler triggers.
#
# Usage (from the repo root, after `gcloud auth login`):
#   PROJECT_ID=my-project BUNDLE_ID=com.example.app ./infra/deploy.sh
# BUNDLE_ID is the iOS app's bundle identifier; without it, sign-in and friend groups stay switched off.
# Re-running it is safe; it updates what already exists.
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your GCP project id}"
REGION="${REGION:-us-central1}"          # us-central1 keeps Cloud Storage inside the always-free tier
BUCKET="${BUCKET:-${PROJECT_ID}-f1-data}"
BUNDLE_ID="${BUNDLE_ID:-}"
SA_NAME="f1-backend"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

gcloud config set project "$PROJECT_ID" >/dev/null
echo "==> Enabling APIs"
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com storage.googleapis.com iam.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com

echo "==> Bucket gs://$BUCKET"
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access

echo "==> Service account"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SA_NAME" --display-name="F1 predictions backend"
# A new service account can take a minute to become visible to other APIs, so retry the grant.
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" \
    --role=roles/storage.objectAdmin >/dev/null 2>&1; then
    break
  fi
  [ "$attempt" = 10 ] && { echo "Could not grant bucket access to $SA"; exit 1; }
  echo "    waiting for the service account to propagate..."
  sleep 10
done

echo "==> Firestore (accounts, friend groups and their picks)"
gcloud firestore databases describe --database="(default)" >/dev/null 2>&1 || \
  gcloud firestore databases create --database="(default)" --location="$REGION" --type=firestore-native
# Enabling APIs edits the project's IAM policy in the background, so this can hit a concurrent-change conflict; retry.
for attempt in 1 2 3 4 5 6; do
  if gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" \
    --role=roles/datastore.user --condition=None >/dev/null 2>&1; then
    break
  fi
  [ "$attempt" = 6 ] && { echo "Could not grant Firestore access to $SA"; exit 1; }
  echo "    IAM policy busy, retrying..."
  sleep $((attempt * 5))
done

echo "==> Session signing key"
gcloud secrets describe f1-session-secret >/dev/null 2>&1 || \
  openssl rand -hex 32 | tr -d '\n' | gcloud secrets create f1-session-secret --data-file=- --replication-policy=automatic
gcloud secrets add-iam-policy-binding f1-session-secret --member="serviceAccount:$SA" \
  --role=roles/secretmanager.secretAccessor >/dev/null

echo "==> API service"
gcloud run deploy f1-api --source "$ROOT/api" --region "$REGION" --service-account "$SA" \
  --allow-unauthenticated --set-env-vars "F1_BUCKET=$BUCKET,APPLE_BUNDLE_ID=$BUNDLE_ID" \
  --set-secrets "SESSION_SECRET=f1-session-secret:latest" \
  --memory 512Mi --cpu 1 --min-instances 0 --max-instances 3 --concurrency 80 --quiet

echo "==> Prediction job"
gcloud run jobs deploy f1-pipeline --source "$ROOT/pipeline" --region "$REGION" --service-account "$SA" \
  --set-env-vars "F1_STORE=gs://$BUCKET,F1_SIMULATIONS=20000,F1_GROUPS=1" \
  --memory 2Gi --cpu 1 --task-timeout 7200 --max-retries 0 --quiet
gcloud run jobs add-iam-policy-binding f1-pipeline --region "$REGION" \
  --member="serviceAccount:$SA" --role=roles/run.invoker >/dev/null

echo "==> Schedules (hourly Thu-Mon for race weekends, twice a day otherwise)"
RUN_URI="https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/f1-pipeline:run"
schedule() {
  local name="$1" cron="$2"
  if gcloud scheduler jobs describe "$name" --location "$REGION" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$name" --location "$REGION" --schedule "$cron" --time-zone UTC \
      --uri "$RUN_URI" --http-method POST --oauth-service-account-email "$SA" --quiet
  else
    gcloud scheduler jobs create http "$name" --location "$REGION" --schedule "$cron" --time-zone UTC \
      --uri "$RUN_URI" --http-method POST --oauth-service-account-email "$SA"
  fi
}
schedule f1-pipeline-race-weekend "10 * * * 0,1,4,5,6"
schedule f1-pipeline-midweek "10 6,18 * * 2,3"

if [ -z "$(gcloud run jobs executions list --job f1-pipeline --region "$REGION" --limit 1 --format='value(name)')" ]; then
  echo "==> First run (the first one backfills history and takes 30-60 minutes; it runs in the background)"
  gcloud run jobs execute f1-pipeline --region "$REGION" --async
fi

API_URL="$(gcloud run services describe f1-api --region "$REGION" --format='value(status.url)')"
echo
echo "Done. API: $API_URL"
echo "Once the first run finishes, check it: curl $API_URL/v1/meta.json"
echo "Progress: https://console.cloud.google.com/run/jobs/details/$REGION/f1-pipeline/executions?project=$PROJECT_ID"
