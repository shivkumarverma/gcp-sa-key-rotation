"""
Thin wrapper around the Google IAM v1 REST API.
All methods return plain dataclasses — no business logic here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from googleapiclient import discovery
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


@dataclass
class ServiceAccount:
    name: str          # full resource name: projects/{proj}/serviceAccounts/{email}
    email: str
    project_id: str
    unique_id: str     # numeric client_id


@dataclass
class ServiceAccountKey:
    name: str                      # full resource name including key ID
    key_id: str                    # trailing segment after last "/"
    valid_after_time: Optional[datetime]   # creation time; used to pick the latest key
    valid_before_time: Optional[datetime]  # None if not set (non-expiring)
    service_account_name: str      # parent SA resource name


def build_iam_client(credentials):
    """Build and return a Google IAM v1 API client using the provided credentials."""
    return discovery.build("iam", "v1", credentials=credentials, cache_discovery=False)



def list_service_accounts(iam_client, project_id: str) -> list[ServiceAccount]:
    """List all service accounts in the given project, handling pagination."""
    accounts: list[ServiceAccount] = []
    request = iam_client.projects().serviceAccounts().list(
        name=f"projects/{project_id}"
    )
    while request is not None:
        response = request.execute()
        for acct in response.get("accounts", []):
            accounts.append(ServiceAccount(
                name=acct["name"],
                email=acct["email"],
                project_id=project_id,
                unique_id=acct.get("uniqueId", ""),
            ))
        request = iam_client.projects().serviceAccounts().list_next(
            previous_request=request, previous_response=response
        )
    logger.debug("Found %d service accounts in project %s", len(accounts), project_id)
    return accounts


def list_keys_for_account(
    iam_client, sa_name: str
) -> list[ServiceAccountKey]:
    """
    List USER_MANAGED keys for a service account.
    Keys with no validBeforeTime (non-expiring) have valid_before_time=None.
    """
    response = (
        iam_client.projects()
        .serviceAccounts()
        .keys()
        .list(name=sa_name, keyTypes=["USER_MANAGED"])
        .execute()
    )
    def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))

    keys: list[ServiceAccountKey] = []
    for k in response.get("keys", []):
        key_id = k["name"].split("/")[-1]
        keys.append(ServiceAccountKey(
            name=k["name"],
            key_id=key_id,
            valid_after_time=_parse_dt(k.get("validAfterTime")),
            valid_before_time=_parse_dt(k.get("validBeforeTime")),
            service_account_name=sa_name,
        ))
    logger.debug("Found %d USER_MANAGED keys for %s", len(keys), sa_name)
    return keys


def upload_public_key(
    iam_client,
    sa_name: str,
    public_key_data_b64: str,
) -> dict:
    """
    Upload a base64-encoded X.509 PEM certificate as a new UPLOADED key for the SA.
    Returns the full key resource dict from GCP (includes 'name' with the new key ID).
    """
    try:
        result = (
            iam_client.projects()
            .serviceAccounts()
            .keys()
            .upload(
                name=sa_name,
                body={"publicKeyData": public_key_data_b64},
            )
            .execute()
        )
    except HttpError as exc:
        raise RuntimeError(
            f"Failed to upload public key for {sa_name}: HTTP {exc.resp.status} — {exc.content!r}"
        ) from exc
    logger.debug("Uploaded new key for %s → %s", sa_name, result.get("name"))
    return result
