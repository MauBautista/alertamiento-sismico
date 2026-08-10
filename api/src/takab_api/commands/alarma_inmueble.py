"""[T-2.106] La ALARMA DEL INMUEBLE: una sirena que un humano ordenó, no un sismo.

Decisión de producto ratificada el 2026-08-09:

    Una activación manual es **alarma del inmueble, no evacuación sísmica**.
    Suena la sirena del edificio —que es su diseño— y la app debe anunciarla como
    tal: sin instrucción de evacuación sísmica y sin el contador T+ de sismo.

Por qué hacía falta superficie nueva y no había regresión que arreglar: el
quórum de pánico (`POST /sites/{id}/manual-activation-votes`) emite un
`siren/activate` FIRMADO y **no crea incidente**, así que jamás llegaba a
`mobile-state`, que deriva su fase de incidentes. El edificio sonaba y el
teléfono del ocupante no decía nada — exactamente el vacío que la app existe
para llenar.

Vive junto a `service.py` y `quorum_actuation.py` porque la verdad de esto es un
COMANDO, no un incidente. Es hermana de `incident/autoridad.py` (T-2.105) en
forma y en disciplina: función pura, default-deny, consultada por `mobile_state`,
porque el teléfono JAMÁS decide fases (spec móvil §4.1).

Qué NO cambia: nada de esto toca el camino determinista SASMEX→sirena del
gabinete (regla de oro 1), ni silencia sirena alguna. Aquí sólo se decide qué se
le dice a una persona.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - solo para el tipo de la fase
    from takab_api.schemas.mobile import Phase

#: Actor sistema del burst de cuórum sísmico (`quorum_actuation.QUORUM_ACTOR_UUID`).
#: Su `siren/activate` NO es una activación manual: es la actuación firmada que la
#: nube comanda al confirmar ≥3 estaciones, y ésa llega a la app por su incidente,
#: como `alert_active`. Se excluye en la CONSULTA (`queries/mobile.SIREN_ORDER`).
#: Se nombra aquí para que quede escrito por qué la consulta lo filtra.
_ACTOR_SISTEMA_DOC = "quorum_actuation.QUORUM_ACTOR_UUID"

#: La ÚNICA acción que enciende la afirmación «suena».
_ACTIVAR = "activate"

#: [T-2.70.a·B1] `device_health.relays_state` = 'unreadable' es el gabinete
#: diciendo *«no pude preguntar quién gobierna los pines»*: con `gpio_owner=gpio`
#: y `takab-gpio` caído ese edificio no tiene sirena, ni gas, ni ascensores, ni
#: retenedores. Es el ÚNICO desmentido honesto que la nube tiene sobre el relé.
_RELES_ILEGIBLES = "unreadable"


@dataclass(frozen=True)
class OrdenSirena:
    """La última orden sobre la sirena del edificio que un gabinete confirmó
    haber EJECUTADO, más lo que ese mismo gabinete dice de sí en su último latido.

    ``action``        ``activate`` | ``deactivate`` (lo último que tocó el relé).
    ``issued_at``     cuándo se emitió — el instante que la app muestra.
    ``relays_state``  censo de relés del ÚLTIMO latido de ESE gabinete.
    ``gateway_age_s`` antigüedad de ese latido; ``None`` = jamás latió.
    """

    action: str
    issued_at: datetime
    relays_state: str | None
    gateway_age_s: float | None


def suena_la_alarma(
    orden: OrdenSirena | None,
    *,
    ahora: datetime,
    vigencia_s: float,
    sin_enlace_s: float,
) -> datetime | None:
    """¿Desde cuándo suena la alarma del inmueble? ``None`` = no se afirma nada.

    **De dónde sale la verdad de «está sonando».** Del ACK DE EJECUCIÓN del
    gabinete: ``commands.status = 'acked'`` sobre un ``siren/activate``. Es el ack
    que la regla de oro 8 exige para todo comando de actuador, y es lo único que
    dice que la orden llegó al relé. Un comando ``pending`` se publicó y nadie
    confirmó nada; uno ``rejected`` o ``expired`` no encendió sirena alguna.
    Pintarlos como una sirena sonando sería la regla de oro 7 al revés.

    **Cuatro formas de dejar de sostenerlo**, todas default-deny:

    1. **La última orden ejecutada fue ``deactivate``.** Alguien silenció. Manda
       lo último que TOCÓ el relé, no lo último que se pidió: por eso la consulta
       sólo mira comandos ``acked``, en las dos direcciones. Un ``deactivate``
       todavía ``pending`` no ha silenciado nada y la alarma sigue anunciada.
    2. **El gabinete lleva más de ``sin_enlace_s`` callado** (o jamás latió).
       Misma doctrina que ``derive_fleet_state``: SIN ENLACE manda sobre todo lo
       demás, porque el censo de un gabinete que lleva horas mudo es un dato
       viejo y no describe lo que pasa ahora.
    3. **``relays_state == 'unreadable'``.** El gabinete no puede ni preguntar
       quién gobierna sus pines ⇒ no hay sirena que anunciar. Los otros dos
       valores NO desmienten, por la misma razón que no degradan la flota:
       ``stopped`` es ambiguo en firmware ≤1.9.0 y ``None`` es ausencia de
       opinión — y la ausencia nunca es diagnóstico.
    4. **Caducó** (ver ``vigencia_s`` en ``Settings.building_alarm_max_s``).

    Lo que esta función NO puede afirmar, y conviene tenerlo escrito: la nube
    **no sabe si el relé de la sirena está energizado ahora mismo**. La migración
    0036 decidió a propósito no persistir el censo canal a canal
    (``relays_state`` sólo dice si el gabinete PUDO mirarse los relés). Así que
    esto es «el gabinete confirmó que ejecutó la orden de encender y nadie la ha
    revertido», que es la afirmación más fuerte que los datos sostienen — y la
    pantalla está redactada para decir exactamente eso.
    """
    if orden is None or orden.action != _ACTIVAR:
        return None
    if orden.relays_state == _RELES_ILEGIBLES:
        return None
    if orden.gateway_age_s is None or orden.gateway_age_s > sin_enlace_s:
        return None
    if (ahora - orden.issued_at).total_seconds() > vigencia_s:
        return None
    return orden.issued_at


def fase_del_sitio(fase_sismica: Phase, alarma_desde: datetime | None) -> Phase:
    """Precedencia: **LO SÍSMICO MANDA SIEMPRE.**

    ``alert_active`` > ``shaking_concluded`` > ``reentry_approved`` >
    ``building_alarm`` > ``idle``.

    Las tres primeras son ramas excluyentes del MISMO incidente, así que basta
    con que cualquier fase sísmica distinta de ``idle`` gane: una alarma de
    inmueble jamás puede robarle la pantalla a una evacuación autorizada, ni
    tapar el check-in de vida, ni sugerir que el reingreso aprobado se revocó.

    Y al revés, que es el criterio 3 de la tarea: por este camino **un pánico no
    puede producir ``alert_active`` jamás**. Lo único que esta función puede
    devolver cuando no hay sismo es ``building_alarm`` o ``idle``.
    """
    if fase_sismica != "idle":
        return fase_sismica
    return "building_alarm" if alarma_desde is not None else "idle"
