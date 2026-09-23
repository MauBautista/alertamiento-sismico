"""[T-8.12 · A-145 · A-150 · A-140] Quién firmó, a qué hora local, y los títulos del ejecutivo.

* **FIRMÓ** imprimía `dictamens.signed_by` —el `sub` de Cognito, un UUID entero—
  en la línea de más peso del documento. Ahora: el rol en castellano, DERIVADO de
  la matriz (quien tiene `sign_dictamen`), y el `display_name` de
  `user_profiles` si existe. Nada de UUID en el papel. `D-36` no cambia: el
  renglón de firma del EMISOR sigue siendo la persona moral.
* **La hora**: todo iba en UTC. La UTC se queda —casa con la consola y con el
  pie— y la hora local del inmueble va a su lado, en la portada, la cronología,
  el ejecutivo y el reporte de simulacro.
* **El ejecutivo** titulaba «. QUÉ PASÓ»: `section()` componía `f"{n}. {t}"`
  también con el número vacío.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import text

import auth_utils as au
from takab_api.auth.matrix import roles_with_action
from takab_api.db.engine import get_engine
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.dictamen import rotulos
from takab_api.dictamen.builder import build_model
from takab_api.dictamen.model import ActionRow, DictamenRow
from takab_api.dictamen.pdf import render
from takab_api.drill_report import render as render_simulacro
from tests.api.test_drill_report import _rep
from tests.dictamen.test_pdf import _OPENED, model
from tests.documentos.espia import espia_del_render

_SUB = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"


def _firmado(nombre: str | None) -> list[DictamenRow]:
    return [
        DictamenRow(
            "d-2",
            "inhabit_monitor",
            _OPENED + timedelta(hours=2),
            _SUB,
            "dictamen-v1",
            "d-1",
            firmante_nombre=nombre,
        ),
        DictamenRow("d-1", "inhabit_monitor", _OPENED, None, "dictamen-v1", None),
    ]


def _texto(m, variante: str = "technical"):  # noqa: ANN001, ANN202
    with espia_del_render() as cap:
        render(m, variante)
    return cap


# ─────────────────────────────────────────────────────────────── FIRMÓ (A-145)


def test_el_rol_que_firma_se_DERIVA_de_la_matriz() -> None:
    """Hoy sólo `inspector` tiene `sign_dictamen`. Si lo tuvieran dos roles, el
    papel no podría elegir uno y diría «firmante autorizado»."""
    assert roles_with_action("sign_dictamen") == ("inspector",)
    assert rotulos.rol_que_firma() == rotulos.ROL["inspector"]


def test_FIRMO_lleva_el_ROL_y_el_NOMBRE_y_nunca_el_UUID() -> None:
    cap = _texto(model(dictamens=_firmado("Ing. Laura Méndez"), verdict_signed=True))
    cierre = cap.seccion("FIRMA Y DESLINDE")
    assert "INSPECTOR · Ing. Laura Méndez" in cierre
    assert _SUB not in cap.texto, "el identificador de Cognito sigue en el papel"
    assert _SUB not in cap.membrete


def test_FIRMO_sin_nombre_registrado_lleva_SOLO_el_rol() -> None:
    """Un nombre inventado sería peor que ninguno; el UUID no es un nombre."""
    cap = _texto(model(dictamens=_firmado(None), verdict_signed=True))
    cierre = cap.seccion("FIRMA Y DESLINDE")
    assert "INSPECTOR" in cierre
    assert _SUB not in cap.texto


def test_la_FECHA_DE_FIRMA_va_con_su_hora_local() -> None:
    cap = _texto(model(dictamens=_firmado("Ing. Laura Méndez"), verdict_signed=True))
    assert "2026-08-03 12:00:00 UTC · 06:00:00 hora del centro" in cap.seccion("FIRMA Y DESLINDE")


@pytest.mark.asyncio
async def test_el_builder_trae_el_NOMBRE_de_user_profiles(base_data, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    firmante = str(uuid.uuid4())
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO user_profiles (user_sub, tenant_id, display_name) "
                "VALUES (:u, :t, 'Ing. Laura Méndez')"
            ),
            {"u": firmante, "t": au.DB_TENANT_PRIV},
        )
        await conn.execute(
            text(
                "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by) "
                "VALUES (:t, :i, 'inhabit_monitor', '{}'::jsonb, :u)"
            ),
            {"t": au.DB_TENANT_PRIV, "i": iid, "u": firmante},
        )
    ctx = SessionCtx(tenant_id=au.DB_TENANT_PRIV, role="inspector", user_id=firmante)
    async with get_tenant_conn(ctx) as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))
    assert m is not None
    assert m.dictamens[0].signed_by == firmante
    assert m.dictamens[0].firmante_nombre == "Ing. Laura Méndez"
    # Y el render no deja escapar el `sub` aunque el modelo lo lleve.
    cap = _texto(m)
    assert firmante not in cap.texto
    assert "INSPECTOR · Ing. Laura Méndez" in cap.seccion("FIRMA Y DESLINDE")


@pytest.mark.asyncio
async def test_el_builder_trae_la_ZONA_del_inmueble(base_data, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    async with get_engine().begin() as conn:
        zona = (
            await conn.execute(
                text("SELECT timezone FROM sites WHERE site_id = :s"), {"s": au.DB_SITE_PRIV}
            )
        ).scalar_one()
    ctx = SessionCtx(tenant_id=au.DB_TENANT_PRIV, role="inspector", user_id=str(uuid.uuid4()))
    async with get_tenant_conn(ctx) as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))
    assert m is not None
    assert m.zona_horaria == zona


# ──────────────────────────────────────────────────── la hora local (A-150)


def test_la_PORTADA_lleva_la_hora_local_junto_a_la_UTC() -> None:
    cap = _texto(model(closed_at=_OPENED + timedelta(minutes=30), state="closed"))
    portada = cap.portada()
    assert "2026-08-03 10:00:00 UTC · 04:00:00 hora del centro" in portada
    assert "2026-08-03 10:30:00 UTC · 04:30:00 hora del centro" in portada


def test_la_CRONOLOGIA_lleva_la_hora_local() -> None:
    cap = _texto(model(actions=[ActionRow(_OPENED, "siren_on", "system:edge")]))
    cronologia = cap.seccion("CRONOLOGÍA DEL INCIDENTE")
    assert "2026-08-03 10:00:00 UTC" in cronologia
    assert "04:00:00 hora del centro" in cronologia


def test_una_zona_de_OTRO_huso_se_respeta() -> None:
    """La zona es la del inmueble (`sites.timezone`), no una fija del documento."""
    cap = _texto(model(zona_horaria="America/Tijuana"))
    assert "03:00:00 hora del noroeste" in cap.portada()


def test_el_EJECUTIVO_dice_la_hora_local_en_QUE_PASO() -> None:
    cap = _texto(model(), "executive")
    que_paso = cap.seccion("QUÉ PASÓ")
    assert "10:00 UTC" in que_paso and "04:00 hora del centro" in que_paso


def test_el_SIMULACRO_lleva_la_hora_local() -> None:
    with espia_del_render() as cap:
        render_simulacro(_rep())
    seccion = cap.seccion("EL SIMULACRO")
    assert "2026-09-02 18:00:00 UTC · 12:00:00 hora del centro" in seccion
    assert "2026-09-02 18:05:00 UTC · 12:05:00 hora del centro" in seccion


# ─────────────────────────────────────────── los títulos del ejecutivo (A-140)


def test_el_EJECUTIVO_titula_SIN_el_punto_suelto() -> None:
    lector = PdfReader(io.BytesIO(render(model(), "executive")))
    texto = "\n".join(p.extract_text() or "" for p in lector.pages)
    assert "QUÉ PASÓ" in texto
    assert ". QUÉ" not in texto, "el ejecutivo sigue titulando «. QUÉ PASÓ»"
    for renglon in texto.splitlines():
        assert not renglon.lstrip().startswith(". "), f"título con punto suelto: {renglon!r}"


def test_el_PERICIAL_sigue_numerando() -> None:
    """La otra mitad: quitar el punto sin número no puede quitar el número."""
    cap = _texto(model())
    assert "1. CROQUIS DEL EVENTO" in cap.texto
