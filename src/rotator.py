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


@dataclass
class RotationRecord:
    project_id: str
    sa_email: str
    old_key_id: str
    expiry_date: Optional[datetime]   # None if key has no expiry
    days_remaining: Optional[int]     # None if key has no expiry
    status: str                       # "Rotated" | "Error" | "Expiring" | "OK"
    new_key_id: str = field(default="")
    storage_location: str = field(default="")
    rotation_timestamp: Optional[datetime] = field(default=None)
    error_message: str = field(default="")
    key_valid: Optional[bool] = field(default=None)
    key_validation_error: str = field(default="")


def check_key_expiry(key: gcp_client.ServiceAccountKey, threshold_days: int) -> bool:
    """Return True if the key expires within threshold_days (or is already expired)."""
    if key.valid_before_time is None:
        return False
    now = datetime.now(timezone.utc)
    days_remaining = (key.valid_before_time - now).days
    return days_remaining <= threshold_days


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
) -> list[RotationRecord]:
    """
    Scan all service accounts in a project and either report or rotate expiring keys.
    Per-SA errors are caught and recorded — the run continues for remaining accounts.
    """
    records: list[RotationRecord] = []

    try:
        accounts = gcp_client.list_service_accounts(iam_client, project_id)
    except Exception as exc:
        logger.error("Failed to list service accounts in project %s: %s", project_id, exc)
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

        for key in [key]:
            expiring = check_key_expiry(key, config.expiry_threshold_days)
            days = _days_remaining(key)

            if not config.rotation_enabled:
                # Scan-only mode: classify and record, no GCP writes
                status = "Expiring" if expiring else "OK"
                if expiring:
                    logger.warning(
                        "[SCAN] Key %s for %s expires %s (%s days remaining)",
                        key.key_id, sa.email,
                        key.valid_before_time.date() if key.valid_before_time else "N/A",
                        days,
                    )
                else:
                    logger.debug("[SCAN] Key %s for %s is OK (%s days remaining)", key.key_id, sa.email, days)
                records.append(RotationRecord(
                    project_id=project_id,
                    sa_email=sa.email,
                    old_key_id=key.key_id,
                    expiry_date=key.valid_before_time,
                    days_remaining=days,
                    status=status,
                ))
            else:
                # Rotate mode
                if not expiring:
                    logger.debug("[ROTATE] Key %s for %s is OK, skipping", key.key_id, sa.email)
                    records.append(RotationRecord(
                        project_id=project_id,
                        sa_email=sa.email,
                        old_key_id=key.key_id,
                        expiry_date=key.valid_before_time,
                        days_remaining=days,
                        status="OK",
                    ))
                    continue

                logger.warning(
                    "[ROTATE] Key %s for %s expires %s (%s days) — rotating",
                    key.key_id, sa.email,
                    key.valid_before_time.date() if key.valid_before_time else "N/A",
                    days,
                )
                try:
                    new_key_id, location, key_valid, key_validation_error = rotate_key(iam_client, sa, storage)
                    records.append(RotationRecord(
                        project_id=project_id,
                        sa_email=sa.email,
                        old_key_id=key.key_id,
                        expiry_date=key.valid_before_time,
                        days_remaining=days,
                        status="Rotated",
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
                        sa_email=sa.email,
                        old_key_id=key.key_id,
                        expiry_date=key.valid_before_time,
                        days_remaining=days,
                        status="Error",
                        error_message=str(exc),
                    ))

    return records


def run(
    config: AppConfig,
    iam_client,
    storage: Optional[KeyStorage],
) -> list[RotationRecord]:
    """Process all configured projects and return all RotationRecords."""
    all_records: list[RotationRecord] = []
    for project_id in config.projects:
        logger.info("Processing project: %s", project_id)
        records = process_project(iam_client, project_id, config, storage)
        all_records.extend(records)

    # Summary log
    total = len(all_records)
    expiring = sum(1 for r in all_records if r.status == "Expiring")
    rotated = sum(1 for r in all_records if r.status == "Rotated")
    errors = sum(1 for r in all_records if r.status == "Error")

    if config.rotation_enabled:
        logger.info(
            "Run complete [ROTATE mode] — %d keys checked, %d rotated, %d errors",
            total, rotated, errors,
        )
    else:
        logger.info(
            "Run complete [SCAN mode] — %d keys checked, %d expiring within %d days",
            total, expiring, config.expiry_threshold_days,
        )

    return all_records
