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

[T-2.120] **La premisa de la que nació este módulo caducó, y con ella su única
fuente.** `T-2.106` escribió que la nube «no sabe si el relé de la sirena está
energizado ahora mismo» y por eso derivaba la alarma de la última orden que TOCÓ
el relé. `T-2.116` metió ese dato en el acuse (``commands.ack->'channel_state'``,
el canal recalculado por el arbitraje del gabinete), así que ahora hay DOS
fuentes que no valen lo mismo: una medición y una deducción. Las dos siguen
sirviendo —el gabinete de campo aún no manda censo y ése es el caso de hoy— pero
salen etiquetadas, porque presentar una inferencia como una medición en la
superficie que hace sonar un teléfono es exactamente lo que prohíbe la regla de
oro 7.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

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

#: [T-2.120] El canal del que habla esta pantalla. Un censo de otro canal (gas,
#: ascensores) NO dice nada de la sirena y no se lee como si lo dijera.
_CANAL_SIRENA = "siren"

#: [T-2.120] De dónde salió la afirmación «suena», que es lo que la app necesita
#: para no presentar una inferencia como si fuera una medición:
#:
#: · ``relay_measured``  — del ``channel_state`` del acuse (`T-2.116`): el estado
#:   del canal TRAS EL ARBITRAJE, recalculado por el dueño de los pines.
#: · ``order_inferred`` — de la ORDEN ejecutada más la corroboración del latido
#:   (el método de `T-2.106`). Es lo mejor que hay cuando el gabinete no declara
#:   el relé, y **es el caso de hoy**: el gabinete de campo todavía corre el
#:   código anterior a `T-2.116`.
Origen = Literal["relay_measured", "order_inferred"]


@dataclass(frozen=True)
class AlarmaDelInmueble:
    """La alarma que se anuncia, CON su procedencia.

    Que ``since`` viaje solo era suficiente mientras sólo había una forma de
    saberlo. Desde `T-2.116` hay dos y no valen igual, así que la procedencia
    viaja pegada al hecho — separarlas es cómo una inferencia acaba leyéndose
    como una medición tres capas más arriba.
    """

    #: ``commands.issued_at`` de la orden ejecutada (la app lo pinta como hora).
    since: datetime
    origen: Origen


@dataclass(frozen=True)
class OrdenSirena:
    """La última orden sobre la sirena del edificio que un gabinete confirmó
    haber EJECUTADO, más lo que ese mismo gabinete dice de sí en su último latido.

    ``action``        ``activate`` | ``deactivate`` (lo último que tocó el relé).
    ``issued_at``     cuándo se emitió — el instante que la app muestra.
    ``relays_state``  censo de relés del ÚLTIMO latido de ESE gabinete.
    ``gateway_age_s`` antigüedad de ese latido; ``None`` = jamás latió.
    ``channel_state`` [T-2.120] el censo del canal que viaja DENTRO del acuse
                      (``commands.ack->'channel_state'``, `T-2.116`). ``None`` =
                      el gabinete no lo declara — jamás «en reposo».
    """

    action: str
    issued_at: datetime
    relays_state: str | None
    gateway_age_s: float | None
    channel_state: Any = None


def sirena_activada(channel_state: Any) -> bool | None:
    """¿Quedó la SIRENA en su estado de protección? Tres respuestas, no dos.

    ``True``/``False`` son MEDICIONES del gabinete: el estado del canal tras el
    arbitraje de demandas (`T-2.116`), que es lo que la spec móvil §2.2 pide
    —«el resultado real llega en el ``command_ack`` con el estado recalculado del
    relé»— y lo que `handle_command_ack` persiste en ``commands.ack``.

    ``None`` es **«no pude preguntar»**: firmware anterior al schema 1.11.0,
    actuador BACnet, o un acuse de rechazo que no llegó a ejecutar nada. Nunca,
    bajo ninguna lectura, «el relé está en reposo». Colapsar los dos convertiría
    el despliegue escalonado de `T-2.116` en un apagón silencioso de la alarma
    del inmueble en toda la flota todavía sin actualizar.

    Espejo exacto de ``sirenChannelState()`` en
    ``mobile/src/features/control/ackState.ts``: mismo default-deny en la
    lectura (canal ``siren`` + ``activated`` booleano, o no es medición), para
    que las dos superficies no puedan derivar en su idea de qué es un censo.
    """
    if not isinstance(channel_state, dict):
        return None
    if channel_state.get("channel") != _CANAL_SIRENA:
        return None
    activada = channel_state.get("activated")
    return activada if isinstance(activada, bool) else None


def suena_la_alarma(
    orden: OrdenSirena | None,
    *,
    ahora: datetime,
    vigencia_s: float,
    sin_enlace_s: float,
) -> AlarmaDelInmueble | None:
    """¿Desde cuándo suena la alarma del inmueble? ``None`` = no se afirma nada.

    **De dónde sale la verdad de «está sonando».** Del ACK DE EJECUCIÓN del
    gabinete: ``commands.status = 'acked'`` sobre un ``siren/activate``. Es el ack
    que la regla de oro 8 exige para todo comando de actuador, y es lo único que
    dice que la orden llegó al relé. Un comando ``pending`` se publicó y nadie
    confirmó nada; uno ``rejected`` o ``expired`` no encendió sirena alguna.
    Pintarlos como una sirena sonando sería la regla de oro 7 al revés.

    **[T-2.120] Y dentro de ese mismo ack, cuando el gabinete lo declara, viene
    el relé.** ``channel_state`` (`T-2.116`) es el estado del canal TRAS EL
    ARBITRAJE. Manda sobre la inferencia en las dos direcciones:

    · ``activated = False`` **desmiente**, aunque la orden ejecutada fuera un
      ``activate`` con ``success=true``. El acuse describe LA ORDEN; el censo
      describe EL RELÉ, y son cosas distintas — ésa es la ficha `T-2.116`
      entera. Sin esta rama, un `activate` que el arbitraje no honró (fail-safe,
      prueba en curso, otra demanda) encendía la pantalla del inmueble completo
      y despertaba a la gente de madrugada.
    · ``activated = True`` **sostiene**, y la afirmación sale marcada
      ``relay_measured``: es un hecho medido en el sitio, no una deducción.
    · ``None`` —«no pude preguntar»— **degrada** al método de `T-2.106` y sale
      marcada ``order_inferred``. Es el caso de HOY: hasta que el gabinete de
      campo se re-despliegue, ningún acuse trae censo.

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

    **Las guardas de frescura se aplican TAMBIÉN al camino medido**, y no es un
    descuido: ``channel_state`` describe el relé en el instante del acuse, no
    ahora. Un gabinete que lleva horas mudo, uno que ya no puede leerse los relés
    o una alarma caducada siguen desmintiendo igual — un dato medido y viejo
    pintado como vivo es la regla de oro 7 con mejor coartada, no una excepción.

    Lo que esta función sigue SIN poder afirmar: qué hace el relé *en este
    segundo*. La migración 0036 decidió a propósito no persistir el censo canal a
    canal (``relays_state`` sólo dice si el gabinete PUDO mirarse los relés), y
    `T-2.116` trae el censo pegado a un acuse, no un flujo continuo. Así que con
    medición esto es «el gabinete midió el relé energizado al ejecutar, y nadie
    lo ha revertido desde entonces», y sin ella, «el gabinete confirmó que
    ejecutó la orden de encender y nadie la ha revertido». Son afirmaciones
    distintas, van etiquetadas distinto, y la pantalla puede redactarse para
    cada una.
    """
    if orden is None or orden.action != _ACTIVAR:
        # Un `deactivate` acusado con el relé TODAVÍA activo (el caso de vida de
        # `T-2.110`) tampoco entra: la persona retiró su demanda y lo que sostiene
        # la sirena es otra cosa —una alerta enclavada, que gana la precedencia
        # por su propia fase, o una prueba—. Anunciarlo como alarma del inmueble
        # le atribuiría a esa persona una sirena que intentó apagar. Quien SÍ lo
        # explica es la hoja de mando del táctico (`ackState.ts`, T-2.116).
        return None
    medida = sirena_activada(orden.channel_state)
    if medida is False:
        return None
    if orden.relays_state == _RELES_ILEGIBLES:
        return None
    if orden.gateway_age_s is None or orden.gateway_age_s > sin_enlace_s:
        return None
    if (ahora - orden.issued_at).total_seconds() > vigencia_s:
        return None
    return AlarmaDelInmueble(
        since=orden.issued_at,
        origen="relay_measured" if medida is True else "order_inferred",
    )


def fase_del_sitio(fase_sismica: Phase, alarma: AlarmaDelInmueble | None) -> Phase:
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
    return "building_alarm" if alarma is not None else "idle"
