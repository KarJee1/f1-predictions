#!/usr/bin/env bash
# Deploys the backend to Google Cloud (free tier): a storage bucket, the read API on Cloud Run,
# the prediction job as a Cloud Run job, and two Cloud Scheduler triggers.
#
# Usage (from the repo root, after `gcloud auth login`):
#   PROJECT_ID=my-project ./infra/deploy.sh
# Re-running it is safe; it updates what already exists.
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your GCP project id}"
REGION="${REGION:-us-central1}"          # us-central1 keeps Cloud Storage inside the always-free tier
BUCKET="${BUCKET:-${PROJECT_ID}-f1-data}"
SA_NAME="f1-backend"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

gcloud config set project "$PROJECT_ID" >/dev/null
echo "==> Enabling APIs"
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com storage.googleapis.com iam.googleapis.com

echo "==> Bucket gs://$BUCKET"
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access

echo "==> Service account"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SA_NAME" --display-name="F1 predictions backend"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" \
  --role=roles/storage.objectAdmin >/dev/null

echo "==> API service"
gcloud run deploy f1-api --source "$ROOT/api" --region "$REGION" --service-account "$SA" \
  --allow-unauthenticated --set-env-vars "F1_BUCKET=$BUCKET" \
  --memory 512Mi --cpu 1 --min-instances 0 --max-instances 3 --concurrency 80 --quiet

echo "==> Prediction job"
gcloud run jobs deploy f1-pipeline --source "$ROOT/pipeline" --region "$REGION" --service-account "$SA" \
  --set-env-vars "F1_STORE=gs://$BUCKET,F1_SIMULATIONS=20000" \
  --memory 2Gi --cpu 1 --task-timeout 3600 --max-retries 0 --quiet
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

echo "==> First run (takes a few minutes)"
gcloud run jobs execute f1-pipeline --region "$REGION" --wait

API_URL="$(gcloud run services describe f1-api --region "$REGION" --format='value(status.url)')"
echo
echo "Done. API: $API_URL"
echo "Check it: curl $API_URL/v1/meta.json"
