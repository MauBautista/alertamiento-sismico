"""Seam de S3: el mismo código habla con AWS real o con un S3 local (MinIO).

Sin este seam el bucket de evidencia SOLO existía en AWS, así que en local
`POST /incidents/{id}/report` moría siempre en 503 ("bucket de evidencia no
configurado") y era imposible ver un reporte generado sin credenciales de AWS.

`s3_endpoint_url` vacío ⇒ AWS real (producción, intacto). Con valor ⇒ ese
endpoint y **path-style** obligatorio: el estilo virtual-host por defecto de
boto3 pide `bucket.127.0.0.1`, que no resuelve en ningún DNS.
"""

from __future__ import annotations

import pytest

from takab_api.routers._s3 import PRESIGN_TTL_S, presign_get, s3_client
from takab_api.settings import Settings


@pytest.fixture(autouse=True)
def _creds(monkeypatch: pytest.MonkeyPatch) -> None:
    # Firmar un presigned URL exige credenciales; crear el cliente no.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")


def test_sin_endpoint_configurado_apunta_a_aws_real() -> None:
    client = s3_client(Settings(evidence_bucket="takab-dev-evidence"))
    assert "amazonaws.com" in client.meta.endpoint_url


def test_con_endpoint_local_usa_ese_host_y_path_style() -> None:
    settings = Settings(
        evidence_bucket="takab-dev-evidence",
        s3_endpoint_url="http://127.0.0.1:9000",
    )
    client = s3_client(settings)

    assert client.meta.endpoint_url == "http://127.0.0.1:9000"
    # virtual-host style daría `takab-dev-evidence.127.0.0.1` ⇒ DNS inexistente.
    assert client.meta.config.s3["addressing_style"] == "path"


def test_presign_local_es_descargable_por_el_navegador() -> None:
    """La consola abre esta URL tal cual (`openDownload`): tiene que resolver."""
    settings = Settings(
        evidence_bucket="takab-dev-evidence",
        s3_endpoint_url="http://127.0.0.1:9000",
    )
    url = presign_get(settings, "evidence/t/i/report.pdf")

    assert url.startswith("http://127.0.0.1:9000/takab-dev-evidence/evidence/t/i/report.pdf")
    assert f"X-Amz-Expires={PRESIGN_TTL_S}" in url
