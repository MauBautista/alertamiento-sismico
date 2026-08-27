#!/usr/bin/env bash
# Despliega el código del edge al Pi (T-1.40). Idempotente.
#
# Hasta ahora el código llegaba a /opt/takab por un rsync manual sin versionar
# (el gap lo documentó la auditoría de Fase 1.6). Este script ES el mecanismo:
#   1. rsync de edge/ y shared/schemas/ a una RELEASE NUEVA
#      (`releases/<ts>-<sha>/`), que nadie apunta todavía;
#   2. PRE-VUELO sobre esa release: `compileall` del código recién copiado.
#      Abortar aquí no toca el gabinete — la release queda inerte;
#   3. MIGRACIÓN al layout A/B si el gabinete todavía tiene `edge` como
#      directorio (una vez por gabinete, y sólo en ventana declarada), y marca
#      de FW_VERSION dentro de la release;
#   4. `uv sync` con los extras de EDGE_EXTRAS DENTRO de la release: cada
#      versión lleva su propio venv, que es lo que hace COMPLETA la vuelta atrás;
#   5. GATE: importa el CÓDIGO DE LA RELEASE (`takab_edge.supervisor` y
#      `takab_edge.gpio.__main__` — los dos entry points de las unidades) y sus
#      dependencias críticas (lgpio, awsiot). Aborta SIN activar nada si falla;
#   6. instala/refresca las unidades systemd versionadas, HABILITA (o
#      deshabilita) la unidad del dueño de los pines según lo que el `edge.env`
#      de ESTE gabinete declare en `TAKAB_EDGE_GPIO_OWNER`, la levanta con
#      `start` (no-op si ya corre) y ACTIVA la release por `bin/canary.sh`, que
#      repunta el symlink, reinicia al cliente, mide salud SOSTENIDA y vuelve
#      atrás solo si falla; después, la poda de releases antiguas;
#   7. verificación: PROPIEDAD DE LOS PINES — quién sostiene el cerrojo del GPIO
#      Y si ese dueño corre el código que acabamos de desplegar (ESTO sí puede
#      tumbar el despliegue) + últimas líneas del journal (INFORMATIVO: su fallo
#      no lo tumba).
#
# [T-2.70·rev] POR QUÉ HAY DOS GATES Y NO UNO. El gate original era
# `python -c 'import lgpio, awsiot'`: DOS DEPENDENCIAS DE TERCEROS que viven en
# el `.venv`, y el `.venv` está EXCLUIDO del rsync. O sea que el único gate del
# despliegue no podía fallar por culpa del código que se estaba desplegando —
# era ciego justo a la causa más probable de que un gabinete no arranque tras un
# update. El gate de ahora importa el árbol recién copiado; el import de
# `takab_edge.supervisor` arrastra los ~18 submódulos del supervisor y es lo
# mínimo que demuestra que el árbol nuevo es ARRANCABLE sin tocar hardware ni
# nube (la pin factory y el MQTT se instancian en `_on_start`/`build`, no al
# importar).
#
# Y POR QUÉ EL PRE-VUELO ES SINTÁCTICO Y EL GATE ES DE IMPORTS: el pre-vuelo
# corre ANTES del `uv sync`, con el venv VIEJO. Un `import` ahí daría falsos
# abortos cada vez que el commit nuevo añada una dependencia (aún no instalada).
# `compileall` no depende de nada instalado: es puro parseo, cero falsos
# positivos, y atrapa el error de sintaxis — que es destructivo y frecuente —
# cuando todavía no se ha destruido nada.
#
# [T-2.70] DESPLIEGUE A/B: EL CÓDIGO NUEVO NO PISA AL VIEJO. Hasta esta ficha el
# despliegue era IN-PLACE sobre una instalación EDITABLE del venv, así que el
# swap reescribía el código BAJO LOS PIES del proceso vivo y la reversibilidad
# era PARCIAL: `edge.prev` devolvía el fuente, pero NO lo que `uv sync` hubiera
# hecho en el `.venv`. Un rollback completo exigía volver a correr este script
# desde el commit anterior — o sea, con un enlace a internet y una persona.
#
# Ahora cada despliegue aterriza ENTERO en `${RAIZ}/releases/<id>/`, con SU
# PROPIO `.venv`, y `${RAIZ}/edge` es un SYMLINK que decide cuál corre. El
# `ExecStart` de las dos unidades no cambia —sigue siendo
# `/opt/takab/edge/.venv/bin/…`—: lo que cambia es a dónde resuelve ese `edge`.
# En consecuencia:
#   · La vuelta atrás es COMPLETA (fuente + dependencias) y cuesta un `mv -T`
#     del symlink más un `restart` del cliente. La decide y la ejecuta
#     `${RAIZ}/bin/canary.sh` EN EL GABINETE, no la nube: regla de oro 2.
#   · El código nuevo se verifica ANTES de existir para systemd. Un pre-vuelo
#     que aborta ya no deja «el disco con código nuevo sin verificar que el
#     próximo arranque ejecutaría»: deja una release inerte que nadie apunta.
#   · Reiniciar al DUEÑO DE LOS PINES sigue siendo una ACTUACIÓN FÍSICA sobre el
#     edificio: `GpioController._on_stop()` llama `drive_all_safe()`, que
#     de-energiza los relés — con el fail-safe por defecto eso CIERRA EL GAS y
#     SUELTA LOS RETENEDORES DE PUERTA, y el arranque los repone. Por eso la
#     activación sólo reinicia al CLIENTE, y el dueño sigue exigiendo
#     `--ventana-de-mantenimiento` declarada.
#
# LO QUE SIGUE SIN SER: una actualización que el gabinete SE BAJA solo. El
# artefacto sigue viajando por `rsync` desde la máquina del operador; lo que la
# nube gobierna es la ACTIVACIÓN (comando firmado) y el orden del canary, no la
# distribución. Un OTA de verdad —artefacto firmado en S3 que el gabinete tira—
# es otra ficha.
#
# [T-2.70.a·D3] QUIÉN ES EL DUEÑO DE LOS PINES YA NO ES UNA CONSTANTE. Aquí se
# afirmaba COMO HECHO que `takab-edge` es el proceso que sostiene el reflejo
# SASMEX→sirena, y se apoyaba en la exclusión mutua que las unidades declaraban
# entre sí (gate #6, supervisor único). Era cierto hasta D3 y hoy es narrativa
# FALSA en el archivo que se lee ANTES de desplegar: D3 retiró esa directiva
# —anclado en `test_las_dos_unidades_YA_NO_son_mutuamente_excluyentes`— y el
# dueño lo decide `TAKAB_EDGE_GPIO_OWNER` en /etc/takab/edge.env:
#   · `edge` (defecto, y todo gabinete desplegado hasta hoy) — el dueño es
#     `takab-edge`, así que su reinicio ES una ventana de desprotección acotada
#     por `TimeoutStopSec` y cuesta un ciclo eléctrico de gas y retenedores;
#   · `gpio` — el dueño es `takab-gpio` y reiniciar `takab-edge` NO mueve un pin
#     (criterio 7 de la ficha). A cambio, el proceso que sostiene la sirena deja
#     de reiniciarse solo: este script lo HABILITA y lo LEVANTA, pero **no lo
#     reinicia** salvo que se declare `--ventana-de-mantenimiento`, y si se queda
#     con código anterior el despliegue NO se declara bueno (paso 7).
# Este script no adivina cuál de los dos es: lo LEE del gabinete.
# El despliegue A/B es lo que quita las tres cosas, y ES lo que hace este script
# desde T-2.70: sincroniza a /opt/takab/releases/<id>/ con su propio venv, lo
# verifica y sólo entonces repunta el symlink /opt/takab/edge (el ExecStart de
# las unidades NO cambia). El agente que revierte vive FUERA de cualquier
# release —`${RAIZ}/bin/canary.sh`, sin una línea de `takab_edge`— porque si
# takab-edge no arranca no puede quedar en él el único que sabe volver atrás.
#
# ⚠ ACREDITACIÓN PENDIENTE: esto cambia el ARRANQUE del camino de vida. El
# primer despliegue A/B sobre un gabinete real migra `${RAIZ}/edge` de
# directorio a symlink, y eso no se declara bueno con tests en verde: exige el
# gate G-01 (restart en frío del Pi con las dos unidades volviendo solas). Ver
# `takab-docs/runbooks/RUNBOOK-sesion-de-vida.md`.
#
# Credenciales/identidad NO viajan por aquí: /etc/takab/{certs,edge.env} las
# instala infra/scripts/provision_gateway.sh (regla de oro 6).
#
# Uso: deploy/edge/deploy.sh [ssh_host] [--ventana-de-mantenimiento]
#      (host por defecto: takab-pi5)
#
#   --ventana-de-mantenimiento — REINICIA al dueño de los pines antes que al
#     cliente. Es una ACTUACIÓN FÍSICA declarada: cicla `GAS_VALVE` y
#     `DOOR_RETAINER` (2 transiciones por pin, medidas en
#     edge/tests/test_deploy_artifacts.py) y abre una ventana sin sirena. Sólo
#     con el edificio avisado. Sin esta bandera, el dueño NUNCA se reinicia.
#     Con `TAKAB_EDGE_GPIO_OWNER=gpio` reinicia ADEMÁS a `takab-gpio` para que
#     el dueño estrene el código nuevo; con el dueño todavía dentro de
#     `takab-edge` (el defecto), la activación YA reinicia al dueño y entonces
#     la bandera pasa a ser OBLIGATORIA — sin ella `canary.sh` se niega.
set -euo pipefail

# [T-2.70.a·D3·B2] La bandera va por delante del posicional (mismo patrón que
# infra/scripts/provision_gateway.sh) para que `deploy.sh host --ventana…` y
# `deploy.sh --ventana… host` sean lo mismo y nadie se coma un argumento.
VENTANA_MANTENIMIENTO=0
POSICIONALES=()
while [ $# -gt 0 ]; do
  case "$1" in
  --ventana-de-mantenimiento)
    VENTANA_MANTENIMIENTO=1
    shift
    ;;
  --desde-esta-rama)
    # [T-2.171] La escotilla de A-1. Aqui pesa mas que en la nube: lo que se
    # despliega toca la sirena, asi que desplegar una rama tiene que ser una
    # frase que alguien escribe, no el estado en que quedo el arbol.
    export TAKAB_DEPLOY_RAMA_LIBRE=1
    shift
    ;;
  *)
    POSICIONALES+=("$1")
    shift
    ;;
  esac
done
set -- ${POSICIONALES+"${POSICIONALES[@]}"}

HOST="${1:-takab-pi5}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# [T-2.171] Regla A-1, en codigo. Se pasa `si` a la tolerancia de arbol sucio
# porque este script la DECLARA a proposito unas lineas mas abajo (`--dirty`, y
# el aviso de que la version no es reproducible): depurar en sitio con el
# gabinete delante es un caso real. Rama y limpieza son dos preguntas distintas
# y aqui solo se anade la primera — la segunda ya tenia su respuesta escrita.
# shellcheck source=../lib/guardas.sh
. "${ROOT}/deploy/lib/guardas.sh"
guarda_de_rama "edge" si

# Raíz del gabinete. Es una VARIABLE y no un literal para que
# edge/tests/test_deploy_sh.py pueda correr este script de verdad contra un
# /opt/takab de mentira (con ssh/rsync/uv/systemctl falsos) y comprobar el ORDEN
# REAL de las operaciones — en particular que un gate que aborta deja el árbol
# vivo intacto. En producción nadie exporta esta variable: vale /opt/takab.
RAIZ_REMOTA="${TAKAB_REMOTE_ROOT:-/opt/takab}"
# Las rutas del árbol vivo y de la instantánea las deriva el bloque remoto de
# esta misma raíz; aquí sólo hace falta el destino del rsync de ensayo.

# [T-2.70.a·D1.5] Cerrojo de PROPIEDAD DE LOS PINES del gabinete: el archivo
# sobre el que el dueño del GPIO sostiene un flock exclusivo (ver el paso 7 y
# `EdgeSettings.gpio_lock_file`). Variable por la misma razón que la raíz remota:
# el sandbox de edge/tests/test_deploy_sh.py necesita apuntarlo a un tmp_path. En
# producción nadie la exporta y vale /var/lib/takab/gpio.lock — que es lo que
# `gpio_lock_file` resuelve para un GABINETE (`dev_mode=false`, que es lo que
# ponen explícitamente las dos unidades). Fuera del Pi ese mismo campo deriva un
# cerrojo por gabinete en el directorio temporal, pero este script no despliega
# fuera del Pi.
CERROJO_GPIO="${TAKAB_EDGE_GPIO_LOCK_PATH:-/var/lib/takab/gpio.lock}"

# [T-2.70.a·D1·MENOR-1] Cuánto se SONDEA la propiedad de los pines tras el
# reinicio, en segundos. No es un `sleep`: es el techo de una espera que termina
# en cuanto hay dueño (ver paso 7). Generoso a propósito —el arranque real mide
# 0.60 s en x86 y ~1.0 s con los imports de producción, y el margen en el Pi 4
# no es medible sin el Pi—, porque el coste de pasarse es esperar unos segundos
# de más en un gabinete AVERIADO, y el coste de quedarse corto es declarar «el
# gabinete NO está protegiendo» sobre un gabinete SANO: eso empuja a revertir,
# revertir es reiniciar, y reiniciar mueve GAS_VALVE y DOOR_RETAINER.
# Variable por la misma razón que las dos de arriba: el sandbox necesita
# acortarla para probar la rama de agotamiento sin tardar 45 s por test.
PLAZO_PROPIEDAD="${TAKAB_DEPLOY_PLAZO_PROPIEDAD:-45}"

# [T-2.70.a·D3·B2] IDENTIDAD DEL GABINETE. Es el `EnvironmentFile=` de LAS DOS
# unidades (sin `-`: sin este archivo no arranca ninguna) y desde D3 también
# dice QUIÉN es el dueño de los pines. El despliegue lo LEE —jamás lo escribe:
# lo instala `infra/scripts/provision_gateway.sh`, que además lo FUSIONA (regla
# de oro 6 y la lección del PR #13). Variable por la misma razón que las tres de
# arriba: el sandbox de edge/tests/test_deploy_sh.py no puede escribir en /etc.
ARCHIVO_ENTORNO="${TAKAB_EDGE_ENV_FILE:-/etc/takab/edge.env}"

# ---------------------------------------------------------------------------
# EXTRAS DEL PI. `uv sync` DESINSTALA lo que no esté en el set resuelto, así que
# esta lista no es "qué añadir": es "qué debe existir en el venv". Sincronizar
# con un solo extra PODÓ `awsiotsdk` en el primer deploy real y dejó al gabinete
# offline spooleando.
#
# Los dos arrays los lee `edge/tests/test_deploy_artifacts.py`, que los cruza
# contra `[project.optional-dependencies]` de `edge/pyproject.toml` y exige que
# TODO extra declarado esté en uno de los dos. Así, declarar un extra nuevo
# obliga a decidir si va al Pi, y el olvido sale en rojo en CI en vez de salir
# en un gabinete mudo.
EDGE_EXTRAS=(hardware aws)
# Declarados en pyproject pero NO instalados, cada uno con su razón:
#   bacnet — driver BACnet/IP real (T-1.9); hoy se usa el simulador.
#   lora   — módem ESP32 por USB-serial (T-2.33); hardware aún no instalado.
EDGE_EXTRAS_OMITIDOS=(bacnet lora)

EDGE_EXTRA_FLAGS=""
for _extra in "${EDGE_EXTRAS[@]}"; do
  EDGE_EXTRA_FLAGS+=" --extra ${_extra}"
done

# SHA que se esta desplegando. `--dirty` es deliberado: si el arbol tiene cambios sin
# commitear, lo que corre en el gabinete NO es ese commit y la ficha de la flota debe
# decirlo en vez de fingir limpieza.
FW_VERSION="$(git -C "$ROOT" describe --always --dirty --abbrev=7)"
echo "→ versión a desplegar: ${FW_VERSION}"
case "$FW_VERSION" in
*-dirty) echo "  OJO: árbol sucio; el gabinete reportará '${FW_VERSION}' (no es un commit reproducible)" ;;
esac

# [T-2.70] EL ID DE LA RELEASE. Lleva la marca de tiempo POR DELANTE del sha, y
# las dos partes hacen falta:
#   · el sha solo NO es único. `git describe --always --dirty` devuelve la MISMA
#     cadena para cualquier árbol sucio, así que dos despliegues seguidos de una
#     sesión de trabajo caerían en el mismo directorio — y si ese directorio es
#     el que está corriendo, el rsync reescribe el código bajo los pies del
#     proceso vivo, que es exactamente el defecto que el layout A/B elimina.
#     Ni siquiera con un árbol limpio: re-desplegar el mismo commit pisaría la
#     release activa.
#   · la marca delante hace que el orden alfabético sea el CRONOLÓGICO, que es
#     lo que la poda y cualquier `ls` necesitan para no mentir.
# UTC y no hora local: un gabinete cuyo huso cambie de estación reordenaría sus
# propias releases.
RELEASE_ID="$(date -u +%Y%m%dT%H%M%SZ)-${FW_VERSION}"
DESTINO_RELEASE="${RAIZ_REMOTA}/releases/${RELEASE_ID}"

# --- 1. LA RELEASE NUEVA: aterriza donde nadie la ejecuta --------------------
# `--delete` aquí es sobre un directorio RECIÉN CREADO, no sobre lo que el
# gabinete ejecuta: el `RELEASE_ID` lleva marca de tiempo, así que ninguna
# release se escribe dos veces y ningún rsync puede tocar la que está corriendo.
# El árbol vivo no se toca hasta el paso 6, y sólo si los gates pasan.
# `rsync` crea el ÚLTIMO componente del destino, no los intermedios: sin esto,
# un gabinete recién aprovisionado (sin ${RAIZ_REMOTA}/shared) muere con
# «mkdir … failed: No such file or directory». Lo destapó el sandbox de
# edge/tests/test_deploy_sh.py, que parte de una raíz vacía; contra el Pi actual
# no se veía porque los directorios ya existían de despliegues anteriores.
ssh "$HOST" "mkdir -p '${DESTINO_RELEASE}/edge' '${DESTINO_RELEASE}/shared' '${RAIZ_REMOTA}/bin'"

# [T-2.70] LA RELEASE ES AUTOCONTENIDA: `edge/` y `shared/schemas/` viajan
# DENTRO de ella, no a un `${RAIZ}/shared` compartido entre versiones. Si los
# contratos vivieran fuera, una vuelta atrás devolvería el código y NO los
# schemas contra los que ese código valida — media reversión, que es la peor.
#
# Y por eso el symlink apunta a `<release>/edge` y no a `<release>`:
# `takab_edge/schemas.py` resuelve los contratos como
# `Path(__file__).resolve().parents[2] / "shared" / "schemas"`, así que el
# paquete tiene que colgar de un directorio que TENGA un `shared` hermano.
echo "→ sincronizando edge/ y shared/schemas/ a ${HOST}:${DESTINO_RELEASE}"
rsync -az --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  "$ROOT/edge/" "$HOST:${DESTINO_RELEASE}/edge/"
rsync -az --delete "$ROOT/shared/schemas/" "$HOST:${DESTINO_RELEASE}/shared/schemas/"

# El agente de canary/reversión va a `${RAIZ}/bin`, FUERA de toda release: es lo
# único que puede revertir a una versión que no arranca, así que no puede vivir
# dentro de la versión que se está sustituyendo. Se refresca en cada despliegue
# —es un archivo, no un servicio— y no depende de `takab_edge` ni del venv.
rsync -az "$ROOT/deploy/edge/canary.sh" "$HOST:${RAIZ_REMOTA}/bin/canary.sh"
ssh "$HOST" "chmod 0755 '${RAIZ_REMOTA}/bin/canary.sh'"

echo "→ pre-vuelo, swap, dependencias, gate, unidades y reinicio en ${HOST}"
# El bloque remoto va en un heredoc CITADO ('REMOTO'): nada se expande aquí.
# Lo único que viaja del lado local son los flags de extras, la versión y la raíz
# remota, como variables de entorno del `bash -s` remoto, para que cada valor
# viva en UN solo sitio.
ssh "$HOST" \
  "EDGE_EXTRA_FLAGS='${EDGE_EXTRA_FLAGS}' FW_VERSION='${FW_VERSION}' RELEASE_ID='${RELEASE_ID}' TAKAB_REMOTE_ROOT='${RAIZ_REMOTA}' TAKAB_EDGE_GPIO_LOCK_PATH='${CERROJO_GPIO}' TAKAB_DEPLOY_PLAZO_PROPIEDAD='${PLAZO_PROPIEDAD}' TAKAB_EDGE_ENV_FILE='${ARCHIVO_ENTORNO}' TAKAB_DEPLOY_VENTANA='${VENTANA_MANTENIMIENTO}' TAKAB_DEPLOY_RUTAS_OCULTAS='${TAKAB_DEPLOY_RUTAS_OCULTAS:-}' TAKAB_UV_PYTHON_DIR='${TAKAB_UV_PYTHON_DIR:-}' bash -s" <<'REMOTO'
set -euo pipefail
# SSH no interactivo no carga el PATH de login: uv vive en ~/.local/bin.
export PATH="$HOME/.local/bin:$PATH"

RAIZ="${TAKAB_REMOTE_ROOT:-/opt/takab}"
# `VIVO` es la ruta que los `ExecStart` de las dos unidades nombran, y desde
# T-2.70 es un SYMLINK a `<release>/edge`. Nada de lo que sigue lo escribe: lo
# repunta `canary.sh`, y sólo tras verificar la release nueva.
VIVO="${RAIZ}/edge"
RELEASES="${RAIZ}/releases"
NUEVA="${RELEASES}/${RELEASE_ID}/edge"
ENTORNO="${TAKAB_EDGE_ENV_FILE:-/etc/takab/edge.env}"
VENTANA="${TAKAB_DEPLOY_VENTANA:-0}"

# --- 2. PRE-VUELO: verificar ANTES de destruir -------------------------------
# El gate de imports (paso 5) llega TARDE por construcción: para que los imports
# signifiquen algo hace falta el `uv sync`, y para el `uv sync` hace falta el
# pyproject nuevo YA en su sitio. Lo que sí se puede comprobar sobre el árbol de
# ensayo, sin nada instalado y sin destruir nada, es que TODO el código nuevo
# PARSEA. Un error de sintaxis en cualquier módulo del supervisor deja al
# gabinete en crash-loop, y hasta hoy ese fallo no lo veía nadie: el gate viejo
# sólo importaba lgpio y awsiot, que ni siquiera viajan en el rsync.
#
# Se compila con el intérprete DEL VENV cuando existe, no con el `python3` del
# sistema: en el Pi (Debian 13) el del sistema es 3.13 y el del venv 3.12, y
# sintaxis válida en uno puede no serlo en el otro. Un pre-vuelo que compila con
# el intérprete equivocado es un gate que dice OK sobre algo que no arranca —
# justo el defecto que este bloque existe para no repetir. Sin venv todavía
# (gabinete recién aprovisionado) cae al del sistema, que es mejor que nada.
PY_PREVUELO="${VIVO}/.venv/bin/python"
[ -x "$PY_PREVUELO" ] || PY_PREVUELO="python3"

# [T-2.70.a·D3·m5] LA IDENTIDAD, ANTES QUE EL CÓDIGO. Las dos unidades declaran
# `EnvironmentFile=/etc/takab/edge.env` **sin el prefijo `-`**, o sea que sin ese
# archivo NINGUNA arranca. Es la dirección correcta y está anclada en
# `test_ninguna_unidad_TOLERA_arrancar_sin_la_identidad_del_gabinete`: la
# alternativa (`-EnvironmentFile`) dejaría al DUEÑO DE LOS PINES arrancar con los
# defaults de código —el mapa de `GpioPins` incluido— y energizar los pines
# EQUIVOCADOS de un gabinete cableado, en silencio y con la unidad en verde.
#
# Lo que este bloque añade es DECIRLO A TIEMPO. Sin él, el despliegue instalaba
# las unidades, reiniciaba y el operador se enteraba 45 s después con «NADIE
# reclamó los pines» — un diagnóstico que apunta al cerrojo cuando lo que falta
# es el archivo de identidad. Va en el pre-vuelo porque aquí todavía no se ha
# destruido nada.
# CON SUDO, y no es un detalle: en un gabinete real este archivo es `0600
# root:root` —lleva la clave HMAC y el PIN del panel— y este bloque corre como el
# usuario de despliegue, igual que `sudo install` y `sudo systemctl` de más abajo.
# Leerlo a pelo daba `Permission denied` y el pre-vuelo concluía «este gabinete no
# tiene identidad», abortando TODO despliegue a un gabinete de verdad. Y el daño
# peor estaba detrás del guard: la lectura de `TAKAB_EDGE_GPIO_OWNER` habría
# fallado igual de callada y caído al default `edge`, con lo que en un gabinete D3
# el despliegue DESHABILITA `takab-gpio` y lo deja sin dueño de pines tras el
# siguiente reinicio. Medido contra `gw-dev-0001` el 2026-08-09.
if ! sudo -n test -r "$ENTORNO" 2>/dev/null; then
  if sudo -n test -e "$ENTORNO" 2>/dev/null; then
    echo "✗ ABORTADO EN PRE-VUELO: la identidad de este gabinete existe en" >&2
    echo "  ${ENTORNO} pero NI SIQUIERA CON SUDO se puede leer." >&2
    echo "  Revisa permisos/propietario (esperado: 0600 root:root) y el sudoers" >&2
    echo "  del usuario de despliegue. NADA se ha destruido." >&2
    exit 1
  fi
  echo "✗ ABORTADO EN PRE-VUELO: este gabinete no tiene identidad legible en" >&2
  echo "  ${ENTORNO}." >&2
  echo "  Las dos unidades lo declaran EnvironmentFile= SIN '-', así que ninguna" >&2
  echo "  arrancaría: ni el dueño de los pines ni el supervisor. Un dueño que" >&2
  echo "  arrancara sin este archivo lo haría con el MAPA DE PINES por defecto." >&2
  echo "  NADA se ha destruido: el árbol vivo (${VIVO}) sigue intacto." >&2
  echo "  Instálalo con infra/scripts/provision_gateway.sh (FUSIONA, no pisa" >&2
  echo "  las claves que el gabinete ya tenga) y vuelve a desplegar." >&2
  exit 1
fi

# QUIÉN es el dueño de los pines de ESTE gabinete. `tail -1` porque
# `EnvironmentFile=` tiene la semántica de siempre en esta casa —gana la
# ÚLTIMA—, la misma que ya rige para el registro del cerrojo, para systemd y
# para bash; leer la primera habilitaría la unidad equivocada. Vacío ⇒ `edge`,
# que es el default de `EdgeSettings.gpio_owner` y el estado de todo gabinete
# desplegado hasta hoy.
# `sudo -n` por lo mismo que el guard de arriba: el archivo es 0600 root:root. Un
# fallo de lectura aquí NO puede quedar en silencio —caería al default `edge` y
# deshabilitaría al dueño dedicado de un gabinete D3—, así que el guard de arriba
# ya garantizó que se puede leer antes de llegar aquí.
DUENO_CONFIGURADO="$(sudo -n sed -n 's/^[[:space:]]*TAKAB_EDGE_GPIO_OWNER=//p' "$ENTORNO" |
  tail -1 | tr -d "\"' " || true)"
[ -n "$DUENO_CONFIGURADO" ] || DUENO_CONFIGURADO=edge
echo "→ dueño de los pines declarado por ${ENTORNO}: ${DUENO_CONFIGURADO}"

echo "→ pre-vuelo: compilando el código recién copiado (nada activado todavía)"
if ! "$PY_PREVUELO" -m compileall -q "${NUEVA}/takab_edge" "${NUEVA}/simulators" >/dev/null; then
  echo "✗ ABORTADO EN PRE-VUELO: el código nuevo no compila." >&2
  # [T-2.70] ESTE MENSAJE YA NO TIENE LETRA PEQUEÑA. Con el despliegue in-place
  # había que distinguir «no se reinició» de «el disco ya tiene el código nuevo
  # sin verificar», porque el próximo arranque lo habría ejecutado. Con A/B la
  # release rechazada es INERTE: nadie la apunta, ni ahora ni tras un corte de
  # luz.
  echo "  El gabinete NO se ha tocado: ${VIVO} sigue apuntando a la release" >&2
  echo "  anterior y ningún arranque ejecutará ésta. Estado seguro." >&2
  echo "  La release rechazada quedó en ${NUEVA} para inspección." >&2
  exit 1
fi

# --- 3. MIGRACIÓN AL LAYOUT A/B (una sola vez por gabinete) ------------------
# Todo gabinete desplegado hasta T-2.70 tiene `${RAIZ}/edge` como DIRECTORIO de
# verdad. El layout A/B lo necesita como SYMLINK, y ese cambio no es un detalle
# de disco: cambia el ARRANQUE DEL CAMINO DE VIDA, porque es la ruta que los
# `ExecStart` de las dos unidades nombran.
#
# Por eso la migración EXIGE ventana declarada, y por dos razones distintas:
#   · entre el `mv` del directorio y el `mv -T` del symlink hay un hueco de
#     milisegundos en que `${RAIZ}/edge` NO EXISTE. Un import perezoso del
#     proceso vivo justo ahí lo tumba (y `Restart=always` lo repone, con lo que
#     eso cuesta en un gabinete cuyo dueño de pines sea `takab-edge`);
#   · el árbol heredado se conserva como release para poder VOLVER a él, y
#     estrenarlo exige un reinicio que resuelva la ruta nueva.
#
# El árbol heredado se copia ENTERO —incluido su `.venv`— y no se poda: es la
# única vuelta atrás que este gabinete tiene el día de su primera activación
# A/B, y ofrecer una que no existe es el defecto que este script ya corrigió una
# vez para `edge.prev`.
if [ -e "$VIVO" ] && [ ! -L "$VIVO" ]; then
  if [ "$VENTANA" != 1 ]; then
    echo "✗ ABORTADO: este gabinete todavía tiene ${VIVO} como DIRECTORIO." >&2
    echo "  Migrarlo al layout A/B cambia la ruta desde la que arrancan las dos" >&2
    echo "  unidades, así que no se hace sin ventana: vuelve a lanzar con" >&2
    echo "  --ventana-de-mantenimiento, con el edificio avisado." >&2
    echo "  La release nueva ya está en ${NUEVA} y es inerte: no se pierde nada." >&2
    exit 1
  fi
  HEREDADA="${RELEASES}/heredada-$(date -u +%Y%m%dT%H%M%SZ)"
  echo "→ MIGRACIÓN A/B: conservando el árbol vivo como ${HEREDADA}"
  mkdir -p "${HEREDADA}/edge" "${HEREDADA}/shared/schemas"
  rsync -a "${VIVO}/" "${HEREDADA}/edge/"
  [ -d "${RAIZ}/shared/schemas" ] &&
    rsync -a "${RAIZ}/shared/schemas/" "${HEREDADA}/shared/schemas/"
  mv -T "$VIVO" "${RAIZ}/edge.premigracion"
  ln -sfn "${HEREDADA}/edge" "${VIVO}.nuevo"
  mv -T "${VIVO}.nuevo" "$VIVO"
  # El original ya está copiado y el symlink resuelve a la copia, así que los
  # `sys.path` del proceso vivo —que nombran `${RAIZ}/edge` literalmente—
  # vuelven a resolver. Se borra para no dejar dos copias en una microSD.
  rm -rf "${RAIZ}/edge.premigracion"
fi

# ¿HAY VUELTA ATRÁS? Con A/B la pregunta ya no es «¿se tomó instantánea?» sino
# «¿a qué release apunta el symlink AHORA y sigue entera?». Se responde antes de
# tocar nada, porque de ella depende el mensaje que el operador se lleva.
RELEASE_ANTERIOR="$(readlink "$VIVO" 2>/dev/null || true)"
if [ -n "$RELEASE_ANTERIOR" ] && [ -x "${RELEASE_ANTERIOR}/.venv/bin/takab-edge" ]; then
  HAY_INSTANTANEA=1
else
  echo "  (primer despliegue A/B de este gabinete: no hay release anterior completa)"
  HAY_INSTANTANEA=0
fi

echo "→ marcando la versión desplegada (FW_VERSION=${FW_VERSION})"
printf '%s\n' "$FW_VERSION" > "${NUEVA}/FW_VERSION"

# [T-2.70·CAMPO 2026-08-23] DÓNDE INSTALA `uv` SU INTÉRPRETE, Y POR QUÉ ES UN
# ASUNTO DEL CAMINO DE VIDA.
#
# Las dos unidades declaran `ProtectHome=true`, o sea que para ellas `/home`,
# `/root` y `/run/user` NO EXISTEN. Un venv cuyo `bin/python` sea un symlink a
# `~/.local/share/uv/python/...` arranca perfectamente desde una sesión ssh y
# muere con **203/EXEC — No such file or directory** cuando lo lanza systemd: el
# ejecutable existe, el que no existe (en ese namespace) es su intérprete.
#
# ESTO PASÓ DE VERDAD, la primera noche del layout A/B. Hasta entonces el venv
# del Pi era UNO y se reusaba desde julio, con su intérprete en
# `/opt/takab/.python` porque alguien exportó esta variable A MANO aquella vez.
# El hecho sobrevivía en un directorio y en ningún archivo. Con A/B cada release
# estrena venv, así que `uv` tuvo que elegir intérprete por primera vez en meses
# — y se lo instaló en `$HOME`. El gabinete quedó SIN DUEÑO DE PINES: sin
# sirena, sin cierre de gas y sin retenedores, con las dos unidades ciclando.
#
# `ssh host "bash -s"` es un shell NO interactivo y NO de login: no lee
# `.profile` ni `.bashrc`, así que ninguna variable del usuario llega aquí. Por
# eso se declara AQUÍ, en el único sitio que gobierna todos los despliegues.
export UV_PYTHON_INSTALL_DIR="${TAKAB_UV_PYTHON_DIR:-}"
[ -n "$UV_PYTHON_INSTALL_DIR" ] || export UV_PYTHON_INSTALL_DIR=/opt/takab/.python

# Lo que `ProtectHome=true` le quita a las dos unidades. Es una VARIABLE por la
# misma razón que `TAKAB_REMOTE_ROOT`: el sandbox de edge/tests/test_deploy_sh.py
# no puede montar un `/home` de mentira, y sin poder apuntar el gate a un prefijo
# suyo no habría forma de demostrar que muerde. En producción nadie la exporta y
# valen los tres prefijos reales, anclados por texto en
# test_deploy_artifacts.py::test_el_gate_del_interprete_vigila_lo_que_ProtectHome_oculta
# — para que la costura no pueda perder los dientes en silencio.
RUTAS_OCULTAS="${TAKAB_DEPLOY_RUTAS_OCULTAS:-}"
[ -n "$RUTAS_OCULTAS" ] || RUTAS_OCULTAS="/home /root /run/user"

cd "$NUEVA"
# takab-edge corre como root y deja __pycache__ de root DENTRO del venv; sin
# esto, el uv sync del usuario falla con Permission denied en cada deploy. En
# una release RECIÉN creada no hay venv todavía y esto es un no-op; sigue
# haciendo falta para el caso en que un despliegue anterior abortara a mitad y
# dejara la release a medio construir.
[ -d .venv ] && sudo chown -R "$USER":"$USER" .venv
# --- 4. Extras del Pi real (ver EDGE_EXTRAS arriba). `uv sync` PODA lo que no
# esté en el set: sincronizar de menos desinstala, no es un no-op.
# shellcheck disable=SC2086
uv sync ${EDGE_EXTRA_FLAGS} --quiet

# --- 5. GATE: EL CÓDIGO DESPLEGADO ARRANCA (antes de tocar el proceso que actúa)
# Esto es lo único que separa un despliegue roto de un gabinete muerto.
#
# Se comprueban DOS cosas, y la segunda es la que el gate viejo no miraba:
#
#   a) `lgpio` y `awsiot` — dependencias de TERCEROS del venv. `gpio` es
#      `critical=True` y el supervisor hace fail-fast: si `lgpio` no importa
#      —justo lo que deja un `uv sync` mal invocado o cortado por un enlace
#      flaco— el proceso crashea AL ARRANCAR.
#
#   b) `takab_edge.supervisor` y `takab_edge.gpio.__main__` — EL CÓDIGO QUE
#      ACABA DE VIAJAR. Son exactamente los dos entry points que ejecutan los
#      ExecStart de takab-edge.service y takab-gpio.service, y su import
#      arrastra el grafo entero de submódulos del supervisor. Importarlos es lo
#      mínimo que demuestra que el árbol nuevo es ARRANCABLE, y no toca hardware
#      ni nube: la pin factory se fija en `_on_start` y el transporte MQTT se
#      construye en `build()`, ninguno al importar.
#
# El gate viejo era `import lgpio, awsiot` a secas: dos paquetes que el rsync
# EXCLUYE del despliegue, o sea un gate que no podía fallar por culpa del código
# desplegado. Era ciego justo a lo que debía verificar.
echo "→ GATE DEL CÓDIGO DESPLEGADO (antes de reiniciar)"
if ! .venv/bin/python -c 'import lgpio, awsiot' 2>&1; then
  echo "✗ ABORTADO: el venv no puede importar lgpio y/o awsiot." >&2
  FALLO_GATE="dependencias del venv (revisa el 'uv sync': ¿red? ¿extras?)"
elif ! .venv/bin/python -c 'import takab_edge.supervisor, takab_edge.gpio.__main__, takab_edge.pinlink.cli' 2>&1; then
  echo "✗ ABORTADO: el CÓDIGO DESPLEGADO no importa." >&2
  FALLO_GATE="el árbol recién copiado (los ExecStart de las unidades no arrancarían)"
elif [ ! -x .venv/bin/takab-edge ] || [ ! -x .venv/bin/takab-gpio ] || [ ! -x .venv/bin/takab-gpioctl ]; then
  echo "✗ ABORTADO: faltan los ejecutables que lanzan las unidades systemd." >&2
  FALLO_GATE="los console scripts .venv/bin/takab-{edge,gpio,gpioctl}"
elif [ -n "$(
  INTERPRETE="$(readlink -f .venv/bin/python 2>/dev/null || true)"
  if [ -z "$INTERPRETE" ]; then echo oculto; fi
  for _pref in $RUTAS_OCULTAS; do
    case "$INTERPRETE" in "${_pref}"/*) echo oculto ;; esac
  done
)" ]; then
  # [T-2.70·CAMPO] EL GATE QUE FALTABA, y que ningún test en verde podía dar.
  # Los tres gates anteriores corren como el usuario del despliegue, con /home
  # ENTERO visible: por construcción no pueden ver el único fallo que mató al
  # gabinete la primera noche del layout A/B. Un venv es "importable" aquí y
  # 203/EXEC allí, porque `ProtectHome=true` le quita a las unidades justo el
  # directorio donde `uv` había puesto el intérprete.
  #
  # Se comprueba la RUTA RESUELTA y no el symlink: lo que systemd tiene que
  # poder abrir es el binario final.
  echo "✗ ABORTADO: el intérprete del venv vive donde las unidades NO pueden verlo." >&2
  FALLO_GATE="$(readlink -f .venv/bin/python 2>/dev/null || echo '(ilegible)') — ProtectHome=true oculta /home, /root y /run/user"
else
  FALLO_GATE=""
fi

if [ -n "$FALLO_GATE" ]; then
  # [T-2.70] EL ESTADO QUE ESTE MENSAJE DESCRIBE CAMBIÓ, Y A MEJOR. Con el
  # despliegue in-place había que avisar de que «el disco ya tiene el código
  # nuevo sin verificar» y de que el próximo corte de luz lo ejecutaría. Con
  # A/B la release que acaba de fallar el gate es INERTE: nadie la apunta.
  echo "  Causa: ${FALLO_GATE}" >&2
  echo "" >&2
  echo "  ESTADO DEL GABINETE: intacto." >&2
  echo "  · ${VIVO} sigue apuntando a ${RELEASE_ANTERIOR:-(nada)}." >&2
  echo "  · La release ${RELEASE_ID} NO se activó y ningún arranque la ejecutará." >&2
  echo "  · No hay nada que revertir: el gabinete nunca llegó a estrenarla." >&2
  echo "" >&2
  if [ "$HAY_INSTANTANEA" != 1 ]; then
    # El caso que sí sigue siendo malo: un gabinete que TODAVÍA no tiene una
    # release completa a la que apuntar. No es que el despliegue haya dejado
    # algo peor — es que no había nada antes.
    echo "  OJO: este gabinete no tiene ninguna release anterior completa, así" >&2
    echo "  que sigue SIN código bueno. Despliega un commit sano antes de irte." >&2
  fi
  echo "  La release rechazada queda en ${NUEVA} para inspección." >&2
  exit 1
fi

# --- 6. Unidades + habilitación del dueño + reinicio -------------------------
sudo install -m 0644 systemd/takab-edge.service systemd/takab-gpio.service /etc/systemd/system/
sudo systemctl daemon-reload

# [T-2.70.a·D3·B2] 6.a — QUE LA UNIDAD DEL DUEÑO EXISTA PARA SYSTEMD.
#
# Hasta aquí el script instalaba LAS DOS unidades, hacía `daemon-reload` y
# reiniciaba `takab-edge`, y nada más. Sin un solo `enable`, un gabinete
# provisionado con `TAKAB_EDGE_GPIO_OWNER=gpio` quedaba así: `takab-edge` ya no
# instancia su `GpioController`, `takab-gpio` no está habilitada, y al próximo
# corte de luz el Pi arranca SIN DUEÑO DE PINES — un edificio sin sirena, sin
# cierre de gas, sin retorno de ascensores y sin retenedores.
#
# `enable` y `disable` son symlinks: no arrancan, no detienen y NO TOCAN UN PIN.
# Por eso se pueden hacer en cualquier despliegue, en las dos direcciones.
if [ "$DUENO_CONFIGURADO" = gpio ]; then
  # Los dos van con `|| echo`, y no es descuido: EL VEREDICTO LO DA EL PASO 7,
  # que MIDE quién sostiene el cerrojo. Dejar que `set -e` abortara aquí cambiaría
  # una comprobación medida por el código de salida de `systemctl` —que dice
  # «no arrancó», no «el gabinete no protege»— y encima dejaría al cliente sin
  # reiniciar con el disco ya cambiado. Además el dueño tiene `Restart=always` +
  # `StartLimitIntervalSec=0`: un fallo transitorio se cura solo, y uno
  # permanente lo delata el paso 7 con el diagnóstico bueno.
  sudo systemctl enable takab-gpio ||
    echo "⚠ no se pudo HABILITAR takab-gpio; el paso 7 dirá si hay dueño" >&2
  # `start` y NO `restart`: sobre un dueño ya vivo, `start` es un no-op y no
  # mueve un solo pin; `restart` costaría un ciclo eléctrico de GAS_VALVE y
  # DOOR_RETAINER en CADA despliegue, que es exactamente el coste que D3 existe
  # para eliminar. Lo que este `start` sí arregla es el gabinete donde el dueño
  # todavía no ha corrido nunca: ahí los pines no los tiene nadie y arrancarlo
  # no es un ciclo, es pasar de «sin protección» a «protegido».
  #
  # Va ANTES del `restart takab-edge` por el `After=takab-gpio.service` de la
  # unidad: el cliente no debe estrenar su socket contra un dueño que aún no ató
  # la puerta.
  sudo systemctl start takab-gpio ||
    echo "⚠ no se pudo ARRANCAR takab-gpio; el paso 7 dirá si hay dueño" >&2
elif systemctl is-enabled takab-gpio >/dev/null 2>&1; then
  # El caso contrario, y no es teórico: un sitio que probó D3 y devolvió
  # `TAKAB_EDGE_GPIO_OWNER` a `edge` se queda con la unidad del dueño dedicado
  # HABILITADA. No pasa nada hasta el siguiente corte de luz; entonces arrancan
  # las dos, gana `takab-gpio` (por el `After=` de takab-edge) y el supervisor
  # cicla contra el cerrojo PARA SIEMPRE: sin nube, sin SeedLink y sin panel.
  # Eléctricamente mudo (D1.1) y operativamente ciego.
  #
  # Se DESHABILITA, no se detiene: detener sí sería actuación física, y encima
  # sobre el proceso que en ese momento puede tener los pines.
  echo "⚠ takab-gpio estaba HABILITADA en un gabinete cuyo ${ENTORNO} declara" >&2
  echo "  TAKAB_EDGE_GPIO_OWNER=${DUENO_CONFIGURADO}. Al próximo arranque en frío" >&2
  echo "  las dos unidades reclamarían el mismo cerrojo y takab-edge quedaría en" >&2
  echo "  crash-loop (sin nube, sin SeedLink, sin panel). Se deshabilita el" >&2
  echo "  symlink; NO se detiene nada: detenerla movería gas y retenedores." >&2
  sudo systemctl disable takab-gpio
fi

# [T-2.70.a·D3·B2] 6.b — EL REINICIO DEL DUEÑO VA EN VENTANA DECLARADA.
#
# Reiniciar al dueño de los pines cuesta un ciclo eléctrico de gas y retenedores
# más una ventana sin sirena. Hacerlo en cada despliegue devolvería el coste que
# D3 acaba de quitar, sólo que cambiando de proceso; no hacerlo NUNCA deja al
# dueño con el código anterior indefinidamente. La salida no es elegir a ciegas
# por el operador: es que lo declare, y que el paso 7 se niegue a decir ✓ si no
# lo hizo y hacía falta.
# [T-2.70] 6.c — LA ACTIVACIÓN LA HACE EL CANARY, NO ESTE SCRIPT.
#
# Aquí había un `systemctl restart takab-edge` a secas, y con él el despliegue
# terminaba en el instante en que systemd forkeaba el proceso. Un proceso que
# arranca y crashea al segundo 4 se declaraba bueno y el operador se iba del
# sitio con el gabinete ciclando. `${RAIZ}/bin/canary.sh` repunta el symlink,
# reinicia al CLIENTE, mide salud sostenida —unidad activa, MainPID sin
# relevo, pines con dueño, panel contestando— y vuelve atrás solo si falla.
#
# Vive fuera de toda release a propósito: si la versión nueva no arranca, el
# reversor no puede ser parte de ella.
MARCA_ACTIVACION="$(date +%s)"
# `--atendido` porque esto lo lanzó una persona por ssh y está leyendo esta
# salida: en un gabinete cuyo dueño de pines siga siendo `takab-edge`, el canary
# AVISA del ciclo de gas y retenedores y sigue, que es lo que este script ya
# hacía antes de la ficha. Un comando firmado de la nube NO pasa esta bandera, y
# allí el mismo gabinete exige ventana declarada.
ARGS_CANARY=(activar "$RELEASE_ID" --atendido)
[ "$VENTANA" = 1 ] && ARGS_CANARY+=(--ventana-de-mantenimiento)
ESTADO_CANARY=0
sudo -n env \
  TAKAB_REMOTE_ROOT="$RAIZ" \
  TAKAB_CANARY_ESTADO="${TAKAB_CANARY_ESTADO:-/var/lib/takab/canary}" \
  TAKAB_EDGE_GPIO_LOCK_PATH="${TAKAB_EDGE_GPIO_LOCK_PATH:-/var/lib/takab/gpio.lock}" \
  TAKAB_EDGE_ENV_FILE="$ENTORNO" \
  "${RAIZ}/bin/canary.sh" "${ARGS_CANARY[@]}" || ESTADO_CANARY=$?

case "$ESTADO_CANARY" in
0) : ;; # activada y sana
2)
  echo "✗ DESPLIEGUE NO VERIFICADO: el canary no pudo MEDIR la salud." >&2
  echo "  La release ${RELEASE_ID} quedó puesta y NO se declara buena." >&2
  exit 1
  ;;
*)
  echo "✗ DESPLIEGUE REVERTIDO: la release ${RELEASE_ID} no pasó el canary." >&2
  echo "  Veredicto: $(sudo -n cat "${TAKAB_CANARY_ESTADO:-/var/lib/takab/canary}/veredicto.json" 2>/dev/null || echo '(ilegible)')" >&2
  echo "  Diagnóstico: journalctl -u takab-edge -n 80 --no-pager" >&2
  exit 1
  ;;
esac

# 6.d — EL DUEÑO DE LOS PINES, SÓLO EN VENTANA Y SÓLO DESPUÉS.
#
# Va DESPUÉS de la activación y no antes, al revés que en el layout in-place:
# el `ExecStart` del dueño resuelve por el mismo symlink, así que reiniciarlo
# antes del repunte lo dejaría estrenando la versión VIEJA — un ciclo de gas y
# retenedores a cambio de nada. Y va después del canary y no en paralelo porque
# si la release nueva no pasa el remojo no hay ninguna razón para tocar los
# pines: la vuelta atrás ya ocurrió y el dueño sigue con el código bueno.
if [ "$DUENO_CONFIGURADO" = gpio ] && [ "$VENTANA" = 1 ]; then
  echo "→ VENTANA DE MANTENIMIENTO declarada: reiniciando al DUEÑO DE LOS PINES"
  echo "  (esto CICLA GAS_VALVE y DOOR_RETAINER y abre una ventana sin sirena;"
  echo "   se hace aquí y no a mano para que caiga bajo la verificación del paso 7)"
  sudo systemctl restart takab-gpio
fi

# 6.e — PODA. Un gabinete con microSD no puede acumular releases con su venv.
# Se conservan las `TAKAB_DEPLOY_RELEASES_VIVAS` más recientes, y ADEMÁS —pase
# lo que pase— la activa y la anterior: son las dos que una vuelta atrás
# necesita, y podarlas convertiría la poda en el defecto que el canary existe
# para evitar. La release que acaba de fallar un canary tampoco se borra aquí:
# es la evidencia.
RETENCION="${TAKAB_DEPLOY_RELEASES_VIVAS:-3}"
ACTIVA_AHORA="$(readlink "$VIVO" 2>/dev/null || true)"
ls -1dt "${RELEASES}"/*/ 2>/dev/null | tail -n +$((RETENCION + 1)) | while read -r vieja; do
  vieja="${vieja%/}"
  case "$ACTIVA_AHORA" in "${vieja}/edge") continue ;; esac
  case "$RELEASE_ANTERIOR" in "${vieja}/edge") continue ;; esac
  # [T-2.70·CAMPO 2026-08-23] LA HEREDADA NO SE PODA NUNCA, y la razón es que la
  # RECENCIA es el criterio equivocado para ella. Es el árbol que este gabinete
  # llevaba corriendo ANTES de que existiera el layout A/B: meses de operación
  # real detrás, y la única versión de la que se sabe que este edificio sobrevive
  # a un corte de luz. Todas las releases nuevas son, por definición, más
  # recientes que ella, así que una poda por fecha se la lleva la primera — y
  # eso pasó la misma noche del estreno: tres releases en disco, todas del mismo
  # día, y ninguna con historia. Ocupa un venv; la red de seguridad vale más.
  case "${vieja##*/}" in heredada-*) continue ;; esac
  echo "  podando release antigua: ${vieja}"
  rm -rf "$vieja"
done

# --- 7. VERIFICACIÓN: ¿QUIÉN ES DUEÑO DE LOS PINES? --------------------------
# [T-2.70.a·D1.5] Aquí decía `systemctl is-active takab-edge`, y eso mide EL
# PROCESO EQUIVOCADO por construcción: comprueba que una unidad CON NOMBRE PROPIO
# esté arriba, no que alguien esté sosteniendo el GPIO del gabinete. El día que
# `takab-edge` deje de tocar los pines —que es literalmente el objetivo de
# T-2.70.a— esa línea seguiría saliendo verde con la sirena sin dueño. Y ni
# siquiera hoy distingue «arrancó y protege» de «arrancó y `gpio` no pudo tomar
# los pines»: `is-active` sale `active` en los dos casos.
#
# El cerrojo de propiedad (T-2.70.a·D1.1) da la prueba DIRECTA: quien tiene los
# pines sostiene un `flock` EXCLUSIVO sobre este archivo y deja escrito dentro su
# PID y su unidad. Así que aquí no se nombra ninguna unidad: se PREGUNTA quién
# manda, y por eso esta verificación sobrevive intacta al día en que la respuesta
# pase a ser `takab-gpio`.
#
# `TAKAB_EDGE_GPIO_LOCK_PATH` es el mismo seam que `TAKAB_REMOTE_ROOT`: en
# producción nadie lo exporta y vale el default, que es lo que
# `EdgeSettings.gpio_lock_file` resuelve para un gabinete (`dev_mode=false`) —
# dentro de /var/lib/takab, que es `WorkingDirectory=` y `ReadWritePaths=` de
# LAS DOS unidades.
CERROJO="${TAKAB_EDGE_GPIO_LOCK_PATH:-/var/lib/takab/gpio.lock}"
PLAZO="${TAKAB_DEPLOY_PLAZO_PROPIEDAD:-45}"

# [T-2.70.a·D1·MENOR-1] SE SONDEA, NO SE DUERME. Aquí había un `sleep 3` tras el
# `systemctl restart` y UN SOLO disparo del veredicto. Eso medía bien mientras lo
# verificado era «systemd forkeó el proceso» —satisfecho en t≈0—, pero desde
# D1.5 lo verificado es «`gpio._on_start` corrió su primera sentencia», que llega
# DESPUÉS del intérprete, de numpy/scipy y de `supervisor.build()`. Con el mismo
# plazo y sin reintento, un gabinete SANO que tarde 4 s se reportaba como «NADIE
# es dueño de los pines… el gabinete NO está protegiendo».
#
# Ese falso rojo es el daño de segundo orden más caro del script: empuja al
# operador a revertir, revertir es reiniciar, y reiniciar mueve GAS_VALVE y
# DOOR_RETAINER (la lección que este mismo archivo documenta arriba); y entrena a
# ignorar la ÚNICA comprobación que dice si la sirena tiene dueño. Medido
# exec→cerrojo: 0.60 s en x86/dev y ~1.0 s con los imports de producción — el
# margen en el Pi 4 no es medible sin el Pi, y ése es justo el argumento para
# SONDEAR en vez de subir la constante a ciegas.
#
# El veredicto es EL MISMO de antes; lo único que cambia es que se re-pregunta
# hasta que haya dueño o hasta agotar el plazo, y los mensajes de abajo pasan a
# ser los de la rama de AGOTAMIENTO. Dos matices que no son de tiempo:
#   · «no se pudo interrogar el cerrojo» sale del bucle EN EL ACTO: que falte
#     util-linux o no exista /var/lib/takab no se arregla esperando 45 s.
#   · el registro (que es informativo, ver abajo) sólo se re-lee durante una
#     GRACIA corta desde que el cerrojo aparece tomado, porque lo único que
#     puede tardar ahí es el hueco de microsegundos entre el `flock` y el
#     `pwrite` de `gpio._registrar_dueno`. Su causa realista —ENOSPC— es
#     permanente, y su desenlace es un AVISO, no un aborto: esperar no compra
#     nada y alargaría cada despliegue sobre un disco lleno.
GRACIA_REGISTRO=2
INICIO_ESPERA=$SECONDS
TOMADO_EN=""
ESTADO_CERROJO=0
DUENO_PID=""
DUENO_UNIDAD=""
PROPIEDAD=""

while : ; do
  # El síntoma más probable de un arranque que murió antes de `gpio`: el archivo
  # ni existe. Se distingue del resto porque el diagnóstico es distinto (no es
  # «se soltó», es «nunca llegó a reclamarse»), y porque `flock` lo CREARÍA y
  # borraría la pista.
  if [ ! -e "$CERROJO" ]; then
    PROPIEDAD=sin_archivo
  else
    # `flock -n -E 9`: 9 = «está tomado» (lo que queremos), 0 = «lo tomé yo, o
    # sea que NADIE lo tenía», cualquier otro = no se pudo interrogar. Los tres
    # casos son distintos y ninguno puede confundirse con los otros.
    ESTADO_CERROJO=0
    flock -n -E 9 "$CERROJO" true || ESTADO_CERROJO=$?

    if [ "$ESTADO_CERROJO" = 0 ]; then
      PROPIEDAD=libre
    elif [ "$ESTADO_CERROJO" != 9 ]; then
      PROPIEDAD=ilegible
    else
      [ -n "$TOMADO_EN" ] || TOMADO_EN=$SECONDS
      # El cerrojo está tomado. El registro dice POR QUIÉN. `tail -1` porque gana
      # la última línea, igual que en systemd y en bash: un relevo que escribiera
      # un registro más corto sobre uno más largo dejaría cola del dueño ANTERIOR
      # y con `head -1` se reportaría al que ya no manda. `|| true` porque un
      # registro que no se puede ni leer es el caso de abajo, no un fallo del
      # `set -e`.
      DUENO_PID="$(sed -n 's/^pid=//p' "$CERROJO" 2>/dev/null | tail -1 || true)"
      DUENO_UNIDAD="$(sed -n 's/^unit=//p' "$CERROJO" 2>/dev/null | tail -1 || true)"

      # `/proc` y no `kill -0`: el proceso corre como root y el usuario del
      # deploy no, así que `kill -0` daría EPERM y abortaría un despliegue sano.
      if [ -n "$DUENO_PID" ] && [ ! -d "/proc/${DUENO_PID}" ]; then
        PROPIEDAD=pid_fantasma
      elif [ -z "$DUENO_PID" ] || [ -z "$DUENO_UNIDAD" ]; then
        PROPIEDAD=registro_mudo
      elif ! systemctl is-active "$DUENO_UNIDAD" >/dev/null 2>&1; then
        # Que la unidad que DICE ser dueña esté viva para systemd: si los pines
        # los sostiene un proceso suelto (un `python -m takab_edge.gpio` de una
        # sesión SSH), el gabinete no sobrevive al próximo reinicio y esto tiene
        # que salir en rojo. Se interroga a `$DUENO_UNIDAD` y JAMÁS a un nombre
        # escrito aquí: el día del criterio 1 de T-2.70.a los pines pasan a
        # `takab-gpio` mientras `takab-edge` sigue activa haciendo todo lo demás,
        # y preguntar por el nombre viejo declararía ✓ midiendo a un proceso que
        # ya no toca el GPIO.
        PROPIEDAD=unidad_muerta
      else
        PROPIEDAD=con_dueno
      fi
    fi
  fi

  ESPERADO=$(( SECONDS - INICIO_ESPERA ))
  if [ "$PROPIEDAD" = con_dueno ] || [ "$PROPIEDAD" = ilegible ]; then
    break
  fi
  if [ "$PROPIEDAD" = registro_mudo ] &&
     [ $(( SECONDS - TOMADO_EN )) -ge "$GRACIA_REGISTRO" ]; then
    break
  fi
  if [ "$ESPERADO" -ge "$PLAZO" ]; then
    break
  fi
  sleep 0.25
done

case "$PROPIEDAD" in
sin_archivo)
  echo "✗ DESPLIEGUE NO VERIFICADO: NADIE reclamó los pines — el cerrojo" >&2
  echo "  ${CERROJO} ni siquiera existe tras esperar ${ESPERADO} s. Ningún" >&2
  echo "  proceso del edge llegó a la primera línea de gpio._on_start desde" >&2
  echo "  el reinicio." >&2
  echo "  Diagnóstico: journalctl -u takab-edge -u takab-gpio -n 50 --no-pager" >&2
  exit 1
  ;;
libre)
  echo "✗ DESPLIEGUE NO VERIFICADO: NADIE es dueño de los pines." >&2
  echo "  Tras esperar ${ESPERADO} s el cerrojo ${CERROJO} está LIBRE, así que" >&2
  echo "  ningún proceso vivo sostiene el GPIO: el gabinete NO está protegiendo" >&2
  echo "  (ni sirena, ni gas, ni retenedores). La unidad puede estar 'active' y" >&2
  echo "  aun así ser cierto — por eso esto ya no se comprueba con" >&2
  echo "  'systemctl is-active'." >&2
  echo "  Diagnóstico: journalctl -u takab-edge -u takab-gpio -n 50 --no-pager" >&2
  exit 1
  ;;
ilegible)
  echo "✗ DESPLIEGUE NO VERIFICADO: no se pudo interrogar el cerrojo ${CERROJO}" >&2
  echo "  (flock salió ${ESTADO_CERROJO}). Sin poder medir la propiedad de los" >&2
  echo "  pines, este despliegue no se declara bueno: ¿existe /var/lib/takab?" >&2
  echo "  ¿está util-linux instalado?" >&2
  exit 1
  ;;
pid_fantasma)
  echo "✗ DESPLIEGUE NO VERIFICADO: el registro de ${CERROJO} nombra al pid" >&2
  echo "  ${DUENO_PID}, que no existe. El cerrojo lo sostiene otro proceso: el" >&2
  echo "  gabinete no está en un estado que se pueda declarar bueno." >&2
  exit 1
  ;;
unidad_muerta)
  echo "✗ DESPLIEGUE NO VERIFICADO: los pines los tiene '${DUENO_UNIDAD}'" >&2
  echo "  (pid ${DUENO_PID}), y systemd NO la da por activa tras ${ESPERADO} s." >&2
  echo "  El edificio está protegido AHORA, pero por algo que systemd no" >&2
  echo "  gobierna: el gabinete no sobrevive al próximo reinicio — ni a que se" >&2
  echo "  cierre la sesión SSH que lo lanzó. Salidas: reiniciar la unidad que" >&2
  echo "  debe tener los pines, o matar al proceso suelto y dejar que arranque" >&2
  echo "  la unidad (OJO: eso mueve GAS_VALVE y DOOR_RETAINER)." >&2
  echo "  Diagnóstico: systemctl status '${DUENO_UNIDAD}'; ps -o pid,cmd -p ${DUENO_PID}" >&2
  exit 1
  ;;
esac

# [T-2.70.a·D1·MENOR-2] Cerrojo tomado y registro MUDO: AVISO, no aborto. Aquí se
# abortaba acusando a «un 'flock' suelto de una sesión SSH», y eso contradecía a
# la otra mitad de D1: `gpio._registrar_dueno` escribe el registro dentro de un
# try/except y CONSERVA la propiedad si su E/S falla —está anclado por
# `test_un_registro_que_no_se_puede_escribir_no_tumba_la_propiedad`—, porque un
# ENOSPC con /var/lib/takab lleno o un EIO de una microSD muriéndose no son razón
# para dejar la sirena, el gas y los retenedores sin dueño. Un gabinete así
# protege perfectamente y se declaraba secuestrado, mandando al operador a buscar
# un intruso que no existe en vez de al disco.
#
# El `flock` YA demostró que HAY dueño; el texto es un extra. Lo que sí sigue
# abortando (arriba) es un registro DESMENTIDO por /proc: ahí el texto no está
# ausente, está contradicho.
# --- 7.b ¿EL DUEÑO DE LOS PINES CORRE EL CÓDIGO QUE ACABAMOS DE DESPLEGAR? ---
#
# [T-2.70.a·D3·B2] El agujero que reabría en el REINICIO lo que D1.5 cerró en la
# VERIFICACIÓN. El paso 7 mide un hecho verdadero —«hay dueño»— y hasta hoy lo
# reportaba como el hecho que importa: «el despliegue llegó al dueño». Con el
# dueño en `takab-gpio` y sin reinicio, el proceso que sostiene la sirena, el
# gas y los retenedores se queda con el código anterior INDEFINIDAMENTE —
# incluido el `Type=notify` que el `daemon-reload` escribió y no aplicó— y el
# script imprimía `✓ pines del gabinete en poder de takab-gpio (pid N)`. Verde.
#
# Se mide en dos pasos, y el segundo es lo que hace usable al primero:
#
#   1. ¿ARRANCÓ DESPUÉS DEL SWAP? El swap reescribe el árbol bajo los pies de
#      quien corre (venv editable, in-place), así que quien arrancó antes tiene,
#      por construcción, el código anterior en memoria. El arranque del proceso
#      sale de `/proc/<pid>/stat` (campo 22, ticks desde el boot) + `btime` de
#      `/proc/stat`; NO del mtime de `/proc/<pid>`, que se actualiza y da la hora
#      ACTUAL (medido: un proceso de 6 s de vida reportaba mtime = ahora).
#   2. Si arrancó antes: ¿CAMBIÓ SU CÓDIGO? Un gate que dijera «no se reinició ⇒
#      rojo» saldría rojo en TODOS los despliegues de un gabinete D3 —el dueño no
#      se reinicia nunca, por diseño— y eso entrena al operador a ignorar el
#      único rojo que dice si la sirena tiene dueño. La mayoría de los
#      despliegues tocan el supervisor, la nube o el panel, y el código del dueño
#      no cambia: ahí no hay nada que ciclar y el ✓ es honesto.
#
# La lista de archivos del dueño se DERIVA de sus imports (los módulos bajo el
# árbol vivo que arrastra `takab_edge.gpio.__main__`, que es su `ExecStart`), no
# se enumera: una lista a mano se queda una versión por detrás del proyecto y
# deja de ver justo el archivo nuevo. Y ante cualquier duda —sin instantánea del
# árbol anterior, intérprete que revienta, salida inesperada— se asume CAMBIÓ:
# «no se puede medir» no puede resolverse imprimiendo un ✓, igual que en la rama
# `ilegible` de arriba.
DUENO_RANCIO=0
CAMBIOS_DEL_DUENO=""
if [ "$PROPIEDAD" = con_dueno ]; then
  INICIO_DUENO=0
  # ¿LLEGAMOS A MEDIR el arranque, o sólo no pudimos? Sin esta distinción, un
  # `/proc/<pid>/stat` ilegible (contenedor con hidepid, kernel endurecido) dejaba
  # INICIO_DUENO=0, y 0 es "antes" que cualquier swap: el script pasaba a AFIRMAR
  # "arrancó ANTES del swap", que es un hecho que no había medido. El veredicto
  # rojo es correcto en los dos casos —fail-closed—, pero la razón que se le da al
  # operador no puede ser inventada: mandarlo a una ventana de mantenimiento a
  # ciclar gas y retenedores por un dato que nadie leyó es caro y es mentira.
  ARRANQUE_MEDIDO=0
  if [ -r "/proc/${DUENO_PID}/stat" ]; then
    ARRANQUE_CRUDO="$(cat "/proc/${DUENO_PID}/stat" 2>/dev/null || true)"
    # El `comm` del campo 2 puede llevar espacios y paréntesis: se corta por el
    # ÚLTIMO ')' y a partir de ahí el primer campo es `state` (el 3), así que el
    # 22 —starttime— queda en el índice 19 de lo que queda.
    ARRANQUE_CAMPOS="${ARRANQUE_CRUDO##*) }"
    read -r -a CAMPOS_PROC <<<"$ARRANQUE_CAMPOS"
    TICKS="${CAMPOS_PROC[19]:-}"
    BOOT="$(sed -n 's/^btime //p' /proc/stat | tail -1 || true)"
    HZ="$(getconf CLK_TCK 2>/dev/null || echo 100)"
    # Los tres se validan por separado: concatenarlos dejaba pasar un TICKS vacío
    # con un BOOT numérico, y la aritmética de bash lo habría leído como 0. Aquí
    # eso «sólo» habría dado un falso RANCIO, pero un parser que se cree lo que
    # no midió es cómo se llega a los otros defectos de este archivo.
    case "$TICKS" in "" | *[!0-9]*) TICKS="" ;; esac
    case "$BOOT" in "" | *[!0-9]*) BOOT="" ;; esac
    case "$HZ" in "" | 0 | *[!0-9]*) HZ=100 ;; esac
    if [ -n "$TICKS" ] && [ -n "$BOOT" ]; then
      INICIO_DUENO=$((BOOT + TICKS / HZ))
      ARRANQUE_MEDIDO=1
    fi
  fi

  if [ "$ARRANQUE_MEDIDO" != 1 ]; then
    DUENO_RANCIO=1
    CAMBIOS_DEL_DUENO="(no se pudo LEER el arranque del dueño en /proc/${DUENO_PID}/stat)"
  elif [ "$INICIO_DUENO" -ge "$MARCA_ACTIVACION" ]; then
    : # arrancó DESPUÉS del repunte: corre lo que acabamos de activar
  elif [ "$HAY_INSTANTANEA" != 1 ]; then
    DUENO_RANCIO=1
    CAMBIOS_DEL_DUENO="(no hay release anterior con la que comparar)"
  else
    # `-c` con un guion suelto: sin escribir archivos en el gabinete y con el
    # intérprete DEL VENV, que es el que ejecuta el ExecStart de la unidad.
    HUELLA="$(.venv/bin/python -c '
# HUELLA-DEL-DUENO-DE-LOS-PINES
import importlib, pathlib, sys

# `.resolve()` atraviesa el symlink: `vivo` acaba siendo la release ACTIVA
# y `previo` la anterior, que es justo la comparación que interesa.
vivo = pathlib.Path(sys.argv[1]).resolve()
previo = pathlib.Path(sys.argv[2]).resolve()
importlib.import_module("takab_edge.gpio.__main__")
cambiados = []
for modulo in list(sys.modules.values()):
    origen = getattr(modulo, "__file__", None)
    if not origen:
        continue
    ruta = pathlib.Path(origen).resolve()
    if not ruta.is_relative_to(vivo):
        continue
    relativa = ruta.relative_to(vivo)
    antes = previo / relativa
    nuevo = ruta.read_bytes() if ruta.is_file() else None
    viejo = antes.read_bytes() if antes.is_file() else None
    if nuevo != viejo:
        cambiados.append(str(relativa))
print("DUENO-CAMBIO " + " ".join(sorted(cambiados)) if cambiados else "DUENO-IGUAL")
' "$VIVO" "$RELEASE_ANTERIOR" 2>/dev/null || true)"
    case "$HUELLA" in
    DUENO-IGUAL) : ;; # mismo código: no hay nada que reiniciar
    DUENO-CAMBIO*)
      DUENO_RANCIO=1
      CAMBIOS_DEL_DUENO="${HUELLA#DUENO-CAMBIO }"
      ;;
    *)
      DUENO_RANCIO=1
      CAMBIOS_DEL_DUENO="(no se pudo comparar el código del dueño: '${HUELLA}')"
      ;;
    esac
  fi
fi

if [ "$DUENO_RANCIO" = 1 ]; then
  if [ "${ARRANQUE_MEDIDO:-0}" = 1 ]; then
    echo "✗ DESPLIEGUE NO VERIFICADO: el DUEÑO DE LOS PINES corre CÓDIGO ANTERIOR." >&2
    echo "  Los pines los tiene '${DUENO_UNIDAD}' (pid ${DUENO_PID}), que arrancó" >&2
    echo "  ANTES del swap de este despliegue y cuyo código SÍ cambió:" >&2
  else
    # Sin medición NO se afirma cuándo arrancó ni que su código cambiara: sólo
    # que no se pudo comprobar. El desenlace es el mismo —rojo— y el operador
    # sigue teniendo que ir a la ventana de mantenimiento; lo que cambia es que
    # ya no se le da como hecho algo que nadie leyó.
    echo "✗ DESPLIEGUE NO VERIFICADO: no consta que el DUEÑO DE LOS PINES corra" >&2
    echo "  el código que acabamos de desplegar." >&2
    echo "  Los pines los tiene '${DUENO_UNIDAD}' (pid ${DUENO_PID}) y NO SE PUDO" >&2
    echo "  COMPROBAR que ejecute lo recién desplegado:" >&2
  fi
  echo "    ${CAMBIOS_DEL_DUENO}" >&2
  echo "" >&2
  echo "  LO QUE ESTO ES Y LO QUE NO ES:" >&2
  echo "  · El gabinete PROTEGE AHORA MISMO — sirena, gas, ascensores y" >&2
  echo "    retenedores tienen dueño; sólo que es el dueño de ayer." >&2
  echo "  · El código nuevo YA está en disco: el próximo arranque del dueño lo" >&2
  echo "    ejecutará, con o sin ti." >&2
  echo "  · NO REVIERTAS. Revertir también es reiniciar, cuesta el mismo ciclo de" >&2
  echo "    GAS_VALVE y DOOR_RETAINER, y deja el gabinete más atrás." >&2
  echo "" >&2
  echo "  Reiniciar al dueño es una ACTUACIÓN FÍSICA (2 transiciones por pin en" >&2
  echo "  gas y retenedores, más una ventana sin sirena), así que va con el" >&2
  echo "  edificio avisado y por el camino que vuelve a verificar la propiedad:" >&2
  echo "    deploy/edge/deploy.sh <host> --ventana-de-mantenimiento" >&2
  exit 1
fi

if [ "$PROPIEDAD" = registro_mudo ]; then
  echo "⚠ pines TOMADOS, pero el registro de ${CERROJO} no dice quién los tiene." >&2
  echo "  Esto NO tumba el despliegue: el flock lo sostiene el kernel y ya" >&2
  echo "  demostró que hay dueño; el registro es informativo y gpio conserva la" >&2
  echo "  propiedad cuando su E/S falla. Un registro vacío apunta AL DISCO de" >&2
  echo "  este gabinete, no a un intruso:" >&2
  echo "    revisa df -h /var/lib/takab   (ENOSPC: spool offline, evidencia)" >&2
  echo "    y dmesg | tail                (EIO de la microSD)" >&2
  echo "  Lo que queda SIN verificar es que el dueño sea una unidad systemd, o" >&2
  echo "  sea que este gabinete puede no sobrevivir al próximo reinicio — y, sin" >&2
  echo "  pid en el registro, tampoco si corre el código que acabamos de poner." >&2
  echo "✓ pines del gabinete RECLAMADOS (dueño anónimo: registro ilegible)"
else
  echo "✓ pines del gabinete en poder de ${DUENO_UNIDAD} (pid ${DUENO_PID})"
fi
# PASO INFORMATIVO — por eso termina en `|| true`. Es el último comando del
# bloque remoto y corre bajo `set -euo pipefail`, así que su código de salida
# ERA el del despliegue entero: un journal recortado (`Storage=volatile` tras un
# reboot), un permiso que falta o un fallo del pipe convertían un despliegue YA
# TERMINADO —unidades instaladas, takab-edge reiniciado y activo— en «deploy
# fallido». Éxito reportado como fracaso, e invita a revertir un gabinete sano:
# revertir es reiniciar, y reiniciar mueve gas y retenedores de puerta.
journalctl -u takab-edge -n 8 --no-pager | tail -8 || true
REMOTO

echo "✓ edge desplegado en ${HOST}, con los pines del gabinete RECLAMADOS"
echo "  OJO: 'con dueño' NO es 'corriendo el código nuevo'. Eso lo confirma el"
echo "  siguiente latido en la consola (columna del gabinete en /fleet): el"
echo "  estado de versión debe quedar AL DÍA, no SIN REINICIAR."
