# shellcheck shell=bash
# deploy/lib/guardas.sh — la regla A-1, en codigo. Se SOURCEA, no se ejecuta.
#
# [T-2.171] A-1 no es nueva: `deploy/cloud/README.md:55` la escribe desde la
# auditoria de cierre — *«Deploy SOLO desde main pusheado con CI verde […] Lo que
# se despliega debe ser EXACTAMENTE lo que el repositorio y el CI vieron»*. Lo que
# era nuevo es que estuviera SOLO ahi: un paso de checklist que un humano verifica
# «antes de tocar nada».
#
# El 2026-08-27 esa checklist fallo DOS VECES el mismo dia, con el arbol en una
# rama de trabajo: un `terraform apply` que no aplico el topic ni la regla que
# venia a aplicar, y un `make cloud-deploy` que puso en la nube un build sin la
# migracion que lo acompanaba.
#
# Y lo peor no fue equivocarse: fue que TODO salio en verde. El gate del
# despliegue comprobo que la API corre el commit desplegado y que su esquema esta
# al dia —ciertas las dos, del commit equivocado—; la alarma de deriva comparo
# imagen contra base y coincidian; el plan de terraform comparo codigo contra
# estado y «sin cambios» era la respuesta correcta. Un gate verifica que
# desplegaste LO QUE PEDISTE; ninguno puede saber que querias otra cosa. Esa
# pregunta hay que hacerla ANTES, y es la unica que hace este fichero.
#
# El precedente ya vivia en `deploy/landing/deploy.sh`, que sirve HTML. La nube y
# el gabinete —que tocan la sirena— no lo tenian. Extraerlo aqui es lo que impide
# que tres copias divierjan.

guardas_fallo() { echo "ERROR: $*" >&2; exit 1; }

# guarda_de_rama <componente> [tolera_arbol_sucio]
#
# `tolera_arbol_sucio` existe por el EDGE y por nada mas: `deploy/edge/deploy.sh`
# declara a proposito que un arbol sucio se puede desplegar (marca la version con
# `--dirty` y avisa), porque depurar en sitio con el gabinete delante es un caso
# real. Rama y limpieza son DOS preguntas distintas; esto solo anade la primera y
# no toca la segunda.
guarda_de_rama() {
  local componente="${1:?componente}"
  local tolera_sucio="${2:-no}"

  if [ "${TAKAB_DEPLOY_RAMA_LIBRE:-0}" = "1" ]; then
    # La escotilla NO es silenciosa: desplegar una rama a `dev` para probarla es
    # legitimo y frecuente, pero tiene que quedar dicho en voz alta y en el log.
    echo "⚠️  ${componente}: --desde-esta-rama declarado. Se despliega '$(git branch --show-current || echo DETACHED)'" >&2
    echo "    ($(git rev-parse --short HEAD)), que NO es main. Esto no es un despliegue reproducible." >&2
    return 0
  fi

  local rama
  rama="$(git branch --show-current || true)"
  [ "$rama" = "main" ] || guardas_fallo "$(_guardas_por_que_no_main "$componente" "$rama")"

  if [ "$tolera_sucio" != "si" ]; then
    [ -z "$(git status --porcelain)" ] \
      || guardas_fallo "${componente}: el arbol no esta limpio. Lo que se despliega tiene que ser EXACTAMENTE lo que el CI vio; commitea o descarta primero."
  fi

  # El `fetch` NO puede fallar en silencio: sin el se juzga contra una
  # `origin/main` rancia, y eso es un dato viejo disfrazado de dato — la clase de
  # mentira que persigue la regla de oro 7. Si no hay red, la guardia se niega en
  # vez de dar por bueno lo que no pudo comprobar.
  git fetch -q origin main \
    || guardas_fallo "${componente}: no se pudo hacer 'git fetch origin main'. Sin eso, comparar contra origin/main seria comparar contra una copia vieja; la guardia NO pasa por no poder mirar."

  local sin_pushear
  sin_pushear="$(git log origin/main..main --oneline)"
  [ -z "$sin_pushear" ] || guardas_fallo "$(printf '%s: main tiene commits SIN PUSHEAR, asi que el CI no los ha visto:\n%s' "$componente" "$sin_pushear")"

  # A-1 pide main pusheado Y CON CI VERDE. La mitad del CI depende de `gh`, y sin
  # el no se puede comprobar. Que eso pase EN SILENCIO seria un fallback
  # haciendose pasar por un OK: la guardia quedaria a media potencia sin que nadie
  # lo supiera. Se sigue —negarse dejaria sin desplegar a una maquina sin `gh`,
  # que es una decision mas grande que esta ficha— pero se dice.
  if command -v gh >/dev/null 2>&1; then
    local ci
    ci="$(gh run list --branch main -L 1 --json conclusion -q '.[0].conclusion' 2>/dev/null || echo "")"
    [ "$ci" = "success" ] \
      || guardas_fallo "${componente}: el ultimo CI de main no esta en verde (estado: ${ci:-desconocido}). A-1 pide main pusheado Y con CI verde."
  else
    echo "⚠️  ${componente}: sin 'gh' no se pudo comprobar el CI de main. A-1 se aplica A MEDIAS: se verifico la rama y que este pusheada, NO que el CI este en verde." >&2
  fi
}

# El mensaje del rechazo. La pregunta util el 27-ago no era «donde estoy» —eso ya
# lo sabia— sino «QUE ME FALTA»: por eso enumera los commits que main tiene y este
# arbol no, que es exactamente lo que no se habria desplegado.
_guardas_por_que_no_main() {
  local componente="$1" rama="$2" falta
  git fetch -q origin main 2>/dev/null || true
  falta="$(git log --oneline HEAD..origin/main 2>/dev/null | head -10)"
  printf '%s: se despliega desde main, y el arbol esta en %s (%s).\n' \
    "$componente" "${rama:-DETACHED}" "$(git rev-parse --short HEAD)"
  if [ -n "$falta" ]; then
    printf '  Lo que main tiene y esta rama NO —o sea, lo que este despliegue se dejaria fuera—:\n%s\n' "$falta"
  else
    printf '  Esta rama no va por detras de main; aun asi no es main, y lo que se despliega tiene que ser lo que el CI vio.\n'
  fi
  printf '  Salidas: `git checkout main && git pull`, o `--desde-esta-rama` si de verdad quieres desplegar esta rama a dev.\n'
  printf '  Para volver atras NO hace falta esto: un rollback se hace con `CLOUD_TAG=<sha-anterior>`, desde main.\n'
}
