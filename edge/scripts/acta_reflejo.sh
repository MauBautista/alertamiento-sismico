#!/usr/bin/env bash
# Recoge el ACTA DEL REFLEJO de un gabinete (T-5.22 · GATE-HW / G-04).
#
# POR QUÉ ESTO ES UN SCRIPT Y NO TRES COMANDOS EN UN RUNBOOK
# ----------------------------------------------------------
# Lo era, y los tres estaban rotos. Comprobado contra el Pi real el 2026-09-04:
#
#   1. La ruta se derivaba con `systemctl show -p Environment takab-edge`, que
#      muestra SOLO las directivas `Environment=` de la unidad y **no** el
#      contenido de su `EnvironmentFile=`. El gabinete tiene la variable en
#      `/etc/takab/edge.env`, así que el comando devolvía vacío y el `dirname`
#      moría con «missing operand».
#   2. El paso siguiente ignoraba esa ruta y leía `~/reflejo.jsonl`, que no
#      existe.
#   3. El `scp` final llevaba un literal `...` sin rellenar.
#
# O sea: la sesión presencial habría llegado al gabinete, pulsado el WR-1, y se
# habría vuelto sin evidencia. Un procedimiento que solo se ejecuta una vez cada
# varios meses y que nadie prueba entre medias **tiene que ser ejecutable**, y
# por eso lo cubre `edge/tests/test_acta_reflejo_script.sh`.
#
# USO
# ---
#   edge/scripts/acta_reflejo.sh --check            # ANTES de ir: ¿hay acta?
#   edge/scripts/acta_reflejo.sh                    # al terminar: resumen + copia
#   HOST=otro-pi edge/scripts/acta_reflejo.sh
#
# `--check` es la mitad que ahorra el viaje: si el gabinete no tiene desplegado
# el módulo del acta, la sesión no puede producir evidencia por bien que salga la
# medición, y eso se sabe desde el escritorio.

set -euo pipefail

HOST="${HOST:-takab-pi5}"
UNIDAD="${UNIDAD:-takab-edge}"
DESTINO="${DESTINO:-.}"
# Array y no cadena: una cadena partida por el shell es justo el defecto
# que shellcheck señala (SC2086), y aquí lleva credenciales de conexión.
read -r -a SSH_OPTS <<<"${SSH_OPTS:--o ConnectTimeout=10}"

rojo() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }

# La ruta del acta se DERIVA, nunca se teclea: es hermana del spool de la nube
# (`audit.ledger_dir_for`). Y la variable se lee de los EnvironmentFile que la
# unidad declara, que es donde el gabinete real la tiene.
remoto_ruta() {
  # shellcheck disable=SC2029  # `$UNIDAD` se expande AQUÍ a propósito: el nombre
  # de la unidad lo elige quien invoca, no el gabinete.
  ssh "${SSH_OPTS[@]}" "$HOST" "
    set -eu
    ficheros=\$(systemctl show -p EnvironmentFiles '$UNIDAD' |
                sed 's/^EnvironmentFiles=//' | tr ' ' '\n' |
                sed 's/ *(ignore_errors=[^)]*)//' | grep -v '^\$' || true)
    spool=''
    for f in \$ficheros; do
      [ -r \"\$f\" ] || continue
      v=\$(grep -m1 '^TAKAB_EDGE_CLOUD_SPOOL_DIR=' \"\$f\" | cut -d= -f2- || true)
      [ -n \"\$v\" ] && spool=\$v && break
    done
    [ -n \"\$spool\" ] || { echo 'SIN_SPOOL'; exit 0; }
    echo \"\$(dirname \"\$spool\")/actuation-ledger/reflejo.jsonl\"
  "
}

# ¿Está DESPLEGADO el módulo del acta? Sin él no hay nada que recoger, y el
# síntoma —un fichero que no existe— es indistinguible de «no hubo flancos».
remoto_desplegado() {
  ssh "${SSH_OPTS[@]}" "$HOST" "
    find /opt/takab/edge -name reflejo.py -path '*audit*' 2>/dev/null | head -1
  "
}

resumen_remoto() {
  local ruta="$1"
  # shellcheck disable=SC2029  # ídem: la ruta la derivó este script.
  ssh "${SSH_OPTS[@]}" "$HOST" "python3 - '$ruta' <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
if not p.is_file():
    print('SIN_ACTA'); raise SystemExit(0)
actas = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
# Los pulsos de PRUEBA del WR-1 no acreditan el camino real: se cuentan aparte.
reales = [a for a in actas if not a.get('es_prueba')]
pruebas = len(actas) - len(reales)
if not reales:
    print(f'SIN_REALES {pruebas}'); raise SystemExit(0)
ms = sorted(float(a['latencia_ms']) for a in reales)
print(json.dumps({
    'reales': len(reales), 'pruebas': pruebas,
    'mejor_ms': ms[0], 'peor_ms': ms[-1],
    'ultima': reales[-1]['medido_en'], 'fw': reales[-1].get('fw_version'),
    'canales': reales[-1].get('canales'),
}, ensure_ascii=False))
PY"
}

main() {
  local solo_check=0
  [ "${1:-}" = "--check" ] && solo_check=1

  info "gabinete: $HOST · unidad: $UNIDAD"

  local desplegado
  desplegado=$(remoto_desplegado || true)
  if [ -z "$desplegado" ]; then
    rojo "EL ACTA NO ESTÁ DESPLEGADA en $HOST."
    rojo "  El gabinete no puede escribir ni una línea, así que la sesión"
    rojo "  presencial NO produciría evidencia por bien que salga la medición."
    rojo "  Despliega una versión con 'takab_edge/audit/reflejo.py' antes de ir."
    return 2
  fi
  verde "acta desplegada: $desplegado"

  local ruta
  ruta=$(remoto_ruta)
  if [ "$ruta" = "SIN_SPOOL" ]; then
    rojo "no se pudo derivar la ruta: la unidad no declara TAKAB_EDGE_CLOUD_SPOOL_DIR"
    return 3
  fi
  info "acta: $ruta"

  local resumen
  resumen=$(resumen_remoto "$ruta")
  case "$resumen" in
    SIN_ACTA)
      rojo "todavía no hay acta: el gabinete no ha visto ningún flanco del WR-1."
      [ "$solo_check" = 1 ] && return 0
      return 4
      ;;
    SIN_REALES*)
      rojo "solo hay pulsos de PRUEBA (${resumen#SIN_REALES }): no acreditan el camino real."
      [ "$solo_check" = 1 ] && return 0
      return 4
      ;;
  esac
  verde "resumen: $resumen"

  if [ "$solo_check" = 1 ]; then
    verde "PRECONDICIÓN OK: el gabinete puede producir evidencia."
    return 0
  fi

  local salida
  salida="$DESTINO/evidencia-G04-$(date +%Y%m%d-%H%M%S).jsonl"
  scp "${SSH_OPTS[@]}" "$HOST:$ruta" "$salida" >/dev/null
  verde "artefacto: $salida"
  info "Ahora actualiza takab-docs/MEDICIONES-TAKAB.md §2 con las cifras Y esta ruta."
}

main "$@"
