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
from seed_shared import SITE_NAME, TENANT_NAME
from takab_api.db.engine import get_engine
from takab_api.drill_report import (
    ReporteSimulacro,
    SitioReporte,
    linea_de_aborto,
    linea_de_audio,
    linea_de_cierre,
    motivo_sin_acuse,
    nombre_presentable,
    render,
)
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

#: Un uuid de sitio cualquiera, para el caso «sin nombre y sin código».
UUID_SITIO = "d1000000-0000-0000-0000-000000000009"


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


# ── [T-5.17] Qué sonó, en el documento ─────────────────────────────────────
#
# El hueco que cierra: el sha256 del asset se registraba AL ARRANCAR el gabinete,
# no al sonar, y la única constancia de la reproducción era una línea del journal
# de ese Pi. Un reporte de cumplimiento que dice «se voceó» sin decir QUÉ no
# responde a la pregunta que le van a hacer.
#
# Se prueba la LÍNEA, no los bytes del PDF: el texto es lo que hay que fijar y
# rasparlo del binario probaría el renderizador, no el enunciado.

AUDIO_OK = {
    "asset_id": "takab-simulacro-v1",
    "sha256": "b" * 64,
    "will_sound": True,
    "reason": "",
}


def test_la_linea_cita_el_asset_y_su_HUELLA() -> None:
    linea = linea_de_audio(SitioReporte("A", True, True, 12.0, audio=AUDIO_OK))
    assert "takab-simulacro-v1" in linea
    # La huella recortada: un PDF no es sitio para 64 caracteres por sitio, y los
    # 16 primeros ya identifican el binario contra el catálogo.
    assert "b" * 16 in linea
    assert "b" * 64 not in linea


def test_un_sitio_que_NO_voceo_lo_dice_con_su_razon() -> None:
    """«No sonó» y «no sabemos qué sonó» son dos respuestas distintas."""
    sin_voceo = {
        "asset_id": None,
        "sha256": None,
        "will_sound": False,
        "reason": "voceo por audio deshabilitado (audio_enabled=false)",
    }
    linea = linea_de_audio(SitioReporte("A", True, True, 12.0, audio=sin_voceo))
    assert "SIN VOCEO" in linea.upper()
    assert "audio_enabled" in linea, "la razón se pierde y el lector no puede actuar"


def test_un_gabinete_que_NO_REPORTA_audio_no_se_confunde_con_uno_que_no_voceo() -> None:
    """Firmware anterior a `T-5.17`: no lo trae. Eso NO es «no sonó»."""
    linea = linea_de_audio(SitioReporte("A", True, True, 12.0, audio=None)).upper()
    assert "NO REPORTADO" in linea
    assert "SIN VOCEO" not in linea


def test_un_asset_LOCAL_sin_id_de_catalogo_se_cita_por_su_huella() -> None:
    """La grabación del sitio no tiene id de catálogo, y su hash sigue valiendo."""
    local = {"asset_id": None, "sha256": "c" * 64, "will_sound": True, "reason": ""}
    linea = linea_de_audio(SitioReporte("A", True, True, 12.0, audio=local))
    assert "c" * 16 in linea
    assert "local" in linea.lower()


def test_el_PDF_sigue_siendo_DETERMINISTA_con_el_audio_dentro() -> None:
    """La huella del reporte solo prueba algo si dos renders coinciden."""
    r = _rep(SitioReporte("A", True, True, 12.0, audio=AUDIO_OK))
    assert render(r) == render(_rep(SitioReporte("A", True, True, 12.0, audio=AUDIO_OK)))


# ── [T-6.16] PRESENTABLE ANTE PROTECCIÓN CIVIL ─────────────────────────────
#
# Lo que faltaba para poder entregarlo: el documento se titulaba con el UUID del
# cliente, no decía CÓMO TERMINÓ el simulacro y, por cada sitio sin acuse, no
# decía POR QUÉ — cuando la consola sí distingue un rechazo de un silencio.
#
# Se prueban las LÍNEAS, no los bytes del PDF: rasparlas del binario probaría el
# renderizador, no el enunciado (misma disciplina que T-5.17).


def test_jamas_se_imprime_un_UUID_donde_hay_NOMBRE() -> None:
    """Un reporte con `d1000000-…` en la cabecera no se entrega a nadie."""
    assert nombre_presentable("Torre Reforma", "TR-01", UUID_SITIO) == "Torre Reforma"
    # Sin nombre, el CÓDIGO — que es lo que el operador teclea y reconoce.
    assert nombre_presentable(None, "TR-01", UUID_SITIO) == "TR-01"
    assert nombre_presentable("", "TR-01", UUID_SITIO) == "TR-01"


def test_un_sitio_SIN_nombre_y_SIN_codigo_se_declara_como_tal() -> None:
    """El uuid recortado se leía como si fuera un nombre. Ahora se rotula.

    No se inventa un nombre ni se deja el hueco: el documento dice que ese sitio
    no tiene nombre registrado y da el identificador para poder buscarlo.
    """
    linea = nombre_presentable(None, None, UUID_SITIO)
    assert "SIN NOMBRE" in linea.upper()
    assert UUID_SITIO[:8] in linea, "sin el identificador, el sitio no se puede buscar"


@pytest.mark.parametrize(
    ("stop_reason", "stopped", "esperado"),
    [
        ("manual", True, "DETENID"),
        ("aborted", True, "ABORTAD"),
        ("cancelled", True, "CANCELAD"),
        ("executed", True, "EJECUTAD"),
        (None, True, "SIN MOTIVO REGISTRADO"),
        (None, False, "SIN CERRAR"),
    ],
)
def test_la_linea_de_cierre_dice_COMO_TERMINO(stop_reason, stopped, esperado) -> None:
    """Un reporte que no dice cómo terminó el simulacro no acredita nada."""
    rep = _rep()
    rep.stop_reason = stop_reason
    rep.stopped_at = BASE + timedelta(minutes=5) if stopped else None
    assert esperado in linea_de_cierre(rep).upper()


def test_el_cierre_por_ALERTA_REAL_lleva_su_motivo() -> None:
    """«Abortado» sin el porqué obliga a preguntar; con él, no."""
    rep = _rep(
        SitioReporte(
            "A",
            True,
            True,
            12.0,
            aborted_at=BASE + timedelta(minutes=1),
            abort_reason="tier instrumental restricted",
        )
    )
    rep.stop_reason = "aborted"
    linea = linea_de_cierre(rep)
    assert "ALERTA REAL" in linea.upper()
    assert "tier instrumental restricted" in linea


def test_la_linea_de_cierre_NO_MIRA_EL_RELOJ() -> None:
    """Determinismo: si dijera «en curso» vs «ventana cumplida» según la hora,
    dos exportaciones del mismo simulacro darían bytes distintos y la huella
    dejaría de probar nada."""
    rep = _rep()
    rep.stop_reason = None
    rep.stopped_at = None
    assert linea_de_cierre(rep) == linea_de_cierre(rep)
    assert str(rep.duration_s) in linea_de_cierre(rep)


def test_el_motivo_del_NO_ACUSE_distingue_el_rechazo_del_silencio() -> None:
    """La consola ya lo distinguía; el documento los colapsaba en un guion.

    Un RECHAZO es un gabinete que recibió la orden, verificó la firma y dijo que
    no —y su razón se puede arreglar—; un SILENCIO es un gabinete que no
    contestó. Reaccionar igual a los dos es no haber leído el reporte.
    """
    rechazado = SitioReporte(
        "A", True, False, None, command_status="rejected", ack_detail="command_enabled=false"
    )
    assert "RECHAZ" in motivo_sin_acuse(rechazado).upper()
    assert "command_enabled=false" in motivo_sin_acuse(rechazado)

    expirado = SitioReporte("B", True, False, None, command_status="expired")
    assert "EXPIR" in motivo_sin_acuse(expirado).upper()

    callado = SitioReporte("C", True, False, None, command_status="pending")
    assert "SIN ACUSE" in motivo_sin_acuse(callado).upper()

    sin_gabinete = SitioReporte("D", False, False, None, command_status=None)
    assert "COMANDABLE" in motivo_sin_acuse(sin_gabinete).upper()


def test_un_sitio_que_acuso_y_luego_ABORTO_lo_dice_en_su_linea() -> None:
    """Acusó (cuenta como acuse) y después cortó el simulacro: las dos cosas."""
    s = SitioReporte(
        "A",
        True,
        True,
        12.0,
        aborted_at=BASE + timedelta(minutes=1),
        abort_reason="SASMEX real",
    )
    r = _rep(s)
    assert [x.site_name for x in r.acusaron] == ["A"], "abortar no borra que acusó"
    assert "ABORT" in linea_de_aborto(s).upper()
    assert "SASMEX real" in linea_de_aborto(s)
    assert linea_de_aborto(SitioReporte("B", True, True, 1.0)) == ""


def test_el_PDF_sigue_siendo_DETERMINISTA_con_el_cierre_y_los_motivos() -> None:
    def modelo() -> ReporteSimulacro:
        r = _rep(
            SitioReporte("A", True, True, 12.0, aborted_at=BASE, abort_reason="SASMEX real"),
            SitioReporte("B", True, False, None, command_status="rejected", ack_detail="demo_mode"),
            SitioReporte("C", False, False, None),
        )
        r.stop_reason = "aborted"
        return r

    assert render(modelo()) == render(modelo())


async def test_el_documento_lleva_el_NOMBRE_del_cliente_y_del_sitio(
    client, gateway, publisher, monkeypatch
):
    """El endpoint completo: lo que llega al modelo es el nombre, no el UUID.

    Se intercepta el render para leer el MODELO. Raspar el texto del PDF no es
    posible —va comprimido y por glifos— y probaría el renderizador, no que la
    consulta trajo el nombre.
    """
    capturado: dict[str, ReporteSimulacro] = {}

    def espia(rep: ReporteSimulacro) -> bytes:
        capturado["rep"] = rep
        return render(rep)

    monkeypatch.setattr("takab_api.routers.drills.render_drill_report", espia)

    with mock_aws():
        _bucket()
        did = await _simulacro(client, publisher)
        r = await client.post(f"/drills/{did}/report", headers=_token())
        assert r.status_code == 201, r.text

    rep = capturado["rep"]
    assert rep.tenant_name == TENANT_NAME, "la cabecera sigue llevando el UUID del cliente"
    assert au.DB_TENANT_PRIV not in rep.tenant_name
    assert [s.site_name for s in rep.sitios] == [SITE_NAME]
    # Y el estado crudo del comando viaja: sin él no se puede decir POR QUÉ.
    assert rep.sitios[0].command_status == "pending"
    assert rep.stop_reason is None
