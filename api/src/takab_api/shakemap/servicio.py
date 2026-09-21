"""T-7.24 · La pasada del worker que calcula el mini-ShakeMap de un incidente.

DÓNDE CORRE, Y POR QUÉ NO ES UN MICROSERVICIO
─────────────────────────────────────────────
La viñeta diferida del blueprint hablaba del «microservicio mini-ShakeMap». Este
diseño **no propone uno** (`design/BLOQUE-IV-ARQUITECTURA.md §A.4`), y la razón
es de operación y no de gusto: un servicio más es un despliegue más, una alarma
más, un rol IAM más y una superficie más que puede caerse — y lo que se calcula
aquí **no es continuo**. Corre en el worker de incidentes que ya existe, con
transacción propia, como el resto de pasadas: un fallo aquí no puede revertir una
correlación, un dictamen ni un cierre ya escritos. Jamás en la ingesta: el camino
que abre un incidente por un pulso del WR-1 no se alarga (reglas de oro 1 y 4).

Y va **antes** de la pasada que consulta a USGS, no después. Parece al revés —el
epicentro que trae USGS es justo lo que le falta a la capa 2— pero el orden lo
fija un invariante que ya está probado: *la única pasada que habla con un tercero
tiene que ser la última* (`tests/catalogo/test_enganche_al_worker.py`), porque su
lentitud no puede retrasar a nadie. El epicentro que llegue en esta vuelta entra
en el mapa en la siguiente, que llega en segundos, y entra por el mecanismo
normal de refresco: un mapa que no está `completo` se rehace.

CUÁNDO SE CALCULA, Y CUÁNDO SE DEJA DE CALCULAR
───────────────────────────────────────────────
Candidato = incidente que **ya entró en revisión** (la huella que deja
`transition_incident`, igual que `catalogo/consulta.py`: es el estado histórico y
no el actual, porque un incidente puede cerrarse después y el mapa le sigue
sirviendo al dictamen) y que además:

* no tiene snapshot — nunca se calculó; o
* tiene uno que **no está `completo`** y lleva más de `shakemap_refresco_s` sin
  rehacerse. Puede llegarle el epicentro del catálogo (`T-7.25`) o el spool de un
  gabinete que estaba sin red, y entonces el mapa mejora.

Un `completo` **no se recalcula jamás**: ya tiene epicentro, magnitud y medidas,
y volver a hacerlo sería gastar el bucle en confirmar lo mismo. Eso es lo que
hace que la pasada converja en vez de ser un bucle caliente.

La ventana hacia atrás se DERIVA de `incident_review_ttl_s`, como la de la
consulta al catálogo: un número propio aquí sería un tercer plazo que envejecería
aparte. Consecuencia, escrita para que no sorprenda: si el worker estuviera caído
más que esa ventana, los incidentes de antes **no estrenan mapa**. La alternativa
—barrer el histórico entero— haría que un arranque en frío recalculara meses de
incidentes bloqueando el bucle que sostiene la actuación comandada por el quórum.

⚠️ EL PUENTE ASYNC, Y POR QUÉ EXISTE
────────────────────────────────────
El worker es psycopg **síncrono**; `estaciones.build_estaciones` —la tabla por
estación de `T-7.17`— es **async**, porque nació para el request. Antes que
escribir una segunda consulta de features (la cuarta de este repositorio) para
los mismos números, esta pasada abre un bucle de eventos y una conexión async
propia y reusa aquélla: dos caminos a los mismos números acaban discrepando, y
aquí el que discrepara pintaría un mapa distinto del que enseña la tabla.

El engine es efímero (`NullPool` + `dispose()`) a propósito: `asyncio.run` crea y
cierra un bucle en cada pasada, y un pool cacheado dejaría conexiones atadas a un
bucle ya cerrado. El coste es una conexión nueva por pasada **con candidatos** —
sin candidatos no se abre ninguna.

⚠️ Y dentro del puente pasan dos cosas que no se ven en la firma, y las dos son
la diferencia entre un mapa y un no-op silencioso:

1. **`SET LOCAL ROLE takab_ingest`.** En producción el DSN ya es de ese rol y es
   un no-op; en local el DSN es el superusuario, así que sin esto los tests
   ejercerían privilegios que la nube no tiene. Mismo motivo que `db/engine.py`.
2. **`set_config('app.tenant_id', …)` por incidente.** `build_estaciones` lee
   `waveform_features_1s_secure`, una vista `security_barrier` cuyo JOIN a
   `sites` se evalúa con la RLS del DUEÑO de la vista, que **no** tiene BYPASSRLS.
   Sin el GUC la vista devuelve cero filas: todos los mapas saldrían `sin_datos`
   sin un solo error en el log. Y ponerlo derivado de `incidents.tenant_id` hace
   que el aislamiento entre clientes sea por construcción, no por cuidado.

LO QUE LE CUESTA AL BUCLE
─────────────────────────
El bucle del worker es serial: lo que esta pasada tarda es lo que se retrasa la
correlación, la reproducción, la actuación comandada por el quórum, el dictamen y
las fases de la vuelta siguiente. Aquí no hay un tercero, pero sí una consulta de
features **por inmueble y por incidente**, que es lo que crece sin avisar. Por
eso `shakemap_presupuesto_s` se comprueba antes de CADA incidente, y lo que no
cabe se calcula en la vuelta siguiente diciendo por qué (`corte`).

IDEMPOTENCIA (regla de oro 3)
─────────────────────────────
`ON CONFLICT (incident_id) DO UPDATE`: la clave natural es el incidente y es la
PRIMARY KEY. `calculado_en` **sí** se refresca, porque aquí la fecha del cálculo
es el dato — dice con qué información se hizo el mapa.

EL CERROJO, Y LA TRAMPA QUE ESTA PASADA SE AHORRA
─────────────────────────────────────────────────
`pg_try_advisory_xact_lock`: de TRANSACCIÓN, no de sesión. La pasada hace **un
solo commit al final**, así que no necesita el cerrojo de sesión de
`catalogo/consulta.py` — y por tanto se ahorra entera la fuga que aquella ficha
midió (un `unlock` sobre una transacción abortada pierde la excepción original y
deja el cerrojo tomado para siempre, matando el subsistema en silencio). Aquí no
hay nada que deba sobrevivir a un fallo a mitad: el snapshot o se escribe entero
o se recalcula en la vuelta siguiente, que es idempotente.

Y si el cerrojo está tomado, **se dice**. Un no-op silencioso es el modo de fallo
más caro de este repositorio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from takab_api import procedencia as pr
from takab_api.estaciones import build_estaciones
from takab_api.forensics import umbral_de_comparacion
from takab_api.shakemap import calculo as C

if TYPE_CHECKING:
    import psycopg
    from sqlalchemy.ext.asyncio import AsyncConnection

    from takab_api.schemas.estaciones import EstacionesOut
    from takab_api.settings import Settings

logger = logging.getLogger("takab_api.shakemap")

#: Clave del advisory lock de la pasada. De TRANSACCIÓN (ver el encabezado).
LOCK_KEY = 0x7A24

#: Tope de incidentes que se TRAEN en la pasada. No es la cota del bloqueo —de eso
#: se ocupa `shakemap_presupuesto_s`, que corta por reloj de pared antes de cada
#: incidente—: es una cota de la CONSULTA, para que un pico de incidentes no
#: traiga miles de filas a memoria. Los que sobren entran en la siguiente pasada.
MAX_POR_PASADA = 20

#: Por qué la pasada dejó candidatos sin calcular. Son cosas distintas y ninguna
#: es un error; lo que no puede pasar es que no se digan.
CORTE_POR_TOPE = "tope"
CORTE_POR_PRESUPUESTO = "presupuesto"
CORTE_POR_CERROJO = "cerrojo"

#: Los candidatos. `answered_at`/`outcome`/`review_status`… vienen para derivar la
#: PROCEDENCIA del epicentro con el mismo `procedencia.de_consulta` que usan la
#: consola y el papel: una segunda derivación acabaría diciendo otra cosa.
#:
#: ⚠️ La consulta al catálogo entra por LATERAL y no por un `LEFT JOIN` directo:
#: `catalog_consultations` tiene PK `(incident_id, provider)` y hoy sólo hay un
#: proveedor, pero el día que haya dos este JOIN duplicaría el incidente y se
#: calcularía dos veces el mismo mapa. El LATERAL deja escrito que se toma UNA.
_CANDIDATOS_SQL = """
SELECT i.incident_id, i.tenant_id, i.site_id, i.opened_at,
       e.source            AS evento_fuente,
       e.depth_km::float8  AS depth_km,
       e.meta              AS evento_meta,
       c.provider AS consulta_provider, c.asked_at AS consulta_asked_at,
       c.answered_at, c.outcome, c.catalog_key AS consulta_key,
       r.source AS cat_source, r.consulted_at, r.review_status, r.provider_event_id
  FROM incidents i
  LEFT JOIN seismic_events e ON e.event_id = i.event_id
  LEFT JOIN incident_shakemap m ON m.incident_id = i.incident_id
  LEFT JOIN LATERAL (
    SELECT cc.* FROM catalog_consultations cc
     WHERE cc.incident_id = i.incident_id
     ORDER BY cc.answered_at DESC NULLS LAST, cc.provider
     LIMIT 1
  ) c ON true
  LEFT JOIN reference_earthquakes r ON r.catalog_key = c.catalog_key
 WHERE i.opened_at >= %(desde)s
   AND EXISTS (SELECT 1 FROM incident_actions a
                WHERE a.incident_id = i.incident_id AND a.kind = 'in_review')
   AND (m.incident_id IS NULL
        OR (m.estado <> %(completo)s AND m.calculado_en <= %(rehacer_antes_de)s))
 ORDER BY i.opened_at ASC
 LIMIT %(lim)s
"""

#: `ON CONFLICT (incident_id) DO UPDATE`: recalcular no duplica (regla de oro 3).
#: `tenant_id` no se toca en el UPDATE — un incidente no cambia de cliente, y si
#: alguna vez lo pareciera, lo que hay que arreglar es eso y no esta fila.
_UPSERT_SQL = """
INSERT INTO incident_shakemap
       (incident_id, tenant_id, calculado_en, estado, ley, epicentro,
        cobertura_km, puntos, anillos)
VALUES (%(inc)s, %(tenant)s, %(ahora)s, %(estado)s, %(ley)s, %(epicentro)s::jsonb,
        %(cobertura)s, %(puntos)s::jsonb, %(anillos)s::jsonb)
ON CONFLICT (incident_id) DO UPDATE
   SET calculado_en = EXCLUDED.calculado_en,
       estado       = EXCLUDED.estado,
       ley          = EXCLUDED.ley,
       epicentro    = EXCLUDED.epicentro,
       cobertura_km = EXCLUDED.cobertura_km,
       puntos       = EXCLUDED.puntos,
       anillos      = EXCLUDED.anillos
"""


@dataclass(frozen=True)
class PasadaDeShakemap:
    """Lo que hizo una pasada. ``corte`` es lo que no se calla.

    Tuplas y no listas, por la lección de `catalogo/consulta.py`: un `frozen`
    cuyas colecciones se rellenan con `.append()` después es decorativo.
    """

    calculados: tuple[str, ...] = ()
    #: ``None`` = se calcularon TODOS los candidatos. Si no, por qué no.
    corte: str | None = None

    @property
    def truncada(self) -> bool:
        """¿Quedaron candidatos? Se calculan en la vuelta siguiente."""
        return self.corte is not None


@dataclass(frozen=True)
class _Lectura:
    """Lo que el puente async saca de la base para UN incidente."""

    incident_id: str
    tenant_id: str
    medidas: tuple[C.Medida, ...]
    epicentro: C.Epicentro | None
    niveles: tuple[C.Nivel, ...]


def niveles_de(umbral) -> tuple[C.Nivel, ...]:  # noqa: ANN001 - felt.UmbralComparacion
    """Los niveles de los anillos: los umbrales con que ESTE sistema decide.

    No es una escala inventada, y ése es medio contrato de la ficha. Por eso los
    nombres NO se escriben aquí —se derivan de los campos de PGA de
    `felt.Thresholds` (`calculo.UMBRALES`)— y los valores se LEEN de la banda del
    inmueble que abrió el incidente, resuelta con `umbral_de_comparacion`, el
    MISMO resolvedor que usan la tabla por estación y el dictamen: no hay un
    segundo, así que no pueden discrepar. Con `getattr` no queda dónde teclear un
    número, que es lo que hace comprobable la afirmación.

    ⚠️ Aquí ya NO está `correlation_min_pga_g`. Es el piso de coherencia de
    identidad de `T-5.11` —«¿pudo notarse siquiera aquí?»—, no un umbral con el
    que se decida nada sobre el edificio, y como nivel de mapa daba anillos de
    5 623 km para el M7.1 de referencia. Retirado el 2026-09-21 por decisión del
    integrador; la razón larga, en el encabezado de `calculo.py`.

    ⚠️ La PROCEDENCIA de la banda (`umbral.origen`: del inmueble o de referencia)
    **no se duplica en este snapshot**: viaja, para ese mismo sitio y ese mismo
    instante, en `GET /incidents/{id}/estaciones`, que es donde el operador la
    lee. Guardarla también aquí crearía un segundo sitio donde puede divergir, y
    un umbral de fábrica presentado como del edificio es el defecto que cerró
    `T-7.35`.
    """
    return tuple(C.Nivel(nombre, getattr(umbral.thresholds, nombre)) for nombre in C.UMBRALES)


def run_shakemap_pass(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    now: datetime | None = None,
    max_por_pasada: int = MAX_POR_PASADA,
    reloj: Callable[[], float] = time.monotonic,
) -> PasadaDeShakemap:
    """Calcula y persiste el mini-ShakeMap de los incidentes que lo necesitan."""
    ahora = now or datetime.now(tz=UTC)
    tomado = conn.execute("SELECT pg_try_advisory_xact_lock(%s) AS tomado", (LOCK_KEY,)).fetchone()[
        "tomado"
    ]
    if not tomado:
        # Otra instancia está calculando. No es un error y no se reintenta: la
        # siguiente pasada llega en segundos. **Pero se DICE**, porque un no-op
        # silencioso es el modo de fallo más caro de este repositorio.
        logger.info(
            "shakemap: la pasada no tomó el cerrojo (otra instancia la está "
            "corriendo); no se calculó ningún mapa en esta vuelta"
        )
        conn.rollback()
        return PasadaDeShakemap(corte=CORTE_POR_CERROJO)

    try:
        return _pasada(conn, settings, ahora=ahora, maximo=max_por_pasada, reloj=reloj)
    except Exception:
        # El cerrojo es de transacción: el rollback lo suelta. No hay nada que
        # perder —el snapshot se recalcula entero en la vuelta siguiente— y sí
        # algo que evitar: dejar la conexión del worker con una transacción
        # abortada, que es lo que le revienta a la pasada siguiente.
        conn.rollback()
        raise


def _pasada(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    ahora: datetime,
    maximo: int,
    reloj: Callable[[], float],
) -> PasadaDeShakemap:
    """Los candidatos que quepan en el presupuesto de reloj.

    ``reloj`` es monótono —``time.monotonic``— y no el de pared: el presupuesto
    mide DURACIÓN, y un salto de NTP a mitad no puede ni regalar ni robar
    segundos. ``ahora`` sigue siendo el reloj de calendario, que es otra cosa y
    se escribe en la base.
    """
    desde = ahora - timedelta(seconds=settings.incident_review_ttl_s)
    filas = conn.execute(
        _CANDIDATOS_SQL,
        {
            "desde": desde,
            "completo": C.ESTADO_COMPLETO,
            "rehacer_antes_de": ahora - timedelta(seconds=settings.shakemap_refresco_s),
            "lim": maximo + 1,
        },
    ).fetchall()
    if not filas:
        conn.rollback()  # sólo se leyó: soltar el snapshot y el cerrojo
        return PasadaDeShakemap()

    # Se traen `maximo + 1` para SABER si había más, no para calcularlos.
    corte = CORTE_POR_TOPE if len(filas) > maximo else None
    candidatas = filas[:maximo]

    lecturas, corte_lectura = _lee(settings, candidatas, reloj=reloj)
    corte = corte_lectura or corte

    calculados: list[str] = []
    for lectura in lecturas:
        mapa = C.calcula(
            list(lectura.medidas),
            epicentro=lectura.epicentro,
            niveles=lectura.niveles,
            cobertura_km=settings.shakemap_cobertura_km,
            # El tope del radio se DERIVA y no es un ajuste nuevo: es la
            # distancia máxima epicentro↔sitio con la que este sistema acepta
            # que un sismo del catálogo sea el que sacudió este edificio
            # (`forensics/correlacion.py`). Un anillo más lejos afirmaría que el
            # modelo alcanza donde el propio sistema se niega a atribuir — y un
            # segundo número aquí envejecería aparte del primero, que es la
            # razón por la que la ventana hacia atrás también se deriva.
            radio_max_km=settings.correlation_max_km,
        )
        _escribe(conn, lectura, mapa, ahora=ahora)
        calculados.append(lectura.incident_id)

    conn.commit()
    if calculados or corte:
        logger.info(
            "shakemap: %d mapas calculados%s",
            len(calculados),
            "" if corte is None else f" (PASADA CORTADA POR {corte.upper()})",
        )
    return PasadaDeShakemap(calculados=tuple(calculados), corte=corte)


def _escribe(conn: psycopg.Connection, lectura: _Lectura, mapa: C.Mapa, *, ahora: datetime) -> None:
    conn.execute(
        _UPSERT_SQL,
        {
            "inc": lectura.incident_id,
            "tenant": lectura.tenant_id,
            "ahora": ahora,
            "estado": mapa.estado,
            "ley": mapa.ley,
            "epicentro": json.dumps(C.epicentro_json(mapa)),
            "cobertura": mapa.cobertura_km,
            "puntos": json.dumps(C.puntos_json(mapa)),
            "anillos": json.dumps(C.anillos_json(mapa)),
        },
    )


# --------------------------------------------------------------------------
# El puente async: reusar la tabla por estación en vez de escribir la cuarta
# consulta de features. Ver el encabezado del módulo.
# --------------------------------------------------------------------------


def _lee(
    settings: Settings, filas: list[dict], *, reloj: Callable[[], float]
) -> tuple[list[_Lectura], str | None]:
    """Cruza al mundo async. ``asyncio.run`` a propósito, y no un loop reusado.

    El llamador es el worker, que es síncrono de arriba abajo: si alguien llamara
    a esta pasada desde dentro de un bucle de eventos, `asyncio.run` levantaría
    `RuntimeError` en vez de hacer algo raro en silencio, que es la conducta que
    se quiere.
    """
    return asyncio.run(_lee_async(settings, filas, reloj=reloj))


async def _lee_async(
    settings: Settings, filas: list[dict], *, reloj: Callable[[], float]
) -> tuple[list[_Lectura], str | None]:
    motor = create_async_engine(settings.database_url, poolclass=NullPool)
    salida: list[_Lectura] = []
    corte: str | None = None
    arranque = reloj()
    try:
        async with motor.connect() as conn:
            for fila in filas:
                # ⚠️ El presupuesto se comprueba ANTES de empezar el incidente, no
                # después: comprobarlo después sólo diría cuánto se pasó, y lo que
                # hay que acotar es cuánto se va a pasar. El PRIMERO siempre se
                # calcula —si no, un presupuesto mal puesto convertiría la pasada
                # en un no-op silencioso y nadie tendría mapa jamás.
                if salida and reloj() - arranque > settings.shakemap_presupuesto_s:
                    corte = CORTE_POR_PRESUPUESTO
                    break
                lectura = await _lee_uno(conn, settings, fila)
                if lectura is not None:
                    salida.append(lectura)
    finally:
        await motor.dispose()
    return salida, corte


async def _lee_uno(conn: AsyncConnection, settings: Settings, fila: dict) -> _Lectura | None:
    tenant_id = str(fila["tenant_id"])
    incident_id = str(fila["incident_id"])
    # El rol del worker y el contexto de tenant. Los dos, y por este orden: sin
    # el rol, en local se ejercerían privilegios que la nube no tiene; sin el
    # GUC, la vista segura de features devuelve cero filas y el mapa sale
    # `sin_datos` sin un solo error. Ver el encabezado del módulo.
    await conn.execute(text('SET LOCAL ROLE "takab_ingest"'))
    await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
    try:
        tabla = await build_estaciones(conn, incident_id, settings)
        if tabla is None:
            return None
        umbral = await umbral_de_comparacion(
            conn, site_id=str(fila["site_id"]), tenant_id=tenant_id, at=fila["opened_at"]
        )
        return _Lectura(
            incident_id=incident_id,
            tenant_id=tenant_id,
            medidas=_medidas_de(tabla),
            epicentro=_epicentro_de(fila, tabla),
            niveles=niveles_de(umbral),
        )
    finally:
        # Cierra la transacción: `SET LOCAL` y `set_config(..., is_local=true)`
        # mueren con ella, así que el incidente siguiente empieza limpio y no
        # hereda el tenant del anterior. Sólo se leyó: no hay nada que commitear.
        await conn.rollback()


def _medidas_de(tabla: EstacionesOut) -> tuple[C.Medida, ...]:
    """Capa 1, tomada de la tabla por estación (`T-7.17`) sin re-consultar nada.

    Los CUATRO datos del punto —pico de PGA, pico de PGV, hora del pico y voto de
    cuórum— salen de la misma lectura, que es lo que impide que el mapa y la
    tabla del operador cuenten historias distintas del mismo inmueble.

    ⚠️ `pgv_cms` viajó en `None` hasta el 2026-09-21 mientras el contrato lo
    prometía y el PDF del dictamen le imprimía una columna: un campo que no se
    puede llenar es peor que uno que no se promete. Se resolvió ampliando la
    consulta que YA existe en `build_estaciones` (`peak_pgv_cms`), no abriendo
    una cuarta: dos caminos a los mismos números acaban discrepando.
    """
    return tuple(
        C.Medida(
            site_id=e.site_id,
            site_code=e.site_code,
            site_name=e.site_name,
            lat=e.lat,
            lon=e.lon,
            dist_km=e.dist_km,
            pga_g=e.peak_pga_g,
            pgv_cms=e.peak_pgv_cms,
            medido_en=e.peak_ts,
            voto_contado=e.counted,
        )
        # Sin coordenadas no hay punto que pintar. `sites.geom` es NOT NULL, así
        # que esto no debería pasar nunca; si pasa, se cae el inmueble del mapa y
        # no el mapa entero.
        for e in tabla.items
        if e.lat is not None and e.lon is not None
    )


def _epicentro_de(fila: dict, tabla: EstacionesOut) -> C.Epicentro | None:
    """El origen del sismo, con de dónde salió, o ``None`` si no hay.

    Las coordenadas y la magnitud salen de la MISMA tabla por estación que
    calculó las distancias: si salieran de la consulta de candidatos y aquélla
    reubicara el epicentro, los puntos y los anillos quedarían centrados en sitios
    distintos y el mapa mentiría en el detalle que más se mira.
    """
    if tabla.epicentro_lat is None or tabla.epicentro_lon is None:
        return None
    meta = fila.get("evento_meta") or {}
    # ⚠️ Que HUBO consulta se reconoce por `provider`, que es NOT NULL en la
    # tabla — no por `answered_at` ni por `catalog_key`. Con esos dos, una
    # pregunta EN VUELO (`answered_at` NULL, sin clave todavía) se leía como
    # `sin_dato_externo`, o sea «nadie preguntó nunca», que es lo CONTRARIO de lo
    # que pasó. Es exactamente la confusión que `T-7.25` existe para impedir, y
    # aquí volvía a aparecer por el lado del mapa. Medido el 2026-09-20 con
    # `test_una_consulta_EN_VUELO_deja_el_epicentro_en_consultando`.
    consulta = (
        {
            "provider": fila.get("consulta_provider"),
            "asked_at": fila.get("consulta_asked_at"),
            "answered_at": fila.get("answered_at"),
            "outcome": fila.get("outcome"),
        }
        if fila.get("consulta_provider") is not None
        else None
    )
    estado = pr.de_consulta(
        consulta,
        {
            "source": fila.get("cat_source"),
            "consulted_at": fila.get("consulted_at"),
            "review_status": fila.get("review_status"),
            "provider_event_id": fila.get("provider_event_id"),
        }
        if fila.get("cat_source") is not None
        else None,
    )
    return C.Epicentro(
        lat=tabla.epicentro_lat,
        lon=tabla.epicentro_lon,
        depth_km=fila.get("depth_km"),
        magnitud=tabla.magnitude,
        # Quién lo localizó (`seismic_events.source`) y el estado del glosario
        # son cosas distintas: el centroide de nuestro propio cuórum es un
        # epicentro NUESTRO, y presentarlo sin decirlo lo confundiría con la
        # solución de una agencia.
        fuente=str(fila.get("evento_fuente") or "desconocida"),
        procedencia=estado.estado,
        catalog_key=fila.get("consulta_key") or (meta.get("reproduccion") or {}).get("catalog_key"),
    )
