"""[T-9.42 · D-48] El informe automático AVISA: correo a la cascada y push OPS al círculo táctico.

La pasada del worker `informes` deja la acción `post_event_report`. El orquestador
ancla a ESA acción dos jobs —`email` y `push`— que conviven por el índice único
`(action_id, channel)`:

* el **correo** va a los destinatarios `email` de la cascada del sitio (los mismos
  que reciben el incidente), sin URL prefirmada ni adjunto: el PDF se descarga con
  sesión, porque un enlace reenviado no debe abrirlo;
* el **push OPS** va a los roles de `movement_alert` —el círculo táctico de F1 y el
  administrador—, derivados de la matriz. **Ningún ocupante lo recibe**: el informe
  es para quien decide, no para quien está evacuando.
"""

from __future__ import annotations

import json
import uuid

from takab_api.auth.matrix import roles_with_action
from takab_api.notify.orchestrator import run_notify_pass
from takab_api.notify.providers import cuerpo_email
from takab_api.notify.push import PUSH_CLASS_OPS
from takab_api.settings import Settings
from tests.notify.test_escalada_avisa_a_todos import BASE, _Escena, esc  # noqa: F401
from tests.notify.test_orchestrator import _providers, _Scenario, scenario  # noqa: F401

TACTICOS = set(roles_with_action("movement_alert"))


def _telefono(e: _Escena, sitio: str, rol: str) -> str:
    token = str(uuid.uuid4())
    e.conn.execute(
        "INSERT INTO push_tokens (push_token_id, tenant_id, user_sub, platform, token, "
        "site_id, role) VALUES (%s,%s,%s,'android',%s,%s,%s)",
        (token, e.sc.tenant, str(uuid.uuid4()), f"tok-{token}", sitio, rol),
    )
    e.conn.commit()
    return token


def _informe_listo(e: _Escena, incidente: str, *, preliminar: bool = True) -> str:
    """La acción que deja la pasada del worker `informes` al terminar."""
    fila = e.conn.execute(
        "INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor, payload) "
        "VALUES (%s,%s,%s,'post_event_report','system:informes',%s::jsonb) "
        "RETURNING action_id",
        (
            incidente,
            e.sc.tenant,
            BASE,
            json.dumps(
                {
                    "report_id": str(uuid.uuid4()),
                    "evidence_id": str(uuid.uuid4()),
                    "variant": "executive",
                    "trigger": "plazo",
                    "preliminar": preliminar,
                }
            ),
        ),
    ).fetchone()
    e.conn.commit()
    return str(fila["action_id"])


def _jobs(e: _Escena, accion: str) -> dict[str, dict]:
    filas = e.conn.execute(
        "SELECT channel, target, status FROM notification_jobs WHERE action_id = %s", (accion,)
    ).fetchall()
    assert len({f["channel"] for f in filas}) == len(filas), "un job por canal y acción"
    return {f["channel"]: f for f in filas}


def _sitio(e: _Escena, incidente: str) -> str:
    return str(
        e.conn.execute(
            "SELECT site_id FROM incidents WHERE incident_id = %s", (incidente,)
        ).fetchone()["site_id"]
    )


def test_correo_a_la_cascada_y_push_OPS_a_los_tacticos_y_a_ningun_ocupante(esc: _Escena) -> None:  # noqa: F811
    incidente = esc.sc.seed_incident(trigger="local_threshold", severity="watch")
    sitio = _sitio(esc, incidente)
    ocupante = _telefono(esc, sitio, "occupant")
    brigada = _telefono(esc, sitio, "brigadista")
    accion = _informe_listo(esc, incidente)

    proveedores = {**_providers(), "push": esc.push}
    run_notify_pass(esc.conn, Settings(), proveedores, now=BASE)

    jobs = _jobs(esc, accion)
    assert set(jobs) == {"email", "push"}
    assert jobs["email"]["target"] == {"to": ["ops@example.mx"]}
    assert jobs["push"]["target"]["push_class"] == PUSH_CLASS_OPS
    assert set(jobs["push"]["target"]["roles"]) == TACTICOS
    assert "occupant" not in jobs["push"]["target"]["roles"]

    alcanzados = {d.push_token_id for devices, _ in esc.push.entregas for d in devices}
    assert brigada in alcanzados
    assert ocupante not in alcanzados, "el informe no es para quien está evacuando"

    [(_, mensaje)] = [
        (t, m) for t, m in proveedores["email"].sent if m.get("kind") == "post_event_report"
    ]
    assert mensaje["headline"].startswith("TAKAB Ailert · Informe del evento · ")
    assert mensaje["preliminar"] is True
    assert "url" not in mensaje and "attachment" not in mensaje
    cuerpo = cuerpo_email(mensaje)
    assert cuerpo.splitlines()[0].startswith("El informe posterior al evento de ")
    assert "Es PRELIMINAR: el inmueble todavía no tiene dictamen firmado." in cuerpo


def test_el_enlace_lleva_al_cierre_del_evento_y_no_al_PDF(esc: _Escena) -> None:  # noqa: F811
    from takab_api.notify.orchestrator import _message

    fila = {
        "incident_id": "0f0a0000-0000-0000-0000-000000000001",
        "site_id": "s",
        "site_name": "Torre A",
        "site_code": "TA",
        "severity": "warning",
        "trigger": "sasmex",
        "state": "open",
        "opened_at": BASE,
        "event_id": None,
        "action_id": "a",
        "action_kind": "post_event_report",
        "action_actor": "system:informes",
        "action_payload": {"preliminar": False, "evidence_id": "e"},
    }
    mensaje = _message(fila, base_url="https://consola.example/")
    assert (
        mensaje["link"]
        == "https://consola.example/triage/0f0a0000-0000-0000-0000-000000000001/cierre"
    )
    assert mensaje["preliminar"] is False
    assert "PRELIMINAR" not in cuerpo_email(mensaje)


def test_es_idempotente(esc: _Escena) -> None:  # noqa: F811
    incidente = esc.sc.seed_incident(trigger="local_threshold", severity="watch")
    _telefono(esc, _sitio(esc, incidente), "brigadista")
    accion = _informe_listo(esc, incidente)

    esc.pasada()
    esc.pasada(5)
    esc.pasada(60)

    assert set(_jobs(esc, accion)) == {"email", "push"}


def test_sin_correo_en_la_cascada_no_hay_correo_pero_si_push(
    scenario: _Scenario,  # noqa: F811
    caplog,
) -> None:
    """Sin destinatarios no se inventa uno; se DICE, como en el aviso del pánico."""
    scenario.seed_config({"notifications": {"sms": {"to": "+525522222222"}}})
    escena = _Escena(scenario)
    incidente = escena.sc.seed_incident(trigger="local_threshold", severity="watch")
    _telefono(escena, _sitio(escena, incidente), "brigadista")
    accion = _informe_listo(escena, incidente)

    escena.pasada()

    assert set(_jobs(escena, accion)) == {"push"}
    assert any("post_event_report" in r.getMessage() for r in caplog.records)
