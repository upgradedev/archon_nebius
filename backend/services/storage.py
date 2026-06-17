"""
S3-compatible storage service.

Works with Nebius Object Storage, AWS S3, GCP GCS (via S3 compatibility layer),
Azure Blob (via Azurite or S3 adapter), LocalStack for local dev.
Switch providers by changing STORAGE_ENDPOINT_URL in .env.
"""

import os
import json
import boto3
from botocore.config import Config


def _client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("STORAGE_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("NEBIUS_REGION", "eu-north1"),
        config=Config(signature_version="s3v4"),
    )


BUCKET = os.getenv("NEBIUS_BUCKET_NAME", "archon-docs")


def upload_file(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    _client().put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=content_type)
    return key


def download_json(key: str) -> dict:
    obj = _client().get_object(Bucket=BUCKET, Key=key)
    return json.loads(obj["Body"].read())


def list_keys(prefix: str) -> list[str]:
    paginator = _client().get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def put_json(key: str, data: dict) -> str:
    body = json.dumps(data, ensure_ascii=False, indent=2).encode()
    return upload_file(key, body, "application/json")


def delete_key(key: str) -> None:
    _client().delete_object(Bucket=BUCKET, Key=key)


def delete_prefix(prefix: str) -> int:
    """Delete all S3 objects whose key starts with prefix. Returns count deleted."""
    if not prefix:
        return 0
    paginator = _client().get_paginator("list_objects_v2")
    objects: list[dict] = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            objects.append({"Key": obj["Key"]})
    if not objects:
        return 0
    for i in range(0, len(objects), 1000):
        _client().delete_objects(
            Bucket=BUCKET,
            Delete={"Objects": objects[i : i + 1000]},
        )
    return len(objects)


def key_exists(key: str) -> bool:
    try:
        _client().head_object(Bucket=BUCKET, Key=key)
        return True
    except Exception:
        return False
