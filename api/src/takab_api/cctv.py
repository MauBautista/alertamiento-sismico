"""Ensamblado del CCTV de un incidente (T-3.12.c).

Una sola función lo construye y la pantalla y el PDF consumen el **mismo objeto** —misma
disciplina que `forensics`—. Si cada uno lo recalculara, tarde o temprano el reporte diría
un `t90` distinto del que el operador vio, y ése es el fallo que ningún revisor perdona.

TRES ESTADOS, Y CONFUNDIRLOS ES EL DEFECTO
──────────────────────────────────────────
* **sin cámara** — el sitio no tiene ninguna declarada. No hay nada que enseñar y se dice.
* **con clip, sin análisis** — el vídeo está y nadie lo ha contado todavía (hoy, mientras
  el Lambda espera ventana AWS). El reporte dice `ANÁLISIS PENDIENTE`, no un cero.
* **con análisis** — las métricas.

Los tres se ven igual si no se pregunta por la cámara, y significan cosas opuestas: «este
edificio no tiene CCTV» frente a «lo tiene y no grabó» frente a «grabó y nadie miró».

EL VEREDICTO DE REINGRESO SE DERIVA AQUÍ, Y TIENE UN GEMELO
───────────────────────────────────────────────────────────
La misma regla —una latencia de reingreso NEGATIVA es un hallazgo de seguridad, no un
número— vive también en `analyzer/takab_cctv/metricas.py::veredicto_reingreso`. Están
duplicadas porque son **dos paquetes que no se importan entre sí**: la API lee las métricas
ya calculadas de Postgres y el analizador las produce. Lo que no puede pasar es que una de
las dos deje de considerarlo un hallazgo, y por eso hay un test a cada lado.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.queries import cctv as q
from takab_api.schemas.cctv import (
    ANALISIS_PENDIENTE,
    NO_CCTV,
    CapturaOut,
    CctvOut,
    ClipOut,
    DiscrepanciaOut,
    EvacuacionOut,
)

#: Los cuatro papeles del reporte, en el orden en que se cuentan. Se listan SIEMPRE los
#: cuatro, con o sin foto: una fila ausente se confunde con una sección que no se generó.
PAPELES = ("pre", "egress", "peak", "reentry")

_SIN_FOTO = {
    "pre": "no hay captura del estado previo",
    "egress": "no hay captura del momento de mayor salida",
    "peak": "no hay captura del aforo máximo",
    "reentry": "no hay captura del inicio del reingreso",
}


def veredicto_reingreso(lag_s: float | None) -> tuple[bool, str]:
    """`(es_hallazgo, frase)`. Gemelo de `analyzer…metricas.veredicto_reingreso`."""
    if lag_s is None:
        return False, "SIN DATO · no se observó el inicio del reingreso"
    if lag_s < 0:
        return True, (
            f"⚠ EL REINGRESO EMPEZÓ {abs(lag_s):.0f} s ANTES del dictamen firmado: "
            "el inmueble se reocupó sin certificación de habitabilidad"
        )
    return False, f"el reingreso empezó {lag_s:.0f} s después del dictamen firmado"


def correlacion(t90_s: float | None, pga: float | None, pgv: float | None) -> str:
    """«Sacudió tanto, la gente tardó tanto» — el dato que ninguno de los dos da solo."""
    if t90_s is None:
        return "SIN TIEMPO DE SALIDA · no se pudo medir la evacuación"
    partes = []
    if pga is not None:
        partes.append(f"PGA {pga:.3f} g")
    if pgv is not None:
        partes.append(f"PGV {pgv:.1f} cm/s")
    if not partes:
        return f"la mayor parte salió en {t90_s:.0f} s · SIN SACUDIDA DECLARADA"
    return f"sacudida {' · '.join(partes)} — la mayor parte salió en {t90_s:.0f} s"


def _lectura_discrepancia(aforo: int | None, checkins: int | None) -> str:
    if aforo is None or checkins is None:
        return "SIN CRUCE · falta una de las dos estimaciones"
    d = aforo - checkins
    if d == 0:
        return "las dos estimaciones coinciden"
    if d > 0:
        return (
            f"{d} persona(s) MÁS en cámara que en el pase de lista: "
            "puede haber gente fuera que no confirmó"
        )
    return (
        f"{-d} persona(s) MÁS en el pase de lista que en cámara: "
        "puede haber gente que confirmó desde otro punto, o fuera del encuadre"
    )


async def build_cctv(conn: AsyncConnection, incident_id: str | UUID) -> CctvOut | None:
    """Todo el CCTV del incidente, o `None` si el incidente no es visible.

    `None` y no una excepción: quien llama decide si eso es un 404 (router) o una sección
    ausente (PDF). La RLS ya decidió qué incidentes existen para este request.
    """
    parametros = {"incident_id": str(incident_id)}
    fila_camara = (await conn.execute(q.HAY_CAMARA, parametros)).mappings().first()
    sacudida = (await conn.execute(q.SACUDIDA, parametros)).mappings().first()
    if sacudida is None:
        return None  # el incidente no existe para este request

    con_camara = bool(fila_camara and fila_camara["hay"])
    clips = [
        ClipOut(
            clip_id=r["clip_id"],
            started_at=r["started_at"],
            ended_at=r["ended_at"],
            sha256=r["sha256"],
            size_bytes=r["size_bytes"],
            coverage=r["coverage"],
            disponible=bool(r["s3_key"]),
            purged_at=r["purged_at"],
        )
        for r in (await conn.execute(q.CLIPS, parametros)).mappings()
    ]
    por_papel = {r["role"]: r for r in (await conn.execute(q.CAPTURAS, parametros)).mappings()}
    capturas = [
        CapturaOut(
            papel=papel,
            still_id=por_papel[papel]["still_id"],
            captured_at=por_papel[papel]["captured_at"],
            sha256=por_papel[papel]["sha256"],
            disponible=bool(por_papel[papel]["s3_key"]),
            purged_at=por_papel[papel]["purged_at"],
        )
        if papel in por_papel
        else CapturaOut(papel=papel, razon=_SIN_FOTO[papel])
        for papel in PAPELES
    ]

    metricas = (await conn.execute(q.METRICAS, parametros)).mappings().first()
    if metricas is None:
        estado = (
            ANALISIS_PENDIENTE
            if clips
            else NO_CCTV
            if not con_camara
            else ("CÁMARA DECLARADA · sin clip para este incidente")
        )
        return CctvOut(
            incident_id=UUID(str(incident_id)),
            con_camara=con_camara,
            estado=estado,
            clips=clips,
            capturas=capturas,
        )

    es_hallazgo, frase = veredicto_reingreso(metricas["reentry_lag_s"])
    return CctvOut(
        incident_id=UUID(str(incident_id)),
        con_camara=con_camara,
        estado="análisis disponible",
        clips=clips,
        capturas=capturas,
        evacuacion=EvacuacionOut(
            peak_n=metricas["peak_n"],
            peak_at=metricas["peak_at"],
            t50_s=metricas["t50_s"],
            t90_s=metricas["t90_s"],
            reentry_start_at=metricas["reentry_start_at"],
            dictamen_lag_s=metricas["dictamen_lag_s"],
            reentry_lag_s=metricas["reentry_lag_s"],
            reingreso_antes_del_dictamen=es_hallazgo,
            veredicto_reingreso=frase,
            correlacion=correlacion(
                metricas["t90_s"], sacudida["max_pga_g"], sacudida["max_pgv_cms"]
            ),
            provenance=metricas["provenance"],
        ),
        discrepancia=DiscrepanciaOut(
            aforo_camara=metricas["peak_n"],
            checkins=metricas["checkin_count"],
            diferencia=(
                metricas["peak_n"] - metricas["checkin_count"]
                if metricas["peak_n"] is not None and metricas["checkin_count"] is not None
                else None
            ),
            lectura=_lectura_discrepancia(metricas["peak_n"], metricas["checkin_count"]),
        ),
    )
