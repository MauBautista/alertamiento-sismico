#!/usr/bin/env bash
# shellcheck shell=bash
# deploy/cloud/margen-y-poda.sh — ¿cabe el despliegue? Y si no cabe, ¿por qué?
#
# Se EJECUTA en la instancia (viaja por base64 como `takab-secrets.sh` y el
# compose), no se sourcea. Por eso vive aquí y no en `deploy/lib/`, que es donde
# están los ficheros que otros scripts *sourcean* (`guardas.sh`, `poda.sh`).
#
#     margen-y-poda.sh <registry> <etiqueta-que-se-despliega>
#
# EL DEFECTO QUE LO TRAJO AQUÍ (T-7.46, medido el 2026-09-16)
# ----------------------------------------------------------
# `make cloud-deploy` murió con `failed to register layer: no space left on
# device`. La raíz estaba al 99 % —20 GiB, 268 MB libres— con 65 imágenes de
# Docker y 16,23 GB, algunas de siete semanas atrás: **ningún despliegue había
# podado nunca**. El acumulador no tenía freno ni testigo.
#
# Y el fallo salió por pantalla como otra cosa. Las dos bajadas de imagen de este
# despliegue son EFECTOS COLATERALES —`docker run` de alembic y el `docker
# compose up` de la unidad—, no hay ningún `docker pull`; `docker run` devuelve
# 125 cuando el demonio no puede arrancar el contenedor, así que el único texto
# legible decía «alembic upgrade head FALLÓ (rc=125) — la API no se toca» y
# mandaba a mirar migraciones. El `no space left on device` estaba enterrado en
# el volcado de stderr del final. Eso costó una hora.
#
# POR QUÉ EL ORDEN ES medir → podar → medir → juzgar
# --------------------------------------------------
# Juzgar antes de podar abortaría un despliegue que la poda habría salvado, que
# es literalmente lo que pasó ese día: había 11,37 GB recuperables. Y podar sin
# medir antes y después deja el log sin la única cifra que dice si el margen se
# está estrechando despliegue a despliegue.
#
# LA VENTANA ES POR IDENTIDAD, NUNCA POR FECHA NI `-a` A SECAS
# ------------------------------------------------------------
# Las dos formas fáciles están descartadas con evidencia del propio repositorio:
#
# * **`--filter until=<horas>`** es el criterio que se tecleó a mano aquel día, y
#   la recencia ya se midió como equivocada en campo: la poda por fecha del edge
#   se llevó la release heredada la misma noche del estreno, porque *toda*
#   release nueva es más reciente que ella (`deploy/edge/deploy.sh`, y su ancla
#   `test_la_poda_JAMAS_se_lleva_la_release_heredada`). Además no acota nada: sin
#   despliegues durante tres semanas borra hasta la que corre; con ocho en un día
#   no borra nada.
# * **`docker image prune -a`** solo perdona lo que tiene un contenedor encima.
#   Con el stack abajo —y `takab-cloud.service` lo deja abajo si
#   `takab-secrets.service` no materializa los secretos— se lleva también la
#   última imagen buena.
#
# Aquí se construye la lista de lo que se CONSERVA y se borra el resto:
#
#   (a) lo que está corriendo AHORA, leído de `docker ps`. No del compose ni del
#       fichero de entorno: `docker ps` no necesita que el compose esté escrito,
#       no interpola variables y ve también a `takab-db`, que NO está en el
#       compose (lo arranca `user_data` con `docker run`).
#   (b) la etiqueta que se va a desplegar, por si ya estuviera bajada.
#   (c) las `RETENCION` más recientes de cada repo. Aquí la recencia SÍ vale,
#       porque es un techo sobre lo que sobra, no el criterio que decide si algo
#       imprescindible se queda.
#
# Y la poda **nombra sus dos repositorios**: nada que no sea `takab/cloud` ni
# `takab/console` se toca jamás, empezando por la imagen de TimescaleDB que
# sostiene la base de datos.
#
# ⚠️ CONSERVAR LA IMAGEN ANTERIOR NO ES UNA VUELTA ATRÁS. La única reversión de
# la nube que el repositorio declara es `CLOUD_TAG=<sha-viejo> make cloud-deploy`
# (`deploy/lib/guardas.sh`), que vuelve a correr este mismo despliegue y baja la
# imagen de ECR si falta. Lo que la copia local compra es velocidad, no una
# capacidad nueva: la cota real de cuántas vueltas atrás EXISTEN es la política
# de ciclo de vida de ECR, que conserva las 10 más recientes por repositorio. La
# retención local no puede prometer más que eso, y lo fija una prueba.
#
# (`T-2.70` NO entra aquí, aunque la ficha original lo citara: es el canary del
# EDGE y opera sobre directorios de release, no sobre imágenes de Docker.)

set -euo pipefail

REGISTRY="${1:?falta el registro ECR}"
ETIQUETA="${2:?falta la etiqueta que se despliega}"

#: Cuántas etiquetas se conservan por repositorio, además de lo que corre y lo
#: que se despliega. Es el mismo número que el edge declara para sus releases
#: vivas, para que las dos mitades del sistema digan uno y no dos.
#:
#: ⚠️ No puede superar el `countNumber` de la política de ciclo de vida de ECR
#: (`infra/terraform/modules/registry`): más allá de esas imágenes la etiqueta ya
#: no existe en el registro, y guardarla en el disco promete una vuelta atrás que
#: nadie puede ejecutar. Lo comprueba
#: `test_la_retencion_local_no_promete_mas_de_lo_que_ECR_conserva`.
RETENCION="${TAKAB_RETENCION_IMAGENES:-3}"

#: Bytes libres que tienen que quedar DESPUÉS de podar para dejar seguir.
#:
#: MEDIDO en la instancia el 2026-09-16, no estimado: el tamaño en disco de
#: `takab/cloud` es 432 MB, pero su coste MARGINAL —lo que ocupa una etiqueta
#: nueva sobre las capas base que ya están— es 279,7 MB, y el de `takab/console`
#: es 2,4 MB. Un despliegue añade pues ~282 MB de residuo permanente.
#:
#: El PICO es mayor que el residuo: durante la bajada conviven el blob que se
#: descarga y las capas ya desempaquetadas, así que se cuenta ~2× el marginal
#: (~570 MB) para el par de imágenes. A eso se le suma la holgura de operación de
#: la máquina —los logs de los contenedores, el spool de SSM, el `/tmp` del
#: contenedor de migración— y se redondea hacia arriba con margen para dos
#: despliegues seguidos sin poda efectiva.
#:
#: 2 GiB. Si esta cifra estorba, la conversación es sobre el tamaño de la raíz
#: (ver la decisión escrita junto a `root_block_device` en el terraform), no
#: sobre bajar el número.
MINIMO_LIBRE=$((2 * 1024 * 1024 * 1024))

REPOS=("takab/cloud" "takab/console")

# --- medir ------------------------------------------------------------------

# El punto de montaje se DERIVA del propio Docker en vez de escribir `/`: el día
# que alguien mueva el data-root a otro volumen, este guardia tiene que seguir
# midiendo el disco que se llena, no el que solía llenarse.
RAIZ_DOCKER="$(docker info -f '{{.DockerRootDir}}' 2>/dev/null || true)"
if [ -z "$RAIZ_DOCKER" ]; then
  echo "✗ no se pudo preguntarle a Docker dónde guarda sus imágenes." >&2
  echo "  NO se sigue: un despliegue que no sabe cuánto disco tiene es el fallo" >&2
  echo "  del 2026-09-16. La API no se ha tocado." >&2
  exit 2
fi

libres_en() {
  # Bytes libres del sistema de ficheros que contiene ese directorio. `-P`
  # fuerza el formato POSIX de una sola línea: sin él, un dispositivo de nombre
  # largo parte la fila en dos y el `$4` deja de ser lo que se cree.
  df -PB1 "$1" | awk 'NR==2 {print $4}'
}
total_en() {
  df -PB1 "$1" | awk 'NR==2 {print $2}'
}
legible() {
  # Sin `numfmt --to=iec` a propósito: no está garantizado en toda imagen mínima
  # y esto tiene que funcionar donde corra, no donde nos guste.
  awk -v b="$1" 'BEGIN {
    split("B KB MB GB TB", u, " "); i = 1
    while (b >= 1024 && i < 5) { b /= 1024; i++ }
    printf (i == 1 ? "%d %s" : "%.1f %s"), b, u[i]
  }'
}

ANTES="$(libres_en "$RAIZ_DOCKER")"
TOTAL="$(total_en "$RAIZ_DOCKER")"
if [ -z "$ANTES" ] || [ -z "$TOTAL" ]; then
  echo "✗ no se pudo medir el margen de disco: df no devolvió cifras para $RAIZ_DOCKER." >&2
  echo "  NO se sigue. La API no se ha tocado." >&2
  exit 2
fi
USADO_PCT=$(( (TOTAL - ANTES) * 100 / TOTAL ))
echo "→ margen en $RAIZ_DOCKER antes de podar: $(legible "$ANTES") libres de $(legible "$TOTAL") (${USADO_PCT} % usado)"

# --- qué se conserva --------------------------------------------------------

CONSERVA="$(
  {
    # (a) lo que corre ahora mismo, sea del compose o no.
    docker ps --format '{{.Image}}' 2>/dev/null || true
    # (b) lo que se va a desplegar.
    for repo in "${REPOS[@]}"; do echo "${REGISTRY}/${repo}:${ETIQUETA}"; done
    # (c) las N más recientes de cada repo.
    for repo in "${REPOS[@]}"; do
      docker images --filter "reference=${REGISTRY}/${repo}" \
        --format '{{.CreatedAt}}\t{{.Repository}}:{{.Tag}}' 2>/dev/null |
        sort -r | head -n "$RETENCION" | cut -f2
    done
  } | sort -u
)"

echo "  conservando: lo que corre, ${ETIQUETA} y las ${RETENCION} etiquetas más recientes de cada repo"

# --- podar ------------------------------------------------------------------

PODADAS=0
FALLIDAS=0
for repo in "${REPOS[@]}"; do
  # `docker images` de un repo concreto: la poda NUNCA barre el catálogo entero,
  # así que la imagen de la base de datos no puede caer por accidente.
  while IFS= read -r imagen; do
    [ -n "$imagen" ] || continue
    if printf '%s\n' "$CONSERVA" | grep -qxF "$imagen"; then
      continue
    fi
    if docker rmi "$imagen" >/dev/null 2>&1; then
      echo "    podada $imagen"
      PODADAS=$((PODADAS + 1))
    else
      # No se calla: una imagen que no se deja borrar es justo la que conviene
      # mirar, y el margen de abajo sigue siendo quien decide si se puede seguir.
      echo "    ⚠ no se pudo borrar $imagen (¿la usa un contenedor parado?)"
      FALLIDAS=$((FALLIDAS + 1))
    fi
  done < <(docker images --filter "reference=${REGISTRY}/${repo}" --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -v ':<none>$' || true)
done

# --- volver a medir y juzgar ------------------------------------------------

DESPUES="$(libres_en "$RAIZ_DOCKER")"
if [ -z "$DESPUES" ]; then
  echo "✗ no se pudo volver a medir el margen tras podar. NO se sigue." >&2
  exit 2
fi
USADO_PCT=$(( (TOTAL - DESPUES) * 100 / TOTAL ))
LIBERADO=$((DESPUES - ANTES))

if [ "$PODADAS" -eq 0 ] && [ "$FALLIDAS" -eq 0 ]; then
  # También se dice cuando no hay nada que hacer: una poda silenciosa es lo que
  # hace que nadie sepa cuánto margen quedaba.
  echo "✓ nada que podar; margen en $RAIZ_DOCKER: $(legible "$DESPUES") libres de $(legible "$TOTAL") (${USADO_PCT} % usado)"
else
  echo "✓ podadas ${PODADAS} imágenes ($FALLIDAS sin borrar), $(legible "$LIBERADO") recuperados; margen: $(legible "$DESPUES") libres de $(legible "$TOTAL") (${USADO_PCT} % usado)"
fi

if [ "$DESPUES" -lt "$MINIMO_LIBRE" ]; then
  cat >&2 <<AVISO
✗ margen insuficiente en ${RAIZ_DOCKER}: $(legible "$DESPUES") libres y hacen falta $(legible "$MINIMO_LIBRE")
  La poda ya corrió y sólo liberó $(legible "$LIBERADO"): no sobran imágenes, falta disco.
  Las imágenes de Docker viven en el volumen RAÍZ (20 GiB), NO en /data (40 GiB):
  la alarma takab-dev-disco-datos-lleno no mira este volumen.
  Qué hacer, en este orden:
    1) docker system df            — qué ocupa y cuánto es recuperable
    2) du -xh --max-depth=2 /var   — los logs de contenedor NO los poda docker
    3) docker image prune -a -f    — se lleva también la copia local de la vuelta
                                     atrás; sólo si urge y con el stack ARRIBA
    4) crecer la raíz: decisión humana (ver T-7.46 y la nota junto a
       root_block_device en infra/terraform/modules/database)
  La API no se ha tocado: la nube sigue sirviendo lo que servía.
AVISO
  exit 3
fi
