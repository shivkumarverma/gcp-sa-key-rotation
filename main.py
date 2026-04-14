"""
GCP Service Account Key Rotation Tool — Cloud Run Job entry point.

All configuration is loaded from GCP Secret Manager.
Bootstrap env vars required:
  GOOGLE_APPLICATION_CREDENTIALS  — SA JSON file path (or use ADC)
  SECRET_MANAGER_PROJECT_ID       — GCP project that owns the secrets
  LOG_LEVEL                       — DEBUG / INFO / WARNING / ERROR (default: INFO)
"""

from __future__ import annotations

import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from src.config import load_config
from src import gcp_client, rotator
from src.acs_email_client import send_report
from src.excel_builder import build_report
from src.email_template import build_email_body
from src.storage import build_storage


def _setup_logging(log_level: str) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=fmt,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient.discovery").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    logging.getLogger("azure.communication.email").setLevel(logging.WARNING)


def main() -> None:
    config = load_config()
    _setup_logging(config.log_level)
    logger = logging.getLogger(__name__)

    mode = "ROTATE" if config.rotation_enabled else "SCAN ONLY"
    logger.info("=" * 60)
    logger.info("GCP SA Key Rotation Tool — mode: %s", mode)
    logger.info("Projects  : %s", ", ".join(config.projects))
    logger.info("Threshold : %d days", config.expiry_threshold_days)
    logger.info("=" * 60)

    iam_client = gcp_client.build_iam_client(config.credentials)

    storage = None
    if config.rotation_enabled:
        storage = build_storage(
            storage_backend=config.storage_backend,
            gcs_bucket=config.gcs_bucket,
            local_dir=config.local_dir,
            credentials=config.credentials,
        )

    records = rotator.run(config, iam_client, storage)

    # Build Excel report
    date_tag = datetime.now().strftime("%Y-%m-%d")
    mode_tag = "rotation" if config.rotation_enabled else "scan"
    report_filename = f"sa_key_{mode_tag}_report_{date_tag}.xlsx"
    report_path = Path(tempfile.gettempdir()) / report_filename

    build_report(records, report_path, config.rotation_enabled)
    logger.info("Excel report: %s", report_path)

    # Send email via ACS (Gmail SMTP fallback on 429)
    mode_suffix = "[Rotation Report]" if config.rotation_enabled else "[Scan Report]"
    subject = f"{config.email_subject} {mode_suffix} — {date_tag}"
    html_body = build_email_body(records, subject, report_filename, config.rotation_enabled)

    try:
        raw = report_path.read_bytes()
        if not raw.startswith(b"PK"):
            logger.error("Report is not a valid xlsx file — skipping email.")
        else:
            send_report(
                to=config.email_recipients,
                subject=subject,
                html_body=html_body,
                attachment_name=report_filename,
                attachment_bytes=raw,
                acs_connection_string=config.acs_connection_string,
                acs_sender_address=config.acs_sender_address,
                gmail_user=config.gmail_user,
                gmail_app_password=config.gmail_app_password,
            )
    except Exception:
        logger.exception("Failed to send email report.")

    errors = sum(1 for r in records if r.status == "Error")
    if errors:
        logger.error("%d key(s) failed to rotate. Check logs above.", errors)
        sys.exit(1)


if __name__ == "__main__":
    main()
