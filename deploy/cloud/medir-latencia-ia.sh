#!/bin/bash
# deploy/cloud/medir-latencia-ia.sh — [T-7.26] Cuánto tarda de verdad la capa narrativa.
#
# Existe porque `openrouter_timeout_s` vale 8.0 s y ese número NO SE INVENTA: el
# criterio 2 de T-7.26 pide medirlo contra el proveedor real, desde la instancia real,
# con el modelo que el despliegue tiene puesto. Hasta que esta medición exista no se
# puede decidir si el tope sube o si la generación tiene que salir de la petición HTTP
# y servirse con sondeo.
#
# ---------------------------------------------------------------------------
# LA TRAMPA QUE ESTE SCRIPT EXISTE PARA NO PISAR
# ---------------------------------------------------------------------------
# **No se puede medir a través del guardia que se está validando.** Con el tope en 8 s,
# toda llamada más lenta que 8 s no devuelve una latencia: devuelve una degradación
# («el proveedor no respondió») y `Narrative.latency_ms` se queda en `None`. O sea que
# medir con la configuración puesta borraría exactamente la cola que se quiere ver, y
# la conclusión sería «nunca pasa de 8 s» — cierto por construcción y falso en el
# mundo. Por eso la medición corre con un tope ALTO y propio (`--tope-medicion`,
# 90 s por defecto), que vive sólo dentro del proceso de medición: no se escribe nada
# en `/etc/takab/cloud.env` y el contenedor que sirve sigue con su 8.0.
#
# ---------------------------------------------------------------------------
# QUÉ MIDE, Y POR QUÉ SON TRES NÚMEROS Y NO UNO
# ---------------------------------------------------------------------------
#  1. **El catálogo** (`GET /models`). `build_narrative` pregunta SIEMPRE si el modelo
#     admite imágenes, también en un incidente sin una sola fotografía —es una lectura
#     deliberada de `D-32`, ver el comentario en `narrative/__init__.py`. Se recuerda
#     por PROCESO (`_VISION_SABIDA`), así que la primera exportación después de cada
#     despliegue la paga entera. Y la paga con el MISMO `openrouter_timeout_s`: son dos
#     viajes bajo un solo tope, que es la razón de que el número de arriba no baste.
#  2. **La generación sin fotografías** — el dictamen de un incidente sin reporte de
#     daños, que es el caso corriente.
#  3. **La generación con seis fotografías al tope** — el peor caso que `T-7.27` hizo
#     posible: `MAX_FOTOS_IA` (6) × `MAX_BYTES_SALIDA` (150 KiB) = 900 KiB que se van
#     en base64, o sea ~1.2 MB de cuerpo. Medir sólo el caso de texto y fijar el tope
#     con él dejaría la redacción asistida cayéndose justo en los incidentes con daño,
#     que son los únicos en los que alguien va a leer la prosa.
#
# Lo que una exportación en frío paga es (1) + (2 ó 3), y el tope los acota por
# separado. El veredicto del final compara contra eso, no contra la suma.
#
# ---------------------------------------------------------------------------
# QUÉ NO HACE
# ---------------------------------------------------------------------------
# No escribe en la base, no sube nada a S3, no genera un PDF, no toca la configuración
# de la instancia y no reinicia ningún servicio. Corre `docker exec` contra el
# contenedor que ya está arriba. **No imprime la clave** —se resuelve con el rol de la
# instancia y nunca sale del proceso— **ni la prosa** que devuelve el modelo: de la
# respuesta salen los tiempos, los tamaños, el conteo de tokens y el sha256, que es lo
# que hace la cifra auditable sin publicar el texto.
#
# Sí GASTA: son llamadas reales al proveedor y se cobran. Con los valores por defecto
# son 10 generaciones (5 sin fotos + 5 con seis fotos) más 10 lecturas de catálogo.
#
# Los hechos del incidente son SINTÉTICOS y están poblados a la forma de uno real
# (3 estaciones, 12 hitos de cronología, 2 reportes de daño). Se imprime el peso en
# bytes y `prompt_tokens` de cada llamada justo para que la cifra se pueda contrastar
# el día que haya una exportación real: si aquel cuerpo pesa el doble que éste, esta
# medición no gobierna y hay que repetirla.
set -u

uso() {
  cat <<'USO'
uso: bash deploy/cloud/medir-latencia-ia.sh [opciones]

  --rondas N            llamadas por brazo (por defecto 5)
  --tope-medicion S     tope en segundos SOLO para medir (por defecto 90). Ver la
                        cabecera: medir con el tope de producción borra la cola.
  --modelo SLUG         probar ESE modelo en vez del desplegado (no cambia nada en
                        la instancia: vive sólo dentro del proceso de medición)
  --solo-texto          sólo el brazo sin fotografías
  --solo-fotos          sólo el brazo con seis fotografías al tope
  --crudo               imprime también las líneas MEDIDA tal cual

entorno: AWS_PROFILE (takab-dev) · AWS_REGION (us-east-2)
         TF_DEV (infra/terraform/envs/dev)
requiere: aws jq terraform · y la sesión SSO viva (dura 1 hora)
USO
}

RONDAS=5
TOPE_MEDICION=90
#: Slug a PROBAR, distinto del desplegado. Vacío = el que la nube tiene puesto.
#: Existe para contestar «¿cuál elegimos?» y no sólo «¿cuánto tarda el que hay?»:
#: la medición es además la prueba de CALIDAD, porque un modelo que no sabe seguir
#: el formato de secciones cae en el guardrail y el informe sale con prosa
#: determinista — eso aquí aparece como `degradada`, no como una latencia buena.
MODELO=""
ARMAS="texto,fotos"
CRUDO=0
while [ $# -gt 0 ]; do
  case "$1" in
  --rondas) RONDAS="${2:-}"; shift 2 ;;
  --tope-medicion) TOPE_MEDICION="${2:-}"; shift 2 ;;
  --modelo) MODELO="${2:-}"; shift 2 ;;
  --solo-texto) ARMAS="texto"; shift ;;
  --solo-fotos) ARMAS="fotos"; shift ;;
  --crudo) CRUDO=1; shift ;;
  -h | --help) uso; exit 0 ;;
  *) echo "medir-latencia-ia: opción desconocida '$1'" >&2; uso >&2; exit 2 ;;
  esac
done

AWS_PROFILE="${AWS_PROFILE:-takab-dev}"
AWS_REGION="${AWS_REGION:-us-east-2}"
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
TF_DEV="${TF_DEV:-$RAIZ/infra/terraform/envs/dev}"
aws_cli() { aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"; }

for b in aws jq terraform python3; do
  command -v "$b" >/dev/null 2>&1 || { echo "medir-latencia-ia: falta '$b'" >&2; exit 2; }
done

ID="$(terraform -chdir="$TF_DEV" output -raw db_instance_id 2>/dev/null || true)"
if [ -z "$ID" ]; then
  echo "medir-latencia-ia: no hay salida 'db_instance_id' en $TF_DEV." >&2
  echo "  ¿aplicaste el terraform? ¿la sesión SSO está viva? (dura 1 hora)" >&2
  exit 2
fi

echo "→ instancia $ID · rondas=$RONDAS · brazos=$ARMAS · tope de MEDICIÓN=${TOPE_MEDICION}s"
echo "  (el tope de producción NO se toca; ver la cabecera de este fichero)"

# El programa remoto. Los parámetros viajan por entorno porque el heredoc va entre
# comillas simples a propósito: nada de lo de dentro se expande en esta máquina.
# ⚠️ El prelúdio y el cuerpo van dentro de UNA SOLA sustitución, y no es cosmética:
# `$( )` SE COME LOS SALTOS DE LÍNEA FINALES. Con dos sustituciones concatenadas, el
# `\n` que cierra `export RONDAS TOPE ARMAS` desaparecía y la línea quedaba pegada al
# `docker exec` siguiente — el remoto moría con «export: '-i': not a valid identifier»
# y la medición no llegaba a empezar. Medido contra la instancia el 2026-09-22.
CMD="$(
  printf 'RONDAS=%s\nTOPE=%s\nARMAS=%s\nMODELO=%s\nexport RONDAS TOPE ARMAS MODELO\n' \
    "$RONDAS" "$TOPE_MEDICION" "$ARMAS" "$MODELO"
  cat <<'REMOTO'
docker exec -i -e RONDAS -e TOPE -e ARMAS -e MODELO takab-cloud-api-1 python - <<'PY'
import asyncio, hashlib, io, json, os, sys, time

from takab_api.settings import Settings
from takab_api.narrative import select_provider
from takab_api.narrative import openrouter as orm
from takab_api.narrative.base import (
    DanoRedactado, EstacionRedactada, HitoRedactado, ImagenAdjunta,
    NarrativeFacts, NarrativeRequest,
)
from takab_api.documentos import fotos as fotos_mod

RONDAS = int(os.environ.get("RONDAS", "5"))
TOPE = float(os.environ.get("TOPE", "90"))
ARMAS = [a for a in os.environ.get("ARMAS", "texto,fotos").split(",") if a]

# Igual que `routers/reports.py`: se instancia, se lee del entorno del contenedor.
base = Settings()
# ⚠️ EL OVERRIDE. Sin esto la medición se corta justo donde empieza la pregunta.
_cambios = {"openrouter_timeout_s": TOPE}
if os.environ.get("MODELO"):
    _cambios["openrouter_model"] = os.environ["MODELO"]
s = base.model_copy(update=_cambios)

print("CFG\tmodelo=%s\ttope_produccion=%.1f\ttope_medicion=%.1f" % (
    s.openrouter_model, base.openrouter_timeout_s, TOPE), flush=True)

elegido = select_provider(s)
if elegido.degraded_reason or elegido.provider.name != orm.NAME:
    print("ABORTA\t%s" % (elegido.degraded_reason or "la nube no sale a la red (IA apagada o sin modelo)"), flush=True)
    sys.exit(3)
prov = elegido.provider


def foto(n):
    """Una derivada del tamaño que produce `documentos/fotos.preparar`, al tope."""
    from PIL import Image
    lado = fotos_mod.LADO_MAX
    # Ruido: comprime mal, que es lo que hace pesar a una fotografía de daño real.
    im = Image.frombytes("RGB", (lado, lado * 3 // 4), os.urandom(lado * (lado * 3 // 4) * 3))
    for q in (85, 70, 55, 45, 35, 28, 22, 18):
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=q)
        if buf.tell() <= fotos_mod.MAX_BYTES_SALIDA:
            break
    b = buf.getvalue()
    h = hashlib.sha256(b).hexdigest()
    return ImagenAdjunta(jpeg=b, sha256=h, sha256_enviado=h,
                         ancho=lado, alto=lado * 3 // 4, reporte=1 + (n % 2))


def hechos(adjuntas, disponibles):
    estaciones = tuple(
        EstacionRedactada(
            orden=i, propia=(i == 1),
            dist_km=None if i == 1 else round(4.2 * i, 1),
            t_teorico_s=None if i == 1 else round(0.8 * i, 2),
            t_medido_s=None if i == 1 else round(0.9 * i, 2),
            peak_pga_g=round(0.031 + 0.004 * i, 4),
            umbral_pga_g=0.07, umbral_origen="referencia", tier="watch")
        for i in range(1, 4))
    cronologia = tuple(
        HitoRedactado(t_desde_apertura_s=float(3 * i), kind=k, rotulo=r, actor=a)
        for i, (k, r, a) in enumerate((
            ("incident_opened", "Incidente abierto", "system"),
            ("sasmex_received", "Alerta SASMEX recibida", "edge"),
            ("siren_on", "Sirena activada", "edge"),
            ("command_ack", "Acuse del gabinete", "edge"),
            ("state_changed", "Cambio de estado", "system"),
            ("damage_reported", "Reporte de daños", "user"),
            ("damage_reported", "Reporte de daños", "user"),
            ("photo_uploaded", "Fotografía adjuntada", "user"),
            ("triage_claimed", "Tomado en triage", "user"),
            ("verdict_signed", "Dictamen firmado", "user"),
            ("siren_off", "Sirena desactivada", "edge"),
            ("incident_closed", "Incidente cerrado", "user"),
        ), start=1))
    danos = (
        DanoRedactado(orden=1, rol="brigadista", personas_en_riesgo=False,
                      categorias=(("grietas_muro", "moderado"), ("vidrio_roto", "leve")),
                      fotos_adjuntas=min(adjuntas, 3), fotos_no_adjuntas=0),
        DanoRedactado(orden=2, rol="security_guard", personas_en_riesgo=True,
                      categorias=(("caida_plafon", "moderado"),),
                      fotos_adjuntas=max(adjuntas - 3, 0), fotos_no_adjuntas=0),
    )
    return NarrativeFacts(
        folio="TKB-DEV-0001-20260921-0007", opened_at="2026-09-21T18:04:11+00:00",
        severity="alta", trigger="sasmex", opened_trigger="sasmex", state="closed",
        event_source="SASMEX", verdict_label="REVISION ESTRUCTURAL",
        verdict_status="review", verdict_signed=True,
        verdict_actions=("inspeccion_visual", "restringir_acceso"),
        rule_set_version="v14", basis={"pga_g": 0.043, "umbral_g": 0.035},
        reason_recorded=True, site_criticality="alta", felt_band="moderado",
        felt_label="Percibido por todos", calibrated=True, peak_pga_g=0.043,
        peak_pgv_cms=2.71, lead_time="18 s", station_count=3, catalog_line="SSN M5.4",
        stations=estaciones, reproduccion=False, channel_count=4,
        clipped_channels=(), action_counts=(("siren_on", 1), ("command_ack", 2)),
        damage_counts=(("grietas_muro", 1), ("vidrio_roto", 1), ("caida_plafon", 1)),
        timeline=cronologia, damage_reports=danos,
        photos_attached=adjuntas, photos_available=disponibles,
        dictamen_count=1, has_epicenter=True, has_raw_waveform=True,
        has_archived_miniseed=True, absences=(),
    )


async def main():
    for arma in ARMAS:
        imgs = tuple(foto(i) for i in range(orm_max())) if arma == "fotos" else ()
        f = hechos(len(imgs), len(imgs))
        for r in range(1, RONDAS + 1):
            # Cada ronda paga el catálogo: es lo que paga la PRIMERA exportación de
            # cada proceso, y ése es el caso que el tope tiene que cubrir.
            orm.olvidar_vision()
            t0 = time.monotonic()
            vis = await prov.admite_imagenes()
            ms_cat = int((time.monotonic() - t0) * 1000)
            req = NarrativeRequest(facts=f, model=s.openrouter_model, images=imgs)
            pesa = len(json.dumps(orm.cuerpo_de(req), ensure_ascii=False).encode("utf-8"))
            t1 = time.monotonic()
            n = await prov.generate(req)
            ms_gen = int((time.monotonic() - t1) * 1000)
            print("MEDIDA\t%s\t%d\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (
                arma, r, ms_cat, ms_gen, pesa,
                n.prompt_tokens if n.prompt_tokens is not None else "-",
                n.completion_tokens if n.completion_tokens is not None else "-",
                n.cost_usd if n.cost_usd is not None else "-",
                n.provider, (n.degraded_reason or "-"),
                "vision_si" if vis.admite else ("vision_NO:" + (vis.motivo or "?")),
                (n.output_sha256 or "-")[:12]), flush=True)

def orm_max():
    from takab_api.narrative.redact import MAX_FOTOS_IA
    return MAX_FOTOS_IA

asyncio.run(main())
PY
REMOTO
)"

# Antes de mandarlo: ¿PARSEA? Un guion roto viaja igual, cuesta un viaje a SSM y vuelve
# con un error del intérprete remoto en vez de una medición. `bash -n` lo caza aquí, gratis,
# y es exactamente lo que faltaba el día que el `export` se pegó a la línea siguiente.
if ! bash -n <<<"$CMD" 2>/dev/null; then
  echo "medir-latencia-ia: el guion remoto NO parsea; no se manda nada. Detalle:" >&2
  bash -n <<<"$CMD" >&2 || true
  exit 2
fi

P="$(mktemp)"
jq -n --arg c "$CMD" '{commands: [$c]}' >"$P"
CID="$(aws_cli ssm send-command --instance-ids "$ID" --document-name AWS-RunShellScript \
  --comment "takab: medicion de latencia de la capa narrativa (T-7.26)" \
  --parameters "file://$P" --query Command.CommandId --output text 2>/dev/null || true)"
rm -f "$P"
[ -n "$CID" ] || { echo "medir-latencia-ia: 'aws ssm send-command' falló contra $ID" >&2; exit 1; }
echo "→ comando SSM $CID; midiendo (puede tardar varios minutos)…"

# El plazo se DERIVA de lo que se pidió, no es una constante: con --rondas 20 y fotos,
# un plazo fijo cortaría la propia medición y diría que la nube no contestó.
LIMITE=$(( 60 + RONDAS * $(echo "$ARMAS" | tr ',' '\n' | grep -c .) * (TOPE_MEDICION + 10) ))
ESPERADO=0
while [ "$ESPERADO" -lt "$LIMITE" ]; do
  ESTADO="$(aws_cli ssm get-command-invocation --command-id "$CID" --instance-id "$ID" \
    --query Status --output text 2>/dev/null || true)"
  case "$ESTADO" in Success | Failed | Cancelled | TimedOut) break ;; esac
  sleep 10; ESPERADO=$((ESPERADO + 10))
done

SALIDA="$(aws_cli ssm get-command-invocation --command-id "$CID" --instance-id "$ID" \
  --query StandardOutputContent --output text 2>/dev/null || true)"
ERROR="$(aws_cli ssm get-command-invocation --command-id "$CID" --instance-id "$ID" \
  --query StandardErrorContent --output text 2>/dev/null || true)"

if [ "${ESTADO:-}" != "Success" ]; then
  echo "medir-latencia-ia: el comando terminó en '${ESTADO:-sin estado}'" >&2
  [ -n "$SALIDA" ] && printf '%s\n' "$SALIDA" >&2
  [ -n "$ERROR" ] && printf '%s\n' "$ERROR" >&2
  exit 1
fi

printf '%s\n' "$SALIDA" | grep '^CFG' | tr '\t' ' ' | sed 's/^CFG /→ /'
if printf '%s\n' "$SALIDA" | grep -q '^ABORTA'; then
  echo
  printf '%s\n' "$SALIDA" | grep '^ABORTA' | sed 's/^ABORTA\t/✗ no se pudo medir: /'
  echo "  La medición necesita la capa narrativa ENCENDIDA y la clave legible por el"
  echo "  rol de la instancia. Eso es T-7.26 criterio 1: secreto + terraform + despliegue."
  exit 1
fi
[ "$CRUDO" -eq 1 ] && printf '%s\n' "$SALIDA" | grep '^MEDIDA'

printf '%s\n' "$SALIDA" | grep '^MEDIDA' | TOPE_PROD="$(
  printf '%s\n' "$SALIDA" | grep '^CFG' | sed 's/.*tope_produccion=\([0-9.]*\).*/\1/')" python3 - <<'AGREGA'
import os, statistics, sys

tope = float(os.environ.get("TOPE_PROD") or 8.0)
por_arma = {}
degradadas = []
for linea in sys.stdin:
    c = linea.rstrip("\n").split("\t")
    if len(c) < 12:
        continue
    _, arma, ronda, cat, gen, pesa, pin, pout, coste, prov, razon, _resto = c[:12]
    d = por_arma.setdefault(arma, {"cat": [], "gen": [], "pesa": [], "pin": [], "pout": [], "coste": []})
    d["cat"].append(int(cat)); d["pesa"].append(int(pesa))
    # ⚠️ UNA LLAMADA DEGRADADA NO ES UNA LATENCIA. Si el proveedor no contestó, lo
    # que se sabe de ella es que tardó MÁS que el tope de medición, no CUÁNTO: es una
    # observación censurada. Metiéndola en la muestra, el máximo se convertía en el
    # propio tope de medición y el veredicto llegaba a recomendar «sube el tope por
    # encima de 90012 ms» — un número que no mide nada y que además es el techo que
    # pusimos nosotros. Se cuentan aparte y se declaran.
    if razon != "-":
        degradadas.append((arma, ronda, razon, int(gen)))
    else:
        d["gen"].append(int(gen))
        for k, v in (("pin", pin), ("pout", pout)):
            if v != "-":
                d[k].append(int(v))
        if coste != "-":
            d["coste"].append(float(coste))

if not por_arma:
    print("✗ no hubo ni una medida: revisa la salida cruda con --crudo")
    sys.exit(1)

def pct(v, p):
    v = sorted(v)
    if len(v) == 1:
        return v[0]
    i = min(len(v) - 1, max(0, round((p / 100) * (len(v) - 1))))
    return v[i]

ROTULO = {"texto": "sin fotografías", "fotos": "con 6 fotografías al tope"}
print()
print("  brazo                        n   catálogo ms        generación ms      cuerpo")
print("                                   p50   p95   max    p50   p95   max    KiB")
peor = 0
for arma, d in por_arma.items():
    n = len(d["gen"])
    peor = max(peor, max(d["cat"]))
    if n:
        peor = max(peor, max(d["gen"]))
        cols = "%5d %5d %5d" % (pct(d["gen"], 50), pct(d["gen"], 95), max(d["gen"]))
    else:
        cols = "    -     -     -"
    print("  %-26s %2d  %5d %5d %5d  %s  %6.0f" % (
        ROTULO.get(arma, arma), n,
        pct(d["cat"], 50), pct(d["cat"], 95), max(d["cat"]),
        cols, statistics.mean(d["pesa"]) / 1024))
print()
for arma, d in por_arma.items():
    if d["pin"]:
        print("  %-26s tokens entrada p50=%d · salida p50=%d%s" % (
            ROTULO.get(arma, arma), pct(d["pin"], 50), pct(d["pout"], 50),
            (" · coste medio $%.5f" % statistics.mean(d["coste"])) if d["coste"] else ""))

if degradadas:
    print()
    print("  ⚠️ %d llamada(s) DEGRADADA(S), fuera de la muestra de latencias." % len(degradadas))
    print("     La razón es la misma que el papel habría impreso:")
    for arma, ronda, razon, ms in degradadas:
        print("       · %s ronda %s → %s (a los %d ms)" % (ROTULO.get(arma, arma), ronda, razon, ms))

print()
print("  ── VEREDICTO ─────────────────────────────────────────────────────────────")
print("  tope en producción: %.1f s (%d ms). Peor viaje MEDIDO: %d ms." % (tope, int(tope * 1000), peor))
margen = tope * 1000 / peor if peor else float("inf")
if degradadas:
    # Muestra CENSURADA: hubo viajes que no volvieron, y de ésos no se sabe cuánto
    # habrían tardado. Con una cota superior desconocida no se puede proponer un tope,
    # y proponerlo igual sería inventarse el número que esta ficha vino a medir.
    print("  → NO SE PUEDE FIJAR UN TOPE con esta muestra: %d de %d viajes NO VOLVIERON." % (
        len(degradadas), len(degradadas) + sum(len(d["gen"]) for d in por_arma.values())))
    print("    De una llamada que no contestó se sabe que tardó MÁS que el tope de")
    print("    medición, no cuánto. Lo que hay que hacer, en este orden:")
    print("      1) mirar la razón de arriba: si dice «no aceptó la clave» o «respondió")
    print("         con error», esto no es latencia y el tope no es el problema;")
    print("      2) si de verdad son plantones, repetir con --tope-medicion más alto")
    print("         hasta que ninguna se corte, y sólo entonces leer el veredicto;")
    print("      3) si ni así vuelven, la respuesta es (b): sacar la generación de la")
    print("         petición HTTP y servirla con sondeo.")
elif peor <= tope * 1000 * 0.5:
    print("  → EL TOPE AGUANTA con holgura (x%.1f). No hay que tocarlo." % margen)
elif peor <= tope * 1000:
    print("  → El tope cubre lo medido pero con poco margen (x%.1f)." % margen)
    print("    Con %d muestras la cola larga no está caracterizada: o se sube el tope," % sum(len(d["gen"]) for d in por_arma.values()))
    print("    o se acepta que unos pocos dictámenes salgan con prosa determinista.")
else:
    print("  → EL TOPE SE QUEDA CORTO: lo medido lo rebasa.")
    print("    Dos salidas, y la ficha pide elegir una:")
    print("      a) subir `openrouter_timeout_s` por encima de %d ms — pero eso deja" % peor)
    print("         una petición HTTP de exportación colgada ese tiempo;")
    print("      b) sacar la generación de la petición y servirla con sondeo.")
print("  Recuerda: el catálogo y la generación son DOS viajes bajo el MISMO tope.")
print("  Una exportación en frío paga los dos; el tope acota cada uno por separado.")
AGREGA
