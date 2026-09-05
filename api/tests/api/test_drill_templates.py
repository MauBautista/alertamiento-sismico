"""T-5.13 · Plantillas de simulacro: CRUD, copia y lo que NO se puede callar.

Reutiliza el arnés de `test_drills.py` —fleet con gateway comandable, publisher
fake, claves HMAC inline— porque la mitad de esta ficha es que **una plantilla se
lance de verdad**, con sus comandos firmados, y no que el CRUD devuelva 201.

Los cuatro criterios de la ficha, y dónde vive cada uno:

* CRUD con el mismo rol que dispara ⇒ ``test_el_CRUD_va_con_el_permiso_de_disparar``
  y ``test_un_rol_sin_drill_start_no_toca_las_plantillas``.
* La copia no se reescribe ⇒ ``test_editar_la_plantilla_NO_reescribe_el_simulacro_ya_lanzado``.
* Los sitios inservibles se DICEN ⇒ el bloque «lo que no se puede callar».
* Aislamiento entre clientes ⇒ el bloque final.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher
from takab_api.routers.commands import router as commands_router
from takab_api.routers.drill_templates import router as templates_router
from takab_api.routers.drills import router as drills_router
from tests.api.test_commands_router import (  # noqa: F401  (fixtures por nombre)
    KEY,
    THING,
    _FakePublisher,
    gateway,
    publisher,
)


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.include_router(drills_router)
    application.include_router(templates_router)
    application.include_router(commands_router)
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _hmac_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))


def _token(role: str = "tenant_admin", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _crear(client, **over) -> dict:
    cuerpo = {"name": "Macrosimulacro septiembre", "duration_s": 120, "note": "9:00 h"}
    cuerpo.update(over)
    r = await client.post("/drill-templates", json=cuerpo, headers=_token())
    assert r.status_code == 201, r.text
    return r.json()


async def _sql(sql: str, params: dict | None = None) -> list:
    """Ejecuta y devuelve filas si las hay. Un UPDATE devuelve la lista vacía."""
    async with get_engine().begin() as conn:
        res = await conn.execute(text(sql), params or {})
        return res.mappings().all() if res.returns_rows else []


#: Segundo edificio del tenant A. No lo siembra el conftest y hace falta para el
#: caso que de verdad importa: una plantilla PARCIALMENTE degradada.
#:
#: El id lleva el número de la ficha a propósito. `…0000a2` —el siguiente
#: «obvio»— YA lo usan `test_console_scope` y `test_mobile_core` para sus propios
#: segundos sitios, y ninguno lo borra: en la suite completa la inserción moría
#: con `UniqueViolation` aunque el módulo pasara en aislado.
SITIO_B = "7a000000-0000-0000-0000-00000000513b"


@pytest.fixture
async def dos_sitios(gateway) -> str:
    """Añade un segundo sitio comandable y lo RETIRA del todo al terminar.

    Se borra en orden de FK y no se deja puesto: `sites` no entra en ningún
    `TRUNCATE` por test, así que un edificio olvidado aquí cambiaría el conjunto
    «todos los comandables» de cualquier test posterior de la sesión.
    """
    await _sql(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(CAST(:s AS uuid), CAST(:t AS uuid), 'T513B', 'Torre B', "
        "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography)",
        {"s": SITIO_B, "t": au.DB_TENANT_PRIV},
    )
    await _sql(
        "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) VALUES "
        "(gen_random_uuid(), CAST(:t AS uuid), CAST(:s AS uuid), 'SER-B2', 'thing-b2')",
        {"t": au.DB_TENANT_PRIV, "s": SITIO_B},
    )
    yield SITIO_B
    for tabla in ("drill_template_sites", "drill_sites", "commands", "gateways", "sites"):
        await _sql(f"DELETE FROM {tabla} WHERE site_id = CAST(:s AS uuid)", {"s": SITIO_B})


@pytest.fixture(autouse=True)
async def _limpiar_plantillas(base_data):
    """El `TRUNCATE` del conftest es POR SESIÓN, no por test.

    Da igual en `drills`, que no tiene ninguna restricción de unicidad; aquí no:
    el nombre es único por tenant, así que sin esto el segundo test que crea
    «Macrosimulacro septiembre» choca con la fila del primero y el rojo culpa a
    la restricción en vez de al arrastre.
    """
    yield
    async with get_engine().begin() as conn:
        await conn.execute(text("DELETE FROM drill_template_sites"))
        await conn.execute(text("UPDATE drills SET from_template_id = NULL"))
        await conn.execute(text("DELETE FROM drill_templates"))
        # Y se devuelve el inventario a su sitio. Varios tests de aquí RETIRAN un
        # gabinete o un edificio a propósito —es lo que esta ficha tiene que
        # declarar— y esas filas sobreviven al test: sin restaurarlas, el
        # siguiente caso mide el destrozo del anterior. Medido: siete rojos
        # «sitio sin gateway comandable» que no tenían nada que ver con su test.
        await conn.execute(text("UPDATE gateways SET status = 'provisioned'"))
        await conn.execute(text("UPDATE sites SET status = 'active'"))


# ---- CRUD, con el permiso que ya existía --------------------------------------


async def test_el_CRUD_va_con_el_permiso_de_disparar(client, gateway) -> None:
    """Criterio 1. Sin rol nuevo: quien puede lanzar puede definir cómo se lanza."""
    creada = await _crear(client, site_ids=[au.DB_SITE_PRIV])
    assert creada["name"] == "Macrosimulacro septiembre"
    assert creada["duration_s"] == 120
    assert [s["site_id"] for s in creada["sites"]] == [au.DB_SITE_PRIV]
    assert creada["todos_los_sitios"] is False

    leida = await client.get(f"/drill-templates/{creada['template_id']}", headers=_token())
    assert leida.status_code == 200 and leida.json()["template_id"] == creada["template_id"]

    listada = await client.get("/drill-templates", headers=_token())
    assert [t["template_id"] for t in listada.json()["items"]] == [creada["template_id"]]

    editada = await client.put(
        f"/drill-templates/{creada['template_id']}",
        json={"name": "Macrosimulacro septiembre", "duration_s": 600, "site_ids": []},
        headers=_token(),
    )
    assert editada.status_code == 200
    assert editada.json()["duration_s"] == 600
    # Editar REEMPLAZA el conjunto: quitar un sitio tiene que quitarlo de verdad.
    assert editada.json()["sites"] == [] and editada.json()["todos_los_sitios"] is True

    borrada = await client.delete(f"/drill-templates/{creada['template_id']}", headers=_token())
    assert borrada.status_code == 204
    assert (await client.get("/drill-templates", headers=_token())).json()["items"] == []


async def test_un_rol_sin_drill_start_no_toca_las_plantillas(client) -> None:
    """`gov_operator` LEE el registro de simulacros; esto es configuración, no evidencia."""
    for metodo, ruta in [
        ("get", "/drill-templates"),
        ("post", "/drill-templates"),
    ]:
        r = await getattr(client, metodo)(
            ruta,
            headers=_token(role="gov_operator"),
            **({"json": {"name": "x"}} if metodo == "post" else {}),
        )
        assert r.status_code == 403, f"{metodo} {ruta} → {r.status_code}"


async def test_borrar_ARCHIVA_y_libera_el_nombre(client, gateway) -> None:
    """Se archiva porque cada simulacro que salió de ella la cita como procedencia.

    Desde fuera se comporta como un borrado, y eso incluye lo que nadie recuerda
    hasta que muerde: **el nombre vuelve a estar libre**.
    """
    primera = await _crear(client)
    await client.delete(f"/drill-templates/{primera['template_id']}", headers=_token())

    segunda = await _crear(client)  # mismo nombre
    assert segunda["template_id"] != primera["template_id"]

    # Y la fila sigue ahí, con su marca: la procedencia no se quedó huérfana.
    filas = await _sql(
        "SELECT archived_at FROM drill_templates WHERE template_id = CAST(:t AS uuid)",
        {"t": primera["template_id"]},
    )
    assert filas[0]["archived_at"] is not None


async def test_dos_plantillas_vivas_no_pueden_llamarse_igual(client) -> None:
    """«Macrosimulacro septiembre» tiene que significar UNA cosa dentro del cliente."""
    await _crear(client)
    r = await client.post(
        "/drill-templates",
        json={"name": "  macrosimulacro SEPTIEMBRE  ", "duration_s": 60},
        headers=_token(),
    )
    assert r.status_code == 409, r.text


async def test_una_plantilla_archivada_es_inexistente(client) -> None:
    creada = await _crear(client)
    await client.delete(f"/drill-templates/{creada['template_id']}", headers=_token())
    for metodo in ("get", "delete"):
        r = await getattr(client, metodo)(
            f"/drill-templates/{creada['template_id']}", headers=_token()
        )
        assert r.status_code == 404


async def test_guardar_contra_un_sitio_inalcanzable_se_RECHAZA(client, gateway) -> None:
    """Al GUARDAR sí se rechaza: sería crear la trampa de golpe.

    Al USARLA no —se declara—, porque el inventario cambia entre una cosa y otra.
    Es la asimetría deliberada de esta ficha.

    El gabinete se retira DENTRO del test en vez de omitir la fixture: la fila de
    `gateways` sobrevive a los tests anteriores de la sesión, así que un caso que
    dependiera de su ausencia mediría el orden de ejecución, no la regla.
    """
    await _sql("UPDATE gateways SET status = 'retired'")
    r = await client.post(
        "/drill-templates",
        json={"name": "Sin gabinete", "site_ids": [au.DB_SITE_PRIV], "duration_s": 60},
        headers=_token(),
    )
    assert r.status_code == 404, r.text

    # Y un sitio que directamente no existe tampoco se guarda.
    r2 = await client.post(
        "/drill-templates",
        json={
            "name": "Fantasma",
            "site_ids": ["00000000-0000-4000-8000-0000000000ff"],
            "duration_s": 60,
        },
        headers=_token(),
    )
    assert r2.status_code == 404, r2.text


# ---- lanzar desde la plantilla: COPIA, no referencia --------------------------


async def test_lanzar_desde_la_plantilla_copia_sus_valores(client, gateway, publisher) -> None:
    """Criterio 2, primera mitad: dos clics y el simulacro sale con lo definido."""
    plantilla = await _crear(client, site_ids=[au.DB_SITE_PRIV], duration_s=120, note="9:00 h")

    r = await client.post(
        "/drills", json={"from_template": plantilla["template_id"]}, headers=_token()
    )
    assert r.status_code == 201, r.text
    drill = r.json()
    assert drill["duration_s"] == 120 and drill["note"] == "9:00 h"
    assert [s["site_id"] for s in drill["sites"]] == [au.DB_SITE_PRIV]
    assert drill["from_template_id"] == plantilla["template_id"]
    # Y salió DE VERDAD: comando firmado con la duración de la plantilla dentro.
    assert publisher.published[0][1]["payload"]["duration_s"] == 120


async def test_editar_la_plantilla_NO_reescribe_el_simulacro_ya_lanzado(
    client, gateway, publisher
) -> None:
    """Criterio 2, segunda mitad — y el corazón de la ficha.

    Un simulacro es evidencia de cumplimiento: si editar la plantilla cambiara lo
    que dice el registro de septiembre, la evidencia sería reescribible y no
    valdría nada. Por eso `from_template_id` es PROCEDENCIA y no dependencia, y
    nada del camino de lectura la desreferencia.
    """
    plantilla = await _crear(client, site_ids=[au.DB_SITE_PRIV], duration_s=120, note="9:00 h")
    drill = (
        await client.post(
            "/drills", json={"from_template": plantilla["template_id"]}, headers=_token()
        )
    ).json()

    await client.put(
        f"/drill-templates/{plantilla['template_id']}",
        json={"name": "OTRO NOMBRE", "duration_s": 1800, "note": "cambiada", "site_ids": []},
        headers=_token(),
    )

    releido = (await client.get("/drills", headers=_token())).json()["items"]
    ya_lanzado = next(d for d in releido if d["drill_id"] == drill["drill_id"])
    assert ya_lanzado["duration_s"] == 120, "la edición reescribió la duración del simulacro"
    assert ya_lanzado["note"] == "9:00 h", "la edición reescribió la nota del simulacro"
    assert [s["site_id"] for s in ya_lanzado["sites"]] == [au.DB_SITE_PRIV]


async def test_lo_explicito_gana_sobre_lo_heredado(client, gateway, publisher) -> None:
    plantilla = await _crear(client, site_ids=[au.DB_SITE_PRIV], duration_s=120, note="9:00 h")
    drill = (
        await client.post(
            "/drills",
            json={"from_template": plantilla["template_id"], "duration_s": 60, "note": None},
            headers=_token(),
        )
    ).json()
    assert drill["duration_s"] == 60
    # `note: null` explícito BORRA la heredada. Tratarlo como «no dijo nada»
    # devolvería un texto que el operador acaba de quitar al banner del gabinete.
    assert drill["note"] is None


async def test_se_puede_ARMAR_la_agenda_desde_la_plantilla(client, gateway, publisher) -> None:
    """Media ficha: se define en septiembre y se ejecuta el día 19 con un clic."""
    plantilla = await _crear(client, site_ids=[au.DB_SITE_PRIV], duration_s=120, note="9:00 h")
    r = await client.post(
        "/drills",
        json={"from_template": plantilla["template_id"], "scheduled_at": "2030-09-19T14:00:00Z"},
        headers=_token(),
    )
    assert r.status_code == 201, r.text
    agenda = r.json()
    assert agenda["active"] is False and agenda["scheduled_at"] is not None
    assert agenda["duration_s"] == 120 and agenda["note"] == "9:00 h"
    assert agenda["from_template_id"] == plantilla["template_id"]
    assert publisher.published == [], "una agenda NO emite comandos"


async def test_plantilla_y_agenda_armada_son_excluyentes(client, gateway) -> None:
    """Dos orígenes para el mismo campo acabarían discrepando."""
    plantilla = await _crear(client, duration_s=120)
    r = await client.post(
        "/drills",
        json={
            "from_template": plantilla["template_id"],
            "from_scheduled": "00000000-0000-4000-8000-0000000000ff",
        },
        headers=_token(),
    )
    assert r.status_code == 422


async def test_una_plantilla_inexistente_es_404(client, gateway) -> None:
    r = await client.post(
        "/drills",
        json={"from_template": "00000000-0000-4000-8000-0000000000ff"},
        headers=_token(),
    )
    assert r.status_code == 404


# ---- lo que NO se puede callar (criterio 3) -----------------------------------


async def test_un_sitio_RETIRADO_de_la_plantilla_se_declara(client, gateway) -> None:
    """Criterio 3, al leerla: quien la elige está mirando la lista."""
    await _crear(client, site_ids=[au.DB_SITE_PRIV])
    await _sql(
        "UPDATE sites SET status = 'retired' WHERE site_id = CAST(:s AS uuid)",
        {"s": au.DB_SITE_PRIV},
    )

    item = (await client.get("/drill-templates", headers=_token())).json()["items"][0]
    assert item["sitios_no_usables"] == 1
    assert item["sites"][0]["estado"] == "retirado"
    assert item["sites"][0]["motivo"] == "el sitio está dado de baja"


async def test_un_sitio_SIN_GABINETE_no_se_confunde_con_uno_retirado(client, gateway) -> None:
    """Los motivos van separados: uno es de inventario y otro de campo, y quien
    lee el número llama a personas distintas."""
    plantilla = await _crear(client, site_ids=[au.DB_SITE_PRIV])
    await _sql("UPDATE gateways SET status = 'retired'")

    item = (
        await client.get(f"/drill-templates/{plantilla['template_id']}", headers=_token())
    ).json()
    assert item["sites"][0]["estado"] == "sin_gabinete"
    assert item["sites"][0]["motivo"] == "el sitio no tiene gabinete comandable"


async def test_lanzarla_PARCIALMENTE_degradada_no_encoge_el_conjunto_en_silencio(
    client, dos_sitios, publisher
) -> None:
    """**El criterio 3 en su forma más importante.**

    No se bloquea: un edificio que perdió el enlace no puede dejar sin simulacro a
    los otros —misma decisión que ya tomó `T-2.48` para las agendas—. Lo que no
    puede pasar es que desaparezca sin más: queda en el registro, sin comando y
    rotulado `commandable=False`, que es lo que distingue «no había a quién
    mandarle» de «no acusó».
    """
    otro = dos_sitios
    plantilla = await _crear(client, site_ids=[au.DB_SITE_PRIV, otro])

    # El segundo edificio pierde el enlace DESPUÉS de definirse la plantilla.
    await _sql(
        "UPDATE gateways SET status = 'retired' WHERE site_id = CAST(:s AS uuid)", {"s": otro}
    )

    r = await client.post(
        "/drills", json={"from_template": plantilla["template_id"]}, headers=_token()
    )
    assert r.status_code == 201, r.text
    drill = r.json()
    por_sitio = {s["site_id"]: s for s in drill["sites"]}
    assert set(por_sitio) == {au.DB_SITE_PRIV, otro}, "un sitio desapareció del registro"
    assert por_sitio[au.DB_SITE_PRIV]["commandable"] is True
    assert por_sitio[otro]["commandable"] is False
    assert por_sitio[otro]["command_id"] is None
    # Y sonó donde sí se podía: el otro edificio no se quedó sin simulacro.
    assert len(publisher.published) == 1

    # Queda en la bitácora con su conteo, no solo en la respuesta.
    aud = await _sql(
        "SELECT meta FROM audit_log WHERE verb = 'drill_started' ORDER BY ts DESC LIMIT 1"
    )
    assert aud[0]["meta"]["unreachable"] == 1
    assert aud[0]["meta"]["from_template"] == plantilla["template_id"]


async def test_si_NINGUNO_es_alcanzable_se_rechaza_diciendo_POR_QUE(
    client, gateway, publisher
) -> None:
    """Distinto del caso parcial, y no por capricho: un simulacro que no suena en
    ninguna parte no es un simulacro, es un registro falso de que se hizo uno.

    Lo que importa es el MENSAJE. El 409 que había culpaba al inventario del
    tenant («no tiene sitios con gateway comandable»), y con una plantilla eso
    puede ser mentira: el cliente puede tener veinte comandables y ninguno estar
    en la lista. Mandaría a arreglar lo que no está roto.
    """
    plantilla = await _crear(client, site_ids=[au.DB_SITE_PRIV])
    await _sql("UPDATE gateways SET status = 'retired'")

    r = await client.post(
        "/drills", json={"from_template": plantilla["template_id"]}, headers=_token()
    )
    assert r.status_code == 409, r.text
    assert "de la lista" in r.json()["detail"]
    assert "el tenant no tiene" not in r.json()["detail"]
    assert publisher.published == []


async def test_una_plantilla_SIN_sitios_apunta_a_todos_los_comandables(
    client, gateway, publisher
) -> None:
    """Vacío = «todos», la misma convención que `site_ids = None` y que el modal."""
    plantilla = await _crear(client, site_ids=[])
    assert plantilla["todos_los_sitios"] is True and plantilla["sitios_no_usables"] == 0

    drill = (
        await client.post(
            "/drills", json={"from_template": plantilla["template_id"]}, headers=_token()
        )
    ).json()
    # El conjunto esperado se DERIVA de la base, no se teclea: cualquier test que
    # deje un edificio de más cambiaría el número y el rojo culparía a la ficha.
    esperado = {
        str(r["site_id"])
        for r in await _sql(
            "SELECT s.site_id FROM sites s WHERE s.tenant_id = CAST(:t AS uuid) "
            "AND s.status <> 'retired' AND EXISTS (SELECT 1 FROM gateways g "
            " WHERE g.site_id = s.site_id AND g.status <> 'retired' "
            "   AND g.iot_thing IS NOT NULL)",
            {"t": au.DB_TENANT_PRIV},
        )
    }
    assert esperado, "sin sitios comandables el caso no prueba nada"
    assert {s["site_id"] for s in drill["sites"]} == esperado


# ---- aislamiento entre clientes (criterio 4 · regla de oro 5) -----------------


async def test_otro_tenant_no_ve_la_plantilla_ni_la_puede_usar(client, gateway) -> None:
    plantilla = await _crear(client, site_ids=[au.DB_SITE_PRIV])

    ajeno = _token(tenant=au.DB_TENANT_PRIV2)
    assert (await client.get("/drill-templates", headers=ajeno)).json()["items"] == []
    # 404 y no 403: un 403 confirmaría que la plantilla del otro cliente existe.
    assert (
        await client.get(f"/drill-templates/{plantilla['template_id']}", headers=ajeno)
    ).status_code == 404
    assert (
        await client.put(
            f"/drill-templates/{plantilla['template_id']}",
            json={"name": "secuestrada", "duration_s": 60},
            headers=ajeno,
        )
    ).status_code == 404
    assert (
        await client.delete(f"/drill-templates/{plantilla['template_id']}", headers=ajeno)
    ).status_code == 404
    assert (
        await client.post(
            "/drills", json={"from_template": plantilla["template_id"]}, headers=ajeno
        )
    ).status_code == 404


async def test_dos_clientes_pueden_llamar_igual_a_su_plantilla(client, gateway) -> None:
    """El nombre identifica DENTRO de un cliente: el índice único es por tenant."""
    await _crear(client)
    r = await client.post(
        "/drill-templates",
        json={"name": "Macrosimulacro septiembre", "duration_s": 60},
        headers=_token(tenant=au.DB_TENANT_PRIV2),
    )
    assert r.status_code == 201, r.text
