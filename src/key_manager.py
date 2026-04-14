"""
RSA key generation, X.509 certificate creation, and GCP service account JSON assembly.
No GCP API calls — fully testable offline.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_rsa_key_pair() -> tuple[bytes, bytes]:
    """
    Generate an RSA 2048 key pair. Returns (private_key_pem, public_cert_pem).

    The public component is wrapped in a self-signed X.509 certificate with
    CN=unused and 90-day validity — matching the manual openssl command:
        openssl req -x509 -nodes -newkey rsa:2048 -days 90
                    -keyout private_key.pem -out public_key.pem -subj "/CN=unused"
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "unused"),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=90))
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)

    return private_pem, cert_pem


def encode_public_key_for_upload(cert_pem: bytes) -> str:
    """Base64-encode the PEM certificate for GCP keys.create publicKeyData field."""
    return base64.standard_b64encode(cert_pem).decode("ascii")


def build_key_json(
    project_id: str,
    service_account_email: str,
    client_id: str,
    key_id: str,
    private_key_pem: bytes,
) -> dict:
    """
    Assemble a GCP service account JSON credential file (standard format).
    The private key is the locally generated RSA key; key_id is assigned by GCP
    after uploading the public certificate.
    """
    encoded_email = urllib.parse.quote(service_account_email, safe="")
    return {
        "type": "service_account",
        "project_id": project_id,
        "private_key_id": key_id,
        "private_key": private_key_pem.decode("utf-8"),
        "client_email": service_account_email,
        "client_id": client_id,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": (
            f"https://www.googleapis.com/robot/v1/metadata/x509/{encoded_email}"
        ),
    }


def write_key_file(
    key_dict: dict,
    output_dir: Path,
    service_account_email: str,
    key_id: str,
) -> Path:
    """Write the JSON key dict to a file and return its path."""
    safe_email = service_account_email.replace("@", "_").replace(".", "_")
    filename = f"{safe_email}_{key_id[:8]}.json"
    path = output_dir / filename
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(key_dict, fh, indent=2)
    return path
