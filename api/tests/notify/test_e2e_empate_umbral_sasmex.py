"""[T-9.02 · T-9.03] PATA 2 DEL E2E — el empate umbral→SASMEX, del gabinete al teléfono.

La revisión de F0 lo encontró: los tests de la nube de T-9.02 y T-9.03 metían el
SASMEX directamente en `handle_local_event`, o subían el `trigger` con un UPDATE.
Ése era un mensaje que el gabinete real NO mandaba: `CloudConnector._dedup_key`
no incluía `source`, y un SASMEX con el mismo `event_id` (T-7.49, un id por
episodio) y el mismo tier que el umbral se tomaba por re-publicación idéntica y
no salía del Pi. La nube estaba arreglada para un caso que no le podía llegar.

**EL PAYLOAD NO SE ESCRIBE AQUÍ A MANO.** Se lee de
`edge/tests/vectors/local_events_umbral_y_sasmex.json`, que produce el
supervisor REAL en `edge/tests/test_supervisor_cloud_wiring.py` (pata 1) y
verifica contra esa misma corrida: la secuencia exacta de `LocalEvent` que sale
del Pi cuando la sacudida dispara el umbral y el WR-1 da SASMEX en el mismo
episodio. Los dos venv no se ven —`import takab_edge` desde api falla—, así que
el vector es la costura (mismo método que `test_e2e_estado_del_rele.py`, T-2.116).

Aquí el MISMO vector recorre la cadena de la nube, en el orden en que llega:
contrato (`contracts/loader`) → ingesta (`handle_local_event`) → orquestador
(`run_notify_pass`), con una pasada del orquestador ENTRE el umbral y el SASMEX,
que es lo que convierte el empate en una ESCALADA: el edificio ya recibió el push
de «advertencia» y tiene que recibir el de evacuar.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from takab_api.contracts.loader import discriminate, validate
from takab_api.contracts.meta import Meta
from takab_api.incident.autoridad import autoriza_evacuacion
from takab_api.ingest.handlers import GatewayCtx, handle_local_event
from takab_api.notify.orchestrator import run_notify_pass
from takab_api.notify.push import PUSH_CLASS_CRISIS
from takab_api.settings import Settings
from tests.notify.test_escalada_avisa_a_todos import _Escena
from tests.notify.test_orchestrator import (  # noqa: F401
    BASE,
    SRC_LAT,
    SRC_LON,
    _providers,
    _Scenario,
    scenario,
)

#: Lo que sale del gabinete real (pata 1 del E2E).
VECTOR = (
    Path(__file__).resolve().parents[3]
    / "edge"
    / "tests"
    / "vectors"
    / "local_events_umbral_y_sasmex.json"
)

META = Meta(principal="gw-t902-e2e", topic="takab/events", ts_iot=None)


def _vector() -> list[dict]:
    return json.loads(VECTOR.read_text("utf-8"))


def _rebasado(eventos: list[dict]) -> list[dict]:
    """`created_at` es el reloj de pared del gabinete: se traslada a la época
    AISLADA de los tests de notify (`BASE`, 2033) conservando orden e intervalos.

    El orquestador barre TODOS los inquilinos dentro de su ventana: con la fecha
    del vector (2026) recogería incidentes que otras suites dejaron commiteados
    alrededor de esa hora y les planificaría avisos que la limpieza de este
    escenario no borra. Es el único campo que se toca, y es volátil ya en la pata 1.
    """
    origen = datetime.fromisoformat(eventos[0]["created_at"])
    return [
        {**e, "created_at": (BASE + (datetime.fromisoformat(e["created_at"]) - origen)).isoformat()}
        for e in eventos
    ]


@pytest.fixture
def esc(scenario: _Scenario) -> Iterator[_Escena]:  # noqa: F811
    e = _Escena(scenario)
    scenario.seed_config()
    yield e


def _gabinete(esc: _Escena, eventos: list[dict]) -> tuple[GatewayCtx, str]:
    """El inmueble del gabinete, con UN teléfono registrado (sin él no hay push).

    El registro se da de alta con la identidad que el vector trae —el código de
    inquilino y de sitio del gabinete—, así que `check_identity` compara contra
    el payload tal cual salió del Pi, sin reescribirlo.
    """
    conn = esc.conn
    sitio = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s,%s,%s,'Sitio E2E T-9.02', ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
        (sitio, esc.sc.tenant, f"E2E-{sitio[:8]}", SRC_LON, SRC_LAT),
    )
    token = str(uuid.uuid4())
    # [T-9.11 · D-39] El teléfono es de la BRIGADA: el umbral local solo despierta a
    # los roles de `movement_alert`, y la escalada a SASMEX, a todo el edificio.
    conn.execute(
        "INSERT INTO push_tokens (push_token_id, tenant_id, user_sub, platform, token, "
        "site_id, role) VALUES (%s,%s,%s,'android',%s,%s,'brigadista')",
        (token, esc.sc.tenant, str(uuid.uuid4()), f"tok-{token}", sitio),
    )
    conn.commit()
    ctx = GatewayCtx(
        gateway_id=uuid.uuid4(),
        gateway_serial="gw-t902-e2e",
        iot_thing="gw-t902-e2e",
        tenant_id=uuid.UUID(esc.sc.tenant),
        tenant_code=eventos[0]["tenant_id"],
        site_id=uuid.UUID(sitio),
        site_code=eventos[0]["site_id"],
        sensors={},
    )
    return ctx, sitio


def _ingerir(esc: _Escena, evento: dict, ctx: GatewayCtx) -> None:
    """Lo que hace el worker con cada mensaje de `takab/events`: contrato y handler."""
    clase = discriminate("local_event", evento)
    assert clase == "local_event"
    validate(clase, evento)  # lo primero que toca el mensaje en la nube
    assert handle_local_event(esc.conn, evento, META, ctx).is_ok
    esc.conn.commit()


def _incidente(esc: _Escena, evento: dict) -> dict:
    filas = esc.conn.execute(
        "SELECT incident_id, trigger, opened_trigger, severity, state, summary "
        "FROM incidents WHERE event_uuid = %s",
        (uuid.UUID(evento["event_id"]),),
    ).fetchall()
    assert len(filas) == 1, "un episodio del gabinete es UN incidente (T-7.49)"
    return filas[0]


def _pasada(esc: _Escena, en: datetime) -> None:
    run_notify_pass(esc.conn, Settings(), {**_providers(), "push": esc.push}, now=en)


def test_el_vector_es_el_empate_que_motiva_la_ficha() -> None:
    """Guardia del arnés: si el vector deja de describir el empate, esta pata
    probaría otra cosa en verde. Umbral local hasta evacuar y, DESPUÉS, SASMEX en
    el mismo tier y el mismo episodio."""
    eventos = _vector()
    assert len({e["event_id"] for e in eventos}) == 1
    assert eventos[-1]["source"] == "sasmex"
    assert all(e["source"] == "local_threshold" for e in eventos[:-1])
    assert eventos[-2]["tier"] == eventos[-1]["tier"] == "evacuate_or_hold"


def test_e2e_el_SASMEX_del_gabinete_escala_el_incidente_y_avisa_a_todo_el_edificio(
    esc: _Escena,
) -> None:
    """CRITERIO de T-9.02 + T-9.03 sobre el mensaje REAL del gabinete.

    1. El umbral abre el incidente como `local_threshold`: una estación sola
       sólo ADVIERTE, y el orquestador planifica el push de advertencia.
    2. Llega el SASMEX —el mismo episodio, el mismo tier—: el disparo sube a
       `sasmex` sin reescribir la apertura, y el incidente pasa a autorizar.
    3. La siguiente pasada deja `alert_escalated` en la bitácora y un push
       CRISIS nuevo, a TODO el edificio: el teléfono dormido se entera.
    """
    eventos = _rebasado(_vector())
    *umbrales, sasmex = eventos
    ctx, _sitio = _gabinete(esc, eventos)
    settings = Settings()

    for evento in umbrales:
        _ingerir(esc, evento, ctx)
    antes = _incidente(esc, sasmex)
    assert (antes["trigger"], antes["severity"]) == ("local_threshold", "critical")
    assert not autoriza_evacuacion(antes["trigger"], None, settings.quorum_min_nodes)

    _pasada(esc, BASE.replace(second=1))
    incidente = str(antes["incident_id"])
    assert [j["target"].get("autoriza") for j in esc.push_de_incidente(incidente)] == [False], (
        "el push de advertencia tenía que planificarse diciendo que NO autorizaba evacuar"
    )
    assert len(esc.push.entregas) == 1
    assert esc.escaladas(incidente) == []

    _ingerir(esc, sasmex, ctx)
    despues = _incidente(esc, sasmex)
    assert despues["trigger"] == "sasmex", (
        "el SASMEX del gabinete no subió el disparo: el ocupante no vería la orden de evacuar"
    )
    assert despues["opened_trigger"] == "local_threshold", "la apertura no se reescribe"
    assert autoriza_evacuacion(despues["trigger"], None, settings.quorum_min_nodes)

    _pasada(esc, BASE.replace(second=5))
    escaladas = esc.escaladas(incidente)
    assert len(escaladas) == 1, "la escalada no dejó rastro en la bitácora del incidente"
    assert escaladas[0]["payload"]["from_trigger"] == "local_threshold"
    assert escaladas[0]["payload"]["to_trigger"] == "sasmex"
    jobs = esc.push_de_escalada(incidente)
    assert len(jobs) == 1, "la escalada no encoló el push de evacuar"
    assert jobs[0]["action_id"] == escaladas[0]["action_id"]
    assert jobs[0]["target"]["push_class"] == PUSH_CLASS_CRISIS
    assert "roles" not in jobs[0]["target"], "el push de evacuar va a TODO el edificio"
    assert jobs[0]["status"] == "sent"
    assert len(esc.push.entregas) == 2, "el push de evacuar no llegó a salir hacia el proveedor"
