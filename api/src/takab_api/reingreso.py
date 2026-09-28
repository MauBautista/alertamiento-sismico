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
1b. [F3·r2 · D-43] **Un ROJO de la regla SIN FIRMAR** (sólo filas v2, ``band =
   'rojo'``) ⇒ `reentry_blocked`/``pendiente_dictamen`` citando ese incidente, sin
   cota de edad y por encima de la regla 2: un daño tardío subió la banda del sismo
   principal y una réplica cerrada después con VERDE firmado no lo inspeccionó.
   ⚠️ **La falta de cota de edad es DECISIÓN DECLARADA, no un olvido** (D-43,
   F3·r3). La cota del ``lookback`` de la regla 2 existe para que un incidente que
   nadie dictaminó no bloquee para siempre; la 1b NO la lleva a propósito: un ROJO
   de la regla dice que la PGA o un daño reportado cruzaron el umbral de «no
   habitar», y eso no se vuelve habitable porque pase el tiempo. Falla del lado
   seguro (deja a alguien fuera, nunca lo mete) y **sólo la firma de un inspector
   lo levanta**: ni el sistema ni una confirmación pueden firmar un ROJO. Un SASMEX
   con PGA ≥ 0,10 g cerrado por TTL sin inspección sigue en ``pendiente_dictamen``
   meses después, y eso es lo que se quiere.
   Las reglas 1 y 1b viven en ``bloqueo_persistente`` y **también rigen con un
   incidente ABIERTO** (``mobile_site``): el VERDE de la réplica abierta no tapa el
   ROJO del principal.
1c. [D-49 · R2] **Un AMARILLO de la regla SIN CONFIRMAR** (sólo filas v2, ``band =
   'amarillo'``) de CUALQUIER incidente que cuente ⇒ `reentry_blocked`/
   ``pendiente_confirmacion`` citando ese incidente, **sin caducidad a propósito**
   (como la 1b) y por debajo de la 1 y la 1b: el VERDE que el sistema firma en una
   réplica no dice que alguien confirmó el AMARILLO del sismo principal. Sólo lo
   levanta una confirmación o una firma sobre ESE incidente.
1d. [D-49 · R5] **Una ESCALADA al inspector SIN ATENDER** (acción ``dictamen_request``
   sin firma HUMANA posterior —inspector o confirmación; las firmas anteriores a la
   0073, sin tipo, cuentan como inspector—) de CUALQUIER incidente que cuente ⇒
   `reentry_blocked`/``pendiente_dictamen`` citando ese incidente, sin caducidad y
   por debajo de la 1, 1b y 1c. Medido en la ronda 4: la escalada sólo frenaba el
   VERDE del sistema de SU incidente, y el VERDE que el sistema firma en la réplica
   liberaba el reingreso con la brigada esperando a su inspector. También rige sobre
   el propio incidente ABIERTO: una petición posterior a su firma habitable la deja
   en suspenso. La levanta cualquier firma humana posterior (R3: la confirmación de
   la brigada también). El VERDE del sistema NO la levanta.
3. Nada de lo anterior ⇒ `idle`.

**[D-49 · R1] Sin calma no hay reingreso.** Ninguna firma —sistema, confirmación
ni inspector— produce `reentry_approved` si el último tier del sitio no es
``normal`` (``en_calma``). La regla entera, con y sin incidente abierto, la aplica
``decide_reingreso``: es la ÚNICA puerta que usa ``mobile_state`` en sus dos ramas.

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

[T-9.32 · D-43] ``pendiente_confirmacion``: la cabeza del candidato está SIN
firmar y su banda (columna ``dictamens.band``) es ``amarillo`` — la regla
``dictamen-v2`` dijo «habitable con vigilancia» y falta que la brigada, el
inspector o la administración lo CONFIRMEN. Sin banda (fila histórica) o con un
ROJO sin firmar sigue siendo ``pendiente_dictamen``. Desde D-43 firmar ya no
cierra el incidente por sí solo (hace falta además la clasificación), pero el
veredicto sigue sobreviviendo al cierre exactamente igual.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
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
    #: [T-9.30 · D-43] Banda de la cabeza (``verde``/``amarillo``/``rojo``); ``None``
    #: en filas anteriores a la 0073. Sólo decide ``pendiente_confirmacion``.
    dictamen_band: str | None = None
    #: [D-49 · R5] ¿Tiene una ``dictamen_request`` que ninguna firma HUMANA posterior
    #: atendió (``sistema.ATIENDE_ESCALADA_SQL``)? Regla 1d.
    escalada_pendiente: bool = False


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


def bloqueo_persistente(
    incidentes: Sequence[IncidenteCerrado], *, min_nodes: int
) -> Reingreso | None:
    """Reglas 1, 1b, 1c y 1d: el bloqueo que NO caduca, o ``None`` si no hay ninguno.

    [F3·r3 · D-43 · D-49] Es la ÚNICA copia de esas tres reglas. La usa ``deriva_reingreso``
    (sin incidente abierto que autorice) y también la rama del incidente ABIERTO de
    ``mobile_site``: un VERDE firmado en la réplica abierta no puede liberar el
    reingreso si el sismo principal —abierto o cerrado— tiene un NO HABITAR firmado
    vigente o un ROJO de la regla sin firmar. ``incidentes`` en cualquier orden y con
    duplicados; los que no cuentan (no ordenaron evacuar, o terminales) se descartan
    aquí.
    """
    cuentan = [inc for inc in incidentes if _cuenta(inc, min_nodes)]

    # 1 · NO HABITAR vigente: precedencia sobre todo, sin caducidad.
    bloqueantes = [inc for inc in cuentan if _no_habitable_vigente(inc)]
    if bloqueantes:
        cita = max(
            bloqueantes,
            key=lambda i: (i.dictamen_at or i.opened_at, i.opened_at, str(i.incident_id)),
        )
        return Reingreso(fase="reentry_blocked", razon="no_habitable", incidente=cita)

    # 1b · [F3·r2 · D-43] ROJO de la regla SIN FIRMAR: la prudencia subió sola (un
    # daño tardío sobre el sismo principal) y nadie la ha inspeccionado. Sin cota de
    # edad y por encima de la regla 2: una réplica cerrada después con un VERDE
    # firmado NO dice que el daño de éste se inspeccionó. SÓLO filas v2 (``band =
    # 'rojo'``): las v1 no tienen banda, y un SASMEX viejo con su preliminar sin
    # firmar bloquearía el edificio para siempre.
    rojos = [inc for inc in cuentan if not inc.dictamen_firmado and inc.dictamen_band == "rojo"]
    if rojos:
        cita = max(
            rojos,
            key=lambda i: (i.dictamen_at or i.opened_at, i.opened_at, str(i.incident_id)),
        )
        return Reingreso(fase="reentry_blocked", razon="pendiente_dictamen", incidente=cita)

    # 1c · [D-49 · R2] AMARILLO de la regla SIN CONFIRMAR: bloqueo persistente, SIN
    # caducidad y de CUALQUIER incidente que cuente. Medido en la ronda 3: el VERDE
    # que el sistema firma en la réplica (su PGA y sus daños son otros) liberaba el
    # reingreso con el AMARILLO del sismo principal sin que nadie lo confirmara, y
    # D-43 exige una persona detrás de cada AMARILLO. Sólo lo levanta una
    # confirmación o una firma sobre ESE incidente. SÓLO filas v2 (``band =
    # 'amarillo'``): las v1 no tienen banda y no bloquean.
    amarillos = [
        inc for inc in cuentan if not inc.dictamen_firmado and inc.dictamen_band == "amarillo"
    ]
    if amarillos:
        cita = max(
            amarillos,
            key=lambda i: (i.dictamen_at or i.opened_at, i.opened_at, str(i.incident_id)),
        )
        return Reingreso(fase="reentry_blocked", razon="pendiente_confirmacion", incidente=cita)

    # 1d · [D-49 · R5] ESCALADA al inspector SIN ATENDER: la brigada pidió que viniera
    # una persona y nadie firmó después. Sin caducidad y de CUALQUIER incidente que
    # cuente: el VERDE del sistema en la réplica no es la inspección que se pidió.
    escalados = [inc for inc in cuentan if inc.escalada_pendiente]
    if escalados:
        cita = max(
            escalados,
            key=lambda i: (i.dictamen_at or i.opened_at, i.opened_at, str(i.incident_id)),
        )
        return Reingreso(fase="reentry_blocked", razon="pendiente_dictamen", incidente=cita)

    return None


def en_calma(tier: str | None) -> bool:
    """[D-49 · R1] ¿El edificio dejó de moverse? El último tier del sitio es ``normal``.

    ÚNICA copia del criterio para el reingreso y para la confirmación. Sin ninguna
    evaluación el tier es ``normal`` —mismo criterio que ``incident/lifecycle`` y la
    gracia del VERDE del sistema (``dictamen/service._gracia_cumplida``)—: un sitio
    que nunca reportó una transición no está sacudiéndose."""
    return tier is None or tier == "normal"


def decide_reingreso(
    incidentes: Sequence[IncidenteCerrado],
    *,
    abierto: IncidenteCerrado | None,
    tier: str | None,
    ahora: datetime,
    min_nodes: int,
    ventana_firma_s: float,
    lookback_pendiente_s: float,
) -> Reingreso | None:
    """[D-49] LA regla del reingreso, para las DOS ramas de ``mobile_state``.

    * ``abierto`` = el incidente ABIERTO que autoriza evacuar (con su cabeza), o
      ``None``. Con él, ``None`` de vuelta significa «manda la alerta del abierto»
      (``alert_active``/``shaking_concluded``): sólo una cabeza habitable FIRMADA
      del abierto puede proponer algo, y
      1. **R1** — sin calma (``en_calma(tier)`` falso) no se autoriza: manda la
         alerta, ninguna firma (sistema, confirmación, inspector) lo cambia;
      2. los bloqueos persistentes de OTROS incidentes (1, 1b, 1c, 1d) mandan, y
         la 1d también por una escalada sin atender del PROPIO abierto (R5);
      3. si no, ``reentry_approved``.
    * Sin ``abierto``: ``deriva_reingreso`` sobre los cerrados, y R1 convierte una
      autorización en ``reentry_blocked`` sin razón (el edificio se mueve; ninguna
      de las razones del contrato lo describe y ``blocked`` es lo que lee la app).

    ``tier`` se lee UNA vez por petición (el router) y llega aquí.
    """
    if abierto is None:
        r = deriva_reingreso(
            incidentes,
            ahora=ahora,
            min_nodes=min_nodes,
            ventana_firma_s=ventana_firma_s,
            lookback_pendiente_s=lookback_pendiente_s,
        )
        if r.fase == "reentry_approved" and not en_calma(tier):
            return Reingreso(fase="reentry_blocked", incidente=r.incidente)
        return r
    if not (abierto.dictamen_firmado and abierto.dictamen_status in HABITABLES):
        return None
    if not en_calma(tier):
        return None
    otros = [inc for inc in incidentes if inc.incident_id != abierto.incident_id]
    # [D-49 · R5] La escalada del PROPIO abierto (su fila puede venir en ``incidentes``:
    # la consulta de escaladas no distingue abiertos de cerrados). Su cabeza es
    # habitable firmada, así que en ``bloqueo_persistente`` sólo puede entrar por la
    # 1d, y la precedencia 1 > 1b > 1c > 1d la decide esa misma función.
    if abierto.escalada_pendiente or any(
        inc.incident_id == abierto.incident_id and inc.escalada_pendiente for inc in incidentes
    ):
        otros.append(
            abierto if abierto.escalada_pendiente else replace(abierto, escalada_pendiente=True)
        )
    bloqueo = bloqueo_persistente(otros, min_nodes=min_nodes)
    if bloqueo is not None:
        return bloqueo
    return Reingreso(fase="reentry_approved", incidente=abierto)


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
    bloqueo = bloqueo_persistente(cerrados, min_nodes=min_nodes)
    if bloqueo is not None:
        return bloqueo
    cuentan = [inc for inc in cerrados if _cuenta(inc, min_nodes)]

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
        # [T-9.32 · D-43] Un AMARILLO de la regla sólo espera a que alguien lo
        # confirme; cualquier otra cosa sin firmar espera un dictamen.
        razon: RazonBloqueo = (
            "pendiente_confirmacion" if inc.dictamen_band == "amarillo" else "pendiente_dictamen"
        )
        return Reingreso(fase="reentry_blocked", razon=razon, incidente=inc)
    # Cabeza firmada ⇒ habitable: las no habitables salieron en la regla 1.
    if inc.dictamen_at is not None and _hace_s(ahora, inc.dictamen_at) < ventana_firma_s:
        return Reingreso(fase="reentry_approved", incidente=inc)
    return _IDLE
