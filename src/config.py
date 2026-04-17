"""
Configuration: loads all settings from GCP Secret Manager.
See .env.example for required environment variables.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import secretmanager
from google.oauth2 import service_account
from google.oauth2.service_account import Credentials

load_dotenv()

logger = logging.getLogger(__name__)

_SM_PROJECT = os.environ.get("SECRET_MANAGER_PROJECT_ID", "finops-billing-central-prod").strip()
_SM_VERSION = os.environ.get("SECRET_MANAGER_VERSION", "latest").strip()
_SA_SECRET_ID = os.environ.get("SERVICE_ACCOUNT_SECRET_ID", "SERVICE_ACCOUNT_SECRET_ID").strip()

if not _SM_PROJECT:
    raise ValueError("SECRET_MANAGER_PROJECT_ID environment variable is required.")
if not _SA_SECRET_ID:
    raise ValueError("SERVICE_ACCOUNT_SECRET_ID environment variable is required.")

# ---------------------------------------------------------------------------
# Step 1 — Bootstrap: use ADC (Cloud Run's attached SA) to reach Secret Manager
# ---------------------------------------------------------------------------
_bootstrap_sm = secretmanager.SecretManagerServiceClient()

def _bootstrap_get(secret_id: str) -> str:
    name = f"projects/{_SM_PROJECT}/secrets/{secret_id}/versions/{_SM_VERSION}"
    return _bootstrap_sm.access_secret_version(request={"name": name}).payload.data.decode("utf-8").strip()

# ---------------------------------------------------------------------------
# Step 2 — Load the main service account JSON from Secret Manager
# Same pattern as billing project (Credentials.from_service_account_info)
# ---------------------------------------------------------------------------
_sa_info = json.loads(_bootstrap_get(_SA_SECRET_ID))
_credentials: Credentials = service_account.Credentials.from_service_account_info(
    _sa_info,
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)

# ---------------------------------------------------------------------------
# Step 3 — Re-create SM client with the loaded SA for all subsequent fetches
# ---------------------------------------------------------------------------
_client = secretmanager.SecretManagerServiceClient(credentials=_credentials)


def get_secret(secret_id: str) -> str:
    """Fetch a required secret — raises if the secret does not exist."""
    name = f"projects/{_SM_PROJECT}/secrets/{secret_id}/versions/{_SM_VERSION}"
    return _client.access_secret_version(request={"name": name}).payload.data.decode("utf-8").strip()


def _get_optional(secret_id: str, default: str = "") -> str:
    """Fetch an optional secret — falls back to env var, then default."""
    try:
        return get_secret(secret_id)
    except Exception:
        return os.environ.get(secret_id, default)


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    projects: list[str]
    expiry_threshold_days: int
    rotation_enabled: bool
    storage_backend: str
    gcs_bucket: str
    local_dir: Path
    email_recipients: list[str]
    email_subject: str
    acs_connection_string: str
    acs_sender_address: str
    gmail_user: str
    gmail_app_password: str
    log_level: str
    credentials: Credentials = field(repr=False)   # loaded SA, passed to IAM/GCS clients


def load_config() -> AppConfig:
    """Fetch all config from Secret Manager using the loaded service account."""
    # Required — will raise if the secret is missing
    projects = [p.strip() for p in get_secret("GCP_PROJECTS").split(",") if p.strip()]
    email_recipients = [r.strip() for r in get_secret("EMAIL_REPORTS_TO").split(",") if r.strip()]

    # Optional — fall back to built-in defaults
    expiry_threshold_days = int(_get_optional("EXPIRY_THRESHOLD_DAYS", "14"))
    rotation_enabled = _get_optional("ENABLE_ROTATION", "true").lower() == "true"
    storage_backend = _get_optional("STORAGE_BACKEND", "gcs")
    gcs_bucket = _get_optional("GCS_BUCKET", "gcp-bucket-sa-keys-store")
    local_dir = Path(_get_optional("LOCAL_DIR", "./keys"))
    email_subject = _get_optional("EMAIL_SUBJECT", "GCP Service Account Key Report")

    # ACS Email + Gmail SMTP fallback (optional)
    acs_connection_string = _get_optional("ACS_CONNECTION_STRING","")
    acs_sender_address = _get_optional("ACS_SENDER_ADDRESS","")
    gmail_user = _get_optional("GMAIL_USER","")
    gmail_app_password = _get_optional("GMAIL_APP_PASSWORD","")

    # LOG_LEVEL stays as a plain env var — not sensitive
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    return AppConfig(
        projects=projects,
        expiry_threshold_days=expiry_threshold_days,
        rotation_enabled=rotation_enabled,
        storage_backend=storage_backend,
        gcs_bucket=gcs_bucket,
        local_dir=local_dir,
        email_recipients=email_recipients,
        email_subject=email_subject,
        acs_connection_string=acs_connection_string,
        acs_sender_address=acs_sender_address,
        gmail_user=gmail_user,
        gmail_app_password=gmail_app_password,
        log_level=log_level,
        credentials=_credentials,
    )
