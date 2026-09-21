"""[T-7.25] La pasada del worker: preguntarle a USGS por el incidente que entró en revisión.

QUÉ RESUELVE, Y POR QUÉ NO BASTABA CON LA 0060
──────────────────────────────────────────────
`shared/glossary/procedencia.json` nombra cinco estados, y uno de ellos
—``consultando``— **era inalcanzable**: `procedencia.de_fila()` lo deriva de una
fila de `reference_earthquakes`, y mientras la pregunta está en vuelo esa fila no
existe. Así que un timeout, un 5xx o un worker que muere a mitad se leían igual
que «nadie preguntó nunca». Esta pasada registra el INTENTO en
`catalog_consultations` **antes** de salir a la red, y de ahí sale el estado.

EL ORDEN ES EL MECANISMO
────────────────────────
1. Se escribe el intento y **se commitea**.
2. Se pregunta (fuera de toda transacción: una llamada HTTP dentro de una
   transacción abierta la mantiene viva tanto como tarde el tercero).
3. Se escribe el desenlace y se commitea.

Si el proceso muere entre (1) y (3), la fila queda con ``answered_at IS NULL`` y
la procedencia dice ``consultando``, que es exactamente lo que pasó. Hacerlo al
revés —una sola transacción al final— haría que morir a mitad fuera
indistinguible de no haber preguntado.

DÓNDE CORRE, Y DÓNDE NO
───────────────────────
En el worker de incidentes, **después** de la pasada de fases y con transacción
propia, como el resto de pasadas: un fallo aquí no puede revertir una
correlación, un dictamen ni un cierre ya escritos. Jamás en la ingesta: el camino
que abre un incidente por un pulso del WR-1 no se alarga (reglas de oro 1 y 4).
Su caída, su lentitud o la ausencia de internet no tocan al gabinete.

IDEMPOTENCIA (regla de oro 3)
─────────────────────────────
* La clave natural del intento es ``(incident_id, provider)``; ``asked_at`` no
  entra nunca en el `DO UPDATE`, así que reconsultar **no reescribe la fecha
  original**, que es la que se cita.
* La identidad de una fila del catálogo es ``(source, provider_event_id)``, y hay
  un índice único que lo impone. `catalog_key` es una clave NUESTRA que el worker
  no puede reproducir: si la identidad fuera ésa, reconsultar `us2000ar20` —que
  ya está sembrado como ``USGS-2017-09-19-PUE``— metería el Puebla-Morelos 2017
  dos veces.
* Un incidente con la consulta resuelta y ``confirmado`` no se vuelve a
  preguntar: la fuente ya declaró cuál es su solución. Se vuelve a preguntar en
  dos casos, y cada uno con su reloj —los dos sobre ``last_attempt_at``, nunca
  sobre ``asked_at``—: el que **no obtuvo respuesta**
  (``catalog_usgs_reintento_s``) y el que quedó **``preliminar``**
  (``catalog_usgs_refresco_preliminar_s``), porque «puede cambiar» es una
  afirmación con caducidad y el dictamen se firma dentro de esa ventana.
* Y un reintento que NO obtiene respuesta **no borra la respuesta anterior**:
  escribe por `_SIN_RESPUESTA_SQL`, que deja intactos ``answered_at`` y
  ``catalog_key``. Volver a preguntar puede mejorar un dato; nunca empeorarlo.

LO QUE LA PASADA LE CUESTA AL BUCLE (y por qué está acotado por reloj)
──────────────────────────────────────────────────────────────────────
El bucle del worker es serial: en la misma vuelta corren la correlación, la
reproducción, la actuación comandada por el quórum, el dictamen y las fases. Lo
que esta pasada tarda es lo que se retrasa **todo aquello**, así que su coste no
puede quedar en manos de un tercero. `catalog_usgs_presupuesto_s` lo acota: se
comprueba antes de CADA pregunta, con el timeout dentro de la cuenta, de modo
que el peor caso de la pasada es ese número (10 s) y no `máximo × timeout` (dos
minutos). Lo que no cabe se pregunta en la vuelta siguiente y el corte queda en
el log y en :class:`PasadaDeConsulta`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from takab_api import procedencia as pr
from takab_api.catalogo import fdsn
from takab_api.forensics import correlacion as corr

if TYPE_CHECKING:
    import psycopg

    from takab_api.settings import Settings

logger = logging.getLogger("takab_api.catalogo")

#: Clave del advisory lock de la pasada. A diferencia del resto de pasadas es de
#: SESIÓN y no de transacción: aquí se commitea varias veces (el intento antes de
#: la red, el desenlace después), y un `pg_advisory_xact_lock` se soltaría en el
#: primer commit dejando a otra instancia preguntando lo mismo a la vez.
#:
#: ⚠️ Y por ser de sesión, **soltarlo es responsabilidad del código**: nadie lo
#: suelta al terminar la transacción. Ver :func:`_suelta_el_cerrojo`, que existe
#: por eso y sólo por eso.
_CONSULTA_LOCK_KEY = 0x7A25

#: Tope de incidentes que se TRAEN en la pasada. Ya no es la cota del bloqueo
#: —de eso se ocupa `catalog_usgs_presupuesto_s`, que corta por reloj de pared
#: antes de cada pregunta—: es sólo una cota de la CONSULTA, para que un pico de
#: incidentes no traiga miles de filas a memoria. Los que sobren entran en la
#: siguiente pasada, que llega en segundos.
#:
#: ⚠️ Hasta T-7.25 este número SÍ era la cota, y era falsa: veinte llamadas
#: seriales de 6 s son dos minutos de bloqueo del bucle que sostiene la
#: actuación comandada por el quórum y la correlación.
_MAX_POR_PASADA = 20

#: Por qué la pasada dejó candidatos sin preguntar. Se distinguen porque quieren
#: decir cosas distintas: `tope` es «había más de los que se traen» y
#: `presupuesto` es «se acabó el reloj». Los dos son normales y ninguno es un
#: error; lo que no puede pasar es que no se digan.
CORTE_POR_TOPE = "tope"
CORTE_POR_PRESUPUESTO = "presupuesto"

#: Los tres desenlaces. Se IMPORTAN de `procedencia`, donde vive su otro extremo
#: —la derivación del estado que la UI pinta—, en vez de escribirlos aquí: dos
#: listas del mismo vocabulario acaban divergiendo, y la que divergiera dejaría al
#: worker escribiendo un desenlace que nadie sabe traducir.
CORRELACIONADO = pr.DESENLACE_CORRELACIONADO
SIN_CORRELACION = pr.DESENLACE_SIN_CORRELACION
SIN_RESPUESTA = pr.DESENLACE_SIN_RESPUESTA

#: Los candidatos: incidentes que YA entraron en revisión —la huella que deja
#: `transition_incident`, no el estado actual, porque un incidente puede cerrarse
#: después y la respuesta le sigue sirviendo al dictamen— y que o no se han
#: consultado nunca, o se consultaron y **no obtuvieron respuesta**.
#:
#: `answered_at IS NULL` cubre los dos casos que hay que reintentar (la pregunta
#: en vuelo cuyo worker murió, y el `sin_respuesta` explícito) sin enumerar
#: desenlaces: un desenlace nuevo no dejaría este predicado obsoleto.
#:
#: Y la TERCERA rama, la de `preliminar`: un sismo que la fuente todavía no ha
#: revisado se vuelve a preguntar con su propio reloj
#: (`catalog_usgs_refresco_preliminar_s`). Sin ella, «PUEDE CAMBIAR» se
#: congelaba en un dictamen firmado justo durante la ventana en que la fuente
#: revisa: el predicado excluía toda consulta con `answered_at` puesto, así que
#: un preliminar NO se re-preguntaba jamás. Un `confirmado` sí queda fuera para
#: siempre, y eso es correcto: la fuente ya declaró cuál es su solución.
#:
#: ⚠️ El orden es `opened_at ASC` —el MÁS VIEJO primero— y no al revés. Con
#: `DESC`, un goteo de incidentes nuevos dejaba a los viejos sin preguntar hasta
#: que vencía el TTL de revisión, y sin rastro de que se les hubiera saltado:
#: el que menos ventana le queda es justo el que no llegaba nunca. Preguntar
#: primero por el más viejo no puede acaparar la pasada, porque en cuanto se
#: pregunta queda escrito `last_attempt_at` y ese incidente se calla durante su
#: reintento.
_CANDIDATOS_SQL = """
SELECT i.incident_id, i.tenant_id,
       COALESCE(e.detected_at, i.opened_at) AS detectado_en,
       ST_Y(s.geom::geometry)::float8 AS lat,
       ST_X(s.geom::geometry)::float8 AS lon
  FROM incidents i
  JOIN sites s ON s.site_id = i.site_id
  LEFT JOIN seismic_events e ON e.event_id = i.event_id
  LEFT JOIN catalog_consultations c
         ON c.incident_id = i.incident_id AND c.provider = %(prov)s
  LEFT JOIN reference_earthquakes r ON r.catalog_key = c.catalog_key
 WHERE i.opened_at >= %(desde)s
   AND EXISTS (SELECT 1 FROM incident_actions a
                WHERE a.incident_id = i.incident_id AND a.kind = 'in_review')
   AND (c.incident_id IS NULL
        OR (c.answered_at IS NULL AND c.last_attempt_at <= %(reintentar_antes_de)s)
        OR (r.review_status = %(preliminar)s
            AND c.last_attempt_at <= %(repreguntar_preliminar_antes_de)s))
 ORDER BY i.opened_at ASC
 LIMIT %(lim)s
"""

#: `asked_at` NO entra en el `DO UPDATE`: es la fecha que se cita y no se reescribe.
_INTENTO_SQL = """
INSERT INTO catalog_consultations
       (incident_id, provider, tenant_id, asked_at, last_attempt_at, attempts)
VALUES (%(inc)s, %(prov)s, %(tenant)s, %(ahora)s, %(ahora)s, 1)
ON CONFLICT (incident_id, provider) DO UPDATE
   SET last_attempt_at = EXCLUDED.last_attempt_at,
       attempts        = catalog_consultations.attempts + 1
RETURNING asked_at, attempts
"""

#: El desenlace de un intento que SÍ obtuvo respuesta. Pisa las cuatro columnas
#: porque la respuesta nueva sustituye entera a la anterior.
_DESENLACE_SQL = """
UPDATE catalog_consultations
   SET answered_at = %(answered)s,
       outcome     = %(outcome)s,
       catalog_key = %(key)s,
       detail      = %(detail)s
 WHERE incident_id = %(inc)s AND provider = %(prov)s
"""

#: ⚠️ El desenlace de un intento que NO obtuvo respuesta, que **no puede ser el
#: mismo UPDATE**. Éste no toca `answered_at` ni `catalog_key` jamás.
#:
#: Hasta aquí la rama sin respuesta escribía por `_DESENLACE_SQL` con
#: ``answered=None, key=None``, y eso estaba bien mientras la fila sólo podía
#: nacer sin respuesta. Desde que un ``preliminar`` **se re-pregunta** por su
#: propio reloj, ese UPDATE le cae a filas que YA habían correlacionado: un
#: corte de red de diez segundos borraba `answered_at`, la clave del sismo y el
#: detalle, y la superficie pasaba de `preliminar` —con su magnitud citable— a
#: `consultando`. Eso no es degradar con honestidad: es **perder un dato bueno**
#: y afirmar que nunca lo tuvimos.
#:
#: Lo que sí cambia: `attempts` y `last_attempt_at` (los escribe el intento), y
#: una nota al final del detalle. La nota lleva marca propia y se REEMPLAZA con
#: `split_part`, no se acumula: seis reintentos en la ventana de revisión no
#: pueden convertir el detalle en un log.
_SIN_RESPUESTA_SQL = """
UPDATE catalog_consultations
   SET outcome = CASE WHEN answered_at IS NULL THEN %(outcome)s ELSE outcome END,
       detail  = CASE WHEN answered_at IS NULL THEN %(motivo)s
                      ELSE split_part(detail, %(marca)s, 1) || %(nota)s END
 WHERE incident_id = %(inc)s AND provider = %(prov)s
"""

#: La marca que abre la nota del reintento fallido. Es lo que permite
#: reemplazarla en vez de acumularla, así que **tiene que ser la misma cadena**
#: con la que se compone la nota: por eso se compone de ella.
_MARCA_REINTENTO = " · REINTENTO SIN RESPUESTA"

#: El `DO UPDATE` refresca TAMBIÉN las cifras, no sólo la procedencia. Dejar una
#: magnitud vieja junto a un `consulted_at` recién puesto sería lo peor de las dos
#: cosas: «se lo preguntamos hace un minuto» estampado sobre un número de antes.
#: `catalog_key` y `created_at` no se tocan — la clave es nuestra y la fecha de
#: alta es un hecho sobre la fila, no sobre el sismo.
_CATALOGO_SQL = """
INSERT INTO reference_earthquakes
       (catalog_key, origin_time, magnitude, place, epicenter, depth_km,
        source, source_ref, consulted_at, review_status, provider_event_id)
VALUES (%(key)s, %(t0)s, %(mag)s, %(place)s,
        ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
        %(depth)s, %(source)s, %(ref)s, %(consultado)s, %(estado)s, %(pid)s)
ON CONFLICT (source, provider_event_id) WHERE provider_event_id IS NOT NULL
DO UPDATE SET origin_time   = EXCLUDED.origin_time,
              magnitude     = EXCLUDED.magnitude,
              place         = EXCLUDED.place,
              epicenter     = EXCLUDED.epicenter,
              depth_km      = EXCLUDED.depth_km,
              source_ref    = EXCLUDED.source_ref,
              consulted_at  = EXCLUDED.consulted_at,
              review_status = EXCLUDED.review_status
RETURNING catalog_key,
          ST_X(epicenter::geometry)::float8 AS lon_escrita,
          ST_Y(epicenter::geometry)::float8 AS lat_escrita
"""


@dataclass(frozen=True)
class PasadaDeConsulta:
    """Lo que hizo una pasada, por desenlace. ``corte`` es lo que no se calla.

    ⚠️ **Tuplas, no listas.** Esto se declaraba ``frozen=True`` y sus tres listas
    se llenaban con ``.append()`` DESPUÉS de construirlo: el congelado era
    decorativo y el resultado de la pasada era mutable para cualquiera que lo
    tuviera en la mano. Ahora se acumula en locales y el objeto se construye una
    vez, al final, con lo que de verdad pasó.
    """

    correlacionados: tuple[str, ...] = ()
    sin_correlacion: tuple[str, ...] = ()
    sin_respuesta: tuple[str, ...] = ()
    #: ``None`` = se preguntó por TODOS los candidatos. Si no, por qué no:
    #: :data:`CORTE_POR_TOPE` o :data:`CORTE_POR_PRESUPUESTO`.
    corte: str | None = None

    @property
    def truncada(self) -> bool:
        """¿Quedaron candidatos sin preguntar? Se preguntan en la vuelta siguiente."""
        return self.corte is not None

    @property
    def consultados(self) -> tuple[str, ...]:
        return (*self.correlacionados, *self.sin_correlacion, *self.sin_respuesta)


def criterio_de(settings: Settings) -> corr.Criterio:
    """El MISMO criterio de identidad de `T-5.11`, construido de `Settings`.

    No hay un segundo: la ventana de la consulta, el radio de la consulta y el
    veredicto salen todos de aquí.
    """
    return corr.Criterio(
        v_s_km_s=settings.correlation_v_s_km_s,
        margen_s=settings.correlation_margin_s,
        radio_km=settings.correlation_max_km,
        pga_minima_g=settings.correlation_min_pga_g,
    )


def run_consulta_catalogo_pass(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    now: datetime | None = None,
    max_por_pasada: int = _MAX_POR_PASADA,
    transport: Any | None = None,
    reloj: Callable[[], float] = time.monotonic,
) -> PasadaDeConsulta:
    """Consulta USGS por los incidentes en revisión que todavía no tienen respuesta.

    Apagada (``catalog_usgs_enabled=False``, el defecto) **no abre un socket ni
    escribe una fila**: todo evento sigue en ``sin_dato_externo``, que es lo que
    hoy es cierto. Encenderla es configuración, no despliegue.
    """
    if not settings.catalog_usgs_enabled:
        return PasadaDeConsulta()

    ahora = now or datetime.now(tz=UTC)
    tomado = conn.execute(
        "SELECT pg_try_advisory_lock(%s) AS tomado", (_CONSULTA_LOCK_KEY,)
    ).fetchone()["tomado"]
    if not tomado:
        # Otra instancia está preguntando. No es un error y no se reintenta: la
        # siguiente pasada llega en segundos. **Pero se DICE.** Esta rama y la
        # del cerrojo que no se suelta son la misma superficie: si el cerrojo se
        # quedara tomado, la pasada entraría aquí para siempre, y sin esta línea
        # eso sería un no-op silencioso — el modo de fallo más caro de este
        # repositorio, y el que el propio módulo cita dos veces más abajo.
        logger.info(
            "catálogo: la pasada no tomó el cerrojo (otra instancia la está "
            "corriendo); no se preguntó nada en esta vuelta"
        )
        conn.rollback()
        return PasadaDeConsulta()

    try:
        return _pasada(
            conn,
            settings,
            ahora=ahora,
            maximo=max_por_pasada,
            transport=transport,
            reloj=reloj,
        )
    finally:
        _suelta_el_cerrojo(conn)


def _suelta_el_cerrojo(conn: psycopg.Connection) -> None:
    """Suelta el advisory lock de SESIÓN pase lo que pase, y sin tapar el fallo.

    ⚠️ **Esto era una fuga, y la fuga mataba la pasada para siempre.** El `finally`
    ejecutaba el `pg_advisory_unlock` directamente. Si `_pasada` moría con la
    transacción abierta —la consulta de candidatos falla, y con ella toda la
    transacción queda abortada—, ese `execute` reventaba con
    ``InFailedSqlTransaction``: la excepción original se PERDÍA (una excepción
    lanzada en un `finally` sustituye a la que iba en vuelo) y el cerrojo se
    quedaba tomado en `work_conn`, que el motor del worker **no cierra**. A
    partir de ahí todas las pasadas caían en la rama `if not tomado` y el
    subsistema quedaba muerto sin una línea que lo dijera.

    El `rollback()` de la primera línea es todo el arreglo: deja la sesión en
    condiciones de ejecutar el `unlock`. No pierde trabajo — la pasada commitea
    el intento y el desenlace según los escribe, y nunca deja nada pendiente.

    Y si aun así no se pudiera soltar (una conexión rota, por ejemplo — en cuyo
    caso el servidor suelta el cerrojo solo al cerrarla), se registra y se sigue:
    lo que no puede hacer esta función es tapar el fallo que la trajo aquí.
    """
    try:
        conn.rollback()
        conn.execute("SELECT pg_advisory_unlock(%s)", (_CONSULTA_LOCK_KEY,))
        conn.commit()
    except Exception:
        logger.exception(
            "catálogo: no se pudo soltar el cerrojo de la pasada; si la conexión "
            "sigue viva, la consulta no volverá a entrar hasta que el motor la reponga"
        )


def _pasada(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    ahora: datetime,
    maximo: int,
    transport: Any | None,
    reloj: Callable[[], float],
) -> PasadaDeConsulta:
    """Pregunta por los candidatos que quepan en el presupuesto de reloj.

    ``reloj`` es monótono —``time.monotonic``— y no el de pared: el presupuesto
    mide DURACIÓN, y un salto de NTP a mitad de la pasada no puede ni regalar ni
    robar segundos. ``ahora`` sigue siendo el reloj de calendario, que es otra
    cosa y se escribe en la base.
    """
    # La ventana hacia atrás se DERIVA del TTL de la revisión: preguntar por un
    # incidente que ya venció y que nadie va a mirar no le sirve a nadie, y un
    # número propio aquí sería un tercer plazo que envejecería aparte.
    desde = ahora - timedelta(seconds=settings.incident_review_ttl_s)
    refresco = settings.catalog_usgs_refresco_preliminar_s
    filas = conn.execute(
        _CANDIDATOS_SQL,
        {
            "prov": fdsn.PROVEEDOR,
            "desde": desde,
            "reintentar_antes_de": ahora - timedelta(seconds=settings.catalog_usgs_reintento_s),
            "repreguntar_preliminar_antes_de": ahora - timedelta(seconds=refresco),
            "preliminar": pr.PRELIMINAR,
            "lim": maximo + 1,
        },
    ).fetchall()
    conn.commit()  # sólo se leyó; y hay que soltar la transacción antes de la red

    # Se traen `maximo + 1` para saber si había más, no para preguntarlos. Si
    # además se acaba el reloj, el motivo que queda escrito es el del
    # presupuesto: es el que explica por qué se paró AHÍ y no en el tope.
    corte = CORTE_POR_TOPE if len(filas) > maximo else None
    por_desenlace: dict[str, list[str]] = {
        CORRELACIONADO: [],
        SIN_CORRELACION: [],
        SIN_RESPUESTA: [],
    }
    arranque = reloj()
    preguntados = 0
    for fila in filas[:maximo]:
        # ⚠️ El presupuesto se comprueba ANTES de salir a la red y con el timeout
        # DENTRO de la cuenta: comprobarlo después sólo diría cuánto se pasó, y
        # lo que hay que acotar es cuánto se va a pasar. Así el peor caso de la
        # pasada es `catalog_usgs_presupuesto_s`, no `maximo × timeout`.
        #
        # La PRIMERA siempre se pregunta, aunque el presupuesto sea menor que el
        # timeout: una configuración así convertiría la pasada en un no-op
        # silencioso —nadie preguntaría nunca y nada lo diría—, y el peor caso de
        # una sola llamada ya lo acota el propio timeout.
        gastado = reloj() - arranque
        if preguntados and gastado + settings.catalog_usgs_timeout_s > (
            settings.catalog_usgs_presupuesto_s
        ):
            corte = CORTE_POR_PRESUPUESTO
            break
        preguntados += 1
        try:
            desenlace = _consulta_un_incidente(
                conn, settings, fila, ahora=ahora, transport=transport
            )
        except Exception:  # noqa: BLE001 - un incidente no puede costar la pasada
            logger.exception(
                "catálogo: la consulta del incidente %s falló; queda en `consultando`",
                fila["incident_id"],
            )
            conn.rollback()
            continue
        por_desenlace[desenlace].append(str(fila["incident_id"]))

    resultado = PasadaDeConsulta(
        correlacionados=tuple(por_desenlace[CORRELACIONADO]),
        sin_correlacion=tuple(por_desenlace[SIN_CORRELACION]),
        sin_respuesta=tuple(por_desenlace[SIN_RESPUESTA]),
        corte=corte,
    )
    if resultado.consultados or corte:
        logger.info(
            "catálogo: %d correlacionados, %d sin correlación, %d sin respuesta en %.1f s%s",
            len(resultado.correlacionados),
            len(resultado.sin_correlacion),
            len(resultado.sin_respuesta),
            reloj() - arranque,
            ""
            if corte is None
            else f" (PASADA CORTADA POR {corte.upper()}: quedan más para la siguiente)",
        )
    return resultado


def _consulta_un_incidente(
    conn: psycopg.Connection,
    settings: Settings,
    fila: dict,
    *,
    ahora: datetime,
    transport: Any | None,
) -> str:
    incident_id = str(fila["incident_id"])
    criterio = criterio_de(settings)
    detectado = fila["detectado_en"]

    # (1) El intento, COMMITEADO antes de tocar la red. Si el proceso muere aquí
    # en adelante, la fila dice `consultando` y no «nadie preguntó».
    conn.execute(
        _INTENTO_SQL,
        {
            "inc": incident_id,
            "prov": fdsn.PROVEEDOR,
            "tenant": fila["tenant_id"],
            "ahora": ahora,
        },
    )
    conn.commit()

    # (2) La pregunta. La ventana es la MISMA cota que usa `queries/forensics.py`
    # para traer candidatos de la base: simétrica y superconjunto del criterio,
    # para que un evento originado DESPUÉS de nuestra detección pueda salir
    # nombrado como descarte en vez de desaparecer dentro de un `WHERE`.
    #
    # ⚠️ UN SOLO RELOJ por pasada (`ahora`), y es deliberado: `asked_at`,
    # `answered_at` y `reference_earthquakes.consulted_at` describen el mismo
    # acto, y tomarlos de tres relojes distintos haría que una fila dijera que
    # contestó antes de que se preguntara. El desfase que introduce está acotado
    # por el timeout —seis segundos, escrito en `Settings`—, que es mucho menos
    # de lo que vale esa coherencia.
    tope = timedelta(seconds=criterio.retraso_maximo_s)
    try:
        respuesta = fdsn.consulta(
            settings,
            desde=detectado - tope,
            hasta=detectado + tope,
            lat=fila["lat"],
            lon=fila["lon"],
            radio_km=criterio.radio_km,
            transport=transport,
            now=ahora,
        )
    except fdsn.SinRespuesta as exc:
        # `answered_at` se queda como estaba: en NULL si nunca contestó —y eso es
        # lo que hace alcanzable `consultando`—, y con su fecha si ya había
        # contestado antes. El motivo se guarda para que quien lea la tabla no
        # tenga que ir al log del worker. Ver `_anota_sin_respuesta`.
        _anota_sin_respuesta(conn, incident_id, ahora=ahora, motivo=exc.motivo)
        return SIN_RESPUESTA

    # (3) El veredicto, con el criterio de identidad de `T-5.11`. Sin segunda ley.
    return _resuelve(
        conn,
        respuesta,
        incident_id=incident_id,
        detectado=detectado,
        lat=fila["lat"],
        lon=fila["lon"],
        criterio=criterio,
    )


def _resuelve(
    conn: psycopg.Connection,
    respuesta: fdsn.Respuesta,
    *,
    incident_id: str,
    detectado: datetime,
    lat: float,
    lon: float,
    criterio: corr.Criterio,
) -> str:
    # ⚠️ `citables`, no `publicados`: son los que se pueden ESCRIBIR, y llamarlos
    # «publicados» es lo que hizo que el desenlace dijera «0 evento(s) publicados»
    # de una respuesta con once. Lo que la fuente publicó es `respuesta.eventos`.
    citables, sin_magnitud = _citables(respuesta.eventos)
    resultado = corr.correlaciona(
        [
            corr.Candidato(
                catalog_key=e.provider_event_id,  # identidad del PROVEEDOR, no la nuestra
                origin_time=e.origin_time,
                magnitude=e.magnitude,
                lat=e.lat,
                lon=e.lon,
                depth_km=e.depth_km,
            )
            for e in citables
        ],
        detectado_en=detectado,
        sitio_lat=lat,
        sitio_lon=lon,
        criterio=criterio,
    )

    if resultado.acierto is None:
        detail = _por_que_no(
            resultado, publicados=len(respuesta.eventos), sin_magnitud=sin_magnitud
        )
        _escribe_desenlace(
            conn,
            incident_id,
            answered=respuesta.consultado_en,
            outcome=SIN_CORRELACION,
            key=None,
            detail=detail,
        )
        return SIN_CORRELACION

    ganador = next(e for e in citables if e.provider_event_id == resultado.acierto.catalog_key)
    catalog_key = _graba_en_el_catalogo(conn, ganador, respuesta)
    km = resultado.acierto.km_al_sitio
    _escribe_desenlace(
        conn,
        incident_id,
        answered=respuesta.consultado_en,
        outcome=CORRELACIONADO,
        key=catalog_key,
        detail=(
            f"{ganador.provider_event_id} · {ganador.place} · "
            f"{'' if km is None else f'{km:.0f} km del sitio · '}"
            f"estado en la fuente '{ganador.estado_en_la_fuente or 'no declarado'}'"
        ),
    )
    return CORRELACIONADO


def _citables(eventos: tuple[fdsn.EventoPublicado, ...]) -> tuple[list, int]:
    """Los eventos que se pueden ESCRIBIR, y cuántos se quedaron fuera.

    ⚠️ **Desviación consciente del criterio puro.** `correlacion.evalua` no
    rechaza a un candidato por no traer magnitud —«desconocida» no es
    «incoherente»—, y aquí sí se filtra antes de correlacionar. La razón es de
    persistencia, no de física: ``reference_earthquakes.magnitude`` es
    ``NOT NULL``, así que un acierto sin magnitud no se podría escribir, y
    rellenarlo con un cero sería la cifra inventada que todo este subsistema
    existe para impedir. Tampoco aportaría nada citable: lo único que traería es
    la hora de origen.

    Se cuentan los descartados para poder decirlo en el desenlace en vez de que
    desaparezcan.
    """
    citables = [e for e in eventos if e.magnitude is not None]
    return citables, len(eventos) - len(citables)


def _por_que_no(resultado: corr.Resultado, *, publicados: int, sin_magnitud: int) -> str:
    """La razón de `sin_correlacion`, con los números que la sostienen.

    Sin esto, «sin correlación» es un hueco y el operador lo lee como «no pasó
    nada». Con esto es un hecho sobre el evento: el catálogo tiene N sismos en la
    ventana y ninguno es éste, y aquí están los tres primeros con su motivo.

    ⚠️ ``publicados`` es **lo que publicó la fuente**, citable o no, y no los
    citables. Recibía `len(citables)` y lo estampaba bajo el rótulo «publicados»,
    que es justo la cifra que este parámetro existe para dar: con once eventos
    sin magnitud el detalle decía «0 evento(s) publicados y ninguno evaluable
    (11 sin magnitud publicada)» — una frase que se desmiente a sí misma en
    doce palabras, en el campo que alguien lee a las 3 de la mañana.
    """
    if not publicados:
        return "la fuente no publicó ningún evento en la ventana consultada"
    coletilla = f" ({sin_magnitud} sin magnitud publicada, no citables)" if sin_magnitud else ""
    if not resultado.descartes:
        return f"{publicados} evento(s) publicados y ninguno evaluable{coletilla}"
    motivos = " · ".join(f"{d.catalog_key}: {d.detalle}" for d in resultado.descartes[:3])
    return f"{len(resultado.descartes)} evento(s) y ninguno es éste — {motivos}{coletilla}"


def _graba_en_el_catalogo(
    conn: psycopg.Connection, evento: fdsn.EventoPublicado, respuesta: fdsn.Respuesta
) -> str:
    """Escribe (o refresca) la fila del catálogo y devuelve su ``catalog_key``.

    La clave que se PROPONE es ``USGS-<id del proveedor>``, determinista. Si el
    sismo ya estaba en la tabla por su identidad ``(source, provider_event_id)``
    —las seis filas USGS del seed lo están—, el `ON CONFLICT` conserva la clave
    que ya tenía: ``USGS-2017-09-19-PUE`` no se convierte en ``USGS-us2000ar20``,
    porque hay dictámenes y ventanas de reproducción que la citan.
    """
    fila = conn.execute(
        _CATALOGO_SQL,
        {
            "key": f"{fdsn.PROVEEDOR}-{evento.provider_event_id}",
            "t0": evento.origin_time,
            "mag": evento.magnitude,
            "place": evento.place,
            "lon": evento.lon,
            "lat": evento.lat,
            "depth": evento.depth_km,
            "source": fdsn.PROVEEDOR,
            "ref": fdsn.cita(evento, respuesta.url),
            "consultado": respuesta.consultado_en,
            "estado": evento.review_status,
            "pid": evento.provider_event_id,
        },
    ).fetchone()
    _verifica_el_epicentro(evento, fila)
    return str(fila["catalog_key"])


#: Tolerancia de la relectura del epicentro, en grados. No es una tolerancia
#: física: `geography` guarda float8, así que la ida y vuelta es exacta salvo
#: redondeo. 1e-6 grados son ~11 cm — cualquier discrepancia real será de cientos
#: de kilómetros, no de centímetros.
_TOLERANCIA_GRADOS = 1e-6


def _verifica_el_epicentro(evento: fdsn.EventoPublicado, fila: dict) -> None:
    """Relee lo que se ESCRIBIÓ y lo compara con lo que dijo la fuente.

    ⚠️ **Esta función existe por una mutación medida.** Cambiar
    ``ST_MakePoint(%(lon)s, %(lat)s)`` por ``ST_MakePoint(%(lat)s, %(lon)s)``
    dejaba 493 pruebas en verde. PostGIS no protege: una latitud de -98.7384 no
    es un error para él, la coacciona al rango con un simple ``NOTICE`` y guarda
    ``POINT(18.2702 -81.2616)`` — un epicentro en el Caribe, con la cifra y la
    cita del sismo de Puebla. El módulo documentaba el peligro a gritos en el
    lado de la LECTURA (el orden `[lon, lat]` del GeoJSON) y nadie lo vigilaba en
    el de la ESCRITURA, que es el que acaba dibujado en un croquis firmado.

    Levantar aquí deja al incidente en ``consultando`` con la fila del catálogo
    revertida por el ``rollback`` de la pasada: **no escribir un epicentro es
    mucho menos grave que escribir uno falso**, porque el segundo se imprime
    después bajo una firma y nadie vuelve a preguntarse de dónde salió.
    """
    dlat = abs(float(fila["lat_escrita"]) - evento.lat)
    dlon = abs(float(fila["lon_escrita"]) - evento.lon)
    if dlat > _TOLERANCIA_GRADOS or dlon > _TOLERANCIA_GRADOS:
        raise ValueError(
            f"el epicentro escrito no es el que publicó la fuente para "
            f"{evento.provider_event_id}: la fuente dijo lat {evento.lat:.4f} / "
            f"lon {evento.lon:.4f} y en la base quedó lat "
            f"{float(fila['lat_escrita']):.4f} / lon {float(fila['lon_escrita']):.4f}"
        )


def _anota_sin_respuesta(
    conn: psycopg.Connection, incident_id: str, *, ahora: datetime, motivo: str
) -> None:
    """El intento no obtuvo respuesta — **sin borrar la respuesta anterior**.

    Ver :data:`_SIN_RESPUESTA_SQL`: un fallo de red en el refresco de un
    ``preliminar`` no puede llevarse por delante `answered_at`, `catalog_key` y
    el detalle de una correlación que ya estaba escrita.
    """
    nota = f"{_MARCA_REINTENTO} ({ahora.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ}): {motivo}"
    conn.execute(
        _SIN_RESPUESTA_SQL,
        {
            "inc": incident_id,
            "prov": fdsn.PROVEEDOR,
            "outcome": SIN_RESPUESTA,
            "motivo": motivo,
            "marca": _MARCA_REINTENTO,
            "nota": nota,
        },
    )
    conn.commit()


def _escribe_desenlace(
    conn: psycopg.Connection,
    incident_id: str,
    *,
    answered: datetime,
    outcome: str,
    key: str | None,
    detail: str,
) -> None:
    """La fuente CONTESTÓ: su respuesta sustituye entera a la anterior.

    ``answered`` no admite ``None`` a propósito. Lo admitía, y por ahí entraba la
    rama sin respuesta a borrar `answered_at` y `catalog_key` de una fila que ya
    había correlacionado; el tipo es ahora lo que impide que vuelva a pasar.
    """
    conn.execute(
        _DESENLACE_SQL,
        {
            "inc": incident_id,
            "prov": fdsn.PROVEEDOR,
            "answered": answered,
            "outcome": outcome,
            "key": key,
            "detail": detail,
        },
    )
    conn.commit()
