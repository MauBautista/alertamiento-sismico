"""SQL del CCTV de un incidente (T-3.12.c). Solo lectura: quien escribe es el worker."""

from __future__ import annotations

from sqlalchemy import text

#: ¿Tiene este sitio cámara declarada? Es lo que distingue «no hay nada que enseñar» de
#: «hay cámara y no grabó», que son dos fallos MUY distintos y se leen igual si no se
#: pregunta. Se mira por el SITIO del incidente, no por el incidente.
HAY_CAMARA = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM cameras c
        JOIN incidents i ON i.site_id = c.site_id
        WHERE i.incident_id = :incident_id AND c.enabled
    ) AS hay
    """
)

CLIPS = text(
    """
    SELECT clip_id, started_at, ended_at, sha256, size_bytes,
           coverage::float8 AS coverage, s3_key, purged_at
    FROM cctv_clips
    WHERE incident_id = :incident_id
    ORDER BY started_at
    """
)

#: Solo las capturas del REPORTE. El goteo (`role='drip'`) son cientos por incidente y no
#: se listan: son materia prima del conteo, no evidencia que nadie vaya a mirar una a una.
CAPTURAS = text(
    """
    SELECT still_id, role, captured_at, sha256, s3_key, purged_at
    FROM cctv_stills
    WHERE incident_id = :incident_id AND role <> 'drip'
    ORDER BY captured_at
    """
)

#: Las métricas, prefiriendo el conteo FINAL de la nube sobre el preliminar del borde. El
#: `ORDER BY` no es cosmético: si existen las dos filas, la que manda es la final.
METRICAS = text(
    """
    SELECT provenance, t50_s::float8 AS t50_s, t90_s::float8 AS t90_s, peak_n, peak_at,
           reentry_start_at, dictamen_lag_s::float8 AS dictamen_lag_s,
           reentry_lag_s::float8 AS reentry_lag_s, checkin_count
    FROM cctv_evacuation_metrics
    WHERE incident_id = :incident_id
    ORDER BY (provenance = 'final') DESC
    LIMIT 1
    """
)

#: La sacudida, para leerla AL LADO de `t90`. Sale del sismómetro, no de la cámara.
SACUDIDA = text(
    """
    SELECT max_pga_g::float8 AS max_pga_g, max_pgv_cms::float8 AS max_pgv_cms
    FROM incidents WHERE incident_id = :incident_id
    """
)

#: Un clip concreto, para la descarga. Devuelve el tenant para poder auditar sin volver
#: a consultar, y `s3_key` NULL significa podado — no «no existe».
CLIP = text(
    """
    SELECT clip_id, tenant_id, s3_key, purged_at, sha256
    FROM cctv_clips WHERE clip_id = :clip_id
    """
)
