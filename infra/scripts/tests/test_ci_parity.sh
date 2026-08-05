#!/usr/bin/env bash
# Test de PARIDAD local ↔ CI: lo que exige el CI tiene que poder correrse con `make`.
#
# Por qué existe: ni `make lint` ni `make test` corrían el build de web
# (`tsc --noEmit && vite build`), que el job `web` de ci.yml sí corre. Un error de
# tipos en web/src pasaba `make lint && make test` en VERDE en local y reventaba el
# PR en CI. Es la misma familia de fallo que ya se cerró dos veces a mano: el job
# `mobile` existía en CI desde T-2.00 y el Makefile lo ignoraba (por ahí se coló un
# merge en rojo a main el 2026-07-18), y el `ruff format --check` de api tampoco
# estaba. Cada vez que CI gana un paso, alguien tiene que acordarse de espejarlo en
# el Makefile; este test quita el "acordarse".
#
# QUÉ COMPRUEBA
#   1. Extrae todos los `run:` de .github/workflows/ci.yml y exige que cada paso de
#      CALIDAD tenga un comando equivalente dentro de un target de calidad del
#      Makefile (lint, test, drift, build).
#   2. La dirección inversa para los gates de este directorio: todo test_*.sh de
#      infra/scripts/tests/ tiene que correr TAMBIÉN en ci.yml. Un gate que sólo
#      viva en `make test` no protege un PR, porque CI no ejecuta `make test`.
#   3. Que exista el agregador `verify` y que web declare el script `typecheck` que
#      reutiliza su `build`.
#
# QUÉ CUENTA COMO "PASO DE CALIDAD"
#   Todo `run:` que una edición del código fuente pueda poner en rojo: lint, formato,
#   typecheck, tests, build y gates de drift.
#
# QUÉ SE EXCLUYE A PROPÓSITO (tabla EXCLUIDOS, cada entrada con su razón)
#   · Instalación de dependencias / toolchain (`npm ci`, `uv sync`,
#     `pip install -e ".[dev]"`): no son gates de calidad; su equivalente local es
#     `make install`, y duplicarlos en cada target sólo alargaría la corrida.
#   · Pasos `uses:` (actions/checkout, setup-node, setup-python, setup-uv,
#     setup-terraform): no son comandos, no hay nada que espejar. El parser sólo mira
#     `run:`, así que quedan fuera sin necesidad de listarlos.
#   · Arranque de servicios (el bloque `services:` del job api): en local lo cubre
#     `docker compose` a través del target `test-db`, del que `make test` depende.
#   · Guardas del entorno del runner (`node --version`): comprueban el runner, no el
#     código. En local `node` es prerrequisito de `npm` y falla solo.
#   · `terraform init` + `validate` (bootstrap y envs/dev) del job `infra`: `validate`
#     exige un `init` que DESCARGA providers, y lintar no puede depender de la red.
#     Decisión consciente, no olvido. (`terraform fmt -check` SÍ está cubierto: es
#     instantáneo y offline, y vive en `make lint` desde T-2.62.)
#   Los excluidos se imprimen al final de cada corrida para que sigan siendo visibles.
#   La tabla es por COMANDO, no por job: un paso nuevo de terraform (o cualquier otro)
#   entra como no cubierto y pone este test en rojo hasta que alguien decida qué hacer.
#
# QUÉ NO ES UN COMANDO (y por qué el filtro es tan estrecho)
#   Dentro de un `run: |` hay líneas que no ejecutan nada y pedirles espejo local sólo
#   produce ruido: comentarios de shell, `set -euo pipefail`, las palabras de control
#   (`do`/`done`/`fi`/`then`/`else`), la cabecera de un `for`, un `echo` suelto, y el
#   CUERPO y el terminador de un heredoc (son DATOS). Todo eso se descarta.
#   Lo que NO se descarta, a propósito: la línea que ABRE el heredoc. `python - <<'EOF'`
#   es una forma real de meter un gate de calidad en CI, y volverla invisible sería
#   justo el agujero que este fichero persigue. Única excepción, por ser inequívoca:
#   `cat`/`tee` con redirección a fichero y sin tubería — eso es escribir un blob,
#   no comprobar nada.
#
# CÓMO EMPAREJA (robusto a espacios y a reordenamientos)
#   · El Makefile se lee con sus variables expandidas ($(WEB_DIR) → web).
#   · A cada receta se le quita el comentario final (` # …`, respetando comillas) y
#     después se parte por `&&`; un `cd X` fija el directorio de los comandos que le
#     siguen en esa misma línea.
#   · De cada comando se quitan los prefijos que no cambian QUÉ se ejecuta
#     (`VAR=valor`, `uv run`, `npx`), y se resuelven `git -C X` y `terraform -chdir=X`
#     a un directorio.
#   · Un paso de CI está CUBIERTO si existe un comando del Makefile en el MISMO
#     directorio cuyos tokens son un SUPERCONJUNTO de los suyos. Así
#     `terraform init -backend=false -input=false >/dev/null` cubre a
#     `terraform init -backend=false`, y un flag extra en local no rompe el test.
#   · …salvo que ese flag extra ANULE el comando: `--fix`, `--write`, `|| true`,
#     `-k`, `--ignore=…`, el prefijo `-` de make… (tabla NEUTRALIZADORES, con la
#     razón de cada uno). Sin ese filtro, `ruff check .` → `ruff check --fix .`
#     dejaba el gate en verde mientras CI se quedaba en rojo.
#   · …y salvo que el comando no llegue a EJECUTARSE. La receta se juzga ENTERA, no
#     trozo a trozo: si un trozo anterior del mismo `&&` es una guarda (`command -v`,
#     `test`, `[`, `if`…), lo que va detrás es condicional y no cubre nada; y si la
#     cabeza del propio trozo es `echo`/`printf`/`true`/`:`, el comando se imprime o
#     se ignora, no se corre. Reproducido 4/4 en verde con exit 0 antes del arreglo:
#       · `command -v terraform >/dev/null && terraform fmt -check -recursive …`
#         (la guarda "no falles si el compañero no tiene terraform" deja `make lint`
#         en verde en una máquina sin terraform mientras CI se queda en rojo — la
#         familia de fallo EXACTA que este gate existe para impedir)
#       · `test -f .lintme && terraform fmt -check -recursive …`
#       · `echo uv run ruff check .`   · `true uv run ruff check .`
#     `||` ya se cazaba porque `partir()` no corta por `||`: el token queda dentro
#     del trozo y NEUTRALIZADORES lo ve. Esa asimetría era la pista.
#   · La comparación es por conjunto de tokens: el orden de los pasos y los espacios
#     son irrelevantes.
#
# LA GUARDA QUE SOSTIENE TODO LO DEMÁS (y hasta dónde llega — leer entero)
#   El emparejamiento vale lo que valga el parser, y un parser ciego da verde sin
#   comprobar nada. Por eso hay una invariante RELATIVA al propio ci.yml: cada
#   clave `run:` que el fichero declara tiene que haber sido consumida por el
#   parser, o el test sale en rojo con el número de línea.
#
#   QUÉ CAZA, medido: cegar el parser al job `web` entero, cegarlo a un solo paso y
#   revertirlo a indentación fija — las tres salen en rojo con línea. Ésa es la clase
#   de fallo que nos mordió tres veces (ceguera ESTRUCTURAL: jobs, pasos, sangría).
#
#   QUÉ NO CAZA, y hay que decirlo: la invariante NO es una red independiente. Es una
#   SEGUNDA implementación de la misma heurística léxica (encontrar la clave `run:`
#   en una línea). Cuando el parser y ella comparten la ceguera, las dos callan a la
#   vez. Pasó con dos formas de YAML perfectamente válidas, verdes con exit 0 y con
#   la invariante bajando de 33/33 a 32/32 sin quejarse:
#       "run": bandit -r src        (clave entrecomillada)
#       run:                        (escalar plano con el valor en la línea siguiente)
#         bandit -r src
#   Las dos están cerradas ahora, pero la LECCIÓN no se cierra: cualquier forma futura
#   que ninguna de las dos lecturas reconozca sigue siendo un verde mentiroso.
#
#   ¿Y una señal genuinamente independiente? La única que existe es un parser de YAML
#   de verdad, y PyYAML está descartado a conciencia (ver "POR QUÉ LITERAL" más abajo):
#   no está garantizado en el `python3` del sistema ni en el runner, y un fallback
#   "úsalo si está" haría que local y CI comprobaran cosas distintas — la familia de
#   fallo que este gate existe para impedir, reintroducida en el vigilante.
#   Se evaluó y se DESCARTÓ una segunda red por job ("todo job tiene que producir al
#   menos un comando"): los únicos jobs que marcaría hoy son los legítimos que sólo
#   llevan `uses:` (workflow reutilizable, o un job de puras actions), o sea que
#   compraría un falso rojo garantizado a cambio de nada. Un gate que grita sin motivo
#   se acaba desactivando.
#   Lo que sí quedó, gratis: desde que la sección 2 lee los pasos que el parser extrajo
#   (en vez de hacer grep sobre el fichero), esa sección es un CANARIO del parser. Su
#   expectativa es un hecho conocido y cierto —ci.yml SÍ corre estos gates—, así que
#   cualquier ceguera sobre el job `infra` sale como "ci.yml NO corre test_*.sh".
#
# LO QUE SIGUE ESCAPANDO (inventario honesto — un punto ciego declarado es un activo)
#   Esta es la última ronda sobre este fichero; el resto se documenta en vez de
#   perseguirse, porque es un test de un test y el regreso puede ser infinito.
#   FALSOS VERDES conocidos (el gate calla y debería hablar):
#     1. Workflows REUTILIZABLES: un job `uses: ./.github/workflows/x.yml` mete pasos
#        que este fichero no mira — sólo lee ci.yml. Limitación de alcance conocida y
#        aceptada, no defecto. Si algún día un gate de calidad se muda ahí, se pierde.
#     2. Otros workflows del directorio (e2e.yml y los que vengan): mismo motivo.
#     3. Pasos con `if:` — un paso condicionado sigue contando como paso; y al revés,
#        un `if: false` en CI no se detecta. La paridad se juzga sobre el texto.
#     4. Matrices (`strategy.matrix`) y `${{ … }}` sin expandir: el comando se compara
#        con la plantilla literal, así que un `run: ${{ matrix.cmd }}` es opaco.
#     5. Cualquier forma de escribir la clave `run` que ni el parser ni `declara_run`
#        reconozcan (ver arriba: comparten heurística). Hoy se cubren bloque, lista
#        compacta, clave entrecomillada y escalar plano multilínea.
#     6. `cd` DENTRO de un `run: |`: el parser no lo sigue (sí lo sigue en el
#        Makefile). Un `cd x && lint` dentro de un bloque se juzga en el wd del job.
#     7. La lista de GUARDAS y de NEUTRALIZADORES es enumerativa: una guarda escrita
#        de otra forma (`pgrep`, `[ -x … ]` con otro nombre, una función de make)
#        vuelve a esconder el comando. Ampliar la lista cuando aparezca.
#     8. El desentrecomillado de `escalar()` es de un solo nivel y sin escapes: un
#        `run: "a \"b\""` o un `'it''s'` se comparan mal. No pasa hoy y arreglarlo
#        bien exige un lexer de YAML, que es la línea que no cruzamos.
#     9. `comandos_utiles()` descarta líneas (andamio de shell, cuerpo de heredoc,
#        `echo` suelto): cada una es un sitio donde esconder un gate. El filtro se
#        mantiene estrecho por eso — un `echo` con `>`/`|`/`;`/`&` SÍ cuenta, y el
#        `python - <<'EOF'` que abre un heredoc también. Verificado con mutación.
#   FALSOS ROJOS conocidos (el gate grita; falla del lado seguro y con mensaje):
#    10. Estilo de FLUJO: `steps: [{name: X, run: y}]`, `defaults: {run: {…}}`.
#        Anclas/alias YAML (`&api` / `*api`) y claves de merge (`<<:`).
#    11. `run: |2` y demás indicadores de indentación explícitos: mensaje dedicado.
#    12. Un heredoc abierto con algo que no sea `cat`/`tee` a fichero (a propósito).
#    13. Rutas escritas distinto en los dos lados: sólo se normaliza el `./` inicial.
#        `bash $(PWD)/x.sh` o una ruta con `..` siguen sin emparejar.
#   FUERA DE ALCANCE por definición: que el comando espejado haga lo mismo. Esto
#   compara TEXTO. Si `make lint` invoca un `npm run lint` cuyo script en package.json
#   está vacío, la paridad sale verde. Eso lo vigilan los tests de cada suite.
#
# Corre con: bash infra/scripts/tests/test_ci_parity.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
CI="$ROOT/.github/workflows/ci.yml"
MK="$ROOT/Makefile"
WEB_PKG="$ROOT/web/package.json"

fallos=0
ok() { printf '  ok   %s\n' "$1"; }
fallo() { printf '  FALLO %s\n' "$1" >&2; fallos=$((fallos + 1)); }
nota() { printf '  --   %s\n' "$1"; }

check() { # <descripcion> <esperado> <obtenido>
  if [ "$2" = "$3" ]; then ok "$1"; else
    fallo "$1"
    printf '        esperado: %s\n        obtenido: %s\n' "$2" "$3" >&2
  fi
}

for f in "$CI" "$MK" "$WEB_PKG"; do
  [ -f "$f" ] || {
    printf 'no existe %s\n' "$f" >&2
    exit 1
  }
done

# ---------------------------------------------------------------------------
# 1. Cada paso de calidad de ci.yml tiene cobertura en un target del Makefile
# ---------------------------------------------------------------------------
echo "== cada paso de calidad de ci.yml se puede correr con make =="

SALIDA="$(
  python3 - "$CI" "$MK" <<'PYFIN'
import posixpath
import re
import shlex
import sys

CI_PATH, MK_PATH = sys.argv[1], sys.argv[2]

# Targets del Makefile que cuentan como cobertura. Un comando escondido en `fmt`
# o en `dev` NO cubre nada: `fmt` escribe en vez de comprobar y `dev` es interactivo.
TARGETS_DE_CALIDAD = ("lint", "test", "drift", "build")

# Pasos de CI que NO exigen espejo local, con su razón (ver cabecera del script).
EXCLUIDOS = {
    "npm ci": "instalación de dependencias (equivale a `make install`)",
    "npm install": "instalación de dependencias (equivale a `make install`)",
    'python -m pip install -e ".[dev]"': "instalación de dependencias (equivale a `make install`)",
    "uv sync": "instalación de dependencias (equivale a `make install`)",
    "node --version": "guarda del entorno del runner, no del código",
    # `validate` EXIGE un `init` previo que DESCARGA providers: meterlo en `lint` haría
    # que no se pueda lintar sin red. Decisión consciente de T-2.62, no olvido.
    "terraform -chdir=infra/terraform/bootstrap init -backend=false": "queda fuera: `init` descarga providers (red) y `lint` tiene que poder correr offline",
    "terraform -chdir=infra/terraform/bootstrap validate": "queda fuera: exige el `init` con red de la línea anterior",
    "terraform -chdir=infra/terraform/envs/dev init -backend=false": "queda fuera: `init` descarga providers (red) y `lint` tiene que poder correr offline",
    "terraform -chdir=infra/terraform/envs/dev validate": "queda fuera: exige el `init` con red de la línea anterior",
}


def norm(texto):
    return " ".join(texto.split())


def dir_norm(d):
    return posixpath.normpath(d) if d else "."


def sin_comentario(texto):
    """Quita el comentario final (` # …`) respetando lo que va entre comillas.

    Sirve para las DOS superficies, porque las dos lo cortan igual: un escalar
    plano de YAML (`run: npm run lint # ojo`) y una línea de receta de make, que
    acaba en un shell. Sin esto, el `#` y las palabras del comentario entraban
    como TOKENS del comando y el paso salía en falso ROJO — "ningún target de
    calidad corre `npm run lint # ojo`" —, un mensaje que invitaba a ampliar
    EXCLUIDOS, que es exactamente lo contrario de lo que queremos.
    """
    fuera = []
    comilla = None
    for i, c in enumerate(texto):
        if comilla is not None:
            if c == comilla:
                comilla = None
        elif c in "'\"":
            comilla = c
        elif c == "#" and (i == 0 or texto[i - 1] in " \t"):
            break
        fuera.append(c)
    return "".join(fuera).rstrip()


def escalar(valor):
    """Escalar YAML de UNA línea → el comando que el shell vería.

    Desentrecomilla y quita el comentario final. Sin desentrecomillar,
    `run: "npm run lint"` le llegaba a `shlex` como UN token con espacios
    (`{'npm run lint'}`), que nunca es subconjunto de `{npm, run, lint}`: falso
    ROJO. Un escalar PLANO de YAML no puede empezar por comilla, así que mirar
    el primer carácter es suficiente para distinguirlos.
    """
    v = valor.strip()
    if v[:1] in ("'", '"'):
        fin = v.rfind(v[0])
        if fin > 0:
            return v[1:fin]
    return sin_comentario(v)


# --- Qué líneas de un `run: |` NO son comandos ------------------------------
# Ver "QUÉ NO ES UN COMANDO" en la cabecera. El filtro es estrecho a propósito:
# cada línea que se descarta es un sitio donde esconder un gate.
RE_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
RE_VUELCA_A_FICHERO = re.compile(r"^(cat|tee)\b[^|]*>")
RE_ANDAMIO = re.compile(r"^(set\s+[-+]|for\b|true\s*$|:\s*$)")
RE_ECO = re.compile(r"^(echo|printf)\b")
ANDAMIO_EXACTO = {"do", "done", "fi", "then", "else", "elif", "esac", ";;", "{", "}", "(", ")"}


def comandos_utiles(lineas):
    fuera = []
    fin_heredoc = None
    for bruta in lineas:
        s = bruta.strip()
        if fin_heredoc is not None:  # cuerpo del heredoc: son DATOS
            if s == fin_heredoc:
                fin_heredoc = None
            continue
        if not s or s.startswith("#"):
            continue
        s = sin_comentario(s)
        if not s:
            continue
        m = RE_HEREDOC.search(s)
        if m:
            fin_heredoc = m.group(2)
            if RE_VUELCA_A_FICHERO.match(s):
                continue  # `cat > f <<'EOF'` escribe un blob; no comprueba nada
        if s in ANDAMIO_EXACTO or RE_ANDAMIO.match(s):
            continue
        if RE_ECO.match(s) and not re.search(r"[|><;&]", s):
            continue
        fuera.append(s)
    return fuera


def cabeza(cmd):
    """Primer token REAL de un comando, saltando los prefijos `VAR=valor`."""
    try:
        toks = shlex.split(cmd)
    except ValueError:
        toks = cmd.split()
    while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
        toks.pop(0)
    return toks[0] if toks else ""


def partir(texto):
    """Una receta/`run:` puede encadenar varios comandos con `&&`."""
    return [p.strip() for p in texto.split("&&") if p.strip()]


def nucleo(cmd, wd):
    """(directorio, tokens) quitando lo que no cambia QUÉ se ejecuta."""
    try:
        toks = shlex.split(cmd)
    except ValueError:
        toks = cmd.split()
    d = wd
    # prefijos de entorno: DATABASE_URL=... / GPIOZERO_PIN_FACTORY=mock
    while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
        toks.pop(0)
    # lanzadores: `uv run pytest` == `pytest`, `npx expo lint` == `expo lint`
    if len(toks) >= 2 and toks[0] == "uv" and toks[1] == "run":
        toks = toks[2:]
    if toks and toks[0] == "npx":
        toks = toks[1:]
    # `bash ./infra/…/x.sh` y `bash infra/…/x.sh` son el mismo comando: el `./`
    # sobra en la comparación y sólo compraba un falso ROJO.
    toks = [t[2:] if t.startswith("./") and len(t) > 2 else t for t in toks]
    # `git -C X` y `terraform -chdir=X` son un `cd` disfrazado
    if len(toks) >= 3 and toks[0] == "git" and toks[1] == "-C":
        d = dir_norm(posixpath.join(d, toks[2]))
        toks = [toks[0]] + toks[3:]
    if len(toks) >= 2 and toks[0] == "terraform" and toks[1].startswith("-chdir="):
        d = dir_norm(posixpath.join(d, toks[1].split("=", 1)[1]))
        toks = [toks[0]] + toks[2:]
    return dir_norm(d), toks


# --- ci.yml: (job, nombre del paso, directorio, comando) ---------------------
# Parser deliberadamente literal (sin PyYAML) y RELATIVO a la indentación.
#
# POR QUÉ LITERAL: PyYAML no está garantizado ni en el `python3` del sistema ni en
# el runner `ubuntu-latest` donde el job `infra` corre este mismo script. Un
# parser que dependa de un paquete opcional comprobaría cosas DISTINTAS en local
# y en CI — que es exactamente la familia de fallo que este gate existe para
# impedir. Un solo camino de código en los dos lados, sin fallback silencioso.
#
# POR QUÉ RELATIVO: la versión anterior exigía indentación FIJA (job = 2, `- ` a
# 6, claves del paso a 8) y un job escrito en el estilo de lista compacto de YAML
# —el de los starter workflows oficiales de GitHub, con los `- ` al MISMO nivel
# que `steps:`— era INVISIBLE. Medido con control: un job `seguridad` con
# `run: bandit -r src` y sin espejo local daba, a 4 espacios, "34 pasos · todo en
# verde · exit 0"; el MISMO paso a 6 espacios daba "35 pasos · FALLO seguridad ·
# Bandit · exit 1". La única variable entre verde y rojo era la sangría, y PyYAML
# confirma que los dos ficheros son el mismo workflow. Variante parcial igual de
# grave: reindentando SÓLO el job `web`, el gate daba verde con 27 pasos sin
# comprobar nada de eslint/prettier/vitest/build/tokens.
#
# LAS FORMAS DE ESCRIBIR LA CLAVE que sí lee (todas son YAML válido y GitHub
# ejecuta todas igual; las tres últimas se le escapaban y daban verde con exit 0):
#     run: cmd                   run: "cmd"  /  run: cmd # nota
#     "run": cmd  /  'run': cmd  (clave entrecomillada)
#     run:            + cmd en la(s) línea(s) siguientes, más indentadas
#     run: # nota     + cmd debajo (el comentario NO es el valor)
# La de FLUJO (`- {name: X, run: y}`) NO la lee, y por eso mismo tiene que salir
# en rojo por la invariante en vez de desaparecer.
#
# La red de última instancia NO es este parser: es la invariante de más abajo.
# Sus límites están escritos en la cabecera, sección "LA GUARDA QUE SOSTIENE
# TODO LO DEMÁS" — leerla antes de confiar en ella.
#
# Devuelve (pasos, líneas con clave `run:` consumidas, líneas de contenido de los
# bloques, pasos con un `run:` que el parser reconoce pero no sabe leer).
RE_CLAVE_PASO = re.compile(r"""^(?P<c>["']?)(?P<k>[A-Za-z][A-Za-z0-9_-]*)(?P=c):\s*(?P<v>.*)$""")
RE_INDICADOR = re.compile(r"^[|>][+-]?$")
RE_INDICADOR_RARO = re.compile(r"^[|>][0-9+-]+$")


def leer_ci(path):
    pasos = []
    run_vistos = set()  # nº de línea de cada clave `run:` que el parser consumió
    lineas_bloque = set()  # nº de línea del CONTENIDO de los bloques de `run:`
    sin_leer = []  # `run:` reconocidos como clave pero con un valor ilegible
    job = None
    job_wd = "."
    jobs_ind = None  # indentación de la clave raíz `jobs:`
    job_ind = None  # indentación de los nombres de job
    steps_ind = None  # indentación de la clave `steps:` del job en curso
    item_ind = None  # indentación del `- ` de los pasos (puede == steps_ind)
    key_ind = None  # indentación de las claves DENTRO del paso
    en_steps = False
    paso = None
    bloque = None

    def cerrar_bloque():
        nonlocal bloque
        if bloque is not None and paso is not None:
            if bloque["plano"]:
                # Escalar multilínea sin indicador: YAML lo PLIEGA en un solo
                # comando. Puede venir entrecomillado, así que pasa por escalar().
                texto = " ".join(ln.strip() for ln in bloque["lineas"] if ln.strip())
                paso["cmds"].extend(comandos_utiles([escalar(texto)]))
            else:
                paso["cmds"].extend(comandos_utiles(bloque["lineas"]))
        bloque = None

    def flush():
        nonlocal paso
        cerrar_bloque()
        if paso is not None:
            wd = paso["wd"] if paso["wd"] is not None else job_wd
            for cmd in paso["cmds"]:
                pasos.append((job, paso["name"] or cmd, wd, cmd))
        paso = None

    for nlinea, raw in enumerate(open(path, encoding="utf-8"), 1):
        linea = raw.rstrip("\n")
        if bloque is not None:
            if not linea.strip():
                bloque["lineas"].append("")
                lineas_bloque.add(nlinea)
                continue
            ind = len(linea) - len(linea.lstrip(" "))
            if bloque["indent"] is None:
                bloque["indent"] = ind
            if ind >= bloque["indent"]:
                bloque["lineas"].append(linea.strip())
                lineas_bloque.add(nlinea)
                continue
            cerrar_bloque()
        if not linea.strip():
            continue
        ind = len(linea) - len(linea.lstrip(" "))
        if linea.lstrip().startswith("#"):
            continue
        if jobs_ind is None:
            if re.match(r"^[ ]*jobs:\s*$", linea):
                jobs_ind = ind
            continue
        if job_ind is None:
            job_ind = ind  # la 1ª clave bajo `jobs:` fija el nivel de los jobs
        if ind < job_ind:  # se cerró el mapa de jobs
            flush()
            job, en_steps = None, False
            continue
        es_item = linea.lstrip().startswith("- ") or linea.strip() == "-"
        if en_steps and ind <= steps_ind and not (es_item and ind >= steps_ind):
            flush()  # una clave del job al nivel de `steps:` cierra los pasos
            en_steps = False
        if ind == job_ind:
            m = re.match(r"^([A-Za-z0-9_-]+):\s*$", linea.strip())
            if m:
                flush()
                job, job_wd, en_steps = m.group(1), ".", False
                steps_ind = item_ind = key_ind = None
                continue
        if job is None:
            continue
        if not en_steps:
            if linea.strip() == "steps:":
                flush()
                en_steps = True
                steps_ind, item_ind, key_ind = ind, None, None
            else:
                km = re.match(r"^(working-directory):\s*(\S.*)$", linea.strip())
                if km:  # defaults.run.working-directory del job
                    job_wd = km.group(2)
            continue
        rest = None
        if es_item and ind >= steps_ind and (item_ind is None or ind == item_ind):
            flush()
            item_ind = ind
            paso = {"name": None, "wd": None, "cmds": []}
            cuerpo = linea.lstrip()[1:]  # quita el `-`
            desplaz = len(cuerpo) - len(cuerpo.lstrip(" "))
            # Las claves del paso se alinean con el 1er carácter tras el guion.
            # `- name:` → key_ind = ind+2; `-` solo en su línea → lo fija la 1ª clave.
            key_ind = ind + 1 + desplaz if cuerpo.strip() else None
            rest = cuerpo.strip()
            if not rest:
                continue
        elif paso is not None and key_ind is None and ind > item_ind:
            key_ind = ind
            rest = linea.strip()
        elif paso is not None and key_ind is not None and ind == key_ind:
            rest = linea.strip()
        if rest is None:
            continue
        km = RE_CLAVE_PASO.match(rest)
        if not km:
            continue
        clave, valor = km.group("k"), km.group("v")
        if clave == "name" and paso is not None:
            paso["name"] = escalar(valor)
        elif clave == "working-directory" and paso is not None:
            paso["wd"] = escalar(valor)
        elif clave == "run" and paso is not None:
            run_vistos.add(nlinea)
            if RE_INDICADOR.match(valor.strip()):
                bloque = {"indent": None, "lineas": [], "plano": False}
            elif RE_INDICADOR_RARO.match(valor.strip()):
                sin_leer.append((job, paso["name"], nlinea, valor.strip()))
            elif escalar(valor):
                paso["cmds"].extend(comandos_utiles([escalar(valor)]))
            else:
                # `run:` SIN valor propio dentro de un PASO = escalar plano cuyo
                # valor va en la(s) línea(s) siguiente(s), más indentadas. (El
                # `run:` de `defaults:` nunca llega aquí: no es clave de paso.)
                # Forma que la gente escribe sin pensar y que daba verde con
                # exit 0. Se comprueba con `escalar()` y no con `valor.strip()`
                # porque `run: # comentario` TAMBIÉN es un `run:` sin valor: el
                # comando está debajo, y mirando el texto crudo el paso entero
                # se volvía invisible (verde con exit 0, medido).
                bloque = {"indent": None, "lineas": [], "plano": True}
    flush()
    return pasos, run_vistos, lineas_bloque, sin_leer


# Invariante RELATIVA AL PROPIO FICHERO: cada clave `run:` que declara ci.yml tiene
# que haber sido consumida por el parser. Sustituye a la guarda vieja —un umbral
# absoluto, `pasos_vistos >= 15`— que no detectaba nada: con el job compacto
# invisible el contador seguía en 34 y 34 >= 15 daba verde.
#
# El reconocimiento está ANCLADO al principio de la línea (tras la indentación y
# tras los guiones de lista). El patrón antiguo aceptaba `run:` precedido de
# CUALQUIER espacio, así que un `name:` que CONTUVIERA `run:` —p. ej.
# `- name: "Paridad (make cubre cada run: de ci.yml)"`, que es justo como se
# llamaría el paso en este repo— contaba como una clave `run:` más y ponía la
# invariante en rojo sin motivo. El estilo de FLUJO se busca aparte y sólo en
# líneas que llevan `{`.
#
# Se descuentan las líneas de CONTENIDO de un bloque (ahí un `run:` sería texto del
# script, no una clave del workflow). Un `run:` SIN valor es ambiguo: puede ser el
# `defaults: run:` (un MAPA, sin comando) o un escalar plano con el valor debajo;
# se distingue mirando si la línea siguiente, más indentada, parece `clave: valor`.
RE_RUN_CLAVE = re.compile(r"""^[ \t]*(?:-[ \t]+)*(?P<c>["']?)run(?P=c):(?P<v>.*)$""")
RE_RUN_FLUJO = re.compile(r"""[{,][ \t]*["']?run["']?:[ \t]*\S""")
RE_CLAVE_YAML = re.compile(r"""^["']?[A-Za-z_][A-Za-z0-9_.-]*["']?:(\s|$)""")


def declara_run(path, lineas_bloque):
    lineas = open(path, encoding="utf-8").read().splitlines()
    declaradas = set()
    for i, raw in enumerate(lineas):
        nlinea = i + 1
        if nlinea in lineas_bloque or raw.lstrip().startswith("#"):
            continue
        if "{" in raw and RE_RUN_FLUJO.search(raw):
            declaradas.add(nlinea)
            continue
        m = RE_RUN_CLAVE.match(raw)
        if not m:
            continue
        if sin_comentario(m.group("v")).strip():
            declaradas.add(nlinea)
            continue
        ind = len(raw) - len(raw.lstrip(" "))
        for sig in lineas[i + 1:]:
            if not sig.strip() or sig.lstrip().startswith("#"):
                continue
            if len(sig) - len(sig.lstrip(" ")) > ind and not RE_CLAVE_YAML.match(sig.strip()):
                declaradas.add(nlinea)  # escalar plano: el comando va debajo
            break
    return declaradas


# --- Tokens que ANULAN la cobertura -----------------------------------------
# La regla de emparejamiento es de SUPERCONJUNTO (un flag extra en local no
# rompe el test: así `terraform init -backend=false -input=false >/dev/null`
# cubre al `terraform init -backend=false` de CI). Eso es lo que la hace robusta
# y, tal cual, era también su agujero: había flags extra que INVIERTEN o RECORTAN
# la semántica del comando y aun así daban el paso por cubierto. Reproducido 5/5
# sobre el Makefile real, todas en verde con exit 0:
#   · `ruff check .` → `ruff check --fix .`  (local REESCRIBE y sale 0; CI, que
#     corre `ruff check .`, se queda en rojo)
#   · `ruff check . || true`                 (el gate local no puede fallar)
#   · `-terraform fmt -check ...`            (el `-` de make ignora el fallo)
#   · `pytest -q -m "not perf" --ignore=tests/rls -k "not slow"` (se vacía la
#     suite local sin que el gate lo note)
#   · `npm run format:check --write`
# Control inverso, para que la regla no sea vacua: QUITAR un token sí se caza
# (`ruff format --check .` → `ruff format .` ⇒ FALLO api · Formato (ruff)).
#
# Se deniega por token EXTRA, no por token presente: si CI mismo usara `--fix`,
# la paridad exigiría `--fix` en local y este filtro no aplicaría.
NEUTRALIZADORES = {
    # (A) convierten el rojo en verde o escriben en vez de comprobar
    "--fix": "reescribe los ficheros en vez de comprobarlos, y sale 0",
    "--fix-only": "reescribe los ficheros en vez de comprobarlos, y sale 0",
    "--unsafe-fixes": "reescribe los ficheros en vez de comprobarlos, y sale 0",
    "--write": "escribe el formato en vez de comprobarlo, y sale 0",
    "-w": "escribe el formato en vez de comprobarlo, y sale 0",
    "--exit-zero": "fuerza el código de salida 0: el gate no puede fallar",
    "--passWithNoTests": "sale 0 aunque no se ejecute NINGÚN test",
    "--if-present": "sale 0 si el script no existe: un typo lo vuelve un no-op",
    "--no-verify": "se salta los hooks de verificación",
    "--collect-only": "no ejecuta los tests, sólo los recolecta",
    "--co": "no ejecuta los tests, sólo los recolecta",
    "--dry-run": "no ejecuta nada",
    "--no-error-on-unmatched-pattern": "sale 0 si el glob no encaja con nada",
    "||": "deja pasar el fallo del comando anterior (el `|| true` clásico)",
    ";": "descarta el código de salida del comando anterior",
    "|": "en una tubería el código de salida es el del ÚLTIMO comando",
    "&": "lanzar en segundo plano devuelve 0 al instante",
    # (B) recortan en silencio LO QUE se comprueba: verde local, rojo en CI
    "-k": "filtra qué tests corren: puede vaciar la suite local",
    "-t": "filtra qué tests corren: puede vaciar la suite local",
    "--onlyChanged": "corre sólo lo que cambió: no es lo que corre CI",
    "--changed": "corre sólo lo que cambió: no es lo que corre CI",
}
# Por prefijo, para cazar también la forma `--ignore=x` (`startswith`).
NEUTRALIZADORES_PREFIJO = {
    "--ignore": "excluye parte de lo que CI sí comprueba",
    "--exclude": "excluye parte de lo que CI sí comprueba",
    "--deselect": "excluye parte de lo que CI sí comprueba",
    "--testPathIgnorePatterns": "excluye parte de lo que CI sí comprueba",
    "--testNamePattern": "filtra qué tests corren: puede vaciar la suite local",
    "--maxfail": "corta la corrida: local puede no llegar a lo que CI sí corre",
    "--bail": "corta la corrida: local puede no llegar a lo que CI sí corre",
}
# `-x` (== `--maxfail=1`) queda FUERA a propósito: es demasiado ambiguo como
# token suelto (`bash -x`, `tar -x`) y meterlo compraría falsos ROJOS.


def neutraliza(extras):
    """(token, razón) del primer token extra que anula la cobertura, o None."""
    for tok in sorted(extras):
        if tok in NEUTRALIZADORES:
            return tok, NEUTRALIZADORES[tok]
        for pref, razon in NEUTRALIZADORES_PREFIJO.items():
            if tok.startswith(pref):
                return tok, razon
    return None


# --- Trozos del `&&` que impiden que el comando llegue a ejecutarse ----------
# `partir()` corta la receta por `&&` y antes se juzgaba cada trozo AISLADO, así
# que el prefijo desaparecía y una guarda del tipo "no falles si el compañero no
# tiene terraform instalado" dejaba `make lint` en verde en una máquina sin
# terraform mientras CI se quedaba en rojo. Ahora la receta se juzga entera: lo
# que va detrás de una guarda es CONDICIONAL y no cubre nada.
# Las dos listas son enumerativas; ampliarlas cuando aparezca otra forma.
GUARDAS = ("command", "test", "[", "[[", "if", "while", "until", "case", "type", "which", "hash", "grep")
NO_EJECUTAN = {
    "echo": "`echo` imprime el comando, no lo ejecuta",
    "printf": "`printf` imprime el comando, no lo ejecuta",
    "true": "`true` sale 0 ignorando sus argumentos: no ejecuta nada",
    "false": "`false` sale 1 ignorando sus argumentos: no ejecuta nada",
    ":": "`:` es el no-op del shell: ignora sus argumentos",
}


def prefijos_make(receta):
    """Consume los prefijos de receta de make y dice si estaba el `-`.

    El `-` de make significa "ignora el fallo de esta línea": una receta
    `-terraform fmt -check ...` NO puede poner `make lint` en rojo, o sea que no
    cubre nada. El código anterior hacía `lstrip("@-+")` y se lo comía sin más,
    así que esa mutación pasaba el gate en verde con exit 0.
    """
    i, ignora = 0, False
    while i < len(receta) and receta[i] in "@-+":
        ignora = ignora or receta[i] == "-"
        i += 1
    return receta[i:], ignora


# --- Makefile: comandos de los targets de calidad ---------------------------
def leer_makefile(path):
    txt = open(path, encoding="utf-8").read()
    txt = re.sub(r"\\\n[ \t]*", " ", txt)  # continuaciones
    variables = dict(re.findall(r"^([A-Z][A-Z0-9_]*)\s*[:?]?=\s*(.*)$", txt, re.M))
    for _ in range(5):
        for k, v in list(variables.items()):
            variables[k] = re.sub(
                r"\$\(([A-Z][A-Z0-9_]*)\)", lambda m: variables.get(m.group(1), m.group(0)), v
            )
    cmds = []
    target = None
    for linea in txt.splitlines():
        if linea.startswith("\t"):
            if target not in TARGETS_DE_CALIDAD:
                continue
            receta, ignora_fallo = prefijos_make(linea.lstrip("\t"))
            if not receta.strip() or receta.lstrip().startswith("#"):
                continue
            receta = re.sub(
                r"\$\(([A-Z][A-Z0-9_]*)\)",
                lambda m: variables.get(m.group(1), m.group(0)),
                receta,
            )
            receta = sin_comentario(receta)
            wd = "."
            guarda = None
            for sub in partir(receta):
                cd = re.match(r"^cd\s+(\S+)$", sub)
                if cd:  # `cd` no es una guarda: si falla, el repo está roto
                    wd = dir_norm(posixpath.join(wd, cd.group(1)))
                    continue
                cab = cabeza(sub)
                veto = NO_EJECUTAN.get(cab, guarda)
                cmds.append((sub, wd, ignora_fallo, veto))
                if guarda is None and cab in GUARDAS:
                    guarda = (
                        "va detrás de la guarda `%s` en la misma receta: si la guarda "
                        "falla en local el comando NO corre y make sigue en verde" % norm(sub)
                    )
            continue
        m = re.match(r"^([a-zA-Z][a-zA-Z0-9_.-]*):(?!=)", linea)
        target = m.group(1) if m else (None if linea.strip() else target)
    return cmds


pasos, run_vistos, lineas_bloque, sin_leer = leer_ci(CI_PATH)
declaradas = declara_run(CI_PATH, lineas_bloque)
mk = [nucleo(c, w) + (ignora, veto) for c, w, ignora, veto in leer_makefile(MK_PATH)]

# Guarda anti-silencio (ver `declara_run`): comparación RELATIVA al fichero, no
# un umbral absoluto. `perdidas` son las líneas `run:` que el parser no vio.
perdidas = sorted(declaradas - run_vistos)
print("COUNT\t%d" % len(pasos))
print(
    "INVARIANTE\t%d/%d\t%s"
    % (len(run_vistos), len(declaradas), ",".join(str(n) for n in perdidas))
)
# La sección 2 (los gates de este directorio corren también en CI) se resuelve
# con ESTOS comandos, no con un grep sobre el fichero: ver su cabecera.
for _job, _nombre, _wd, _cmd in pasos:
    print("RUNCMD\t%s\t" % norm(_cmd))

for job, nombre, nlinea, valor in sin_leer:
    print(
        "FALLO\t%s · %s\tci.yml línea %d: `run: %s` lleva un indicador de indentación "
        "explícito y este parser no lo lee, así que el comando del paso queda SIN "
        "comprobar. Escríbelo como `run: |` (la indentación normal de YAML basta)."
        % (job, nombre or "?", nlinea, valor)
    )

notas = []
for job, nombre, wd, cmd in pasos:
    for sub in partir(cmd):
        clave = norm(sub)
        if clave in EXCLUIDOS:
            notas.append((job, clave, EXCLUIDOS[clave]))
            continue
        d, toks = nucleo(sub, wd)
        cubierto = False
        rechazos = []
        for md, mtoks, ignora, veto in mk:
            if md != d or not set(toks) <= set(mtoks):
                continue
            # `shlex.join` para que el diagnóstico no pierda las comillas de
            # `-m "not perf"` y se pueda copiar y pegar tal cual.
            receta = ("-" if ignora else "") + shlex.join(mtoks)
            if ignora:
                rechazos.append((receta, "lleva el prefijo `-` de make: ignora el fallo"))
                continue
            if veto:
                rechazos.append((receta, veto))
                continue
            mal = neutraliza(set(mtoks) - set(toks))
            if mal:
                rechazos.append((receta, "`%s` %s" % mal))
                continue
            cubierto = True
            break
        etiqueta = "%s · %s" % (job, nombre)
        if cubierto:
            print("OK\t%s\t" % etiqueta)
        elif rechazos:
            print(
                "FALLO\t%s\tel Makefile corre `%s` en %s/, pero NO cubre `%s`: %s"
                % (etiqueta, rechazos[0][0], d, clave, rechazos[0][1])
            )
        else:
            print(
                "FALLO\t%s\tningún target de calidad (%s) corre `%s` en %s/"
                % (etiqueta, " ".join(TARGETS_DE_CALIDAD), clave, d)
            )

vistos = set()
for job, clave, razon in notas:
    if (clave, razon) in vistos:
        continue
    vistos.add((clave, razon))
    print("NOTA\t`%s` — %s\t" % (clave, razon))
PYFIN
)"

pasos_vistos=0
inv_par="0/0"
inv_perdidas=""
cmds_ci=""
while IFS=$'\t' read -r estado desc detalle; do
  case "$estado" in
  COUNT) pasos_vistos="$desc" ;;
  INVARIANTE)
    inv_par="$desc"
    inv_perdidas="$detalle"
    ;;
  RUNCMD) cmds_ci="$cmds_ci$desc"$'\n' ;;
  OK) ok "$desc" ;;
  FALLO)
    fallo "$desc"
    if [ -n "$detalle" ]; then printf '        %s\n' "$detalle" >&2; fi
    ;;
  NOTA) nota "$desc" ;;
  esac
done <<<"$SALIDA"

echo "== el parser vio TODOS los \`run:\` de ci.yml (un workflow reindentado no puede dar verde vacío) =="
inv_vistos="${inv_par%%/*}"
inv_declaradas="${inv_par##*/}"
if [ -n "$inv_perdidas" ]; then
  fallo "el parser sólo vio $inv_vistos de los $inv_declaradas pasos \`run:\` que declara ci.yml"
  printf '        invisibles en ci.yml, línea(s): %s\n' "$inv_perdidas" >&2
  printf '        El parser lee la clave `run` en bloque, en lista compacta, entrecomillada\n' >&2
  printf '        y con el valor en la línea siguiente; el estilo de FLUJO (`- {name: X,\n' >&2
  printf '        run: y}`), las anclas y los alias, no. O se reescribe ese paso en estilo\n' >&2
  printf '        de bloque, o hay que enseñárselo al parser: lo que NO vale es dejarlo\n' >&2
  printf '        invisible — un job entero sin espejo local pasaba en verde por dos\n' >&2
  printf '        espacios de sangría.\n' >&2
else
  ok "$inv_vistos/$inv_declaradas pasos \`run:\` vistos ($pasos_vistos comandos tras expandir los bloques \`|\`)"
fi
# Segundo cortafuegos, este sobre el FICHERO y no sobre el parser: si ci.yml se
# quedara casi sin pasos, la invariante de arriba seguiría cuadrando (0 == 0).
if [ "$inv_declaradas" -lt 15 ]; then
  fallo "ci.yml declara sólo $inv_declaradas pasos \`run:\` (esperados >=15): ¿se vació el workflow?"
fi

# ---------------------------------------------------------------------------
# 2. Dirección inversa: los gates de infra/scripts/tests/ corren TAMBIÉN en CI
# ---------------------------------------------------------------------------
# La sección 1 vigila que CI no gane pasos sin espejo local. Falta el reverso, y
# para este directorio en concreto es crítico: si este mismo script viviera sólo en
# `make test` —que CI no ejecuta— un PR podría romper la paridad local↔CI sin que
# CI se enterara. Sería reintroducir el fallo que T-2.62 cierra, un piso más arriba,
# y encima en el propio vigilante. Todo test_*.sh de este directorio va en los dos
# lados o no vale.
#
# Se busca sobre los COMANDOS QUE EL PARSER EXTRAJO, no sobre el fichero crudo.
# Con `grep` sobre el fichero, un paso COMENTADO contaba como presente:
#       # - name: Test de paridad local ↔ CI …
#       #   run: bash infra/scripts/tests/test_ci_parity.sh
# daba "ok ci.yml corre test_ci_parity.sh" con exit 0 — el chequeo que existe
# para que un gate no viva sólo en local se desactivaba comentando dos líneas, en
# silencio. Y al revés, un `run: |` legítimo (con `set -euo pipefail` y un
# `for`/`done` antes del `bash …`) daba un falso ROJO, porque la invocación no
# está en la línea del `run:`. Un solo cambio cierra el falso verde y el falso rojo.
# Efecto colateral BUENO: esta sección pasa a ser un canario del parser. Su
# expectativa es un hecho conocido y cierto —ci.yml SÍ corre estos gates—, así que
# si el parser se queda ciego sobre el job `infra`, esto grita.
echo "== los gates de infra/scripts/tests/ corren también en CI =="
for t in "$HERE"/test_*.sh; do
  nombre="$(basename "$t")"
  patron="(^|[[:space:];&|(])bash[[:space:]]+(\./)?infra/scripts/tests/${nombre//./\\.}([[:space:]]|$)"
  if printf '%s' "$cmds_ci" | grep -qE "$patron"; then
    ok "ci.yml corre $nombre"
  else
    fallo "ci.yml NO corre $nombre: sólo lo vigila 'make test', que CI no ejecuta"
  fi
done

# ---------------------------------------------------------------------------
# 3. Estructura: un solo comando local que replica CI
# ---------------------------------------------------------------------------
echo "== el Makefile expone \`build\` y un agregador \`verify\` =="
verify_deps="$(sed -n 's/^verify:[[:space:]]*//p' "$MK" | head -1)"
for dep in lint test build drift; do
  case " $verify_deps " in
  *" $dep "*) ok "verify incluye $dep" ;;
  *) fallo "verify NO incluye $dep (prerrequisitos: '${verify_deps:-<no existe el target verify>}')" ;;
  esac
done

phony="$(sed -n '/^\.PHONY:/,/[^\\]$/p' "$MK" | tr '\\\n' '  ')"
for t in build verify; do
  case " $phony " in
  *" $t "*) ok ".PHONY declara $t" ;;
  *) fallo ".PHONY NO declara $t (make no lo corre si alguien crea un fichero con ese nombre)" ;;
  esac
done

# ---------------------------------------------------------------------------
# 4. web: el typecheck es un script propio y el build lo sigue invocando
# ---------------------------------------------------------------------------
echo "== web declara \`typecheck\` y su \`build\` no pierde el chequeo de tipos =="
lee_script() { # <nombre>
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("scripts",{}).get(sys.argv[2],""))' \
    "$WEB_PKG" "$1"
}
check "web/package.json declara el script typecheck" "tsc --noEmit" "$(lee_script typecheck)"

build_script="$(lee_script build)"
case "$build_script" in
*"run typecheck"*) ok "el build de web REUTILIZA el script typecheck (no puede divergir de \`make lint\`)" ;;
*) fallo "el build de web no reutiliza el script typecheck (tsc suelto = dos fuentes de verdad): '$build_script'" ;;
esac
case "$build_script" in
*"vite build"*) ok "el build de web sigue empaquetando con vite" ;;
*) fallo "el build de web ya no llama a vite build: '$build_script'" ;;
esac

if [ "$fallos" -ne 0 ]; then
  printf '\n%d prueba(s) FALLARON\n' "$fallos" >&2
  exit 1
fi
printf '\ntodo en verde\n'
