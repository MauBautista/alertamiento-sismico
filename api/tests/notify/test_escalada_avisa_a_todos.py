"""[T-9.03] La escalada RE-NOTIFICA a todo el edificio.

Medido en el gabinete real (2026-09-24): el incidente nace `local_threshold` —una
estación sola, que solo ADVIERTE (`incident/autoridad.py`)— y segundos después el
WR-1 de SASMEX lo escala en el mismo episodio. Con T-9.02 el `trigger` ya sube, y
`mobile_state` ya pasa a ordenar evacuar… pero el teléfono dormido no se entera: el
orquestador solo encolaba incidentes SIN jobs, y `uq_notification_jobs_incident`
(incident, channel, mode) impedía un segundo push aunque alguien lo intentara. El
único push que el edificio recibió fue el de «advertencia».

El arreglo, y lo que estas pruebas fijan:

  · el push de incidente guarda si AUTORIZABA evacuar cuando se planificó
    (`target.autoriza`), con la MISMA regla que lee la app;
  · una pasada nueva busca los que se planificaron sin autorizar y AHORA
    autorizan, deja `alert_escalated` en la bitácora y ancla a esa acción un
    push CRISIS nuevo (índice por acción ⇒ idempotente);
  · y no toca a quien autorizaba desde el principio, a los cerrados, ni a los
    jobs anteriores a esta ficha (sin la clave, no se sabe qué se les dijo).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import timedelta

import psycopg
import pytest

from takab_api.notify.orchestrator import run_notify_pass
from takab_api.notify.push import PUSH_CLASS_CRISIS, PushDevice, PushOutcome
from takab_api.settings import Settings
from tests.notify.test_orchestrator import (  # noqa: F401
    BASE,
    _providers,
    _Scenario,
    scenario,
)


class _PushQueEntrega:
    """Proveedor push REAL a efectos del orquestador: entrega a todos y lo apunta."""

    simulated = False

    def __init__(self) -> None:
        self.entregas: list[tuple[list[PushDevice], dict]] = []

    def deliver(self, devices: list[PushDevice], payload: dict) -> PushOutcome:
        self.entregas.append((list(devices), payload))
        return PushOutcome(delivered=len(devices))


class _Escena:
    def __init__(self, sc: _Scenario) -> None:
        self.sc = sc
        self.push = _PushQueEntrega()
        self.eventos: list[str] = []

    @property
    def conn(self) -> psycopg.Connection:
        return self.sc.conn

    def pasada(self, segundos: float = 0.0) -> dict[str, int]:
        return run_notify_pass(
            self.conn,
            Settings(),
            {**_providers(), "push": self.push},
            now=BASE + timedelta(seconds=segundos),
        )

    def incidente(self, *, trigger: str, severity: str = "critical") -> str:
        """Incidente con UN teléfono registrado en su inmueble (sin él no hay push)."""
        incidente = self.sc.seed_incident(trigger=trigger, severity=severity)
        sitio = self.conn.execute(
            "SELECT site_id FROM incidents WHERE incident_id = %s", (incidente,)
        ).fetchone()["site_id"]
        token = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO push_tokens (push_token_id, tenant_id, user_sub, platform, token, "
            "site_id) VALUES (%s,%s,%s,'android',%s,%s)",
            (token, self.sc.tenant, str(uuid.uuid4()), f"tok-{token}", sitio),
        )
        self.conn.commit()
        return incidente

    def enlazar_evento(self, incidente: str, node_count: int) -> str:
        """El evento regional que enlaza el motor de cuórum, con su `node_count`."""
        evento = f"EVT-T903-{uuid.uuid4().hex[:12]}"
        self.conn.execute(
            "INSERT INTO seismic_events (event_id, source, detected_at, meta) "
            "VALUES (%s,'local_quorum',%s,%s::jsonb)",
            (evento, BASE, json.dumps({"node_count": node_count})),
        )
        self.eventos.append(evento)
        self.conn.execute(
            "UPDATE incidents SET event_id = %s WHERE incident_id = %s", (evento, incidente)
        )
        self.conn.commit()
        return evento

    def actualizar(self, incidente: str, **campos: object) -> None:
        sets = ", ".join(f"{c} = %s" for c in campos)
        self.conn.execute(
            f"UPDATE incidents SET {sets} WHERE incident_id = %s",  # noqa: S608 - claves fijas del test
            (*campos.values(), incidente),
        )
        self.conn.commit()

    def escaladas(self, incidente: str) -> list[dict]:
        return self.conn.execute(
            "SELECT action_id, actor, payload FROM incident_actions "
            "WHERE incident_id = %s AND kind = 'alert_escalated'",
            (incidente,),
        ).fetchall()

    def push_de_incidente(self, incidente: str) -> list[dict]:
        return self.conn.execute(
            "SELECT target, status FROM notification_jobs WHERE incident_id = %s "
            "AND channel = 'push' AND action_id IS NULL",
            (incidente,),
        ).fetchall()

    def push_de_escalada(self, incidente: str) -> list[dict]:
        return self.conn.execute(
            "SELECT action_id, target, status, mode FROM notification_jobs "
            "WHERE incident_id = %s AND channel = 'push' AND action_id IS NOT NULL",
            (incidente,),
        ).fetchall()

    def emails_paralelos(self, incidente: str) -> list[dict]:
        return self.conn.execute(
            "SELECT action_id, due_at FROM notification_jobs WHERE incident_id = %s "
            "AND channel = 'email' AND mode = 'parallel'",
            (incidente,),
        ).fetchall()


@pytest.fixture
def esc(scenario: _Scenario) -> Iterator[_Escena]:  # noqa: F811
    e = _Escena(scenario)
    scenario.seed_config()
    try:
        yield e
    finally:
        # `seismic_events` no lleva tenant y la limpieza del escenario no la toca.
        # En 'replica' los FK callan: el incidente que la enlaza lo borra después la
        # limpieza del escenario.
        conn = scenario.conn
        conn.rollback()
        conn.execute("RESET ROLE")
        conn.execute("SET session_replication_role = 'replica'")
        conn.execute("DELETE FROM seismic_events WHERE event_id = ANY(%s)", (e.eventos,))
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()


# --- el hecho que se guarda al planificar ------------------------------------


def test_el_push_de_incidente_guarda_si_autorizaba_al_planificarse(esc: _Escena) -> None:
    local = esc.incidente(trigger="local_threshold")
    sasmex = esc.incidente(trigger="sasmex")

    esc.pasada()

    assert [j["target"].get("autoriza") for j in esc.push_de_incidente(local)] == [False]
    assert [j["target"].get("autoriza") for j in esc.push_de_incidente(sasmex)] == [True]


# --- (1) umbral local que escala a SASMEX ------------------------------------


def test_el_umbral_local_que_escala_a_SASMEX_avisa_a_TODO_el_edificio(esc: _Escena) -> None:
    incidente = esc.incidente(trigger="local_threshold")
    esc.pasada()
    assert esc.escaladas(incidente) == [], "sin escalada todavía no hay nada que avisar"
    assert len(esc.push.entregas) == 1, "el push de advertencia tenía que salir"

    # La ingesta (T-9.02) sube el disparo en el MISMO incidente.
    esc.actualizar(incidente, trigger="sasmex")
    esc.pasada(5)

    escaladas = esc.escaladas(incidente)
    assert len(escaladas) == 1, "la escalada no dejó rastro en la bitácora del incidente"
    accion = escaladas[0]
    assert accion["payload"]["from_trigger"] == "local_threshold"
    assert accion["payload"]["to_trigger"] == "sasmex"
    assert accion["actor"].startswith("system:")

    jobs = esc.push_de_escalada(incidente)
    assert len(jobs) == 1, "la escalada no encoló un push nuevo: el teléfono dormido no se entera"
    job = jobs[0]
    assert job["action_id"] == accion["action_id"], "el push no está anclado a la escalada"
    assert job["target"]["push_class"] == PUSH_CLASS_CRISIS
    assert "roles" not in job["target"], (
        "el push de la escalada va acotado a un círculo: tiene que despertar a TODO el edificio"
    )
    assert job["status"] == "sent"
    assert len(esc.push.entregas) == 2, "el segundo push no llegó a salir hacia el proveedor"


def test_la_escalada_replanifica_el_email_critico_si_no_existia(esc: _Escena) -> None:
    """Un incidente que nació `warning` no tuvo email paralelo crítico; si escala a
    crítico con SASMEX, lo tiene que tener — una sola vez."""
    incidente = esc.incidente(trigger="local_threshold", severity="warning")
    esc.pasada()
    assert esc.emails_paralelos(incidente) == []

    esc.actualizar(incidente, trigger="sasmex", severity="critical")
    esc.pasada(5)

    emails = esc.emails_paralelos(incidente)
    assert len(emails) == 1, f"se esperaba UN email paralelo crítico, hay {len(emails)}"
    assert emails[0]["action_id"] is None


def test_el_email_critico_que_ya_existia_no_se_duplica(esc: _Escena) -> None:
    incidente = esc.incidente(trigger="local_threshold", severity="critical")
    esc.pasada()
    assert len(esc.emails_paralelos(incidente)) == 1

    esc.actualizar(incidente, trigger="sasmex")
    esc.pasada(5)

    assert len(esc.escaladas(incidente)) == 1
    assert len(esc.emails_paralelos(incidente)) == 1


# --- (2) el cuórum de la red llega a `quorum_min_nodes` ----------------------


def test_el_cuorum_que_alcanza_el_minimo_tambien_avisa_a_todos(esc: _Escena) -> None:
    incidente = esc.incidente(trigger="local_threshold")
    evento = esc.enlazar_evento(incidente, node_count=1)
    esc.pasada()
    assert esc.escaladas(incidente) == []

    minimo = Settings().quorum_min_nodes
    esc.conn.execute(
        "UPDATE seismic_events SET meta = %s::jsonb WHERE event_id = %s",
        (json.dumps({"node_count": minimo}), evento),
    )
    esc.conn.commit()
    esc.pasada(5)

    escaladas = esc.escaladas(incidente)
    assert len(escaladas) == 1, "la red corroboró y el edificio no recibió la orden"
    payload = escaladas[0]["payload"]
    assert payload["node_count"] == minimo
    assert payload["from_trigger"] == payload["to_trigger"] == "local_threshold"
    assert len(esc.push_de_escalada(incidente)) == 1


def test_un_cuorum_por_debajo_del_minimo_no_escala(esc: _Escena) -> None:
    """No-vacuidad del caso anterior: lo que escala es alcanzar el mínimo, no que
    el evento exista."""
    incidente = esc.incidente(trigger="local_threshold")
    esc.enlazar_evento(incidente, node_count=Settings().quorum_min_nodes - 1)
    esc.pasada()
    esc.pasada(5)
    assert esc.escaladas(incidente) == []
    assert esc.push_de_escalada(incidente) == []


# --- (3) idempotencia ----------------------------------------------------------


def test_una_segunda_pasada_no_duplica_la_escalada(esc: _Escena) -> None:
    incidente = esc.incidente(trigger="local_threshold")
    esc.pasada()
    esc.actualizar(incidente, trigger="sasmex")
    esc.pasada(5)
    esc.pasada(10)
    esc.pasada(15)

    assert len(esc.escaladas(incidente)) == 1, "cada pasada volvió a escalar"
    assert len(esc.push_de_escalada(incidente)) == 1, "cada pasada volvió a despertar al edificio"
    assert len(esc.push.entregas) == 2


def test_la_base_rechaza_una_SEGUNDA_escalada_del_mismo_incidente(esc: _Escena) -> None:
    """El candado de la 0070, medido: aunque dos escritores se saltaran el NOT EXISTS,
    `uq_incident_actions_escalada` no deja dos escaladas en la bitácora."""
    incidente = esc.incidente(trigger="local_threshold")
    fila = (incidente, esc.sc.tenant, "alert_escalated", "system:test", "{}")
    sql = (
        "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload) "
        "VALUES (%s,%s,%s,%s,%s::jsonb)"
    )
    esc.conn.execute(sql, fila)
    esc.conn.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        esc.conn.execute(sql, (*fila[:3], "system:otro", "{}"))
    esc.conn.rollback()


# --- (4) cerrado ---------------------------------------------------------------


def test_un_incidente_cerrado_no_escala(esc: _Escena) -> None:
    incidente = esc.incidente(trigger="local_threshold")
    esc.pasada()
    esc.actualizar(
        incidente, trigger="sasmex", state="closed", closed_at=BASE + timedelta(seconds=3)
    )
    esc.pasada(5)

    assert esc.escaladas(incidente) == []
    assert esc.push_de_escalada(incidente) == []


# --- (5) ya autorizaba desde el principio ---------------------------------------


def test_el_que_autorizaba_desde_el_principio_no_se_escala(esc: _Escena) -> None:
    incidente = esc.incidente(trigger="sasmex")
    esc.pasada()
    esc.pasada(5)

    assert esc.escaladas(incidente) == []
    assert esc.push_de_escalada(incidente) == []
    assert len(esc.push.entregas) == 1, "a quien ya se le ordenó evacuar se le despertó dos veces"


# --- (6) jobs anteriores a esta ficha -----------------------------------------


def test_un_push_viejo_SIN_la_clave_no_es_candidato(esc: _Escena) -> None:
    """Un job planificado antes de T-9.03 no dice qué se le comunicó al edificio.
    Tratarlo como «no autorizaba» despertaría a todo el mundo por un incidente que
    quizá ya ordenó evacuar; la ficha elige no adivinar."""
    incidente = esc.sc.seed_incident(trigger="local_threshold", severity="critical")
    sitio = esc.conn.execute(
        "SELECT site_id FROM incidents WHERE incident_id = %s", (incidente,)
    ).fetchone()["site_id"]
    esc.conn.execute(
        "INSERT INTO notification_jobs (tenant_id, incident_id, channel, mode, position, "
        "target, due_at, status) VALUES (%s,%s,'push','parallel',0,%s::jsonb,%s,'sent')",
        (esc.sc.tenant, incidente, json.dumps({"site_id": str(sitio)}), BASE),
    )
    esc.conn.commit()
    esc.actualizar(incidente, trigger="sasmex")
    esc.pasada(5)

    assert esc.escaladas(incidente) == []
    assert esc.push_de_escalada(incidente) == []
