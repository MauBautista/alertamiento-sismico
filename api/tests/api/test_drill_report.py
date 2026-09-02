"""Reporte post-simulacro (T-5.14) — la evidencia que se le enseña a Protección Civil.

Lo que fija, y en este orden:

* **Las tres categorías no se colapsan.** «No tenía gabinete comandable» NO es
  «no acusó»: el primero es un problema de inventario y el segundo de operación,
  y quien lee el documento reacciona distinto a cada uno.
* **Un sitio sin acuse no cuenta como cero en el tiempo.** Meterlo en la media la
  hundiría justo con los sitios que peor están — la forma más elegante de que un
  número diga lo contrario de lo que pasa.
* **Determinista.** Dos exportaciones del mismo simulacro dan los MISMOS bytes,
  porque el sello fija la fecha al arranque del simulacro y no al reloj de quien
  exporta. Sin eso la huella no probaría nada.
* Y las propiedades del dictamen: hasheado, registrado como evidencia inmutable y
  auditado.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from moto import mock_aws
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.drill_report import ReporteSimulacro, SitioReporte, render
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.drills import router as drills_router
from tests.api.test_commands_router import (  # noqa: F401  (fixtures por nombre)
    KEY,
    THING,
    _FakePublisher,
    gateway,
    publisher,
)

BUCKET = "takab-dev-evidence"
_REGION = "us-east-2"
BASE = datetime(2026, 9, 2, 18, 0, tzinfo=UTC)


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.include_router(drills_router)
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _hmac_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))
    monkeypatch.setenv("TAKAB_API_EVIDENCE_BUCKET", BUCKET)
    monkeypatch.setenv("TAKAB_API_AWS_REGION", _REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)


def _token(role: str = "tenant_admin") -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=au.DB_TENANT_PRIV, site_scope="*"))


def _bucket() -> None:
    import boto3

    boto3.client("s3", region_name=_REGION).create_bucket(
        Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": _REGION}
    )


async def _sql(sql: str, **p):
    engine = get_engine()
    async with engine.begin() as conn:
        r = await conn.execute(text(sql), p)
        return r.fetchall() if r.returns_rows else []


# ─────────────────────────────────────── el modelo, sin base ni red


def _rep(*sitios: SitioReporte) -> ReporteSimulacro:
    return ReporteSimulacro(
        folio="TKB-DRILL-ABCDEF12",
        tenant_name="Cliente",
        drill_id="abcdef12-0000-0000-0000-000000000000",
        started_at=BASE,
        stopped_at=BASE + timedelta(minutes=5),
        duration_s=300,
        note="trimestral",
        sitios=list(sitios),
    )


def test_las_tres_categorias_no_se_colapsan() -> None:
    r = _rep(
        SitioReporte("Torre A", commandable=True, acked=True, latency_s=12.0),
        SitioReporte("Torre B", commandable=True, acked=False, latency_s=None),
        SitioReporte("Bodega", commandable=False, acked=False, latency_s=None),
    )
    assert [s.site_name for s in r.acusaron] == ["Torre A"]
    assert [s.site_name for s in r.no_acusaron] == ["Torre B"]
    assert [s.site_name for s in r.sin_gabinete] == ["Bodega"]


def test_un_sitio_sin_acuse_NO_cuenta_como_CERO_en_el_tiempo() -> None:
    """El defecto que esto impide: una media hundida por los que peor están."""
    r = _rep(
        SitioReporte("A", commandable=True, acked=True, latency_s=100.0),
        SitioReporte("B", commandable=True, acked=True, latency_s=200.0),
        SitioReporte("C", commandable=True, acked=False, latency_s=None),
    )
    # Con el cero dentro la mediana seria 100; sin el, 150. La segunda es la real.
    assert r.latencia_mediana_s == 150.0
    assert r.latencia_maxima_s == 200.0


def test_sin_un_solo_acuse_los_tiempos_son_NULL_y_el_pdf_lo_declara() -> None:
    r = _rep(SitioReporte("A", commandable=True, acked=False, latency_s=None))
    assert r.latencia_mediana_s is None
    pdf = render(r)
    assert pdf.startswith(b"%PDF")


def test_el_mismo_simulacro_produce_los_MISMOS_bytes() -> None:
    """Determinista, y por eso la huella prueba algo.

    El sello fija la fecha al ARRANQUE del simulacro, no al reloj de quien
    exporta: si fuera lo segundo, dos exportaciones del mismo simulacro darían
    hashes distintos y el sha256 registrado no serviría para nada.
    """
    r = _rep(SitioReporte("A", commandable=True, acked=True, latency_s=42.0))
    assert render(r) == render(
        _rep(SitioReporte("A", commandable=True, acked=True, latency_s=42.0))
    )


# ─────────────────────────────────────────────── el endpoint completo


async def _simulacro(client, publisher) -> str:
    r = await client.post(
        "/drills",
        json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 120, "note": "trimestral"},
        headers=_token(),
    )
    assert r.status_code == 201, r.text
    return r.json()["drill_id"]


async def test_el_reporte_se_sube_se_hashea_se_registra_y_se_audita(client, gateway, publisher):
    with mock_aws():
        _bucket()
        did = await _simulacro(client, publisher)
        r = await client.post(f"/drills/{did}/report", headers=_token())
        assert r.status_code == 201, r.text
        body = r.json()

        filas = await _sql(
            "SELECT kind, s3_key, sha256, drill_id FROM evidence_objects"
            " WHERE drill_id = CAST(:d AS uuid)",
            d=did,
        )
        assert len(filas) == 1, "el reporte no quedó registrado como evidencia"
        assert filas[0].kind == "report_pdf"
        assert filas[0].sha256 == body["sha256"]

        import boto3

        obj = boto3.client("s3", region_name=_REGION).get_object(Bucket=BUCKET, Key=filas[0].s3_key)
        pdf = obj["Body"].read()
        assert pdf.startswith(b"%PDF")
        assert hashlib.sha256(pdf).hexdigest() == body["sha256"]

        verbos = await _sql("SELECT verb, meta FROM audit_log WHERE verb = 'export_drill_report'")
        assert verbos, "la exportación no dejó huella en la bitácora"
        assert verbos[0].meta["drill_id"] == did


async def test_el_reporte_cuenta_las_tres_categorias_por_separado(client, gateway, publisher):
    with mock_aws():
        _bucket()
        did = await _simulacro(client, publisher)
        body = (await client.post(f"/drills/{did}/report", headers=_token())).json()
        # El sitio tiene gabinete comandable y NO acusó (nadie mandó un ack).
        assert body["no_gateway"] == 0
        assert body["not_acked"] == 1
        assert body["acked"] == 0
        # Y sin acuses no hay tiempos: `null`, jamás cero.
        assert body["median_latency_s"] is None


async def test_una_AGENDA_no_tiene_acuses_que_reportar(client, gateway, publisher):
    """Exportarla produciría un documento que afirma cero de cero."""
    with mock_aws():
        _bucket()
        futuro = (datetime.now(tz=UTC) + timedelta(days=1)).isoformat()
        r = await client.post(
            "/drills",
            json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 120, "scheduled_at": futuro},
            headers=_token(),
        )
        did = r.json()["drill_id"]
        rep = await client.post(f"/drills/{did}/report", headers=_token())
        assert rep.status_code == 409, rep.text


@pytest.mark.parametrize("role", ["soc_operator", "inspector", "gov_operator"])
async def test_roles_sin_drill_start_no_exportan(client, gateway, publisher, role):
    with mock_aws():
        _bucket()
        did = await _simulacro(client, publisher)
        r = await client.post(f"/drills/{did}/report", headers=_token(role))
        assert r.status_code == 403
