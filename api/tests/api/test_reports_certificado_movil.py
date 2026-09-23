"""[T-8.12 · A-054] El certificado del móvil sólo sirve un informe POSTERIOR a la firma.

`GET /incidents/{id}/dictamen` exige un dictamen firmado, pero su `pdf_url` era
el `report_pdf` MÁS RECIENTE del incidente, sin mirar cuándo se generó. Firmar no
regenera el PDF, y el móvil no llama a `/report`. El flujo de la demostración
—el inspector firma en el teléfono, el brigadista pulsa «DESCARGAR CERTIFICADO»—
entregaba el documento que dice «DICTAMEN OPERATIVO PRELIMINAR · SIN FIRMA DE
INSPECTOR», o ninguno.

## Qué se eligió, y por qué

**Se GENERA en ese momento**, con la MISMA función que usa la consola
(`routers/reports.generate_report`, llamada como función), y no un `pdf_url=null`:

* es el flujo de la presentación, y con `null` el certificado no existiría
  justo cuando la RBAC §3 lo concede;
* es idempotente por firma: la primera lectura lo genera, las siguientes sirven
  ése —la consulta es «un informe con `created_at` ≥ la firma vigente»—, y dos
  lecturas simultáneas no generan dos (candado consultivo de la transacción);
* respeta el mismo freno de exportación; si se agota, `null`, y la siguiente
  lectura lo vuelve a intentar (el móvil no sondea: pide al abrir o enfocar).

`pdf_url=null` queda para lo que NO se puede certificar: una corrección posterior
a la firma que nadie ha firmado (cualquier PDF de hoy diría PRELIMINAR), y el
bucket sin configurar.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote

import pytest
from fastapi import FastAPI
from moto import mock_aws
from pypdf import PdfReader
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.reports import router as reports_router

pytestmark = pytest.mark.asyncio

BUCKET = "takab-dev-evidence"
_REGION = "us-east-2"
_BRIGADISTA = "b0000000-0000-0000-0000-00000000c812"


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(reports_router)
    return application


@pytest.fixture(autouse=True)
def _bucket_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_EVIDENCE_BUCKET", BUCKET)
    monkeypatch.setenv("TAKAB_API_AWS_REGION", _REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)


def _crea_bucket() -> None:
    import boto3

    boto3.client("s3", region_name=_REGION).create_bucket(
        Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": _REGION}
    )


def _objeto(key: str) -> bytes:
    import boto3

    return boto3.client("s3", region_name=_REGION).get_object(Bucket=BUCKET, Key=key)["Body"].read()


def _brig() -> dict[str, str]:
    return au.bearer(
        au.make_token(
            "brigadista",
            tenant=au.DB_TENANT_PRIV,
            user_id=_BRIGADISTA,
            surface="mobile",
            site_scope=au.DB_SITE_PRIV,
        )
    )


def _inspector() -> dict[str, str]:
    return au.bearer(au.make_token("inspector", tenant=au.DB_TENANT_PRIV))


async def _firma(iid: str, *, cuando: datetime | None = None, firmado: bool = True) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, "
                "created_at) VALUES (:t, :i, 'inhabit_monitor', '{}'::jsonb, :by, "
                "COALESCE(CAST(:c AS timestamptz), now()))"
            ),
            {
                "t": au.DB_TENANT_PRIV,
                "i": iid,
                "by": str(uuid.uuid4()) if firmado else None,
                "c": cuando,
            },
        )


async def _informes(iid: str) -> list:
    async with get_engine().begin() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT s3_key, created_at FROM evidence_objects "
                    "WHERE incident_id = :i AND kind = 'report_pdf' ORDER BY created_at"
                ),
                {"i": iid},
            )
        ).all()


def _encabezado(pdf: bytes) -> str:
    return PdfReader(io.BytesIO(pdf)).pages[0].extract_text() or ""


async def test_NO_sirve_el_informe_PRELIMINAR_generado_antes_de_la_firma(
    client, make_incident
) -> None:
    with mock_aws():
        _crea_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        # La consola generó el PDF ANTES de que nadie firmara: dice PRELIMINAR.
        r = await client.post(f"/incidents/{iid}/report", headers=_inspector())
        assert r.status_code == 201, r.text
        [preliminar] = await _informes(iid)
        assert "PRELIMINAR" in _encabezado(_objeto(preliminar.s3_key))
        # El inspector firma DESPUÉS.
        await _firma(iid, cuando=datetime.now(UTC) + timedelta(seconds=1))

        cert = await client.get(f"/incidents/{iid}/dictamen", headers=_brig())
        assert cert.status_code == 200, cert.text
        url = cert.json()["pdf_url"]
        assert url is not None, "no hay certificado justo cuando la RBAC lo concede"
        assert preliminar.s3_key not in unquote(url), (
            "el certificado del móvil sirve el informe PRELIMINAR, anterior a la firma"
        )
        informes = await _informes(iid)
        assert len(informes) == 2, "no se generó el informe firmado"
        servido = next(f for f in informes if f.s3_key in unquote(url))
        encabezado = _encabezado(_objeto(servido.s3_key))
        assert "DICTAMEN OPERATIVO FIRMADO" in encabezado
        assert "DICTAMEN OPERATIVO PRELIMINAR" not in encabezado


async def test_si_ya_hay_un_informe_POSTERIOR_a_la_firma_se_sirve_ESE(
    client, make_incident
) -> None:
    with mock_aws():
        _crea_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        await _firma(iid, cuando=datetime.now(UTC) - timedelta(minutes=5))
        r = await client.post(f"/incidents/{iid}/report", headers=_inspector())
        assert r.status_code == 201, r.text
        [firmado] = await _informes(iid)

        cert = await client.get(f"/incidents/{iid}/dictamen", headers=_brig())
        assert firmado.s3_key in unquote(cert.json()["pdf_url"])
        assert len(await _informes(iid)) == 1, "regeneró un informe que ya existía"


async def test_un_informe_POSTERIOR_a_la_firma_pero_renderizado_SIN_ella_no_se_sirve(
    client, make_incident
) -> None:
    """[T-8.12 · 2ª vuelta] `created_at >= firma` compara el `now()` de DOS
    transacciones distintas. Una exportación que EMPEZÓ después que la de la firma
    pero leyó la cadena de dictámenes ANTES de su commit renderiza el PRELIMINAR y
    queda con una fecha posterior a la firma. La ventana es de milisegundos; la
    prueba la reproduce con las dos filas que esa exportación dejaría: su objeto
    de evidencia y su `export_pdf`, cuyo dictamen vigente NO era el firmado."""
    with mock_aws():
        _crea_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        await _firma(iid, cuando=datetime.now(UTC) - timedelta(minutes=5))
        colado = f"evidence/{au.DB_TENANT_PRIV}/{iid}/report-technical-colado.pdf"
        async with get_engine().begin() as conn:
            ev = (
                await conn.execute(
                    text(
                        "INSERT INTO evidence_objects (tenant_id, incident_id, kind, s3_key, "
                        "sha256) VALUES (:t, :i, 'report_pdf', :k, :s) RETURNING evidence_id"
                    ),
                    {"t": au.DB_TENANT_PRIV, "i": iid, "k": colado, "s": "f" * 64},
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO audit_log (tenant_id, actor, verb, object, meta) "
                    "VALUES (:t, 'user:consola', 'export_pdf', :o, CAST(:m AS jsonb))"
                ),
                {
                    "t": au.DB_TENANT_PRIV,
                    "o": f"evidence:{ev}",
                    # La cabeza que ESA exportación leyó: ninguna (aún no había firma).
                    "m": '{"variant": "technical", "dictamen_vigente": null}',
                },
            )
        cert = await client.get(f"/incidents/{iid}/dictamen", headers=_brig())
        url = cert.json()["pdf_url"]
        assert url is not None
        assert colado not in unquote(url), (
            "sirvió como certificado un informe renderizado sin la firma vigente"
        )
        servido = next(f for f in await _informes(iid) if f.s3_key in unquote(url))
        assert "DICTAMEN OPERATIVO FIRMADO" in _encabezado(_objeto(servido.s3_key))


async def test_DOS_lecturas_NO_generan_dos_certificados(client, make_incident) -> None:
    with mock_aws():
        _crea_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        await _firma(iid)
        a = await client.get(f"/incidents/{iid}/dictamen", headers=_brig())
        b = await client.get(f"/incidents/{iid}/dictamen", headers=_brig())
        assert a.json()["pdf_url"] and b.json()["pdf_url"]
        assert len(await _informes(iid)) == 1


async def test_DOS_lecturas_SIMULTANEAS_generan_UN_solo_certificado(client, make_incident) -> None:
    """[T-8.12 · 2ª vuelta] La de arriba es SECUENCIAL: la segunda lectura encuentra
    el informe ya confirmado y el candado nunca se disputa. Aquí las dos van a la
    vez (`asyncio.gather`): el render va a un hilo, así que la primera suelta el
    loop mientras genera y la segunda llega con el candado cogido."""
    import asyncio

    with mock_aws():
        _crea_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        await _firma(iid)
        a, b = await asyncio.gather(
            client.get(f"/incidents/{iid}/dictamen", headers=_brig()),
            client.get(f"/incidents/{iid}/dictamen", headers=_brig()),
        )
        assert a.status_code == b.status_code == 200, (a.text, b.text)
        urls = [r.json()["pdf_url"] for r in (a, b)]
        assert any(urls), "ninguna de las dos lecturas obtuvo el certificado"
        assert len(await _informes(iid)) == 1, "dos lecturas a la vez generaron DOS informes"
        # La que perdió el candado no inventa uno: vuelve sin PDF, y la siguiente
        # lectura sirve el que generó la otra.
        c = await client.get(f"/incidents/{iid}/dictamen", headers=_brig())
        assert c.json()["pdf_url"]
        assert len(await _informes(iid)) == 1


async def test_una_correccion_SIN_FIRMAR_posterior_no_se_certifica(client, make_incident) -> None:
    """Cualquier PDF de hoy diría PRELIMINAR: la cabeza de la cadena no está firmada."""
    with mock_aws():
        _crea_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        await _firma(iid, cuando=datetime.now(UTC) - timedelta(minutes=5))
        await _firma(iid, firmado=False)
        cert = await client.get(f"/incidents/{iid}/dictamen", headers=_brig())
        assert cert.status_code == 200
        assert cert.json()["signed"] is True
        assert cert.json()["pdf_url"] is None
        assert await _informes(iid) == [], "generó un PDF que habría dicho PRELIMINAR"


async def test_la_generacion_desde_el_movil_queda_AUDITADA_con_su_origen(
    client, make_incident
) -> None:
    with mock_aws():
        _crea_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        await _firma(iid)
        await client.get(f"/incidents/{iid}/dictamen", headers=_brig())
    async with get_engine().begin() as conn:
        filas = (
            await conn.execute(text("SELECT actor, meta FROM audit_log WHERE verb = 'export_pdf'"))
        ).all()
    assert len(filas) == 1
    assert filas[0].actor == f"user:{_BRIGADISTA}"
    assert filas[0].meta["origen"] == "certificado_movil"
    assert filas[0].meta["site_id"] == au.DB_SITE_PRIV


async def test_el_ORIGEN_lo_estampa_quien_llama_y_no_el_ROL_de_quien_lee(
    client, make_incident
) -> None:
    """[T-8.12 · 2ª vuelta] Un INSPECTOR también tiene `dictamen_read`, y además tiene
    `generate_report`. El origen se DEDUCÍA del rol —`None` si el rol podía exportar—,
    así que cuando el inspector abría el certificado en el móvil y lo disparaba, la
    exportación quedaba auditada como si la hubiera pedido la consola. Y al revés:
    una exportación de la consola nunca puede salir marcada como del móvil."""
    with mock_aws():
        _crea_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        await _firma(iid)
        cert = await client.get(f"/incidents/{iid}/dictamen", headers=_inspector())
        assert cert.status_code == 200, cert.text
        assert cert.json()["pdf_url"], "no se generó el certificado"
        r = await client.post(f"/incidents/{iid}/report", headers=_inspector())
        assert r.status_code == 201, r.text
    async with get_engine().begin() as conn:
        filas = (
            await conn.execute(
                text("SELECT meta FROM audit_log WHERE verb = 'export_pdf' ORDER BY audit_id")
            )
        ).all()
    assert [f.meta.get("origen") for f in filas] == ["certificado_movil", None], (
        "el origen de la exportación salió del ROL y no de QUIÉN la pidió"
    )


async def test_el_origen_NO_es_un_parametro_que_la_red_pueda_elegir() -> None:
    """La consola no puede declararse «certificado del móvil»: el origen no aparece
    en el contrato público del endpoint (la app de producción, sin el router doble
    del fixture de este módulo)."""
    esquema = create_app().openapi()["paths"]["/incidents/{incident_id}/report"]["post"]
    nombres = {p["name"] for p in esquema.get("parameters", [])}
    assert "origen" not in nombres, nombres


async def test_si_la_generacion_FALLA_el_certificado_sigue_en_pie(
    client, make_incident, monkeypatch
) -> None:
    """S3 caído: los metadatos del dictamen firmado salen igual, sin PDF, y la
    lectura queda auditada. Antes de esta ficha el endpoint no generaba nada y no
    podía caerse por S3; generar no puede convertirlo en un 500."""
    from takab_api.routers import reports as reports_mod

    def revienta(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("S3 no responde (prueba)")

    monkeypatch.setattr(reports_mod, "put_object", revienta)
    with mock_aws():
        _crea_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        await _firma(iid)
        cert = await client.get(f"/incidents/{iid}/dictamen", headers=_brig())
    assert cert.status_code == 200, cert.text
    assert cert.json()["signed"] is True
    assert cert.json()["pdf_url"] is None
    assert await _informes(iid) == [], "quedó una fila de evidencia sin su objeto"
    async with get_engine().begin() as conn:
        leidas = (
            await conn.execute(
                text("SELECT count(*) FROM audit_log WHERE verb = 'dictamen_read' AND object = :o"),
                {"o": f"incident:{iid}"},
            )
        ).scalar_one()
    assert leidas == 1, "la lectura del certificado no quedó auditada"
