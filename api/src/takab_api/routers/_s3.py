"""Helpers S3 del bucket de evidencia (compartidos por exports/reports).

boto3 usa las credenciales del rol de la tarea ECS en prod y las de moto en
tests; el presigned URL se firma en proceso (sin red).
"""

from __future__ import annotations

import boto3

from takab_api.settings import Settings

PRESIGN_TTL_S = 300


def presign_get(settings: Settings, s3_key: str) -> str:
    """URL GET presignada de ``PRESIGN_TTL_S`` sobre el bucket de evidencia."""
    client = boto3.client("s3", region_name=settings.aws_region)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.evidence_bucket, "Key": s3_key},
        ExpiresIn=PRESIGN_TTL_S,
    )


def put_object(settings: Settings, s3_key: str, body: bytes, *, content_type: str) -> None:
    """Sube un objeto al bucket de evidencia."""
    client = boto3.client("s3", region_name=settings.aws_region)
    client.put_object(
        Bucket=settings.evidence_bucket, Key=s3_key, Body=body, ContentType=content_type
    )
