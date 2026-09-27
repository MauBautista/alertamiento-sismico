#!/usr/bin/env bash
# [T-7.07] El guion de la demostración al cliente, comprobable por máquina.
#
# NO es `demo/run.py` (aquél es el arnés de la Fase 1: levanta MinIO y una base
# local y ejercita edge→nube sin tocar hardware). Esto mira el sistema REAL —el
# gabinete de Puebla, la nube desplegada y el Pixel— y contesta las preguntas
# que, contestadas tarde, cuestan la demostración entera:
#
#   --preflight  ¿se puede tocar el radio ya, o hay algo puesto que hará que el
#                pulso no produzca ni incidente ni aviso, sin error a la vista?
#   --check      tras el pulso: ¿pasó lo que el guion promete, y en el plazo?
#   --reporte    acto 4: ¿el PDF existe y lleva de verdad una imagen dentro?
#   --full       [T-7.28] el ensayo general: los cuatro actos en orden,
#                cronometrados, cada uno con su comprobación, y al final la
#                tabla del Registro lista para pegar. Sigue sin accionar nada:
#                lo físico lo hace la persona y el guion mide y pregunta.
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
#   TAKAB_DEMO_SIN_PAUSA   1 = --full no espera a nadie (prueba del guion, NO
#                          un ensayo: la tabla que salga lo dice en su pie)
#   TAKAB_DEMO_ENSAYO_ID   nombre de la corrida (def. la hora UTC)
#
# La red por defecto es `192.168.1.0/24` a propósito: es la red donde el equipo
# se va a INSTALAR. Desde la de desarrollo hay que decirle dónde mirar con
# `TAKAB_DEMO_PANEL_URL`, y la dirección del Pi cambia por DHCP.
set -uo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
# El gabinete coge dirección por DHCP y se ha mudado CUATRO veces en dos semanas
# (.3.91 → .3.140 → .1.86 → .1.142), rompiendo cada vez lo que apuntaba a la de
# antes — la última, el 2026-09-21, al volver a la red de instalación.
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
    rojo "enclavado vivo (alert_latched=$latch sasmex_active=$sasmex): límpialo con el botón CERRAR ALERTA del panel (PIN) — o curl -X POST -H 'X-Takab-Pin: <PIN>' $PANEL/api/reset — o el acto 3 no se distingue del anterior"
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
    # [T-8.13] Ensayo 2 (2026-09-24): el WR-1 se pulsó 81 s después de que el golpe
    # del acto 2 volviera a `normal`. El gabinete cierra el episodio tras 90 s de
    # calma (T-7.49), le puso al pulso la identidad del golpe, y la nube ESCALÓ el
    # incidente del acto 2 a SASMEX en vez de abrir otro. Esa es una causa distinta
    # de «el pulso no viajó», y la única que se arregla esperando: se nombra.
    local sumado
    sumado="$(consulta "SELECT incident_id FROM incidents WHERE site_id='$SITIO' AND trigger='sasmex' AND opened_at < '$DESDE' AND opened_at >= '$DESDE'::timestamptz - interval '15 minutes' ORDER BY opened_at DESC LIMIT 1")"
    if [ -n "$sumado" ]; then
      rojo "el pulso NO abrió incidente propio: se SUMÓ al incidente ${sumado:0:8}, abierto antes por el acto anterior (mismo episodio del gabinete: menos de 90 s de calma entre el golpe y el WR-1). No es una avería: deja 2 min de calma y repite el acto 3"
    else
      rojo "no llegó ningún incidente 'sasmex' en ${ESPERA_S}s: el pulso no viajó (¿modo prueba armado? ¿gabinete sin nube?)"
    fi
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

# ------------------------------------------------------- ensayo general (--full)
#
# [T-7.28] El ensayo general: los cuatro actos EN ORDEN, cronometrados, y cada uno
# con la comprobación de máquina que ya existía suelta.
#
# ---------------------------------------------------------------------------
# QUÉ ES Y QUÉ NO ES
# ---------------------------------------------------------------------------
# Es un CRONÓMETRO y un DIRECTOR DE ESCENA. **No acciona nada** — el invariante de
# este fichero («solo lee») sigue intacto y es el que permite correrlo delante de
# un cliente sin miedo. Lo físico lo hace la persona: golpear la losa, pulsar el
# WR-1, sacar la foto, firmar el dictamen. El guion dice cuándo, espera, mide, y
# después pregunta a la máquina si pasó lo que el acto promete.
#
# ---------------------------------------------------------------------------
# DE QUÉ RELOJ SON ESTOS TIEMPOS — y por qué importa decirlo
# ---------------------------------------------------------------------------
# reloj: PROPIO — de la máquina donde corre este script. Son tiempos de ENSAYO
# (cuánto se tardó en representar cada acto), **no latencias del sistema**. La
# diferencia no es sutil: el Registro ya guarda latencias medidas por el sistema
# con su propio reloj —el acta del reflejo, 4,96 ms sobre un presupuesto de 100—,
# y presentar «acto 3: 2 min 14 s» junto a aquéllas, sin decir cuál es cuál,
# convertiría el tiempo que tardó una persona en pulsar un botón en una cifra de
# rendimiento del producto. Por eso la tabla que sale de aquí rotula su columna
# «duración del acto» y el pie declara el reloj.
#
# ---------------------------------------------------------------------------
# LO QUE NO PUEDE HACER, A PROPÓSITO
# ---------------------------------------------------------------------------
# **No puede inventarse un tiempo.** Un acto que se salta se registra `omitido`
# y SIN duración — nunca con cero. Un cero se lee como «tardó nada» y es la
# mentira más fácil de colar en una tabla de tiempos.
#
# Costura: `TAKAB_DEMO_SIN_PAUSA=1` no espera a nadie (es lo que deja probar el
# ensayo entero sin gabinete). Con ella los actos duran lo que tarda la máquina,
# y el pie de la tabla lo DICE, para que una corrida de prueba no se pueda pegar
# en el Registro como si hubiera habido una persona delante.

#: Una fila por acto: nombre TAB inicio TAB fin TAB veredicto TAB detalle.
#: Se guardan MARCAS y la duración se DERIVA al imprimir (T-7.60): un acumulador
#: de duraciones no deja comprobar después que el orden de los actos fue el que
#: dice la tabla.
MARCAS=()
ACTO_T0=0
ACTO_NOMBRE=""
ACTO_V0=0
ACTO_R0=0

#: Reloj del ensayo. Único sitio donde se lee la hora, para que no haya dos.
ahora_epoch() { date +%s; }

#: ¿Hay alguien al otro lado? Se comprueba UNA vez y se recuerda, porque de esto
#: depende si la tabla que salga significa algo.
#:
#: ⚠️ EL AGUJERO QUE CIERRA, medido el 2026-09-22. `read -r r </dev/tty` SIN terminal
#: no bloquea: falla, deja `r` vacío y `pausa` devuelve 0 — o sea que el guion recorría
#: los cuatro actos solo, dando cada uno por representado, y sacaba una tabla de tiempos
#: que no medían nada. Y salía SIN el aviso del pie, porque ese aviso cuelga de
#: `TAKAB_DEMO_SIN_PAUSA` y nadie la había puesto.
#:
#: Era el peor de los tres desenlaces posibles: no el que falla (se ve), ni el que avisa
#: (es honesto), sino **el que se parece a un ensayo de verdad**. Y lo primero que se hace
#: con esa tabla es pegarla en el § Registro, que es el documento donde se AFIRMA que el
#: ensayo ocurrió.
hay_terminal() {
  # Las llaves NO son adorno: `: </dev/tty 2>/dev/null` procesa las redirecciones de
  # izquierda a derecha, así que el fallo de abrir /dev/tty ya se ha escrito en stderr
  # cuando el `2>/dev/null` entra en vigor. Agrupando, el silenciado cubre al grupo.
  [ -e /dev/tty ] && { : </dev/tty; } 2>/dev/null
}

pausa() {
  if [ "${TAKAB_DEMO_SIN_PAUSA:-0}" = "1" ]; then
    printf '  \033[36m→\033[0m %s \033[2m(sin pausa)\033[0m\n' "$1"
    return 0
  fi
  printf '  \033[36m→\033[0m %s\n' "$1"
  printf '     cuando esté hecho, pulsa ENTER (o «s» + ENTER para SALTAR el acto): '
  local r
  IFS= read -r r </dev/tty || r=""
  case "$r" in s | S | saltar) return 1 ;; esac
  return 0
}

abre_acto() {
  ACTO_NOMBRE="$1"
  ACTO_T0="$(ahora_epoch)"
  ACTO_V0="$VERDES"
  ACTO_R0="$ROJOS"
  echo
  printf '\033[1m── %s ──\033[0m\n' "$1"
}

#: `$1` = veredicto forzado, o vacío para DERIVARLO de los rojos que cayeron
#: dentro del acto. Derivarlo es lo que impide que un acto se declare bueno
#: mientras su propia comprobación pinta un ✗ tres líneas más arriba.
cierra_acto() {
  local forzado="${1:-}" detalle="${2:-}" fin veredicto
  fin="$(ahora_epoch)"
  if [ -n "$forzado" ]; then
    veredicto="$forzado"
  elif [ "$ROJOS" -gt "$ACTO_R0" ]; then
    veredicto="rojo"
  else
    veredicto="ok"
  fi
  MARCAS+=("$ACTO_NOMBRE	$ACTO_T0	$fin	$veredicto	$detalle")
}

omite_acto() {
  MARCAS+=("$ACTO_NOMBRE	$ACTO_T0	-	omitido	$1")
  printf '  \033[33m•\033[0m acto OMITIDO: %s\n' "$1"
  AVISOS=$((AVISOS + 1))
}

#: mm:ss de una duración. Se le pasa la resta ya hecha por quien tiene las dos
#: marcas: aquí no se vuelve a leer el reloj.
mmss() {
  local s="$1"
  printf '%d:%02d' $((s / 60)) $((s % 60))
}

# --- acto 1 · el SOC en reposo -------------------------------------------------

c_acto1_reposo() {
  leer_panel || return 1
  local tier activos paquetes huecos
  tier="$(campo .last_tier)"
  activos="$(jq -r '[.relays[]? | select(.activated == true) | .channel] | join(", ")' <<<"$ESTADO")"
  paquetes="$(campo .seedlink.packets_seen)"
  huecos="$(campo .seedlink.gaps)"

  [ "$tier" = "normal" ] &&
    verde "nivel en reposo: normal" ||
    rojo "el gabinete NO está en reposo (last_tier=${tier:-?}): el acto 1 enseña un sistema tranquilo"
  [ -z "$activos" ] &&
    verde "relés en reposo" ||
    rojo "relés accionados ($activos): el acto 1 no puede abrir con la sirena puesta"
  c_nube_desde_el_gabinete
  if [ -n "$paquetes" ]; then
    if [ "${huecos:-0}" -eq 0 ] 2>/dev/null; then
      verde "SeedLink: $paquetes paquetes, 0 huecos"
    else
      aviso "SeedLink: $paquetes paquetes con $huecos huecos — dilo tú antes de que lo pregunten"
    fi
  else
    aviso "el panel no declara seedlink: no hay cifra de continuidad que enseñar"
  fi
  ACTO1_DETALLE="nivel $tier · relés en reposo · ${paquetes:-?} paquetes/${huecos:-?} huecos"
}

# --- acto 2 · movimiento aislado, SIN señal del WR-1 ---------------------------

#: El acto 2 promete DOS cosas y la segunda es la que vende: que el edificio se
#: movió, que el sistema lo vio **y que no accionó nada**. La segunda se mide
#: contra `actuation_records`, no contra el panel: el panel dice si un relé está
#: accionado AHORA, y un relé que se moviera y volviera pasaría por delante de él
#: sin dejar rastro. La bitácora es append-only y no se puede desdecir.
c_acto2_movimiento() {
  local desde="$1" iid n
  abrir_base || return 1
  iid="$(consulta "SELECT incident_id FROM incidents WHERE site_id='$SITIO' AND opened_trigger='local_threshold' AND opened_at >= to_timestamp($desde) ORDER BY opened_at DESC LIMIT 1")"
  if [ -z "$iid" ]; then
    rojo "el golpe no abrió incidente 'local_threshold' en la nube: o no llegó al umbral, o el gabinete no publica"
    ACTO2_DETALLE="sin incidente"
    return 1
  fi
  verde "incidente local_threshold $iid abierto por el movimiento"
  n="$(consulta "SELECT count(*) FROM actuation_records WHERE site_id='$SITIO' AND occurred_at >= to_timestamp($desde)")"
  if [ "${n:-0}" = "0" ]; then
    verde "NINGÚN relé se movió (bitácora de actuación vacía desde el inicio del acto)"
  else
    rojo "se registraron $n actuaciones: el acto 2 promete que una estación sola NO acciona (T-2.32)"
  fi
  ACTO2_DETALLE="incidente ${iid:0:8} · $n actuaciones"
}

# --- la tabla del Registro -----------------------------------------------------

registro_markdown() {
  local marcado n=0
  echo
  echo "════════════════════════════════════════════════════════════════════════"
  echo "REGISTRO · pega esto en takab-docs/runbooks/RUNBOOK-demo-cliente.md § Registro"
  echo "════════════════════════════════════════════════════════════════════════"
  echo
  echo "**Ensayo del $(date -u +%Y-%m-%dT%H:%M:%SZ) · corrida \`$ENSAYO_ID\`.**"
  echo
  echo "| Acto | Duración | Veredicto | Qué midió la máquina |"
  echo "|---|---|---|---|"
  for marcado in "${MARCAS[@]}"; do
    local nombre t0 t1 ver det dur
    IFS='	' read -r nombre t0 t1 ver det <<<"$marcado"
    if [ "$t1" = "-" ]; then
      dur="—"
    else
      dur="$(mmss $((t1 - t0)))"
    fi
    case "$ver" in
    ok) ver="✓" ;;
    rojo) ver="✗" ;;
    omitido) ver="omitido" ;;
    esac
    printf '| %s | %s | %s | %s |\n' "$nombre" "$dur" "$ver" "${det:-—}"
    n=$((n + 1))
  done
  echo
  echo "> **De qué reloj son estas duraciones.** De la máquina que corrió"
  echo "> \`guion.sh --full\`, y son tiempos de REPRESENTACIÓN: cuánto se tardó en"
  echo "> ejecutar cada acto delante de quien miraba. **No son latencias del"
  echo "> sistema** — ésas las mide el propio sistema y viven en las filas de arriba"
  echo "> de esta misma sección (el acta del reflejo, la entrega del aviso)."
  if [ "${TAKAB_DEMO_SIN_PAUSA:-0}" = "1" ]; then
    echo ">"
    echo "> ⚠️ **Corrida SIN PAUSAS (\`TAKAB_DEMO_SIN_PAUSA=1\`): no hubo una persona"
    echo "> representando los actos.** Las duraciones son lo que tardó la máquina en"
    echo "> preguntar, no un ensayo. NO la pegues en el Registro como si lo fuera."
  fi
  echo
  echo "Clasificación pendiente: **\`reproduccion\`** (ver el cierre de este guion)."
}

full() {
  # Se comprueba ANTES de empezar, no en el primer acto: abortar en el acto 3 deja al
  # gabinete a medias y con el cliente delante.
  if [ "${TAKAB_DEMO_SIN_PAUSA:-0}" != "1" ] && ! hay_terminal; then
    echo "guion.sh --full: no hay terminal, así que NO HAY NADIE a quien esperar." >&2
    echo >&2
    echo "  Un ensayo es una persona representando los actos: golpear la losa, pulsar" >&2
    echo "  el WR-1, sacar la foto en el Pixel, firmar en la consola. Sin terminal, las" >&2
    echo "  pausas no paran nada y saldría una tabla de tiempos que no miden nada —y que" >&2
    echo "  se parece a la de un ensayo de verdad, que es lo peligroso." >&2
    echo >&2
    echo "  · Para ENSAYAR: córrelo desde una TERMINAL DE VERDAD, con el gabinete" >&2
    echo "    delante. ⚠️ El «!» de una sesión asistida NO es un terminal: llega aquí" >&2
    echo "    igual que un cron. Abre una ventana de terminal y córrelo allí." >&2
    echo "  · Para PROBAR EL GUION sin ensayar: TAKAB_DEMO_SIN_PAUSA=1, y entonces la" >&2
    echo "    tabla lo dice en su pie para que nadie la pegue en el § Registro." >&2
    # `exit`, no `return`: el despachador llama a `resumen` después de `full`, y
    # `resumen` decide el código por el número de ✗. Con `return 2` esta negativa salía
    # con código 0 — un guion que se niega y dice «todo bien» es peor que uno que no se
    # niega, porque un arnés que lo invoque lo dará por ensayado.
    exit 2
  fi
  ENSAYO_ID="${TAKAB_DEMO_ENSAYO_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
  echo "ENSAYO GENERAL · corrida $ENSAYO_ID · sitio $SITIO"
  echo "  Este guion NO acciona nada. Lo físico lo haces tú; él mide y comprueba."
  [ "${TAKAB_DEMO_SIN_PAUSA:-0}" = "1" ] &&
    echo "  ⚠️ SIN PAUSAS: no espera a nadie. Esto NO es un ensayo, es una prueba del guion."

  # ── acto 0 ──────────────────────────────────────────────────────────────
  abre_acto "0 · Preflight"
  preflight
  if [ "$ROJOS" -gt "$ACTO_R0" ]; then
    cierra_acto rojo "$((ROJOS - ACTO_R0)) ✗ en el preflight"
    echo
    echo "ENSAYO ABORTADO en el preflight. NO toques el radio: cada ✗ hace que el"
    echo "guion falle SIN dar error a la vista, que es justo lo que no se puede"
    echo "permitir con un cliente delante."
    registro_markdown
    return 1
  fi
  cierra_acto ok "$((VERDES - ACTO_V0)) ✓"

  # ── acto 1 ──────────────────────────────────────────────────────────────
  ACTO1_DETALLE=""
  abre_acto "1 · El SOC operando normal"
  if pausa "enseña la consola y el panel del gabinete en reposo"; then
    c_acto1_reposo
    cierra_acto "" "$ACTO1_DETALLE"
  else
    omite_acto "lo saltó quien conducía"
  fi

  # ── acto 2 ──────────────────────────────────────────────────────────────
  ACTO2_DETALLE=""
  abre_acto "2 · Movimiento aislado, SIN señal del WR-1"
  local t_acto2
  t_acto2="$(ahora_epoch)"
  if pausa "golpea la losa junto al sensor hasta que el panel escale de nivel"; then
    c_acto2_movimiento "$t_acto2"
    cierra_acto "" "$ACTO2_DETALLE"
  else
    omite_acto "lo saltó quien conducía"
  fi

  # ── acto 3 ──────────────────────────────────────────────────────────────
  abre_acto "3 · El pulso del WR-1"
  # [T-8.13] Lo que costó el acto 3 del ensayo 2: con menos de 90 s de calma tras el
  # golpe, el gabinete junta el WR-1 al mismo episodio y no hay incidente SASMEX propio.
  echo "  ⚠️ antes de tocar el WR-1: 2 min de calma desde que el panel volvió a 'normal'"
  echo "     tras el golpe del acto 2. Con menos de 90 s el gabinete lo junta al mismo"
  echo "     episodio: no abre incidente SASMEX propio y el PDF lo cuenta como umbral local."
  DESDE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if pausa "pulsa el WR-1 AHORA (el check empieza a contar desde este instante)"; then
    check
    cierra_acto "" "$(( VERDES - ACTO_V0 )) ✓ · $(( ROJOS - ACTO_R0 )) ✗"
  else
    omite_acto "lo saltó quien conducía"
  fi

  # ── acto 4 ──────────────────────────────────────────────────────────────
  abre_acto "4 · Después de la sacudida"
  if pausa "reporte de daños en el Pixel, dictamen firmado en la consola, y genera el PDF"; then
    reporte
    cierra_acto "" "$(( VERDES - ACTO_V0 )) ✓ · $(( ROJOS - ACTO_R0 )) ✗"
  else
    omite_acto "lo saltó quien conducía"
  fi

  # ── limpieza ────────────────────────────────────────────────────────────
  echo
  printf '\033[1m── Limpieza · parte del guion, no del después ──\033[0m\n'
  echo "  1) suelta el enclavado: botón CERRAR ALERTA del panel, 2 clics + PIN (el campo"
  echo "     es de contraseña: los dígitos no salen en el proyector). Por terminal, CON el PIN:"
  echo "       curl -X POST -H 'X-Takab-Pin: <PIN>' $PANEL/api/reset"
  echo "     Sin la cabecera el panel responde 401 {\"error\":\"pin\"}: no se colgó, falta el PIN."
  echo "  2) en la consola, clasifica el incidente como 'reproduccion'."
  echo
  echo "     ⚠️ 'reproduccion', NO 'prueba'. Las dos cierran el incidente y ninguna"
  echo "     cuenta en la tasa de falsos positivos, así que la diferencia no se ve"
  echo "     en ningún número — se ve en lo que el registro DICE que pasó. 'prueba'"
  echo "     es mantenimiento o puesta en marcha; 'reproduccion' es exactamente esto:"
  echo "     una demostración. El valor se creó en T-7.14 (D-33) porque una corrida"
  echo "     de demostración no cabía en las otras cuatro sin mentir, y usar 'prueba'"
  echo "     desperdicia esa distinción el día que alguien audite el historial."

  registro_markdown
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
  --full) echo "El ensayo tiene actos en ✗. La tabla de arriba dice CUÁL: repite ESE acto, no el ensayo entero." ;;
  esac
  return 1
}

ACCION="${1:---preflight}"
case "$ACCION" in
--preflight) preflight ;;
--check) check ;;
--reporte) reporte ;;
--full) full ;;
-h | --help)
  sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
  ;;
*)
  echo "uso: $(basename "$0") [--preflight|--check|--reporte|--full]" >&2
  exit 2
  ;;
esac
resumen
