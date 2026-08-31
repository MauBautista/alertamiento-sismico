"""El ejecutor del conteo en la nube (T-3.12.b · `D-24`).

Un mensaje SQS por clip registrado; el handler baja el vídeo y el goteo del incidente,
corre el **mismo núcleo que el CLI** (`pipeline.analizar`) y escribe la curva y las
métricas con `provenance='final'`.

POR QUÉ SQS Y NO UNA NOTIFICACIÓN DE S3 DIRECTA
───────────────────────────────────────────────
La tentación era colgar el Lambda del bucket. No se puede, y el motivo es concreto: el
prefijo `evidence/` **ya tiene** una notificación hacia la cola de backfill, y S3 rechaza
configuraciones con filtros solapados. Colgar el Lambda de `evidence/*.mp4` chocaría con la
que ya existe y **rompería la ingesta del miniSEED**, que es lo que registra los objetos.

Así que el disparo lo da quien ya sabe que un clip acaba de existir: el worker de backfill,
en el mismo punto donde audita el egreso —cuando su `INSERT … RETURNING` dice que la fila
es NUEVA—. Eso hereda gratis su idempotencia: SQS entrega *at-least-once*, y una reentrega
no vuelve a encolar porque no vuelve a crear.

LO QUE ESTE HANDLER NO HACE, Y ES DELIBERADO
────────────────────────────────────────────
**No inventa un análisis cuando algo falta.** Si el clip no está, si el modelo no carga o
si el ffmpeg no es apto, **lanza** y deja que el mensaje vuelva a la cola y acabe en la DLQ.
La alternativa —escribir métricas a medias— dejaría en el dictamen unos números que nadie
podría distinguir de los buenos. El reporte ya sabe decir `CLIP DISPONIBLE · ANÁLISIS
PENDIENTE`, que es la verdad mientras esto no termine.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from takab_cctv.capturas import fotogramas_del_goteo
from takab_cctv.detector import Montaje, cargar_onnx
from takab_cctv.pipeline import analizar, fotogramas_del_clip

log = logging.getLogger("takab_cctv.lambda")

#: Dónde viven el modelo y el ffmpeg DENTRO de la imagen. Los dos van horneados y no se
#: descargan en arranque: un número que acaba en un dictamen tiene que poder atribuirse a
#: una versión exacta del modelo, y un peso que se baja al vuelo no permite decir cuál era.
MODELO = os.environ.get("TAKAB_CCTV_MODELO", "/opt/modelos/yolox_nano.onnx")
FFMPEG = os.environ.get("TAKAB_CCTV_FFMPEG", "/opt/bin/ffmpeg")

#: Muestreo del clip. Ver `capturas.extraer`: la evacuación dura minutos y el aforo se mide
#: por fotograma, no por trayectoria.
FPS = float(os.environ.get("TAKAB_CCTV_FPS", "0.5"))


class AnalisisImposible(RuntimeError):
    """Falta algo para analizar. **Se lanza**: el mensaje vuelve a la cola, no se inventa."""


def _conectar():
    """Conexión a la base. Import perezoso: los tests del núcleo no tocan Postgres."""
    import psycopg  # noqa: PLC0415

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise AnalisisImposible("falta DATABASE_URL en el entorno del Lambda")
    return psycopg.connect(dsn)


def _clip_y_goteo(conn, clip_id: str) -> dict:
    """Todo lo que hace falta del clip, en UNA consulta. Sin fila, no hay análisis."""
    fila = conn.execute(
        """
        SELECT c.incident_id, c.tenant_id, c.camera_id, c.s3_key, c.started_at,
               i.opened_at, cam.profile
          FROM cctv_clips c
          JOIN incidents i ON i.incident_id = c.incident_id
          LEFT JOIN cameras cam ON cam.camera_id = c.camera_id
         WHERE c.clip_id = %s
        """,
        (clip_id,),
    ).fetchone()
    if fila is None:
        raise AnalisisImposible(f"no hay clip {clip_id} en la base")
    campos = (
        "incident_id",
        "tenant_id",
        "camera_id",
        "s3_key",
        "started_at",
        "opened_at",
        "perfil",
    )
    return dict(zip(campos, fila, strict=True))


def _escribir(conn, datos: dict, analisis) -> None:
    """Curva y métricas, idempotentes. `ON CONFLICT` porque SQS entrega at-least-once.

    Se escribe la curva ENTERA y no solo las métricas: es de donde sale la gráfica del
    reporte, y cuatro números sin la serie que los respalda no son auditables.
    """
    with conn.transaction():
        for punto in analisis.curva:
            conn.execute(
                """
                INSERT INTO cctv_occupancy
                       (incident_id, camera_id, ts, provenance, tenant_id, n_people)
                VALUES (%s, %s, %s, 'final', %s, %s)
                ON CONFLICT (incident_id, camera_id, ts, provenance) DO UPDATE
                   SET n_people = EXCLUDED.n_people
                """,
                (datos["incident_id"], datos["camera_id"], punto.ts, datos["tenant_id"], punto.n),
            )
        e = analisis.evacuacion
        conn.execute(
            """
            INSERT INTO cctv_evacuation_metrics
                   (incident_id, provenance, tenant_id, t50_s, t90_s, peak_n, peak_at,
                    reentry_start_at, dictamen_lag_s, reentry_lag_s, checkin_count)
            VALUES (%s, 'final', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (incident_id, provenance) DO UPDATE SET
                   t50_s = EXCLUDED.t50_s, t90_s = EXCLUDED.t90_s,
                   peak_n = EXCLUDED.peak_n, peak_at = EXCLUDED.peak_at,
                   reentry_start_at = EXCLUDED.reentry_start_at,
                   dictamen_lag_s = EXCLUDED.dictamen_lag_s,
                   reentry_lag_s = EXCLUDED.reentry_lag_s,
                   checkin_count = EXCLUDED.checkin_count,
                   computed_at = now()
            """,
            (
                datos["incident_id"],
                datos["tenant_id"],
                e.get("t50_s"),
                e.get("t90_s"),
                e.get("peak_n"),
                e.get("peak_at"),
                e.get("reentry_start_at"),
                e.get("dictamen_lag_s"),
                e.get("reentry_lag_s"),
                e.get("checkin_count"),
            ),
        )


def analizar_clip(clip_id: str, *, conectar=_conectar) -> dict:
    """Un clip, de punta a punta. Devuelve un resumen para el log."""
    with conectar() as conn:
        datos = _clip_y_goteo(conn, clip_id)
        t0 = datos["opened_at"]
        bucket = os.environ.get("TAKAB_CCTV_BUCKET")
        if not bucket:
            raise AnalisisImposible("falta TAKAB_CCTV_BUCKET en el entorno del Lambda")

        # El clip cubre la salida; el goteo, el reingreso — que ocurre horas después. Las
        # dos series se fusionan en `analizar`, y con una sola los tiempos salen mal: con
        # solo el goteo, `t90` se mide desde el primer JPEG y no desde la señal.
        fotogramas = fotogramas_del_clip(
            f"s3://{bucket}/{datos['s3_key']}",
            t0=t0,
            clip_pre_s=(t0 - datos["started_at"]).total_seconds(),
            fps=FPS,
            ffmpeg=FFMPEG,
            endpoint_url=os.environ.get("TAKAB_API_S3_ENDPOINT_URL"),
        )
        with tempfile.TemporaryDirectory(prefix="takab-goteo-") as tmp:
            fotogramas += _bajar_goteo(conn, datos, bucket, Path(tmp))

        detector = cargar_onnx(MODELO, ffmpeg=FFMPEG)
        analisis = analizar(
            fotogramas,
            detector,
            t0=t0,
            ancho=int(os.environ.get("TAKAB_CCTV_ANCHO", "640")),
            alto=int(os.environ.get("TAKAB_CCTV_ALTO", "480")),
            montaje=Montaje(os.environ.get("TAKAB_CCTV_MONTAJE", Montaje.PICADO.value)),
        )
        _escribir(conn, datos, analisis)
    return {
        "clip_id": clip_id,
        "muestras": analisis.muestras,
        "pico": analisis.evacuacion.get("peak_n"),
    }


def _bajar_goteo(conn, datos: dict, bucket: str, carpeta: Path) -> list[tuple[datetime, bytes]]:
    """Las capturas del goteo del mismo incidente. **Su ausencia NO es un error.**

    El goteo puede no existir todavía —llega durante horas— y el análisis del clip sigue
    siendo válido sin él: lo que falta es el reingreso, y `calcular` ya sabe declararlo como
    `SIN DATO` en vez de inventarlo.
    """
    import boto3  # noqa: PLC0415

    filas = conn.execute(
        "SELECT s3_key FROM cctv_stills WHERE incident_id = %s ORDER BY captured_at",
        (datos["incident_id"],),
    ).fetchall()
    if not filas:
        log.info("cctv: el incidente %s no tiene goteo todavía", datos["incident_id"])
        return []
    s3 = boto3.client("s3", endpoint_url=os.environ.get("TAKAB_API_S3_ENDPOINT_URL"))
    for (key,) in filas:
        s3.download_file(bucket, key, str(carpeta / Path(key).name))
    return fotogramas_del_goteo(carpeta)


def handler(event, _context=None):  # noqa: ANN001
    """Entrada del Lambda. Un registro SQS por clip.

    **No captura excepciones a propósito.** Un fallo tiene que devolver el mensaje a la
    cola y acabar en la DLQ, que es donde se ve. Tragárselo dejaría el incidente con
    `ANÁLISIS PENDIENTE` para siempre y sin nadie a quien preguntarle por qué.
    """
    resultados = []
    for record in event.get("Records", []):
        cuerpo = json.loads(record["body"])
        clip_id = cuerpo["clip_id"]
        log.info("cctv: analizando clip %s", clip_id)
        resultados.append(analizar_clip(clip_id))
    log.info("cctv: %d clip(s) analizados", len(resultados))
    return {"analizados": resultados}
