#!/usr/bin/env bash
# [T-7.07] El guion de la demostración al cliente, comprobable por máquina.
#
# NO es `demo/run.py` (aquél es el arnés de la Fase 1: levanta MinIO y una base
# local y ejercita edge→nube sin tocar hardware). Esto mira el sistema REAL —el
# gabinete de Puebla, la nube desplegada y el Pixel— y contesta dos preguntas
# que, contestadas tarde, cuestan la demostración entera:
#
#   --preflight  ¿se puede tocar el radio ya, o hay algo puesto que hará que el
#                pulso no produzca ni incidente ni aviso, sin error a la vista?
#   --check      tras el pulso: ¿pasó lo que el guion promete, y en el plazo?
#   --reporte    acto 4: ¿el PDF existe y lleva de verdad una imagen dentro?
#
# **Por qué existe.** Cada una de las cosas que comprueba ya se ha caído sola al
# menos una vez, y todas fallan EN SILENCIO: el modo prueba del WR-1 armado
# convierte el pulso en un ensayo que no publica a la nube; el modo demostración
# (`D-27`) suprime los comandos firmados y el simulacro se registra igual, con
# 201 y cero comandos; un enclavado vivo de la prueba anterior hace que la sirena
# no vuelva a sonar; y un teléfono sin token registrado no recibe nada aunque
# todo lo demás esté perfecto. Ninguna de las cuatro se ve mirando la consola.
#
# **Solo LEE.** No mueve un relé, no abre un incidente, no publica nada. Lo único
# que escribe es su propia salida.
#
# Costuras (para las pruebas, y para correrlo desde otra red):
#
#   TAKAB_DEMO_PANEL_URL   panel del gabinete      (def. http://raspberry-cerebro.local:8080)
#   TAKAB_DEMO_DSN         base de datos YA accesible; si se da, NO se abre túnel
#   TAKAB_DEMO_SITE        sitio de la demostración (def. el piloto de Puebla)
#   TAKAB_DEMO_TENANT      tenant                  (def. el de desarrollo)
#   TAKAB_DEMO_DESTINOS    regex de destinatarios PROPIOS permitidos
#   TAKAB_DEMO_ADB         binario de adb          (def. adb)
#   TAKAB_DEMO_ESPERA_S    plazo de `--check`      (def. 45)
#   TAKAB_DEMO_DESDE       desde cuándo cuenta un incidente (def. ahora)
#   TAKAB_DEMO_INCIDENTE   incidente para `--reporte` (def. el último del sitio)
#   TAKAB_DEMO_BUCKET      bucket de evidencia (def. el de este entorno en AWS)
#
# La red por defecto es `192.168.1.0/24` a propósito: es la red donde el equipo
# se va a INSTALAR. Desde la de desarrollo hay que decirle dónde mirar con
# `TAKAB_DEMO_PANEL_URL`, y la dirección del Pi cambia por DHCP.
set -uo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
# El gabinete coge dirección por DHCP y se ha mudado tres veces en tres días
# (.3.91 → .3.140 → .1.86), rompiendo cada vez lo que apuntaba a la de antes.
# Se le pregunta POR NOMBRE: el Pi se anuncia por mDNS y eso sobrevive al cambio.
PANEL="${TAKAB_DEMO_PANEL_URL:-http://raspberry-cerebro.local:8080}"
SITIO="${TAKAB_DEMO_SITE:-d1000000-0000-0000-0000-000000000000}"
TENANT="${TAKAB_DEMO_TENANT:-d0000000-0000-0000-0000-000000000001}"
#: Qué cuenta como destinatario PROPIO. La cascada de una demostración no puede
#: escribirle a un tercero: el correo dice «ALERTA SÍSMICA» y no lleva la palabra
#: simulacro en el asunto.
DESTINOS_OK="${TAKAB_DEMO_DESTINOS:-@takabailert\.com|mauriciobaujim(\+[a-z]+)?@gmail\.com}"
ADB="${TAKAB_DEMO_ADB:-adb}"
ESPERA_S="${TAKAB_DEMO_ESPERA_S:-45}"
SQL_FASE="$RAIZ/infra/scripts/sql/staging-incident/phase.sql"

VERDES=0
ROJOS=0
AVISOS=0

verde() {
  printf '  \033[32m✓\033[0m %s\n' "$1"
  VERDES=$((VERDES + 1))
}
rojo() {
  printf '  \033[31m✗\033[0m %s\n' "$1"
  ROJOS=$((ROJOS + 1))
}
aviso() {
  printf '  \033[33m•\033[0m %s\n' "$1"
  AVISOS=$((AVISOS + 1))
}

# --------------------------------------------------------------- panel del Pi

ESTADO=""

leer_panel() {
  if ! ESTADO="$(curl -fsS --max-time 8 "$PANEL/api/status" 2>/dev/null)"; then
    rojo "el panel no contesta en $PANEL/api/status — ¿equipo fuera de la red del gabinete?"
    return 1
  fi
  verde "panel del gabinete vivo en $PANEL"
}

#: Un campo del estado, por ruta con puntos. Devuelve '' si no está.
#:
#: ⚠️ NADA de `// empty` aquí: el `//` de jq trata `false` como AUSENTE, así que
#: `.test_mode.active // empty` devuelve la cadena vacía justo en el caso bueno
#: —el modo prueba desarmado— y el guion diría «el panel no declara test_mode»
#: con el panel declarándolo perfectamente. Ya mordió una vez en
#: `deploy/cloud/conformidad.sh`; aquí lo cazaron las pruebas antes de mordernos.
campo() { jq -r "$1 | if . == null then empty else . end" <<<"$ESTADO" 2>/dev/null; }

# --------------------------------------------------------------------- la base

PSQL=()

abrir_base() {
  if [ -n "${TAKAB_DEMO_DSN:-}" ]; then
    PSQL=(psql "$TAKAB_DEMO_DSN" -v ON_ERROR_STOP=1 -tA)
    return 0
  fi
  # shellcheck source=/dev/null
  . "$RAIZ/infra/scripts/lib/tunel.sh"
  abrir_tunel "${TAKAB_DEMO_PUERTO:-5438}" || return 1
  local sec
  sec="$(credenciales_db)" || return 1
  export PGPASSWORD
  PGPASSWORD="$(jq -r .password <<<"$sec")"
  PSQL=(psql -h 127.0.0.1 -p "$TUNEL_PUERTO" -U "$(jq -r .username <<<"$sec")" \
    -d "$(jq -r .dbname <<<"$sec")" -v ON_ERROR_STOP=1 -tA)
}

consulta() { "${PSQL[@]}" -c "$1" 2>/dev/null; }

# ------------------------------------------------------------------ preflight

c_modo_prueba() {
  case "$(campo .test_mode.active)" in
  false) verde "modo prueba del WR-1 DESARMADO" ;;
  true) rojo "modo prueba del WR-1 ARMADO ($(campo .test_mode.remaining_s)s): el pulso NO publica a la nube y no habrá incidente ni aviso" ;;
  *) rojo "el panel no declara test_mode: no se puede saber si el pulso será real" ;;
  esac
}

c_enclavado() {
  local latch sasmex
  latch="$(campo .alert_latched)"
  sasmex="$(campo .sasmex_active)"
  if [ "$latch" = "false" ] && [ "$sasmex" = "false" ]; then
    verde "sin enclavado vivo: el pulso se verá como algo nuevo"
  else
    rojo "enclavado vivo (alert_latched=$latch sasmex_active=$sasmex): límpialo con POST $PANEL/api/reset o el acto 3 no se distingue del anterior"
  fi
}

c_reles() {
  local activos motivo
  activos="$(jq -r '[.relays[]? | select(.activated == true) | .channel] | join(", ")' <<<"$ESTADO")"
  motivo="$(campo .relays_status.reason)"
  if [ -n "$activos" ]; then
    rojo "relés ya accionados ($activos): el acto 2 no puede enseñar «nada se movió»"
  else
    verde "relés en reposo"
  fi
  [ "$motivo" = "ok" ] && verde "cadena de relés sana (reason=ok)" ||
    rojo "cadena de relés en '$motivo': revísala antes de prometer una sirena"
}

c_simulacro() {
  [ "$(campo .drill.active)" = "false" ] &&
    verde "sin simulacro en curso" ||
    rojo "hay un simulacro activo: la consola pintará la franja de simulacro encima de la demostración"
}

c_nube_desde_el_gabinete() {
  local online admin
  online="$(campo .cloud.online)"
  admin="$(campo .cloud.admin_state)"
  if [ "$online" = "true" ] && [ "$admin" = "active" ]; then
    verde "el gabinete ve la nube (rtt $(campo .cloud.mqtt_rtt_ms | cut -c1-5) ms, cola $(campo .cloud.queued))"
  else
    rojo "el gabinete no está publicando (online=$online admin_state=$admin): habrá sirena pero no incidente en la consola"
  fi
}

c_voceo() {
  # No decide por nadie: DECLARA qué va a sonar. Lo único que es un fallo es que
  # no suene nada, porque entonces el acto 3 no se oye.
  local audio sirena
  audio="$(campo .audio.enabled)"
  sirena="$(jq -r '[.relays[]? | select(.channel == "siren")] | length' <<<"$ESTADO")"
  if [ "$audio" = "true" ]; then
    aviso "voceo por el jack ENCENDIDO (audio.enabled=true): va a sonar por el altavoz del gabinete"
  fi
  if [ "${sirena:-0}" -gt 0 ]; then
    verde "relé de sirena instalado: el acto 3 suena por la sirena"
  elif [ "$audio" = "true" ]; then
    verde "sin relé de sirena, pero el voceo por jack está encendido"
  else
    rojo "no hay relé de sirena NI voceo por jack: el acto 3 no se oiría"
  fi
}

c_modo_demostracion() {
  local n
  n="$(consulta "SELECT count(*) FROM demo_mode WHERE tenant_id='$TENANT' AND (expires_at IS NULL OR expires_at > now())")"
  if [ "$n" = "0" ]; then
    verde "modo demostración APAGADO (D-27 no suprime nada)"
  else
    rojo "modo demostración ENCENDIDO: suprime los comandos firmados y los avisos, y todo responde 201 como si nada"
  fi
}

#: El `rule_set` que RIGE al sitio se elige igual que en `notify/orchestrator.py`:
#: el del sitio si existe y, si no, el del cliente. Mirar solo `scope_id = sitio`
#: daría «sin cascada» en un tenant que la tiene puesta arriba, y el preflight
#: diría que no le escribe a nadie justo cuando le escribe a todos.
CONFIG_DEL_SITIO="SELECT config::text FROM rule_sets WHERE is_active
   AND ((scope_type='site' AND scope_id='\$SITIO') OR (scope_type='tenant' AND scope_id='\$TENANT'))
 ORDER BY (scope_type='site') DESC, version DESC LIMIT 1"

c_destinatarios() {
  local destinos ajenos
  destinos="$(consulta "$(eval "echo \"$CONFIG_DEL_SITIO\"")")"
  if [ -z "$destinos" ]; then
    aviso "el sitio no tiene cascada configurada: el acto 3 no mandará correo a nadie"
    return
  fi
  ajenos="$(grep -oE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+|\+[0-9]{8,}' <<<"$destinos" |
    grep -vE "$DESTINOS_OK" | sort -u | tr '\n' ' ')"
  if [ -z "$ajenos" ]; then
    verde "todos los destinatarios de la cascada son propios"
  else
    rojo "la cascada le escribiría a terceros: $ajenos — el correo dice ALERTA SÍSMICA y no lleva «simulacro» en el asunto"
  fi
}

c_telefono() {
  local estado paquete tokens
  estado="$("$ADB" get-state 2>/dev/null | tr -d '\r')"
  if [ "$estado" != "device" ]; then
    rojo "el Pixel no está por USB (adb get-state: ${estado:-nada}): sin él no hay acto 3 que enseñar"
    return
  fi
  paquete="$("$ADB" shell pm list packages com.takab.ailert 2>/dev/null | tr -d '\r')"
  [ -n "$paquete" ] &&
    verde "la app está instalada en el teléfono" ||
    rojo "la app NO está instalada en el teléfono"
  tokens="$(consulta "SELECT count(*) FROM push_tokens WHERE site_id='$SITIO' AND revoked_at IS NULL")"
  if [ "${tokens:-0}" -gt 0 ]; then
    verde "$tokens dispositivo(s) enrolado(s) en el sitio y con token vivo"
  else
    rojo "ningún token de push para este sitio: el teléfono no recibirá el aviso (abre la app y entra como ocupante)"
  fi
}

c_sitio_limpio() {
  local n
  n="$(consulta "SELECT count(*) FROM incidents WHERE site_id='$SITIO' AND state <> 'closed'")"
  if [ "$n" = "0" ]; then
    verde "sin incidentes abiertos en el sitio: el acto 3 abrirá uno nuevo"
  else
    aviso "$n incidente(s) abierto(s) en el sitio: ciérralos o el acto 4 trabajará sobre el viejo"
  fi
}

preflight() {
  echo "PREFLIGHT · gabinete $PANEL · sitio $SITIO"
  echo
  leer_panel || return 1
  c_modo_prueba
  c_enclavado
  c_reles
  c_simulacro
  c_nube_desde_el_gabinete
  c_voceo
  abrir_base || {
    rojo "sin base de datos no se pueden comprobar modo demostración, destinatarios ni teléfonos"
    return 1
  }
  c_modo_demostracion
  c_destinatarios
  c_telefono
  c_sitio_limpio
}

# ---------------------------------------------------------------------- check

#: Momento desde el que cuenta un incidente como «de este pulso». Sin esto, un
#: incidente de ayer daría el check por bueno sin que el radio hubiera hecho nada.
#: Se puede fijar (`TAKAB_DEMO_DESDE`) para mirar hacia atrás cuando el check se
#: corre después, con el acto ya terminado.
DESDE="${TAKAB_DEMO_DESDE:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

check() {
  echo "CHECK · esperando el pulso del WR-1 hasta ${ESPERA_S}s · sitio $SITIO"
  echo "  (cuentan solo los incidentes abiertos después de $DESDE)"
  echo
  abrir_base || return 1

  local iid="" t0 ahora
  t0="$(date +%s)"
  while :; do
    iid="$(consulta "SELECT incident_id FROM incidents WHERE site_id='$SITIO' AND trigger='sasmex' AND opened_at >= '$DESDE' ORDER BY opened_at DESC LIMIT 1")"
    [ -n "$iid" ] && break
    ahora="$(date +%s)"
    [ $((ahora - t0)) -ge "$ESPERA_S" ] && break
    sleep 2
  done

  if [ -z "$iid" ]; then
    rojo "no llegó ningún incidente 'sasmex' en ${ESPERA_S}s: el pulso no viajó (¿modo prueba armado? ¿gabinete sin nube?)"
    return 1
  fi
  verde "incidente sasmex $iid abierto ($(( $(date +%s) - t0 ))s tras empezar a mirar)"

  local fase
  fase="$("${PSQL[@]}" -v site="$SITIO" -v iid="$iid" -f "$SQL_FASE" 2>/dev/null | head -1)"
  case "$fase" in
  phase=alert_active*) verde "la app deriva ${fase%% *} — la pantalla de crisis es lo que toca" ;;
  "") rojo "no se pudo derivar la fase de la app" ;;
  *) rojo "la app deriva '${fase%% *}' y no 'phase=alert_active': el teléfono no abrirá la crisis" ;;
  esac

  leer_panel >/dev/null 2>&1 || true
  if [ -n "$ESTADO" ]; then
    local reles reflejo
    reles="$(jq -r '[.relays[]? | select(.activated == true) | .channel] | join(", ")' <<<"$ESTADO")"
    reflejo="$(campo .latencies.reflex_s)"
    [ -n "$reles" ] &&
      verde "el gabinete acusa relés accionados: $reles" ||
      rojo "ningún relé accionado en el panel: la sirena no llegó a moverse"
    [ -n "$reflejo" ] &&
      verde "acta del reflejo con latencia ${reflejo}s (presupuesto $(campo .latencies.reflex_budget_s)s)" ||
      aviso "el panel no publica latencia de reflejo todavía"
  else
    aviso "sin panel no se puede afirmar el movimiento de los relés"
  fi

  local push
  push="$(consulta "SELECT status FROM notification_jobs WHERE incident_id='$iid' AND channel='push' ORDER BY created_at DESC LIMIT 1")"
  case "$push" in
  sent) verde "el aviso al teléfono salió de verdad (push 'sent')" ;;
  "") aviso "todavía no hay job de push para el incidente" ;;
  simulated) rojo "el push quedó 'simulated': la nube corre sin proveedor real y ningún teléfono sonó" ;;
  *) rojo "el push quedó '$push'" ;;
  esac
  echo "$iid" >"${TAKAB_DEMO_ULTIMO:-/tmp/takab-demo-incidente}"
}

# -------------------------------------------------------------------- reporte

reporte() {
  echo "REPORTE · acto 4 · sitio $SITIO"
  echo
  abrir_base || return 1
  local iid pdf fotos
  iid="${TAKAB_DEMO_INCIDENTE:-$(consulta "SELECT incident_id FROM incidents WHERE site_id='$SITIO' ORDER BY opened_at DESC LIMIT 1")}"
  [ -n "$iid" ] || {
    rojo "no hay ningún incidente en el sitio"
    return 1
  }
  echo "  incidente $iid"
  pdf="$(consulta "SELECT s3_key FROM evidence_objects WHERE incident_id='$iid' AND kind='report_pdf' ORDER BY created_at DESC LIMIT 1")"
  fotos="$(consulta "SELECT count(*) FROM evidence_objects WHERE incident_id='$iid' AND kind='photo'")"
  if [ -z "$pdf" ]; then
    rojo "no hay PDF de reporte para el incidente: genéralo desde la consola"
    return 1
  fi
  verde "PDF del reporte: $pdf"
  # Las fotos del brigadista se DECLARAN, no se exigen: la autoridad es lo que
  # lleva el PDF dentro, que es lo que recibe el cliente. Medido el 2026-09-12:
  # un reporte técnico sin una sola foto de brigada llevaba 8 imágenes embebidas
  # (las gráficas), así que exigir fotos ponía en rojo un reporte entregable.
  [ "${fotos:-0}" -gt 0 ] &&
    verde "$fotos foto(s) de brigada colgando del incidente" ||
    aviso "sin fotos de brigada en este incidente (el reporte llevará solo sus gráficas)"

  # La prueba de verdad es que el PDF LLEVE la imagen dentro, no que exista una
  # foto suelta en la base. Se baja y se cuentan sus imágenes embebidas.
  if ! command -v pdfimages >/dev/null 2>&1; then
    aviso "sin 'pdfimages' (poppler-utils) no se puede mirar DENTRO del PDF; se afirma solo por la base"
    return
  fi
  local bucket tmp n
  # El bucket NO es una columna de `evidence_objects` —eso costó un «no se pudo
  # bajar el PDF» que parecía un problema de permisos—: es un ajuste de la API
  # (`settings.evidence_bucket`). Se deriva de AWS, con override por entorno.
  bucket="${TAKAB_DEMO_BUCKET:-$(aws s3 ls 2>/dev/null | awk '/takab-dev-evidence/ { print $3; exit }')}"
  tmp="$(mktemp -t takab-reporte-XXXX.pdf)"
  if [ -n "$bucket" ] && aws s3 cp "s3://$bucket/$pdf" "$tmp" >/dev/null 2>&1; then
    # Imágenes DISTINTAS, no apariciones: el membrete se repite en cada página y
    # arrastra su máscara, así que un reporte de 4 páginas sin una sola gráfica
    # ni foto contaba «8 imágenes embebidas» y se leía como que el documento va
    # lleno. Medido el 2026-09-12 con el reporte del acto 4: las ocho eran el
    # mismo objeto. Se cuentan objetos únicos de tipo `image` (la `smask` es la
    # transparencia del anterior, no una imagen más).
    local paginas
    n="$(pdfimages -list "$tmp" 2>/dev/null | awk 'NR>2 && $3=="image" { print $9 }' | sort -u | grep -c .)"
    paginas="$(pdfinfo "$tmp" 2>/dev/null | awk '/^Pages:/ { print $2 }')"
    if [ "${n:-0}" -gt 1 ]; then
      verde "el PDF lleva $n imágenes DISTINTAS en ${paginas:-?} páginas"
    elif [ "${n:-0}" -eq 1 ]; then
      aviso "el PDF lleva UNA sola imagen distinta en ${paginas:-?} páginas: es el membrete, no evidencia ni gráficas con datos"
    else
      rojo "el PDF no lleva ninguna imagen dentro"
    fi
  else
    aviso "no se pudo bajar el PDF de S3 para mirarlo por dentro"
  fi
  rm -f "$tmp"
}

# ----------------------------------------------------------------------- main

#: El cierre dice qué hacer, y eso depende de en qué acto estamos: «no toques el
#: radio» delante del cliente, con el radio ya pulsado, manda a arreglar lo que no
#: es y hace perder el minuto que importa.
resumen() {
  echo
  echo "RESUMEN: $VERDES ✓ · $AVISOS • · $ROJOS ✗"
  [ "$ROJOS" -gt 0 ] || return 0
  case "$ACCION" in
  --preflight) echo "NO toques el radio todavía: cada ✗ hace que el guion falle SIN dar error a la vista." ;;
  --check) echo "El pulso no produjo lo que el guion promete. Mira el panel y el registro del worker notify." ;;
  --reporte) echo "El reporte no está entregable todavía: genéralo desde la consola y vuelve a correr esto." ;;
  esac
  return 1
}

ACCION="${1:---preflight}"
case "$ACCION" in
--preflight) preflight ;;
--check) check ;;
--reporte) reporte ;;
-h | --help)
  sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
  ;;
*)
  echo "uso: $(basename "$0") [--preflight|--check|--reporte]" >&2
  exit 2
  ;;
esac
resumen
