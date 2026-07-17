"""Helpers S3 del bucket de evidencia (compartidos por exports/reports).

boto3 usa las credenciales del rol de la tarea ECS en prod y las de moto en
tests; el presigned URL se firma en proceso (sin red).

`s3_endpoint_url` es el seam para hablar con un S3 LOCAL (MinIO) en desarrollo:
vacío ⇒ AWS real, sin cambio alguno para producción. Con valor ⇒ ese endpoint.
"""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config

from takab_api.settings import Settings

PRESIGN_TTL_S = 300


def s3_client(settings: Settings) -> Any:
    """Cliente S3 contra AWS o contra el S3 local, según `s3_endpoint_url`."""
    if not settings.s3_endpoint_url:
        return boto3.client("s3", region_name=settings.aws_region)

    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.s3_endpoint_url,
        # Path-style OBLIGATORIO: el estilo virtual-host por defecto de boto3
        # firmaría contra `mi-bucket.127.0.0.1`, un host que no existe. Con
        # path-style la URL queda `http://127.0.0.1:9000/mi-bucket/clave`, que
        # es la que el navegador abre desde la consola.
        config=Config(s3={"addressing_style": "path"}),
    )


def presign_get(settings: Settings, s3_key: str) -> str:
    """URL GET presignada de ``PRESIGN_TTL_S`` sobre el bucket de evidencia."""
    return s3_client(settings).generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.evidence_bucket, "Key": s3_key},
        ExpiresIn=PRESIGN_TTL_S,
    )


def read_object(settings: Settings, s3_key: str) -> bytes | None:
    """Lee el objeto COMPLETO del bucket de evidencia (verificación de hash,
    T-2.10). ``None`` si no existe. Se usa server-side: alterar un byte del blob
    tras la captura cambia su SHA-256 y la verificación falla."""
    client = s3_client(settings)
    try:
        resp = client.get_object(Bucket=settings.evidence_bucket, Key=s3_key)
    except client.exceptions.NoSuchKey:
        return None
    return resp["Body"].read()


def presign_put(settings: Settings, s3_key: str, *, content_type: str | None = None) -> str:
    """URL PUT presignada (subida directa del cliente) sobre el bucket de evidencia.

    [T-2.03] La app móvil sube assets/evidencia SIN credenciales AWS: el backend
    firma la intención de subida (regla de oro 6) con TTL corto.
    """
    params: dict[str, Any] = {"Bucket": settings.evidence_bucket, "Key": s3_key}
    if content_type:
        params["ContentType"] = content_type
    return s3_client(settings).generate_presigned_url(
        "put_object", Params=params, ExpiresIn=PRESIGN_TTL_S
    )


def put_object(settings: Settings, s3_key: str, body: bytes, *, content_type: str) -> None:
    """Sube un objeto al bucket de evidencia."""
    s3_client(settings).put_object(
        Bucket=settings.evidence_bucket, Key=s3_key, Body=body, ContentType=content_type
    )
