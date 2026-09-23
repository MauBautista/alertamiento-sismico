"""[T-8.12] Dos exportaciones en el MISMO segundo no se pisan el objeto.

La clave del informe era `report-<variante>-<AAAAMMDDTHHMMSSZ>.pdf`: sellada al
SEGUNDO. Dos exportaciones de la misma variante dentro del mismo segundo —dos
operadores a la vez, o el certificado del móvil que se genera justo detrás de la
firma— caían en la MISMA clave, la segunda sobrescribía el objeto de la primera
y la fila de evidencia de aquélla quedaba citando un sha256 que ya no casaba con
nada. Se destapó así: el test del certificado, en la suite completa, servía el
PDF firmado bajo la clave del preliminar. Es la clase de defecto de `A-142`
(el reporte de simulacro con clave fija), en el otro generador.

Se fuerza el mismo segundo congelando el reloj del router: dejarlo al azar haría
de esto una prueba intermitente, que es justo como se escondía.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from moto import mock_aws
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers import reports as reports_mod
from takab_api.routers.reports import router as reports_router

pytestmark = pytest.mark.asyncio

BUCKET = "takab-dev-evidence"
_REGION = "us-east-2"
_CONGELADO = datetime(2026, 9, 24, 17, 0, 0, tzinfo=UTC)


class _RelojCongelado(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ANN001, ANN206
        return _CONGELADO if tz is None else _CONGELADO.astimezone(tz)


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(reports_router)
    return application


async def test_DOS_exportaciones_en_el_MISMO_segundo_no_se_pisan(
    client, make_incident, monkeypatch
) -> None:
    import boto3

    monkeypatch.setenv("TAKAB_API_EVIDENCE_BUCKET", BUCKET)
    monkeypatch.setenv("TAKAB_API_AWS_REGION", _REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)
    monkeypatch.setattr(reports_mod, "datetime", _RelojCongelado)
    tok = au.bearer(au.make_token("inspector", tenant=au.DB_TENANT_PRIV))
    with mock_aws():
        s3 = boto3.client("s3", region_name=_REGION)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": _REGION})
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        a = await client.post(f"/incidents/{iid}/report", headers=tok)
        b = await client.post(f"/incidents/{iid}/report", headers=tok)
        assert a.status_code == b.status_code == 201, (a.text, b.text)
        # La segunda exportación lleva a la primera en su cadena de custodia: los
        # bytes son distintos, que es lo que hace dañino compartir la clave.
        assert a.json()["sha256"] != b.json()["sha256"]

        async with get_engine().begin() as conn:
            filas = (
                await conn.execute(
                    text(
                        "SELECT s3_key, sha256 FROM evidence_objects "
                        "WHERE incident_id = :i AND kind = 'report_pdf'"
                    ),
                    {"i": iid},
                )
            ).all()
        assert len(filas) == 2
        assert filas[0].s3_key != filas[1].s3_key, "las dos exportaciones van a la MISMA clave"
        for fila in filas:
            datos = s3.get_object(Bucket=BUCKET, Key=fila.s3_key)["Body"].read()
            assert hashlib.sha256(datos).hexdigest() == fila.sha256, (
                f"la fila {fila.s3_key} cita un sha256 que ya no casa con su objeto"
            )
            # Y sigue reconociéndose como informe del incidente en el backfill.
            assert fila.s3_key.rsplit("/", 1)[-1].startswith("report-")
