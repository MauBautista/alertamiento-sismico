"""[T-7.05 · H-1] El latido de arranque, visto desde el lado que lo EMITE.

`shared/schemas/tests/latido_arranque_sin_dato.json` es el cuerpo que el
2026-09-10 acabó en la cola de mensajes muertos de telemetría, leído de esa cola
el 2026-09-12 antes de drenarla. La lectura se truncó a media lista de relés y
el fichero enumera allí, una por una, las cuatro cosas que quedaron detrás del
corte y cómo se completaron. La nube prueba que ese cuerpo se acepta, que se
guarda con NULLs y que reproduce la razón exacta de aquel rechazo
(`api/tests/test_ingest_latido_arranque.py`); aquí se prueba la mitad que esa
suite no puede: que **es de verdad lo que este gabinete emite al arrancar**, y
no un payload escrito a mano que se parecía. Un vector copiado a mano en dos
suites diverge — el precedente está al lado, en `hmac_vectors.json`.

Las cuatro sondas sin dato no se enumeran en este fichero: se leen del propio
vector. Si mañana alguien le quita una, estos tests dejan de ejercerla y lo
dicen en vez de callarlo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from takab_edge.contracts import HealthSnapshot, UpsStatus
from takab_edge.health import HealthMonitor, UpsReading

_RAIZ = Path(__file__).resolve().parents[2]
_VECTOR = _RAIZ / "shared/schemas/tests/latido_arranque_sin_dato.json"
_ESQUEMA = _RAIZ / "shared/schemas/health_snapshot.schema.json"

#: Las que añade la regla de AWS IoT al mensaje, no el gabinete.
_META = ("meta_principal", "meta_topic", "meta_ts_iot")


def _vector() -> tuple[dict, list[str]]:
    doc = json.loads(_VECTOR.read_text("utf-8"))
    cuerpo = {k: v for k, v in doc["mensaje"].items() if k not in _META}
    return cuerpo, doc["sondas_sin_dato"]


class _SondasDeArranque:
    """Las sondas que SÍ miden desde el primer segundo (reloj, temperatura,
    certificado, disco), con los valores que el gabinete reportó aquella noche.

    Las otras cuatro no dependen de esta clase: dependen de que no haya ni
    cliente SeedLink, ni RTT medido, ni UPS. Estos cuatro números no los compara
    ningún assert —los tests de abajo miran los `null`—, y aun así se ponen los
    del latido y no unos redondos: una sonda inventada aquí invita a «refrescar»
    el vector desde este fichero, que es justo como se pierde la procedencia."""

    def temperature_c(self) -> float:
        return 53.556

    def ntp_offset_s(self) -> float:
        return 0.0021230000000000003

    def ups(self) -> UpsReading:
        return UpsReading()  # sin hardware ⇒ status unknown, batería y autonomía S/D

    def cert_days_remaining(self) -> int:
        return 8513

    def disk_used_pct(self) -> float:
        return 41.02544068756029


def test_el_vector_de_la_dlq_es_un_latido_que_el_modelo_emite_tal_cual() -> None:
    """Round-trip exacto: nada sobra, nada falta, nada se renombra.

    Es la guarda contra la fiction: el día que el contrato gane o pierda un
    campo, este vector deja de ser «el cuerpo que fue a la DLQ» y hay que
    regenerarlo a conciencia, no descubrirlo en producción.
    """
    cuerpo, sondas = _vector()
    emitido = HealthSnapshot(**cuerpo).model_dump(mode="json")
    assert emitido == cuerpo
    # …y que sigue ejerciendo lo que lo hizo caer: sin esto el vector podría
    # «arreglarse» rellenando las cuatro sondas y todo lo demás seguiría verde.
    for campo in sondas:
        assert cuerpo[campo] is None, f"el vector dejó de ejercer «sin dato» en {campo}"


def test_el_gabinete_al_arrancar_emite_esas_cuatro_sondas_SIN_DATO(settings) -> None:
    """Sin SeedLink, sin RTT y sin UPS: las cuatro dicen «sin dato», no cero.

    `packet_loss_pct` es la que rompió la ingesta, pero las cuatro viajan en el
    MISMO latido: cualquiera de ellas habría bastado.

    Y el `seedlink_lag_s` de 0.178 s que trae el vector no contradice esto:
    `SeedLinkClient.last_lag_s` mide la antigüedad del dato más reciente y, sin
    ninguno todavía, la mide desde que arrancó el módulo. Es la edad del proceso,
    no la salud del enlace — por eso `packet_loss_pct` sigue sin denominador.
    """
    monitor = HealthMonitor(settings, probes=_SondasDeArranque())
    snap = monitor.snapshot()
    _cuerpo, sondas = _vector()

    for campo in sondas:
        assert getattr(snap, campo) is None, (
            f"{campo} vale {getattr(snap, campo)!r} en el latido de arranque: un número "
            "ahí es una medición que nadie ha hecho (regla de oro 7)"
        )
    assert snap.ups_status is UpsStatus.UNKNOWN


def test_el_null_VIAJA_al_cable_y_no_se_queda_en_el_gabinete(settings) -> None:
    """`exclude_none` borraría las cuatro claves y la nube leería sus defaults.

    Ése sería el mismo engaño por otra puerta: ausente ⇒ el validador aplica el
    default del contrato, y el SOC pintaría una cifra que nadie midió.
    """
    monitor = HealthMonitor(settings, probes=_SondasDeArranque())
    publicado = monitor.snapshot().model_dump(mode="json")
    _cuerpo, sondas = _vector()

    for campo in sondas:
        assert campo in publicado, f"{campo} no llegó al cable: la nube usaría su default"
        assert publicado[campo] is None


@pytest.mark.parametrize("campo", _vector()[1])
def test_el_esquema_publicado_admite_null_en_cada_sonda_de_arranque(campo: str) -> None:
    """El contrato que lee la nube, campo a campo y derivado del vector.

    `test_health.py` ya lo vigila para `packet_loss_pct`; esto lo extiende a las
    otras tres del mismo latido sin escribir sus nombres aquí. Estrechar una
    sola devuelve el gabinete a la cola de mensajes muertos.
    """
    esquema = json.loads(_ESQUEMA.read_text("utf-8"))["properties"][campo]
    tipos = {sub.get("type") for sub in esquema.get("anyOf", [])}
    assert "null" in tipos, f"el esquema publicado no admite «sin dato» en {campo}: {esquema}"
    assert "number" in tipos
