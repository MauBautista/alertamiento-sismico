"""[T-9.34 · D-43] Quién firmó se lee de `signature_kind`, y el papel lo dice.

Con D-43 firman TRES: el inspector (como siempre), una persona que CONFIRMA un
AMARILLO que emitió la regla, y el SISTEMA (un VERDE tras la gracia, con la
identidad fija `SYSTEM_DICTAMEN_SIGNER_UUID`). Hasta esta ficha el papel sólo
conocía «firmado» = «lo firmó el inspector»: un VERDE del sistema habría salido
como «FIRMÓ INSPECTOR» —derivado de la matriz— y el deslinde lo habría llamado
«FIRMADO por inspector». Un papel con peso legal no puede atribuir una firma a
quien no firmó.

Lo que se fija aquí:

* ``system`` ⇒ «EMITIDO POR EL SISTEMA · regla dictamen-v2 · banda VERDE», sin la
  palabra INSPECTOR en la sección de firma ni en el deslinde, y sin el UUID fijo.
* ``confirmation`` ⇒ «CONFIRMADO POR <rol>» con el nombre si existe; el rol sale
  de la bitácora (`audit_log.meta.role` del `dictamen_confirmed`), y si no consta
  se DECLARA en vez de suponerlo.
* ``inspector`` y NULL (histórico) ⇒ como hoy.
* La banda se ve: en el banner de la portada y en la cadena de dictámenes.
* Nunca un identificador interno.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.dictamen import model as dm
from takab_api.dictamen import rotulos
from takab_api.dictamen.builder import build_model
from takab_api.dictamen.model import DictamenRow
from takab_api.dictamen.pdf import render
from takab_api.dictamen.sistema import SYSTEM_DICTAMEN_SIGNER_UUID
from tests.dictamen.test_pdf import _OPENED, model
from tests.documentos.espia import espia_del_render

_SUB = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
_FIRMA = "FIRMA Y DESLINDE"


def _preliminar(status: str, band: str | None) -> DictamenRow:
    return DictamenRow("d-1", status, _OPENED, None, "dictamen-v2", None, band=band)


def _sistema() -> list[DictamenRow]:
    return [
        DictamenRow(
            "d-2",
            "normal_operation",
            _OPENED + timedelta(minutes=6),
            SYSTEM_DICTAMEN_SIGNER_UUID,
            "dictamen-v2",
            "d-1",
            signature_kind="system",
            band="verde",
        ),
        _preliminar("normal_operation", "verde"),
    ]


def _confirmado(rol: str | None, nombre: str | None) -> list[DictamenRow]:
    return [
        DictamenRow(
            "d-2",
            "inhabit_monitor",
            _OPENED + timedelta(minutes=20),
            _SUB,
            "sin versión",
            "d-1",
            firmante_nombre=nombre,
            signature_kind="confirmation",
            band="amarillo",
            firmante_rol=rol,
        ),
        _preliminar("inhabit_monitor", "amarillo"),
    ]


def _cap(dictamens: list[DictamenRow], variante: str = "technical", **over):  # noqa: ANN003, ANN202
    m = model(
        dictamens=dictamens,
        verdict_signed=bool(dictamens[0].signed_by),
        verdict_status=dictamens[0].status,
        **over,
    )
    with espia_del_render() as cap:
        render(m, variante)
    return cap


# ───────────────────────────────────────────────────────── el SISTEMA


def test_el_VERDE_del_sistema_se_rotula_EMITIDO_POR_EL_SISTEMA_con_regla_y_banda() -> None:
    cap = _cap(_sistema())
    firma = cap.seccion(_FIRMA)
    assert "EMITIDO POR EL SISTEMA · regla dictamen-v2 · banda VERDE" in firma
    assert "INSPECTOR" not in firma, f"firma del sistema atribuida al inspector:\n{firma}"


def test_el_sistema_NUNCA_imprime_su_identificador_interno() -> None:
    for variante in ("technical", "executive"):
        cap = _cap(_sistema(), variante)
        assert SYSTEM_DICTAMEN_SIGNER_UUID not in cap.texto
        assert SYSTEM_DICTAMEN_SIGNER_UUID not in cap.membrete


def test_el_encabezado_y_el_deslinde_del_sistema_no_dicen_inspector_ni_preliminar() -> None:
    for variante in ("technical", "executive"):
        cap = _cap(_sistema(), variante)
        deslinde = [ln for ln in cap.texto.splitlines() if "No sustituye la evaluación" in ln]
        assert deslinde, "desapareció el deslinde"
        assert dm.DISCLAIMER_ESTADO[True] not in deslinde[0], deslinde[0]
        assert "PRELIMINAR" not in deslinde[0], deslinde[0]
        assert dm.DISCLAIMER_FIRMA["system"] in deslinde[0]
    encabezados = [
        ln for ln in _cap(_sistema()).membrete.splitlines() if ln.startswith("DICTAMEN OPERATIVO")
    ]
    assert encabezados and all("PRELIMINAR" not in ln for ln in encabezados), encabezados
    assert all("EMITIDO POR EL SISTEMA" in ln for ln in encabezados), encabezados


def test_la_prosa_no_atribuye_a_una_persona_lo_que_firmo_el_sistema() -> None:
    from takab_api.narrative.deterministic import sections_for  # noqa: PLC0415
    from takab_api.narrative.redact import facts_from  # noqa: PLC0415

    m = model(dictamens=_sistema(), verdict_signed=True, verdict_status="normal_operation")
    prosa = "\n".join(cuerpo for _, cuerpo in sections_for(facts_from(m)))
    for mentira in (
        "firmado por un inspector",
        "lo firmó un inspector",
        "una persona",
        "preliminar",
    ):
        assert mentira not in prosa.lower(), f"la prosa dice «{mentira}» de un VERDE del sistema"
    assert "firmado por el sistema" in prosa


# ─────────────────────────────────────────────────────── la CONFIRMACIÓN


def test_la_confirmacion_se_rotula_CONFIRMADO_POR_el_rol_y_el_nombre() -> None:
    cap = _cap(_confirmado("brigadista", "Ana Ruiz"))
    firma = cap.seccion(_FIRMA)
    assert "CONFIRMADO POR BRIGADISTA · Ana Ruiz" in firma
    assert "INSPECTOR" not in firma
    assert _SUB not in cap.texto and _SUB not in cap.membrete


def test_la_confirmacion_sin_nombre_lleva_solo_el_rol() -> None:
    firma = _cap(_confirmado("tenant_admin", None)).seccion(_FIRMA)
    assert "CONFIRMADO POR ADMINISTRADOR" in firma


def test_la_confirmacion_sin_rol_en_la_bitacora_lo_DECLARA() -> None:
    """Suponer «brigadista» por costumbre sería afirmar un rol que no consta."""
    firma = _cap(_confirmado(None, None)).seccion(_FIRMA)
    assert f"CONFIRMADO POR {dm.ROL_CONFIRMANTE_NO_CONSTA}" in firma
    assert "BRIGADISTA" not in firma


def test_el_deslinde_de_una_confirmacion_no_dice_inspector() -> None:
    cap = _cap(_confirmado("brigadista", None))
    deslinde = [ln for ln in cap.texto.splitlines() if "No sustituye la evaluación" in ln]
    assert deslinde and dm.DISCLAIMER_ESTADO[True] not in deslinde[0], deslinde
    assert dm.DISCLAIMER_FIRMA["confirmation"] in deslinde[0]


# ───────────────────────────────────── el inspector y lo histórico, como hoy


@pytest.mark.parametrize("kind", ["inspector", None])
def test_inspector_e_historico_se_rotulan_como_hoy(kind: str | None) -> None:
    filas = [
        DictamenRow(
            "d-2",
            "inhabit_monitor",
            _OPENED + timedelta(hours=2),
            _SUB,
            "dictamen-v1",
            "d-1",
            firmante_nombre="Ing. Laura Méndez",
            signature_kind=kind,
        ),
        DictamenRow("d-1", "inhabit_monitor", _OPENED, None, "dictamen-v1", None),
    ]
    cap = _cap(filas)
    assert "INSPECTOR · Ing. Laura Méndez" in cap.seccion(_FIRMA)
    assert dm.DISCLAIMER_ESTADO[True] in cap.texto


# ─────────────────────────────────────────────────────────── la BANDA


@pytest.mark.parametrize(
    ("status", "band", "rotulo"),
    [
        ("normal_operation", "verde", "BANDA VERDE"),
        ("inhabit_monitor", "amarillo", "BANDA AMARILLA"),
        ("no_inhabit_inspect", "rojo", "BANDA ROJA"),
    ],
)
def test_la_banda_se_ve_en_la_portada_y_en_la_cadena(status: str, band: str, rotulo: str) -> None:
    cap = _cap([_preliminar(status, band)])
    assert rotulo in cap.seccion("CADENA DE DICTÁMENES")
    portada = cap.texto.split("CLASIFICACIÓN")[0]
    assert rotulo in portada, f"la banda no se ve en la portada: {portada[:300]!r}"
    assert rotulo in _cap([_preliminar(status, band)], "executive").texto


def test_un_dictamen_v1_sin_banda_no_inventa_una() -> None:
    cap = _cap([DictamenRow("d-1", "inhabit_monitor", _OPENED, None, "dictamen-v1", None)])
    for rotulo in rotulos.BANDA.values():
        assert rotulo not in cap.texto


def test_el_amarillo_sin_firmar_dice_que_espera_confirmacion() -> None:
    firma = _cap([_preliminar("inhabit_monitor", "amarillo")]).seccion(_FIRMA)
    assert dm.PENDIENTE_CONFIRMACION in firma


def test_los_rotulos_de_banda_cubren_el_CHECK_del_DDL() -> None:
    assert set(rotulos.BANDA) == {"verde", "amarillo", "rojo"}


# ─────────────────────────────────────────────────────────── el BUILDER


@pytest.mark.asyncio
async def test_el_builder_trae_tipo_banda_y_el_ROL_del_que_confirmo(
    base_data, make_incident
) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    quien = str(uuid.uuid4())
    async with get_engine().begin() as conn:
        d1 = (
            await conn.execute(
                text(
                    "INSERT INTO dictamens (tenant_id, incident_id, status, basis, band, "
                    "created_at) VALUES (:t, :i, 'inhabit_monitor', "
                    "'{\"rule_set_version\": \"dictamen-v2\"}'::jsonb, 'amarillo', "
                    "now() - interval '5 minutes') RETURNING dictamen_id"
                ),
                {"t": au.DB_TENANT_PRIV, "i": iid},
            )
        ).scalar_one()
        d2 = (
            await conn.execute(
                text(
                    "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, "
                    "supersedes_dictamen_id, signature_kind, band) VALUES (:t, :i, "
                    "'inhabit_monitor', '{}'::jsonb, :u, :d1, 'confirmation', 'amarillo') "
                    "RETURNING dictamen_id"
                ),
                {"t": au.DB_TENANT_PRIV, "i": iid, "u": quien, "d1": d1},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO audit_log (tenant_id, actor, verb, object, meta) "
                "VALUES (:t, :a, 'dictamen_confirmed', :o, CAST(:m AS jsonb))"
            ),
            {
                "t": au.DB_TENANT_PRIV,
                "a": f"user:{quien}",
                "o": f"incident:{iid}",
                "m": json.dumps({"dictamen_id": str(d2), "role": "brigadista"}),
            },
        )
    ctx = SessionCtx(tenant_id=au.DB_TENANT_PRIV, role="inspector", user_id=quien)
    async with get_tenant_conn(ctx) as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))
    assert m is not None
    cabeza, cola = m.dictamens
    assert (cabeza.signature_kind, cabeza.band, cabeza.firmante_rol) == (
        "confirmation",
        "amarillo",
        "brigadista",
    )
    assert (cola.signature_kind, cola.band, cola.firmante_rol) == (None, "amarillo", None)
    with espia_del_render() as cap:
        render(m, "technical")
    assert "CONFIRMADO POR BRIGADISTA" in cap.seccion(_FIRMA)
    assert quien not in cap.texto


def test_en_la_cronologia_quien_CONFIRMO_no_es_INSPECTOR() -> None:
    """`firmantes_de_la_cadena` nombraba a todo firmante con el rol de la matriz."""
    from takab_api.dictamen.model import ActionRow  # noqa: PLC0415

    cap = _cap(
        _confirmado("brigadista", "Ana Ruiz"),
        actions=[ActionRow(_OPENED, "dictamen_confirmed", f"user:{_SUB}")],
    )
    crono = cap.seccion("CRONOLOGÍA DEL INCIDENTE")
    assert "BRIGADISTA · Ana Ruiz" in crono
    assert "INSPECTOR" not in crono
    assert (
        rotulos.firmantes_de_la_cadena([(SYSTEM_DICTAMEN_SIGNER_UUID, None, "system", None)]) == {}
    )


@pytest.mark.asyncio
async def test_el_builder_lee_el_ROL_del_BASIS_sin_la_bitacora(base_data, make_incident) -> None:
    """[F3·r2] La confirmación guarda ``basis.confirmacion.rol``: el papel lo rotula
    aunque la fila de bitácora no exista (o la lectura del papel no la alcance)."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    quien = str(uuid.uuid4())
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, "
                "signature_kind, band) VALUES (:t, :i, 'inhabit_monitor', "
                '\'{"confirmacion": {"rol": "tenant_admin"}}\'::jsonb, :u, '
                "'confirmation', 'amarillo')"
            ),
            {"t": au.DB_TENANT_PRIV, "i": iid, "u": quien},
        )
    ctx = SessionCtx(tenant_id=au.DB_TENANT_PRIV, role="inspector", user_id=quien)
    async with get_tenant_conn(ctx) as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))
    assert m is not None
    assert m.dictamens[0].firmante_rol == "tenant_admin"


# ───────────────────────────── F3·r3 · el inspector que confirma, el daño rojo


def test_si_CONFIRMA_un_INSPECTOR_el_deslinde_no_dice_sin_firma_de_inspector() -> None:
    """El papel imprimía a la vez «CONFIRMADO POR INSPECTOR» y un deslinde que decía
    «… sin firma de inspector». Una de las dos frases era falsa."""
    cap = _cap(_confirmado("inspector", None))
    deslinde = [ln for ln in cap.texto.splitlines() if "No sustituye la evaluación" in ln]
    assert deslinde, cap.texto
    assert "sin firma de inspector" not in deslinde[0], deslinde
    assert dm.DISCLAIMER_CONFIRMACION_INSPECTOR in deslinde[0]
    assert "CONFIRMADO POR INSPECTOR" in cap.seccion(_FIRMA)


def test_si_CONFIRMA_la_brigada_el_deslinde_sigue_diciendo_sin_firma_de_inspector() -> None:
    cap = _cap(_confirmado("brigadista", None))
    assert dm.DISCLAIMER_CONFIRMACION in cap.texto
    assert dm.DISCLAIMER_CONFIRMACION_INSPECTOR not in cap.texto


def test_AMARILLO_sin_firmar_con_un_dano_ROJO_espera_al_INSPECTOR_no_a_la_brigada() -> None:
    """La API se niega a confirmar (409 «requiere inspector») un AMARILLO con un daño
    rojo reportado que la regla aún no subió: el papel no puede decir que espera a
    la brigada."""
    from takab_api.dictamen.model import DanoFila

    dano = DanoFila(
        report_id="r-1",
        rol="brigadista",
        zona=None,
        categorias=[{"key": "structural", "severity": "critical"}],
        personas_en_riesgo=False,
        notas=None,
        ts=_OPENED + timedelta(minutes=3),
    )
    cap = _cap([_preliminar("inhabit_monitor", "amarillo")], danos=[dano])
    firma = cap.seccion(_FIRMA)
    assert dm.PENDIENTE_FIRMA_INSPECTOR in firma
    assert dm.PENDIENTE_CONFIRMACION not in firma
    assert "PENDIENTE DE CONFIRMACIÓN" not in cap.texto
