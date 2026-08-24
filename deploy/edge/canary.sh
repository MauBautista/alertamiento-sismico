#!/usr/bin/env bash
# TAKAB Ailert — activación con remojo y vuelta atrás automática (T-2.70).
#
# QUÉ ES ESTO Y POR QUÉ VIVE FUERA DEL CÓDIGO QUE ACTUALIZA.
#
# `deploy.sh` deja una release NUEVA en `${RAIZ}/releases/<id>/` con su propio
# venv, verificada y sin tocar el árbol vivo. Este script es lo único que la
# ACTIVA: repunta el symlink `${RAIZ}/edge`, reinicia al cliente, MIDE si el
# gabinete quedó sano y —si no— vuelve atrás solo.
#
# Vive en `${RAIZ}/bin/canary.sh`, FUERA de cualquier release, y no importa una
# sola línea de `takab_edge`. No es una preferencia de estilo: es el requisito
# que la cabecera de `deploy.sh` fichó como bloqueante —«el agente que revierte
# tendría que vivir FUERA de takab-edge (si takab-edge no arranca, no queda
# nadie que revierta)»—. Un reversor escrito en el código que se está
# sustituyendo no puede revertir el caso que importa: el de la versión que no
# arranca.
#
# QUÉ MIDE, Y POR QUÉ NO `systemctl is-active`.
#
# `is-active` a los 3 s no es un canary: un proceso que arranca y crashea al
# segundo 4 se reporta como despliegue exitoso, y con `Restart=always` el
# gabinete queda ciclando mientras el operador se va del sitio. Está fichado así
# en `TASKS.md` (T-2.70.a, refinamiento 3) y es el defecto que este script
# existe para cerrar. Aquí la salud es CUATRO hechos a la vez, sostenidos en el
# tiempo:
#
#   1. `takab-edge` está `active` para systemd;
#   2. su MainPID NO CAMBIÓ durante el remojo — un crash-loop se delata por el
#      relevo de PID aunque cada instancia individual esté `active`;
#   3. los pines siguen teniendo DUEÑO (`flock` exclusivo sobre el cerrojo, con
#      su registro confirmado por /proc), que es lo único que dice si el
#      edificio está protegido;
#   4. el panel local contesta 200 — o sea que el supervisor no sólo arrancó:
#      llegó a servir.
#
# MEDIDO MAL ≠ NO MEDIDO, y de esa distinción depende que este script no haga
# daño. «El proceso está muerto» se mide y manda revertir. «No pude preguntar»
# (falta `curl`, /proc ilegible, systemd ausente) NO manda revertir: revertir es
# reiniciar, reiniciar cuesta una ventana sin sirena, y hacerlo por un dato que
# nadie leyó es exactamente el daño de segundo orden que `deploy.sh` documenta
# en su paso 7. Ante «no pude preguntar» este script deja la versión nueva
# puesta, sale 2 y lo GRITA — jamás imprime un ✓.
#
# LO QUE ESTE SCRIPT NO TOCA NUNCA: `takab-gpio`. Es el dueño de los pines en un
# gabinete D3 y reiniciarlo cicla `GAS_VALVE` y `DOOR_RETAINER` (2 transiciones
# por pin, medidas) y abre una ventana sin sirena. Regla de oro 4. La única
# unidad que este script reinicia es `takab-edge`, el cliente.
#
# EL CASO `TAKAB_EDGE_GPIO_OWNER=edge`, que es el de todo gabinete desplegado
# hasta el 2026-08-16: ahí `takab-edge` ES el dueño de los pines, así que
# reiniciarlo SÍ es actuación física —cicla `GAS_VALVE` y `DOOR_RETAINER` y abre
# una ventana sin sirena—. Lo que decide si eso se permite NO es el gabinete: es
# QUIÉN LO ORDENÓ, y hay dos maneras muy distintas de llegar aquí.
#
#   · ATENDIDO (`--atendido`, que es como llama `deploy.sh`): hay una persona que
#     lanzó el despliegue a sabiendas y está leyendo esta salida. Ese reinicio ya
#     ocurría en CADA despliegue antes de esta ficha; negarlo ahora no protegería
#     a nadie, sólo dejaría al gabinete sin poder actualizarse. Se AVISA con todas
#     las letras y se sigue.
#   · REMOTO (el defecto, y como llegará el comando firmado de la nube): no hay
#     nadie delante. Ahí sí se exige `--ventana-de-mantenimiento` declarada, y sin
#     ella se niega: una actualización ordenada desde la consola no puede cerrar
#     el gas de un edificio a espaldas de quien está dentro.
#
# REVERTIR no exige nada de esto en ningún caso. Si se llegó a revertir es porque
# el gabinete ya está roto; ahí el reinicio no es el daño, es la cura, y negarse
# dejaría el edificio sin alertamiento esperando a que alguien conduzca al sitio.
#
# El día en que todos los gabinetes tengan `TAKAB_EDGE_GPIO_OWNER=gpio` (T-2.70.a)
# esta distinción deja de tener consecuencias: activar no mueve un solo pin.
#
# Uso:
#   canary.sh activar <id-de-release> [--ventana-de-mantenimiento] [--atendido]
#   canary.sh revertir [--motivo "texto"]
#   canary.sh estado
set -euo pipefail

RAIZ="${TAKAB_REMOTE_ROOT:-/opt/takab}"
VIVO="${RAIZ}/edge"
RELEASES="${RAIZ}/releases"
CERROJO="${TAKAB_EDGE_GPIO_LOCK_PATH:-/var/lib/takab/gpio.lock}"
ENTORNO="${TAKAB_EDGE_ENV_FILE:-/etc/takab/edge.env}"
ESTADO_DIR="${TAKAB_CANARY_ESTADO:-/var/lib/takab/canary}"
VEREDICTO="${ESTADO_DIR}/veredicto.json"

# Plazos. Los tres son variables por la misma razón que `TAKAB_REMOTE_ROOT`: el
# sandbox de `edge/tests/test_canary_sh.py` los acorta para probar la rama de
# agotamiento sin tardar tres minutos por test. En el Pi nadie los exporta.
#
#   ARRANQUE — cuánto se le da a la versión nueva para dar su PRIMERA lectura
#     sana. 90 s es el `TimeoutStartSec=` de las unidades: darle menos sería
#     matar por impaciencia a un arranque que systemd todavía considera vivo.
#   REMOJO — cuánto tiene que SOSTENER esa salud. 120 s no sale de la nada: con
#     `RestartSec=2` y la escalera de `RestartSteps=5`, un crash-loop encadena
#     sus primeros 5 reintentos en ~170 s, y el remojo tiene que ser largo para
#     ver al menos un relevo de PID. Acortarlo devuelve el defecto de `is-active`.
#   INTERVALO — cada cuánto se pregunta.
PLAZO_ARRANQUE="${TAKAB_CANARY_PLAZO_ARRANQUE:-90}"
PLAZO_REMOJO="${TAKAB_CANARY_REMOJO:-120}"
INTERVALO="${TAKAB_CANARY_INTERVALO:-3}"
# El panel local (T-1.53/T-2.15) sirve `/api/status` con LECTURA ABIERTA: no
# hace falta el PIN, así que este script no consume ningún secreto (regla de
# oro 6). El puerto sale del `edge.env` del gabinete cuando lo declara.
PANEL="${TAKAB_CANARY_PANEL:-}"

VENTANA=0
ATENDIDO=0
MOTIVO=""
POSICIONALES=()
while [ $# -gt 0 ]; do
  case "$1" in
  --ventana-de-mantenimiento)
    VENTANA=1
    shift
    ;;
  --atendido)
    ATENDIDO=1
    shift
    ;;
  --motivo)
    MOTIVO="${2:-}"
    shift 2
    ;;
  *)
    POSICIONALES+=("$1")
    shift
    ;;
  esac
done
set -- ${POSICIONALES+"${POSICIONALES[@]}"}

ACCION="${1:-}"

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

# QUIÉN es el dueño de los pines de ESTE gabinete. Misma lectura que `deploy.sh`
# —`tail -1`, gana la última— y por la misma razón: es la semántica de
# `EnvironmentFile=` en systemd, y leer la primera respondería por un gabinete
# distinto del que se está tocando. Vacío ⇒ `edge`, el default de
# `EdgeSettings.gpio_owner`.
dueno_configurado() {
  local valor
  valor="$(sed -n 's/^[[:space:]]*TAKAB_EDGE_GPIO_OWNER=//p' "$ENTORNO" 2>/dev/null |
    tail -1 | tr -d "\"' " || true)"
  [ -n "$valor" ] || valor=edge
  printf '%s' "$valor"
}

puerto_panel() {
  local valor
  valor="$(sed -n 's/^[[:space:]]*TAKAB_EDGE_LOCAL_API_PORT=//p' "$ENTORNO" 2>/dev/null |
    tail -1 | tr -d "\"' " || true)"
  case "$valor" in "" | *[!0-9]*) valor=8080 ;; esac
  printf '%s' "$valor"
}

# El PID principal de `takab-edge` según systemd. Es lo que convierte «está
# active» en «está active Y ES EL MISMO PROCESO»: un crash-loop mantiene la
# unidad `active` casi todo el tiempo y sólo se delata por el relevo de PID.
pid_principal() {
  systemctl show -p MainPID --value takab-edge 2>/dev/null || true
}

# Salud del gabinete. Escribe el motivo en `RAZON_SALUD` y devuelve:
#   0 = sano
#   1 = MEDIDO ENFERMO — hay vuelta atrás que dar
#   2 = NO SE PUDO MEDIR — no se revierte nada por esto (ver la cabecera)
RAZON_SALUD=""
medir_salud() {
  local pid_esperado="${1:-}"
  RAZON_SALUD=""

  if ! command -v systemctl >/dev/null 2>&1; then
    RAZON_SALUD="no hay systemctl con el que preguntar por la unidad"
    return 2
  fi
  if ! systemctl is-active takab-edge >/dev/null 2>&1; then
    RAZON_SALUD="systemd NO da takab-edge por activa"
    return 1
  fi

  # [T-2.70·CAMPO 2026-08-23] `MainPID=0` NO ES «NO PUDE MEDIR»: ES UNA MEDICIÓN,
  # Y ES MALA. Aquí los tres valores se fundían en uno y el resultado fue que el
  # canary dejó puesta una release que no arrancaba.
  #
  # Lo que pasó, medido en el gabinete: el `ExecStart` de las dos unidades
  # apuntaba a un venv cuyo intérprete `ProtectHome=true` esconde, así que el
  # exec moría con 203. Con `Type=simple` systemd da la unidad por arrancada en
  # el fork —`is-active` dice `active`— y el fallo llega en el hijo, dejando
  # `MainPID=0`. Ese par «activa y sin proceso principal» es exactamente el
  # retrato de un `ExecStart` que no llegó a ejecutarse, y tratarlo como «no
  # pude preguntar» convirtió una vuelta atrás automática en un edificio sin
  # sirena, sin cierre de gas y sin retenedores hasta que alguien lo miró.
  #
  # «No pude medir» queda para lo que de verdad no se pudo preguntar: que
  # `systemctl show` falle, o que conteste algo que no es un número.
  local pid estado_show=0
  pid="$(pid_principal)" || estado_show=$?
  if [ "$estado_show" != 0 ]; then
    RAZON_SALUD="no se pudo preguntar el MainPID de takab-edge (systemctl salió ${estado_show})"
    return 2
  fi
  case "$pid" in
  "" | *[!0-9]*)
    RAZON_SALUD="systemd contestó un MainPID que no es un número: ${pid:-(vacío)}"
    return 2
    ;;
  esac
  if [ "$pid" = 0 ]; then
    RAZON_SALUD="systemd da takab-edge por ACTIVA y no tiene proceso principal (MainPID=0): su ExecStart no llegó a ejecutarse"
    return 1
  fi
  if [ -n "$pid_esperado" ] && [ "$pid" != "$pid_esperado" ]; then
    # EL HALLAZGO QUE `is-active` NO PUEDE VER. La unidad sigue `active` y el
    # proceso es OTRO: arrancó, murió y systemd lo repuso. Con `Restart=always`
    # eso puede durar para siempre, y cada ciclo del dueño de los pines mueve
    # gas y retenedores.
    RAZON_SALUD="takab-edge se REINICIÓ durante el remojo (pid ${pid_esperado} → ${pid}): crash-loop"
    return 1
  fi

  # PROPIEDAD DE LOS PINES. Es lo único que dice si el edificio está protegido,
  # y se pregunta igual que en el paso 7 de `deploy.sh`: `flock -n -E 9`, donde
  # 9 = «está tomado» (lo que queremos) y 0 = «lo tomé yo, o sea que NADIE lo
  # tenía». Cualquier otro código es «no se pudo interrogar».
  if [ ! -e "$CERROJO" ]; then
    RAZON_SALUD="el cerrojo ${CERROJO} no existe: nadie llegó a reclamar los pines"
    return 1
  fi
  local estado=0
  flock -n -E 9 "$CERROJO" true || estado=$?
  if [ "$estado" = 0 ]; then
    RAZON_SALUD="el cerrojo ${CERROJO} está LIBRE: el gabinete NO está protegiendo"
    return 1
  fi
  if [ "$estado" != 9 ]; then
    RAZON_SALUD="no se pudo interrogar el cerrojo ${CERROJO} (flock salió ${estado})"
    return 2
  fi
  local dueno_pid
  dueno_pid="$(sed -n 's/^pid=//p' "$CERROJO" 2>/dev/null | tail -1 || true)"
  if [ -n "$dueno_pid" ] && [ ! -d "/proc/${dueno_pid}" ]; then
    RAZON_SALUD="el registro del cerrojo nombra al pid ${dueno_pid}, que no existe"
    return 1
  fi

  # EL PANEL. Que el supervisor no sólo arrancara: que llegara a SERVIR. Es lo
  # que separa «el proceso vive» de «el gabinete es operable», y en un gabinete
  # D3 es además la única de las cuatro señales que atraviesa la costura
  # `GpioLink` — o sea que un cliente que no puede hablar con el dueño de los
  # pines se ve aquí y en ningún otro sitio.
  if ! command -v curl >/dev/null 2>&1; then
    RAZON_SALUD="no hay curl con el que preguntar al panel"
    return 2
  fi
  if ! curl -fsS --max-time 5 "$PANEL" >/dev/null 2>&1; then
    RAZON_SALUD="el panel local (${PANEL}) no contesta"
    return 1
  fi

  RAZON_SALUD="sano"
  return 0
}

escribir_veredicto() {
  local resultado="$1" destino="$2" anterior="$3" razon="$4"
  mkdir -p "$ESTADO_DIR"
  # JSON a mano y no con python: este script no puede depender del intérprete de
  # una release que quizá no arranca. Los valores no llevan comillas ni saltos
  # (son ids de release y frases nuestras), y la razón se sanea por si acaso.
  razon="$(printf '%s' "$razon" | tr -d '"\\' | tr '\n' ' ')"
  printf '{"resultado":"%s","destino":"%s","anterior":"%s","razon":"%s","ts":"%s"}\n' \
    "$resultado" "$destino" "$anterior" "$razon" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    >"$VEREDICTO"
}

# Repunta el symlink. Se escribe a un nombre temporal y se RENOMBRA encima, en
# vez de `rm` + `ln`: `rename(2)` es atómico, así que no existe un instante en
# que `${RAIZ}/edge` no exista. Sin eso, un corte de luz en ese hueco dejaría al
# gabinete sin `ExecStart` y sin arranque — un edificio sin alertamiento por una
# operación de disco.
#
# LA `-T` DEL `mv` ES LA QUE SALVA, y no es cosmética: sin ella, `mv` sobre un
# destino que es un SYMLINK A DIRECTORIO lo sigue y mueve el temporal DENTRO de
# la release activa. El symlink se queda apuntando a la versión de antes, el
# script sigue adelante y el despliegue se declara hecho sobre código que nadie
# activó. Medido: quitar la `-T` pone en rojo SEIS de estos tests.
# La `-n` del `ln` es la misma familia de trampa un paso antes; aquí el
# temporal nunca existe todavía, así que no cambia nada — se escribe igual para
# que el día que alguien colapse las dos líneas en una no reintroduzca el
# defecto.
apuntar() {
  local destino="$1"
  ln -sfn "$destino" "${VIVO}.nuevo"
  # `mv -T` sobre el symlink es ATÓMICO (rename(2)): no existe un instante en
  # que `${RAIZ}/edge` no exista. Sin esto, un corte de luz entre el `rm` y el
  # `ln` dejaría al gabinete sin `ExecStart` y sin arranque.
  mv -T "${VIVO}.nuevo" "$VIVO"
}

release_actual() {
  readlink "$VIVO" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# activar
# ---------------------------------------------------------------------------
activar() {
  local id="${1:-}"
  if [ -z "$id" ]; then
    echo "uso: canary.sh activar <id-de-release> [--ventana-de-mantenimiento]" >&2
    exit 64
  fi
  # EL DESTINO ES `<release>/edge`, NO LA RELEASE ENTERA, y el porqué no es
  # estético: `takab_edge/schemas.py` resuelve `shared/schemas` como
  # `Path(__file__).resolve().parents[2] / "shared" / "schemas"`. Con el symlink
  # apuntando a la release, esos `parents[2]` caerían en `${RAIZ}/releases` y el
  # gabinete buscaría los contratos donde no están. Apuntando a `<release>/edge`
  # caen en `<release>`, así que cada release lleva SUS contratos y una vuelta
  # atrás los revierte con el código. `_default_root()` de `version.py` —el
  # directorio que contiene al paquete— resuelve por la misma razón, y por eso
  # `FW_VERSION` vive dentro de `edge/`.
  local destino="${RELEASES}/${id}/edge"

  # --- Guardas. Todas ANTES de tocar el symlink: una vez repuntado, cualquier
  # negativa ya cuesta un reinicio.
  if [ ! -d "$destino" ]; then
    echo "✗ no existe la release ${RELEASES}/${id} (falta ${destino})" >&2
    exit 1
  fi
  if [ ! -x "${destino}/.venv/bin/takab-edge" ]; then
    echo "✗ la release ${id} no trae el ejecutable que lanza la unidad" >&2
    echo "  (${destino}/.venv/bin/takab-edge). Sin él, activar = apagar el gabinete." >&2
    exit 1
  fi
  if [ -e "$VIVO" ] && [ ! -L "$VIVO" ]; then
    # El gabinete todavía no está migrado al layout A/B: `${RAIZ}/edge` es un
    # DIRECTORIO de verdad. Repuntar aquí borraría el árbol vivo.
    echo "✗ ${VIVO} no es un symlink: este gabinete no está migrado al layout A/B." >&2
    echo "  Lo migra deploy.sh; este script no toca un árbol vivo que no puede devolver." >&2
    exit 1
  fi

  local anterior
  anterior="$(release_actual)"
  if [ -n "$anterior" ] && [ ! -x "${anterior}/.venv/bin/takab-edge" ]; then
    # LA MISMA HONESTIDAD QUE `deploy.sh` APLICA A `edge.prev`: no se ofrece una
    # vuelta atrás que no existe. Si la release anterior ya no está entera —la
    # podó una retención, la borró alguien—, activar sería un viaje de ida.
    echo "⚠ la release anterior (${anterior}) ya no está completa:" >&2
    echo "  si esta activación sale mal, NO hay vuelta atrás automática." >&2
    anterior=""
  fi

  local dueno
  dueno="$(dueno_configurado)"
  if [ "$dueno" != gpio ]; then
    if [ "$VENTANA" != 1 ] && [ "$ATENDIDO" != 1 ]; then
      echo "✗ ${ENTORNO} declara TAKAB_EDGE_GPIO_OWNER=${dueno}: en este gabinete" >&2
      echo "  takab-edge ES el dueño de los pines, así que reiniciarlo CICLA" >&2
      echo "  GAS_VALVE y DOOR_RETAINER y abre una ventana sin sirena." >&2
      echo "  Una activación REMOTA no hace eso a espaldas del edificio: declara" >&2
      echo "  --ventana-de-mantenimiento, o migra el gabinete a" >&2
      echo "  TAKAB_EDGE_GPIO_OWNER=gpio (T-2.70.a), donde esta activación no" >&2
      echo "  mueve un solo pin." >&2
      exit 1
    fi
    echo "⚠ este gabinete todavía tiene al DUEÑO DE LOS PINES dentro de takab-edge" >&2
    echo "  (${ENTORNO}: TAKAB_EDGE_GPIO_OWNER=${dueno}), así que la activación" >&2
    echo "  CICLA GAS_VALVE y DOOR_RETAINER y abre una ventana sin sirena." >&2
    echo "  Se sigue porque lo ordenó una persona; migrar a" >&2
    echo "  TAKAB_EDGE_GPIO_OWNER=gpio (T-2.70.a) quita este coste." >&2
  fi

  [ -n "$PANEL" ] || PANEL="http://127.0.0.1:$(puerto_panel)/api/status"

  if [ "$anterior" = "$destino" ]; then
    echo "→ la release ${id} YA está activa; no se repunta nada"
    escribir_veredicto ya_activa "$destino" "$anterior" "el symlink ya apuntaba ahí"
    exit 0
  fi

  echo "→ activando ${id}"
  echo "  anterior: ${anterior:-(ninguna)}"
  apuntar "$destino"
  # El veredicto se escribe ANTES del reinicio, no después: si el gabinete se
  # queda colgado a mitad, lo que hay en disco tiene que decir de dónde venía.
  # Un reversor que no sabe a dónde volver no es un reversor.
  escribir_veredicto en_curso "$destino" "$anterior" "symlink repuntado, reiniciando"
  # `|| revertir` y NO `systemctl restart` a secas: con `set -e`, un `restart`
  # que sale distinto de 0 —unidad mal escrita, `ExecStart` que no existe,
  # dependencia sin montar— MATABA a este script con el symlink YA repuntado.
  # O sea: el reversor moría dejando puesto exactamente lo que no arranca, y el
  # próximo corte de luz ejecutaría eso. Lo destapó
  # `test_una_release_que_no_levanta_vuelve_atras_sola`.
  if ! systemctl restart takab-edge; then
    echo "✗ systemd no pudo arrancar takab-edge con la release ${id}" >&2
    revertir_a "$anterior" "$destino" "systemctl restart takab-edge falló"
    return
  fi

  # --- Fase 1: ARRANQUE. Se le da al gabinete hasta `PLAZO_ARRANQUE` para dar
  # su primera lectura sana. Aquí una lectura enferma NO es veredicto: un
  # supervisor que todavía está levantando sus 16 módulos está legítimamente
  # «no sano» durante segundos.
  local pid_soak="" transcurrido=0 estado
  while [ "$transcurrido" -lt "$PLAZO_ARRANQUE" ]; do
    estado=0
    medir_salud "" || estado=$?
    if [ "$estado" = 0 ]; then
      pid_soak="$(pid_principal)"
      break
    fi
    if [ "$estado" = 2 ]; then
      echo "⚠ ACTIVACIÓN NO VERIFICADA: ${RAZON_SALUD}" >&2
      echo "  La release ${id} QUEDA PUESTA. No se revierte por un dato que" >&2
      echo "  nadie pudo leer: revertir es reiniciar, y reiniciar cuesta." >&2
      escribir_veredicto no_medible "$destino" "$anterior" "$RAZON_SALUD"
      exit 2
    fi
    sleep "$INTERVALO"
    transcurrido=$((transcurrido + INTERVALO))
  done

  if [ -z "$pid_soak" ]; then
    echo "✗ la release ${id} no dio una sola lectura sana en ${PLAZO_ARRANQUE} s" >&2
    echo "  Último motivo: ${RAZON_SALUD}" >&2
    revertir_a "$anterior" "$destino" "no arrancó: ${RAZON_SALUD}"
    return
  fi

  echo "  arrancó (pid ${pid_soak}); remojo de ${PLAZO_REMOJO} s"

  # --- Fase 2: REMOJO. Desde la primera lectura sana, la salud tiene que
  # SOSTENERSE. Una sola lectura enferma aquí sí es veredicto: el gabinete ya
  # había demostrado que podía estar sano.
  transcurrido=0
  while [ "$transcurrido" -lt "$PLAZO_REMOJO" ]; do
    sleep "$INTERVALO"
    transcurrido=$((transcurrido + INTERVALO))
    estado=0
    medir_salud "$pid_soak" || estado=$?
    if [ "$estado" = 1 ]; then
      echo "✗ la release ${id} se cayó durante el remojo: ${RAZON_SALUD}" >&2
      revertir_a "$anterior" "$destino" "$RAZON_SALUD"
      return
    fi
    if [ "$estado" = 2 ]; then
      echo "⚠ REMOJO INTERRUMPIDO: ${RAZON_SALUD}" >&2
      echo "  La release ${id} QUEDA PUESTA, sin ✓." >&2
      escribir_veredicto no_medible "$destino" "$anterior" "$RAZON_SALUD"
      exit 2
    fi
  done

  echo "✓ release ${id} activa y sana durante ${PLAZO_REMOJO} s"
  escribir_veredicto ok "$destino" "$anterior" "remojo de ${PLAZO_REMOJO} s sin una sola lectura enferma"
}

# ---------------------------------------------------------------------------
# revertir
# ---------------------------------------------------------------------------

# Vuelta atrás. `anterior` puede venir vacío —primera release del gabinete, o
# release anterior podada—: entonces no hay nada que hacer salvo decirlo con
# todas las letras. Un rollback que finge haber ocurrido es peor que ninguno.
revertir_a() {
  local anterior="$1" fallida="$2" razon="$3"
  if [ -z "$anterior" ]; then
    echo "✗✗ NO HAY VUELTA ATRÁS: no consta una release anterior completa." >&2
    echo "   El gabinete se queda con ${fallida}, que acaba de fallar." >&2
    echo "   Causa: ${razon}" >&2
    echo "   Diagnóstico: journalctl -u takab-edge -n 80 --no-pager" >&2
    escribir_veredicto sin_vuelta "$fallida" "" "$razon"
    exit 1
  fi

  echo "→ REVIRTIENDO a ${anterior}"
  apuntar "$anterior"
  escribir_veredicto revirtiendo "$anterior" "$fallida" "$razon"
  # Aquí NO se exige ventana declarada aunque el dueño sea `takab-edge`: si se
  # llegó a este punto el gabinete ya está roto, y el reinicio no es el daño
  # sino la cura. Ver la cabecera.
  #
  # `|| true` por la razón contraria a la de arriba: aquí un `restart` que falla
  # NO puede abortar. Lo que decide el veredicto es el bucle de salud de abajo,
  # que MIDE; morir por el código de salida de systemctl dejaría al operador sin
  # saber si el gabinete quedó sano, que es la única pregunta que importa.
  systemctl restart takab-edge || true

  local transcurrido=0 estado
  while [ "$transcurrido" -lt "$PLAZO_ARRANQUE" ]; do
    estado=0
    medir_salud "" || estado=$?
    if [ "$estado" = 0 ]; then
      echo "✓ revertido a ${anterior}; el gabinete volvió a estar sano" >&2
      echo "  La release ${fallida} NO se borra: es la evidencia del fallo." >&2
      escribir_veredicto revertido "$anterior" "$fallida" "$razon"
      exit 1
    fi
    sleep "$INTERVALO"
    transcurrido=$((transcurrido + INTERVALO))
  done

  # LO PEOR QUE PUEDE PASAR, y se dice sin adornos: volvimos a la versión que
  # funcionaba y TAMPOCO está sana. Eso ya no es un update malo — es el
  # gabinete. Sale con un código propio para que quien llame no lo confunda con
  # un rollback normal.
  echo "✗✗ REVERTIDO Y SIGUE ENFERMO: ni ${anterior} levanta el gabinete." >&2
  echo "   Último motivo: ${RAZON_SALUD}" >&2
  echo "   Esto ya no es la actualización: es el gabinete. Requiere visita." >&2
  escribir_veredicto revertido_sin_salud "$anterior" "$fallida" "$RAZON_SALUD"
  exit 3
}

revertir_manual() {
  [ -n "$PANEL" ] || PANEL="http://127.0.0.1:$(puerto_panel)/api/status"
  local actual anterior
  actual="$(release_actual)"
  # La release a la que volver sale del veredicto en disco, que es lo que
  # `activar` dejó escrito ANTES de reiniciar.
  anterior="$(sed -n 's/.*"anterior":"\([^"]*\)".*/\1/p' "$VEREDICTO" 2>/dev/null || true)"
  if [ -z "$anterior" ] || [ ! -x "${anterior}/.venv/bin/takab-edge" ]; then
    echo "✗ no consta una release anterior completa a la que volver" >&2
    echo "  (veredicto: ${VEREDICTO})" >&2
    exit 1
  fi
  revertir_a "$anterior" "$actual" "${MOTIVO:-reversión ordenada a mano}"
}

case "$ACCION" in
activar) activar "${2:-}" ;;
revertir) revertir_manual ;;
estado)
  if [ -r "$VEREDICTO" ]; then
    cat "$VEREDICTO"
  else
    printf '{"resultado":"sin_datos","destino":"%s","anterior":"","razon":"nunca se activó nada por aquí","ts":""}\n' \
      "$(release_actual)"
  fi
  ;;
*)
  echo "uso: canary.sh {activar <id> [--ventana-de-mantenimiento] | revertir [--motivo T] | estado}" >&2
  exit 64
  ;;
esac
