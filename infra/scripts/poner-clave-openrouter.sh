#!/usr/bin/env bash
# infra/scripts/poner-clave-openrouter.sh — pone (o ROTA) la clave de OpenRouter en
# Secrets Manager sin que el valor toque nunca la línea de comandos.
#
# ---------------------------------------------------------------------------
# POR QUÉ EXISTE, Y NO UN COMANDO SUELTO
# ---------------------------------------------------------------------------
# El comando suelto se intentó dos veces el 2026-09-22 y falló las dos, de formas
# distintas y ninguna evidente:
#
#   1. `create-secret` con el secreto YA CREADO devuelve `ResourceExistsException` y
#      **no escribe nada**. La clave se dio por puesta durante un día entero mientras
#      cada dictamen salía con prosa determinista y un 401 en el registro.
#   2. La versión con `read -rs … | jq --arg …` murió con «jq: --arg takes two
#      parameters» porque `read` no tenía terminal, la variable quedó vacía y el
#      encadenado siguió adelante: `aws` recibió una cadena de longitud 0.
#
# Las dos comparten la misma causa: **una tubería larga en la que un eslabón falla en
# silencio y los de después siguen trabajando con nada**. Aquí cada paso comprueba lo
# suyo y se detiene.
#
# ---------------------------------------------------------------------------
# LO QUE NO HACE, A PROPÓSITO
# ---------------------------------------------------------------------------
# **No imprime la clave, ni recortada.** Una clave en una terminal es una clave en el
# desplazamiento de la terminal, y de ahí a una captura de pantalla (regla de oro 6).
# Tampoco la deja en el historial: no viaja como argumento de nada.
#
# **No valida contra OpenRouter.** Comprobar que la clave FUNCIONA es de
# `make cloud-medir-latencia-ia`, que además mide. Aquí sólo se descarta lo imposible.
set -euo pipefail

PERFIL="${AWS_PROFILE:-takab-dev}"
REGION="${AWS_REGION:-us-east-2}"
SECRETO="${TAKAB_OPENROUTER_SECRET_ID:-takab/dev/openrouter}"

for b in aws python3; do
  command -v "$b" >/dev/null 2>&1 || { echo "falta '$b'" >&2; exit 2; }
done

echo "→ secreto $SECRETO · perfil $PERFIL · región $REGION"

# ── 1 · la sesión, ANTES de pedir nada ──────────────────────────────────────
# Pedirle la clave a alguien y después descubrir que el SSO caducó es hacerle repetir
# el paso más incómodo. Se comprueba primero.
if ! aws sts get-caller-identity --profile "$PERFIL" --region "$REGION" >/dev/null 2>&1; then
  echo "✗ la sesión de AWS no está viva. Renuévala y vuelve:" >&2
  echo "    aws sso logout && aws sso login --profile $PERFIL" >&2
  echo "  (el 'logout' antes NO es adorno: con la caché rancia el login parece ir bien" >&2
  echo "   y después falla con InvalidGrantException.)" >&2
  exit 1
fi

# ── 2 · la clave, por el terminal y nunca por argumento ─────────────────────
# Se lee de /dev/tty EXPLÍCITAMENTE. Con `read` a secas, en un contexto sin terminal
# —un `!` de una sesión asistida, una tubería, un cron— la lectura no falla: devuelve
# vacío, y el guion de antes siguió adelante con esa nada hasta que AWS se quejó del
# largo 0. Aquí, sin terminal, se dice y se para.
if [ ! -t 0 ] && [ ! -e /dev/tty ]; then
  echo "✗ no hay terminal para pedir la clave sin mostrarla." >&2
  echo "  Alternativa: guárdala en un fichero (sólo la clave, sin comillas) y usa" >&2
  echo "    TAKAB_OPENROUTER_KEY_FILE=/ruta/al/fichero bash $0" >&2
  exit 2
fi

CLAVE=""
if [ -n "${TAKAB_OPENROUTER_KEY_FILE:-}" ]; then
  [ -r "$TAKAB_OPENROUTER_KEY_FILE" ] || { echo "✗ no puedo leer $TAKAB_OPENROUTER_KEY_FILE" >&2; exit 2; }
  CLAVE="$(tr -d ' \t\r\n' <"$TAKAB_OPENROUTER_KEY_FILE")"
  echo "→ leída del fichero (no se imprime)"
else
  printf 'Pega la clave de OpenRouter (no se verá al escribir) y pulsa ENTER: '
  IFS= read -rs CLAVE </dev/tty || true
  printf '\n'
fi

# ── 3 · la forma, con la MISMA regla que el código ──────────────────────────
# Es la regla de `narrative/openrouter.py::_tiene_forma_de_clave`. Duplicarla aquí es
# deliberado y acotado: este guion corre desde una máquina que no tiene el paquete de
# la API instalado, y el valor que compara no sale de ningún sitio compartido. Lo que
# NO se puede hacer es aflojarla en un lado y no en el otro, así que si cambia allí,
# cambia aquí — y lo nota la primera rotación que rechace una clave buena.
if [ -z "$CLAVE" ]; then
  echo "✗ no se leyó nada. NO se ha tocado el secreto." >&2
  exit 1
fi
case "$CLAVE" in
sk-or-*) ;;
*)
  echo "✗ eso no empieza por 'sk-or-'. ¿Pegaste una clave de otro proveedor?" >&2
  echo "  NO se ha tocado el secreto." >&2
  exit 1
  ;;
esac
case "$CLAVE" in
*...* | *…*)
  echo "✗ eso lleva puntos suspensivos: es el MARCADOR de la documentación, no una clave." >&2
  echo "  Es exactamente lo que había dentro del secreto hasta hoy. NO se ha tocado." >&2
  exit 1
  ;;
esac
if [ "${#CLAVE}" -lt 24 ]; then
  echo "✗ son ${#CLAVE} caracteres y una clave de OpenRouter pasa de 70." >&2
  echo "  ¿Se cortó al pegar? NO se ha tocado el secreto." >&2
  exit 1
fi
echo "✓ tiene forma de clave (${#CLAVE} caracteres; el valor no se imprime)"

# ── 4 · el JSON, construido por python3 y no por comillas ───────────────────
# Con `printf '{"api_key":"%s"}'` una clave con un carácter raro rompería el JSON en
# silencio y el secreto quedaría con basura. `json.dumps` escapa lo que haya.
CUERPO="$(CLAVE="$CLAVE" python3 -c 'import json,os; print(json.dumps({"api_key": os.environ["CLAVE"]}))')"

# ── 5 · escribir, y COMPROBAR que la versión cambió ─────────────────────────
ANTES="$(aws secretsmanager describe-secret --profile "$PERFIL" --region "$REGION" \
  --secret-id "$SECRETO" --query LastChangedDate --output text 2>/dev/null || echo "")"

if ! aws secretsmanager put-secret-value --profile "$PERFIL" --region "$REGION" \
  --secret-id "$SECRETO" --secret-string "$CUERPO" >/dev/null; then
  echo "✗ AWS rechazó la escritura. El secreto NO cambió." >&2
  exit 1
fi
unset CLAVE CUERPO

DESPUES="$(aws secretsmanager describe-secret --profile "$PERFIL" --region "$REGION" \
  --secret-id "$SECRETO" --query LastChangedDate --output text)"
if [ "$ANTES" = "$DESPUES" ]; then
  echo "✗ la fecha de último cambio no se movió ($DESPUES): la escritura no surtió efecto." >&2
  exit 1
fi
echo "✓ secreto actualizado · último cambio $DESPUES (antes: ${ANTES:-desconocido})"

cat <<'FIN'

Lo que falta, y es lo único que prueba que la clave SIRVE:

    make cloud-medir-latencia-ia

  · latencias y tokens          → funciona, y esa cifra cierra T-7.26
  · «ClaveSinForma»             → dentro del secreto no hay una clave
  · «no aceptó la clave (401)»  → la clave es real y el proveedor la rechaza:
                                  revocada, o la cuenta sin saldo
FIN
