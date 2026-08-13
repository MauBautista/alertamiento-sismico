"""Estado derivado de la flota edge (T-1.22 · B1/G7).

``derive_fleet_state`` es la VERDAD ÚNICA del estado de un gateway: se calcula
server-side a partir del último ``device_health`` y los umbrales de ``settings``.
La UI (T-1.28) solo pinta el resultado; jamás recalcula. Función pura → testeable
con filas fixture sin DB.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Estados posibles (strings de UI en español, tal cual los pinta el SOC).
OPERATIVO = "OPERATIVO"
DEGRADADO = "DEGRADADO"
SIN_ENLACE = "SIN ENLACE"

# --------------------------------------------------------------------------
# [T-2.70.a·B1] Censo de relés del último latido (`device_health.relays_state`)
# --------------------------------------------------------------------------
#: El gabinete publicó el estado de sus relés.
RELAYS_REPORTED = "reported"
#: Preguntó al dueño de los pines y no hay filas (módulo detenido / sin relés).
RELAYS_STOPPED = "stopped"
#: **No pudo preguntar**: nadie contesta como dueño de los pines.
RELAYS_UNREADABLE = "unreadable"
#: Pill de la UI. Es la ÚNICA señal que delata a un gabinete con
#: `gpio_owner=gpio` y `takab-gpio` caído: sin sirena, sin cierre de gas, sin
#: retorno de ascensores y sin retenedores, con `takab-edge` latiendo cada 60 s y
#: todas las demás métricas en verde.
#:
#: [T-2.85.b · deuda 2 · 2026-08-13] Decía ``RELÉS ILEGIBLES``. Es el MISMO
#: hecho que el panel del gabinete rotula ``NO CONTESTA`` —el módulo que
#: gobierna los relés no responde—, y quien opera mira LAS DOS pantallas: la del
#: Pi en el sitio y ésta desde el SOC, o al revés en plena madrugada. Cada
#: traducción que hace de cabeza bajo presión es un sitio donde se equivoca.
#: El vocabulario único vive en ``shared/glossary/estados.json`` (eje
#: ``pieza_muda``) y lo vigila ``web/src/features/fleet/estadoGlosario.test.ts``,
#: que LEE esta constante en vez de copiarla.
#:
#: El prefijo ``RELÉS ·`` se conserva a propósito: ``degrade_reasons`` es una
#: lista de pills sin más contexto, y un ``NO CONTESTA`` a secas junto a
#: ``EN BATERÍA`` no dice QUÉ es lo que no contesta.
RELAYS_ILEGIBLES = "RELÉS · NO CONTESTA"


def derive_fleet_state(
    *,
    age_s: float | None,
    power_status: str | None,
    battery_pct: float | None,
    cert_days_remaining: int | None,
    mqtt_rtt_ms: float | None,
    seedlink_lag_s: float | None,
    ntp_offset_ms: float | None,
    sin_enlace_s: float,
    relays_state: str | None = None,
    battery_min_pct: float,
    cert_min_days: int,
    mqtt_rtt_max_ms: float,
    seedlink_lag_max_s: float,
    ntp_offset_max_ms: float,
) -> str:
    """Deriva ``OPERATIVO`` | ``DEGRADADO`` | ``SIN ENLACE``.

    - ``SIN ENLACE``: sin heartbeat (``age_s is None``) o el último es más viejo
      que ``sin_enlace_s`` (el gateway dejó de reportar).
    - ``DEGRADADO``: con enlace vivo pero alguna métrica fuera de rango.
    - ``OPERATIVO``: con enlace y todas las métricas sanas.

    Una métrica ``None`` («sin dato», contrato honesto de T-1.40) NUNCA degrada:
    no tener UPS no es lo mismo que estar en batería.

    [T-2.70.a·B1] ``relays_state`` es la excepción aparente y no lo es: lo que
    degrada no es la AUSENCIA del dato sino la afirmación ``unreadable``, que es
    el gabinete diciendo *«no pude preguntar quién gobierna la sirena»*. Ver
    ``fleet_degrade_reasons``.

    El orden importa: ``SIN ENLACE`` sigue mandando. El censo de relés de un
    gabinete que lleva horas callado es un dato viejo y no describe lo que pasa
    ahora — misma doctrina que ``derive_version_drift`` (T-2.69).
    """
    if age_s is None or age_s > sin_enlace_s:
        return SIN_ENLACE
    reasons = fleet_degrade_reasons(
        power_status=power_status,
        battery_pct=battery_pct,
        cert_days_remaining=cert_days_remaining,
        mqtt_rtt_ms=mqtt_rtt_ms,
        seedlink_lag_s=seedlink_lag_s,
        ntp_offset_ms=ntp_offset_ms,
        relays_state=relays_state,
        battery_min_pct=battery_min_pct,
        cert_min_days=cert_min_days,
        mqtt_rtt_max_ms=mqtt_rtt_max_ms,
        seedlink_lag_max_s=seedlink_lag_max_s,
        ntp_offset_max_ms=ntp_offset_max_ms,
    )
    return DEGRADADO if reasons else OPERATIVO


def fleet_degrade_reasons(
    *,
    power_status: str | None,
    battery_pct: float | None,
    cert_days_remaining: int | None,
    mqtt_rtt_ms: float | None,
    seedlink_lag_s: float | None,
    ntp_offset_ms: float | None,
    relays_state: str | None = None,
    battery_min_pct: float,
    cert_min_days: int,
    mqtt_rtt_max_ms: float,
    seedlink_lag_max_s: float,
    ntp_offset_max_ms: float,
) -> list[str]:
    """QUÉ métrica degrada, en el idioma de la UI (T-1.40, backlog de T-1.28).

    Es la MISMA verdad que ``derive_fleet_state`` (que la llama): si esta lista
    no está vacía, el estado es DEGRADADO. La UI pinta cada razón como pill en
    vez de dejar al operador adivinar cuál de seis métricas se salió de rango.

    **[T-2.70.a·B1] ``RELÉS · NO CONTESTA``, y por qué SÓLO ``unreadable``.** Desde
    que D3 sacó al dueño de los pines a `takab-gpio`, un gabinete con
    `gpio_owner=gpio` y ese proceso caído se queda sin sirena, sin cierre de gas,
    sin retorno de ascensores y sin retenedores **mientras `takab-edge` late cada
    60 s con todas estas métricas perfectas**. Ninguna alarma lo veía;
    `gateway_offline` tampoco, porque el que late está vivo. Este es el único
    campo que lo delata, y por eso tiene que degradar: sin degradar, la tarjeta
    del SOC se pinta verde y el operador no tiene motivo para abrirla.

    Los otros dos valores NO degradan, y la razón es la honestidad, no la
    prudencia:

    · ``stopped`` (``relays: []``) es **ambiguo en firmware ≤1.9.0**, que no sabe
      emitir el ``null``: su `[]` puede ser «módulo detenido» o «lectura fallida»
      y no hay forma de saberlo desde aquí. Degradar sobre un dato ambiguo pinta
      de ámbar a la flota vieja sin saber si le pasa algo, y una pantalla que
      grita sin motivo enseña a no mirarla. Se registra y la consola lo pinta
      S/D — que no es verde.
    · ``None`` es ausencia de opinión (misma disciplina que ``fw_running``): el
      gabinete no habla de relés. Ausencia nunca es diagnóstico.
    """
    reasons: list[str] = []
    if relays_state == RELAYS_UNREADABLE:
        reasons.append(RELAYS_ILEGIBLES)
    if power_status == "battery":
        reasons.append("EN BATERÍA")
    if battery_pct is not None and battery_pct < battery_min_pct:
        reasons.append(f"BATERÍA {battery_pct:.0f}%")
    if cert_days_remaining is not None and cert_days_remaining < cert_min_days:
        reasons.append(f"CERT {cert_days_remaining}d")
    if mqtt_rtt_ms is not None and mqtt_rtt_ms > mqtt_rtt_max_ms:
        reasons.append(f"MQTT {mqtt_rtt_ms:.0f}ms")
    if seedlink_lag_s is not None and seedlink_lag_s > seedlink_lag_max_s:
        reasons.append(f"SEEDLINK {seedlink_lag_s:.1f}s")
    if ntp_offset_ms is not None and abs(ntp_offset_ms) > ntp_offset_max_ms:
        reasons.append(f"NTP {ntp_offset_ms:+.0f}ms")
    return reasons


# --------------------------------------------------------------------------
# T-2.69 · Inventario de versiones: qué corre cada gabinete y cuánto se quedó atrás
# --------------------------------------------------------------------------

#: Nunca declaró versión y nunca latió. Recién dado de alta, o jamás conectado.
VERSION_SIN_REPORTAR = "SIN REPORTAR"
#: Late, y declara honestamente que NO SABE qué versión corre (`FW_VERSION`
#: borrado por un `rsync --delete` a medias, un reaprovisionamiento, un archivo
#: ilegible). Es un HECHO, no un silencio.
VERSION_NO_DECLARA = "NO DECLARA"
#: Hay una versión guardada, pero el gabinete lleva más de `sin_enlace_s` callado.
#: Lo que la consola tiene es la ÚLTIMA que reportó, NO la que corre.
VERSION_ULTIMA_CONOCIDA = "ÚLTIMA CONOCIDA"
#: Se sabe qué corre, pero no hay registro de releases contra el cual medirlo.
VERSION_SIN_REFERENCIA = "SIN REFERENCIA"
#: Corre algo que NO figura en el registro. Contradicción, no ausencia.
VERSION_DESCONOCIDA = "DESCONOCIDA"
VERSION_AL_DIA = "AL DÍA"
VERSION_ATRASADA = "ATRASADA"
#: [T-2.70] El código nuevo ESTÁ EN EL DISCO y el proceso sigue con el viejo.
#: No es «atrasada» (ahí falta desplegar) ni «al día» (ahí no falta nada): falta
#: que el reinicio ocurra o que alguien mire por qué no ocurrió.
VERSION_SIN_REINICIAR = "SIN REINICIAR"


class ReleaseRef(BaseModel):
    """Un release publicado, tal y como lo devuelve ``queries.fw_releases``.

    ``age_s`` es la antigüedad de la PUBLICACIÓN (no la del gabinete): con ella
    "cuánto lleva corriendo código viejo" se responde en la moneda que el
    operador entiende, sin que el cliente tenga que restar relojes.
    """

    version: str
    age_s: float | None = None


class VersionDrift(BaseModel):
    """Qué versión corre un gabinete y cuánto se ha quedado atrás (verdad única).

    ``releases_behind`` es la ÚNICA medida de "cuánto atrás" que se puede calcular
    honestamente: los SHAs de 7 hex que produce ``deploy/edge/deploy.sh`` no son
    ordenables, y la nube no tiene el repo git para contar commits. Vale ``None``
    siempre que la versión no figure en el registro (o no haya versión): decir 0
    ahí sería afirmar "al día" sobre algo que nadie publicó.
    """

    state: str
    releases_behind: int | None = None
    release_age_s: float | None = None


def derive_version_drift(
    *,
    fw_version: str | None,
    age_s: float | None,
    sin_enlace_s: float,
    releases: Sequence[ReleaseRef],
    fw_running: str | None = None,
) -> VersionDrift:
    """Deriva el estado de versión de UN gabinete. Función pura (sin DB, sin reloj).

    ``releases`` llega ORDENADO del más nuevo al más antiguo (así lo devuelve la
    query); el índice dentro de esa lista **es** ``releases_behind``.

    El orden de las guardas no es casual — va de lo que impide saber a lo que
    permite comparar:

    1. **Sin versión** ⇒ ``SIN REPORTAR`` (nunca latió) o ``NO DECLARA`` (late y
       dice que no sabe). Dos causas distintas, dos rótulos distintos: un ``S/D``
       genérico volvería a fundirlas y el operador no sabría a quién llamar.
    2. **Versión pero sin enlace** ⇒ ``ÚLTIMA CONOCIDA``. **Este es el criterio 3
       de T-2.69 y el defecto del 14-jul**: un gabinete callado tres semanas pudo
       ser reflasheado, apagado o robado. Lo guardado es la última versión que
       reportó, jamás "la que corre". Se comprueba ANTES que el registro, porque
       ninguna coincidencia con el último release rescata un dato viejo.
    3. **Sin registro** ⇒ ``SIN REFERENCIA``: se sabe qué corre, no si es lo
       actual. Culpar al gabinete (``DESCONOCIDA``) por un vacío de la plataforma
       sería mandar al operador a arreglar lo que no era.
    4. **Fuera del registro** ⇒ ``DESCONOCIDA``. Aquí caen los ``-dirty`` que
       ``deploy.sh`` produce a propósito con el árbol sucio: la comparación es por
       IGUALDAD EXACTA, así que ``62f3f1e-dirty`` no es ``62f3f1e``.
    5. **[T-2.70] Disco ≠ proceso** ⇒ ``SIN REINICIAR``. Ver abajo.
    6. Y solo entonces, ``AL DÍA`` / ``ATRASADA``.

    ``releases_behind`` sí se calcula en ``ÚLTIMA CONOCIDA``: quien planifica una
    ola de actualización (T-2.70) necesita saber qué se quedó atrás aunque hoy no
    pueda alcanzarlo. La honestidad la carga el rótulo, no el número.

    **[T-2.70] Por qué la deriva se mide contra ``fw_running`` y no contra
    ``fw_version``.** ``fw_version`` es lo que el gabinete lee de su archivo
    ``FW_VERSION`` en cada latido, y `deploy/edge/deploy.sh` lo escribe (L44)
    ANTES de reiniciar (L61) — tiene que ser en ese orden, porque el
    ``rsync --delete`` de la L31 lo borraría si se escribiera antes. Entre esas
    dos líneas, y **para siempre** si el ``uv sync`` revienta o la unidad agota
    su ``StartLimitBurst`` y queda en ``failed``, el disco ya tiene el código
    nuevo y el proceso sigue ejecutando el viejo.

    Medir contra el disco diría ``AL DÍA`` sobre un gabinete que no aplicó nada.
    Por eso el número describe lo que CORRE y el rótulo ``SIN REINICIAR`` nombra
    la causa: no falta desplegar (eso es ``ATRASADA``, y se arregla desplegando),
    falta que el reinicio ocurra — o que alguien mire por qué no ocurrió.

    ``fw_running=None`` es **ausencia de opinión**, no desajuste: los gabinetes
    con contrato ≤1.8.0 no mandan el campo, y leerlo como discrepancia marcaría
    ``SIN REINICIAR`` a toda la flota vieja de golpe.
    """
    if fw_version is None:
        # Sin versión de disco no hay dos cosas que comparar, aunque `fw_running`
        # traiga algo: el hecho que manda sigue siendo que no declara versión.
        return VersionDrift(state=VERSION_SIN_REPORTAR if age_s is None else VERSION_NO_DECLARA)
    # Lo que el gabinete EJECUTA; a falta de ese dato (contrato viejo), lo del disco.
    efectiva = fw_version if fw_running is None else fw_running
    known = next((r for r in releases if r.version == efectiva), None)
    behind = next((i for i, r in enumerate(releases) if r.version == efectiva), None)
    age = None if known is None else known.age_s
    if age_s is None or age_s > sin_enlace_s:
        # ANTES que el desajuste: un gabinete callado tres semanas pudo
        # reiniciarse, romperse o ser robado. Diagnosticar «SIN REINICIAR» sobre
        # un dato viejo sería mandar a alguien a arreglar lo que quizá ya no está.
        return VersionDrift(
            state=VERSION_ULTIMA_CONOCIDA, releases_behind=behind, release_age_s=age
        )
    if fw_running is not None and fw_running != fw_version:
        return VersionDrift(state=VERSION_SIN_REINICIAR, releases_behind=behind, release_age_s=age)
    if not releases:
        return VersionDrift(state=VERSION_SIN_REFERENCIA)
    if behind is None:
        return VersionDrift(state=VERSION_DESCONOCIDA)
    return VersionDrift(
        state=VERSION_AL_DIA if behind == 0 else VERSION_ATRASADA,
        releases_behind=behind,
        release_age_s=age,
    )


class ReleaseOut(BaseModel):
    """Un release del registro de plataforma (``GET /fleet/releases``)."""

    release_id: UUID
    version: str
    released_at: datetime
    age_s: float | None = None
    notes: str | None = None
    published_by: str | None = None


class ReleaseCreate(BaseModel):
    """Publicar un release en el registro (``POST /fleet/releases``).

    ``version`` es el valor que ``deploy/edge/deploy.sh`` escribirá en el
    ``FW_VERSION`` del gabinete, y la comparación con lo que el aparato declara es
    por IGUALDAD EXACTA. Se recorta el espacio en blanco por la MISMA razón por la
    que lo recortan las dos puntas del otro camino —``edge/takab_edge/version.py``
    al leer el archivo y ``ingest/handlers.py`` al recibir el latido—: si aquí no
    se recortara, un ``"62f3f1e "` pegado desde una terminal quedaría en el
    registro para siempre (la tabla no admite UPDATE) sin poder coincidir JAMÁS
    con ningún gabinete, y toda la flota que corriera ese código saldría
    ``DESCONOCIDA``. Dos normalizaciones que no coinciden son un fallo silencioso;
    el ``max_length`` también es el mismo (64) que el de la ingesta.

    ``released_at`` se puede fijar para dar de alta releases ya desplegados sin
    falsear su antigüedad (corregirla después sería imposible).
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=64)
    released_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("version")
    @classmethod
    def _trim(cls, v: str) -> str:
        version = v.strip()
        if not version:
            raise ValueError("version vacía")
        return version


def sig_fingerprint(sig: str | None) -> str | None:
    """Huella corta de la firma HMAC publicada.

    La firma cruda NUNCA sale del servidor: junto al payload sería material de
    ataque offline contra la clave. La huella basta para que el operador vea que
    dos gabinetes traen la misma config firmada.
    """
    if not sig:
        return None
    return hashlib.sha256(sig.encode()).hexdigest()[:12]


class GatewayConfigStateOut(BaseModel):
    """Estado del config firmado que el gateway tiene REALMENTE (T-1.30 · C4).

    ``publish`` solo registra la intención (202 ``pending_sync``); quien firma y
    entrega es el worker de T-1.23. Este modelo es lo único que autoriza a la
    consola a decir "SINCRONIZADO" en vez de "PENDIENTE".

    - ``in_sync``: el payload publicado coincide con el documento que el worker
      volvería a publicar (``config.edge`` fusionado con ``equipment`` y
      ``cloud_admin_state``). Es la negación del predicado de publicación.
    - ``has_edge_config``: hay un documento que publicarle. [B3] Es el espejo del
      gate de publicación del worker (``base IS NOT NULL``), no "el rule_set
      activo trae bloque ``edge``": el worker también recompone la base desde el
      último doc publicado, así que un rule_set inactivo NO implica que no haya
      nada que mandar. Falso ⇒ no se publicará nunca —ni rule_set con ``edge`` ni
      doc anterior del que partir— y pintar PENDIENTE para siempre sería mentir.
    - ``is_syncable``: el gateway PUEDE recibir config firmada — tiene ``iot_thing``
      y no está retirado *y ya avisado*. [T-2.65] Un gabinete recién retirado sigue
      siendo sincronizable hasta que reciba su último sobre, el que le declara la
      baja: sacarlo de la lista ANTES de avisarle es justo el defecto que dejaba al
      gabinete latiendo invisible. Recibido el sobre, deja el flujo de config.
    - ``version``/``published_at``: los del último documento firmado; ``None`` si
      nunca se publicó.
    """

    gateway_id: UUID
    version: int | None = None
    published_at: datetime | None = None
    sig_fingerprint: str | None = None
    in_sync: bool
    has_edge_config: bool
    is_syncable: bool


class EquipmentProfile(BaseModel):
    """[T-2.31] Actuadores INSTALADOS físicamente en el sitio del gabinete.

    No toda estación tiene gas/ascensores/puertas. Contrato: 5 bools, default
    todo-true (la flota existente no cambia de conducta), claves desconocidas
    rechazadas — un typo en 'gas_valve' no puede volverse "instalado" silencioso.
    Viaja al edge FUSIONADO en el doc firmado del config sync (una sola firma
    cubre config + equipamiento).
    """

    model_config = ConfigDict(extra="forbid")

    siren: bool = True
    strobe: bool = True
    gas_valve: bool = True
    elevator: bool = True
    door_retainer: bool = True


class GatewayOut(BaseModel):
    """Gateway del tenant + estado derivado del último ``device_health``.

    [T-2.35] ``site_name``/``site_code``/``site_status`` los pone el SERVIDOR. La web
    los resolvía haciendo join contra ``/sites``, que oculta los retirados: un gabinete
    huérfano perdía su nombre y la UI lo rebautizaba ``SITIO <8 hex>``, de modo que dos
    huérfanos distintos se veían idénticos. Con el nombre en la fila no hay fallback que
    inventar — la clase de bug entera desaparece.
    """

    gateway_id: UUID
    site_id: UUID
    site_name: str
    site_code: str
    site_status: str
    serial: str
    fw_version: str | None = None
    # [T-2.70] Qué código EJECUTA el proceso (congelado al arrancar), frente al
    # `fw_version` de arriba, que es el que hay EN EL DISCO. Viaja crudo además
    # del `version_state` derivado porque cuando difieren el operador necesita
    # ver AMBOS SHAs para saber qué quedó escrito sin aplicarse. `None` = el
    # gabinete no lo declara (contrato ≤1.8.0) o no lo sabe.
    fw_running: str | None = None
    iot_thing: str | None = None
    status: str
    has_wr1: bool
    equipment: EquipmentProfile = Field(default_factory=EquipmentProfile)
    installed_at: datetime | None = None
    row_version: str
    derived_state: str
    # QUÉ degrada (vacía salvo en DEGRADADO): pills de la UI, misma verdad que
    # derive_fleet_state (T-1.40).
    degrade_reasons: list[str] = []
    last_heartbeat_ts: datetime | None = None
    power_status: str | None = None
    battery_pct: float | None = None
    cert_days_remaining: int | None = None
    mqtt_rtt_ms: float | None = None
    seedlink_lag_s: float | None = None
    ntp_offset_ms: float | None = None
    # [T-2.70.a·B1] Si el gabinete pudo leer el censo de sus relés en el ÚLTIMO
    # latido: `reported` · `stopped` · `unreadable` · `None` (no opina). Viaja
    # crudo además de la pill `RELÉS · NO CONTESTA` porque la consola necesita los
    # cuatro casos, no sólo el que degrada: con `stopped` y con `None` los
    # actuadores se pintan **S/D**, jamás ARMADO. Hasta esta tarea el grid de
    # relés derivaba `armed` de que el enlace estuviera vivo, así que un gabinete
    # sin dueño de pines —que late perfectamente— mostraba sus cinco actuadores
    # en ARMADO. Regla de oro 7: un dato que no se pudo obtener no se pinta bueno.
    relays_state: str | None = None
    # [T-2.60.a] Retirado PERO sigue latiendo. No es un estado más del gabinete:
    # es una CONTRADICCIÓN entre lo que la organización cree (dado de baja) y lo
    # que el aparato hace (reportar). Por eso va aparte de `status` y de
    # `derived_state`, que siguen diciendo cada uno su verdad sin mezclarse.
    #
    # Exige acción humana en una de las dos direcciones —desmontarlo de verdad o
    # restaurarlo—, y hasta entonces hay un edificio cuya supervisión nadie mira.
    is_ghost: bool = False
    # Cuándo y quién, para no obligar a irse a la auditoría a mano. `None` cuando
    # no está retirado, y también cuando lo está pero la bitácora no lo recoge
    # (p. ej. un retiro hecho por SQL): ahí el fantasma se delata igual, solo que
    # sin quién — mejor eso que callarse por falta de un dato accesorio.
    retired_at: datetime | None = None
    retired_by: str | None = None
    # [T-2.69] Inventario de versiones. `fw_version` de arriba dice QUÉ declaró el
    # gabinete la última vez; estos cuatro campos dicen si eso sigue siendo cierto
    # y cuánto se ha quedado atrás. Se derivan server-side (misma disciplina que
    # `derived_state`): la UI solo pinta, y no hay una segunda opinión que pueda
    # divergir. Ver `derive_version_drift`.
    version_state: str = VERSION_SIN_REPORTAR
    releases_behind: int | None = None
    release_age_s: float | None = None
    # EDAD DEL DATO DE VERSIÓN, que NO es la edad del release ni un sinónimo
    # cosmético de `age_s`: es `None` cuando no hay versión que fechar, y por eso
    # la consola puede decir "S/D" en vez de pintar una antigüedad de un dato que
    # no existe. La versión cabalga en CADA latido, así que cuando hay versión su
    # edad es la del último latido.
    version_age_s: float | None = None


class HealthBucket(BaseModel):
    """Un tramo de la historia de salud. Todo opcional salvo el instante y la cuenta.

    Un bucket sin dato para una métrica vale ``None``, **nunca 0**: "no reportó RTT"
    y "reportó 0 ms" son hechos distintos y confundirlos pinta una línea plana que
    parece salud perfecta (regla de oro 7).
    """

    ts: datetime
    heartbeats: int
    mqtt_rtt_p95_ms: float | None = None
    seedlink_lag_max_s: float | None = None
    ntp_offset_abs_max_ms: float | None = None
    battery_min_pct: float | None = None


class GatewayHealthOut(BaseModel):
    """Historia de 24 h de un gabinete (T-2.38).

    ``heartbeat_completeness`` mide LATIDOS, no datos sísmicos: es la fracción de
    latidos periódicos recibidos frente a los esperados por la cadencia del edge. Se
    rotula así en la UI a propósito — la completitud de forma de onda exigiría contar
    la serie sísmica por segundo, y hoy no hay agregado que lo haga barato.
    """

    gateway_id: UUID
    buckets: list[HealthBucket] = []
    outages: int = 0
    downtime_s: float = 0.0
    last_outage_end: datetime | None = None
    heartbeat_completeness: float | None = None


class GatewayRowOut(BaseModel):
    """Fila cruda de ``gateways`` (respuesta de las mutaciones de T-1.32).

    Sin ``derived_state``: ese lo deriva ``derive_fleet_state`` del último
    ``device_health``, y un gabinete recién dado de alta todavía no tiene ninguno.
    Inventarle "OPERATIVO" sería exactamente la clase de dato falso que prohíbe la
    regla de oro 7.
    """

    gateway_id: UUID
    tenant_id: UUID
    site_id: UUID
    serial: str
    fw_version: str | None = None
    iot_thing: str | None = None
    status: str
    has_wr1: bool
    equipment: EquipmentProfile = Field(default_factory=EquipmentProfile)
    installed_at: datetime | None = None
    row_version: str


class GatewayCreate(BaseModel):
    """Alta de gabinete. NO hay ``tenant_id``: se hereda del sitio (y RLS lo valida).

    La API **no llama a AWS**. Escribe la fila con ``status='provisioned'`` e
    ``iot_thing`` nulo salvo que el operador ya conozca el thing creado por Terraform
    (``infra/scripts/provision_gateway.sh``). Sin ``iot_thing`` el gabinete no es
    sincronizable, y la consola lo dice: PENDIENTE DE APROVISIONAR. Un endpoint HTTP
    que pudiera emitir certificados X.509 sería una superficie de ataque contra la
    identidad de los gabinetes.
    """

    model_config = ConfigDict(extra="forbid")

    site_id: UUID
    serial: str = Field(min_length=1, max_length=64)
    iot_thing: str | None = Field(default=None, max_length=128)
    has_wr1: bool = True
    equipment: EquipmentProfile = Field(default_factory=EquipmentProfile)
    installed_at: datetime | None = None


class GatewayUpdate(BaseModel):
    """Edición de gabinete. ``status`` y ``fw_version`` no aparecen a propósito.

    ``online``/``degraded``/``offline`` los deriva el heartbeat, no el operador; y
    ``retired`` se alcanza por ``DELETE``. Dejar que un formulario escribiera "online"
    haría que la Flota Edge mintiera sobre un gabinete muerto.

    [T-2.69] ``fw_version`` sale por la misma razón, y era el caso más grave. Este
    PUT es de REEMPLAZO TOTAL y la consola reenviaba el campo prellenado con CADA
    edición, así que cualquier operador podía anotar —o borrar— una versión que el
    gabinete nunca corrió. En un gabinete vivo el siguiente latido lo corregía en
    ≤60 s; en uno SIN ENLACE la mentira era PERMANENTE, y es justo ese sobre el que
    más importa saber la verdad. La versión la declara el aparato en cada latido
    (T-1.74) y ese es su ÚNICO escritor. ``extra='forbid'`` ⇒ un cliente viejo que
    lo mande recibe 422, no un silencio.
    """

    model_config = ConfigDict(extra="forbid")

    site_id: UUID
    serial: str = Field(min_length=1, max_length=64)
    iot_thing: str | None = Field(default=None, max_length=128)
    has_wr1: bool = True
    equipment: EquipmentProfile = Field(default_factory=EquipmentProfile)
    installed_at: datetime | None = None
    base_row_version: str | None = None
