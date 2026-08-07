#!/usr/bin/env bash
# Despliega el código del edge al Pi (T-1.40). Idempotente.
#
# Hasta ahora el código llegaba a /opt/takab por un rsync manual sin versionar
# (el gap lo documentó la auditoría de Fase 1.6). Este script ES el mecanismo:
#   1. rsync de edge/ y shared/schemas/ a un árbol de ENSAYO (`edge.incoming`),
#      SIN tocar el árbol vivo;
#   2. PRE-VUELO sobre el árbol de ensayo: `compileall` del código recién
#      copiado. Abortar aquí no destruye NADA — el disco sigue con lo viejo;
#   3. INSTANTÁNEA del árbol vivo (`edge.prev`) —si HAY árbol vivo: en el primer
#      despliegue de un gabinete no lo hay, y entonces NO hay vuelta atrás que
#      ofrecer— y sólo entonces el swap destructivo + marca de FW_VERSION;
#   4. `uv sync` con los extras de EDGE_EXTRAS dentro del Pi;
#   5. GATE: importa el CÓDIGO DESPLEGADO (`takab_edge.supervisor` y
#      `takab_edge.gpio.__main__` — los dos entry points de las unidades) y sus
#      dependencias críticas (lgpio, awsiot). Aborta SIN reiniciar si falla;
#   6. instala/refresca las unidades systemd versionadas y reinicia takab-edge;
#   7. verificación: unidad activa (ESTO sí puede tumbar el despliegue) +
#      últimas líneas del journal (INFORMATIVO: su fallo no lo tumba).
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
# [T-2.70] LO QUE ESTE SCRIPT TODAVÍA NO ES. El despliegue sigue siendo IN-PLACE
# sobre una instalación EDITABLE del venv (`_editable_impl_takab_edge.pth` apunta
# al árbol fuente), así que el swap del paso 3 reescribe el código BAJO LOS PIES
# del proceso vivo. En consecuencia:
#   · La reversibilidad es PARCIAL y sólo de código fuente: `edge.prev` permite
#     restaurar el árbol anterior (el paso 3 lo deja escrito), pero NO revierte
#     lo que el `uv sync` haya hecho en el `.venv`. Un rollback completo exige
#     volver a correr este script desde el commit anterior.
#   · Un `systemctl restart takab-edge` es una ACTUACIÓN FÍSICA sobre el
#     edificio: `GpioController._on_stop()` llama `drive_all_safe()`, que
#     de-energiza los relés — con el fail-safe por defecto eso CIERRA EL GAS y
#     SUELTA LOS RETENEDORES DE PUERTA, y el arranque los repone.
#   · Y `takab-edge` es el proceso que sostiene el reflejo SASMEX→sirena (gate
#     #6: supervisor único, `Conflicts=takab-gpio.service`), así que la ventana
#     de reinicio ES una ventana de desprotección, acotada por `TimeoutStopSec`.
# Lo que quitaría las tres cosas es un despliegue A/B: sincronizar a
# /opt/takab/releases/<sha>/ con su propio venv, verificarlo, y solo entonces
# repuntar el symlink /opt/takab/edge (el ExecStart de las unidades NO cambia) y
# reiniciar; el rollback pasa a ser `ln -sfn` + restart. NO se implementó en
# T-2.70 a propósito: cambia el arranque del camino de vida y el agente que
# revierte tendría que vivir FUERA de takab-edge (si takab-edge no arranca, no
# queda nadie que revierta). Eso exige acreditación en el Pi real —el gate G-01—
# y esta tarea no podía tocarlo.
#
# Credenciales/identidad NO viajan por aquí: /etc/takab/{certs,edge.env} las
# instala infra/scripts/provision_gateway.sh (regla de oro 6).
#
# Uso: deploy/edge/deploy.sh [ssh_host]      (default: takab-pi5)
set -euo pipefail

HOST="${1:-takab-pi5}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Raíz del gabinete. Es una VARIABLE y no un literal para que
# edge/tests/test_deploy_sh.py pueda correr este script de verdad contra un
# /opt/takab de mentira (con ssh/rsync/uv/systemctl falsos) y comprobar el ORDEN
# REAL de las operaciones — en particular que un gate que aborta deja el árbol
# vivo intacto. En producción nadie exporta esta variable: vale /opt/takab.
RAIZ_REMOTA="${TAKAB_REMOTE_ROOT:-/opt/takab}"
# Las rutas del árbol vivo y de la instantánea las deriva el bloque remoto de
# esta misma raíz; aquí sólo hace falta el destino del rsync de ensayo.
ARBOL_ENSAYO="${RAIZ_REMOTA}/edge.incoming"

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

# --- 1. ENSAYO: el código nuevo aterriza SIN tocar el árbol vivo -------------
# `--delete` aquí es sobre `edge.incoming`, no sobre lo que el gabinete ejecuta:
# limpia restos de un deploy anterior abortado. El árbol vivo no se toca hasta
# que el pre-vuelo del paso 2 pase.
# `rsync` crea el ÚLTIMO componente del destino, no los intermedios: sin esto,
# un gabinete recién aprovisionado (sin ${RAIZ_REMOTA}/shared) muere con
# «mkdir … failed: No such file or directory». Lo destapó el sandbox de
# edge/tests/test_deploy_sh.py, que parte de una raíz vacía; contra el Pi actual
# no se veía porque los directorios ya existían de despliegues anteriores.
ssh "$HOST" "mkdir -p '${RAIZ_REMOTA}/shared'"

echo "→ sincronizando edge/ y shared/schemas/ a ${HOST}:${ARBOL_ENSAYO} (ensayo)"
rsync -az --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  "$ROOT/edge/" "$HOST:${ARBOL_ENSAYO}/"
rsync -az --delete "$ROOT/shared/schemas/" "$HOST:${RAIZ_REMOTA}/shared/schemas.incoming/"

echo "→ pre-vuelo, swap, dependencias, gate, unidades y reinicio en ${HOST}"
# El bloque remoto va en un heredoc CITADO ('REMOTO'): nada se expande aquí.
# Lo único que viaja del lado local son los flags de extras, la versión y la raíz
# remota, como variables de entorno del `bash -s` remoto, para que cada valor
# viva en UN solo sitio.
ssh "$HOST" \
  "EDGE_EXTRA_FLAGS='${EDGE_EXTRA_FLAGS}' FW_VERSION='${FW_VERSION}' TAKAB_REMOTE_ROOT='${RAIZ_REMOTA}' bash -s" <<'REMOTO'
set -euo pipefail
# SSH no interactivo no carga el PATH de login: uv vive en ~/.local/bin.
export PATH="$HOME/.local/bin:$PATH"

RAIZ="${TAKAB_REMOTE_ROOT:-/opt/takab}"
VIVO="${RAIZ}/edge"
ENSAYO="${RAIZ}/edge.incoming"
PREVIO="${RAIZ}/edge.prev"

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

echo "→ pre-vuelo: compilando el código recién copiado (nada destruido todavía)"
if ! "$PY_PREVUELO" -m compileall -q "${ENSAYO}/takab_edge" "${ENSAYO}/simulators" >/dev/null; then
  echo "✗ ABORTADO EN PRE-VUELO: el código nuevo no compila." >&2
  echo "  NADA se ha destruido: el árbol vivo (${VIVO}) sigue intacto en disco," >&2
  echo "  el gabinete sigue corriendo el código anterior y el próximo arranque" >&2
  echo "  también ejecutará el código anterior. Estado seguro." >&2
  echo "  El árbol rechazado quedó en ${ENSAYO} para inspección." >&2
  exit 1
fi

# --- 3. INSTANTÁNEA + SWAP: a partir de aquí el disco YA cambió --------------
# `edge.prev` es la única reversibilidad de código que existe hoy (el despliegue
# es in-place sobre un venv editable). No revierte el `.venv`, pero convierte
# "no hay vuelta atrás" en "hay vuelta atrás del fuente".
echo "→ instantánea del árbol vivo en ${PREVIO}"
if [ -d "$VIVO" ]; then
  mkdir -p "$PREVIO"
  rsync -a --delete --exclude '.venv' "${VIVO}/" "${PREVIO}/"
  HAY_INSTANTANEA=1
else
  # PRIMER despliegue de este gabinete (o alguien borró ${VIVO}): no hay árbol
  # anterior del que tomar instantánea, así que `${PREVIO}` NO EXISTE. Se anota
  # aquí porque el mensaje de aborto de más abajo ofrecía el comando de
  # restauración PASE LO QUE PASE — y prometer una vuelta atrás inexistente es
  # la misma familia de fallo que el «sigue con el código anterior» que este
  # script ya tuvo que corregir: un mensaje que afirma un estado seguro que
  # nadie comprobó, e invita al operador a irse del sitio.
  echo "  (primer despliegue: no hay árbol vivo del que tomar instantánea)"
  HAY_INSTANTANEA=0
fi

echo "→ swap: ${ENSAYO} → ${VIVO}"
mkdir -p "$VIVO"
# `--exclude .venv` protege el venv del Pi TAMBIÉN del `--delete` (rsync no borra
# en destino lo que está excluido).
rsync -a --delete --exclude '.venv' "${ENSAYO}/" "${VIVO}/"
mkdir -p "${RAIZ}/shared"
rsync -a --delete "${RAIZ}/shared/schemas.incoming/" "${RAIZ}/shared/schemas/"

# DESPUES del swap: `--delete` sobre edge/ lo borraria si se escribiera antes. El edge
# lo lee en cada heartbeat y lo publica; la nube lo persiste en `gateways.fw_version`.
# Sin esto la version se anota A MANO y se queda obsoleta en silencio en el siguiente
# despliegue — que es exactamente lo que paso hasta el 2026-07-30.
echo "→ marcando la versión desplegada (FW_VERSION=${FW_VERSION})"
printf '%s\n' "$FW_VERSION" > "${VIVO}/FW_VERSION"

cd "$VIVO"
# takab-edge corre como root y deja __pycache__ de root DENTRO del venv; sin
# esto, el uv sync del usuario falla con Permission denied en cada deploy.
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
elif ! .venv/bin/python -c 'import takab_edge.supervisor, takab_edge.gpio.__main__' 2>&1; then
  echo "✗ ABORTADO: el CÓDIGO DESPLEGADO no importa." >&2
  FALLO_GATE="el árbol recién copiado (los ExecStart de las unidades no arrancarían)"
elif [ ! -x .venv/bin/takab-edge ] || [ ! -x .venv/bin/takab-gpio ]; then
  echo "✗ ABORTADO: faltan los ejecutables que lanzan las unidades systemd." >&2
  FALLO_GATE="los console scripts .venv/bin/takab-{edge,gpio}"
else
  FALLO_GATE=""
fi

if [ -n "$FALLO_GATE" ]; then
  # LA VERDAD, que el mensaje anterior no decía. El script decía «el gabinete NO
  # se ha reiniciado y sigue con el código anterior» — falso y peligroso: el
  # proceso EN MEMORIA sigue siendo el viejo, pero EL DISCO YA TIENE EL NUEVO.
  echo "  Causa: ${FALLO_GATE}" >&2
  echo "" >&2
  echo "  ESTADO REAL DEL GABINETE — léelo antes de irte:" >&2
  echo "  · NO se reinició: el proceso EN MEMORIA sigue siendo el código anterior." >&2
  echo "  · Pero EL DISCO YA TIENE EL CÓDIGO NUEVO, sin verificar. El próximo" >&2
  echo "    arranque —un corte de luz, un crash con Restart=always, un" >&2
  echo "    systemctl— ejecutará ESTE código. El gabinete NO queda en un" >&2
  echo "    estado seguro si te vas ahora." >&2
  echo "" >&2
  # La vuelta atrás SÓLO se ofrece si de verdad se tomó la instantánea. La
  # versión anterior imprimía el comando siempre, incluido el primer despliegue
  # de un gabinete —donde `${PREVIO}` no existe— y el operador se llevaba una
  # promesa falsa: el `rsync` fallaría con "No such file or directory" cuando ya
  # se hubiera ido del sitio.
  if [ "$HAY_INSTANTANEA" = 1 ]; then
    echo "  Para devolverlo al código anterior (fuente; el .venv NO se revierte):" >&2
    echo "    sudo rsync -a --delete --exclude .venv ${PREVIO}/ ${VIVO}/" >&2
    echo "    cd ${VIVO} && uv sync ${EDGE_EXTRA_FLAGS} && sudo systemctl restart takab-edge" >&2
    echo "  Un rollback COMPLETO (fuente + venv) es volver a correr deploy.sh desde" >&2
    echo "  el commit anterior." >&2
  else
    echo "  NO HAY VUELTA ATRÁS de código: era el PRIMER despliegue de este gabinete" >&2
    echo "  (no existía ${VIVO}), así que no se tomó instantánea y ${PREVIO} no existe." >&2
    echo "  No hay código anterior al que volver. Las salidas son: desplegar un" >&2
    echo "  commit sano, o borrar ${VIVO} para dejar el gabinete SIN código en vez de" >&2
    echo "  con código sin verificar que el próximo arranque ejecutaría." >&2
  fi
  exit 1
fi

# --- 6. Unidades + reinicio --------------------------------------------------
sudo install -m 0644 systemd/takab-edge.service systemd/takab-gpio.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart takab-edge
sleep 3
# LA verificación del despliegue, y la única de este bloque que PUEDE tumbarlo.
systemctl is-active takab-edge
# PASO INFORMATIVO — por eso termina en `|| true`. Es el último comando del
# bloque remoto y corre bajo `set -euo pipefail`, así que su código de salida
# ERA el del despliegue entero: un journal recortado (`Storage=volatile` tras un
# reboot), un permiso que falta o un fallo del pipe convertían un despliegue YA
# TERMINADO —unidades instaladas, takab-edge reiniciado y activo— en «deploy
# fallido». Éxito reportado como fracaso, e invita a revertir un gabinete sano:
# revertir es reiniciar, y reiniciar mueve gas y retenedores de puerta.
journalctl -u takab-edge -n 8 --no-pager | tail -8 || true
REMOTO

echo "✓ edge desplegado y takab-edge activo en ${HOST}"
echo "  OJO: 'activo' NO es 'corriendo el código nuevo'. Eso lo confirma el"
echo "  siguiente latido en la consola (columna del gabinete en /fleet): el"
echo "  estado de versión debe quedar AL DÍA, no SIN REINICIAR."
