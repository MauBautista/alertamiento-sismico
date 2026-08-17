"""[T-2.147.c · D-05] Si la brigada no acusa, se avisa al SOC — y NO al edificio.

`D-05` eligió (B): push solo a los tácticos. El agujero conocido de (B) es que la
brigada no conteste, y la pregunta de seguimiento se contestó así: **avisar al
SOC**, no escalar al edificio.

La razón está escrita en la decisión y es la que gobierna este módulo: escalar
automáticamente a todo el mundo reintroduce (A) por la puerta de atrás, solo que
dos minutos después. Avisar al SOC pone a **un humano con contexto** a decidir si
esto merece despertar a 400 personas. **Una máquina no debería tomar esa decisión
por un timeout.**

QUÉ CUENTA COMO «RESPONDIÓ»
----------------------------
Dos cosas distintas, y las dos apagan el aviso porque las dos significan que
alguien ya está mirando:

  · un **acuse de la brigada** (`tactical_ack`, T-2.147.b);
  · o que el **SOC ya haya acusado el incidente** (`state <> 'open'`) — si ya lo
    tienen delante, avisarles de que nadie lo tiene delante es ruido.

Que `147.b` NO mueva el estado del incidente es lo que hace que estas dos
condiciones sigan siendo independientes; si lo moviera, el acuse de la brigada
apagaría el aviso por la razón equivocada.

LA TRAMPA QUE ESTE ARCHIVO VIGILA
----------------------------------
`test_la_ventana_del_escaneo_es_mas_ancha_que_el_plazo`. El worker escanea con
una ventana (`lookback`) y el aviso solo es elegible **después** del plazo. Si la
ventana fuera más estrecha que el plazo, el incidente saldría de ella **antes**
de volverse elegible y el aviso **no saltaría jamás** — en verde, sin un solo
error, y sin que nadie lo supiera hasta que una brigada no contestara de verdad.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from takab_api.notify.orchestrator import run_notify_pass
from takab_api.settings import Settings
from tests.notify.test_orchestrator import (  # noqa: F401
    BASE,
    INSPECTOR_CONFIG,
    _providers,
    _Scenario,
    scenario,
)

PLAZO_S = 120.0
TACTICO = "brigadista"


def _ajustes(**over) -> Settings:
    return Settings(panic_tactical_ack_timeout_s=PLAZO_S, **over)


def _panico(sc: _Scenario, *, hace_s: float) -> str:
    """Un pánico abierto hace `hace_s` segundos (relativo a BASE)."""
    return sc.seed_incident(
        trigger="manual", severity="critical", opened_at=BASE - timedelta(seconds=hace_s)
    )


def _acusa(sc: _Scenario, incident_id: str, user: str = "brigada-1") -> None:
    sc.conn.execute(
        "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor) "
        "VALUES (%s,%s,'tactical_ack',%s)",
        (incident_id, sc.tenant, f"user:{user}"),
    )
    sc.conn.commit()


def _avisos(sc: _Scenario, incident_id: str) -> list[dict]:
    return sc.conn.execute(
        "SELECT actor, payload FROM incident_actions "
        "WHERE incident_id = %s AND kind = 'tactical_ack_timeout' ORDER BY ts",
        (incident_id,),
    ).fetchall()


def _emails_del_aviso(sc: _Scenario, incident_id: str) -> list[dict]:
    """Solo los correos ANCLADOS al aviso de timeout.

    OJO, y es una consecuencia real de `D-11`: un incidente `manual` también
    dispara la **cascada normal** del tenant (webhook/whatsapp/sms/email a los
    destinos operativos configurados). Contar «todos los emails del incidente»
    mezclaría las dos cosas y este test mediría la cascada en vez del aviso.
    """
    return sc.conn.execute(
        "SELECT j.job_id FROM notification_jobs j "
        "JOIN incident_actions a ON a.action_id = j.action_id "
        "WHERE j.incident_id = %s AND j.channel = 'email' "
        "  AND a.kind = 'tactical_ack_timeout'",
        (incident_id,),
    ).fetchall()


# --- El aviso salta ----------------------------------------------------------


def test_sin_acuse_y_pasado_el_plazo_se_avisa_al_SOC(scenario: _Scenario) -> None:  # noqa: F811
    """El caso que `D-05` compró: la brigada no contestó y alguien tiene que saberlo."""
    incident = _panico(scenario, hace_s=PLAZO_S + 30)
    scenario.seed_config(INSPECTOR_CONFIG)

    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE)

    avisos = _avisos(scenario, incident)
    assert len(avisos) == 1, f"se esperaba un aviso al SOC, hay {len(avisos)}"
    assert avisos[0]["actor"] == "system", "el aviso no lo levanta una persona: lo levanta el plazo"
    assert _emails_del_aviso(scenario, incident), (
        "el aviso quedó en el timeline pero no salió del sistema"
    )


def test_el_aviso_NO_escala_al_edificio(scenario: _Scenario) -> None:  # noqa: F811
    """LA PROPIEDAD QUE JUSTIFICA LA DECISIÓN, no solo el código.

    `D-05` descartó despertar al edificio entero. Escalar a todos por un timeout
    reintroduce esa opción con dos minutos de retraso — y peor, sin que nadie la
    haya decidido: la habría tomado un temporizador.
    """
    incident = _panico(scenario, hace_s=PLAZO_S + 30)
    scenario.seed_config(INSPECTOR_CONFIG)

    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE)

    push = [j for j in scenario.jobs(incident) if j["channel"] == "push"]
    clases = {(j["target"] or {}).get("push_class") for j in push}
    roles = [set((j["target"] or {}).get("roles") or []) for j in push]
    assert all(r and "occupant" not in r for r in roles), (
        f"el timeout amplió el círculo del push a {roles}: eso es escalar al "
        "edificio por un temporizador, que es justo lo que D-05 descartó"
    )
    assert clases <= {"PANIC"}, f"apareció una clase de push nueva tras el timeout: {clases}"


# --- El aviso NO salta -------------------------------------------------------


def test_antes_del_plazo_no_se_avisa(scenario: _Scenario) -> None:  # noqa: F811
    """No-vacuidad: el plazo es lo que dispara, no el mero hecho de existir."""
    incident = _panico(scenario, hace_s=PLAZO_S / 2)
    scenario.seed_config(INSPECTOR_CONFIG)

    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE)

    assert _avisos(scenario, incident) == [], (
        "se avisó al SOC antes de que la brigada tuviera tiempo de contestar"
    )


def test_con_acuse_de_la_brigada_no_se_avisa(scenario: _Scenario) -> None:  # noqa: F811
    """Alguien respondió: avisar al SOC de que nadie respondió sería falso."""
    incident = _panico(scenario, hace_s=PLAZO_S + 30)
    scenario.seed_config(INSPECTOR_CONFIG)
    _acusa(scenario, incident)

    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE)

    assert _avisos(scenario, incident) == [], (
        "se avisó al SOC pese a que un táctico había acusado: el aviso diría una "
        "mentira sobre una brigada que sí respondió"
    )


def test_si_el_SOC_ya_acuso_el_incidente_no_se_le_avisa(scenario: _Scenario) -> None:  # noqa: F811
    """Ya lo tienen delante. Avisarles de que nadie lo tiene delante es ruido.

    Y el ruido en un SOC no es inocuo: es lo que enseña a ignorar la bandeja.
    """
    incident = _panico(scenario, hace_s=PLAZO_S + 30)
    scenario.seed_config(INSPECTOR_CONFIG)
    scenario.conn.execute(
        "UPDATE incidents SET state = 'acked' WHERE incident_id = %s", (incident,)
    )
    scenario.conn.commit()

    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE)

    assert _avisos(scenario, incident) == []


def test_un_incidente_SISMICO_sin_acuse_no_dispara_este_aviso(scenario: _Scenario) -> None:  # noqa: F811
    """El plazo es del pánico, no de todo incidente.

    Un sismo ya tiene su propia cascada de notificación; meterle además este
    aviso duplicaría la página del SOC por el mismo hecho.
    """
    incident = scenario.seed_incident(
        trigger="sasmex", severity="critical", opened_at=BASE - timedelta(seconds=PLAZO_S + 30)
    )
    scenario.seed_config(INSPECTOR_CONFIG)

    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE)

    assert _avisos(scenario, incident) == []


def test_una_segunda_pasada_no_avisa_dos_veces(scenario: _Scenario) -> None:  # noqa: F811
    """Idempotencia. Sin ella el SOC recibe un correo por pasada del worker."""
    incident = _panico(scenario, hace_s=PLAZO_S + 30)
    scenario.seed_config(INSPECTOR_CONFIG)

    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE)
    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE)

    assert len(_avisos(scenario, incident)) == 1, "la segunda pasada volvió a avisar al SOC"
    assert len(_emails_del_aviso(scenario, incident)) == 1, "la segunda pasada encoló otro correo"


# --- LA TRAMPA -----------------------------------------------------------------


def test_la_ventana_del_escaneo_es_mas_ancha_que_el_plazo(scenario: _Scenario) -> None:  # noqa: F811
    """EL FALLO SILENCIOSO QUE ESTE MÓDULO PODÍA TENER Y NO TIENE.

    El worker escanea con una ventana (`lookback`) y el aviso solo es elegible
    **pasado el plazo**. Si la ventana fuera más estrecha que el plazo, el
    incidente saldría de ella ANTES de volverse elegible: el aviso no saltaría
    jamás, en verde y sin un solo error — y no se descubriría hasta que una
    brigada de verdad no contestara.

    Aquí el `lookback` es la MITAD del plazo, que es el caso patológico, y el
    aviso tiene que salir igual.
    """
    incident = _panico(scenario, hace_s=PLAZO_S + 30)
    scenario.seed_config(INSPECTOR_CONFIG)

    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE, lookback_s=PLAZO_S / 2)

    assert len(_avisos(scenario, incident)) == 1, (
        "con `lookback` más estrecho que el plazo, el aviso al SOC NO salió: el "
        "incidente sale de la ventana antes de volverse elegible y la brigada "
        "ausente nunca se reporta"
    )


def test_un_panico_MUY_viejo_deja_de_avisarse(scenario: _Scenario) -> None:  # noqa: F811
    """La ventana es ancha, no infinita.

    Sin cota superior, restaurar una base de hace un mes dispararía un correo por
    cada pánico jamás atendido — y el SOC estrenaría el sistema con una bandeja
    llena de emergencias de otro año.
    """
    incident = _panico(scenario, hace_s=30 * 24 * 3600)
    scenario.seed_config(INSPECTOR_CONFIG)

    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE)

    assert _avisos(scenario, incident) == [], (
        "un pánico de hace un mes disparó el aviso: una restauración inundaría "
        "el SOC de emergencias viejas"
    )


def test_el_aviso_nombra_lo_que_el_operador_necesita_decidir(scenario: _Scenario) -> None:  # noqa: F811
    """El SOC tiene que poder decidir SIN abrir otra pantalla.

    Lo que se le pide es la decisión que la máquina no toma: ¿esto merece
    despertar al edificio? Para eso hace falta saber cuánto lleva sin respuesta y
    a cuánta gente se despertó.
    """
    incident = _panico(scenario, hace_s=PLAZO_S + 30)
    scenario.seed_config(INSPECTOR_CONFIG)

    run_notify_pass(scenario.conn, _ajustes(), _providers(), now=BASE)

    payload = _avisos(scenario, incident)[0]["payload"]
    assert "timeout_s" in payload, f"el aviso no dice cuánto plazo se dio: {payload}"
    assert payload.get("tactical_acks") == 0, (
        f"el aviso no declara cuántos acuses hubo (debería ser 0): {payload}"
    )
    assert str(uuid.UUID(str(payload["site_id"]))) == payload["site_id"], (
        "el aviso no nombra el inmueble: el operador no sabe a qué edificio mirar"
    )
