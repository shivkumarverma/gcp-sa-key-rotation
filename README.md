# GCP Service Account Key Rotation

Automated rotation and expiry monitoring for GCP service account keys, deployed as a Cloud Run Job. Scans configured projects, rotates expiring keys using asymmetric RSA cryptography, stores credentials to GCS, and emails a formatted report to stakeholders.

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [How It Works](#2-how-it-works)
3. [Architecture](#3-architecture)
4. [Code Structure](#4-code-structure)
5. [Configuration](#5-configuration)
6. [Deployment](#6-deployment)
7. [Required Permissions (IAM)](#7-required-permissions-iam)
8. [Infrastructure Details](#8-infrastructure-details)
9. [Advantages](#9-advantages)
10. [Limitations](#10-limitations)
11. [Operational Runbook](#11-operational-runbook)

---

## 1. Purpose

GCP service account keys expire (by org policy or key rotation requirements) and must be regularly rotated to maintain access continuity. Manual rotation is error-prone and difficult to audit at scale. This tool automates the full lifecycle:

| Capability | Description |
|---|---|
| **Scan** | Discovers all user-managed keys across multiple GCP projects |
| **Expiry detection** | Flags keys expiring within a configurable threshold (default 14 days) |
| **Rotation** | Generates a new RSA key pair, uploads the public cert to GCP, stores the new JSON credential |
| **Validation** | Verifies the new key works by obtaining an access token (with retries for GCP propagation) |
| **Reporting** | Sends an HTML email with an Excel attachment summarising all results |

### Two Modes

- **ROTATE mode** (`ENABLE_ROTATION=true`): Scans and rotates expiring keys. Default mode.
- **SCAN ONLY mode** (`ENABLE_ROTATION=false`): Audits expiry status without rotating. Use for reporting or dry-runs.

---

## 2. How It Works

### End-to-End Flow

```
Cloud Run Job Triggered (scheduled or manual)
        │
        ▼
┌──────────────────────────────────────────────────┐
│  BOOTSTRAP                                       │
│  Cloud Run's attached SA → Secret Manager        │
│  Fetch main SA credentials JSON from secret      │
│  Rebuild Secret Manager client with main SA      │
│  Load all config from Secret Manager secrets     │
└──────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────┐
│  SCAN                                            │
│  For each project in GCP_PROJECTS:               │
│    List all service accounts (IAM v1)            │
│    For each SA: list USER_MANAGED keys           │
│    Evaluate only the most recently created key   │
│    Flag if expiring within threshold             │
└──────────────────────────────────────────────────┘
        │
        ▼ (ROTATE mode only)
┌──────────────────────────────────────────────────┐
│  ROTATE (per expiring key)                       │
│  1. Generate RSA-2048 key pair (offline)         │
│  2. Wrap public key in self-signed X.509 cert    │
│  3. Upload X.509 cert to GCP IAM → new key ID   │
│  4. Assemble standard SA JSON credential         │
│  5. Store JSON to GCS (or local)                 │
│  6. Validate: get access token (3 retries)       │
└──────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────┐
│  REPORT                                          │
│  Build Excel report (all results)                │
│  Build HTML email (metrics + key table)          │
│  Send via Azure Communication Services           │
│  Fallback to Gmail SMTP on 429 rate-limit        │
└──────────────────────────────────────────────────┘
        │
        ▼
  Exit 0 (all OK) or Exit 1 (any rotation failed)
```

### Key Rotation — Cryptography Detail

GCP supports **external key upload**: you generate the key pair yourself, upload only the public key (as an X.509 certificate), and GCP assigns a key ID. The private key **never leaves your environment**.

```
  Your environment                 GCP IAM
  ─────────────────                ──────────────────────
  RSA-2048 private key  (kept)
  RSA-2048 public key
       └─ wrapped in X.509 cert ──→ upload_public_key()
                                     └─ GCP assigns key_id
  Assemble SA JSON:
    {
      "type": "service_account",
      "private_key": "<RSA private key PEM>",
      "private_key_id": "<key_id from GCP>",
      ...
    }
       └─ stored in GCS ──────────→ available to consumers
```

### Key Validation with Retry

After uploading, GCP takes up to ~30 seconds to propagate the new key. The validator retries 3 times with 10-second delays before marking validation as failed — it does **not** roll back the key if validation fails, since propagation may still succeed.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        GCP Project: finops-billing-central-prod │
│                                                                 │
│  ┌──────────────────┐      ┌─────────────────────────────────┐  │
│  │  Cloud Run Job   │─────▶│       Secret Manager            │  │
│  │  (this service)  │      │  - SA credentials JSON          │  │
│  │                  │      │  - GCP_PROJECTS list            │  │
│  │  Attached SA:    │      │  - EMAIL_REPORTS_TO             │  │
│  │  cloud-run-sa    │      │  - EXPIRY_THRESHOLD_DAYS        │  │
│  └──────────────────┘      │  - ENABLE_ROTATION              │  │
│           │                │  - ACS/Gmail credentials        │  │
│           │                └─────────────────────────────────┘  │
│           │                                                     │
│           │         ┌──────────────────────────────────────┐    │
│           └────────▶│        GCS Bucket                    │    │
│                     │  gcp-bucket-sa-keys-store            │    │
│                     │  service-account-keys/               │    │
│                     │    {project}/{sa_name}/{key_id}.json │    │
│                     └──────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
           │
           │  IAM v1 API calls (list/rotate keys)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Target Projects (any number, e.g. project-a, project-b, ...)  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ SA: svc-app1 │  │ SA: svc-app2 │  │ SA: svc-analytics... │  │
│  │ key expiring │  │ key OK       │  │ key rotated          │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │
           │  Email delivery
           ▼
┌──────────────────────┐     ┌───────────────────────────┐
│  Azure Communication │  or │  Gmail SMTP (fallback)    │
│  Services (ACS)      │     │  smtp.gmail.com:587       │
└──────────────────────┘     └───────────────────────────┘
           │
           ▼
   Recipients defined in EMAIL_REPORTS_TO
```

---

## 4. Code Structure

```
gcp-sa-key-rotation/
├── main.py                  # Entry point: orchestration, report, email
├── requirements.txt         # Python dependencies
├── .env                     # Bootstrap env vars (not committed)
├── config.yaml              # Deprecated (config now in Secret Manager)
├── keys/                    # Local key storage (used when STORAGE_BACKEND=local)
└── src/
    ├── config.py            # 2-step bootstrap + AppConfig dataclass
    ├── gcp_client.py        # Thin GCP IAM v1 API wrapper (no business logic)
    ├── key_manager.py       # RSA key generation, X.509 certs, JSON assembly
    ├── rotator.py           # Core orchestration: scan, rotate, validate
    ├── storage.py           # Storage abstraction: GCSStorage / LocalStorage
    ├── acs_email_client.py  # Email delivery: ACS primary + Gmail fallback
    └── email_template.py    # HTML email builder with metrics card + table
```

### Module Responsibilities

| Module | Responsibility |
|---|---|
| `main.py` | Top-level orchestration, exit codes, report generation, email dispatch |
| `config.py` | 2-step Secret Manager bootstrap, `AppConfig` dataclass |
| `gcp_client.py` | Stateless GCP IAM API wrapper — list SAs, list keys, upload public cert |
| `key_manager.py` | Offline cryptography — RSA pair generation, X.509 wrapping, JSON assembly |
| `rotator.py` | Business logic — expiry check, rotation workflow, key validation, per-SA error handling |
| `storage.py` | Storage abstraction — `GCSStorage` (cleans old keys) and `LocalStorage` |
| `acs_email_client.py` | Dual-path email — ACS with 429 fallback to Gmail SMTP |
| `email_template.py` | Responsive HTML email with metrics, colour-coded status table |

---

## 5. Configuration

### Bootstrap Environment Variables (`.env` / Cloud Run env)

These are the only variables needed before Secret Manager is accessible:

| Variable | Required | Description |
|---|---|---|
| `SECRET_MANAGER_PROJECT_ID` | Yes | GCP project that owns the secrets |
| `SERVICE_ACCOUNT_SECRET_ID` | Yes | Secret ID containing the main SA JSON |
| `SECRET_MANAGER_VERSION` | No | Secret version (default: `latest`) |
| `LOG_LEVEL` | No | Logging level: `DEBUG`, `INFO`, `WARNING` (default: `INFO`) |

### Secrets Loaded from Secret Manager

All operational configuration is stored in Secret Manager and fetched at runtime:

| Secret ID | Default | Description |
|---|---|---|
| `GCP_PROJECTS` | — | Comma-separated list of project IDs to scan |
| `EMAIL_REPORTS_TO` | — | Comma-separated email recipients |
| `EXPIRY_THRESHOLD_DAYS` | `14` | Days before expiry to flag/rotate |
| `ENABLE_ROTATION` | `true` | `true` = rotate; `false` = scan only |
| `STORAGE_BACKEND` | `gcs` | `gcs` or `local` |
| `GCS_BUCKET` | `gcp-bucket-sa-keys-store` | GCS bucket for key storage |
| `LOCAL_DIR` | `./keys` | Local path (used when `STORAGE_BACKEND=local`) |
| `EMAIL_SUBJECT` | `GCP Service Account Key Report` | Email subject prefix |
| `ACS_CONNECTION_STRING` | — | Azure Communication Services connection string |
| `ACS_SENDER_ADDRESS` | — | ACS sender email address |
| `GMAIL_USER` | — | Gmail address (SMTP fallback) |
| `GMAIL_APP_PASSWORD` | — | Gmail app-specific password (SMTP fallback) |

---

## 6. Deployment

### Prerequisites

1. A GCP project to host the Cloud Run Job (referred to as the **host project**)
2. A service account for the Cloud Run Job (the **attached SA**)
3. A Secret Manager secret containing the **main service account JSON** that has access to target projects
4. Target project service account key management permissions

### Step-by-Step Deployment

#### 1. Create the Cloud Run Attached SA

```bash
gcloud iam service-accounts create cloud-run-rotator-sa \
  --display-name="Cloud Run Key Rotator" \
  --project=finops-billing-central-prod
```

#### 2. Grant Secret Manager Access to Attached SA

```bash
# Access to the secret holding the main SA credentials
gcloud secrets add-iam-policy-binding SERVICE_ACCOUNT_SECRET_ID \
  --member="serviceAccount:cloud-run-rotator-sa@finops-billing-central-prod.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=finops-billing-central-prod

# Access to all config secrets
gcloud projects add-iam-policy-binding finops-billing-central-prod \
  --member="serviceAccount:cloud-run-rotator-sa@finops-billing-central-prod.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

#### 3. Build and Push Container

```bash
# Build
docker build -t gcr.io/finops-billing-central-prod/gcp-sa-key-rotation:latest .

# Push
docker push gcr.io/finops-billing-central-prod/gcp-sa-key-rotation:latest
```

Or using Cloud Build:

```bash
gcloud builds submit --tag gcr.io/finops-billing-central-prod/gcp-sa-key-rotation:latest \
  --project=finops-billing-central-prod
```

#### 4. Deploy as Cloud Run Job

```bash
gcloud run jobs create gcp-sa-key-rotation \
  --image=gcr.io/finops-billing-central-prod/gcp-sa-key-rotation:latest \
  --region=us-central1 \
  --service-account=cloud-run-rotator-sa@finops-billing-central-prod.iam.gserviceaccount.com \
  --set-env-vars="SECRET_MANAGER_PROJECT_ID=finops-billing-central-prod,SERVICE_ACCOUNT_SECRET_ID=gcp-sa-rotator-credentials,LOG_LEVEL=INFO" \
  --max-retries=1 \
  --task-timeout=600 \
  --project=finops-billing-central-prod
```

#### 5. Schedule with Cloud Scheduler

```bash
gcloud scheduler jobs create http gcp-sa-key-rotation-schedule \
  --location=us-central1 \
  --schedule="0 8 * * 1" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/finops-billing-central-prod/jobs/gcp-sa-key-rotation:run" \
  --message-body='{}' \
  --oauth-service-account-email=cloud-run-rotator-sa@finops-billing-central-prod.iam.gserviceaccount.com \
  --project=finops-billing-central-prod
```

This runs the job every Monday at 08:00 UTC.

#### 6. Manual Execution

```bash
gcloud run jobs execute gcp-sa-key-rotation \
  --region=us-central1 \
  --project=finops-billing-central-prod
```

### Dockerfile (Example)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

---

## 7. Required Permissions (IAM)

### Cloud Run Attached SA (bootstrap SA)

Needs only Secret Manager read access on the **host project**:

| Role | Scope | Purpose |
|---|---|---|
| `roles/secretmanager.secretAccessor` | Host project | Read all config secrets |

### Main Service Account (loaded from Secret Manager)

This SA performs all actual operations. It needs permissions on **each target project**:

| Role | Scope | Purpose |
|---|---|---|
| `roles/iam.serviceAccountKeyAdmin` | Target project | List, create, delete SA keys |
| `roles/iam.serviceAccountViewer` | Target project | List service accounts |
| `roles/storage.objectAdmin` | GCS bucket | Read/write/delete key JSON files |
| `roles/resourcemanager.projectViewer` | Target project | Fetch project display names |

Grant per target project:

```bash
export MAIN_SA="main-rotator-sa@finops-billing-central-prod.iam.gserviceaccount.com"
export TARGET_PROJECT="your-target-project-id"

gcloud projects add-iam-policy-binding $TARGET_PROJECT \
  --member="serviceAccount:$MAIN_SA" \
  --role="roles/iam.serviceAccountKeyAdmin"

gcloud projects add-iam-policy-binding $TARGET_PROJECT \
  --member="serviceAccount:$MAIN_SA" \
  --role="roles/iam.serviceAccountViewer"

gcloud projects add-iam-policy-binding $TARGET_PROJECT \
  --member="serviceAccount:$MAIN_SA" \
  --role="roles/resourcemanager.projectViewer"
```

Grant on GCS bucket:

```bash
gsutil iam ch serviceAccount:$MAIN_SA:roles/storage.objectAdmin \
  gs://gcp-bucket-sa-keys-store
```

### Minimal Permission Summary

```
finops-billing-central-prod (host project)
├── cloud-run-rotator-sa  →  secretmanager.secretAccessor
└── main-rotator-sa       →  (credentials stored in Secret Manager)

target-project-a / target-project-b / ...
└── main-rotator-sa  →  iam.serviceAccountKeyAdmin
                     →  iam.serviceAccountViewer
                     →  resourcemanager.projectViewer

gs://gcp-bucket-sa-keys-store
└── main-rotator-sa  →  storage.objectAdmin
```

---

## 8. Infrastructure Details

### GCS Bucket: `gcp-bucket-sa-keys-store`

- **Purpose**: Persistent store for rotated service account JSON credentials
- **Path structure**: `service-account-keys/{project_id}/{sa_email}/{key_id}.json`
- **Retention**: GCSStorage deletes all previous keys for a service account when saving a new one (always keeps only the latest)
- **Recommended settings**:
  - Uniform bucket-level access (no ACLs)
  - Customer-managed encryption keys (CMEK) recommended
  - Versioning: optional (old versions are explicitly deleted)
  - Location: same region as Cloud Run Job for lower latency

### Secret Manager Secrets

All secrets should be in the **host project** (`finops-billing-central-prod`):

| Secret ID | Format | Example |
|---|---|---|
| `gcp-sa-rotator-credentials` | JSON | Standard GCP SA JSON key file |
| `GCP_PROJECTS` | Plaintext | `project-a,project-b,project-c` |
| `EMAIL_REPORTS_TO` | Plaintext | `ops@company.com,team@company.com` |
| `ACS_CONNECTION_STRING` | Plaintext | `endpoint=https://...` |
| `ACS_SENDER_ADDRESS` | Plaintext | `noreply@company.com` |
| `GMAIL_USER` | Plaintext | `alerts@company.com` |
| `GMAIL_APP_PASSWORD` | Plaintext | Gmail app-specific password |

### Cloud Run Job Settings

| Setting | Recommended Value | Reason |
|---|---|---|
| CPU | 1 vCPU | Key generation and API calls are not CPU-intensive |
| Memory | 512 MiB | Sufficient for all operations |
| Task timeout | 600s (10 min) | Allows for large project scans + retries |
| Max retries | 1 | Idempotent — safe to retry once on transient failures |
| Concurrency | 1 | Single task per execution |
| Region | Match target projects | Reduces API latency |

### Cloud Scheduler

| Setting | Value |
|---|---|
| Schedule | `0 8 * * 1` (Mondays 08:00 UTC) |
| HTTP method | POST |
| Auth | OAuth — Cloud Run invoker role on attached SA |

Adjust schedule based on `EXPIRY_THRESHOLD_DAYS`. If threshold is 14 days, weekly runs are sufficient.

---

## 9. Advantages

### Security

- **Private key never sent to GCP**: Only the X.509 public certificate is uploaded via `upload_public_key()`. The private key is assembled into the JSON credential and stored directly in GCS.
- **Credentials in Secret Manager**: No hardcoded secrets in code or environment variables (beyond the bootstrap pointers).
- **Least privilege**: The attached Cloud Run SA only reads secrets — all GCP operations are performed by the main SA loaded at runtime.
- **Audit trail**: GCS stores each new key JSON; Cloud Audit Logs record every key creation event.

### Operational

- **Multi-project**: Scans any number of GCP projects in a single run.
- **Per-SA error isolation**: A failure on one service account does not stop processing of others.
- **Non-destructive scan mode**: `ENABLE_ROTATION=false` gives full visibility without making changes — useful for audits and planning.
- **Key validation**: Confirms the new key actually works before marking the rotation as successful.
- **Retry on propagation delay**: GCP can take ~30s to propagate new keys; the validator retries with backoff.
- **Dual email path**: ACS Email as primary with Gmail SMTP as fallback — reduces single points of failure in alerting.
- **Detailed reporting**: Colour-coded HTML email + Excel attachment with all key details for stakeholder distribution.

### Maintainability

- Configuration-driven: all thresholds, project lists, and email addresses are in Secret Manager — no redeployment needed to change them.
- Clean module separation: cryptography, IAM, storage, and email are fully decoupled and independently testable.
- `key_manager.py` has zero GCP dependencies — can be tested offline.

---

## 10. Limitations

| Limitation | Detail |
|---|---|
| **One key per SA evaluated** | Only the most recently created user-managed key is checked. If a SA has multiple keys, older ones are ignored. |
| **No old key deletion** | The tool does not delete the old key after rotation. Old keys remain valid until their expiry or manual removal. |
| **No consumer update** | After rotating a key, the tool stores the new JSON in GCS. It does not push the new credential to the applications consuming the old key — that integration must be handled separately. |
| **X.509 cert validity** | The self-signed cert uploaded to GCP has a 90-day validity (matching `openssl` default). This is the key's validity window in GCP; the JSON credential is independently valid until the key is deleted. |
| **No key deletion on validation failure** | If key validation fails after rotation, the new key remains in GCP. Manual cleanup or re-run is needed. |
| **Single region deployment** | Cloud Run Jobs run in one region; cross-region latency to target project APIs is minimal but non-zero. |
| **ACS rate limits** | ACS Email has per-minute send limits. Heavy report volumes may trigger 429s (handled by fallback, but Gmail also has rate limits). |
| **Secret Manager cost** | Each secret access is a billable operation. With many secrets and frequent runs, cost should be monitored. |
| **No Terraform / IaC** | Infrastructure provisioning (bucket, secrets, Cloud Run Job, Scheduler) is manual or scripted — no Terraform modules are included in this repo. |

---

## 11. Operational Runbook

### Check if the job ran successfully

```bash
gcloud run jobs executions list \
  --job=gcp-sa-key-rotation \
  --region=us-central1 \
  --project=finops-billing-central-prod
```

### View logs for a specific execution

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="gcp-sa-key-rotation"' \
  --limit=200 \
  --project=finops-billing-central-prod \
  --format="value(timestamp, textPayload)"
```

### Trigger a scan-only run (no rotation)

Temporarily set `ENABLE_ROTATION` secret to `false`, then execute:

```bash
gcloud run jobs execute gcp-sa-key-rotation \
  --region=us-central1 \
  --project=finops-billing-central-prod
```

### Add a new project to scan

```bash
# Fetch current value, append new project, update secret
gcloud secrets versions access latest \
  --secret=GCP_PROJECTS \
  --project=finops-billing-central-prod \
  | echo "$(cat),new-project-id" \
  | gcloud secrets versions add GCP_PROJECTS \
    --data-file=- \
    --project=finops-billing-central-prod
```

Then grant permissions on the new project (see [Section 7](#7-required-permissions-iam)).

### Verify rotated key in GCS

```bash
gsutil ls gs://gcp-bucket-sa-keys-store/service-account-keys/YOUR_PROJECT/
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | All operations completed successfully |
| `1` | One or more key rotations failed (check logs and email report) |
