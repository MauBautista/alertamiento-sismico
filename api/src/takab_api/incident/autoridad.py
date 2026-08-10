"""Quién puede ordenar una EVACUACIÓN, y quién solo puede advertir.

[T-2.105] Regla de producto ratificada por Mauricio el 2026-08-09, y es la misma
que el blueprint §1 ya describía para los actuadores — solo que la superficie
móvil no la aplicaba:

    Una alarma y un aviso de evacuación SOLO se despliegan si llega la señal del
    WR-1 de SASMEX, o si tres o más inmuebles se están moviendo y rebasan el
    umbral AL MISMO TIEMPO. Cuando una estación individual siente movimiento que
    rebasa el umbral, solo avisa al SOC y al gabinete, y **solo como
    advertencia**: puede haber sido un factor externo y no un sismo.

Por qué vive en el servidor y no en la app: el teléfono JAMÁS decide fases
(spec móvil §4.1), y una regla de seguridad repartida entre clientes es una
regla que se aplica distinto en cada uno. Aquí es una sola función, pura y
testeable, y `mobile_state` la consulta.

Qué NO cambia: el camino determinista SASMEX→sirena del gabinete, que no pasa
por aquí ni por la nube (regla de oro 1). Esto solo gobierna lo que la app le
dice a una persona.
"""

from __future__ import annotations

#: Orígenes que por sí solos autorizan una orden de evacuación.
#: `sasmex` es el canal primario y autoritativo (contacto seco del WR-1).
#: `quorum` está en el CHECK de `incidents.trigger` por completitud: hoy el motor
#: de correlación NO reescribe el trigger —solo enlaza `event_id`—, así que en la
#: práctica el cuórum se reconoce por `node_count`. Se acepta igual para que un
#: cambio futuro en el motor no reabra este agujero en silencio.
ORIGENES_AUTORITATIVOS = frozenset({"sasmex", "quorum"})


def autoriza_evacuacion(trigger: str, node_count: int | None, min_nodes: int) -> bool:
    """¿Este incidente puede ordenar evacuar a las personas del inmueble?

    ``node_count`` sale del evento sísmico enlazado (``meta.node_count``), que es
    lo que el motor de cuórum escribe al confirmar: por eso un incidente que nace
    `local_threshold` PASA a autorizar en cuanto la red lo corrobora, sin que
    nadie reescriba su trigger.

    Default-deny: un origen desconocido no autoriza. Es la dirección correcta —
    equivocarse hacia «no ordeno evacuar» deja a la gente donde estaba; hacia el
    otro lado, la saca a la calle por un camión que pasó cerca del sensor.
    """
    if trigger in ORIGENES_AUTORITATIVOS:
        return True
    return node_count is not None and node_count >= min_nodes
