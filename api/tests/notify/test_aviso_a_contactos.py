"""[T-9.80 · D-48] Quien pide ayuda avisa a SUS contactos de emergencia, por correo.

El check-in PROPIO ``need_help`` de alguien con contactos deja la acción
``need_help_contacts`` (lo prueba ``tests/api/test_contactos_emergencia.py``). Aquí se
mide lo que hace el orquestador con ella:

* UN job ``email`` anclado a la acción, con ``to`` = los correos de los contactos del
  titular, leídos como ``takab_ingest`` en el momento de encolar;
* el mensaje dice QUIÉN pidió ayuda (su nombre de ``user_profiles``, o «Una persona»),
  en qué inmueble y en qué zona, y la ubicación SÓLO si ese check-in la trajo;
* **sin enlace a la consola**: el contacto no es usuario de TAKAB y un enlace que no
  puede abrir sólo le haría creer que hay algo más que ver;
* sin contactos no se encola nada, y se DICE en el log.

El nombre, la zona y el punto NO viajan en la acción (append-only: ARCO no podría
borrarlos después). Se resuelven al DESPACHAR, de la fila viva del check-in.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator

import pytest

from takab_api.notify.orchestrator import MENSAJE_POR_KIND, _message, run_notify_pass
from takab_api.notify.providers import cuerpo_email
from takab_api.settings import Settings
from tests.notify.test_escalada_avisa_a_todos import BASE, _Escena
from tests.notify.test_orchestrator import _providers, _Scenario, scenario  # noqa: F401

TITULAR = "Ernestina Aviso Coyoacan"
CORREOS = ["primo.aviso@example.mx", "hermana.aviso@example.mx"]


@pytest.fixture
def esc(scenario: _Scenario) -> Iterator[_Escena]:  # noqa: F811
    e = _Escena(scenario)
    scenario.seed_config()
    try:
        yield e
    finally:
        # Lo que la limpieza del escenario no conoce: sin esto el siguiente test
        # heredaría contactos, perfiles y check-ins de un tenant ya borrado.
        conn = scenario.conn
        conn.rollback()
        conn.execute("RESET ROLE")
        conn.execute("SET session_replication_role = 'replica'")
        for tabla in ("emergency_contacts", "life_checkins", "user_profiles", "zones"):
            for tenant in scenario.tenants:
                conn.execute(f"DELETE FROM {tabla} WHERE tenant_id = %s", (tenant,))
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()
        conn.execute("SET ROLE takab_ingest")
        conn.commit()


def _como_superusuario(e: _Escena, sql: str, params: tuple) -> dict | None:
    """Siembra lo que en producción escribe la API (``takab_app``), no el worker."""
    e.conn.execute("RESET ROLE")
    fila = e.conn.execute(sql, params)
    fuera = fila.fetchone() if fila.description else None
    e.conn.commit()
    e.conn.execute("SET ROLE takab_ingest")
    e.conn.commit()
    return fuera


def _pide_ayuda(
    e: _Escena,
    *,
    con_ubicacion: bool = True,
    contactos: list[str] | None = None,
    perfil: bool = True,
) -> tuple[str, str]:
    """Un titular con perfil, contactos y un check-in ``need_help`` → la acción."""
    incidente = e.sc.seed_incident(trigger="sasmex", severity="critical")
    sitio = str(
        e.conn.execute(
            "SELECT site_id FROM incidents WHERE incident_id = %s", (incidente,)
        ).fetchone()["site_id"]
    )
    titular, zona = str(uuid.uuid4()), str(uuid.uuid4())
    _como_superusuario(
        e,
        "INSERT INTO zones (zone_id, tenant_id, site_id, name) VALUES (%s,%s,%s,'Piso 3')",
        (zona, e.sc.tenant, sitio),
    )
    if perfil:
        _como_superusuario(
            e,
            "INSERT INTO user_profiles (user_sub, tenant_id, display_name) VALUES (%s,%s,%s)",
            (titular, e.sc.tenant, TITULAR),
        )
    for posicion, correo in enumerate(CORREOS if contactos is None else contactos, start=1):
        _como_superusuario(
            e,
            "INSERT INTO emergency_contacts (tenant_id, user_sub, posicion, display_name, "
            "email, consent_version, consented_at) VALUES (%s,%s,%s,%s,%s,"
            "'contactos-v1-2026-09',now())",
            (e.sc.tenant, titular, posicion, f"Contacto {posicion}", correo),
        )
    punto = (
        "ST_SetSRID(ST_MakePoint(-99.1612,19.3467),4326)::geography" if con_ubicacion else "NULL"
    )
    checkin = _como_superusuario(
        e,
        "INSERT INTO life_checkins (tenant_id, incident_id, user_id, site_id, status, zone_id, "
        f"geom) VALUES (%s,%s,%s,%s,'need_help',%s,{punto}) RETURNING checkin_id",
        (e.sc.tenant, incidente, titular, sitio, zona),
    )
    fila = e.conn.execute(
        "INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor, payload) "
        "VALUES (%s,%s,%s,'need_help_contacts',%s,%s::jsonb) RETURNING action_id",
        (
            incidente,
            e.sc.tenant,
            BASE,
            f"user:{titular}",
            json.dumps(
                {
                    "user_sub": titular,
                    "checkin_id": str(checkin["checkin_id"]),
                    "con_ubicacion": con_ubicacion,
                }
            ),
        ),
    ).fetchone()
    e.conn.commit()
    return incidente, str(fila["action_id"])


def _pasada(e: _Escena, proveedores: dict, segundos: float = 0.0) -> None:
    from datetime import timedelta

    run_notify_pass(e.conn, Settings(), proveedores, now=BASE + timedelta(seconds=segundos))


def _correos(proveedores: dict) -> list[tuple[dict, dict]]:
    return [(t, m) for t, m in proveedores["email"].sent if m.get("kind") == "need_help_contacts"]


def test_un_correo_a_los_contactos_con_quien_donde_y_la_ubicacion(esc: _Escena) -> None:
    incidente, accion = _pide_ayuda(esc)
    proveedores = {**_providers(), "push": esc.push}
    _pasada(esc, proveedores)

    jobs = esc.conn.execute(
        "SELECT channel, target FROM notification_jobs WHERE action_id = %s", (accion,)
    ).fetchall()
    assert [(j["channel"], j["target"]) for j in jobs] == [("email", {"to": CORREOS})]

    [(destino, mensaje)] = _correos(proveedores)
    assert destino["to"] == CORREOS
    assert mensaje["headline"] == f"TAKAB Ailert · {TITULAR} pidió ayuda · Sitio N"
    assert "link" not in mensaje, "el contacto no es usuario: nada de consola"

    cuerpo = cuerpo_email(mensaje)
    assert cuerpo.splitlines()[0] == (
        f"{TITULAR} indicó que NECESITA AYUDA tras un sismo en Sitio N. Zona: Piso 3."
    )
    assert "https://www.openstreetmap.org/?mlat=19.3467&mlon=-99.1612" in cuerpo
    assert (
        f"Este aviso lo manda TAKAB Ailert porque {TITULAR} lo registró como su "
        "contacto de emergencia." in cuerpo
    )
    assert "consola" not in cuerpo.lower()
    assert incidente not in cuerpo, "los identificadores internos no son para un tercero"


def test_la_ubicacion_solo_si_viajo_en_ese_check_in(esc: _Escena) -> None:
    _pide_ayuda(esc, con_ubicacion=False)
    proveedores = {**_providers(), "push": esc.push}
    _pasada(esc, proveedores)
    [(_, mensaje)] = _correos(proveedores)
    cuerpo = cuerpo_email(mensaje)
    assert "openstreetmap" not in cuerpo
    assert "NECESITA AYUDA" in cuerpo


def test_repetir_la_pasada_no_manda_un_segundo_correo(esc: _Escena) -> None:
    _, accion = _pide_ayuda(esc)
    proveedores = {**_providers(), "push": esc.push}
    for segundos in (0, 5, 60):
        _pasada(esc, proveedores, segundos)
    assert (
        esc.conn.execute(
            "SELECT count(*) AS n FROM notification_jobs WHERE action_id = %s", (accion,)
        ).fetchone()["n"]
        == 1
    )
    assert len(_correos(proveedores)) == 1


def test_sin_contactos_no_hay_job_y_se_dice(esc: _Escena, caplog) -> None:
    _, accion = _pide_ayuda(esc, contactos=[])
    with caplog.at_level(logging.WARNING):
        _pasada(esc, {**_providers(), "push": esc.push})
    assert (
        esc.conn.execute(
            "SELECT count(*) AS n FROM notification_jobs WHERE action_id = %s", (accion,)
        ).fetchone()["n"]
        == 0
    )
    assert any("need_help_contacts" in r.getMessage() for r in caplog.records)


def test_sin_perfil_el_titular_es_una_persona(esc: _Escena) -> None:
    _pide_ayuda(esc, perfil=False)
    proveedores = {**_providers(), "push": esc.push}
    _pasada(esc, proveedores)
    [(_, mensaje)] = _correos(proveedores)
    assert mensaje["headline"] == "TAKAB Ailert · Una persona pidió ayuda · Sitio N"
    assert cuerpo_email(mensaje).startswith("Una persona indicó que NECESITA AYUDA")


def test_ni_con_base_publica_lleva_enlace() -> None:
    """La rama no devuelve ruta: con ``notify_web_public`` encendido tampoco se
    compone un enlace a la consola."""
    fila = {
        "incident_id": "0f0a0000-0000-0000-0000-000000000001",
        "site_id": "s",
        "site_name": "Torre A",
        "site_code": "TA",
        "severity": "critical",
        "trigger": "sasmex",
        "state": "open",
        "opened_at": BASE,
        "event_id": None,
        "action_id": "a",
        "action_kind": "need_help_contacts",
        "action_actor": "user:x",
        "action_payload": {"user_sub": "x", "checkin_id": "c", "con_ubicacion": False},
    }
    mensaje = _message(fila, base_url="https://consola.example/")
    assert "link" not in mensaje
    assert "need_help_contacts" in MENSAJE_POR_KIND
    assert "sin zona" in cuerpo_email(mensaje)
