# Grant all permissions infra-forge-sa needs to:
#   (a) be the Cloud Build runtime SA + deploy the Cloud Run Job
#   (b) read Secret Manager + write to GCS bucket in the host project
#   (c) rotate service-account keys across all target projects
#
# Run once. Idempotent (gcloud add-iam-policy-binding is safe to re-run).

$SA       = "infra-forge-sa@ul-ce-p-902672-01-prj.iam.gserviceaccount.com"
$MEMBER   = "serviceAccount:$SA"
$HOST_PRJ = "ul-ce-p-902672-01-prj"
$BUCKET   = "infraforge-gcs"
$AR_REPO  = "infraforge"
$AR_LOC   = "asia-south1"

$TARGET_PROJECTS = @(
  "ul-ce-d-902156-prj","ul-ce-d-902676-prj","ul-ce-d-902563-prj","ul-ce-p-903673-prj",
  "ul-ce-d-903802-prj","ul-ce-p-904306-prj","ul-ce-d-903438-prj","ul-ce-p-903566-prj",
  "ul-ce-p-904063-prj","ul-ce-u-904064-prj","ul-ce-p-58664-prj","ul-ce-d-58093-prj",
  "ul-ce-p-902564-prj","ul-ce-d-902285-prj","ul-ce-p-902405-prj","ul-ce-p-902672-prj",
  "ul-cp-q-902589-01-prj","ul-cp-p-902593-prj","ul-cp-q-902589-prj","ul-ce-p-902672-01-prj",
  "ul-ce-u-903802-prj","ul-ce-d-903801-prj","ul-ce-p-903801-prj","ul-cp-d-58396-prj",
  "ul-ce-p-931274-prj","ul-cp-p-58415-prj","ul-ce-d-903617-prj","ul-ce-d-903673-prj",
  "ul-ce-d-901983-prj","ul-cp-q-903802-prj","ul-cp-p-903800-prj","ul-ce-d-902675-prj",
  "ul-ce-d-902279-prj","ul-ce-p-902674-prj","ul-cp-d-902619-prj","ul-ce-p-902295-prj",
  "ul-cp-p-902620-cp-prj","ul-ce-p-902673-prj","ul-cp-d-80067-prj","ul-cp-p-80070-prj",
  "ul-cp-d-902590-prj"
)

# ----------------------------------------------------------------------------
# 1. Host project roles (Cloud Build runtime + deploy + Secret Manager)
# ----------------------------------------------------------------------------
$HOST_ROLES = @(
  "roles/cloudbuild.builds.builder",      # run Cloud Build steps
  "roles/logging.logWriter",              # write build logs
  "roles/artifactregistry.writer",        # push images
  "roles/run.admin",                      # deploy Cloud Run Job
  "roles/iam.serviceAccountUser",         # actAs self (Cloud Run runtime SA)
  "roles/secretmanager.secretAccessor",   # read config from Secret Manager
  "roles/storage.objectAdmin"             # build artifacts + key tarball storage
)

Write-Host "===== Host project: $HOST_PRJ =====" -ForegroundColor Cyan
foreach ($role in $HOST_ROLES) {
  Write-Host "  - $role"
  gcloud projects add-iam-policy-binding $HOST_PRJ `
    --member=$MEMBER --role=$role --condition=None --quiet | Out-Null
}

# SA must be able to impersonate itself (Cloud Build deploy step assigns it as the Job runtime SA)
Write-Host "  - actAs on self"
gcloud iam service-accounts add-iam-policy-binding $SA `
  --member=$MEMBER --role="roles/iam.serviceAccountUser" `
  --project=$HOST_PRJ --quiet | Out-Null

# Bucket-scoped (also covered by project-level storage.objectAdmin, but explicit is safer)
Write-Host "  - bucket: gs://$BUCKET (objectAdmin)"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" `
  --member=$MEMBER --role="roles/storage.objectAdmin" --quiet | Out-Null

# Artifact Registry repo-scoped writer (in case project-level is too broad to grant)
Write-Host "  - AR repo: $AR_REPO ($AR_LOC) writer"
gcloud artifacts repositories add-iam-policy-binding $AR_REPO `
  --location=$AR_LOC --project=$HOST_PRJ `
  --member=$MEMBER --role="roles/artifactregistry.writer" --quiet | Out-Null

# ----------------------------------------------------------------------------
# 2. Target project roles (key rotation across all 41 projects)
# ----------------------------------------------------------------------------
$TARGET_ROLES = @(
  "roles/iam.serviceAccountKeyAdmin",     # list / create / delete SA keys
  "roles/iam.serviceAccountViewer",       # list service accounts in project
  "roles/browser"                         # read project metadata (display name, etc.)
)

foreach ($prj in $TARGET_PROJECTS) {
  Write-Host "`n===== Target project: $prj =====" -ForegroundColor Yellow
  foreach ($role in $TARGET_ROLES) {
    Write-Host "  - $role"
    gcloud projects add-iam-policy-binding $prj `
      --member=$MEMBER --role=$role --condition=None --quiet | Out-Null
  }
}

Write-Host "`nDone." -ForegroundColor Green
