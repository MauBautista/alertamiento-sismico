"""Carga y lectura de ``compliance_labels`` por tenant (T-2.82).

Quién escribe: SOLO ``takab_superadmin`` (acción ``manage_tenants``). La tabla llega
del DDL con ``cl_admin`` = escritura para cualquier identidad interna TAKAB — el
comentario del schema lo dice: *"escritura interna hasta ratificar el marco citable —
GATE-LEGAL"*. La API estrecha esa puerta a la mitad, igual que ``routers/dictamens``
estrecha ``dictamens_admin``: cargar una afirmación normativa en la ficha de un
cliente es administrar esa ficha, y eso ya es del dueño de la plataforma.

Quién lee: quien vea al cliente (la RLS decide). Un cliente que no existe *para ti*
devuelve 404, nunca un documento vacío: "no tienes permiso" y "no declaró nada" son
hechos distintos y confundirlos es lo que veta la regla de oro 7.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.compliance import (
    CATALOG,
    DECLARED_NOTICE,
    DOCUMENT_VERSION,
    NO_CLAIMS,
    PROVENANCE,
    UNREADABLE_LEGACY,
)
from takab_api.db.engine import get_engine
from takab_api.routers.compliance import router as compliance_router

PATH = "/tenants/{tid}/compliance-labels"

MARCO = {
    "key": "regulatory_framework",
    "claim": "Reglamento de Construcciones del Distrito Federal, Título Sexto",
    "reference": "Gaceta Oficial del DF, 29/01/2004, art. 139",
}
PROTOCOLO = {
    "key": "internal_protocol",
    "claim": "Plan interno de protección civil del inmueble, revisión 2026",
    "reference": "Acta del comité de seguridad, 14/03/2026",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        monkeypatch.setenv("TAKAB_API_DATABASE_URL", dsn)
    deps._reset_caches()
    get_engine.cache_clear()
    yield
    deps._reset_caches()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(compliance_router)
    return app


async def _get(token: str, tenant_id: str):
    async with au.client_for(_app()) as c:
        return await c.get(PATH.format(tid=tenant_id), headers=au.bearer(token))


async def _put(token: str, tenant_id: str, body: dict):
    async with au.client_for(_app()) as c:
        return await c.put(PATH.format(tid=tenant_id), headers=au.bearer(token), json=body)


def _root(tenant: str = au.DB_TENANT_PRIV) -> str:
    return au.make_token("takab_superadmin", tenant=tenant)


async def _stored(tenant_id: str) -> dict | None:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                text("SELECT labels FROM compliance_labels WHERE tenant_id = CAST(:t AS uuid)"),
                {"t": tenant_id},
            )
        ).first()
    return dict(row.labels) if row else None


async def _write_raw(tenant_id: str, labels: dict) -> None:
    """Escribe la fila a mano, como haría un interno con psql (``cl_admin``)."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO compliance_labels (tenant_id, labels) "
                "VALUES (CAST(:t AS uuid), CAST(:l AS jsonb)) "
                "ON CONFLICT (tenant_id) DO UPDATE SET labels = EXCLUDED.labels"
            ),
            {"t": tenant_id, "l": json.dumps(labels)},
        )


async def _audit(tenant_id: str) -> list[dict]:
    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT verb, object, meta FROM audit_log "
                    "WHERE tenant_id = CAST(:t AS uuid) ORDER BY ts"
                ),
                {"t": tenant_id},
            )
        ).all()
    return [{"verb": r.verb, "object": r.object, "meta": r.meta} for r in rows]


# --- Lectura ------------------------------------------------------------------


async def test_sin_fila_el_cliente_sale_vacio_pero_ENMARCADO(base_data: None) -> None:
    """El estado de hoy: la tabla existe y nadie la carga. Vacío tiene que decirse.

    Y el aviso viaja EN EL PAYLOAD, no en el cliente: una pantalla futura no puede
    "olvidarse" de pintarlo, porque no es suya.
    """
    resp = await _get(_root(), au.DB_TENANT_PRIV)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["unreadable"] is None
    assert body["provenance"] == PROVENANCE
    assert body["notice"] == DECLARED_NOTICE
    assert body["updated_at"] is None
    # Y lo que la pantalla debe IMPRIMIR sale de la misma función que el PDF: vacío
    # no es un hueco, es una frase que dice que la ausencia no es conformidad.
    assert body["notes"] == [NO_CLAIMS]


async def test_lo_que_se_imprime_lo_decide_el_SERVIDOR_en_los_tres_estados(
    base_data: None,
) -> None:
    """Las palabras salen de ``compliance_block`` — la misma que usa el dictamen PDF.
    Si la consola compusiera las suyas, el papel y la pantalla acabarían diciendo
    cosas distintas del mismo cliente."""
    assert (await _get(_root(), au.DB_TENANT_PRIV)).json()["notes"] == [NO_CLAIMS]

    await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO]})
    assert (await _get(_root(), au.DB_TENANT_PRIV)).json()["notes"] == [DECLARED_NOTICE]

    await _write_raw(au.DB_TENANT_PRIV, {"norma": "Cumplimos la NOM-003-SCT"})
    assert (await _get(_root(), au.DB_TENANT_PRIV)).json()["notes"] == [UNREADABLE_LEGACY]


@pytest.mark.parametrize("role", ["tenant_admin", "soc_operator", "inspector", "takab_support"])
async def test_cualquier_rol_lee_las_de_su_propio_cliente(base_data: None, role: str) -> None:
    """Se sirven a la app móvil de todo ocupante: no son un secreto. Lo que importa
    es de QUIÉN se leen, y eso lo decide la RLS."""
    await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO]})
    resp = await _get(au.make_token(role, tenant=au.DB_TENANT_PRIV), au.DB_TENANT_PRIV)
    assert resp.status_code == 200, resp.text
    assert [i["claim"] for i in resp.json()["items"]] == [MARCO["claim"]]


async def test_pedir_las_de_otro_cliente_es_404_y_NO_un_documento_vacio(
    base_data: None,
) -> None:
    """La trampa que evita este 404: si devolviéramos ``items: []``, la consola de un
    cliente pintaría a OTRO cliente como "sin marco declarado" — una afirmación sobre
    un tercero, fabricada por una fuga de permisos."""
    await _put(_root(), au.DB_TENANT_PRIV2, {"items": [MARCO]})
    resp = await _get(au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV), au.DB_TENANT_PRIV2)
    assert resp.status_code == 404


async def test_un_cliente_inexistente_es_404(base_data: None) -> None:
    resp = await _get(_root(), "00000000-0000-0000-0000-0000000000ff")
    assert resp.status_code == 404


async def test_sin_token_es_401(base_data: None) -> None:
    async with au.client_for(_app()) as c:
        resp = await c.get(PATH.format(tid=au.DB_TENANT_PRIV))
    assert resp.status_code == 401


async def test_cada_afirmacion_sale_con_el_titulo_de_su_clase(base_data: None) -> None:
    """El título lo pone el catálogo del servidor, no el cliente: es lo que convierte
    un string suelto en "el cliente declara, de esta clase, esto"."""
    await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO, PROTOCOLO]})
    body = (await _get(_root(), au.DB_TENANT_PRIV)).json()
    assert [(i["key"], i["title"], i["claim"], i["reference"]) for i in body["items"]] == [
        (MARCO["key"], CATALOG[MARCO["key"]], MARCO["claim"], MARCO["reference"]),
        (PROTOCOLO["key"], CATALOG[PROTOCOLO["key"]], PROTOCOLO["claim"], PROTOCOLO["reference"]),
    ]


async def test_una_fila_escrita_a_mano_en_el_formato_viejo_se_declara_ilegible(
    base_data: None,
) -> None:
    """``cl_admin`` deja escribir por psql. Lo que la API no entiende se rotula: ni se
    transcribe (afirmaría sin respaldo) ni desaparece (mentiría por omisión)."""
    await _write_raw(au.DB_TENANT_PRIV, {"norma": "Cumplimos la NOM-003-SCT"})
    body = (await _get(_root(), au.DB_TENANT_PRIV)).json()
    assert body["items"] == []
    assert body["unreadable"] == UNREADABLE_LEGACY


# --- Escritura ----------------------------------------------------------------


async def test_el_superadmin_carga_las_etiquetas(base_data: None) -> None:
    resp = await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO]})
    assert resp.status_code == 200, resp.text
    assert [i["claim"] for i in resp.json()["items"]] == [MARCO["claim"]]
    assert await _stored(au.DB_TENANT_PRIV) == {
        "version": DOCUMENT_VERSION,
        "items": [MARCO],
    }


@pytest.mark.parametrize(
    "role", ["takab_support", "tenant_admin", "soc_operator", "inspector", "gov_operator"]
)
async def test_nadie_mas_carga_etiquetas(base_data: None, role: str) -> None:
    """``takab_support`` incluido, y a propósito: la DB se lo permitiría
    (``cl_admin`` = cualquier interno), la API no. Soporte lee la plataforma; no
    redacta la afirmación normativa que acabará en un dictamen firmado."""
    resp = await _put(
        au.make_token(role, tenant=au.DB_TENANT_PRIV), au.DB_TENANT_PRIV, {"items": []}
    )
    assert resp.status_code == 403
    assert await _stored(au.DB_TENANT_PRIV) is None


async def test_la_carga_deja_el_TEXTO_COMPLETO_en_la_bitacora(base_data: None) -> None:
    """La bitácora no se poda nunca (regla de oro 11). Guardar solo "cambió" dejaría
    imposible saber QUÉ decía la etiqueta el día que se firmó un dictamen."""
    await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO]})
    filas = await _audit(au.DB_TENANT_PRIV)
    assert [f["verb"] for f in filas] == ["compliance_labels_update"]
    meta = filas[0]["meta"]
    assert filas[0]["object"] == f"tenant:{au.DB_TENANT_PRIV}"
    assert meta["provenance"] == PROVENANCE
    assert meta["items"] == [MARCO]
    assert meta["replaced"] == 0


async def test_la_bitacora_se_escribe_en_el_cliente_TOCADO_no_en_el_del_operador(
    base_data: None,
) -> None:
    """``cl_admin`` no filtra por tenant: un superadmin escribe en cualquier cliente.
    Si la fila de auditoría fuera al tenant de SUS claims, el cliente afectado no
    tendría rastro de que alguien le puso una afirmación normativa en la ficha."""
    await _put(_root(tenant=au.DB_TENANT_PRIV), au.DB_TENANT_PRIV2, {"items": [PROTOCOLO]})
    assert [f["verb"] for f in await _audit(au.DB_TENANT_PRIV2)] == ["compliance_labels_update"]
    assert await _audit(au.DB_TENANT_PRIV) == []


async def test_guardar_REEMPLAZA_el_documento_entero(base_data: None) -> None:
    await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO, PROTOCOLO]})
    resp = await _put(_root(), au.DB_TENANT_PRIV, {"items": [PROTOCOLO]})
    assert resp.status_code == 200, resp.text
    assert [i["key"] for i in resp.json()["items"]] == [PROTOCOLO["key"]]
    assert (await _stored(au.DB_TENANT_PRIV))["items"] == [PROTOCOLO]
    assert (await _audit(au.DB_TENANT_PRIV))[-1]["meta"]["replaced"] == 2


async def test_vaciar_las_etiquetas_es_legitimo_y_queda_escrito(base_data: None) -> None:
    await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO]})
    resp = await _put(_root(), au.DB_TENANT_PRIV, {"items": []})
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []
    assert [f["meta"]["items"] for f in await _audit(au.DB_TENANT_PRIV)] == [[MARCO], []]


async def test_cargar_en_un_cliente_inexistente_es_404(base_data: None) -> None:
    resp = await _put(_root(), "00000000-0000-0000-0000-0000000000ff", {"items": [MARCO]})
    assert resp.status_code == 404


# --- Lo que NO se puede afirmar ----------------------------------------------


@pytest.mark.parametrize(
    ("caso", "item"),
    [
        ("clave inventada", {**MARCO, "key": "nom_003_sct"}),
        ("clave vacía", {**MARCO, "key": ""}),
        ("afirmación en blanco", {**MARCO, "claim": "   "}),
        ("referencia en blanco", {**MARCO, "reference": ""}),
        ("afirmación kilométrica", {**MARCO, "claim": "x" * 281}),
        ("referencia kilométrica", {**MARCO, "reference": "x" * 281}),
    ],
)
async def test_una_afirmacion_insostenible_se_rechaza(
    base_data: None, caso: str, item: dict
) -> None:
    resp = await _put(_root(), au.DB_TENANT_PRIV, {"items": [item]})
    assert resp.status_code == 422, f"{caso}: {resp.status_code}"
    assert await _stored(au.DB_TENANT_PRIV) is None


async def test_sin_referencia_no_hay_etiqueta(base_data: None) -> None:
    """ "Dónde lo dice" es obligatorio. No hace verdadera la afirmación: la hace
    SEGUIBLE, que es justo lo que faltó el día de la cita a NOM-003-SCT."""
    sin_ref = {"key": MARCO["key"], "claim": MARCO["claim"]}
    resp = await _put(_root(), au.DB_TENANT_PRIV, {"items": [sin_ref]})
    assert resp.status_code == 422
    assert await _stored(au.DB_TENANT_PRIV) is None


@pytest.mark.parametrize(
    "extra",
    [{"verified": True}, {"provenance": "verified_by_takab"}, {"certified_by": "TAKAB"}],
)
async def test_no_se_puede_colar_una_marca_de_verificacion(base_data: None, extra: dict) -> None:
    resp = await _put(_root(), au.DB_TENANT_PRIV, {"items": [{**MARCO, **extra}]})
    assert resp.status_code == 422
    assert await _stored(au.DB_TENANT_PRIV) is None


async def test_dos_afirmaciones_de_la_misma_clase_se_rechazan(base_data: None) -> None:
    resp = await _put(
        _root(), au.DB_TENANT_PRIV, {"items": [MARCO, {**MARCO, "claim": "otra cosa"}]}
    )
    assert resp.status_code == 422


async def test_un_cuerpo_con_campos_desconocidos_se_rechaza(base_data: None) -> None:
    resp = await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO], "verified_by": "TAKAB"})
    assert resp.status_code == 422


# --- Concurrencia -------------------------------------------------------------


async def test_guardar_sobre_una_version_vieja_es_409_y_no_pisa_nada(base_data: None) -> None:
    """Un PUT reemplaza el documento ENTERO: sin testigo, el segundo editor borra las
    etiquetas del primero sin enterarse — y aquí lo que se borra es una afirmación
    normativa que quizá ya viajó dentro de un dictamen firmado."""
    await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO]})
    viejo = (await _get(_root(), au.DB_TENANT_PRIV)).json()["updated_at"]
    assert (await _put(_root(), au.DB_TENANT_PRIV, {"items": [PROTOCOLO]})).status_code == 200

    resp = await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO], "base_updated_at": viejo})
    assert resp.status_code == 409
    assert (await _stored(au.DB_TENANT_PRIV))["items"] == [PROTOCOLO]


async def test_guardar_con_el_testigo_al_dia_pasa(base_data: None) -> None:
    await _put(_root(), au.DB_TENANT_PRIV, {"items": [MARCO]})
    actual = (await _get(_root(), au.DB_TENANT_PRIV)).json()["updated_at"]
    resp = await _put(_root(), au.DB_TENANT_PRIV, {"items": [PROTOCOLO], "base_updated_at": actual})
    assert resp.status_code == 200, resp.text


async def test_estrenar_la_fila_creyendo_que_ya_existia_es_409(base_data: None) -> None:
    resp = await _put(
        _root(),
        au.DB_TENANT_PRIV,
        {"items": [MARCO], "base_updated_at": "2026-01-01T00:00:00Z"},
    )
    assert resp.status_code == 409
    assert await _stored(au.DB_TENANT_PRIV) is None
