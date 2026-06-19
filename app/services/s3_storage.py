from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from fastapi import HTTPException, status

from app.core.config import settings


_SAFE_KEY_PART_RE = re.compile(r"[^A-Za-z0-9._/-]+")


@dataclass(frozen=True)
class StoredObject:
    key: str
    content: bytes
    content_type: str
    content_length: int


def _require_s3_settings() -> None:
    missing = [
        name
        for name, value in {
            "S3_ENDPOINT": settings.S3_ENDPOINT,
            "S3_ACCESS_KEY": settings.S3_ACCESS_KEY,
            "S3_SECRET_KEY": settings.S3_SECRET_KEY,
            "S3_BUCKET": settings.S3_BUCKET,
        }.items()
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"S3 storage is not configured. Missing: {', '.join(missing)}.",
        )


def _client():
    _require_s3_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def _clean_key_part(value: str) -> str:
    value = _SAFE_KEY_PART_RE.sub("_", value.strip().replace("\\", "/"))
    return value.strip("/._")


def trainer_object_key(filename: str) -> str:
    filename = os.path.basename(filename)
    prefix = _clean_key_part(settings.S3_TRAINER_PREFIX or "trainers")
    return f"{prefix}/{filename}"


def upload_private_object(*, key: str, data: bytes, content_type: str, original_filename: Optional[str] = None) -> None:
    metadata = {}
    if original_filename:
        metadata["original-filename"] = os.path.basename(original_filename)[:200]

    try:
        _client().put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata=metadata,
        )
    except (ClientError, BotoCoreError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure document storage is not available. Please try again.",
        )


def upload_public_object(*, key: str, data: bytes, content_type: str, original_filename: Optional[str] = None) -> str:
    """Uploads an object and returns the public URL (assuming the bucket is public or public-read)."""
    metadata = {}
    if original_filename:
        metadata["original-filename"] = os.path.basename(original_filename)[:200]

    try:
        _client().put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata=metadata,
            # ACL="public-read"  # Some providers block ACLs, so omitting it relying on bucket policy
        )
        # Construct public URL based on endpoint. Supabase: /storage/v1/s3 -> /storage/v1/object/public/
        if "supabase.co" in settings.S3_ENDPOINT:
            base_url = settings.S3_ENDPOINT.replace("/s3", "/object/public/")
            if not base_url.endswith("/"):
                base_url += "/"
            return f"{base_url}{settings.S3_BUCKET}/{key}"
        
        # Generic S3 public URL fallback
        # e.g., https://bucket-name.s3.region.amazonaws.com/key
        endpoint = settings.S3_ENDPOINT.replace("https://", "").replace("http://", "")
        scheme = "https://" if "https://" in settings.S3_ENDPOINT else "http://"
        return f"{scheme}{settings.S3_BUCKET}.{endpoint}/{key}"
    except (ClientError, BotoCoreError) as e:
        print(f"S3 Upload Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Public document storage is not available. Please try again.",
        )


def object_exists(key: str) -> bool:
    try:
        _client().head_object(Bucket=settings.S3_BUCKET, Key=key)
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure document storage could not be checked. Please try again.",
        )
    except BotoCoreError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure document storage could not be checked. Please try again.",
        )


def download_private_object(key: str) -> StoredObject:
    try:
        response = _client().get_object(Bucket=settings.S3_BUCKET, Key=key)
        body = response["Body"].read()
        return StoredObject(
            key=key,
            content=body,
            content_type=response.get("ContentType") or "application/octet-stream",
            content_length=int(response.get("ContentLength") or len(body)),
        )
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document was not found in secure storage.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure document storage is not available. Please try again.",
        )
    except BotoCoreError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure document storage is not available. Please try again.",
        )
