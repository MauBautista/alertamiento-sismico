"""[T-7.14] Armar la reproducción, y vestir con ella el incidente que abra el WR-1.

Dos mitades con dueños distintos, como el modo demostración (`D-27`):

* **Armar/desarmar** lo hace una persona por la API (`routers/demo_mode.py`), con
  su ventana acotada en la base y su fila de auditoría.
* **Vestir** lo hace el worker `takab_api.incident` en su pasada, DESPUÉS de que
  el incidente exista. Nunca la ingesta: el camino que abre un incidente por un
  pulso del WR-1 no se toca ni se alarga (regla de oro 1).

**Jamás crea incidentes ni votos de cuórum.** Escribe un `seismic_events` de
`source='external'` y lo ENLAZA al incidente que ya existía. Un `EVT-REP` que
creara incidentes convertiría una demostración en una alerta para edificios que
no sintieron nada, y un voto de cuórum falsificaría la corroboración de la red —
que es el hecho sobre el que la nube manda comandos firmados.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from psycopg.types.json import Jsonb
from sqlalchemy import text

from takab_api.replay.plan import Estacion, Sismo, plan_de_arribos, velocidades

if TYPE_CHECKING:
    import psycopg
    from sqlalchemy.ext.asyncio import AsyncConnection

    from takab_api.settings import Settings

logger = logging.getLogger("takab_api.replay")

#: Un sitio de DEMOSTRACIÓN se reconoce por el prefijo de su código, igual que en
#: la consola (`web/src/features/fleet/datosDeDemostracion.ts`) y por la misma
#: razón: la convención ya existe, ya la defiende `edge/tests/test_fleet_sim.py`,
#: y una columna nueva sería una segunda verdad sobre el mismo hecho. El patrón va
#: ANCLADO: un `LIKE '%sim%'` marcaría como demo un sitio real llamado
#: `site-simon-01`, y equivocarse en esa dirección —armar una reproducción sobre
#: un edificio con gente dentro— es el error caro.
#: Los dos espejos los compara `api/tests/replay/test_service.py`.
PATRON_SITIO_DEMO = r"^site-sim-[0-9]+$"

#: Tope de la ventana. Espejo del CHECK de la base, que es quien manda: aquí está
#: para contestar 4xx en vez de dejar que reviente la restricción.
VENTANA_MAXIMA_S = 8 * 3600
VENTANA_DEFECTO_S = 3600


class SinSitiosDemo(Exception):
    """El cliente no tiene ningún sitio de demostración."""


class SismoDesconocido(Exception):
    """El `catalog_key` no está en `reference_earthquakes`."""


@dataclass(frozen=True)
class Ventana:
    tenant_id: str
    catalog_key: str
    armed_by: str
    armed_at: datetime
    armed_until: datetime
    note: str

    def restante_s(self, ahora: datetime | None = None) -> float:
        return max(0.0, (self.armed_until - (ahora or datetime.now(tz=UTC))).total_seconds())


_VIVA_SQL = """
SELECT tenant_id, catalog_key, armed_by, armed_at, armed_until, note
  FROM demo_replay
 WHERE tenant_id = CAST(:t AS uuid) AND armed_until > now()
"""


async def ventana_viva(conn: AsyncConnection, tenant_id: str) -> Ventana | None:
    fila = (await conn.execute(text(_VIVA_SQL), {"t": tenant_id})).first()
    return None if fila is None else _ventana(fila._mapping)


def ventana_viva_sync(conn: psycopg.Connection, tenant_id: str) -> Ventana | None:
    fila = conn.execute(
        _VIVA_SQL.replace("CAST(:t AS uuid)", "CAST(%(t)s AS uuid)"), {"t": tenant_id}
    ).fetchone()
    return None if fila is None else _ventana(fila)


def _ventana(m) -> Ventana:
    return Ventana(
        tenant_id=str(m["tenant_id"]),
        catalog_key=m["catalog_key"],
        armed_by=str(m["armed_by"]),
        armed_at=m["armed_at"],
        armed_until=m["armed_until"],
        note=m["note"],
    )


def ventana_maxima(segundos: int | None) -> int:
    """Recorta al techo en vez de rechazar: pedir de más es querer más tiempo."""
    if segundos is None or segundos <= 0:
        return VENTANA_DEFECTO_S
    return min(segundos, VENTANA_MAXIMA_S)


async def armar(
    conn: AsyncConnection,
    *,
    tenant_id: str,
    catalog_key: str,
    actor: str,
    segundos: int | None,
    note: str = "",
    now: datetime | None = None,
) -> Ventana:
    """Arma la ventana. Re-armar la PISA: dos ventanas serían dos verdades.

    Exige sitios de demostración en el cliente. Es LA guarda de esta ficha: sin
    ella, un superadmin podría armar una reproducción sobre un cliente real y sus
    incidentes saldrían rotulados como demostración.
    """
    ahora = now or datetime.now(tz=UTC)
    tiene_demo = (
        await conn.execute(
            text(
                "SELECT 1 FROM sites WHERE tenant_id = CAST(:t AS uuid) AND code ~ :patron LIMIT 1"
            ),
            {"t": tenant_id, "patron": PATRON_SITIO_DEMO},
        )
    ).first()
    if tiene_demo is None:
        raise SinSitiosDemo(tenant_id)

    existe = (
        await conn.execute(
            text("SELECT 1 FROM reference_earthquakes WHERE catalog_key = :k"),
            {"k": catalog_key},
        )
    ).first()
    if existe is None:
        raise SismoDesconocido(catalog_key)

    hasta = ahora + timedelta(seconds=ventana_maxima(segundos))
    # Re-armar es REEMPLAZAR, y se escribe como tal: borrado + alta, no
    # `ON CONFLICT DO UPDATE`. Mismo razonamiento que `demo_mode.encender`, y las
    # dos mitades importan. Privilegio: el `DO UPDATE` exige UPDATE sobre la
    # tabla, y darlo dejaría a la API capaz de correrle la hora de vencimiento a
    # una ventana viva sin que eso fuera un acto nuevo. Semántica: una ventana
    # re-armada tiene su propio `armed_at`, porque es otra ventana.
    await conn.execute(
        text("DELETE FROM demo_replay WHERE tenant_id = CAST(:t AS uuid)"), {"t": tenant_id}
    )
    await conn.execute(
        text(
            "INSERT INTO demo_replay (tenant_id, catalog_key, armed_by, armed_at,"
            " armed_until, note)"
            " VALUES (CAST(:t AS uuid), :k, CAST(:by AS uuid), :at, :until, :note)"
        ),
        {
            "t": tenant_id,
            "k": catalog_key,
            "by": actor,
            "at": ahora,
            "until": hasta,
            "note": note,
        },
    )
    return Ventana(
        tenant_id=tenant_id,
        catalog_key=catalog_key,
        armed_by=actor,
        armed_at=ahora,
        armed_until=hasta,
        note=note,
    )


async def desarmar(conn: AsyncConnection, *, tenant_id: str) -> bool:
    """Idempotente: desarmar lo ya desarmado no es un error, es el estado que se quería."""
    cur = await conn.execute(
        text("DELETE FROM demo_replay WHERE tenant_id = CAST(:t AS uuid)"), {"t": tenant_id}
    )
    return cur.rowcount > 0


# ─────────────────────────────────────────────── la pasada del worker

#: Clave del advisory lock de la pasada.
_REPLAY_LOCK_KEY = 0x7A14

#: Los incidentes que se visten: abiertos por el WR-1, todavía sin evento
#: enlazado y en un cliente con la ventana viva. `event_id IS NULL` es lo que hace
#: la pasada idempotente sin una tabla de control: una vez enlazado, no vuelve.
_CANDIDATOS_SQL = """
SELECT i.incident_id, i.tenant_id, i.opened_at,
       r.catalog_key, r.armed_until,
       e.origin_time, e.magnitude, e.depth_km,
       ST_Y(e.epicenter::geometry) AS lat, ST_X(e.epicenter::geometry) AS lon
  FROM incidents i
  JOIN demo_replay r ON r.tenant_id = i.tenant_id
  JOIN reference_earthquakes e ON e.catalog_key = r.catalog_key
 WHERE i.trigger = 'sasmex'
   AND i.event_id IS NULL
   AND i.opened_at >= %(desde)s
   AND i.opened_at <= r.armed_until
 ORDER BY i.opened_at
 LIMIT %(lim)s
"""

#: Las estaciones que sienten la reproducción: todos los sitios del cliente con
#: gabinete no retirado. No solo los DEMO — el gabinete real es el que da el
#: pulso y tiene que aparecer en el plan.
_ESTACIONES_SQL = """
SELECT DISTINCT s.site_id, s.code,
       ST_Y(s.geom::geometry) AS lat, ST_X(s.geom::geometry) AS lon
  FROM sites s
  JOIN gateways g ON g.site_id = s.site_id AND g.status <> 'retired'
 WHERE s.tenant_id = %(tenant)s
 ORDER BY s.code
"""

_INSERTA_EVENTO_SQL = """
INSERT INTO seismic_events (event_id, source, magnitude, epicenter, depth_km, detected_at, meta)
VALUES (%(id)s, 'external', %(mag)s,
        ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
        %(depth)s, %(t0)s, %(meta)s)
ON CONFLICT (event_id) DO NOTHING
"""

_ENLAZA_SQL = (
    "UPDATE incidents SET event_id = %(ev)s WHERE incident_id = %(id)s AND event_id IS NULL"
)


def event_id_de(tenant_id: str, catalog_key: str, t0: datetime) -> str:
    """``EVT-REP-<hash>`` determinista, con `t0` redondeado al MINUTO.

    Dos gabinetes del mismo cliente que abran incidente por el mismo pulso caen en
    el mismo minuto y comparten evento — que es la verdad: un sismo, un evento. El
    precio es que dos pulsos separados por segundos se funden; en una demostración
    eso es lo que se quiere, y fuera de una demostración no hay ventana armada.
    """
    minuto = t0.astimezone(UTC).replace(second=0, microsecond=0).isoformat()
    semilla = f"{tenant_id}|{catalog_key}|{minuto}".encode()
    return f"EVT-REP-{hashlib.md5(semilla, usedforsecurity=False).hexdigest()[:12]}"


@dataclass(frozen=True)
class PasadaDeReproduccion:
    vestidos: list[str]


def run_replay_pass(
    conn: psycopg.Connection,
    settings: Settings,
    *,
    now: datetime | None = None,
    lookback_s: float = 300.0,
    max_por_pasada: int = 50,
) -> PasadaDeReproduccion:
    """Viste de reproducción los incidentes del WR-1 en clientes con ventana viva.

    Un COMMIT si escribió algo; ROLLBACK si solo leyó (patrón del dictamen).
    """
    ahora = now or datetime.now(tz=UTC)
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_REPLAY_LOCK_KEY,))
    filas = conn.execute(
        _CANDIDATOS_SQL,
        {"desde": ahora - timedelta(seconds=lookback_s), "lim": max_por_pasada},
    ).fetchall()

    vestidos: list[str] = []
    for fila in filas:
        if fila["armed_until"] <= ahora:
            continue  # la ventana venció entre la consulta y aquí: no se viste
        vestidos.append(_vestir(conn, fila, settings))

    if vestidos:
        conn.commit()
        logger.info("reproducción: %d incidentes vestidos", len(vestidos))
    else:
        conn.rollback()
    return PasadaDeReproduccion(vestidos=vestidos)


def _vestir(conn: psycopg.Connection, fila: dict, settings: Settings) -> str:
    tenant_id = str(fila["tenant_id"])
    t0_demo = fila["opened_at"]
    event_id = event_id_de(tenant_id, fila["catalog_key"], t0_demo)

    estaciones = [
        Estacion(str(r["site_id"]), r["code"], float(r["lat"]), float(r["lon"]))
        for r in conn.execute(_ESTACIONES_SQL, {"tenant": fila["tenant_id"]}).fetchall()
    ]
    sismo = _sismo_de(fila, settings)
    plan = plan_de_arribos(sismo, estaciones)

    conn.execute(
        _INSERTA_EVENTO_SQL,
        {
            "id": event_id,
            "mag": fila["magnitude"],
            "lon": sismo.lon,
            "lat": sismo.lat,
            "depth": fila["depth_km"],
            "t0": t0_demo,
            "meta": Jsonb(
                {
                    # El rótulo. No se borra, así que después siempre se puede
                    # saber qué incidentes se vistieron de demostración.
                    "reproduccion": {
                        "catalog_key": fila["catalog_key"],
                        "t0_real": fila["origin_time"].astimezone(UTC).isoformat(),
                        "t0_demo": t0_demo.astimezone(UTC).isoformat(),
                    },
                    # Cuántas estaciones sienten la onda en esta reproducción. Va
                    # PEGADO al rótulo a propósito: nadie puede leer la
                    # corroboración sin ver que es una reproducción.
                    "node_count": len(plan),
                    "v_p_km_s": sismo.v_p_km_s,
                    "v_s_km_s": sismo.v_s_km_s,
                }
            ),
        },
    )
    conn.execute(_ENLAZA_SQL, {"ev": event_id, "id": fila["incident_id"]})
    return str(fila["incident_id"])


def _sismo_de(fila: dict, settings: Settings) -> Sismo:
    v_p, v_s = velocidades(settings.replay_v_s_km_s)
    return Sismo(
        catalog_key=fila["catalog_key"],
        magnitude=float(fila["magnitude"]),
        lat=float(fila["lat"]),
        lon=float(fila["lon"]),
        depth_km=None if fila["depth_km"] is None else float(fila["depth_km"]),
        v_s_km_s=v_s,
        v_p_km_s=v_p,
    )


def compila_patron_demo() -> re.Pattern[str]:
    """El patrón como regex de Python; la base usa el mismo literal con `~`."""
    return re.compile(PATRON_SITIO_DEMO)
