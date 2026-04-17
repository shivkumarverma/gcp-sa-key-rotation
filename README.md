# GCP Service Account Key Rotation Automation

**Cloud Run Job-Based Secure Key Lifecycle Management**

**Developed by the DevOps Team @ Movate**

| Role | Name | Contact |
|---|---|---|
| Team Lead | Vignesh Nagachalavelavan | Vignesh.Nagachalavelavan01@movate.com |
| Engineer | Shiv Kumar Verma | ShivKumar.Verma@movate.com |
| Engineer | Srigopinath Angamuthu Raja | Srigopinath.AngamuthuRaja@movate.com |
| DevOps Engineers | Movate DevOps Team | — |

📄 **Full Documentation (PDF):** [service-account-key-rotation-documentation.pdf](docs/service-account-key-rotation-documenatation.pdf)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Business Problem](#2-business-problem)
3. [Solution Overview](#3-solution-overview)
4. [High-Level Architecture (HLD)](#4-high-level-architecture-hld)
5. [Low-Level Design (LLD)](#5-low-level-design-lld)
6. [Key Technical Highlights](#6-key-technical-highlights)
7. [Key Rotation Policy & Behavior](#7-key-rotation-policy--behavior)
8. [Technology Stack](#8-technology-stack)
9. [Code Structure](#9-code-structure)
10. [Configuration](#10-configuration)
11. [Deployment](#11-deployment)
12. [IAM & Security Model](#12-iam--security-model)
13. [Infrastructure Details](#13-infrastructure-details)
14. [Advantages](#14-advantages)
15. [Limitations](#15-limitations)
16. [Use Cases](#16-use-cases)
17. [Team Scope of Work & Key Distribution](#17-team-scope-of-work--key-distribution)
18. [Operational Runbook](#18-operational-runbook)
19. [Final Outcome](#19-final-outcome)

---

## 1. Executive Summary

This solution automates the **detection, rotation, validation, and reporting** of Google Cloud service account keys across multiple GCP projects.

It eliminates:
- Manual key rotation risks
- Expiry-related outages
- Security vulnerabilities due to long-lived credentials

### Key Outcomes

| Outcome | Description |
|---|---|
| **Secure** | Private key never leaves your environment; only the public certificate is sent to GCP |
| **Automated** | Fully scheduled key lifecycle — no human intervention required |
| **Scalable** | Multi-project support across any number of GCP projects |
| **Auditable** | Logs, reports, and GCS storage tracking for every rotation event |

> **Zero-downtime rotation** is ensured through overlapping key validity and controlled distribution. The old key remains active in GCP IAM until the application team updates their credentials.

---

## 2. Business Problem

| Challenge | Impact |
|---|---|
| Manual key rotation | Human error, missed expiries |
| No centralised visibility | Poor governance, no audit trail |
| Expired keys | Application downtime |
| Long-lived credentials | Increased security risk surface |

---

## 3. Solution Overview

A Cloud Run Job executes on a schedule to:

1. **Scan** all configured GCP projects for user-managed service account keys
2. **Identify** keys expiring within a configurable threshold (default: 14 days)
3. **Rotate** keys securely using RSA-2048 asymmetric cryptography
4. **Store** new credentials in GCS with controlled access
5. **Validate** that the new key works, with retry logic for GCP propagation delay
6. **Report** results via a colour-coded HTML email and an Excel attachment

### Two Operating Modes

| Mode | Setting | Behaviour |
|---|---|---|
| **Rotate Mode** | `ENABLE_ROTATION=true` | Full rotation — scans and rotates all expiring keys. **Default.** |
| **Scan Mode** | `ENABLE_ROTATION=false` | Audit only — reports expiry status without making any changes. |

---

## 4. High-Level Architecture (HLD)

### Component Overview

| Component | Role |
|---|---|
| Cloud Run Job | Execution engine — runs the full rotation workflow |
| Secret Manager | Stores all configuration and the main SA credentials |
| IAM API | Key listing, creation, and public key upload |
| GCS Bucket | Persistent storage for rotated key JSON files |
| Email Service | ACS Email (primary) + Gmail SMTP (fallback) |
| Cloud Scheduler | Triggers the Cloud Run Job on a cron schedule |

### Architecture Diagram

![HLD Architecture](docs/images/hld-architecture.png)

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
           │  IAM v1 API calls (list / rotate keys)
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

## 5. Low-Level Design (LLD)

### Execution Flow

```
Trigger → Bootstrap → Scan → Rotate → Validate → Report
```

### Detailed Phase Breakdown

```
Cloud Run Job Triggered (scheduled or manual)
        │
        ▼
┌──────────────────────────────────────────────────┐
│  PHASE 1 — BOOTSTRAP                             │
│  Cloud Run's attached SA → Secret Manager        │
│  Fetch main SA credentials JSON from secret      │
│  Rebuild Secret Manager client with main SA      │
│  Load all operational config from SM secrets     │
└──────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────┐
│  PHASE 2 — SCAN                                  │
│  For each project in GCP_PROJECTS:               │
│    List all service accounts (IAM v1 API)        │
│    For each SA: list USER_MANAGED keys only      │
│    Evaluate only the most recently created key   │
│    Flag if expiring within EXPIRY_THRESHOLD_DAYS │
└──────────────────────────────────────────────────┘
        │
        ▼ (ROTATE mode only — skipped in SCAN mode)
┌──────────────────────────────────────────────────┐
│  PHASE 3 — ROTATE (per expiring key)             │
│  1. Generate RSA-2048 key pair (offline)         │
│  2. Wrap public key in self-signed X.509 cert    │
│  3. Upload X.509 cert to GCP IAM → new key ID   │
│  4. Assemble standard SA JSON credential file   │
│  5. Store JSON to GCS bucket (or local)          │
└──────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────┐
│  PHASE 4 — VALIDATE                              │
│  Attempt to obtain an access token with new key  │
│  Retry up to 3× with 10s delay (GCP propagation)│
│  Record validation result (Pass / Fail)          │
└──────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────┐
│  PHASE 5 — REPORT                                │
│  Build Excel report (all results, all projects)  │
│  Build HTML email (metrics card + key table)     │
│  Send via Azure Communication Services (ACS)     │
│  Fallback to Gmail SMTP on ACS 429 rate-limit    │
└──────────────────────────────────────────────────┘
        │
        ▼
  Exit 0 (all OK) or Exit 1 (any rotation failed)
```

### Cryptography Detail — Why the Private Key Never Leaves

GCP supports **external key upload**: you generate the RSA key pair locally, upload only the public key wrapped in an X.509 certificate, and GCP assigns a key ID. The private key never travels over the network to GCP.

```
  Your environment                      GCP IAM
  ──────────────────────────            ────────────────────────
  RSA-2048 private key  (stays here)
  RSA-2048 public key
       └─ wrapped in X.509 cert  ──────▶ upload_public_key()
                                          └─ GCP assigns key_id
  Assemble SA JSON credential:
    {
      "type":             "service_account",
      "private_key":      "<RSA private key PEM>",
      "private_key_id":   "<key_id returned by GCP>",
      ...
    }
       └─ stored in GCS  ──────────────▶ available to authorised consumers
```

---

## 6. Key Technical Highlights

### Security

- Private key is generated **offline** and never sent to GCP
- Only the X.509 public certificate is uploaded via `upload_public_key()`
- All sensitive configuration lives in Secret Manager — zero hardcoded credentials

### Flexibility

- **Rotate Mode** — active rotation of expiring keys
- **Scan Mode** — audit-only reporting without any changes

### Reliability

- Per-service-account error isolation — one failure does not block other SAs
- Key validation with 3 retries + 10-second delays (accommodates ~30s GCP propagation window)
- Dual email delivery path: ACS primary → Gmail SMTP fallback

### Reporting

- Colour-coded HTML email with metrics summary and key details table
- Full Excel attachment with 10-column report, auto-filter, and row colour-coding
- Stakeholder-friendly format suitable for governance reviews

![Sample Email Report](docs/images/sample-email-report.png)

![Sample Excel Report](docs/images/sample-excel-report.png)

---

## 7. Key Rotation Policy & Behavior

### Rotation Policy

- Keys are rotated **14 days before expiry** (configurable)
- Controlled via the `EXPIRY_THRESHOLD_DAYS` secret in Secret Manager

```
EXPIRY_THRESHOLD_DAYS = 14
```

### Behavior in GCP IAM

When a key is rotated:

- A **new key is created** in GCP IAM via public cert upload
- The **existing (old) key remains active** — it is NOT deleted automatically

This ensures:
- **Zero downtime** — applications continue using the old key until updated
- **Safe transition** — teams have time to update credentials before the old key expires

### Behavior in GCS Bucket

- Only the **latest rotated key is stored** per service account
- All previous key files for a SA are **automatically deleted** when a new key is saved
- Consumers always find exactly one key file per SA path

### Summary

| Aspect | Behavior |
|---|---|
| Rotation trigger | 14 days before expiry (configurable) |
| GCP IAM keys after rotation | Old + New coexist until old key expires |
| GCS storage | Latest key only — older files auto-deleted |
| Application downtime | None — old key remains valid during transition |

---

## 8. Technology Stack

| Layer | Technology |
|---|---|
| Compute | Google Cloud Run Jobs |
| Scheduler | Google Cloud Scheduler |
| Secrets | Google Secret Manager |
| Storage | Google Cloud Storage (GCS) |
| IAM | GCP IAM v1 REST API |
| Cryptography | Python `cryptography` library (RSA-2048, X.509) |
| Email (primary) | Azure Communication Services (ACS) Email |
| Email (fallback) | Gmail SMTP (`smtp.gmail.com:587`, STARTTLS) |
| Reporting | `openpyxl` (Excel), HTML (email template) |
| Language | Python 3.11 |

---

## 9. Code Structure

```
gcp-sa-key-rotation/
├── main.py                  # Entry point: orchestration, report, email dispatch
├── requirements.txt         # Python dependencies
├── .env                     # Bootstrap env vars (not committed to version control)
├── config.yaml              # Deprecated — config now fully in Secret Manager
├── keys/                    # Local key storage (only when STORAGE_BACKEND=local)
└── src/
    ├── config.py            # 2-step Secret Manager bootstrap + AppConfig dataclass
    ├── gcp_client.py        # Thin GCP IAM v1 API wrapper (no business logic)
    ├── key_manager.py       # RSA key generation, X.509 certs, JSON credential assembly
    ├── rotator.py           # Core logic: scan, rotate, validate, per-SA error handling
    ├── storage.py           # Storage abstraction: GCSStorage / LocalStorage
    ├── acs_email_client.py  # Email delivery: ACS primary + Gmail SMTP fallback
    └── email_template.py    # Responsive HTML email builder: metrics card + status table
```

### Module Responsibilities

| Module | Responsibility |
|---|---|
| `main.py` | Top-level orchestration, exit codes, report generation, email dispatch |
| `config.py` | 2-step Secret Manager bootstrap, `AppConfig` dataclass |
| `gcp_client.py` | Stateless IAM API wrapper — list SAs, list keys, upload public cert |
| `key_manager.py` | Offline cryptography — RSA pair, X.509 wrapping, JSON credential assembly |
| `rotator.py` | Business logic — expiry check, rotation, validation, per-SA error isolation |
| `storage.py` | Storage abstraction — `GCSStorage` (auto-cleans old keys), `LocalStorage` |
| `acs_email_client.py` | Dual-path email — ACS with 429 fallback to Gmail SMTP |
| `email_template.py` | Responsive HTML email with metrics card and colour-coded status table |

### Module Interaction Map

```
main.py (entry point)
  │
  ├─▶ config.py           Load bootstrap vars → fetch SA from SM → load all secrets
  │
  ├─▶ gcp_client.py       Build IAM client
  │
  ├─▶ rotator.py          Orchestrate scan + rotation
  │     ├─▶ gcp_client.py   List SAs and keys; upload public cert
  │     ├─▶ key_manager.py  Generate RSA pair, assemble JSON credential
  │     └─▶ storage.py      Save rotated key to GCS or local
  │
  ├─▶ excel_builder.py    Build XLSX report
  │
  ├─▶ email_template.py   Build HTML email body
  │
  └─▶ acs_email_client.py Send email (ACS → Gmail fallback)
```

---

## 10. Configuration

### Bootstrap Environment Variables

Set these directly on the Cloud Run Job (or in `.env` for local runs). They are the only variables needed before Secret Manager is reachable:

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_MANAGER_PROJECT_ID` | Yes | — | GCP project that owns the secrets |
| `SERVICE_ACCOUNT_SECRET_ID` | Yes | — | Secret ID containing the main SA JSON |
| `SECRET_MANAGER_VERSION` | No | `latest` | Secret version to fetch |
| `LOG_LEVEL` | No | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING` |

### Secrets Loaded from Secret Manager

All operational configuration is stored in Secret Manager and loaded at runtime — no redeployment is needed to change these values:

| Secret ID | Default | Description |
|---|---|---|
| `GCP_PROJECTS` | — | Comma-separated list of project IDs to scan |
| `EMAIL_REPORTS_TO` | — | Comma-separated email recipients |
| `EXPIRY_THRESHOLD_DAYS` | `14` | Days before expiry to flag / rotate |
| `ENABLE_ROTATION` | `true` | `true` = rotate mode; `false` = scan only |
| `STORAGE_BACKEND` | `gcs` | `gcs` or `local` |
| `GCS_BUCKET` | `gcp-bucket-sa-keys-store` | GCS bucket for key JSON storage |
| `LOCAL_DIR` | `./keys` | Local path (only used when `STORAGE_BACKEND=local`) |
| `EMAIL_SUBJECT` | `GCP Service Account Key Report` | Email subject prefix |
| `ACS_CONNECTION_STRING` | — | Azure Communication Services connection string |
| `ACS_SENDER_ADDRESS` | — | ACS sender email address |
| `GMAIL_USER` | — | Gmail address for SMTP fallback |
| `GMAIL_APP_PASSWORD` | — | Gmail app-specific password for SMTP fallback |

---

## 11. Deployment

### Prerequisites

1. A GCP project to host the Cloud Run Job (the **host project**)
2. A service account attached to the Cloud Run Job (the **attached SA**)
3. A Secret Manager secret containing the **main service account JSON** with access to target projects
4. IAM permissions on all target projects (see [Section 12](#12-iam--security-model))

### Step-by-Step Deployment

#### 1. Create the Cloud Run Attached SA

```bash
gcloud iam service-accounts create cloud-run-rotator-sa \
  --display-name="Cloud Run Key Rotator" \
  --project=finops-billing-central-prod
```

#### 2. Grant Secret Manager Access to the Attached SA

```bash
# Grant access to the specific secret holding the main SA credentials
gcloud secrets add-iam-policy-binding SERVICE_ACCOUNT_SECRET_ID \
  --member="serviceAccount:cloud-run-rotator-sa@finops-billing-central-prod.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=finops-billing-central-prod

# Grant access to all config secrets in the host project
gcloud projects add-iam-policy-binding finops-billing-central-prod \
  --member="serviceAccount:cloud-run-rotator-sa@finops-billing-central-prod.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

#### 3. Build and Push the Container

```bash
# Build
docker build -t gcr.io/finops-billing-central-prod/gcp-sa-key-rotation:latest .

# Push
docker push gcr.io/finops-billing-central-prod/gcp-sa-key-rotation:latest
```

Or using Cloud Build (no local Docker required):

```bash
gcloud builds submit \
  --tag gcr.io/finops-billing-central-prod/gcp-sa-key-rotation:latest \
  --project=finops-billing-central-prod
```

#### 4. Deploy as a Cloud Run Job

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

This triggers the job every Monday at 08:00 UTC. Adjust the cron expression to match your `EXPIRY_THRESHOLD_DAYS` setting.

#### 6. Manual Execution

```bash
gcloud run jobs execute gcp-sa-key-rotation \
  --region=us-central1 \
  --project=finops-billing-central-prod
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

---

## 12. IAM & Security Model

### Two-Layer Authentication

| Layer | Service Account | Purpose |
|---|---|---|
| Layer 1 — Bootstrap | Cloud Run attached SA | Reads Secret Manager secrets; no other permissions needed |
| Layer 2 — Operations | Main SA (loaded from Secret Manager) | Performs all key operations across target projects |

This separation means the Cloud Run Job itself has minimal standing permissions. The main SA credentials are fetched at runtime and used only for the duration of the job.

### Required Roles

#### Cloud Run Attached SA (host project only)

| Role | Scope |
|---|---|
| `roles/secretmanager.secretAccessor` | Host project |

#### Main Service Account (per target project)

| Role | Scope | Purpose |
|---|---|---|
| `roles/iam.serviceAccountKeyAdmin` | Target project | List, create service account keys |
| `roles/iam.serviceAccountViewer` | Target project | List service accounts |
| `roles/resourcemanager.projectViewer` | Target project | Fetch project display names for reports |
| `roles/storage.objectAdmin` | GCS bucket | Read, write, and delete key JSON files |

#### Grant Commands

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

gsutil iam ch serviceAccount:$MAIN_SA:roles/storage.objectAdmin \
  gs://gcp-bucket-sa-keys-store
```

### Permission Summary

```
finops-billing-central-prod (host project)
├── cloud-run-rotator-sa  →  roles/secretmanager.secretAccessor
└── main-rotator-sa       →  credentials stored in Secret Manager

target-project-a, target-project-b, ... (each)
└── main-rotator-sa  →  roles/iam.serviceAccountKeyAdmin
                     →  roles/iam.serviceAccountViewer
                     →  roles/resourcemanager.projectViewer

gs://gcp-bucket-sa-keys-store
└── main-rotator-sa  →  roles/storage.objectAdmin
```

---

## 13. Infrastructure Details

### GCS Bucket: `gcp-bucket-sa-keys-store`

| Property | Value |
|---|---|
| Purpose | Persistent storage for rotated SA key JSON credentials |
| Path structure | `service-account-keys/{project_id}/{sa_email}/{key_id}.json` |
| Retention behaviour | `GCSStorage` deletes all previous key files for a SA when saving a new one — only the latest is kept |
| Access control | Uniform bucket-level access (no ACLs) |
| Encryption | CMEK recommended for key material at rest |
| Versioning | Optional — old object versions are explicitly deleted by the tool |
| Location | Same region as Cloud Run Job for lowest latency |

### Secret Manager

All secrets reside in the **host project** (`finops-billing-central-prod`):

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
| Memory | 512 MiB | Sufficient for all in-memory operations |
| Task timeout | 600s (10 min) | Accommodates large project scans + retry delays |
| Max retries | 1 | Safe to retry once — all operations are idempotent |
| Concurrency | 1 | Single task per execution |
| Region | Match target projects | Minimises cross-region API latency |

### Cloud Scheduler

| Setting | Value |
|---|---|
| Schedule | `0 8 * * 1` (every Monday at 08:00 UTC) |
| HTTP method | POST |
| Auth | OAuth — Cloud Run Jobs invoker role on attached SA |
| Retry policy | 3 attempts with exponential backoff |

---

## 14. Advantages

### Security

- **Private key never leaves your environment** — only the X.509 public certificate is uploaded to GCP
- **Zero hardcoded credentials** — all secrets are in Secret Manager, fetched at runtime
- **Least-privilege architecture** — the Cloud Run SA can only read secrets; all key operations are performed by the main SA loaded at runtime
- **Audit trail** — every rotation event is captured in GCS, Cloud Audit Logs, and the emailed Excel report

### Scalability

- **Multi-project** — scans any number of GCP projects in a single run; add new projects by updating a single Secret Manager secret
- **Configuration-driven** — thresholds, project lists, and recipients are all in Secret Manager; no redeployment needed

### Reliability

- **Per-SA error isolation** — a failure on one service account does not stop processing of others
- **Key validation with retry** — confirms the new key works, accommodating GCP's ~30s propagation delay
- **Dual email delivery** — ACS primary with Gmail SMTP fallback reduces alerting single points of failure
- **Zero-downtime rotation** — old and new keys coexist in GCP IAM during the transition window

### Maintainability

- **Modular design** — cryptography, IAM, storage, and email modules are fully decoupled and independently testable
- **Offline-testable crypto** — `key_manager.py` has zero GCP dependencies
- **Scan mode** — `ENABLE_ROTATION=false` provides full audit visibility without any changes

---

## 15. Limitations

| Limitation | Impact |
|---|---|
| **No automatic deletion of old IAM keys** | Old keys remain active in GCP IAM after rotation; manual cleanup is required once applications have been updated |
| **Manual key distribution** | The tool stores new keys in GCS but does not push them to applications — a team handover process is required (see [Section 17](#17-team-scope-of-work--key-distribution)) |
| **No automatic application update** | Applications must be manually updated with the new key JSON; restart and validation is a team responsibility |
| **Only the latest key per SA is evaluated** | If a SA has multiple keys, older ones are ignored and may expire silently |
| **No rollback on validation failure** | If key validation fails, the new key remains in GCP; a manual cleanup or re-run is needed |
| **ACS email rate limits** | Heavy report volumes may trigger ACS 429s; handled by Gmail fallback, but Gmail also has per-day send limits |
| **No Terraform / IaC included** | Infrastructure provisioning is manual or scripted — no Terraform modules are shipped in this repository |

---

## 16. Use Cases

- **Enterprise IAM governance** — enforce key rotation policy across all GCP projects from a single automated job
- **FinOps security automation** — reduce operational overhead of credential management in finance and billing platforms
- **Compliance requirements** — supports SOC 2, ISO 27001, and other frameworks that mandate regular credential rotation and audit evidence
- **Multi-project GCP environments** — centralised rotation across dev, staging, and production projects without per-project tooling

---

## 17. Team Scope of Work & Key Distribution

### Overview

After the automation rotates a key, the new credential must be distributed to the application team that consumes it. This section defines the controlled workflow for that handover.

### Step 1 — Identify Rotated Keys

The job sends two reports after each run:

- **HTML email** — summary with colour-coded status for each SA
- **Excel attachment** — full detail including storage location, rotation timestamp, and validation result

Teams review these reports to identify service accounts with status **Rotated**.

![Sample Email Report](docs/images/sample-email-report.png)

### Step 2 — Access Control

Rotated keys are stored in the GCS bucket with access restricted to authorised personnel only:

| Team | GCS Access |
|---|---|
| DevOps Team | Full — read, write, delete |
| Ops Team (limited members) | Read only |
| Application Team | No direct GCS access — receives keys via controlled handover |

### Step 3 — Key Retrieval from GCS

Authorised personnel (DevOps or Ops):

1. Access the GCS bucket: `gs://gcp-bucket-sa-keys-store/service-account-keys/`
2. Navigate to `{project_id}/{sa_email}/`
3. Download the latest `{key_id}.json` file

```bash
# List keys for a specific SA
gsutil ls gs://gcp-bucket-sa-keys-store/service-account-keys/YOUR_PROJECT/sa@project.iam.gserviceaccount.com/

# Download the latest key
gsutil cp gs://gcp-bucket-sa-keys-store/service-account-keys/YOUR_PROJECT/sa@project.iam.gserviceaccount.com/KEY_ID.json ./
```

### Step 4 — Distribution Flow

```
  Report Generated (Email + Excel)
          │
          ▼
  DevOps / Ops identifies rotated keys from report
          │
          ▼
  Downloads new key JSON from GCS bucket
          │
          ▼
  Shares key with Ops Team (secure channel)
          │
          ▼
  Ops Team shares key with Application Team
          │
          ▼
  Application Team updates credentials
          │
          ▼
  Services restarted / refreshed
          │
          ▼
  Validation completed
```

### Step 5 — Application Team Responsibilities

1. Update the application configuration or secret store with the new service account key JSON
2. Restart or refresh any services that hold the credential in memory
3. Validate that application functionality and GCP access are fully restored

### Security Guidelines

> These rules apply to every member involved in key distribution.

- Access to the GCS bucket is governed strictly by IAM roles — do not grant access outside the approved list
- Keys must be shared only via **secure, approved channels** (e.g. organisation-approved secrets manager, encrypted transfer)
- **Never share keys via email attachments, Slack DMs, or any unencrypted medium**
- **Never store keys locally** beyond the immediate update window
- Delete locally downloaded key files immediately after updating the application

---

## 18. Operational Runbook

### Execute the job manually

```bash
gcloud run jobs execute gcp-sa-key-rotation \
  --region=us-central1 \
  --project=finops-billing-central-prod
```

### Check whether the job ran successfully

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

### Run in scan-only mode (no rotation)

Set the `ENABLE_ROTATION` secret value to `false`, then execute the job:

```bash
gcloud run jobs execute gcp-sa-key-rotation \
  --region=us-central1 \
  --project=finops-billing-central-prod
```

Reset to `true` after the audit is complete.

### Add a new project to scan

```bash
NEW_VALUE="$(gcloud secrets versions access latest \
  --secret=GCP_PROJECTS \
  --project=finops-billing-central-prod),new-project-id"

echo -n "$NEW_VALUE" | gcloud secrets versions add GCP_PROJECTS \
  --data-file=- \
  --project=finops-billing-central-prod
```

Then grant the required IAM roles on the new project (see [Section 12](#12-iam--security-model)).

### Verify a rotated key exists in GCS

```bash
gsutil ls gs://gcp-bucket-sa-keys-store/service-account-keys/YOUR_PROJECT/
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | All scans and rotations completed successfully |
| `1` | One or more key rotations failed — check job logs and the emailed Excel report |

---

## 19. Final Outcome

This solution delivers a production-grade, enterprise-ready key rotation system:

| Capability | Detail |
|---|---|
| **Secure key lifecycle management** | Private key never leaves the environment; only the public cert reaches GCP |
| **Fully automated rotation** | Scheduled Cloud Run Job handles scan, rotate, validate, and report end-to-end |
| **Enterprise-grade reporting** | Colour-coded HTML email + full Excel attachment delivered to stakeholders after every run |
| **Controlled team-based distribution** | IAM-gated GCS access with a defined DevOps → Ops → App Team handover workflow |
| **Zero downtime operations** | Old and new keys coexist in GCP IAM — applications remain functional throughout the transition |
