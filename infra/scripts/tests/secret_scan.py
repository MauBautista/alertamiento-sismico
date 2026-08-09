#!/usr/bin/env python3
"""Barrido de secretos de TAKAB (T-2.86.c · hueco RO-6.a de la matriz).

Hasta hoy la regla de oro 6 —«nada de secretos hardcodeados; AWS Secrets Manager
o variables de entorno; nunca en git»— era la ÚNICA de las once que no tenía ni
un test, ni un paso de CI, ni un pre-commit. Se sostenía enteramente sobre la
disciplina de quien escribía el diff.

═══════════════════════════════════════════════════════════════════════════════
POR QUÉ ESTE ALCANCE: EL ÁRBOL DE TRABAJO ENTERO, NI EL DIFF NI EL HISTORIAL
═══════════════════════════════════════════════════════════════════════════════
Las tres opciones y por qué gana la de en medio:

  · Sólo el DIFF del PR — es lo que hace la mayoría, y no ve lo que YA está
    dentro. El día que se enciende, un secreto que lleva ocho meses en el árbol
    es invisible para siempre; y además el resultado depende del base ref, así
    que un squash, un rebase o un push directo a `main` lo dejan sin nada que
    mirar. Un gate cuyo veredicto cambia según cómo se integró la rama no es un
    gate.

  · Todo el HISTORIAL en cada PR — 395 commits y ~67 MB de `.git` hoy, y crece.
    Es lento, y sobre todo es RUIDOSO en el sentido que mata gates: encuentra
    ficheros de desarrollo borrados hace medio año, y el hallazgo no se puede
    arreglar en el PR que lo destapa (reescribir historia es un force-push, no
    un commit). Un rojo que el autor del PR no puede poner en verde se acaba
    saltando, y con él se salta todo lo demás.

  · El ÁRBOL DE TRABAJO ENTERO (rastreados + nuevos que git no ignora) ← el que
    corre en CI. Ve todo lo que hay dentro hoy, no sólo lo que cambió; es
    determinista (no depende del base ref); y es suficiente como gate de merge,
    porque un secreto NUEVO tiene que aterrizar en el árbol para llegar a
    `main`. Cuesta ~4 s sobre 1 300 ficheros.
    Lo de "+ nuevos" no es adorno: ver `rutas_rastreadas()`. Con `git ls-files`
    a secas, un fichero recién creado y sin `git add` era INVISIBLE en local y
    visible en CI — verde mentiroso en la máquina donde se escribe el código.

El historial NO queda sin barrer: se barre con `--historia`, fuera del camino
del merge. Es una operación de auditoría —se corre al abrir el repo a un
tercero, o cuando salta una sospecha—, no una que pague cada PR. La línea base
de este repo está registrada en la ficha de T-2.86.c.

LO QUE ESTE BARRIDO NO VE, dicho con esas palabras:
  · el historial (a menos que se lo pidas), por lo de arriba;
  · lo que nunca se rastreó: `.env`, `web/.env`, `edge.env` del Pi y todo lo
    que `.gitignore` esconde. Es lo correcto —esos ficheros EXISTEN para tener
    secretos—, pero significa que este gate no dice nada sobre ellos;
  · secretos que no tienen forma de secreto: una contraseña que sea una palabra
    del diccionario dentro de un YAML. Ninguna herramienta la ve, y fingir lo
    contrario es peor que declararlo;
  · ficheros binarios (se detectan por el byte NUL y se saltan enteros).

═══════════════════════════════════════════════════════════════════════════════
LA REGLA DE DISEÑO QUE HACE QUE ESTO SE SIGA MIRANDO EN LA SEMANA DOS
═══════════════════════════════════════════════════════════════════════════════
Este repo tiene contraseñas de desarrollo A PROPÓSITO: `takab_dev` en el DSN de
los tests y en el `docker-compose`, la raíz de MinIO, la llave que firma
`/dev/token`. Un barrido que las marque no sirve: nadie lo mira a la segunda
semana, y entonces tampoco ve el secreto de verdad.

De ahí las dos decisiones:

  1. LAS REGLAS SE ANCLAN A LA FORMA DEL SECRETO, NO AL NOMBRE DE AL LADO.
     `AKIA…`+16, `AC`+32 hex, `sk-…`, `-----BEGIN … PRIVATE KEY-----`: cosas
     que sólo puede haber emitido un proveedor. Se probó la vía contraria
     (marcar `token = …`, `secret = …`) contra el árbol real: 60 líneas, y las
     que más pesaban eran `token = au.make_token(...)` de la suite de auth.
     Eso es exactamente el ruido que desactiva un gate.

  2. LAS EXCLUSIONES SON POR VALOR, NO POR RUTA, Y CADA UNA LLEVA SU RAZÓN.
     Excluir `api/tests/` sería el camino fácil y es justo el que se pudre: a
     partir de ese día, un secreto de verdad dentro de esa carpeta no lo ve
     nadie. Excluir el VALOR `takab_dev` es preciso —da acceso a un contenedor
     local y a nada más, y ya está en claro en `ci.yml`— y no abre ninguna
     puerta futura. Toda entrada de `PERMITIDOS` se imprime al final de cada
     corrida, para que siga siendo visible que está ahí.
     No hay pragma de línea (`# permitido` y sigue) a propósito: silenciar el
     gate tiene que costar un cambio en esta tabla, que se ve en la revisión.

Sin dependencias: sólo `git` y el `python3` del sistema. Misma razón que
`test_ci_parity.sh` — nada que descargar en CI, un solo camino de código en
local y en el runner, y ningún fallback silencioso que haga que comprueben
cosas distintas.

Uso:
    python3 infra/scripts/tests/secret_scan.py              # árbol rastreado
    python3 infra/scripts/tests/secret_scan.py --historia   # auditoría, lenta
    python3 infra/scripts/tests/secret_scan.py --rutas a b  # ficheros sueltos
Salida: 0 limpio · 1 hallazgos · 2 error de uso.
"""

from __future__ import annotations

import argparse
import bisect
import re
import subprocess
import sys
from dataclasses import dataclass

# ───────────────────────────────────────────────────────────────────────────────
# REGLAS — cada una con la forma que sólo puede tener un secreto de ese emisor.
# `grupo` es el nº del grupo de captura que contiene el VALOR (0 = todo el match);
# es lo que se compara contra PERMITIDOS y contra los placeholders.
# ───────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Regla:
    id: str
    que_es: str
    patron: re.Pattern[str]
    grupo: int = 0


REGLAS: tuple[Regla, ...] = (
    Regla(
        "aws-access-key-id",
        "identificador de clave de acceso de AWS (prefijo de tipo + 16)",
        re.compile(r"\b(?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA|AGPA|AIDA|AIPA|ANPA|ANVA|AROA|APKA)[A-Z0-9]{16}\b"),
    ),
    Regla(
        "aws-secret-access-key",
        "clave secreta de AWS (40 caracteres base64 junto a su nombre)",
        # Anclada al nombre: 40 caracteres base64 sueltos aparecen en cualquier
        # hash y marcarlos sin contexto sería ruido puro.
        # El hueco es `[^\w\n]` y no `\W` porque `\W` INCLUYE el salto de línea:
        # con `\W` la regla emparejaba un nombre de una línea con un valor de la
        # siguiente. Se descubrió porque el propio fichero de mutaciones se
        # marcaba a sí mismo. LIMITACIÓN DECLARADA: nombre y valor tienen que
        # estar en el mismo renglón, que es como los escriben .env, YAML y JSON.
        re.compile(
            r"(?i)aws[_.-]?(?:secret|sec)[_.-]?(?:access)?[_.-]?key[^\w\n]{0,20}([A-Za-z0-9/+=]{40})"
        ),
        1,
    ),
    Regla(
        "twilio-account-sid",
        "Account SID de Twilio (`AC` + 32 hex)",
        re.compile(r"\bAC[0-9a-fA-F]{32}\b"),
    ),
    Regla(
        "twilio-api-key-sid",
        "API Key SID de Twilio (`SK` + 32 hex)",
        re.compile(r"\bSK[0-9a-fA-F]{32}\b"),
    ),
    Regla(
        "twilio-auth-token",
        "auth token de Twilio (32 hex junto a su nombre)",
        # `[^\w\n]` y no `\W`: ver la nota de aws-secret-access-key.
        re.compile(r"(?i)auth[_.-]?token[^\w\n]{0,20}([0-9a-fA-F]{32})\b"),
        1,
    ),
    Regla(
        "clave-privada",
        "bloque PEM de clave privada (RSA/EC/OPENSSH/PGP)",
        re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----"),
    ),
    Regla(
        "uri-con-contrasena",
        "URI con la contraseña embebida (`esquema://usuario:CONTRASEÑA@host`)",
        re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:/@\"'<>]+:([^\s@\"'/<>]{3,})@"),
        1,
    ),
    Regla(
        "slack-token",
        "token de Slack (`xox…`)",
        re.compile(r"\bxox[baprse]-[A-Za-z0-9-]{10,}"),
    ),
    Regla(
        "github-token",
        "token de GitHub (`ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_` + 36)",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b"),
    ),
    Regla(
        "google-api-key",
        "clave de API de Google/Firebase (`AIza` + 35)",
        re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ),
    Regla(
        "openai-openrouter-key",
        "clave de OpenAI/OpenRouter (`sk-…`) — la capa narrativa usa una (T-2.42)",
        re.compile(r"\bsk-(?:or-)?(?:v1-)?[A-Za-z0-9]{24,}\b"),
    ),
    Regla(
        "stripe-key",
        "clave de Stripe (`sk_live_`/`rk_live_`/`…_test_`)",
        re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{20,}\b"),
    ),
    Regla(
        "meta-graph-token",
        "access token de Meta/WhatsApp Business (`EAA…`) — canal de T-2.77",
        re.compile(r"\bEAA[A-Za-z0-9]{60,}\b"),
    ),
    Regla(
        "jwt-firmado",
        "JWT de tres segmentos (un token de consola pegado en un fichero)",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{20,}\b"),
    ),
)

# ───────────────────────────────────────────────────────────────────────────────
# PERMITIDOS — por VALOR y con su razón (ver "LA REGLA DE DISEÑO", arriba).
# Se imprimen al final de cada corrida: una exclusión invisible es una exclusión
# que nadie vuelve a cuestionar.
# ───────────────────────────────────────────────────────────────────────────────
PERMITIDOS: dict[str, str] = {
    "takab_dev": (
        "contraseña del Postgres de DESARROLLO. Está en claro en docker-compose.yml, "
        "en .env.example y en el bloque `services:` de ci.yml porque ES el contenedor "
        "local: no da acceso a nada que no esté ya en la máquina de quien la lee. "
        "Aparece 36 veces (DSN de tests, Makefile, runbooks) y marcarla sería apagar "
        "el barrido el primer día — medido: sin esta entrada, el árbol da 37 falsos "
        "positivos y ninguno verdadero."
    ),
    "c%40ve": (
        "contraseña inventada y URL-encodeada en api/tests/ops/test_restore_drill.py; "
        "existe justo para comprobar que `target_from_url` desescapa el `%40`."
    ),
}

# ───────────────────────────────────────────────────────────────────────────────
# PLACEHOLDERS — formas que NO son un valor, con su razón. Van por patrón porque
# son clases enteras, no literales sueltos.
# ───────────────────────────────────────────────────────────────────────────────
PLACEHOLDERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        # El prefijo opcional deja pasar el `AC` del SID: lo que decide es que la
        # parte VARIABLE sea un solo carácter repetido.
        re.compile(r"^[A-Za-z]{0,6}[_.\-]?(.)\1{7,}$"),
        "un solo carácter repetido tras el prefijo del emisor (p. ej. el "
        "`ACffff…ff` de api/tests/notify/test_twilio.py): es la forma canónica "
        "de escribir «aquí va un SID»",
    ),
    (
        re.compile(r"[\$%]?[{<]\s*[A-Za-z_][A-Za-z0-9_.\[\]-]*\s*[}>]"),
        "interpolación de plantilla (`${VAR}`, `{variable}`, `<TU-CLAVE>`): el "
        "fichero no contiene el valor, contiene el hueco donde va",
    ),
    (
        re.compile(r"^\$[A-Za-z_][A-Za-z0-9_]*$"),
        "variable de shell sin llaves (`$APP_PASS`): mismo caso que la anterior",
    ),
    (
        re.compile(
            r"(?i)^[\W_]*(x{3,}|y{3,}|z{3,}|redactado|redacted|placeholder|changeme|"
            r"change-?me|example|ejemplo|dummy|fake|fixture|sample|tu-?clave|"
            r"tu-?password|password|contrasena|contraseña|secret|secreto|todo|"
            r"pon-?aqui|no-?es-?un-?secreto)[\W_]*$"
        ),
        "la palabra dice que no es un valor real (`REDACTADO`, `changeme`, "
        "`<password>`): marcar esto entrena a la gente a ignorar el barrido",
    ),
    (
        re.compile(r"(?i)^(localhost|127\.0\.0\.1|0\.0\.0\.0|example\.(com|org|net))$"),
        "host de ejemplo colado como si fuera la contraseña de una URI",
    ),
)

#: Sufijos que se saltan enteros, con su razón. Deliberadamente CORTO: cada
#: entrada es un sitio donde esconder un secreto. Los binarios no hacen falta
#: listarlos (se detectan por el byte NUL).
RUTAS_SALTADAS: dict[str, str] = {
    "package-lock.json": (
        "lockfile de npm: miles de `integrity: sha512-…` en base64. No lo dispara "
        "ninguna regla de hoy, pero se salta para que el día que alguien añada una "
        "regla de entropía no herede 40 000 líneas de ruido"
    ),
}


def es_placeholder(valor: str) -> str | None:
    for patron, razon in PLACEHOLDERS:
        if patron.search(valor):
            return razon
    return None


def permitido(valor: str) -> str | None:
    """Se perdona si el valor capturado ES, EXACTAMENTE, un permitido declarado.

    La primera versión perdonaba también por SUBCADENA, y eso es un agujero: una
    clave de verdad que llevara `takab_dev` dentro (`takab_dev_prod_9f3a…`)
    quedaba perdonada entera. Se comprobó contra el árbol real que la subcadena
    no hacía falta —las 37 coincidencias perdonadas son exactas— así que la
    laxitud no compraba nada y costaba una puerta.
    """
    return PERMITIDOS.get(valor)


@dataclass(frozen=True)
class Hallazgo:
    origen: str
    linea: int
    regla: Regla
    valor: str
    contexto: str


def _redactar(valor: str) -> str:
    """Nunca se imprime el secreto entero: el log de CI es público en el PR."""
    if len(valor) <= 8:
        return valor[:2] + "…" * (len(valor) > 2)
    return "%s…%s (%d car.)" % (valor[:4], valor[-2:], len(valor))


def escanear_texto(origen: str, texto: str) -> tuple[list[Hallazgo], list[tuple[str, str]]]:
    """(hallazgos, perdonados). `perdonados` documenta lo que se dejó pasar.

    Se barre el fichero ENTERO una vez por regla y el nº de línea se deriva del
    desplazamiento del match. Es una condición del diseño que NINGUNA regla
    cruce el salto de línea, y no se cumplía sola: las dos ancladas al nombre
    usaban `\\W{0,20}`, y `\\W` incluye `\\n`, así que emparejaban el nombre de
    una línea con el valor de la siguiente. Hoy usan `[^\\w\\n]` y el resto
    excluyen `\\s` por construcción.
    """
    hallazgos: list[Hallazgo] = []
    perdonados: list[tuple[str, str]] = []
    inicios: list[int] | None = None
    for regla in REGLAS:
        for m in regla.patron.finditer(texto):
            valor = m.group(regla.grupo) or ""
            razon = es_placeholder(valor) or permitido(valor)
            if razon:
                perdonados.append((valor, razon))
                continue
            if inicios is None:  # sólo se paga si hay algo que reportar
                inicios = [0]
                for i, c in enumerate(texto):
                    if c == "\n":
                        inicios.append(i + 1)
            n = bisect.bisect_right(inicios, m.start())
            ini = inicios[n - 1]
            fin = texto.find("\n", ini)
            linea = texto[ini : fin if fin != -1 else len(texto)]
            hallazgos.append(Hallazgo(origen, n, regla, valor, linea.strip()[:120]))
    hallazgos.sort(key=lambda h: (h.origen, h.linea, h.regla.id))
    return hallazgos, perdonados


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, errors="replace"
    ).stdout


def _texto_de(datos: bytes) -> str | None:
    """None si es binario. El byte NUL es la señal inequívoca y no hay lista de
    extensiones que mantener (una lista de extensiones es un escondite)."""
    if b"\x00" in datos[:8192]:
        return None
    return datos.decode("utf-8", errors="replace")


def rutas_rastreadas() -> list[str]:
    """Rastreados + NO rastreados que git no ignora.

    Los segundos importan y costó verlo: `git ls-files` a secas NO ve un fichero
    recién creado que todavía no se ha hecho `git add`, y ése es justo el estado
    en el que se corre `make test` mientras se escribe una tarea. Medido: un DSN
    con contraseña dentro de un test nuevo daba VERDE en local y ROJO en CI (allí
    el checkout es del commit, así que todo está rastreado). Un gate que dice
    cosas distintas en local y en el runner es la familia de fallo que
    `test_ci_parity.sh` existe para impedir, reintroducida aquí.

    Los ignorados quedan fuera y es lo correcto: `.env`, `web/.env`, el
    `edge.env` del Pi. Existen PARA tener secretos. Queda declarado arriba.
    """
    rastreados = _git("ls-files", "-z").split("\0")
    nuevos = _git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
    return [p for p in (*rastreados, *nuevos) if p]


def escanear_arbol(rutas: list[str]) -> tuple[list[Hallazgo], list[tuple[str, str]], int]:
    hallazgos: list[Hallazgo] = []
    perdonados: list[tuple[str, str]] = []
    vistos = 0
    for ruta in rutas:
        if any(ruta.endswith(s) for s in RUTAS_SALTADAS):
            continue
        try:
            with open(ruta, "rb") as fh:
                datos = fh.read()
        except OSError:
            continue
        texto = _texto_de(datos)
        if texto is None:
            continue
        vistos += 1
        h, p = escanear_texto(ruta, texto)
        hallazgos += h
        perdonados += p
    return hallazgos, perdonados, vistos


def escanear_historia() -> tuple[list[Hallazgo], list[tuple[str, str]], int]:
    """Todos los blobs alcanzables de TODAS las refs. Auditoría, no gate."""
    hallazgos: list[Hallazgo] = []
    perdonados: list[tuple[str, str]] = []
    blobs: dict[str, str] = {}
    for linea in _git("rev-list", "--all", "--objects").splitlines():
        sha, _, ruta = linea.partition(" ")
        if ruta and not any(ruta.endswith(s) for s in RUTAS_SALTADAS):
            blobs.setdefault(sha, ruta)
    vistos = 0
    for sha, ruta in blobs.items():
        salida = subprocess.run(
            ["git", "cat-file", "-t", sha], capture_output=True, text=True
        )
        if salida.stdout.strip() != "blob":
            continue
        datos = subprocess.run(["git", "cat-file", "blob", sha], capture_output=True).stdout
        texto = _texto_de(datos)
        if texto is None:
            continue
        vistos += 1
        h, p = escanear_texto("%s@%s" % (ruta, sha[:8]), texto)
        hallazgos += h
        perdonados += p
    return hallazgos, perdonados, vistos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = ap.add_mutually_exclusive_group()
    modo.add_argument("--historia", action="store_true", help="barre TODOS los blobs de todas las refs (auditoría, lento)")
    modo.add_argument("--rutas", nargs="+", metavar="RUTA", help="barre sólo estas rutas (lo usa la batería de mutaciones)")
    ap.add_argument("--silencioso", action="store_true", help="sólo imprime los hallazgos")
    args = ap.parse_args(argv)

    if args.historia:
        alcance = "historial completo (todos los blobs de todas las refs)"
        hallazgos, perdonados, vistos = escanear_historia()
    elif args.rutas:
        alcance = "rutas indicadas"
        hallazgos, perdonados, vistos = escanear_arbol(args.rutas)
    else:
        alcance = "árbol de trabajo (rastreados + nuevos sin ignorar)"
        hallazgos, perdonados, vistos = escanear_arbol(rutas_rastreadas())

    for h in hallazgos:
        print(
            "SECRETO\t%s:%d\t%s\t%s\t%s"
            % (h.origen, h.linea, h.regla.id, _redactar(h.valor), h.contexto),
            file=sys.stderr if not args.silencioso else sys.stdout,
        )
    if args.silencioso:
        return 1 if hallazgos else 0

    print("barrido: %s · %d ficheros de texto · %d regla(s)" % (alcance, vistos, len(REGLAS)))
    razones = sorted({r for _, r in perdonados})
    if razones:
        print("perdonados (%d coincidencia(s)), por su razón declarada:" % len(perdonados))
        for r in razones:
            print("  --   %s" % r)
    if hallazgos:
        print(
            "\n%d SECRETO(S) EN EL ÁRBOL. Rótalo primero (el valor ya está en git, "
            "quitarlo del fichero no lo revoca) y después sácalo del código: entorno "
            "o AWS Secrets Manager, regla de oro 6. Si es un valor de desarrollo "
            "legítimo, declaralo en PERMITIDOS de este fichero CON SU RAZÓN."
            % len(hallazgos)
        )
        return 1
    print("sin secretos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
