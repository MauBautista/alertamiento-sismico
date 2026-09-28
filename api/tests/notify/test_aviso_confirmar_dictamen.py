"""[T-9.33 · D-43] El AMARILLO de la regla avisa a quien puede CONFIRMARLO, y a nadie más.

Cuando el worker de dictamen emite un AMARILLO sin firmar deja la acción
``dictamen_confirm_requested`` (una por dictamen) y el orquestador la convierte en un
push ``DICTAMEN_CONFIRM`` anclado a esa acción (``uq_notification_jobs_action``) con
``roles`` = ``roles_with_action("confirm_dictamen")``. El ocupante NO lo recibe: no
puede confirmar y su pantalla es la del reingreso.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from takab_api.auth.matrix import roles_with_action
from takab_api.notify.push import (
    _ALERT_TEXT,
    _DELIVERY_STYLE,
    PUSH_CLASS_DICTAMEN_CONFIRM,
    build_push_payload,
)
from tests.notify.test_escalada_avisa_a_todos import BASE, _Escena, esc  # noqa: F401
from tests.notify.test_orchestrator import scenario  # noqa: F401

CONFIRMAN = set(roles_with_action("confirm_dictamen"))


def test_el_estilo_es_OPS_y_la_fase_la_del_dictamen() -> None:
    """Trabajo de revisión, no alarma: canal `ops`, sonido por defecto, prioridad normal."""
    estilo = _DELIVERY_STYLE[PUSH_CLASS_DICTAMEN_CONFIRM]
    assert estilo["channel_id"] == "ops"
    assert estilo["sound"] == "default"
    assert estilo["android_priority"] == "normal"
    assert PUSH_CLASS_DICTAMEN_CONFIRM in _ALERT_TEXT
    payload = build_push_payload(
        push_class=PUSH_CLASS_DICTAMEN_CONFIRM,
        site_id="s",
        incident_id="i",
        phase="dictamen_confirm",
    )
    assert json.loads(payload["default"])["class"] == PUSH_CLASS_DICTAMEN_CONFIRM


def _telefono(e: _Escena, sitio: str, rol: str) -> str:
    token = str(uuid.uuid4())
    e.conn.execute(
        "INSERT INTO push_tokens (push_token_id, tenant_id, user_sub, platform, token, "
        "site_id, role) VALUES (%s,%s,%s,'android',%s,%s,%s)",
        (token, e.sc.tenant, str(uuid.uuid4()), f"tok-{token}", sitio, rol),
    )
    e.conn.commit()
    return token


def _peticion(e: _Escena, incidente: str, *, dictamen: str) -> str:
    """La acción que deja el worker al emitir un AMARILLO sin firmar."""
    fila = e.conn.execute(
        "INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor, payload) "
        "VALUES (%s,%s,%s,'dictamen_confirm_requested','system:dictamen',%s::jsonb) "
        "RETURNING action_id",
        (
            incidente,
            e.sc.tenant,
            BASE,
            json.dumps({"dictamen_id": dictamen, "band": "amarillo"}),
        ),
    ).fetchone()
    e.conn.commit()
    return str(fila["action_id"])


def _jobs(e: _Escena, accion: str) -> list[dict]:
    return e.conn.execute(
        "SELECT target, status FROM notification_jobs WHERE action_id = %s", (accion,)
    ).fetchall()


def test_el_aviso_sale_UNA_vez_a_quien_confirma_y_nunca_al_ocupante(esc: _Escena) -> None:  # noqa: F811
    # CAUTELA: el incidente en sí no manda push (D-39); sólo queda el de la petición.
    incidente = esc.sc.seed_incident(trigger="local_threshold", severity="watch")
    sitio = str(
        esc.conn.execute(
            "SELECT site_id FROM incidents WHERE incident_id = %s", (incidente,)
        ).fetchone()["site_id"]
    )
    ocupante = _telefono(esc, sitio, "occupant")
    brigada = _telefono(esc, sitio, "brigadista")
    inspector = _telefono(esc, sitio, "inspector")
    accion = _peticion(esc, incidente, dictamen=str(uuid.uuid4()))

    esc.pasada()
    esc.pasada(5)

    [job] = _jobs(esc, accion)
    assert job["target"]["push_class"] == PUSH_CLASS_DICTAMEN_CONFIRM
    assert set(job["target"]["roles"]) == CONFIRMAN
    alcanzados = {d.push_token_id for devices, _ in esc.push.entregas for d in devices}
    assert {brigada, inspector} <= alcanzados
    assert ocupante not in alcanzados, "el ocupante no puede confirmar: no se le pide"
    assert any("dictamen_confirm" in str(payload) for _, payload in esc.push.entregas)


def test_si_ya_lo_firmaron_no_se_pide(esc: _Escena) -> None:  # noqa: F811
    """Una confirmación (o firma) POSTERIOR a la petición la deja sin objeto."""
    incidente = esc.sc.seed_incident(trigger="local_threshold", severity="watch")
    accion = _peticion(esc, incidente, dictamen=str(uuid.uuid4()))
    esc.conn.execute(
        "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, "
        "signature_kind, band, created_at) VALUES (%s,%s,'inhabit_monitor','{}'::jsonb,"
        "%s,'confirmation','amarillo',%s)",
        (esc.sc.tenant, incidente, str(uuid.uuid4()), BASE + timedelta(seconds=1)),
    )
    esc.conn.commit()

    esc.pasada(5)

    assert _jobs(esc, accion) == []


def _accion(e: _Escena, incidente: str, kind: str, payload: dict, *, s: float = 0.0) -> str:
    # `ts` distinto por fila: `uq_incident_actions_ack` es (incidente, kind, actor, ts).
    fila = e.conn.execute(
        "INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor, payload) "
        "VALUES (%s,%s,%s,%s,'system:dictamen',%s::jsonb) RETURNING action_id",
        (incidente, e.sc.tenant, BASE + timedelta(seconds=s), kind, json.dumps(payload)),
    ).fetchone()
    e.conn.commit()
    return str(fila["action_id"])


def test_la_CONFIRMACION_y_el_VERDE_del_sistema_liberan_como_una_firma(esc: _Escena) -> None:  # noqa: F811
    """El push OPS de cambio de fase (el que despierta la pantalla del reingreso) sale
    igual para `dictamen_confirmed` y para el VERDE firmado por el SISTEMA que para
    `dictamen_signed`. Un preliminar sin firmar (`dictamen` sin `system`) no lo manda."""
    incidente = esc.sc.seed_incident(trigger="local_threshold", severity="watch")
    confirmada = _accion(esc, incidente, "dictamen_confirmed", {"status": "inhabit_monitor"})
    sistema = _accion(
        esc, incidente, "dictamen", {"status": "normal_operation", "signature_kind": "system"}
    )
    preliminar = _accion(
        esc, incidente, "dictamen", {"status": "inhabit_monitor", "signature_kind": None}, s=1.0
    )

    esc.pasada(5)

    for accion in (confirmada, sistema):
        [job] = _jobs(esc, accion)
        assert job["target"]["push_class"] == "OPS"
        assert "roles" not in job["target"], "la liberación es para TODO el inmueble"
    assert _jobs(esc, preliminar) == []
