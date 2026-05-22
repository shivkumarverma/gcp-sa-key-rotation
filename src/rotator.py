"""
Orchestration: expiry checking, key rotation, and result collection.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src import gcp_client, key_manager
from src.config import AppConfig
from src.storage import KeyStorage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status bands — drives both scan classification and rotate trigger.
# Tuned for a WEEKLY scheduler so the auto-rotate window never slips between runs.
#   days > OK_THRESHOLD_DAYS                                          → OK
#   EXPIRING_SOON_THRESHOLD_DAYS < days <= OK_THRESHOLD_DAYS          → Expiring Soon
#   AUTO_ROTATE_THRESHOLD_DAYS  < days <= EXPIRING_SOON_THRESHOLD     → Critical
#   days <= AUTO_ROTATE_THRESHOLD_DAYS                                → Very Critical
#                                                                       (auto-rotate when ENABLE_ROTATION=true)
# ---------------------------------------------------------------------------
OK_THRESHOLD_DAYS = 20
EXPIRING_SOON_THRESHOLD_DAYS = 15
AUTO_ROTATE_THRESHOLD_DAYS = 7   # also the upper bound of the "Very Critical" band

STATUS_OK = "OK"
STATUS_EXPIRING_SOON = "Expiring Soon"
STATUS_CRITICAL = "Critical"
STATUS_VERY_CRITICAL = "Very Critical"
STATUS_EXPIRED = "Expired"
STATUS_ROTATED = "Rotated"
STATUS_ERROR = "Error"


@dataclass
class RotationRecord:
    project_id: str
    sa_email: str
    old_key_id: str
    expiry_date: Optional[datetime]   # None if key has no expiry
    days_remaining: Optional[int]     # None if key has no expiry
    status: str                       # OK | Expiring Soon | Critical | Rotated | Error
    project_name: str = field(default="")
    new_key_id: str = field(default="")
    storage_location: str = field(default="")
    rotation_timestamp: Optional[datetime] = field(default=None)
    error_message: str = field(default="")
    key_valid: Optional[bool] = field(default=None)
    key_validation_error: str = field(default="")


def classify_key(days_remaining: Optional[int]) -> str:
    """Map a key's days-remaining to its display status band."""
    if days_remaining is None or days_remaining > OK_THRESHOLD_DAYS:
        return STATUS_OK
    if days_remaining > EXPIRING_SOON_THRESHOLD_DAYS:
        return STATUS_EXPIRING_SOON
    if days_remaining > AUTO_ROTATE_THRESHOLD_DAYS:
        return STATUS_CRITICAL
    if days_remaining > 0:
        return STATUS_VERY_CRITICAL
    return STATUS_EXPIRED


def should_auto_rotate(days_remaining: Optional[int]) -> bool:
    """Return True if the key is inside the auto-rotate window (<= threshold)."""
    return days_remaining is not None and days_remaining <= AUTO_ROTATE_THRESHOLD_DAYS


def _days_remaining(key: gcp_client.ServiceAccountKey) -> Optional[int]:
    if key.valid_before_time is None:
        return None
    now = datetime.now(timezone.utc)
    return (key.valid_before_time - now).days


def _validate_key_json(key_dict: dict, retries: int = 3, delay: int = 10) -> tuple[bool, str]:
    """
    Attempt to obtain a GCP access token using the new key JSON.
    Retries to allow time for GCP key propagation (can take up to ~30s).
    Returns (success, error_message).
    """
    from google.oauth2 import service_account as sa_module
    from google.auth.transport.requests import Request as AuthRequest

    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            creds = sa_module.Credentials.from_service_account_info(
                key_dict,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            creds.refresh(AuthRequest())
            return True, ""
        except Exception as exc:
            last_error = str(exc)
            logger.debug("Key validation attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(delay)
    return False, last_error


def rotate_key(
    iam_client,
    sa: gcp_client.ServiceAccount,
    storage: KeyStorage,
) -> tuple[str, str, bool, str]:
    """
    Generate a new RSA key pair, upload the public cert to GCP, build and store
    the JSON credential file, then validate the key works.
    Returns (new_key_id, storage_location, key_valid, key_validation_error).

    GCP never receives the private key — only the X.509 certificate is uploaded.
    """
    private_pem, cert_pem = key_manager.generate_rsa_key_pair()
    b64_cert = key_manager.encode_public_key_for_upload(cert_pem)

    key_resource = gcp_client.upload_public_key(iam_client, sa.name, b64_cert)
    new_key_id = key_resource["name"].split("/")[-1]

    key_dict = key_manager.build_key_json(
        project_id=sa.project_id,
        service_account_email=sa.email,
        client_id=sa.unique_id,
        key_id=new_key_id,
        private_key_pem=private_pem,
    )

    sa_name = sa.email.split("@")[0]
    storage_location = storage.save(json.dumps(key_dict, indent=2), sa.project_id, sa_name, new_key_id)

    logger.info("Validating new key %s for %s...", new_key_id, sa.email)
    key_valid, key_validation_error = _validate_key_json(key_dict)
    if key_valid:
        logger.info("Key validation passed for %s", new_key_id)
    else:
        logger.warning("Key validation failed for %s: %s", new_key_id, key_validation_error)

    return new_key_id, storage_location, key_valid, key_validation_error


def process_project(
    iam_client,
    project_id: str,
    config: AppConfig,
    storage: Optional[KeyStorage],
    skipped_projects: list,
) -> list[RotationRecord]:
    """
    Scan all service accounts in a project and either report or rotate expiring keys.
    Per-SA errors are caught and recorded — the run continues for remaining accounts.
    Project-level access failures are appended to skipped_projects.
    """
    records: list[RotationRecord] = []
    project_name = gcp_client.get_project_display_name(config.credentials, project_id)

    try:
        accounts = gcp_client.list_service_accounts(iam_client, project_id)
    except Exception as exc:
        logger.error("Failed to list service accounts in project %s: %s", project_id, exc)
        skipped_projects.append(project_id)
        return records

    for sa in accounts:
        try:
            keys = gcp_client.list_keys_for_account(iam_client, sa.name)
        except Exception as exc:
            logger.error("Failed to list keys for %s: %s", sa.email, exc)
            continue

        if not keys:
            continue

        # Only evaluate the most recently created key per service account
        key = max(keys, key=lambda k: k.valid_after_time or datetime.min.replace(tzinfo=timezone.utc))
        if len(keys) > 1:
            logger.debug(
                "SA %s has %d USER_MANAGED keys — using latest: %s (created %s)",
                sa.email, len(keys), key.key_id,
                key.valid_after_time.date() if key.valid_after_time else "unknown",
            )

        days = _days_remaining(key)
        scan_status = classify_key(days)
        expiry_str = key.valid_before_time.date() if key.valid_before_time else "N/A"

        log_tag = "[ROTATE]" if config.rotation_enabled else "[SCAN]"
        if scan_status == STATUS_VERY_CRITICAL:
            logger.warning("%s Key %s for %s expires %s (%s days) — VERY CRITICAL",
                           log_tag, key.key_id, sa.email, expiry_str, days)
        elif scan_status == STATUS_CRITICAL:
            logger.warning("%s Key %s for %s expires %s (%s days) — CRITICAL",
                           log_tag, key.key_id, sa.email, expiry_str, days)
        elif scan_status == STATUS_EXPIRING_SOON:
            logger.warning("%s Key %s for %s expires %s (%s days) — expiring soon",
                           log_tag, key.key_id, sa.email, expiry_str, days)
        else:
            logger.debug("%s Key %s for %s is OK (%s days remaining)",
                         log_tag, key.key_id, sa.email, days)

        # Rotate mode + inside auto-rotate window → attempt rotation
        if config.rotation_enabled and should_auto_rotate(days):
            logger.warning(
                "[ROTATE] Key %s for %s has %s days remaining — auto-rotating (threshold %d)",
                key.key_id, sa.email, days, AUTO_ROTATE_THRESHOLD_DAYS,
            )
            try:
                new_key_id, location, key_valid, key_validation_error = rotate_key(iam_client, sa, storage)
                records.append(RotationRecord(
                    project_id=project_id,
                    project_name=project_name,
                    sa_email=sa.email,
                    old_key_id=key.key_id,
                    expiry_date=key.valid_before_time,
                    days_remaining=days,
                    status=STATUS_ROTATED,
                    new_key_id=new_key_id,
                    storage_location=location,
                    rotation_timestamp=datetime.now(timezone.utc),
                    key_valid=key_valid,
                    key_validation_error=key_validation_error,
                ))
                logger.info("Rotated key %s → %s stored at %s", key.key_id, new_key_id, location)
            except Exception as exc:
                logger.error("Failed to rotate key %s for %s: %s", key.key_id, sa.email, exc)
                records.append(RotationRecord(
                    project_id=project_id,
                    project_name=project_name,
                    sa_email=sa.email,
                    old_key_id=key.key_id,
                    expiry_date=key.valid_before_time,
                    days_remaining=days,
                    status=STATUS_ERROR,
                    error_message=str(exc),
                ))
        else:
            records.append(RotationRecord(
                project_id=project_id,
                project_name=project_name,
                sa_email=sa.email,
                old_key_id=key.key_id,
                expiry_date=key.valid_before_time,
                days_remaining=days,
                status=scan_status,
            ))

    return records


def run(
    config: AppConfig,
    iam_client,
    storage: Optional[KeyStorage],
) -> list[RotationRecord]:
    """Process all configured projects and return all RotationRecords."""
    all_records: list[RotationRecord] = []
    skipped_projects: list[str] = []
    for project_id in config.projects:
        logger.info("Processing project: %s", project_id)
        records = process_project(iam_client, project_id, config, storage, skipped_projects)
        all_records.extend(records)

    # Summary log
    total = len(all_records)
    expired = sum(1 for r in all_records if r.status == STATUS_EXPIRED)
    very_critical = sum(1 for r in all_records if r.status == STATUS_VERY_CRITICAL)
    critical = sum(1 for r in all_records if r.status == STATUS_CRITICAL)
    expiring_soon = sum(1 for r in all_records if r.status == STATUS_EXPIRING_SOON)
    rotated = sum(1 for r in all_records if r.status == STATUS_ROTATED)
    errors = sum(1 for r in all_records if r.status == STATUS_ERROR)

    if config.rotation_enabled:
        logger.info(
            "Run complete [ROTATE mode] — %d checked, %d rotated, %d expired, %d very critical, %d critical, %d expiring soon, %d errors",
            total, rotated, expired, very_critical, critical, expiring_soon, errors,
        )
    else:
        logger.info(
            "Run complete [SCAN mode] — %d checked, %d expired, %d very critical (<=%dd), %d critical (<=%dd), %d expiring soon (<=%dd)",
            total, expired, very_critical, AUTO_ROTATE_THRESHOLD_DAYS,
            critical, EXPIRING_SOON_THRESHOLD_DAYS,
            expiring_soon, OK_THRESHOLD_DAYS,
        )

    if skipped_projects:
        logger.warning(
            "Projects skipped (permission denied / access error) [%d]: %s",
            len(skipped_projects), ", ".join(skipped_projects),
        )

    return all_records
