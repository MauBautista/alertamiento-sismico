"""[T-9.04] EL REINGRESO PERSISTENTE: qué se le dice a quien está FUERA del edificio.

`mobile_state` deriva la fase del incidente ABIERTO que autoriza evacuar. Pero la
persona que evacuó sigue fuera cuando ya no hay nada abierto —desde `D-33` firmar
el dictamen cierra el incidente en TRES SEGUNDOS— y lo que necesita saber
entonces es si puede volver a entrar. Esta función lo decide con los incidentes
CERRADOS del sitio, y es pura: sin base, sin reloj propio, testeable entera.

**Tres defectos medidos** que la hicieron falta:

1. **Un NO HABITAR firmado caducaba solo.** La rama de cerrados de `T-7.55` sólo
   re-declaraba dictámenes HABITABLES, así que tres segundos después de firmar
   «no habitable» la app volvía a `idle` con el edificio desbloqueado. Es la
   dirección cara del error: le dice a alguien que puede entrar a un edificio
   que un inspector acaba de declarar inhabitable.
2. **«REINGRESO AUTORIZADO» en reposo por incidentes que nunca ordenaron
   evacuar**, porque la consulta no miraba `autoriza_evacuacion` (T-2.105). Y
   las 8 h contaban desde el CIERRE, así que un cierre tardío —el TTL de
   revisión, una limpieza— resucitaba una autorización firmada días antes.
3. Un incidente local nuevo tapaba a uno autorizante más viejo: vive en el router
   y en las consultas, que filtran en SQL lo que cuenta ANTES de cualquier `LIMIT`.

**Las reglas.** Sólo cuentan los incidentes que **autorizaron evacuar**
(`incident/autoridad.py`, la ÚNICA copia de la regla: una estación sola no
ordenó salir a nadie, no hay reingreso que bloquear ni que autorizar) y cuya
**clasificación vigente no es terminal** (`TERMINALES`: falso positivo, prueba,
reproducción ⇒ ese incidente **no ocurrió** en el edificio). Entre ésos:

1. **Un NO HABITAR vigente manda sobre todo lo demás** ⇒ `reentry_blocked`/
   ``no_habitable``, **sin caducidad**. «Vigente» = la cabeza de la cadena de
   ESE incidente está FIRMADA y no es habitable (un veredicto desconocido cuenta
   como no habitable: default-deny). Sólo lo levanta un dictamen habitable
   firmado después **sobre ese mismo incidente** —lo que dice la ficha—, y eso
   siempre es posible: `sign_dictamen` no mira el estado del incidente. Si hay
   varios, se cita el firmado más recientemente.
2. Si no, **decide UNO: el candidato cerrado MÁS RECIENTEMENTE** (por
   ``closed_at``) de entre los cerrados hace menos de ``lookback_pendiente_s``
   —diga lo que diga; no se cae a otro más viejo—:
   * cabeza SIN firmar (o sin dictamen) ⇒ `reentry_blocked`/
     ``pendiente_dictamen``: un SASMEX que nadie ha inspeccionado no deja el
     edificio en calma.
   * cabeza FIRMADA (habitable: las otras salieron en la regla 1) ⇒
     `reentry_approved` mientras la firma tenga menos de ``ventana_firma_s``
     (8 h desde la FIRMA, no desde el cierre); pasada, `idle`: el último
     veredicto es «habitable» y ya no hace falta repetirlo.
   La cota del ``lookback`` existe para que un incidente que nadie dictaminó no
   bloquee para siempre la pantalla de quien ya volvió a trabajar.
3. Nada de lo anterior ⇒ `idle`.

**Por qué el CIERRE y no la apertura** decide cuál es «el más nuevo»: el cierre
es lo último que pasó con cada incidente —desde `D-33` firmar lo cierra en tres
segundos, así que en uno dictaminado ``closed_at`` ≈ la firma; en uno sin
dictamen es el TTL que lo dejó sin inspeccionar—. Por apertura, un SASMEX
abierto hace tres días y cerrado hace una hora sin que nadie lo viera quedaba
detrás de una habitable caducada sobre uno abierto después, y la app pintaba la
calma. Ante la duda se equivoca hacia «pendiente», que es la dirección barata.

⚠️ **Por qué la regla 1 va ANTES y no «manda el más nuevo»** (refutaciones de F0,
cada una medida contra el endpoint):

* **Un pendiente no puede tapar un NO HABITAR.** La réplica SASMEX que el TTL
  cierra sin dictamen —el edificio ya estaba cerrado, nadie lo inspecciona— es
  lo normal justo después del sismo que provoca un NO HABITAR. Parar en ella
  bajaba el cartel rojo a una franja ámbar y citaba el incidente equivocado.
* **«Más nuevo» no se decide por la apertura.** Un NO HABITAR firmado HOY sobre
  un incidente abierto hace tres días —el daño se descubrió tarde— quedaba
  detrás de una habitable firmada anteayer sobre uno abierto después.
* **Una habitable sobre OTRO incidente no dice que el daño de éste se reparó.**
  La app sigue citando el NO HABITAR, que es donde el inspector tiene que firmar.
  Es la dirección cara del error la que se cierra: equivocarse hacia «no entre»
  deja a alguien fuera un rato de más; hacia el otro lado, lo mete en un edificio
  que un inspector declaró inhabitable.

Los terminales (y los que no ordenaron evacuar) NO SON CANDIDATOS, en vez de
devolver `idle` por el mismo motivo: si mandaran por ser los más nuevos, probar
el WR-1 un martes desbloquearía en la app un inmueble dictaminado inhabitable.
Las consultas los excluyen en SQL ANTES de cualquier ``LIMIT`` (si no, diez
pruebas posteriores sacaban al NO HABITAR de la ventana), y esta función vuelve
a aplicar las dos reglas: la del SQL sólo acota, ésta decide.

El orden lo decide esta función y no el ``ORDER BY`` de la consulta: `T-7.55` ya
dejó escrito que el orden de un ``ORDER BY`` no puede decidir lo que lee alguien
que está decidiendo si entra a un edificio. Por eso acepta ``cerrados`` en
cualquier orden y con duplicados: el router le junta dos consultas.

``pendiente_confirmacion`` se RESERVA en el tipo aunque ninguna regla lo
produzca hoy: lo usa F3, y un valor que ya está en el `Literal` publicado obliga
a la app a declararlo antes de recibirlo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from takab_api.incident.autoridad import autoriza_evacuacion
from takab_api.incident.classification import TERMINALES

#: Dictamen HABITABLE: libera el reingreso (spec §7 · 2.7 «HABITAR»). Cualquier
#: otro veredicto FIRMADO bloquea — incluido uno que esta versión no conozca.
HABITABLES: frozenset[str] = frozenset({"normal_operation", "inhabit_monitor"})

#: Por qué está bloqueado el reingreso. Viaja en ``MobileReentryOut.reason``.
RazonBloqueo = Literal["no_habitable", "pendiente_dictamen", "pendiente_confirmacion"]

#: Las tres fases que esta función puede proponer. La precedencia contra las
#: demás la decide ``commands/alarma_inmueble.fase_del_sitio``.
FaseDeReingreso = Literal["idle", "reentry_approved", "reentry_blocked"]


@dataclass(frozen=True)
class IncidenteCerrado:
    """Un incidente CERRADO del sitio con lo que hace falta para juzgarlo.

    ``dictamen_*`` describen la CABEZA de la cadena (la fila más reciente,
    firmada o no), no la última firmada: una corrección posterior sin firmar
    deja el veredicto en suspenso, igual que en el certificado (`T-8.12`).
    ``dictamen_at`` es el ``created_at`` de esa cabeza, que en una fila firmada
    ES la hora de la firma. ``clasificacion`` es la VIGENTE (corregir inserta,
    `T-5.12`), o ``None`` si nadie lo clasificó.
    """

    incident_id: UUID
    trigger: str
    node_count: int | None
    opened_at: datetime
    closed_at: datetime | None
    clasificacion: str | None
    dictamen_status: str | None
    dictamen_firmado: bool
    dictamen_at: datetime | None


@dataclass(frozen=True)
class Reingreso:
    """El veredicto. ``incidente`` es el que lo produjo (``None`` en `idle`)."""

    fase: FaseDeReingreso
    razon: RazonBloqueo | None = None
    incidente: IncidenteCerrado | None = None


_IDLE = Reingreso(fase="idle")


def _hace_s(ahora: datetime, instante: datetime) -> float:
    return (ahora - instante).total_seconds()


def _cuenta(inc: IncidenteCerrado, min_nodes: int) -> bool:
    """¿Este incidente tiene algo que decir del edificio? Ordenó evacuar y ocurrió."""
    return (
        autoriza_evacuacion(inc.trigger, inc.node_count, min_nodes)
        and inc.clasificacion not in TERMINALES
    )


def _no_habitable_vigente(inc: IncidenteCerrado) -> bool:
    """Cabeza FIRMADA y no habitable: sólo otra firma sobre ESTE incidente lo cambia."""
    return inc.dictamen_firmado and inc.dictamen_status not in HABITABLES


def deriva_reingreso(
    cerrados: Sequence[IncidenteCerrado],
    *,
    ahora: datetime,
    min_nodes: int,
    ventana_firma_s: float,
    lookback_pendiente_s: float,
) -> Reingreso:
    """¿Qué se le dice del reingreso a quien está fuera? Reglas en el docstring del módulo.

    ``cerrados`` en cualquier orden y con duplicados. El llamante sólo debe
    invocarla cuando NO hay incidente abierto que autorice evacuar — con alerta
    viva manda la alerta, siempre.
    """
    cuentan = [inc for inc in cerrados if _cuenta(inc, min_nodes)]

    # 1 · NO HABITAR vigente: precedencia sobre todo, sin caducidad.
    bloqueantes = [inc for inc in cuentan if _no_habitable_vigente(inc)]
    if bloqueantes:
        cita = max(
            bloqueantes,
            key=lambda i: (i.dictamen_at or i.opened_at, i.opened_at, str(i.incident_id)),
        )
        return Reingreso(fase="reentry_blocked", razon="no_habitable", incidente=cita)

    # 2 · el cerrado MÁS RECIENTEMENTE dentro de la espera decide, diga lo que diga.
    recientes = [
        inc
        for inc in cuentan
        if inc.closed_at is not None and _hace_s(ahora, inc.closed_at) < lookback_pendiente_s
    ]
    if not recientes:
        return _IDLE
    # Mismo desempate que el ``ORDER BY closed_at DESC, incident_id DESC`` de la
    # consulta (el ``str`` de un UUID ordena igual que el ``uuid`` de Postgres).
    inc = max(recientes, key=lambda i: (i.closed_at, str(i.incident_id)))
    if not inc.dictamen_firmado:
        return Reingreso(fase="reentry_blocked", razon="pendiente_dictamen", incidente=inc)
    # Cabeza firmada ⇒ habitable: las no habitables salieron en la regla 1.
    if inc.dictamen_at is not None and _hace_s(ahora, inc.dictamen_at) < ventana_firma_s:
        return Reingreso(fase="reentry_approved", incidente=inc)
    return _IDLE
