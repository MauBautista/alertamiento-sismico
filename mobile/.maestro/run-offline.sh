#!/usr/bin/env bash
# Encadena las tres partes del E2E offline y controla el radio entre ellas.
#
# POR QUÉ EXISTE. Dos hechos, los dos medidos en un Pixel 8 Pro el 2026-08-09:
#
#   1. **El modo avión de Android NO apaga el WiFi.** Con `airplane_mode_on=1`,
#      `wlan0` conservaba su IPv4 y el teléfono seguía en línea. El flujo original
#      daba por hecho lo contrario y culpaba a la app de no pintar «MODO OFFLINE»
#      — cuando la app tenía razón: no estaba offline. `expo-network` reportaba
#      `isConnected: true` porque LO ESTABA.
#   2. **Maestro no sabe apagar el WiFi.** No hay comando para el radio, así que
#      esto vive en un script que sí puede hablar con `adb`.
#
# Y por eso son tres partes y no una: el login NECESITA red y lo que se mide
# NECESITA no tenerla. Las partes 2 y 3 no hacen `clearState`, así que heredan la
# sesión y la pantalla de la anterior.
#
# La red se restaura SIEMPRE, con `trap`: un flujo que aborta a media prueba no
# puede dejar el teléfono incomunicado.
set -uo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"

restaurar_red() {
  echo "→ restaurando la red del dispositivo"
  adb shell svc wifi enable >/dev/null 2>&1 || true
  adb shell cmd connectivity airplane-mode disable >/dev/null 2>&1 || true
}
trap restaurar_red EXIT INT TERM

echo "== 1/3 · preparar la sesión (CON red) =="
"$AQUI/run.sh" 05a-offline-preparar.yaml || exit 1

echo
echo "== cortando la red (WiFi + modo avión) =="
adb shell svc wifi disable >/dev/null 2>&1 || true
adb shell cmd connectivity airplane-mode enable >/dev/null 2>&1 || true
sleep 6

echo "== 2/3 · trabajar sin red y ver la cola =="
"$AQUI/run.sh" 05b-offline-cola.yaml || exit 1

echo
echo "== devolviendo la red =="
adb shell cmd connectivity airplane-mode disable >/dev/null 2>&1 || true
adb shell svc wifi enable >/dev/null 2>&1 || true
sleep 10

echo "== 3/3 · la cola drena sola =="
"$AQUI/run.sh" 05c-offline-drena.yaml || exit 1

echo
echo "✓ offline-first acreditado de punta a punta"
