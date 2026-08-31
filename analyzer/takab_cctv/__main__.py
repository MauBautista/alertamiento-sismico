"""`takab-cctv-analyze` — corre el motor sobre un clip y escupe la analítica (T-3.12).

Existe para poder ejercer el pipeline ENTERO en una máquina de desarrollo, contra MinIO y
con un backend falso, antes de que exista el Lambda (`T-3.12.b`, ventana AWS) y antes de que
exista la cámara (`T-3.12.d`, `GATE-HW`). Sin él, lo único ejecutable serían tests unitarios
y el primer contacto con un vídeo real sería en producción.

    python -m takab_cctv --clip clip.mp4 --detector falso --t0 2026-08-29T12:00:00Z
    python -m takab_cctv --clip s3://takab-dev-evidence/evidence/... --endpoint-url http://localhost:9000
    python -m takab_cctv --stills ./pendientes --t0 2026-08-29T12:00:00Z

DOS ENTRADAS QUE SE SUMAN, NO QUE SE ELIGEN
───────────────────────────────────────────
`--clip` procesa vídeo; `--stills` procesa un directorio de JPEG con el nombre que pone el
gabinete (`still-{AAAAMMDDTHHMMSSZ}-{event_id}.jpg`). **Se pueden dar las dos a la vez, y
en un incidente real hay que darlas**, porque la evacuación y el reingreso viven en sitios
distintos:

* el **clip** cubre `T−60 s … T+600 s` — ahí está la salida, o sea `t50` y `t90`;
* el **goteo** empieza donde el clip acaba y dura horas — ahí está el reingreso.

Con solo el goteo, `t90` sale medido desde el primer JPEG y no desde la señal: un número
que parece una evacuación de doce minutos cuando fue de uno. Con solo el clip, el reingreso
no se fecha nunca. Las series se **fusionan por instante** antes de calcular.

(Esto lo enseñó el E2E del simulador, no la revisión: cada camino por separado daba cifras
que parecían correctas.)

Y un efecto secundario útil: `--stills` no necesita ffmpeg, así que el motor se puede
ejercer en una máquina que no lo tenga.

FFMPEG, OTRA VEZ LGPL
─────────────────────
Extraer fotogramas decodifica, así que hace falta ffmpeg — y aquí rige la misma condición
que en el gabinete (`D-24`): build **LGPL**, invocado como **subproceso**, nunca enlazado.
La comprobación está duplicada respecto a `takab_edge.cctv.ffmpeg` y es deliberado: son dos
paquetes que **no pueden importarse entre sí** —uno vive en el Pi y el otro en un contenedor
de la nube— y crear un paquete compartido para una función sería peor que estas veinte
líneas. Lo que NO puede pasar es que solo una de las dos compruebe.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess  # noqa: S404 — ffmpeg por subproceso: es el requisito de licencia
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from takab_cctv.capturas import fotogramas_del_goteo
from takab_cctv.detector import DetectorBackend, DetectorFalso, Montaje, cargar_onnx
from takab_cctv.metricas import Sacudida
from takab_cctv.pipeline import analizar, fotogramas_del_clip

_RE_CONFIG = re.compile(r"^\s*configuration:(.*)$", re.MULTILINE)


class FfmpegNoApto(RuntimeError):
    """Gemelo de `takab_edge.cctv.ffmpeg.FfmpegNoApto`. Ver la nota de la cabecera."""


def verificar_ffmpeg(ruta: str) -> None:
    """Rechaza un ffmpeg que no sea LGPL. **«Desconocida» tampoco pasa.**"""
    try:
        proc = subprocess.run(  # noqa: S603 — ruta de configuración, argumento fijo
            [ruta, "-version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FfmpegNoApto(f"no se pudo interrogar {ruta!r}: {exc}") from exc
    m = _RE_CONFIG.search(proc.stdout + proc.stderr)
    if m is None:
        raise FfmpegNoApto(f"{ruta!r} no declara su línea `configuration:`")
    for bandera in ("--enable-gpl", "--enable-nonfree"):
        if re.search(rf"(?<![\w-]){re.escape(bandera)}(?![\w-])", m.group(1)):
            raise FfmpegNoApto(
                f"{ruta!r} trae {bandera} y D-24 exige un build LGPL. "
                "Usa ffmpeg-master-latest-linux64-lgpl de github.com/BtbN/FFmpeg-Builds"
            )


def _detector(spec: str, ffmpeg: str) -> DetectorBackend:
    """`falso` u `onnx:<ruta>`. El ONNX necesita ffmpeg: es quien decodifica el JPEG.

    Los pesos se dan **por ruta** y nunca se descargan: `ci/licencias.py` vigila el árbol y
    el job `analyzer` corre sin un solo peso. Bajar un modelo desde el código sería meter una
    dependencia de red —y una licencia sin auditar— en el camino del dictamen.
    """
    if spec == "falso":
        return DetectorFalso()
    if spec.startswith("onnx:"):
        return cargar_onnx(spec.removeprefix("onnx:"), ffmpeg=ffmpeg)
    raise SystemExit(f"detector desconocido: {spec!r} (usa `falso` u `onnx:<ruta>`)")


def _instante(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="takab-cctv-analyze", description=__doc__)
    # NO son mutuamente excluyentes: en un incidente real se dan las dos. Ver la cabecera.
    ap.add_argument("--clip", help="vídeo: ruta local o s3://bucket/key")
    ap.add_argument("--stills", help="directorio de JPEG del goteo del gabinete")
    ap.add_argument("--t0", required=True, type=_instante, help="la señal (incidents.opened_at)")
    ap.add_argument("--detector", default="falso", help="`falso` u `onnx:<ruta>`")
    ap.add_argument("--fps", type=float, default=0.5, help="fotogramas por segundo a muestrear")
    ap.add_argument(
        "--clip-pre",
        type=float,
        default=60.0,
        help="segundos de pre-roll del clip (debe coincidir con `cctv.clip_pre_s` del gabinete)",
    )
    ap.add_argument("--ffmpeg", default="ffmpeg", help="binario LGPL de ffmpeg")
    ap.add_argument("--endpoint-url", default=None, help="MinIO local, p.ej. http://localhost:9000")
    ap.add_argument("--ancho", type=int, default=1920)
    ap.add_argument("--alto", type=int, default=1080)
    ap.add_argument("--zona", type=str, default=None, help="polígono JSON normalizado [[x,y],…]")
    ap.add_argument(
        "--montaje",
        type=Montaje,
        choices=list(Montaje),
        default=Montaje.PICADO,
        help=(
            "cómo está montada la cámara: decide QUÉ punto de la caja se compara con la "
            "zona. `picado` (defecto) y `frontal` usan los pies; `cenital` usa el centro, "
            "porque a plomo no hay pies que ver. Es un dato del sitio: lo declara quien "
            "instala, no se adivina"
        ),
    )
    ap.add_argument("--dictamen", type=_instante, default=None)
    ap.add_argument("--checkins", type=int, default=None)
    ap.add_argument("--pga", type=float, default=None)
    ap.add_argument("--pgv", type=float, default=None)
    args = ap.parse_args(argv)

    if not args.clip and not args.stills:
        print("✗ hace falta --clip, --stills, o las dos", file=sys.stderr)
        return 2

    zona = json.loads(args.zona) if args.zona else None
    detector = _detector(args.detector, args.ffmpeg)
    fotogramas: list[tuple[datetime, bytes]] = []

    if args.stills:
        fotogramas += fotogramas_del_goteo(Path(args.stills))
    if args.clip:
        # Solo el camino de vídeo necesita ffmpeg, y por tanto solo él lo exige.
        try:
            verificar_ffmpeg(args.ffmpeg)
        except FfmpegNoApto as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 1
        fotogramas += fotogramas_del_clip(
            args.clip,
            t0=args.t0,
            clip_pre_s=args.clip_pre,
            fps=args.fps,
            ffmpeg=args.ffmpeg,
            endpoint_url=args.endpoint_url,
        )

    # El núcleo es COMPARTIDO con el Lambda (`pipeline.analizar`): el fechado del clip y la
    # fusión de las dos series viven ahí, no aquí, porque dos copias de esa aritmética
    # divergen sin que nadie vea un error — solo un dictamen que dice otra cosa.
    a = analizar(
        fotogramas,
        detector,
        t0=args.t0,
        ancho=args.ancho,
        alto=args.alto,
        zona=zona,
        montaje=args.montaje,
        t_dictamen=args.dictamen,
        checkins=args.checkins,
        sacudida=Sacudida(args.pga, args.pgv),
    )
    salida = {k: v for k, v in asdict(a).items() if k != "curva"}
    print(json.dumps(salida, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
