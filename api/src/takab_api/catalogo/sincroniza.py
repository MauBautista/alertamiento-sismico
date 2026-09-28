"""[T-9.60 · D-46] El worker `catalog-sync`: el catálogo de México al día.

``python -m takab_api.catalogo.sincroniza [--poll-interval 600]``

Cada pasada le pregunta a USGS por lo que CAMBIÓ (``updatedafter``) en la caja de
México desde la última marca, con M≥``catalog_sync_min_mag``, y lo escribe en
``reference_earthquakes`` con ``origen = 'catalog_sync'``. De ahí lo leen la app
(«sismos cerca de tu inmueble», ``GET /sites/{id}/sismos``), el historial del
inmueble y la consola.

LAS CUATRO PROPIEDADES QUE NO SON NEGOCIABLES
─────────────────────────────────────────────

**1 · Nunca queda ``ok`` si no se escribió.** Un fallo de la fuente o de la base
deja ``fallido`` con su motivo (recortado a 300) y NO avanza ``ultimo_updated``:
la pasada siguiente vuelve a pedir lo mismo. ``ultimo_ok`` es lo que la app pinta
como «actualizado»; un catálogo congelado que dijera «al día» es la mentira que
la regla de oro 7 prohíbe.

**2 · Una fila de otro origen no se pisa.** El ``DO UPDATE`` lleva ``WHERE
reference_earthquakes.origen = 'catalog_sync'``: una fila sembrada o de la
consulta por incidente puede estar citada por un dictamen firmado. Se CUENTA
(``respetadas``) en vez de callarse.

**3 · Apagado, ocupado y truncado se DICEN.** Apagado (``catalog_usgs_enabled``,
el mismo gate que la consulta) escribe ``apagado`` en el estado y no abre un
socket. Ocupado (otra instancia con el cerrojo) lo dice el log y el resultado.
Truncado (la fuente devolvió ``limit`` eventos) guarda un cursor y lo dice.

**4 · El truncado no se salta eventos.** La fuente ordena por hora de ORIGEN
(``time-asc``) y no por ``updated``: avanzar la marca al ``updated`` del último
procesado se saltaría los que faltan si tienen un ``updated`` menor. Así que al
truncar la marca NO se mueve; se guarda ``pagina_desde`` (el origen del último) y
la pasada siguiente sigue con ``starttime`` desde ahí. Al terminar la última
página, la marca sube al mayor ``updated`` de TODAS (``pagina_max_updated``).

**Nada de esto toca el camino crítico** (reglas de oro 1 y 2): proceso aparte,
post-hoc, sobre datos públicos. Sin internet, el catálogo se queda viejo y el
estado lo dice; el gabinete no se entera.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

import psycopg

from takab_api.catalogo import fdsn
from takab_api.catalogo.consulta import _verifica_el_epicentro
from takab_api.db import pool
from takab_api.settings import Settings

log = logging.getLogger("takab_api.catalogo.sincroniza")

#: Cerrojo de la pasada. De TRANSACCIÓN: la pasada es una sola transacción (lee el
#: estado, pregunta, escribe y commitea), así que el cerrojo se suelta solo al
#: terminar, también si el proceso muere. Distinto del de la consulta (0x7A25):
#: las dos pasadas pueden correr a la vez, y su única tabla común es idempotente.
LOCK_KEY = 0x7A960

#: Tope del motivo que se escribe. Un traceback de psycopg puede traer la sentencia
#: entera; el estado es para leerlo de un vistazo, el detalle va al log.
_MAX_ERROR = 300

OK = "ok"
FALLIDO = "fallido"
APAGADO = "apagado"
#: No es un estado de la tabla: es lo que devuelve una pasada que no tomó el cerrojo.
OCUPADO = "ocupado"


@dataclass(frozen=True)
class PasadaSync:
    """Lo que hizo una pasada. ``estado`` es el que quedó escrito (o ``ocupado``)."""

    estado: str
    escritos: int = 0
    #: Filas de OTRO origen que la fuente devolvió y no se tocaron (propiedad 2).
    respetadas: int = 0
    #: Eventos sin magnitud publicada: ``reference_earthquakes.magnitude`` es NOT
    #: NULL, y una magnitud inventada sería peor que la ausencia.
    sin_magnitud: int = 0
    truncada: bool = False
    error: str | None = None


_ASEGURA_SQL = (
    "INSERT INTO catalog_sync_state (fuente, estado) VALUES (%s, 'nunca') "
    "ON CONFLICT (fuente) DO NOTHING"
)
_LEE_SQL = (
    "SELECT estado, ultimo_updated, ultimo_ok, pagina_desde, pagina_max_updated "
    "FROM catalog_sync_state WHERE fuente = %s FOR UPDATE"
)
_ANOTA_SQL = (
    "UPDATE catalog_sync_state SET estado = %(estado)s, ultima_corrida = %(ahora)s, "
    "error = %(error)s WHERE fuente = %(fuente)s"
)
_OK_SQL = (
    "UPDATE catalog_sync_state SET estado = 'ok', ultima_corrida = %(ahora)s, "
    "ultimo_ok = %(ahora)s, n_ultima = %(n)s, error = NULL, "
    "ultimo_updated = %(marca)s, pagina_desde = %(pagina)s, "
    "pagina_max_updated = %(pagina_max)s WHERE fuente = %(fuente)s"
)

#: El upsert. ``catalog_key`` de una fila nueva: ``USGS-<id del proveedor>``, la
#: misma que propone la consulta, así que las dos convergen en la misma fila.
#: ``created_at`` y ``origen`` no se tocan nunca en el ``DO UPDATE``.
_UPSERT_SQL = """
INSERT INTO reference_earthquakes
       (catalog_key, origin_time, magnitude, place, epicenter, depth_km,
        source, source_ref, consulted_at, review_status, provider_event_id,
        origen, usgs_mmi, usgs_url, actualizado_en_fuente)
VALUES (%(key)s, %(t0)s, %(mag)s, %(place)s,
        ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
        %(depth)s, %(source)s, %(ref)s, %(consultado)s, %(estado)s, %(pid)s,
        'catalog_sync', %(mmi)s, %(url)s, %(updated)s)
ON CONFLICT (source, provider_event_id) WHERE provider_event_id IS NOT NULL
DO UPDATE SET origin_time           = EXCLUDED.origin_time,
              magnitude             = EXCLUDED.magnitude,
              place                 = EXCLUDED.place,
              epicenter             = EXCLUDED.epicenter,
              depth_km              = EXCLUDED.depth_km,
              source_ref            = EXCLUDED.source_ref,
              consulted_at          = EXCLUDED.consulted_at,
              review_status         = EXCLUDED.review_status,
              usgs_mmi              = EXCLUDED.usgs_mmi,
              usgs_url              = EXCLUDED.usgs_url,
              actualizado_en_fuente = EXCLUDED.actualizado_en_fuente
        WHERE reference_earthquakes.origen = 'catalog_sync'
RETURNING catalog_key,
          ST_X(epicenter::geometry)::float8 AS lon_escrita,
          ST_Y(epicenter::geometry)::float8 AS lat_escrita
"""


def _mayor(*marcas: datetime | None) -> datetime | None:
    vivas = [m for m in marcas if m is not None]
    return max(vivas) if vivas else None


def run_catalog_sync_pass(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    now: datetime | None = None,
    transport: Any | None = None,
) -> PasadaSync:
    """Una pasada. Nunca levanta por la fuente ni por la base: lo ESCRIBE."""
    ahora = now or datetime.now(tz=UTC)
    tomado = conn.execute("SELECT pg_try_advisory_xact_lock(%s) AS tomado", (LOCK_KEY,)).fetchone()[
        "tomado"
    ]
    if not tomado:
        # No es un error ni se reintenta aquí: la siguiente pasada llega sola.
        # Pero se DICE: un cerrojo que no se suelta dejaría esta rama como un no-op
        # silencioso para siempre.
        log.info("catalog-sync: otra instancia tiene el cerrojo; no se preguntó nada")
        conn.rollback()
        return PasadaSync(OCUPADO)

    conn.execute(_ASEGURA_SQL, (fdsn.PROVEEDOR,))
    st = conn.execute(_LEE_SQL, (fdsn.PROVEEDOR,)).fetchone()

    if not settings.catalog_usgs_enabled:
        motivo = "la consulta a USGS está apagada por configuración"
        _anota(conn, APAGADO, ahora, motivo)
        conn.commit()
        return PasadaSync(APAGADO, error=motivo)

    arranque = ahora - timedelta(days=settings.catalog_sync_arranque_dias)
    try:
        resp = fdsn.sincroniza(
            settings,
            desde_updated=st["ultimo_updated"] or arranque,
            desde_origen=st["pagina_desde"] or arranque,
            transport=transport,
            now=ahora,
        )
    except fdsn.SinRespuesta as exc:
        return _falla(conn, ahora, exc.motivo)

    try:
        pasada = _escribe(conn, settings, resp, st, ahora)
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - lo que falle se ESCRIBE, no se traga
        log.exception("catalog-sync: la escritura falló; el estado queda `fallido`")
        conn.rollback()
        return _falla(conn, ahora, f"{type(exc).__name__}: {exc}")

    if pasada.truncada:
        log.warning(
            "catalog-sync: la fuente devolvió el límite (%s); la siguiente pasada "
            "sigue desde el último origen procesado",
            settings.catalog_sync_limite,
        )
    log.info(
        "catalog-sync: %s escritos, %s de otro origen respetados, %s sin magnitud",
        pasada.escritos,
        pasada.respetadas,
        pasada.sin_magnitud,
    )
    return pasada


def _escribe(
    conn: psycopg.Connection,
    settings: Settings,
    resp: fdsn.Respuesta,
    st: dict,
    ahora: datetime,
) -> PasadaSync:
    escritos = respetadas = sin_magnitud = 0
    mayor_updated: datetime | None = None
    for evento in resp.eventos:
        if evento.magnitude is None:
            sin_magnitud += 1
            continue
        if _graba(conn, evento, resp):
            escritos += 1
        else:
            respetadas += 1
        mayor_updated = _mayor(mayor_updated, evento.actualizado_en_fuente)

    publicados = resp.publicados if resp.publicados is not None else len(resp.eventos)
    truncada = publicados >= settings.catalog_sync_limite and bool(resp.eventos)
    pagina_max = _mayor(st["pagina_max_updated"], mayor_updated)
    if truncada:
        # Propiedad 4: la marca se queda; avanza el cursor de ORIGEN. `starttime`
        # es inclusivo, así que el último se vuelve a pedir: idempotente.
        marca = st["ultimo_updated"]
        pagina = max(e.origin_time for e in resp.eventos)
    else:
        marca = _mayor(st["ultimo_updated"], pagina_max)
        pagina = pagina_max = None
    conn.execute(
        _OK_SQL,
        {
            "fuente": fdsn.PROVEEDOR,
            "ahora": ahora,
            "n": escritos,
            "marca": marca,
            "pagina": pagina,
            "pagina_max": pagina_max,
        },
    )
    return PasadaSync(
        OK,
        escritos=escritos,
        respetadas=respetadas,
        sin_magnitud=sin_magnitud,
        truncada=truncada,
    )


def _graba(conn: psycopg.Connection, evento: fdsn.EventoPublicado, resp: fdsn.Respuesta) -> bool:
    """Upsert de un evento. ``False`` = la fila es de otro origen y no se tocó."""
    fila = conn.execute(
        _UPSERT_SQL,
        {
            "key": f"{fdsn.PROVEEDOR}-{evento.provider_event_id}",
            "t0": evento.origin_time,
            "mag": evento.magnitude,
            "place": evento.place,
            "lon": evento.lon,
            "lat": evento.lat,
            "depth": evento.depth_km,
            "source": fdsn.PROVEEDOR,
            "ref": fdsn.cita(evento, resp.url),
            "consultado": resp.consultado_en,
            "estado": evento.review_status,
            "pid": evento.provider_event_id,
            "mmi": evento.mmi,
            "url": evento.url,
            "updated": evento.actualizado_en_fuente,
        },
    ).fetchone()
    if fila is None:
        return False
    # La misma relectura que la consulta: un [lat, lon] invertido no da error en
    # PostGIS, da un epicentro en el Caribe con la cita de un sismo de Oaxaca.
    _verifica_el_epicentro(evento, fila)
    return True


def _anota(conn: psycopg.Connection, estado: str, ahora: datetime, error: str | None) -> None:
    conn.execute(
        _ANOTA_SQL,
        {"estado": estado, "ahora": ahora, "error": error, "fuente": fdsn.PROVEEDOR},
    )


def _falla(conn: psycopg.Connection, ahora: datetime, motivo: str) -> PasadaSync:
    """``fallido`` sin tocar la marca, el cursor ni ``ultimo_ok`` (propiedad 1).

    Puede llegar tras un ``rollback`` que deshizo también la fila del estado, así
    que la vuelve a asegurar.
    """
    recortado = motivo[:_MAX_ERROR]
    log.warning("catalog-sync: pasada fallida (%s)", recortado)
    conn.execute(_ASEGURA_SQL, (fdsn.PROVEEDOR,))
    _anota(conn, FALLIDO, ahora, recortado)
    conn.commit()
    return PasadaSync(FALLIDO, error=recortado)


# ---------------------------------------------------------------------------
# El proceso
# ---------------------------------------------------------------------------


def _pasada_con_conexion(
    conn_factory: Callable[[], psycopg.Connection], settings: Settings
) -> PasadaSync:
    conn = conn_factory()
    try:
        return run_catalog_sync_pass(conn, settings)
    finally:
        conn.close()


class CatalogSyncWorker:
    """Una pasada cada ``poll_s``; un fallo de la pasada se registra y no mata el bucle."""

    def __init__(
        self,
        conn_factory: Callable[[], Any],
        settings: Settings,
        *,
        poll_s: float,
        pasada: Callable[[Callable[[], Any], Settings], object] = _pasada_con_conexion,
    ) -> None:
        self._conn_factory = conn_factory
        self._settings = settings
        self._poll_s = poll_s
        self._pasada = pasada
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self._pasada(self._conn_factory, self._settings)
            except Exception:  # noqa: BLE001 - la vuelta siguiente reintenta
                log.exception("catalog-sync: la pasada falló; se reintenta en la siguiente")
            self._stop.wait(self._poll_s)

    def stop(self) -> None:
        self._stop.set()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="takab_api.catalogo.sincroniza", description=__doc__)
    parser.add_argument("--poll-interval", type=float, default=None, dest="poll_s")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    poll_s = args.poll_s if args.poll_s is not None else settings.catalog_sync_intervalo_s
    worker = CatalogSyncWorker(
        partial(pool.connect, settings.database_url), settings, poll_s=poll_s
    )

    def _para(signum: int, _frame: object) -> None:
        log.info("señal %s recibida; cierre gracioso", signal.Signals(signum).name)
        worker.stop()

    signal.signal(signal.SIGTERM, _para)
    signal.signal(signal.SIGINT, _para)
    log.info(
        "catalog-sync iniciado (poll=%ss, encendido=%s)", poll_s, settings.catalog_usgs_enabled
    )
    worker.run()


if __name__ == "__main__":
    main()
