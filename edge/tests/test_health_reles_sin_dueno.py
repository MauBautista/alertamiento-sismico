"""[T-2.70.a · B1] El latido tiene que poder decir «NO PUDE PREGUNTAR».

D3 sacó al dueño de los pines a su propio proceso (`takab-gpio`). Desde entonces
existe un estado alcanzable en producción que antes no lo era: `gpio_owner=gpio`
con `takab-gpio` caído o sin habilitar. En ese estado el gabinete **no tiene
sirena, ni cierre de gas, ni retorno de ascensores, ni retenedores** — y su
latido sale idéntico al de un gabinete sano salvo por una lista de relés vacía,
que el contrato hacía indistinguible de «el módulo está detenido».

Lo que estos tests miden es exactamente esa distinción, del `except` al cable:

1. `_relay_states` devuelve `None` cuando no pudo preguntar y `[]` cuando
   preguntó y no hay filas. Son dos hechos, no uno.
2. Los tres latidos —medido, detenido, ilegible— **no pueden confundirse** entre
   sí una vez serializados. Ese es el criterio: si el JSON de un gabinete sin
   dueño de pines es igual al de uno con el módulo parado, la nube no tiene con
   qué distinguirlos y el SOC seguirá verde.
3. El `null` VIAJA al cable (nada de `exclude_none`): si alguien "limpiara" el
   dump, la distinción moriría en silencio. Misma vigilancia que `fw_running`.
4. El JSON Schema comprometido admite el `null` — es el contrato que la nube lee.
5. La transición medido→ilegible se REGISTRA: `_log_transition` iteraba
   `snap.relays` sin guarda, así que un `None` habría matado el latido entero.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from takab_edge.contracts import ActuatorChannel, FailSafeMode, HealthSnapshot, RelayState
from takab_edge.gpio_link import GpioLink, GpioLinkUnavailable, GpioSnapshot
from takab_edge.health import HealthMonitor, UpsReading

_RELES = (
    RelayState(
        channel=ActuatorChannel.SIREN, energized=False, fail_safe=FailSafeMode.NORMALLY_OPEN
    ),
    RelayState(
        channel=ActuatorChannel.GAS_VALVE, energized=True, fail_safe=FailSafeMode.FAIL_CLOSE
    ),
)


class _Sondas:
    """Sondas del host que no tocan el host: el test mide relés, no `chronyc`."""

    def temperature_c(self) -> float:
        return 42.0

    def ntp_offset_s(self) -> float | None:
        return 0.001

    def ups(self) -> UpsReading:
        return UpsReading()

    def cert_days_remaining(self) -> int | None:
        return 300

    def disk_used_pct(self) -> float | None:
        return 10.0


class _Dueno:
    """Dueño de los pines de mentira, en sus tres conductas posibles.

    Implementa las CUATRO operaciones de la costura para que `as_link` lo
    reconozca como `GpioLink` y no lo envuelva en un `LocalGpioLink`.
    """

    def __init__(
        self,
        *,
        running: bool = True,
        relays: tuple[RelayState, ...] = _RELES,
        exc: BaseException | None = None,
    ) -> None:
        self._running = running
        self._relays = relays
        self._exc = exc
        self.preguntas = 0

    def snapshot(self) -> GpioSnapshot:
        self.preguntas += 1
        if self._exc is not None:
            raise self._exc
        return GpioSnapshot(
            running=self._running,
            sasmex_active=False,
            siren_sounding=False,
            siren_reason=None,
            audible_silenced=False,
            alert_latched=False,
            actuation_test_active=False,
            test_mode_active=False,
            test_mode_remaining_s=0.0,
            last_reflex_latency_s=None,
            relays=self._relays,
            keepalive_beating=False,
        )

    def apply(self, demands: Any) -> tuple:  # pragma: no cover — la costura lo exige
        return ()

    def action(self, name: str, **params: Any) -> Any:  # pragma: no cover
        return None

    def subscribe(self, event: str, callback: Any) -> None:  # pragma: no cover
        return None


def _monitor(settings: Any, dueno: Any) -> HealthMonitor:
    return HealthMonitor(settings, gpio=dueno, probes=_Sondas(), heartbeat_s=3600.0)


def test_el_dueno_de_mentira_es_reconocido_como_costura() -> None:
    """No-vacuidad: si `as_link` lo envolviera, los tests medirían otra cosa."""
    assert isinstance(_Dueno(), GpioLink)


def test_no_pude_preguntar_no_es_una_lista_vacia(settings) -> None:  # noqa: ANN001
    """El `except` deja de mentir: `None` («sin dato»), no `[]` («no hay»).

    `GpioLinkUnavailable` es literalmente lo que lanza `IpcGpioLink.snapshot()`
    cuando `takab-gpio` no contesta — el estado que D3 volvió alcanzable.
    """
    mudo = _Dueno(exc=GpioLinkUnavailable("el dueño de los pines no contesta"))
    snap = _monitor(settings, mudo).snapshot("test")
    assert mudo.preguntas == 1, "premisa: se intentó preguntar"
    assert snap.relays is None, (
        "el latido salió con una lista vacía: desde la nube eso es «módulo "
        "detenido», que es un estado benigno, y el edificio está sin sirena"
    )


def test_una_averia_en_marcha_tambien_es_sin_dato(settings) -> None:  # noqa: ANN001
    """Cualquier lectura que LANCE es «no pude preguntar»: el latido no sabe.

    El panel del gabinete sí separa `gpio_unreachable` de `gpio_error` (T-2.68)
    porque quien está de pie delante tiene dos journals distintos que mirar. La
    nube no tiene esa acción disponible: lo que necesita saber es que el censo
    de relés NO SE PUDO OBTENER.
    """
    snap = _monitor(settings, _Dueno(exc=RuntimeError("avería en caliente"))).snapshot("test")
    assert snap.relays is None


def test_el_modulo_detenido_sigue_siendo_una_lista_vacia(settings) -> None:  # noqa: ANN001
    """No-vacuidad del par: si `None` se comiera este caso, no habría distinción."""
    snap = _monitor(settings, _Dueno(running=False)).snapshot("test")
    assert snap.relays == [], "«pregunté y el módulo no corre» es un HECHO, no un hueco"


def test_el_censo_medido_sigue_llegando_entero(settings) -> None:  # noqa: ANN001
    """No-vacuidad del camino sano: el latido normal no cambió."""
    snap = _monitor(settings, _Dueno()).snapshot("test")
    assert snap.relays is not None
    assert [r.channel for r in snap.relays] == [r.channel for r in _RELES]


def test_los_tres_latidos_no_pueden_confundirse_en_el_cable(settings) -> None:  # noqa: ANN001
    """EL CRITERIO. Tres gabinetes, tres JSON distintos en la clave `relays`.

    Se comparan los payloads SERIALIZADOS —lo que de verdad cruza a la nube— y no
    los objetos en memoria: la distinción sólo sirve si sobrevive al `model_dump`.
    """
    payloads = {
        nombre: _monitor(settings, dueno).snapshot("test").model_dump(mode="json")["relays"]
        for nombre, dueno in {
            "sano": _Dueno(),
            "detenido": _Dueno(running=False),
            "sin_dueno": _Dueno(exc=GpioLinkUnavailable("mudo")),
        }.items()
    }
    serializados = {nombre: json.dumps(v) for nombre, v in payloads.items()}
    assert len(set(serializados.values())) == 3, (
        f"dos gabinetes en estados distintos publican el mismo latido: {serializados}"
    )
    assert payloads["sin_dueno"] is None


def test_el_sin_dato_viaja_al_cable_y_no_se_omite(settings) -> None:  # noqa: ANN001
    """La clave `relays` VIAJA aunque valga `null`.

    `edge/takab_edge/cloud` publica con `model_dump(mode="json")` **sin**
    `exclude_none`. Si alguien añadiera `exclude_none` "por limpieza", la nube
    vería «el gabinete no opina» donde el gabinete está gritando «no pude
    preguntar» — y la distinción moriría en silencio. Mismo guard que `fw_running`.
    """
    snap = _monitor(settings, _Dueno(exc=GpioLinkUnavailable("mudo"))).snapshot("test")
    crudo = json.loads(snap.model_dump_json())
    assert "relays" in crudo, "la clave desapareció del cable: la nube leerá «no opina»"
    assert crudo["relays"] is None


def test_el_schema_comprometido_admite_el_sin_dato() -> None:
    """El contrato que la nube lee (`shared/schemas/`) tiene que aceptar `null`.

    Sin esto el edge diría la verdad y el esquema publicado la desmentiría.
    """
    raiz = Path(__file__).resolve().parents[2]
    ruta = raiz / "shared" / "schemas" / "health_snapshot.schema.json"
    esquema = json.loads(ruta.read_text())
    relays = esquema["properties"]["relays"]
    tipos = {sub.get("type") for sub in relays.get("anyOf", [])}
    assert "null" in tipos, f"el schema publicado no admite «sin dato» en relays: {relays}"
    assert "array" in tipos


def test_un_payload_viejo_con_lista_vacia_sigue_validando() -> None:
    """Compatibilidad hacia atrás: 1.9.0 mandaba `[]` y tiene que seguir entrando."""
    snap = HealthSnapshot(gateway_id="gw-dev-0001", relays=[])
    assert snap.relays == []


def test_la_transicion_a_reles_ilegibles_se_registra(settings, caplog) -> None:  # noqa: ANN001
    """`_log_transition` iteraba `snap.relays` sin guarda: un `None` lo reventaba.

    Y no basta con que no reviente: pasar de «cinco relés medidos» a «no pude
    preguntar» ES una transición de estado discreto (regla de oro 10) y tiene que
    quedar escrita. Si el guard fuera `snap.relays or ()`, `None` y `[]` darían la
    misma clave y el cambio no se registraría.
    """
    dueno = _Dueno()
    monitor = _monitor(settings, dueno)
    with caplog.at_level(logging.INFO, logger="takab_edge.health"):
        monitor.snapshot("arranque")
        registros_tras_medir = len(caplog.records)
        dueno._exc = GpioLinkUnavailable("takab-gpio se cayó")
        snap = monitor.snapshot("heartbeat")
    assert snap.relays is None
    assert len(caplog.records) > registros_tras_medir, (
        "el gabinete se quedó sin dueño de pines y el journal no lo registró como transición"
    )


def test_la_lista_vacia_y_el_sin_dato_son_transiciones_distintas(settings) -> None:  # noqa: ANN001
    """Detenido → ilegible también es un cambio, y la clave de transición lo ve."""
    dueno = _Dueno(running=False)
    monitor = _monitor(settings, dueno)
    monitor.snapshot("arranque")
    clave_detenido = monitor._last_key
    dueno._exc = GpioLinkUnavailable("mudo")
    monitor.snapshot("heartbeat")
    assert monitor._last_key != clave_detenido, (
        "«módulo detenido» y «no pude preguntar» comparten clave de transición: "
        "el paso de uno a otro no se registraría nunca"
    )


@pytest.mark.parametrize("estado", ["sano", "detenido", "sin_dueno"])
def test_el_latido_arranca_en_los_tres_estados(settings, estado: str) -> None:  # noqa: ANN001
    """`_on_start` llama a `snapshot("startup")` FUERA de todo try.

    Un fallo ahí deja al gabinete sin latido — FANTASMA desde la nube, que es
    peor que el defecto que se está arreglando.
    """
    duenos = {
        "sano": _Dueno(),
        "detenido": _Dueno(running=False),
        "sin_dueno": _Dueno(exc=GpioLinkUnavailable("mudo")),
    }
    monitor = _monitor(settings, duenos[estado])
    monitor.start()
    try:
        assert monitor.running is True
        assert monitor.last_snapshot is not None
    finally:
        monitor.stop()
