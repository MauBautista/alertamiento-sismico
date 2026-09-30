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


# ---------------------------------------------------------------------------
# [T-9.80 · 0078] Al DESPACHAR sólo salen los contactos que SIGUEN en la lista.
#
# El aviso guarda los correos al encolar. Si el titular retira un contacto, o ejerce
# ARCO (que borra la lista entera y no toca un aviso aún `pending`), antes de que el
# aviso salga —el worker estaba caído, o el aviso esperaba un reintento—, el correo
# NO puede llegarle a quien ya no está, ni quedarse guardado en la fila.
# ---------------------------------------------------------------------------


def _encolado_sin_salir(e: _Escena, incidente: str, accion: str) -> str:
    """El job tal como lo deja el encolado, aún sin despachar."""
    fila = _como_superusuario(
        e,
        "INSERT INTO notification_jobs (tenant_id, incident_id, channel, mode, status, "
        "target, due_at, action_id) VALUES (%s,%s,'email','parallel','pending',%s::jsonb,%s,%s) "
        "RETURNING job_id",
        (e.sc.tenant, incidente, json.dumps({"to": CORREOS}), BASE, accion),
    )
    return str(fila["job_id"])


def _retira(e: _Escena, correo: str | None = None) -> None:
    donde, params = "tenant_id = %s", (e.sc.tenant,)
    if correo is not None:
        donde, params = donde + " AND email = %s", (e.sc.tenant, correo)
    _como_superusuario(e, f"DELETE FROM emergency_contacts WHERE {donde}", params)


def _job(e: _Escena, job: str) -> dict:
    return e.conn.execute(
        "SELECT status, target, error FROM notification_jobs WHERE job_id = %s", (job,)
    ).fetchone()


def test_un_contacto_retirado_antes_de_salir_no_recibe_el_aviso(esc: _Escena) -> None:
    incidente, accion = _pide_ayuda(esc)
    job = _encolado_sin_salir(esc, incidente, accion)
    _retira(esc, CORREOS[0])
    proveedores = {**_providers(), "push": esc.push}
    _pasada(esc, proveedores)

    [(destino, _)] = _correos(proveedores)
    assert destino["to"] == CORREOS[1:]
    fila = _job(esc, job)
    assert fila["status"] == "sent"
    assert fila["target"] == {"to": CORREOS[1:]}, "la fila guarda a quién fue DE VERDAD"


def test_sin_contactos_vigentes_el_aviso_se_omite_y_queda_borrado(esc: _Escena) -> None:
    """El caso de ARCO: la lista entera desapareció con el aviso aún en vuelo."""
    from takab_api.privacy.erasure import ERASED_NOTICE_TARGET

    incidente, accion = _pide_ayuda(esc)
    job = _encolado_sin_salir(esc, incidente, accion)
    _retira(esc)
    proveedores = {**_providers(), "push": esc.push}
    _pasada(esc, proveedores)

    assert _correos(proveedores) == [], "no le llega a quien ya no está en la lista"
    fila = _job(esc, job)
    assert fila["status"] == "skipped"
    assert fila["target"] == ERASED_NOTICE_TARGET
    assert "sin contactos vigentes" in fila["error"]


def test_el_error_del_proveedor_no_guarda_los_correos_de_los_contactos(esc: _Escena) -> None:
    """SES en sandbox rechaza citando a los destinatarios. El error se escribe en el job
    y, si es terminal, en `incident_actions` (append-only: ni ARCO lo borraría)."""
    from datetime import timedelta

    from takab_api.notify.providers import NotifyError

    class _SesQueCita:
        simulated = False  # un proveedor REAL: quien no lo declara se trata como simulado
        sent: list = []

        def send(self, target: dict, message: dict) -> None:
            raise NotifyError(
                "ses: MessageRejected: Email address is not verified. The following "
                f"identities failed the check in region US-EAST-2: {', '.join(target['to'])}"
            )

    incidente, accion = _pide_ayuda(esc)
    proveedores = {**_providers(), "push": esc.push, "email": _SesQueCita()}
    run_notify_pass(
        esc.conn, Settings(notify_max_attempts=1), proveedores, now=BASE + timedelta(seconds=0)
    )

    fila = esc.conn.execute(
        "SELECT status, error FROM notification_jobs WHERE action_id = %s", (accion,)
    ).fetchone()
    assert fila["status"] == "failed"
    assert "@" not in fila["error"] and "<correo>" in fila["error"]
    evidencia = esc.conn.execute(
        "SELECT payload FROM incident_actions WHERE incident_id = %s AND payload ? 'error'",
        (incidente,),
    ).fetchall()
    assert evidencia, "el fallo terminal deja evidencia"
    assert all("@" not in json.dumps(e["payload"]) for e in evidencia)


def test_el_recorte_no_devuelve_los_correos_si_arco_los_borro_entretanto(esc: _Escena) -> None:
    """La carrera que midió la segunda revisión. La pasada leyó el aviso con sus
    correos; entre esa lectura y el recorte, ARCO lo dejó borrado. El envío en curso
    ya no se puede parar, pero la fila no puede recuperar los correos."""
    from takab_api.notify.orchestrator import _recorta_a_contactos_vigentes
    from takab_api.privacy.erasure import ERASED_NOTICE_TARGET

    incidente, accion = _pide_ayuda(esc)
    job = _encolado_sin_salir(esc, incidente, accion)
    _retira(esc, CORREOS[0])  # para que el recorte QUIERA escribir
    fila_leida = {
        "job_id": job,
        "channel": "email",
        "tenant_id": esc.sc.tenant,
        "target": {"to": CORREOS},
        "action_payload": esc.conn.execute(
            "SELECT payload FROM incident_actions WHERE action_id = %s", (accion,)
        ).fetchone()["payload"],
    }
    _como_superusuario(  # ARCO, entre la lectura y el recorte
        esc,
        "UPDATE notification_jobs SET target = %s::jsonb WHERE job_id = %s",
        (json.dumps(ERASED_NOTICE_TARGET), job),
    )
    counts: dict[str, int] = {"skipped": 0, "failed": 0, "retried": 0}
    sale_con = _recorta_a_contactos_vigentes(esc.conn, counts, fila_leida, now=BASE, max_attempts=3)
    assert sale_con == {"to": CORREOS[1:]}
    assert _job(esc, job)["target"] == ERASED_NOTICE_TARGET


@pytest.mark.parametrize("rama", ["simulado", "sin_proveedor"])
def test_el_recorte_va_ANTES_de_las_ramas_que_no_envian(esc: _Escena, rama: str) -> None:
    """Un aviso simulado, o sin proveedor, también deja su desenlace en la fila. Si el
    recorte fuera después, se quedaría con los correos de quien ya no está."""
    from datetime import timedelta

    from takab_api.privacy.erasure import ERASED_NOTICE_TARGET

    incidente, accion = _pide_ayuda(esc)
    job = _encolado_sin_salir(esc, incidente, accion)
    _retira(esc)
    proveedores = {**_providers(), "push": esc.push}
    if rama == "simulado":
        proveedores["email"] = object()  # sin `simulated = False`: se trata como simulado
    else:
        del proveedores["email"]
    run_notify_pass(
        esc.conn, Settings(notify_max_attempts=1), proveedores, now=BASE + timedelta(seconds=0)
    )
    fila = _job(esc, job)
    assert fila["status"] == "skipped"
    assert fila["target"] == ERASED_NOTICE_TARGET


def test_un_aviso_a_contactos_por_otro_canal_FALLA_con_su_causa(esc: _Escena) -> None:
    """Sólo se sabe recortar correos. El SMS de D-48 tendrá que comparar teléfonos:
    hasta entonces no sale, ni se omite en silencio."""
    from datetime import timedelta

    incidente, accion = _pide_ayuda(esc)
    fila = _como_superusuario(
        esc,
        "INSERT INTO notification_jobs (tenant_id, incident_id, channel, mode, status, "
        "target, due_at, action_id) VALUES (%s,%s,'sms','parallel','pending', "
        "jsonb_build_object('to', '+525550001111'), %s, %s) RETURNING job_id",
        (esc.sc.tenant, incidente, BASE, accion),
    )
    proveedores = {**_providers(), "push": esc.push}
    run_notify_pass(
        esc.conn, Settings(notify_max_attempts=1), proveedores, now=BASE + timedelta(seconds=0)
    )
    job = _job(esc, str(fila["job_id"]))
    assert job["status"] == "failed"
    assert "sin recorte" in job["error"]
    assert proveedores["sms"].sent == []


def test_si_no_se_puede_leer_la_lista_el_aviso_falla_y_la_pasada_sigue(
    esc: _Escena, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un error de base al leer los contactos no puede envenenar la transacción de la
    pasada entera, la de todos los clientes: savepoint, y el job falla con su causa."""
    from takab_api.notify import orchestrator

    incidente, accion = _pide_ayuda(esc)
    job = _encolado_sin_salir(esc, incidente, accion)
    monkeypatch.setattr(orchestrator, "_CONTACT_EMAILS_SQL", "SELECT email FROM no_existe")
    _pasada(esc, {**_providers(), "push": esc.push})
    fila = _job(esc, job)
    assert fila["status"] in ("pending", "failed")
    assert "no se pudo leer la lista" in fila["error"]
