#!/usr/bin/env bash
# One-time Google Cloud setup for the simulator API (see docs/simulator/CLOUD.md).
#
# Creates, in one project:
#   * an Artifact Registry repository that keeps only the two newest images
#   * two service accounts: one the service runs as (no permissions at all) and one GitHub
#     Actions deploys as
#   * Workload Identity Federation, so GitHub Actions on this repository's main branch can deploy
#     without any key stored in GitHub
#   * a budget that emails the billing account's owner at 50% and 100% of BUDGET_AMOUNT
#
# It deploys nothing: the service itself is deployed by .github/workflows/api.yml.
# Safe to run again: every step checks what already exists.
#
#   PROJECT_ID=my-project ./infra/gcp_setup.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-pandemic-simulator-510718}"
REGION="${REGION:-us-central1}"                        # a region covered by Cloud Run's free tier
GITHUB_REPO="${GITHUB_REPO:-aagamshah15/COVID-19-Analytics}"
SERVICE="${SERVICE:-simulator-api}"
REPOSITORY="${REPOSITORY:-simulator}"
BUDGET_AMOUNT="${BUDGET_AMOUNT:-1}"                    # in the billing account's currency
RUNTIME_ACCOUNT="simulator-api-runtime"
DEPLOY_ACCOUNT="github-deployer"
POOL="github"
PROVIDER="github-actions"
BUDGET_NAME="${SERVICE} alert"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
exists() { "$@" >/dev/null 2>&1; }
# A newly enabled API can take a minute or two to answer.
retry() {
  local attempt
  for attempt in 1 2 3 4 5 6; do
    "$@" && return 0
    echo "  not ready yet, trying again in 15 seconds (${attempt}/6)" >&2
    sleep 15
  done
  return 1
}

command -v gcloud >/dev/null || { echo "gcloud is not installed: https://cloud.google.com/sdk/docs/install" >&2; exit 1; }
ACCOUNT="$(gcloud config get-value account 2>/dev/null)"
[ -n "$ACCOUNT" ] || { echo "Not signed in. Run: gcloud auth login" >&2; exit 1; }
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
BILLING_ACCOUNT="$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingAccountName)')"
BILLING_ACCOUNT="${BILLING_ACCOUNT#billingAccounts/}"
[ -n "$BILLING_ACCOUNT" ] || { echo "Project $PROJECT_ID has no billing account linked. Link one in the console first." >&2; exit 1; }
CURRENCY="$(gcloud billing accounts describe "$BILLING_ACCOUNT" --format='value(currencyCode)')"

RUNTIME_EMAIL="${RUNTIME_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_EMAIL="${DEPLOY_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
POOL_NAME="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}"

say "Setting up ${PROJECT_ID} (${PROJECT_NUMBER}) as ${ACCOUNT}"
echo "Region ${REGION}; deploys allowed from github.com/${GITHUB_REPO} (main branch only)."

say "1/5 Enabling the APIs"
gcloud services enable --project "$PROJECT_ID" \
  run.googleapis.com artifactregistry.googleapis.com iam.googleapis.com iamcredentials.googleapis.com \
  sts.googleapis.com cloudresourcemanager.googleapis.com billingbudgets.googleapis.com

say "2/5 Image repository (keeps the two newest images, inside the 0.5 GB free tier)"
if ! exists gcloud artifacts repositories describe "$REPOSITORY" --project "$PROJECT_ID" --location "$REGION"; then
  gcloud artifacts repositories create "$REPOSITORY" --project "$PROJECT_ID" --location "$REGION" \
    --repository-format docker --description "Simulator API images"
fi
POLICY="$(mktemp)"
trap 'rm -f "$POLICY"' EXIT
cat >"$POLICY" <<'JSON'
[
  {"name": "keep-two-newest", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
  {"name": "delete-the-rest", "action": {"type": "Delete"}, "condition": {"tagState": "any", "olderThan": "1d"}}
]
JSON
gcloud artifacts repositories set-cleanup-policies "$REPOSITORY" --project "$PROJECT_ID" --location "$REGION" \
  --policy "$POLICY" --no-dry-run >/dev/null
echo "Cleanup policy set."

say "3/5 Service accounts"
if ! exists gcloud iam service-accounts describe "$RUNTIME_EMAIL" --project "$PROJECT_ID"; then
  gcloud iam service-accounts create "$RUNTIME_ACCOUNT" --project "$PROJECT_ID" \
    --display-name "Simulator API (runs the service; no permissions)"
fi
if ! exists gcloud iam service-accounts describe "$DEPLOY_EMAIL" --project "$PROJECT_ID"; then
  gcloud iam service-accounts create "$DEPLOY_ACCOUNT" --project "$PROJECT_ID" \
    --display-name "GitHub Actions deployer"
  sleep 10 # a new account takes a moment to become visible to IAM
fi
# The deployer may deploy Cloud Run services and make them public, push images to this one
# repository, and deploy services that run as the runtime account. Nothing else.
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:${DEPLOY_EMAIL}" \
  --role roles/run.admin --condition None >/dev/null
gcloud artifacts repositories add-iam-policy-binding "$REPOSITORY" --project "$PROJECT_ID" --location "$REGION" \
  --member "serviceAccount:${DEPLOY_EMAIL}" --role roles/artifactregistry.writer >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_EMAIL" --project "$PROJECT_ID" \
  --member "serviceAccount:${DEPLOY_EMAIL}" --role roles/iam.serviceAccountUser >/dev/null
echo "Roles granted to ${DEPLOY_EMAIL}."

say "4/5 Keyless sign-in for GitHub Actions"
if ! exists gcloud iam workload-identity-pools describe "$POOL" --project "$PROJECT_ID" --location global; then
  gcloud iam workload-identity-pools create "$POOL" --project "$PROJECT_ID" --location global \
    --display-name "GitHub Actions"
fi
if ! exists gcloud iam workload-identity-pools providers describe "$PROVIDER" --project "$PROJECT_ID" --location global \
  --workload-identity-pool "$POOL"; then
  # Only tokens GitHub issues to this repository's main branch are accepted.
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --project "$PROJECT_ID" --location global \
    --workload-identity-pool "$POOL" --display-name "GitHub Actions" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository == '${GITHUB_REPO}' && assertion.ref == 'refs/heads/main'"
fi
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_EMAIL" --project "$PROJECT_ID" \
  --member "principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository/${GITHUB_REPO}" \
  --role roles/iam.workloadIdentityUser >/dev/null
echo "GitHub Actions on ${GITHUB_REPO}@main can act as ${DEPLOY_EMAIL}."

say "5/5 Budget alert at ${BUDGET_AMOUNT} ${CURRENCY}"
EXISTING="$(retry gcloud billing budgets list --billing-account "$BILLING_ACCOUNT" --billing-project "$PROJECT_ID" \
  --filter "displayName='${BUDGET_NAME}'" --format 'value(name)')"
if [ -n "$EXISTING" ]; then
  echo "Budget \"${BUDGET_NAME}\" already exists."
else
  # Credits are excluded so the alert tracks what the usage would cost, even while free-trial
  # credits are paying for it.
  gcloud billing budgets create --billing-account "$BILLING_ACCOUNT" --billing-project "$PROJECT_ID" \
    --display-name "$BUDGET_NAME" --budget-amount "${BUDGET_AMOUNT}${CURRENCY}" \
    --filter-projects "projects/${PROJECT_NUMBER}" --credit-types-treatment exclude-all-credits \
    --threshold-rule percent=0.5 --threshold-rule percent=1.0 >/dev/null
  echo "Budget created. Alerts go to the billing account's administrators by email."
fi

say "Done. Add these repository variables on GitHub (Settings > Secrets and variables > Actions > Variables):"
cat <<EOF
  gh variable set GCP_PROJECT_ID --repo ${GITHUB_REPO} --body "${PROJECT_ID}"
  gh variable set GCP_REGION --repo ${GITHUB_REPO} --body "${REGION}"
  gh variable set GCP_SERVICE_ACCOUNT --repo ${GITHUB_REPO} --body "${DEPLOY_EMAIL}"
  gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER --repo ${GITHUB_REPO} --body "${POOL_NAME}/providers/${PROVIDER}"

Then run the "api" workflow (Actions > api > Run workflow). The service will be at
  https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app
Once it answers, point the dashboard at it:
  gh variable set SIM_API_URL --repo ${GITHUB_REPO} --body "https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
EOF
