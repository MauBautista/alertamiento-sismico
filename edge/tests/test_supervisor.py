"""supervisor — ensamblaje, orden de dependencias y actuación SIN nube.

El test de "actuación completa con la nube apagada" cierra el DoD de la Fase E
(PLAN-MAESTRO §4, punto 6): P1/P2 probados, no declarados.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from simulators.rs4d import RS4DSimulator
from simulators.wr1 import WR1Simulator
from takab_edge.contracts import ActuatorChannel, AlertSource, Tier, TierDecision
from takab_edge.supervisor import ACKS_TOPIC, EVENTS_TOPIC, EdgeSupervisor

ALL_MODULES = {
    "seedlink",
    "signal",
    "buffer",
    "gpio",
    "rules",
    "actuators",
    "cloud",
    "health",
    "config",
    "security",
    "dispatch",  # T-1.23: consumidor de comandos/config firmados
    "backfill",  # T-1.25: ruta S3 del spool + evidencia offline
    "audio",  # A-6: voceo advisory (deshabilitado por default; gate de hardware)
    "drill",  # T-1.60: simulacro institucional (observador; cero relés)
    "telemetry",  # T-1.56: batcheo escalonado por tier de features
    "local_api",
}


def test_build_registers_all_modules(supervisor):
    assert {m.name for m in supervisor.modules()} == ALL_MODULES


def test_toposort_starts_dependencies_first(supervisor):
    order = [m.name for m in supervisor.modules()]
    for module in supervisor.modules():
        for dep in module.depends_on:
            assert order.index(dep) < order.index(module.name)


def test_all_modules_running_then_stopped(settings):
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.start()
    assert all(m.running for m in sup.modules())
    sup.stop()
    assert not any(m.running for m in sup.modules())


def _boom() -> None:
    raise RuntimeError("fallo de arranque simulado")


def test_noncritical_start_failure_keeps_life_path(settings, monkeypatch):
    """El dashboard LAN (no crítico) con el puerto ocupado NO tumba el gabinete:
    el reflejo SASMEX y la actuación siguen arriba (regla de oro 2)."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    monkeypatch.setattr(sup.local_api, "_on_start", _boom)

    sup.start()  # NO propaga: el módulo no-crítico se aísla

    assert sup.gpio.running, "el reflejo SASMEX debe seguir vivo"
    assert sup.rules.running and sup.actuators.running, "el camino de actuación sigue"
    assert not sup.local_api.running, "el módulo que falló queda sin arrancar"
    sup.stop()


def test_critical_start_failure_propagates(settings, monkeypatch):
    """Un módulo del camino de vida (gpio) que no arranca hace fail-fast: el
    gabinete crashea (systemd reinicia) en vez de correr mudo."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    monkeypatch.setattr(sup.gpio, "_on_start", _boom)

    with pytest.raises(RuntimeError):
        sup.start()


def test_life_path_modules_are_marked_critical(settings):
    """El núcleo de actuación (gpio/rules/actuators) es crítico; la coordinación no."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    critical = {m.name for m in sup.modules() if m.critical}
    assert critical == {"gpio", "rules", "actuators"}
    assert not sup.cloud.critical and not sup.local_api.critical


def test_disk_full_does_not_blind_detection(settings, monkeypatch):
    """Un buffer.append que lanza OSError (disco lleno) no debe impedir que las
    reglas evalúen el paquete: la detección va antes que la persistencia."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    sup.start()

    def _disk_full(_packet):
        raise OSError("ENOSPC: sin espacio en disco")

    monkeypatch.setattr(sup.buffer, "append", _disk_full)
    seen = {"rules": False}
    real_eval = sup.rules.evaluate_features

    def _spy(feature):
        seen["rules"] = True
        return real_eval(feature)

    monkeypatch.setattr(sup.rules, "evaluate_features", _spy)

    packet = next(
        RS4DSimulator(station=settings.station, sample_rate=settings.sample_rate).stream(
            channel="EHZ"
        )
    )
    sup._on_packet(packet)  # NO debe propagar el OSError

    assert seen["rules"], "las reglas evaluaron el paquete pese al disco lleno"
    sup.stop()


def test_disk_full_on_evidence_does_not_break_actuation(settings, monkeypatch):
    """queue_evidence que lanza OSError tras un EVACUATE no debe romper el hilo:
    los actuadores ya dispararon; la evidencia es best-effort.

    [T-2.32] Opt-in instrumental explícito: este test valida el seam de disco
    lleno y la actuación es su observable — sin opt-in no habría secuencia.
    """
    sup = EdgeSupervisor(
        settings.model_copy(update={"instrumental_actuation": True}), seedlink_source=None
    )
    sup.build()
    sup.start()

    def _disk_full(*_a, **_k):
        raise OSError("ENOSPC")

    monkeypatch.setattr(sup.backfill, "queue_evidence", _disk_full)
    fired = {"n": 0}
    real_exec = sup.actuators.execute_sequence

    def _spy(commands):
        fired["n"] += 1
        return real_exec(commands)

    monkeypatch.setattr(sup.actuators, "execute_sequence", _spy)

    decision = TierDecision(tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.THRESHOLD)
    sup._act_and_publish(decision, None)  # NO debe propagar el OSError

    assert fired["n"] == 1, "la secuencia de actuación se ejecutó antes de la evidencia"
    sup.stop()


def test_un_fichero_basura_en_el_spool_no_puede_impedir_el_arranque(settings, tmp_path):
    """El bloqueante de la auditoría: `build()` NO aísla por módulo.

    Un `.json` con `null` en el directorio de pendientes hacía que
    `BackfillManager.__init__` lanzara AttributeError DENTRO de `build()`, y como
    `build()` no tiene el `try` por módulo que sí tiene `start()`, el gabinete
    entero no arrancaba: un edificio sin protección por un fichero de basura.
    El respaldo de evidencia no es camino de vida — su avería jamás puede
    llevarse por delante el reflejo SASMEX (regla de oro 2).
    """
    spool = tmp_path / "spool"
    pending = tmp_path / "backfill-pending"  # hermano del spool (`_default_pending_dir`)
    pending.mkdir(parents=True)
    (pending / "evt-envenenado.json").write_bytes(b"null")

    sup = EdgeSupervisor(
        settings.model_copy(update={"cloud_spool_dir": str(spool)}), seedlink_source=None
    )
    sup.build()  # antes: AttributeError y el proceso no llegaba ni a start()
    sup.start()
    try:
        assert sup.gpio.running and sup.rules.running and sup.actuators.running
        WR1Simulator(sup.gpio).alert()
        assert sup.gpio.relay_state(ActuatorChannel.SIREN).energized is True
        # …y el hallazgo llega al panel, que es donde lo ve quien está de pie
        # frente al gabinete (no sólo al journal).
        evidencia = sup.local_api.status()["evidence"]
        assert evidencia["unreadable"] == 1
        assert evidencia["unreadable_items"] == ["evt-envenenado"]
    finally:
        sup.stop()


def test_sasmex_actuates_with_cloud_offline(supervisor):
    assert supervisor.cloud.online is False
    WR1Simulator(supervisor.gpio).alert()

    # Reflejo local ejecutado sin nube:
    assert supervisor.gpio.relay_state(ActuatorChannel.SIREN).energized is True
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    # La nube sólo encola (offline-first); nunca fue prerequisito para actuar.
    # (Desde T-1.17 la cola también lleva telemetría: se cuenta POR topic.)
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) == 1
    assert supervisor.cloud.queued_by_topic(ACKS_TOPIC) == 5  # secuencia evacuate completa
    assert supervisor.cloud.sent == 0


def test_la_config_viva_de_la_nube_jamas_se_cablea_al_reflejo(settings, tmp_path):
    """[T-2.65 · REGLA DE ORO 1] El estado administrativo no puede llegar al reflejo.

    Su hermano `test_config.py::test_gabinete_retirado_sigue_actuando_la_sirena_por_sasmex`
    prueba el invariante sobre un `GpioController` suelto; ESTE lo prueba sobre el
    CABLEADO REAL, y por eso existe: los apply-listeners se registran en
    `EdgeSupervisor.build()`, así que un `setattr(self.gpio, "settings", cfg)`
    añadido ahí —«que gpio también vea la config nueva», ordenar el edge— no lo
    vería NINGÚN test que construya el controlador a mano, y dejaría al módulo del
    camino de vida leyendo la config viva que publica la nube.

    Hostil por los dos extremos, como el hermano: el gabinete arranca retirado (así
    queda al reiniciar con la caché firmada de T-2.34) y la nube aplica encima otro
    sobre retirado, con el equipamiento declarado todo-ausente. Sirena y estrobo se
    MIDEN.
    """
    from takab_edge.config import EquipmentProfile

    s = settings.model_copy(
        update={
            "cloud_admin_state": "retired",
            "equipment": EquipmentProfile(
                siren=False, strobe=False, gas_valve=False, elevator=False, door_retainer=False
            ),
            # Caché propia: el default apunta a /var/lib/takab (estado del gabinete real).
            "config_cache_path": str(tmp_path / "config-cache.json"),
        }
    )
    sup = EdgeSupervisor(s, seedlink_source=None)
    sup.start()
    try:
        boot = sup.gpio.settings
        assert boot.is_retired is True  # el objeto del módulo del reflejo SÍ dice 'retired'

        raw = s.model_copy(update={"tenant_id": "tenant-retirado"}).model_dump_json().encode()
        version = sup.config.version + 1
        sup.config.apply_signed_update(raw, sup.security.sign_config(raw, version), version)
        assert sup.config.current().is_retired is True

        WR1Simulator(sup.gpio).alert()

        assert sup.gpio.is_activated(ActuatorChannel.SIREN) is True
        assert sup.gpio.is_activated(ActuatorChannel.STROBE) is True
        # Ningún listener acercó la config viva al módulo del reflejo.
        assert sup.gpio.settings is boot
        assert sup.config.current() is not sup.gpio.settings
    finally:
        sup.stop()


def test_instrumental_event_drives_tier(supervisor):
    # Sismo local: varios canales sobre disparo (corroboración ≥2), SIN SASMEX.
    sim = RS4DSimulator(station=supervisor.settings.station)
    now = datetime.now(UTC)
    for channel in ("ENZ", "ENN", "ENE"):
        supervisor.seedlink.feed(sim.packet(channel, now, peak_counts=1_000_000.0))
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    assert len(supervisor.buffer) == 3
    # [T-2.32 · política ratificada] El umbral instrumental es SOLO AVISO: el
    # tier se eleva (panel) pero la sirena NO suena por una estación sola.
    assert supervisor.gpio.relay_state(ActuatorChannel.SIREN).energized is False


def test_production_supervisor_wires_real_seedlink_transport(monkeypatch):
    # En producción (dev_mode=False) el edge DEBE conectar de verdad al Shake.
    from takab_edge.config import EdgeSettings
    from takab_edge.seedlink import ObsPySeedLinkTransport

    monkeypatch.setenv("TAKAB_EDGE_HMAC_KEY", "clave-prod-de-prueba")
    settings = EdgeSettings(dev_mode=False)
    sup = EdgeSupervisor(settings)
    sup.build()  # sólo ensambla; no arranca (no conecta)
    assert isinstance(sup.seedlink._transport, ObsPySeedLinkTransport)
    assert sup.seedlink._transport.station == settings.seedlink_station_code


def test_local_api_wired_with_signal_and_cloud(supervisor):
    """T-1.53: el supervisor cablea signal/cloud/identidad a la mini-consola —
    verificado por COMPORTAMIENTO: un paquete procesado aparece en status()."""
    from takab_edge.contracts import WaveformPacket, utcnow

    supervisor.signal.process(
        WaveformPacket(station="R4F74", channel="EHZ", starttime=utcnow(), samples=[0, 3] * 50)
    )
    status = supervisor.local_api.status()
    assert "EHZ" in status["signal"]["channels"]
    assert status["site_name"] == supervisor.settings.site_name
    assert status["cloud"] is not None


def _sobre_con_ventana(settings) -> dict:
    """Sobre de config con TODOS los nombres plausibles de "ventana abierta".

    Enumerar aquí es correcto AL REVÉS que en el resto de la suite: no se lista lo
    que hay que aceptar, se amplía la superficie del ataque. Un nombre más solo
    puede hacer el test más estricto.
    """
    import json

    sobre = json.loads(settings.model_dump_json())
    sobre.update(
        {
            "maintenance_window": True,
            "maintenance_window_until": "2099-01-01T00:00:00Z",
            "maintenance_mode": True,
            "in_maintenance": True,
            "alarms_muted": True,
            "muted": True,
            "silenced": True,
            "suppress_actuation": True,
        }
    )
    return sobre


def _mide_reles(sup) -> None:
    """RELÉS, no afirmaciones: la demanda Y el pin, sirena Y estrobo."""
    WR1Simulator(sup.gpio).alert()
    assert sup.gpio.is_activated(ActuatorChannel.SIREN) is True
    assert sup.gpio.relay_state(ActuatorChannel.SIREN).energized is True
    assert sup.gpio.is_activated(ActuatorChannel.STROBE) is True
    assert sup.gpio.relay_state(ActuatorChannel.STROBE).energized is True


def test_una_ventana_de_mantenimiento_EN_EL_ARRANQUE_no_calla_la_sirena(settings, tmp_path):
    """[T-2.71 · REGLA DE ORO 1 · vector 1 de 2: la config DE ARRANQUE]

    Este es el vector que casi se me escapa, y por eso está separado del otro. El
    hermano de T-2.65 (`test_la_config_viva_de_la_nube_jamas_se_cablea_al_reflejo`)
    mide que ningún apply-listener acerque la config VIVA al módulo del reflejo —
    y eso deja fuera el camino más probable: `GpioController` lee `self.settings`,
    que es el objeto de ARRANQUE, y desde T-2.34 el arranque se hidrata de una
    caché de config FIRMADA persistida en disco. Una ventana que llegara por ahí
    estaría en `gpio.settings` desde el primer segundo, y un test que solo mirase
    los listeners lo daría por bueno.

    Se mide construyendo el `EdgeSettings` de arranque desde un diccionario que SÍ
    trae los campos de ventana (que es como llegan: la nube publica un dict). Hoy
    `extra="ignore"` los descarta; si alguien los declara para pintarlos en el
    panel LAN, este test es lo que obliga a comprobar los relés antes de seguir.
    """
    arranque = type(settings).model_validate(
        {**_sobre_con_ventana(settings), "config_cache_path": str(tmp_path / "cache.json")}
    )
    sup = EdgeSupervisor(arranque, seedlink_source=None)
    sup.start()
    try:
        _mide_reles(sup)
    finally:
        sup.stop()


def test_una_ventana_de_mantenimiento_DE_LA_NUBE_no_calla_la_sirena(settings, tmp_path):
    """[T-2.71 · REGLA DE ORO 1 · vector 2 de 2: la config VIVA]

    Clon de `test_la_config_viva_de_la_nube_jamas_se_cablea_al_reflejo` cambiando
    el vector: allí el sobre hostil declaraba `cloud_admin_state="retired"`; aquí
    declara una VENTANA DE MANTENIMIENTO ABIERTA. Mide relés y además la IDENTIDAD
    del objeto — que ningún apply-listener haya acercado la config viva al módulo
    del camino de vida.
    """
    import json

    s = settings.model_copy(update={"config_cache_path": str(tmp_path / "cache.json")})
    sup = EdgeSupervisor(s, seedlink_source=None)
    sup.start()
    try:
        boot = sup.gpio.settings
        raw = json.dumps(_sobre_con_ventana(s)).encode()
        version = sup.config.version + 1
        sup.config.apply_signed_update(raw, sup.security.sign_config(raw, version), version)

        _mide_reles(sup)

        assert sup.gpio.settings is boot
        assert sup.config.current() is not sup.gpio.settings
    finally:
        sup.stop()


def test_la_ventana_de_mantenimiento_ni_siquiera_existe_para_el_edge(settings):
    """El invariante de raíz, medido una vez: el edge NO tiene dónde guardar una
    ventana de mantenimiento.

    `EdgeSettings` declara `extra="ignore"`, así que un campo de ventana en el
    sobre de config se descarta. Este test lo mide en vez de confiar en el
    `model_config`: si alguien lo cambiara a `extra="allow"` —o declarara el
    campo— el atributo aparecería y esto se pondría rojo, obligando a mirar los
    dos tests de relés de arriba antes de seguir.
    """
    reconstruido = type(settings).model_validate(_sobre_con_ventana(settings))
    for campo in ("maintenance_window", "maintenance_window_until", "suppress_actuation"):
        assert not hasattr(reconstruido, campo), campo
