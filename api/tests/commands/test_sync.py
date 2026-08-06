"""Config sync firmada contra Postgres real (T-1.23 · B9).

Patrón _Scenario (tenant fresco + cleanup); publisher fake. La versión es
MONÓTONA por gateway y la pasada es idempotente (mismo payload ⇒ no republica).
La firma publicada se verifica con la firma propia — la paridad byte-idéntica
con el edge la garantizan los vectores compartidos (test_signing_vectors).
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.commands.keys import StaticKeyProvider
from takab_api.commands.publisher import PublishError
from takab_api.commands.signing import canonical_payload, sign_config
from takab_api.commands.sync import run_config_sync_pass
from takab_api.settings import Settings

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
KEY = "clave-sync-test"

EDGE_DOC = {"command_enabled": True, "command_ttl_s": 30.0}
# [T-2.31] El worker fusiona gateways.equipment DENTRO del doc firmado: el
# payload publicado siempre trae la clave 'equipment' (default DB = todo-true).
EQUIP_ALL = {
    "siren": True,
    "strobe": True,
    "gas_valve": True,
    "elevator": True,
    "door_retainer": True,
}
# [T-2.65] El doc firmado también transporta el ESTADO ADMINISTRATIVO del
# gabinete. Colapsado a DOS valores en el SQL a propósito: si viajara el
# `gateways.status` crudo (`provisioned`/`online`/`degraded`…), un valor nuevo
# tumbaría el DOCUMENTO ENTERO en el edge y el gabinete se quedaría sin umbrales.
MERGED_DOC = {**EDGE_DOC, "equipment": EQUIP_ALL, "cloud_admin_state": "active"}


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    return url.replace("postgresql+psycopg://", "postgresql://")


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        if self.fail:
            raise PublishError("iot caído (simulado)")
        self.published.append((topic, json.loads(payload)))


class _Scenario:
    def __init__(self, conn: psycopg.Connection, tenant: str) -> None:
        self.conn = conn
        self.tenant = tenant
        self.site = str(uuid.uuid4())
        self.gateway = str(uuid.uuid4())
        self.thing = f"gw-sync-{self.gateway[:8]}"

    def seed_gateway(self, *, iot_thing: str | None = None, equipment: dict | None = None) -> None:
        self.conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(-100.9,11.9),4326)::geography)",
            (self.site, self.tenant, f"CS-{self.site[:8]}"),
        )
        self.conn.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
            "VALUES (%s,%s,%s,%s,%s)",
            (
                self.gateway,
                self.tenant,
                self.site,
                f"SER-{self.gateway[:8]}",
                iot_thing if iot_thing is not None else self.thing,
            ),
        )
        if equipment is not None:
            self.conn.execute(
                "UPDATE gateways SET equipment = %s::jsonb WHERE gateway_id = %s",
                (json.dumps(equipment), self.gateway),
            )
        self.conn.commit()

    def set_equipment(self, equipment: dict) -> None:
        self.conn.execute(
            "UPDATE gateways SET equipment = %s::jsonb WHERE gateway_id = %s",
            (json.dumps(equipment), self.gateway),
        )
        self.conn.commit()

    def set_status(self, status: str) -> None:
        """Espeja lo ÚNICO que hacen `retire_gateway`/`restore_gateway`: mover
        `gateways.status`. Ninguno de los dos publica nada ni toca
        `gateway_config_state` — el aviso tiene que salir por el config sync."""
        self.conn.execute(
            "UPDATE gateways SET status = %s WHERE gateway_id = %s", (status, self.gateway)
        )
        self.conn.commit()

    def retire(self) -> None:
        self.set_status("retired")

    def restore(self) -> None:
        self.set_status("provisioned")

    def deactivate_rule_sets(self) -> None:
        """Deja al gateway SIN rule_set resoluble (no hace falta retirar el sitio:
        `retire_site` jamás toca `rule_sets`)."""
        self.conn.execute(
            "UPDATE rule_sets SET is_active = false WHERE tenant_id = %s", (self.tenant,)
        )
        self.conn.commit()

    def audit_meta(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT meta FROM audit_log WHERE verb = 'config_published' AND object = %s "
            "ORDER BY audit_id",
            (f"gateway:{self.gateway}",),
        ).fetchall()
        return [r["meta"] for r in rows]

    def activate_rule_set(self, config: dict, *, version: int = 1) -> None:
        self.conn.execute(
            "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, "
            "is_active, config) VALUES (%s,'tenant',%s,%s,true,%s::jsonb)",
            (self.tenant, self.tenant, version, json.dumps(config)),
        )
        self.conn.commit()

    def state(self) -> dict | None:
        return self.conn.execute(
            "SELECT version, payload, sig FROM gateway_config_state WHERE gateway_id = %s",
            (self.gateway,),
        ).fetchone()

    def mine(self, publisher: _FakePublisher) -> list[tuple[str, dict]]:
        return [(t, p) for t, p in publisher.published if t == f"takab/cfg/{self.thing}"]


@pytest.fixture
def scenario() -> Iterator[_Scenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    tenant = str(uuid.uuid4())
    try:
        conn.execute("SET ROLE takab_ingest")
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Sync Test')",
            (tenant, tenant[:8]),
        )
        conn.commit()
        yield _Scenario(conn, tenant)
    finally:
        _cleanup(conn, tenant)
        conn.close()


def _cleanup(conn: psycopg.Connection, tenant: str) -> None:
    conn.rollback()
    conn.execute("RESET ROLE")
    try:
        conn.execute("DELETE FROM gateway_config_state WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM commands WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM gateways WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM rule_sets WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sites WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant,))
        conn.commit()
    except psycopg.Error:
        conn.rollback()


def _settings() -> Settings:
    return Settings()


def _keys(scenario: _Scenario, key: str = KEY) -> StaticKeyProvider:
    """Clave per-gateway (T-1.38): solo el thing del escenario firma con KEY."""
    return StaticKeyProvider({scenario.thing: key})


def test_activation_publishes_signed_v1(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()

    published = run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    assert scenario.gateway in published
    mine = scenario.mine(publisher)
    assert len(mine) == 1
    envelope = mine[0][1]
    assert envelope["kind"] == "config_update"
    assert envelope["version"] == 1
    # [T-2.31] El doc firmado viaja FUSIONADO con gateways.equipment.
    assert envelope["payload"] == MERGED_DOC
    expected = sign_config(KEY.encode(), canonical_payload(MERGED_DOC), 1)
    assert envelope["sig"] == expected
    state = scenario.state()
    assert state["version"] == 1 and state["payload"] == MERGED_DOC


def test_rerun_without_change_is_idempotent(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))
    assert len(scenario.mine(publisher)) == 1
    assert scenario.state()["version"] == 1


def test_config_change_bumps_monotonic_version(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    new_doc = {**EDGE_DOC, "command_ttl_s": 20.0}
    scenario.activate_rule_set({"edge": new_doc}, version=2)
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    mine = scenario.mine(publisher)
    assert [p["version"] for _t, p in mine] == [1, 2]
    assert mine[1][1]["payload"] == {
        **new_doc,
        "equipment": EQUIP_ALL,
        "cloud_admin_state": "active",
    }
    assert scenario.state()["version"] == 2


def test_equipment_rides_merged_into_the_signed_payload(scenario: _Scenario) -> None:
    """[T-2.31] El equipamiento del gateway viaja DENTRO del doc firmado (una
    firma cubre config + equipment; el edge no puede recibir uno sin el otro)."""
    partial = {**EQUIP_ALL, "gas_valve": False, "elevator": False}
    scenario.seed_gateway(equipment=partial)
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()

    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    mine = scenario.mine(publisher)
    assert len(mine) == 1
    payload = mine[0][1]["payload"]
    assert payload["equipment"] == partial
    expected = sign_config(KEY.encode(), canonical_payload(payload), 1)
    assert mine[0][1]["sig"] == expected


def test_equipment_edit_triggers_republish_with_bumped_version(scenario: _Scenario) -> None:
    """[T-2.31] Editar SOLO el equipamiento re-publica (IS DISTINCT del estado);
    el re-run posterior vuelve a ser idempotente."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    scenario.set_equipment({**EQUIP_ALL, "door_retainer": False})
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    mine = scenario.mine(publisher)
    assert [p["version"] for _t, p in mine] == [1, 2]
    assert mine[1][1]["payload"]["equipment"]["door_retainer"] is False
    assert scenario.state()["version"] == 2


def test_ruleset_without_edge_key_publishes_nothing(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.activate_rule_set({"quorum": {"min_nodes": 3}})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))
    assert scenario.mine(publisher) == []
    assert scenario.state() is None


def test_gateway_without_thing_is_skipped(scenario: _Scenario) -> None:
    scenario.seed_gateway(iot_thing=None)  # sin identidad IoT → no comandable
    scenario.conn.execute(
        "UPDATE gateways SET iot_thing = NULL WHERE gateway_id = %s", (scenario.gateway,)
    )
    scenario.conn.commit()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))
    assert publisher.published == [] or scenario.state() is None


def test_gateway_without_key_is_fail_closed(scenario: _Scenario) -> None:
    """Sin clave PARA ESE gateway (T-1.38): no publica ni quema versión."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    published = run_config_sync_pass(scenario.conn, _settings(), publisher, StaticKeyProvider({}))
    assert published == []
    assert scenario.mine(publisher) == []
    assert scenario.state() is None


def test_mixed_fleet_signs_only_gateways_with_key(scenario: _Scenario) -> None:
    """Per-gateway (T-1.38): publica solo a quien tiene clave; el resto entra
    cuando la suya aparece (provisión tardía), con SU clave y versión propia."""
    scenario.seed_gateway()
    site2, gw2 = str(uuid.uuid4()), str(uuid.uuid4())
    thing2 = f"gw-sync2-{gw2[:8]}"
    scenario.conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s,%s,%s,'S2', ST_SetSRID(ST_MakePoint(-100.8,11.8),4326)::geography)",
        (site2, scenario.tenant, f"CS2-{site2[:8]}"),
    )
    scenario.conn.execute(
        "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
        "VALUES (%s,%s,%s,%s,%s)",
        (gw2, scenario.tenant, site2, f"SER2-{gw2[:8]}", thing2),
    )
    scenario.conn.commit()
    scenario.activate_rule_set({"edge": EDGE_DOC})

    publisher = _FakePublisher()
    published = run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))
    assert published == [scenario.gateway]
    assert f"takab/cfg/{thing2}" not in [t for t, _ in publisher.published]
    st2 = scenario.conn.execute(
        "SELECT 1 FROM gateway_config_state WHERE gateway_id = %s", (gw2,)
    ).fetchone()
    assert st2 is None  # el candidato sin clave no quema versión

    both = StaticKeyProvider({scenario.thing: KEY, thing2: "clave-2"})
    published2 = run_config_sync_pass(scenario.conn, _settings(), publisher, both)
    assert published2 == [gw2]  # solo el pendiente; el otro ya estaba al día
    env2 = next(p for t, p in publisher.published if t == f"takab/cfg/{thing2}")
    assert env2["version"] == 1
    assert env2["sig"] == sign_config(b"clave-2", canonical_payload(MERGED_DOC), 1)


def test_publish_failure_keeps_candidate_for_retry(scenario: _Scenario) -> None:
    """El fallo de publish NO quema versión ni estado: se reintenta después."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    failing = _FakePublisher(fail=True)
    assert run_config_sync_pass(scenario.conn, _settings(), failing, _keys(scenario)) == []
    assert scenario.state() is None

    ok = _FakePublisher()
    assert run_config_sync_pass(scenario.conn, _settings(), ok, _keys(scenario)) == [
        scenario.gateway
    ]
    assert scenario.mine(ok)[0][1]["version"] == 1


# --- T-2.65 · el sobre firmado transporta el estado administrativo -----------
#
# Opción (A) ratificada 2026-08-05: un gabinete retirado en la nube SIGUE
# PROTEGIENDO y lo DECLARA. El retiro es un acto administrativo que viaja por la
# nube; que apagara la protección convertiría un clic de inventario en la
# desprotección física de un edificio con gente dentro (reglas de oro 1 y 2).
#
# El defecto que cierran estos tests: `WHERE g.status <> 'retired'` sacaba al
# gabinete de la lista de candidatos ANTES de poder avisarle, así que el aviso no
# salía nunca. El 2026-08-04 `gw-dev-0001` siguió latiendo invisible y lo detectó
# un operador preguntando por su estación, no el sistema.

#: Doc con umbrales REALES: lo que un sobre de retiro jamás debe borrar.
RICH_DOC = {
    **EDGE_DOC,
    "thresholds": {"pga_trip_g": 0.15, "pga_watch_g": 0.04},
}


def _merged(doc: dict, admin: str = "active", equipment: dict | None = None) -> dict:
    return {**doc, "equipment": equipment or EQUIP_ALL, "cloud_admin_state": admin}


def test_retiro_publica_un_sobre_que_declara_la_baja_sin_tocar_los_umbrales(
    scenario: _Scenario,
) -> None:
    """CRITERIO 2: el sobre del retiro se publica ANTES de sacar al gabinete de
    la lista de candidatos, y conserva los umbrales con los que protege."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": RICH_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    scenario.retire()
    published = run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    assert published == [scenario.gateway]
    mine = scenario.mine(publisher)
    assert [p["version"] for _t, p in mine] == [1, 2]
    envelope = mine[1][1]
    # Ningún topic nuevo (CRITERIO 1): viaja en el sobre firmado de siempre.
    assert mine[1][0] == f"takab/cfg/{scenario.thing}"
    assert envelope["kind"] == "config_update"
    assert envelope["payload"] == _merged(RICH_DOC, "retired")
    # Lo que de verdad importa: sigue protegiendo con SUS umbrales, no con defaults.
    assert envelope["payload"]["thresholds"] == {"pga_trip_g": 0.15, "pga_watch_g": 0.04}
    assert envelope["payload"]["command_enabled"] is True
    expected = sign_config(KEY.encode(), canonical_payload(envelope["payload"]), 2)
    assert envelope["sig"] == expected


def test_el_sobre_del_retiro_sale_exactamente_una_vez(scenario: _Scenario) -> None:
    """Avisado el gabinete, sale del flujo de config: no se republica en bucle."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))
    scenario.retire()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    assert run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario)) == []
    assert run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario)) == []
    assert [p["version"] for _t, p in scenario.mine(publisher)] == [1, 2]
    assert scenario.state()["version"] == 2


def test_nunca_publicado_y_retirado_recibe_su_sobre_de_baja(scenario: _Scenario) -> None:
    """El retiro llega ANTES de la primera publicación: el aviso sale igual."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    scenario.retire()
    publisher = _FakePublisher()

    assert run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario)) == [
        scenario.gateway
    ]
    mine = scenario.mine(publisher)
    assert len(mine) == 1
    assert mine[0][1]["payload"]["cloud_admin_state"] == "retired"


def test_restaurar_publica_el_estado_activo_con_version_mayor(scenario: _Scenario) -> None:
    """CRITERIO 5 (mitad nube): restaurar re-publica 'active'. El contador de
    versión SOBREVIVE al retiro — si `gateway_config_state` se borrara, la
    versión reiniciaría en 1 y el edge la rechazaría por replay PARA SIEMPRE."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": RICH_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))
    scenario.retire()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    scenario.restore()
    assert run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario)) == [
        scenario.gateway
    ]

    mine = scenario.mine(publisher)
    assert [p["version"] for _t, p in mine] == [1, 2, 3]  # monótona, jamás reinicia
    assert mine[2][1]["payload"] == _merged(RICH_DOC, "active")
    assert scenario.state()["version"] == 3
    # Y no vuelve a hablar hasta que algo cambie de verdad.
    assert run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario)) == []


def test_retirado_sin_rule_set_resoluble_conserva_los_umbrales_ya_publicados(
    scenario: _Scenario,
) -> None:
    """El guardarraíl del COALESCE. `apply_signed_update` es REEMPLAZO TOTAL: un
    sobre de retiro sin la base del último doc apagaría `command_enabled` (la
    actuación por quórum) y devolvería los umbrales a la banda hospital."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": RICH_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    scenario.deactivate_rule_sets()  # ya no hay rule_set activo que resolver
    scenario.retire()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    mine = scenario.mine(publisher)
    assert len(mine) == 2
    payload = mine[1][1]["payload"]
    assert payload == _merged(RICH_DOC, "retired")
    assert payload["thresholds"] == {"pga_trip_g": 0.15, "pga_watch_g": 0.04}
    assert payload["command_enabled"] is True


def test_sin_rule_set_y_sin_payload_previo_no_publica_nada(scenario: _Scenario) -> None:
    """No hay NADA seguro que enviar: saltar, jamás mandar un doc vacío. Un `{}`
    de reemplazo total borraría los umbrales de hardware VIVO."""
    scenario.seed_gateway()
    scenario.retire()
    publisher = _FakePublisher()

    assert run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario)) == []
    assert scenario.mine(publisher) == []
    assert scenario.state() is None


def test_activo_sin_rule_set_resoluble_sigue_sin_recibir_nada(scenario: _Scenario) -> None:
    """El mismo guardarraíl, del lado que más duele: un gabinete ACTIVO cuyo
    rule_set no resuelve NO puede convertirse en candidato por el cambio de
    T-2.65 (el radio de explosión del worker es toda la flota de TODOS los
    tenants: corre como `takab_ingest`, BYPASSRLS)."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"quorum": {"min_nodes": 3}})
    publisher = _FakePublisher()

    assert run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario)) == []
    assert scenario.state() is None


def test_retirado_con_publish_fallido_reintenta_y_acaba_avisando(scenario: _Scenario) -> None:
    """El sobre del retiro hereda el fail-closed: IoT caído no quema la versión
    ni consume el único aviso — el gabinete sigue candidato hasta que llegue."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    scenario.retire()
    failing = _FakePublisher(fail=True)
    assert run_config_sync_pass(scenario.conn, _settings(), failing, _keys(scenario)) == []
    assert scenario.state()["version"] == 1  # versión intacta

    assert run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario)) == [
        scenario.gateway
    ]
    assert scenario.mine(publisher)[1][1]["payload"]["cloud_admin_state"] == "retired"


def test_la_auditoria_declara_por_que_salio_ese_sobre(scenario: _Scenario) -> None:
    """Un sobre de retiro es un acto con consecuencia física: la bitácora de
    compliance tiene que poder leerse sin reconstruir el payload."""
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    publisher = _FakePublisher()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))
    scenario.retire()
    run_config_sync_pass(scenario.conn, _settings(), publisher, _keys(scenario))

    metas = scenario.audit_meta()
    assert [m["version"] for m in metas] == [1, 2]
    assert [m["admin_state"] for m in metas] == ["active", "retired"]


def test_expires_stale_pending_commands(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.conn.execute(
        "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
        "action, nonce, issued_at, expires_at) "
        "VALUES (%s,%s,%s,%s,'siren','activate','n-sync-exp', now() - interval '2 min', "
        "now() - interval '1 min')",
        (scenario.tenant, scenario.site, scenario.gateway, str(uuid.uuid4())),
    )
    scenario.conn.commit()
    # La expiración corre aunque NINGÚN gateway tenga clave (independiente de firma).
    run_config_sync_pass(scenario.conn, _settings(), _FakePublisher(), StaticKeyProvider({}))
    row = scenario.conn.execute("SELECT status FROM commands WHERE nonce = 'n-sync-exp'").fetchone()
    assert row["status"] == "expired"


# --- T-2.65 · el retiro despierta al worker (SLA del aviso) ------------------


def _notifies(conn: psycopg.Connection, do: object) -> list[str]:
    """Escucha `takab_live` en una conexión APARTE mientras `do()` commitea."""
    import select

    listener = psycopg.connect(_dsn(), autocommit=True)
    try:
        listener.execute("LISTEN takab_live")
        do()  # type: ignore[operator]
        select.select([listener], [], [], 3.0)
        gen = listener.notifies(timeout=0.2)
        return [n.payload for n in gen]
    finally:
        listener.close()


def test_retirar_un_gabinete_despierta_al_worker(scenario: _Scenario) -> None:
    """Sin el trigger de la migración 0027 esto salía por el poll de respaldo:
    hasta 30 s entre el clic en la consola y el aviso en el panel del gabinete.

    Medido en vivo antes de arreglarlo: `UPDATE gateways SET status='retired'` no
    emitía NADA (el único trigger sobre `gateways` era el de `equipment`, 0022).
    """
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})

    cargas = _notifies(scenario.conn, scenario.retire)

    assert any(str(scenario.gateway) in c for c in cargas), (
        f"retirar no despertó al worker de config sync: {cargas}"
    )
    assert any('"t": "rule_set"' in c or '"t":"rule_set"' in c for c in cargas)


def test_restaurar_un_gabinete_tambien_despierta_al_worker(scenario: _Scenario) -> None:
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    scenario.retire()

    cargas = _notifies(scenario.conn, scenario.restore)

    assert any(str(scenario.gateway) in c for c in cargas)


def test_el_vaiven_online_offline_NO_despierta_al_worker_de_config(
    scenario: _Scenario,
) -> None:
    """El `WHEN` del trigger es estrecho A PROPÓSITO.

    `gateways.status` no solo lo mueven retire/restore: la ingesta lo reescribe
    con CADA LWT de conexión y desconexión (`ingest/handlers.py::_STATUS_SQL`).
    Un trigger sobre cualquier transición despertaría al worker de config en cada
    flap de MQTT de CADA gabinete de la plataforma, para no publicar nada.
    """
    scenario.seed_gateway()
    scenario.activate_rule_set({"edge": EDGE_DOC})
    scenario.set_status("online")

    cargas = _notifies(scenario.conn, lambda: scenario.set_status("offline"))

    assert not any(str(scenario.gateway) in c for c in cargas), (
        f"un flap de MQTT despertó al worker de config sync: {cargas}"
    )
