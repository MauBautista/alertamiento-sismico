#!/usr/bin/env bash
# El recolector del acta del reflejo SE EJECUTA (T-5.22 · GATE-HW / G-04).
#
# POR QUÉ EXISTE ESTE TEST
# ------------------------
# El procedimiento que este script sustituye vivía como tres comandos escritos a
# mano en un runbook, y **los tres estaban rotos** (comprobado contra el Pi real
# el 2026-09-04: `systemctl show -p Environment` no muestra el `EnvironmentFile`,
# el paso siguiente leía otra ruta, y el `scp` llevaba un literal `...`).
#
# Un procedimiento que se ejecuta una vez cada varios meses, en una sesión
# presencial que cuesta un viaje, **no puede descubrirse roto delante del
# gabinete**. Aquí se ejercita entero contra un `ssh` de mentira: lo que se
# comprueba es que el script sabe leer el estado, distinguir los tres casos que
# significan cosas distintas, y no mentir en ninguno.
#
#   bash edge/tests/test_acta_reflejo_script.sh

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$RAIZ/edge/scripts/acta_reflejo.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ok=0
fallos=0

check() {
  local nombre="$1" cond="$2" detalle="${3:-}"
  if [ "$cond" = "0" ]; then
    printf '  \033[32mOK\033[0m   %s\n' "$nombre"
    ok=$((ok + 1))
  else
    printf '  \033[31mFALLO\033[0m %s %s\n' "$nombre" "$detalle" >&2
    fallos=$((fallos + 1))
  fi
}

# --- gabinete de mentira -----------------------------------------------------
#
# `ssh` y `scp` falsos en el PATH. Reproducen lo que el Pi real contesta: el
# `EnvironmentFiles=` con su `(ignore_errors=no)` pegado —que es la forma exacta
# que devuelve systemd y la que rompía el parseo ingenuo— y un `edge.env` con la
# variable dentro, que es donde el gabinete real la tiene.
crear_gabinete() {
  local desplegado="$1" acta="$2"
  mkdir -p "$TMP/bin" "$TMP/spool/actuation-ledger"
  # El caso `python3` EJECUTA LA ORDEN QUE EL SCRIPT MANDÓ, no una copia suya.
  # Tenerla copiada aquí fue el primer intento y era un espejo: dos mutaciones
  # —publicar solo el mejor caso, y contar los pulsos de prueba como evidencia—
  # **sobrevivieron en verde** porque el test medía su propia copia. Un arnés que
  # reimplementa lo que prueba no prueba nada.
  cat >"$TMP/bin/ssh" <<EOF
#!/usr/bin/env bash
orden="\${*: -1}"
case "\$orden" in
  *"name reflejo.py"*)
      [ "$desplegado" = "si" ] && echo "/opt/takab/edge/takab_edge/audit/reflejo.py"
      ;;
  *EnvironmentFiles*)
      echo "$TMP/spool/actuation-ledger/reflejo.jsonl" ;;
  *)  bash -c "\$orden" ;;
esac
EOF
  cat >"$TMP/bin/scp" <<EOF
#!/usr/bin/env bash
cp "$TMP/spool/actuation-ledger/reflejo.jsonl" "\${*: -1}"
EOF
  chmod +x "$TMP/bin/ssh" "$TMP/bin/scp"
  rm -f "$TMP/spool/actuation-ledger/reflejo.jsonl"
  [ -n "$acta" ] && printf '%s\n' "$acta" >"$TMP/spool/actuation-ledger/reflejo.jsonl"
  return 0
}

correr() {
  PATH="$TMP/bin:$PATH" DESTINO="$TMP" HOST=falso bash "$SCRIPT" "$@" 2>&1
}
codigo() {
  set +e
  PATH="$TMP/bin:$PATH" DESTINO="$TMP" HOST=falso bash "$SCRIPT" "$@" >/dev/null 2>&1
  local c=$?
  set -e
  echo "$c"
}

ACTA_REAL='{"medido_en":"2026-09-04T18:00:00+00:00","latencia_s":0.00416,"latencia_ms":4.16,"gateway_id":"gw-dev-0001","fw_version":"abc","es_prueba":false,"canales":{"siren":true}}
{"medido_en":"2026-09-04T18:01:00+00:00","latencia_s":0.00812,"latencia_ms":8.12,"gateway_id":"gw-dev-0001","fw_version":"abc","es_prueba":false,"canales":{"siren":true}}'
ACTA_PRUEBA='{"medido_en":"2026-09-04T18:00:00+00:00","latencia_s":0.004,"latencia_ms":4.0,"gateway_id":"gw-dev-0001","fw_version":"abc","es_prueba":true,"canales":{}}'

echo "acta del reflejo · el recolector se ejecuta"

# --- 1 · el caso que ahorra el viaje ----------------------------------------
crear_gabinete "no" "$ACTA_REAL"
salida="$(correr --check || true)"
check "sin el acta DESPLEGADA lo dice y no sigue" \
  "$([[ "$salida" == *"NO ESTÁ DESPLEGADA"* ]] && echo 0 || echo 1)" "$salida"
check "y sale con código propio (2), no con un 0 que parecería éxito" \
  "$([ "$(codigo --check)" = "2" ] && echo 0 || echo 1)"

# --- 2 · desplegado y sin flancos: OTRO hecho, otro mensaje ------------------
crear_gabinete "si" ""
salida="$(correr --check || true)"
check "desplegado pero sin actas se distingue de 'no desplegado'" \
  "$([[ "$salida" == *"ningún flanco"* && "$salida" != *"DESPLEGADA"* ]] && echo 0 || echo 1)" "$salida"

# --- 3 · solo pulsos de prueba: no acreditan nada ---------------------------
crear_gabinete "si" "$ACTA_PRUEBA"
salida="$(correr --check || true)"
check "un acta de solo PRUEBAS no se cuenta como evidencia" \
  "$([[ "$salida" == *"pulsos de PRUEBA"* ]] && echo 0 || echo 1)" "$salida"

# --- 4 · el caso bueno ------------------------------------------------------
crear_gabinete "si" "$ACTA_REAL"
salida="$(correr --check || true)"
check "con actas reales declara la precondición cumplida" \
  "$([[ "$salida" == *"PRECONDICIÓN OK"* ]] && echo 0 || echo 1)" "$salida"
check "publica MEJOR y PEOR, no solo el mejor" \
  "$([[ "$salida" == *'"mejor_ms": 4.16'* && "$salida" == *'"peor_ms": 8.12'* ]] && echo 0 || echo 1)" \
  "$salida"

salida="$(correr || true)"
artefacto="$(find "$TMP" -maxdepth 1 -name 'evidencia-G04-*.jsonl' | head -1)"
check "se TRAE el artefacto, que es lo que un cliente puede pedir" \
  "$([ -s "$artefacto" ] && echo 0 || echo 1)" "$artefacto"
check "y recuerda actualizar la fuente única de la cifra" \
  "$([[ "$salida" == *"MEDICIONES-TAKAB.md"* ]] && echo 0 || echo 1)"

# --- 5 · guarda de no-vacuidad ----------------------------------------------
# Sin esto, un `ssh` de mentira que no contestara nada dejaría todos los
# `[[ ... ]]` en falso y el test en verde por vacío.
check "el arnés VE al gabinete de mentira (no está midiendo la nada)" \
  "$([ "$(PATH="$TMP/bin:$PATH" ssh falso 'find /opt/takab/edge -name reflejo.py')" != "" ] && echo 0 || echo 1)"

echo
if [ "$fallos" -eq 0 ]; then
  printf '\033[32m%s\033[0m\n' "acta del reflejo: $ok OK · 0 fallos"
else
  printf '\033[31m%s\033[0m\n' "acta del reflejo: $ok OK · $fallos FALLOS" >&2
  exit 1
fi
