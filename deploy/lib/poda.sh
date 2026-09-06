# shellcheck shell=bash
# deploy/lib/poda.sh — qué claves del bucket sobran. Se SOURCEA, no se ejecuta.
#
# EL DEFECTO QUE LO TRAJO AQUÍ (despliegue de la landing v3, 2026-09-06)
# ---------------------------------------------------------------------
# La poda de `deploy/landing/deploy.sh` ordenaba las dos listas con `sort` y las
# restaba con `comm`. En el despliegue real eso escupió, a mitad del log:
#
#     comm: archivo 1 no está en orden ordenado
#     comm: archivo 2 no está en orden ordenado
#
# `sort` colaciona según la locale y `comm` compara byte a byte. Bajo
# `es_ES.UTF-8` —la de la máquina desde la que se despliega— la colación IGNORA
# el guion bajo, así que `sort` coloca:
#
#     404.html
#     apple-touch-icon.png        <-- entre medias
#     _astro/archivo-400.woff2
#
# mientras que para `comm` el orden correcto es `_astro/...` antes que `apple...`
# (`_` es 0x5F y `a` es 0x61). Los dos tenían razón; no hablaban el mismo idioma.
#
# POR QUÉ IMPORTA, Y POR QUÉ NO SE VIO
# ------------------------------------
# Lo que `comm -23` devuelve es la lista de claves A BORRAR de producción. Con
# las entradas desincronizadas puede fallar en las dos direcciones: dejar pasar
# un huérfano —inocuo— o **emitir una clave que SÍ está en la copia local**, es
# decir, borrar del sitio vivo un fichero que la página necesita.
#
# El aviso salía por stderr, en medio de doscientas líneas de `aws s3 sync`, y el
# script terminaba en `== OK ==` porque el smoke posterior sólo mira `/`, `/no-existe`
# y la rev: tres peticiones que siguen respondiendo aunque falte una fuente o una
# imagen. Un despliegue puede estropear el sitio y aun así pasar su propio smoke.
#
# LA FORMA DE LA SOLUCIÓN
# -----------------------
# La función NO tiene precondición de orden: ordena ella misma las dos listas, y
# lo hace todo —los `sort` y el `comm`— dentro de un subshell con `LC_ALL=C`, que
# es el único idioma en el que ambas herramientas coinciden. Así el defecto no
# puede volver por el camino por el que vino: no hay un contrato de ordenación
# que un llamador futuro pueda incumplir sin darse cuenta.
#
# Vive en `deploy/lib/` por lo mismo que `guardas.sh` (T-2.171): la alternativa
# era una copia en el script y otra en su test, y dos copias de la misma resta
# acaban divergiendo — divergiendo, además, en la que decide qué se borra.

# claves_huerfanas <fichero-remoto> <fichero-local>
#
# Escribe por stdout, una por línea, las claves que están en la lista remota y no
# en la local. Las listas pueden venir en CUALQUIER orden y con repetidos.
claves_huerfanas() {
  local remoto="${1:?lista de claves remotas}" copia_local="${2:?lista de claves locales}"
  [ -r "$remoto" ] || { echo "poda: no se puede leer '$remoto'" >&2; return 2; }
  [ -r "$copia_local" ] || { echo "poda: no se puede leer '$copia_local'" >&2; return 2; }
  (
    export LC_ALL=C
    comm -23 <(sort -u "$remoto") <(sort -u "$copia_local")
  )
}
