"""
Storage abstraction for saving JSON key files.
Supports local filesystem and Google Cloud Storage.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class KeyStorage(Protocol):
    def save(self, content: str, project_id: str, sa_name: str, key_id: str) -> str:
        """Save key JSON content and return the storage location (path or URI)."""
        ...


def _blob_path(project_id: str, sa_name: str, key_id: str) -> str:
    """Build the canonical key path: projects/{project}/{sa_name}/{key_id}.json"""
    return f"service-account-keys/{project_id}/{sa_name}/{key_id}.json"


class LocalStorage:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def save(self, content: str, project_id: str, sa_name: str, key_id: str) -> str:
        rel = _blob_path(project_id, sa_name, key_id)
        path = self.output_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("Key saved locally: %s", path)
        return str(path)


class GCSStorage:
    def __init__(self, bucket_name: str, credentials) -> None:
        self.bucket_name = bucket_name
        self._credentials = credentials

    def save(self, content: str, project_id: str, sa_name: str, key_id: str) -> str:
        from google.cloud import storage as gcs

        blob_name = _blob_path(project_id, sa_name, key_id)
        client = gcs.Client(credentials=self._credentials)
        bucket = client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(content, content_type="application/json")
        uri = f"gs://{self.bucket_name}/{blob_name}"
        logger.info("Key saved to GCS: %s", uri)
        return uri


def build_storage(storage_backend: str, gcs_bucket: str, local_dir: Path, credentials) -> KeyStorage:
    if storage_backend == "gcs":
        return GCSStorage(bucket_name=gcs_bucket, credentials=credentials)
    return LocalStorage(output_dir=local_dir)
