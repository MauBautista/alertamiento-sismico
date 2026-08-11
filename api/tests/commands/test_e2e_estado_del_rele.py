"""[T-2.116] PATA 2 DEL E2E — el estado del relé sobrevive al ingest.

La spec móvil §2.2 (`takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md:536`)
dice, literalmente:

    «Silenciar sirena» es una **retirada de la demanda del canal manual** en el
    arbitraje del edge — si otra demanda activa (alerta vigente) mantiene la
    sirena, la UI lo explica («La sirena permanece activa por alerta vigente»)
    en lugar de fingir éxito: el resultado real llega en el `command_ack` con el
    estado recalculado del relé.

Y su criterio de aceptación: «silenciar durante alerta activa NO apaga la sirena
y la UI comunica el porqué (ack con estado recalculado)».

`handle_command_ack` copiaba a `commands.ack` una lista CERRADA de claves
—`channel, action, success, latency_s, executed_at, detail, results`— así que un
campo nuevo del gabinete se habría perdido en silencio aunque el edge lo mandara.

**EL PAYLOAD NO SE ESCRIBE AQUÍ A MANO.** Se lee de
`edge/tests/vectors/command_ack_siren_arbitrado.json`, que produce el gabinete
REAL en `edge/tests/test_estado_del_rele_en_el_acuse.py` (pata 1) y verifica
byte a byte contra esa misma corrida. Los dos venv no se ven —`import
takab_edge` desde api falla—, así que el vector es la costura entre las patas:
si el edge deja de emitir el campo, la pata 1 cae; si la nube deja de
persistirlo, cae ésta.

La pata 3 es `mobile/src/features/control/estadoDelRele.test.tsx`, que lee el
MISMO archivo y comprueba lo que la persona termina leyendo en la hoja.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import psycopg
import pytest

from conftest import GW_A, SITE_A, TENANT_A, use
from takab_api.contracts.loader import ContractError, discriminate, validate
from takab_api.contracts.meta import Meta
from takab_api.ingest.handlers import GatewayCtx, handle_command_ack

#: El acuse tal cual sale del gabinete real (pata 1 del E2E).
VECTOR = (
    Path(__file__).resolve().parents[3]
    / "edge"
    / "tests"
    / "vectors"
    / "command_ack_siren_arbitrado.json"
)

USER = "9e0aa000-0000-0000-0000-000000000001"
META = Meta(principal="SER-A", topic="takab/acks", ts_iot=1782000000000)


@pytest.fixture
def acuse_del_gabinete() -> dict:
    return json.loads(VECTOR.read_text())


def _ctx() -> GatewayCtx:
    return GatewayCtx(
        gateway_id=uuid.UUID(GW_A),
        gateway_serial="SER-A",
        iot_thing="SER-A",
        tenant_id=uuid.UUID(TENANT_A),
        tenant_code="A",
        site_id=uuid.UUID(SITE_A),
        site_code="site-a",
        sensors={},
    )


def _emitir_silenciar(conn: psycopg.Connection, nonce: str) -> str:
    """El comando tal cual lo emite la ruta táctica: `siren/deactivate`."""
    conn.execute("RESET ROLE")
    row = conn.execute(
        "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
        "action, nonce, expires_at) "
        "VALUES (%s,%s,%s,%s,'siren','deactivate',%s, now() + interval '30 seconds') "
        "RETURNING command_id",
        (TENANT_A, SITE_A, GW_A, USER, nonce),
    ).fetchone()
    return str(row[0])


def _ack_persistido(conn: psycopg.Connection, command_id: str) -> dict:
    conn.execute("RESET ROLE")
    return conn.execute("SELECT ack FROM commands WHERE command_id = %s", (command_id,)).fetchone()[
        0
    ]


# ------------------------------------------------------- el contrato compartido


def test_el_vector_del_gabinete_es_un_command_ack_valido(acuse_del_gabinete) -> None:
    """Lo que el edge emite entra por la puerta del ingest, no por la DLQ.

    `contracts/loader.validate` es lo primero que toca el mensaje: si el campo
    nuevo no estuviera en `shared/schemas/command_ack.schema.json`, el acuse del
    gabinete real acabaría en la cola de veneno en vez de en `commands.ack`.
    """
    assert discriminate("actuator_ack", acuse_del_gabinete) == "command_ack"
    validate("command_ack", acuse_del_gabinete)  # no lanza


def test_el_acuse_declara_lo_que_la_spec_pide(acuse_del_gabinete) -> None:
    """El vector NO es un mock amable: dice éxito Y sirena energizada a la vez.

    Es la combinación exacta de la spec §2.2 y la que ningún contrato podía
    expresar hasta esta ficha: la orden se ejecutó (`success`) y el relé NO se
    apagó (`channel_state.activated`), porque otra demanda lo sostiene.
    """
    assert acuse_del_gabinete["channel"] == "siren"
    assert acuse_del_gabinete["action"] == "deactivate"
    assert acuse_del_gabinete["success"] is True
    estado = acuse_del_gabinete["channel_state"]
    assert estado["activated"] is True
    assert estado["reason"] == "alert"
    assert estado["alert_latched"] is True


# ------------------------------------------------------------------ E2E · pata 2


def test_e2e_el_ingest_persiste_el_estado_recalculado_del_rele(
    seeded: psycopg.Connection, acuse_del_gabinete
) -> None:
    """CRITERIO 1 de la ficha, mitad nube: `handle_command_ack` lo persiste."""
    command_id = _emitir_silenciar(seeded, acuse_del_gabinete["nonce"])
    use(seeded, "takab_ingest")

    assert handle_command_ack(seeded, acuse_del_gabinete, META, _ctx()).is_ok

    ack = _ack_persistido(seeded, command_id)
    # Lo que ya se guardaba, intacto.
    assert ack["channel"] == "siren" and ack["action"] == "deactivate"
    assert ack["success"] is True
    # Y el campo que la spec exige, entero — no una bandera aplanada: la app
    # tiene que poder decir POR QUÉ sigue sonando, no sólo que sigue sonando.
    assert ack["channel_state"] == acuse_del_gabinete["channel_state"]
    assert ack["channel_state"]["activated"] is True
    assert ack["channel_state"]["reason"] == "alert"


def test_e2e_el_comando_queda_acked_aunque_la_sirena_siga_sonando(
    seeded: psycopg.Connection, acuse_del_gabinete
) -> None:
    """`acked` describe LA ORDEN; `channel_state`, EL RELÉ. Son dos cosas.

    Colapsarlas era el defecto: `status='acked'` sobre un `deactivate` se leía
    como «silenciada» en toda la cadena, incluida la derivación de
    `building_alarm` de T-2.106 («manda lo último que TOCÓ el relé»).
    """
    command_id = _emitir_silenciar(seeded, acuse_del_gabinete["nonce"])
    use(seeded, "takab_ingest")
    handle_command_ack(seeded, acuse_del_gabinete, META, _ctx())

    seeded.execute("RESET ROLE")
    estado = seeded.execute(
        "SELECT status FROM commands WHERE command_id = %s", (command_id,)
    ).fetchone()[0]
    assert estado == "acked"
    assert _ack_persistido(seeded, command_id)["channel_state"]["activated"] is True


def test_un_gabinete_viejo_no_inventa_estado_de_rele(seeded: psycopg.Connection) -> None:
    """Un Pi sin re-desplegar sigue acusando, y su acuse dice «no sé».

    ADITIVO de verdad: el campo ausente se persiste como `null`, que la app lee
    como «el gabinete no lo declara» y NUNCA como «el relé está en reposo».
    """
    viejo = {
        "kind": "command_ack",
        "command_id": "cid-viejo",
        "nonce": "n-viejo-0001",
        "channel": "siren",
        "action": "deactivate",
        "success": True,
        "latency_s": 0.12,
        "executed_at": "2026-08-10T12:00:00+00:00",
        "detail": "relay",
    }
    validate("command_ack", viejo)  # el schema 1.11.0 sigue aceptándolo
    command_id = _emitir_silenciar(seeded, viejo["nonce"])
    use(seeded, "takab_ingest")
    assert handle_command_ack(seeded, viejo, META, _ctx()).is_ok
    assert _ack_persistido(seeded, command_id)["channel_state"] is None


def test_un_estado_de_rele_malformado_no_entra(acuse_del_gabinete) -> None:
    """El contrato es el guardián: `channel_state` no es un saco de cualquier cosa."""
    roto = dict(acuse_del_gabinete)
    roto["channel_state"] = {"activated": "sí"}  # falta `channel`, tipo inválido
    with pytest.raises(ContractError):
        validate("command_ack", roto)


# ------------------------------------------- la otra mitad: la traza del incidente


EVENT_HEX = "b7a1c2d3e4f5460788990a1b2c3d4e5f"


def _incidente(conn: psycopg.Connection) -> str:
    conn.execute("RESET ROLE")
    row = conn.execute(
        "INSERT INTO incidents (event_uuid, tenant_id, site_id, opened_at, severity, trigger) "
        "VALUES (%s,%s,%s, now(), 'critical', 'sasmex') RETURNING incident_id",
        (uuid.UUID(EVENT_HEX), TENANT_A, SITE_A),
    ).fetchone()
    return str(row[0])


def test_la_traza_bms_guarda_el_rele_y_no_solo_el_verbo(
    seeded: psycopg.Connection, acuse_del_gabinete
) -> None:
    """[T-2.110] `siren_off` es LA ORDEN; `channel_state`, EL RELÉ.

    `handle_actuator_ack` mapea `(siren, deactivate) → siren_off` y esa fila se
    escribe IGUAL cuando el arbitraje descartó la orden: el gabinete ejecutó el
    retiro de la demanda y la sirena siguió sonando. Un consumidor que derive
    «la sirena está apagada» del `kind` se equivoca en el caso exacto de la
    spec, y era de ahí de donde el panel táctico iba a sacarlo.
    """
    from takab_api.ingest.handlers import handle_actuator_ack

    incident_id = _incidente(seeded)
    use(seeded, "takab_ingest")
    ack = {
        "channel": "siren",
        "action": "deactivate",
        "event_id": EVENT_HEX,
        "success": True,
        "latency_s": 0.12,
        "executed_at": "2026-08-10T12:00:00+00:00",
        "detail": "relay",
        "channel_state": acuse_del_gabinete["channel_state"],
    }
    validate("actuator_ack", ack)  # mismo schema 1.11.0, familia hermana
    assert handle_actuator_ack(seeded, ack, META, _ctx()).is_ok

    seeded.execute("RESET ROLE")
    kind, payload = seeded.execute(
        "SELECT kind, payload FROM incident_actions WHERE incident_id = %s",
        (incident_id,),
    ).fetchone()
    assert kind == "siren_off"  # la ORDEN que se ejecutó…
    assert payload["channel_state"]["activated"] is True  # …y el RELÉ, que no se apagó
