"""Matriz requisito→test (T-2.84): la trazabilidad no puede declarar cobertura que no existe.

`takab-docs/MATRIZ-REQUISITO-TEST.md` es el documento que ve el cliente (`T-2.86` lo enlaza
"huecos incluidos"). Una matriz de trazabilidad es el documento más fácil de falsificar del
proyecto: se escribe una vez, se llena de verdes y a partir del día siguiente miente sin que
nadie se entere. Este archivo existe para que **no pueda**.

**Qué garantiza.** Tres cosas mecánicas:

1. **la lista de requisitos se DERIVA de su fuente** —`CLAUDE.md §2` (reglas de oro),
   `BLUEPRINT §14` (invariantes y diferido) y `RUNBOOK-auditoria-cierre §10` (gates físicos)—,
   así que añadir una regla de oro, un invariante o un gate rompe el build hasta que la matriz
   lo trate. No hay copia que se desincronice;
2. **cada cita se resuelve contra el árbol real**: el ancla es el NOMBRE del test —que
   sobrevive a moverse de línea— y el `archivo:línea` es un dato **derivado** por AST. Borrar
   o renombrar un test citado pone esto en rojo; es el criterio 3 de la ficha;
3. **la palabra CUBIERTO se calcula, no se teclea**. Un test que existe pero se salta, o que
   sólo cruza documentos, o que vive en una suite que no bloquea el merge, **no cuenta como
   cobertura**: la fila baja a `SIN COBERTURA` con su motivo, sin que nadie tenga que
   acordarse. Es la lección de `T-2.63` (cinco tests de hardware saltándose en silencio con
   el job en verde) y de `T-2.58` (67 tests del panel saltados por falta de `node`).

**Qué NO garantiza**, y hay que decirlo antes de que alguien lea un verde de aquí: que el test
citado *demuestre semánticamente* su afirmación. Eso lo decide un humano al escribir la fila.
Ver el inventario del final, que es parte del entregable y no un apéndice.

**Por qué la lista de requisitos NO sale de `TASKS.md`.** Era el candidato obvio: 678 criterios
de aceptación ya escritos. Se descartó por tres razones medidas el 2026-08-08:

- *no es un contrato, es una bitácora*: los criterios describen el trabajo de una tarea, no la
  promesa del producto, y el documento de entrega (`T-2.86`) necesita lo segundo;
- *sus casillas no son señal fiable*: de los 442 criterios que cuelgan de tareas `[x]`, **34
  siguen sin marcar**, y **5 tareas cerradas tienen sus criterios enteros en `[ ]`** (`T-2.61`,
  `T-2.62`, `T-2.63`, `T-2.64`, `T-2.69`). Derivar cobertura de ahí sería heredar esa deriva;
- *cambia con cada tarea*: la matriz estaría en rojo permanente por movimiento del backlog,
  que es justo el ruido que hace que un documento se deje de mirar.

Los nueve *decision-gates* de `PLAN-MAESTRO §3` tampoco entran: son decisiones de arquitectura
—no conductas del sistema— y ya los vigila `test_docs_consistency.py`. Las once reglas de oro,
en cambio, llevan intactas desde la fundación y son exactamente lo que un cliente compra:
"esto NUNCA depende de internet".

Hereda el fixture de sesión ``_migrated`` (``conftest.py:57``) sin usarlo: no toca la DB.

Para regenerar el documento tras mover un test citado::

    python api/tests/test_matriz_trazabilidad.py --escribir
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

CLAUDE_MD = REPO / "CLAUDE.md"
BLUEPRINT = REPO / "takab-docs" / "BLUEPRINT-TECNICO-TAKAB.md"
RUNBOOK_AUDITORIA = REPO / "takab-docs" / "runbooks" / "RUNBOOK-auditoria-cierre.md"
WORKFLOWS = REPO / ".github" / "workflows"
MATRIZ = REPO / "takab-docs" / "MATRIZ-REQUISITO-TEST.md"


# ===========================================================================
# 1 · Las tres fuentes de requisitos, derivadas (nunca copiadas)
# ===========================================================================

_SECCION_REGLAS = "## 2. Reglas de oro"

#: `N. **<enunciado>**` — la forma que usa `CLAUDE.md §2` para cada regla de oro.
REGLA_RE = re.compile(r"^(?P<n>\d+)\. \*\*(?P<enunciado>.+?)\*\*", re.M)

_SECCION_INVARIANTES = "## 14. Fuera de alcance / diferido explícito"

#: `[INVARIANTE · <clave>]` / `[DIFERIDO · <clave>]`. Es el MISMO censo del que ya tira
#: `test_docs_consistency.py`, en su test de que cada viñeta declara si es prohibición o
#: diferido: dos tests leyendo la misma fuente desde extremos distintos.
CLASE_RE = re.compile(r"\[(?P<clase>INVARIANTE|DIFERIDO) · (?P<clave>[^\]]+)\]")

_SECCION_GATES = "## 10. Registro de gates HW/despliegue"

#: Fila del registro de gates: `| G-0N | <gate> | <prueba> | <criterio> | …`.
GATE_FILA_RE = re.compile(r"^\|\s*(?P<id>G-\d{2})\s*\|\s*(?P<titulo>[^|]+)\|", re.M)


def _seccion(texto: str, encabezado: str, *, fuente: str) -> str:
    i = texto.find(encabezado)
    assert i != -1, (
        f"`{fuente}` ya no tiene la sección {encabezado!r}. Es de donde sale el censo de "
        "requisitos: sin ella esta matriz no puede decidir nada y se volvería vacía EN "
        "SILENCIO, que es exactamente el defecto que viene a evitar."
    )
    j = texto.find("\n## ", i + 1)
    return texto[i:] if j == -1 else texto[i:j]


def reglas_de_oro() -> dict[str, str]:
    """{`RO-N`: enunciado} tal como las declara `CLAUDE.md §2`."""
    sec = _seccion(CLAUDE_MD.read_text(encoding="utf-8"), _SECCION_REGLAS, fuente="CLAUDE.md")
    return {f"RO-{m.group('n')}": m.group("enunciado").strip() for m in REGLA_RE.finditer(sec)}


def invariantes() -> dict[str, str]:
    """{`INV-<clave>` / `DIF-<clave>`: viñeta} tal como los declara `BLUEPRINT §14`."""
    sec = _seccion(BLUEPRINT.read_text(encoding="utf-8"), _SECCION_INVARIANTES, fuente="BLUEPRINT")
    out: dict[str, str] = {}
    for vineta in re.split(r"\n(?=- )", sec):
        if not vineta.lstrip().startswith("- "):
            continue
        m = CLASE_RE.search(vineta)
        if not m:
            continue
        prefijo = "INV" if m.group("clase") == "INVARIANTE" else "DIF"
        enunciado = " ".join(vineta.split())[2:]
        # `strip` con backtick: la clase va entre comillas invertidas en el documento y
        # quitarla deja un ``` `` ``` vacío colgando del título.
        out[f"{prefijo}-{m.group('clave')}"] = CLASE_RE.sub("", enunciado).strip(" ·—-`")
    return out


def gates_fisicos() -> dict[str, str]:
    """{`G-0N`: título} tal como los declara `RUNBOOK-auditoria-cierre §10`."""
    sec = _seccion(
        RUNBOOK_AUDITORIA.read_text(encoding="utf-8"), _SECCION_GATES, fuente="RUNBOOK-auditoria"
    )
    return {m.group("id"): m.group("titulo").strip() for m in GATE_FILA_RE.finditer(sec)}


# ===========================================================================
# 2 · Dónde corre cada suite, y si su rojo bloquea un merge
# ===========================================================================
#
# Un test que nadie ejecuta no es cobertura, igual que uno que se salta. La raíz del archivo
# citado decide su suite; el nombre del job se comprueba literalmente contra su workflow, y si
# el workflow **no** dispara en `pull_request` sus tests no acreditan nada. Es el caso real de
# `web/e2e/`: la matriz de Playwright es `workflow_dispatch` + `continue-on-error` **a
# propósito** (`e2e.yml:1-19`), así que su verde es información, no garantía.


@dataclass(frozen=True)
class Suite:
    raiz: str
    workflow: str
    job_ci: str
    lenguaje: str


SUITES: tuple[Suite, ...] = (
    Suite("api/tests", "ci.yml", "api · ruff + pytest", "python"),
    Suite("demo/tests", "ci.yml", "api · ruff + pytest", "python"),
    Suite("edge/tests", "ci.yml", "edge · ruff + pytest (sin hardware)", "python"),
    Suite("web/src", "ci.yml", "web · eslint + prettier + vitest + build", "typescript"),
    Suite("mobile/src", "ci.yml", "mobile · eslint + tsc + jest", "typescript"),
    Suite("infra/terraform", "ci.yml", "infra · terraform fmt + validate + test", "tftest"),
    Suite("infra/scripts/tests", "ci.yml", "infra · terraform fmt + validate + test", "bash"),
    Suite(
        "web/e2e",
        "e2e.yml",
        "web · playwright 1280×800 / 1440×900 / 1920×1080",
        "typescript",
    ),
)


def _texto_workflow(nombre: str) -> str:
    ruta = WORKFLOWS / nombre
    assert ruta.is_file(), (
        f"el workflow `{nombre}` ya no existe: ninguna suite puede apoyarse en él"
    )
    return ruta.read_text(encoding="utf-8")


def bloquea_el_merge(suite: Suite) -> bool:
    """¿El workflow de esta suite corre en cada PR? Derivado del `on:` del propio archivo."""
    texto = _texto_workflow(suite.workflow)
    cabecera = texto.split("\njobs:", 1)[0]
    return "pull_request:" in cabecera or "pull_request :" in cabecera


def _suite_de(archivo: str) -> Suite:
    for s in SUITES:
        if archivo.startswith(s.raiz + "/"):
            return s
    raise AssertionError(
        f"`{archivo}` no cuelga de ninguna raíz de suite conocida "
        f"({[s.raiz for s in SUITES]}). Una cita a un archivo que ninguna suite ejecuta no es "
        "cobertura: o lo mueves a una suite, o declaras la raíz nueva aquí junto con el "
        "workflow y el job que la corren."
    )


# ===========================================================================
# 3 · El resolutor: nombre del test → `archivo:línea` + si puede no ejecutarse
# ===========================================================================
#
# El ancla es el NOMBRE. La línea es derivada y se recalcula en cada corrida: mover un test
# treinta líneas hacia abajo NO invalida la cita, sólo cambia el número que la matriz publica.
# Borrarlo o renombrarlo la rompe, que es lo que pide el criterio 3 de la ficha.

#: Marcas que significan "esto puede no ejecutarse". `perf` está aquí porque el CI corre
#: `pytest -q -m "not perf"` y el conftest la salta salvo `TAKAB_RUN_PERF=1`: una prueba de
#: rendimiento no acredita nada en un PR.
_MARCAS_QUE_APAGAN = frozenset({"skip", "skipif", "skipunless", "xfail", "perf"})

#: Llamadas que apagan un test desde dentro del cuerpo (o del módulo).
_LLAMADAS_QUE_APAGAN = frozenset({"skip", "importorskip", "xfail"})


class CitaRota(AssertionError):
    """La cita apunta a un test que ya no existe con ese nombre."""


@dataclass(frozen=True)
class Localizacion:
    linea: int
    #: Motivo por el que puede no ejecutarse, o `None` si corre siempre.
    apagable: str | None


def _marcas(nodo: ast.AST) -> set[str]:
    """Marcas `pytest.mark.<X>` / `unittest.skipIf` presentes en un decorador o asignación."""
    vistos: set[str] = set()
    for sub in ast.walk(nodo):
        if isinstance(sub, ast.Attribute):
            vistos.add(sub.attr.lower())
        elif isinstance(sub, ast.Name):
            vistos.add(sub.id.lower())
    return vistos & _MARCAS_QUE_APAGAN


def _apaga_desde_dentro(nodo: ast.AST) -> bool:
    for sub in ast.walk(nodo):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if isinstance(f, ast.Attribute) and f.attr in _LLAMADAS_QUE_APAGAN:
            return True
        if isinstance(f, ast.Name) and f.id in _LLAMADAS_QUE_APAGAN:
            return True
    return False


def _marcas_de_modulo(arbol: ast.Module) -> set[str]:
    out: set[str] = set()
    for nodo in arbol.body:
        destinos: set[str] = set()
        if isinstance(nodo, ast.Assign):
            destinos = {t.id for t in nodo.targets if isinstance(t, ast.Name)}
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            destinos = {nodo.target.id}
        if "pytestmark" in destinos and nodo.value is not None:  # type: ignore[union-attr]
            out |= _marcas(nodo.value)  # type: ignore[union-attr]
        # `pytest.skip(..., allow_module_level=True)` / `pytest.importorskip(...)` sueltos.
        if isinstance(nodo, ast.Expr | ast.Assign) and _apaga_desde_dentro(nodo):
            out.add("skip")
    return out


def _localiza_python(texto: str, nombre: str) -> Localizacion:
    arbol = ast.parse(texto)
    del_modulo = _marcas_de_modulo(arbol)
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef) or nodo.name != nombre:
            continue
        encontradas = set(del_modulo)
        for dec in nodo.decorator_list:
            encontradas |= _marcas(dec)
        if _apaga_desde_dentro(nodo):
            encontradas.add("skip")
        return Localizacion(nodo.lineno, ", ".join(sorted(encontradas)) or None)
    raise CitaRota(nombre)


#: `describe(`, `suite(` y el `test.describe(` de Playwright. Sirve para saber si un `it`
#: hereda un `.skip` de su bloque.
_DESCRIBE_RE = re.compile(
    r"^(?P<sangria>\s*)(?:test\.describe|describe|suite)(?P<mod>(?:\.\w+)*)\("
)


def _regex_titulo(titulo: str) -> re.Pattern[str]:
    """`it("t")`, `test('t')` y también `it.each([...])( "t" )`, que parte la llamada en dos.

    El `(?!\\.describe)` evita que un `test.describe("X")` se resuelva como si fuera un test
    llamado `X`. El grupo opcional del medio come los argumentos de `.each(...)` con un nivel
    de paréntesis anidados, que es lo que hay en el repo hoy (cadenas con `(503)` dentro).
    """
    return re.compile(
        r"\b(?:it|test)(?!\.describe)(?P<mod>(?:\.\w+)*)\s*"
        r"(?:\((?:[^()]|\([^()]*\))*\)\s*)?"
        r"\(\s*(?P<c>['\"`])" + re.escape(titulo) + r"(?P=c)",
        re.S,
    )


def _describes_abiertos(lineas: list[str], hasta: int) -> list[bool]:
    """¿Están apagados los `describe` que ENVUELVEN a la línea `hasta` (1-based)?

    Hay que llevar una pila con la sangría, no basta con «algún `describe.skip` más
    arriba»: un bloque apagado que ya se cerró queda por encima en el archivo y no envuelve
    nada. Ese atajo daba por saltado un test vivo, y un falso «no cuenta» ensucia la matriz
    igual que un falso «cuenta».
    """
    pila: list[tuple[int, bool]] = []
    for linea in lineas[:hasta]:
        if not linea.strip():
            continue
        sangria = len(linea) - len(linea.lstrip())
        while pila and pila[-1][0] >= sangria:
            pila.pop()
        d = _DESCRIBE_RE.match(linea)
        if d:
            mod = d.group("mod")
            pila.append((sangria, ".skip" in mod or ".todo" in mod))
    return [apagado for _, apagado in pila]


def _localiza_typescript(texto: str, titulo: str) -> Localizacion:
    m = _regex_titulo(titulo).search(texto)
    if not m:
        raise CitaRota(titulo)
    # La línea es la del TÍTULO, no la del inicio de la llamada: en un `it.each([...])(…)`
    # el nombre vive varias líneas más abajo y es adonde quiere saltar quien lee la matriz.
    linea = texto.count("\n", 0, m.start("c")) + 1
    envolventes = _describes_abiertos(texto.splitlines(), linea)
    propio = ".skip" in m.group("mod") or ".todo" in m.group("mod")
    return Localizacion(linea, "skip" if (propio or any(envolventes)) else None)


def _localiza_tftest(texto: str, nombre: str) -> Localizacion:
    patron = re.compile(r'^\s*run\s+"' + re.escape(nombre) + r'"\s*\{')
    for n, linea in enumerate(texto.splitlines(), start=1):
        if patron.match(linea):
            return Localizacion(n, None)
    raise CitaRota(nombre)


def _localiza_bash(texto: str, nombre: str) -> Localizacion:
    patron = re.compile(r"^\s*(?:function\s+)?" + re.escape(nombre) + r"\s*\(\)\s*\{")
    for n, linea in enumerate(texto.splitlines(), start=1):
        if patron.match(linea):
            return Localizacion(n, None)
    raise CitaRota(nombre)


_LOCALIZADORES = {
    "python": _localiza_python,
    "typescript": _localiza_typescript,
    "tftest": _localiza_tftest,
    "bash": _localiza_bash,
}


def localiza(archivo: str, nombre: str) -> Localizacion:
    ruta = REPO / archivo
    suite = _suite_de(archivo)
    if not ruta.is_file():
        raise CitaRota(f"{archivo} — el archivo ya no existe")
    loc = _LOCALIZADORES[suite.lenguaje](ruta.read_text(encoding="utf-8"), nombre)
    if loc.apagable is None and not bloquea_el_merge(suite):
        return Localizacion(loc.linea, f"suite no bloqueante ({suite.workflow})")
    return loc


# ===========================================================================
# 4 · El registro: afirmaciones y sus pruebas
# ===========================================================================

COMPORTAMIENTO = "comportamiento"
DOCUMENTAL = "documental"


@dataclass(frozen=True)
class Evidencia:
    #: Ruta relativa al repo. La raíz decide la suite y el lenguaje.
    archivo: str
    #: **El ancla.** Nombre exacto de la función (python), título literal de `it()`/`test()`
    #: (typescript), `run "…"` (tftest) o nombre de función (bash).
    test: str
    #: Qué demuestra, en una línea. Se publica en la matriz.
    demuestra: str
    #: `comportamiento` = ejercita el código. `documental` = sólo cruza textos entre sí, y
    #: **nunca** acredita una afirmación de conducta: que un `.md` siga diciendo "no hagas X"
    #: no prueba que el código no haga X.
    tipo: str = COMPORTAMIENTO
    #: Motivo declarado por el que el test puede no correr. Tiene que coincidir con lo que ve
    #: el AST: ponerle un `skipif` a un test citado como incondicional pone esto en rojo.
    apagable: str | None = None
    #: Paso del workflow que hace IMPOSIBLE ese salto en CI, citado literalmente. Existe por
    #: un caso real: el arnés del panel del gabinete lleva `skipif(node ausente)` y `ci.yml`
    #: corre `node --version` como paso propio **justo para que no pueda saltarse en
    #: silencio** (T-2.58, donde 67 tests se saltaron así). Con la garantía verificada, la
    #: evidencia sí acredita; si alguien borra el paso del workflow, esto se pone en rojo y
    #: la fila cae a `SIN COBERTURA` sola.
    garantia_ci: str | None = None


@dataclass(frozen=True)
class Afirmacion:
    aid: str
    texto: str
    evidencias: tuple[Evidencia, ...] = ()
    #: Qué implica el hueco. **Obligatorio si y sólo si** la afirmación acaba sin cobertura.
    hueco: str = ""


@dataclass(frozen=True)
class Requisito:
    rid: str
    afirmaciones: tuple[Afirmacion, ...] = ()
    nota: str = ""
    #: Sólo gates: por qué ningún test de software puede cerrarlo. Obligatorio para `G-0N`.
    no_automatizable: str = ""


# --- Reglas de oro ---------------------------------------------------------

_RO = (
    Requisito(
        "RO-1",
        nota=(
            "El reflejo SASMEX→sirena se prueba con la nube explícitamente caída, no con la "
            "nube ausente por casualidad. La afirmación `d` es la que no se sostiene: el "
            "proceso mínimo que estas pruebas ejercitan **no es** el que corre hoy en el "
            "gabinete (ver `RO-4.f`)."
        ),
        afirmaciones=(
            Afirmacion(
                "RO-1.a",
                "Con la nube caída, el contacto SASMEX energiza la sirena.",
                (
                    Evidencia(
                        "edge/tests/test_supervisor.py",
                        "test_sasmex_actuates_with_cloud_offline",
                        "`cloud.online is False` y aun así el relé de sirena queda energizado; "
                        "`cloud.sent == 0`.",
                    ),
                    Evidencia(
                        "edge/tests/test_e2e.py",
                        "test_sasmex_reflex_and_sequence_cloud_off",
                        "E2E con la nube apagada: `siren_sounding` inmediato y 1 evento "
                        "encolado (no enviado).",
                    ),
                ),
            ),
            Afirmacion(
                "RO-1.b",
                "Ningún estado de la nube (config viva, ventana de mantenimiento) desarma "
                "ni calla el reflejo.",
                (
                    Evidencia(
                        "edge/tests/test_supervisor.py",
                        "test_la_config_viva_de_la_nube_jamas_se_cablea_al_reflejo",
                        "La config publicada desde la nube no llega al camino del reflejo.",
                    ),
                    Evidencia(
                        "edge/tests/test_supervisor.py",
                        "test_una_ventana_de_mantenimiento_DE_LA_NUBE_no_calla_la_sirena",
                        "Una ventana de mantenimiento remota no silencia la sirena.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-1.c",
                "El proceso mínimo `takab-gpio` —el que toca sirena, gas y puertas— no carga "
                "ninguna dependencia fuera de una lista blanca cerrada (IA incluida).",
                (
                    Evidencia(
                        "edge/tests/test_gpio_process.py",
                        "test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada",
                        "Lista blanca *fail-closed* sobre el grafo de importación real, en "
                        "tres montajes de arranque.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-1.d",
                "El proceso que corre en el gabinete desplegado ES ese proceso mínimo.",
                (),
                hueco=(
                    "Nada lo comprueba, y el valor por defecto va en contra: "
                    "`edge/takab_edge/config/settings.py` declara "
                    '`gpio_owner = "edge"` por defecto, '
                    "así que salvo que `/etc/takab/edge.env` diga `TAKAB_EDGE_GPIO_OWNER=gpio` "
                    "quien abre los pines es el supervisor de 16 módulos "
                    "(`EdgeSupervisor`, vía `edge_owns_pins`). Ese archivo no está en el "
                    "repo y ningún test lee "
                    "su contenido. **Consecuencia: `RO-1.c` acredita un proceso que puede no "
                    "ser el que sostiene la sirena.** Mismo hueco que `RO-4.f`."
                ),
            ),
            Afirmacion(
                "RO-1.e",
                "La latencia contacto WR-1 → los cinco relés se mide y cabe en el "
                "presupuesto (<100 ms).",
                (
                    Evidencia(
                        "edge/tests/test_e2e.py",
                        "test_latencia_contacto_wr1_a_los_cinco_reles_bajo_presupuesto",
                        "Mide contacto→nivel físico de los 5 pines y exige <0.100 s, con "
                        "guarda anti-teatro de que el tramo medido contiene el reflejo.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-1.f",
                "La detección instrumental de una sola estación es SOLO AVISO: no mueve "
                "relés (política ratificada en T-2.32).",
                (
                    Evidencia(
                        "edge/tests/test_e2e.py",
                        "test_instrumental_quake_visual_only_no_actuation",
                        "Sismo simulado completo: el tier sube y los 5 relés siguen en "
                        "`activated is False`.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-1.g",
                "El opt-in por sitio `instrumental_actuation` restaura la actuación autónoma.",
                (
                    Evidencia(
                        "edge/tests/test_e2e.py",
                        "test_instrumental_actuation_optin_restores_sequence",
                        "Mismo sismo con el opt-in activo: los 5 relés vuelven a actuar.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-1.h",
                "La IA asesora y jamás emite un veredicto: la capa narrativa no puede "
                "invocar al motor de reglas ni colocar un dictamen.",
                (
                    Evidencia(
                        "api/tests/narrative/test_contract.py",
                        "test_la_capa_narrativa_no_puede_invocar_al_motor_de_reglas",
                        "Escaneo AST de `narrative/**`: no importa `dictamen.rules|service`.",
                    ),
                    Evidencia(
                        "api/tests/narrative/test_contract.py",
                        "test_el_veredicto_del_pdf_no_depende_de_la_prosa",
                        "El veredicto del PDF es el mismo con y sin prosa generada.",
                    ),
                ),
            ),
        ),
    ),
    Requisito(
        "RO-2",
        afirmaciones=(
            Afirmacion(
                "RO-2.a",
                "Sin nube, el gabinete sigue detectando y accionando.",
                (
                    Evidencia(
                        "edge/tests/test_supervisor.py",
                        "test_sasmex_actuates_with_cloud_offline",
                        "Nube caída: tier + sirena energizada + 5 acks encolados localmente.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-2.b",
                "Dos horas sin enlace y al reconectar no se pierde ni se duplica un evento.",
                (
                    Evidencia(
                        "edge/tests/test_cloud.py",
                        "test_offline_two_hours_then_reconnect_zero_loss_zero_dup",
                        "Los eventos encolados se drenan en orden y sin `event_id` repetido.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-2.c",
                "La cola durable sobrevive al reinicio del proceso.",
                (
                    Evidencia(
                        "edge/tests/test_cloud.py",
                        "test_durable_queue_survives_restart",
                        "Un `CloudConnector` nuevo sobre el mismo spool recupera el atraso.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-2.d",
                "La evidencia miniSEED encolada offline se sube al reconectar.",
                (
                    Evidencia(
                        "edge/tests/test_backfill.py",
                        "test_offline_event_evidence_uploads_on_reconnect",
                        "Cero PUT mientras está offline; al volver, sube con su sha256.",
                    ),
                ),
            ),
        ),
    ),
    Requisito(
        "RO-3",
        afirmaciones=(
            Afirmacion(
                "RO-3.a",
                "El mismo `event_id` recorrido dos veces por el camino completo "
                "(SQS→consumidor→DB) produce un solo incidente.",
                (
                    Evidencia(
                        "api/tests/test_ingest_e2e.py",
                        "test_local_event_escalates_into_single_incident",
                        "Dos mensajes con el mismo `event_id` ⇒ una fila en `incidents`, DLQ "
                        "vacía.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-3.b",
                "La idempotencia está en la DB, no sólo en el código de aplicación.",
                (
                    Evidencia(
                        "api/tests/test_idempotency.py",
                        "test_incident_event_uuid_idempotent",
                        "`ON CONFLICT (event_uuid) DO NOTHING`: rowcount 1 y luego 0.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-3.c",
                "La superficie de escritura HTTP tolera el reintento del cliente offline.",
                (
                    Evidencia(
                        "api/tests/api/test_mobile_core.py",
                        "test_checkin_replay_offline_es_idempotente",
                        "Reenviar el mismo `checkin_id` devuelve la fila idéntica; otro "
                        "portador con el mismo id recibe 409.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-3.d",
                "El nonce de intención emitido por el servidor es de un solo uso.",
                (
                    Evidencia(
                        "api/tests/api/test_command_intent.py",
                        "test_intencion_firmada_feliz_y_replay_rechazado",
                        "Primera llamada 201; el replay exacto del intento firmado, 409.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-3.e",
                "El anti-replay de configuración firmada sobrevive a un reinicio del edge.",
                (
                    Evidencia(
                        "edge/tests/test_config.py",
                        "test_replay_rejected_across_restart",
                        "Un `ConfigStore` nuevo sobre la misma caché sigue rechazando la "
                        "versión ya vista.",
                    ),
                ),
            ),
        ),
    ),
    Requisito(
        "RO-4",
        nota=(
            "«Mínimo» está bien cubierto; **«auditable» no lo está en el edge**, y la "
            "pregunta de qué proceso corre de verdad en el gabinete no la responde ningún "
            "test."
        ),
        afirmaciones=(
            Afirmacion(
                "RO-4.a",
                "El proceso GPIO no carga dependencias pesadas (NumPy/SciPy/ObsPy).",
                (
                    Evidencia(
                        "edge/tests/test_gpio_process.py",
                        "test_gpio_process_does_not_import_heavy_deps",
                        "Ninguna de numpy/obspy/scipy/pandas/matplotlib en `sys.modules` del hijo.",
                    ),
                    Evidencia(
                        "edge/tests/test_gpio_process.py",
                        "test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada",
                        "Y la versión *fail-closed*: lista blanca en vez de lista negra.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-4.b",
                "Arranca en menos de un segundo.",
                (
                    Evidencia(
                        "edge/tests/test_gpio_process.py",
                        "test_gpio_process_starts_under_one_second",
                        "Mide de la primera importación al retorno de `run_gpio_process`.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-4.c",
                "La propiedad de los pines es exclusiva: un segundo dueño no toca un pin.",
                (
                    Evidencia(
                        "edge/tests/test_gpio_ownership.py",
                        "test_un_segundo_dueno_no_toca_un_solo_pin_y_lo_grita",
                        "El segundo `GpioController` muere antes de abrir un pin y grita el "
                        "PID del dueño.",
                    ),
                    Evidencia(
                        "edge/tests/test_gpio_traspaso.py",
                        "test_los_dos_servicios_a_la_vez_no_mueven_un_solo_pin",
                        "Seis rondas de crash-loop cruzado: cero transiciones eléctricas de "
                        "más en gas y retenedor.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-4.d",
                "Un arranque fallido deja los relés en seguro ANTES de soltar el cerrojo.",
                (
                    Evidencia(
                        "edge/tests/test_gpio_ownership.py",
                        "test_un_arranque_fallido_deja_los_reles_EN_SEGURO_antes_de_soltar_el_cerrojo",
                        "Fotografía el nivel y la función de los 5 pines en el instante exacto "
                        "de liberar el cerrojo.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-4.e",
                "«Auditable»: toda acción de actuador queda registrada en el edge con quién "
                "la ordenó y cuándo.",
                (),
                hueco=(
                    "No hay bitácora de actuación en el gabinete. `ActuatorAck` "
                    "(`edge/takab_edge/contracts.py`) lleva canal, acción, `event_id`, "
                    "éxito y latencia — **no lleva actor**, y `GpioController.set_relay` no "
                    "emite ni una línea de registro. El único `audit_log` vive en la nube "
                    "(`api/src/takab_api/audit.py`), o sea que **una actuación ejecutada con "
                    "el enlace caído —el caso para el que existe el gabinete— no deja rastro "
                    "auditable en ninguna parte.** Es la mitad no construida de la regla 4."
                ),
            ),
            Afirmacion(
                "RO-4.f",
                "El gabinete desplegado corre el proceso mínimo como dueño de los pines.",
                (),
                hueco=(
                    "Ningún test lee qué unidad queda habilitada ni qué dice "
                    "`/etc/takab/edge.env`, y `deploy/edge/deploy.sh` no ejecuta ningún "
                    "`systemctl enable`. Los tests de despliegue van a propósito en la "
                    "dirección contraria: "
                    "`edge/tests/test_deploy_sh.py"
                    "::test_la_verificacion_no_esta_anclada_al_nombre_takab_edge` "
                    "exige que la comprobación sea agnóstica del nombre. Con "
                    '`gpio_owner = "edge"` por defecto, **el estado de fábrica es el que la '
                    "regla 4 prohíbe** y sólo un archivo fuera del repo lo corrige. Es la "
                    "otra cara de `RO-1.d`."
                ),
            ),
        ),
    ),
    Requisito(
        "RO-5",
        afirmaciones=(
            Afirmacion(
                "RO-5.a",
                "Toda tabla de negocio lleva `tenant_id`, comprobado DERIVANDO la lista del "
                "catálogo y no de una lista escrita a mano.",
                (),
                hueco=(
                    "El único cruce contra el catálogo corre en la dirección opuesta —las "
                    "tablas que YA tienen `tenant_id` deben tener RLS (`RO-5.b`)—, así que "
                    "**una tabla de negocio nueva que nazca sin `tenant_id` no es vista por "
                    "nadie**: no tiene la columna, luego no entra en el censo, luego no se le "
                    "exige RLS. El punto ciego se cierra solo. La lista más parecida a un "
                    "censo, `api/tests/test_timescale_jobs.py::test_business_tables_have_force`, "
                    "es una tupla de cuatro nombres escrita a mano."
                ),
            ),
            Afirmacion(
                "RO-5.b",
                "Toda tabla con `tenant_id` tiene RLS activa y con políticas, derivado del "
                "catálogo de Postgres.",
                (
                    Evidencia(
                        "api/tests/ops/test_restore_check.py",
                        "test_la_base_migrada_pasa_entera",
                        "`verify()` recorre `pg_catalog` y falla cualquier tabla con "
                        "`tenant_id` sin `relrowsecurity`, y cualquier tabla con RLS y cero "
                        "políticas.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-5.c",
                "Una lectura cruzada entre tenants no devuelve nada.",
                (
                    Evidencia(
                        "api/tests/test_rls_isolation.py",
                        "test_app_cannot_read_other_tenant",
                        "Como `takab_app` con `app.tenant_id=B`, contar filas de A da 0.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-5.d",
                "Una escritura cruzada entre tenants es rechazada por la DB.",
                (
                    Evidencia(
                        "api/tests/test_rls_isolation.py",
                        "test_app_cannot_write_other_tenant",
                        "El `INSERT` etiquetado con otro tenant levanta "
                        "`InsufficientPrivilege` (WITH CHECK).",
                    ),
                ),
            ),
            Afirmacion(
                "RO-5.e",
                "La API rechaza el cruce con un JWT real, no sólo la DB.",
                (
                    Evidencia(
                        "api/tests/auth/test_guc_propagation.py",
                        "test_gucs_propagate_and_no_cross_tenant_read",
                        "Petición HTTP real: el token de A ve el incidente de A y no el de B, "
                        "y simétrico.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-5.f",
                "La función de alcance, invocada con el filtro puesto, deja cero sitios ante "
                "un claim vacío.",
                (
                    Evidencia(
                        "api/tests/auth/test_console_scope.py",
                        "test_fase_B_un_claim_vacio_significa_cero_sitios",
                        "Unidad pura con `enforced=True`: claim vacío ⇒ cero sitios.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-5.g",
                "El servidor filtra de verdad por sitio en el despliegue real.",
                (),
                hueco=(
                    "La conducta impuesta sólo se prueba como unidad pura pasando "
                    "`enforced=True` a mano; **ningún test recorre el HTTP con el filtro "
                    "puesto**. En producción la perilla está en `False` "
                    "(`api/src/takab_api/settings.py`) y es la única brecha multi-tenant "
                    "viva, la que `T-2.89` existe para cerrar. Y hay algo peor que el hueco: "
                    "dos tests HTTP fijan la conducta NO impuesta —"
                    "`api/tests/api/test_console_scope.py::test_fase_A_sin_claim_la_consola_NO_se_queda_en_blanco`"
                    " y `::test_me_dice_si_el_servidor_esta_filtrando_de_verdad`—, así que "
                    "**encender la perilla pondrá la suite en rojo**. Quien ejecute `T-2.89` "
                    "tiene que contar con eso."
                ),
            ),
        ),
    ),
    Requisito(
        "RO-6",
        afirmaciones=(
            Afirmacion(
                "RO-6.a",
                "Ningún secreto vive en el árbol: alguien barre el repo buscándolos.",
                (),
                hueco=(
                    "**No existe barrido de secretos en ninguna parte.** Ni test, ni paso de "
                    "CI, ni `.pre-commit-config.yaml` (no hay), ni `gitleaks`/`trufflehog`/"
                    "`detect-secrets` en todo el repo. La regla 6 se sostiene hoy sólo sobre "
                    "la disciplina de quien escribe el diff — que es exactamente la clase de "
                    "garantía que este proyecto no acepta en ninguna otra regla."
                ),
            ),
            Afirmacion(
                "RO-6.b",
                "Sin secreto configurado, la superficie que lo necesita se cierra en vez de "
                "seguir sirviendo.",
                (
                    Evidencia(
                        "api/tests/api/test_command_intent.py",
                        "test_sin_secreto_configurado_es_503_fail_closed",
                        "Borrado `TAKAB_API_COMMAND_INTENT_SECRET`, los endpoints tácticos "
                        "devuelven 503.",
                    ),
                    Evidencia(
                        "api/tests/commands/test_keys.py",
                        "test_build_key_provider_precedence_and_fail_closed",
                        "Precedencia env → Secrets Manager, y sin ninguno `key_for()` "
                        "devuelve `None` (cierra, no inventa).",
                    ),
                ),
            ),
            Afirmacion(
                "RO-6.c",
                "En producción, un secreto ausente hace ruido en el arranque en vez de caer "
                "al valor por defecto de desarrollo.",
                (),
                hueco=(
                    "`Settings` no tiene ningún validador de entorno: sus valores por defecto "
                    "**son credenciales de desarrollo**, así que una variable que falte en "
                    "producción no truena — se resuelve silenciosamente al default de dev. Lo "
                    "cubierto en `RO-6.b` es *fail-closed por endpoint* para dos secretos "
                    "concretos; no hay guarda de arranque para el resto."
                ),
            ),
        ),
    ),
    Requisito(
        "RO-7",
        nota=(
            "Cobertura por muestreo, no sistemática: cada superficie tiene su prueba "
            "ejemplar, y **no hay nada que obligue a la número 28**."
        ),
        afirmaciones=(
            Afirmacion(
                "RO-7.a",
                "Un censo DERIVADO obliga a que todo componente que pinte dato de servidor "
                "declare sus cuatro estados.",
                (
                    Evidencia(
                        "web/e2e/screens.spec.ts",
                        "declara los estados obligatorios: nunca una caja en blanco",
                        "Por pantalla, exige ≥1 `[data-state]` con valor del conjunto "
                        "permitido; nunca exige que exista `stale`.",
                        apagable="suite no bloqueante (e2e.yml)",
                    ),
                ),
                hueco=(
                    "No existe censo derivado. La guarda real es el ayudante opt-in "
                    "`web/src/test-utils/states.ts::expectFourStates()`, que cada test tiene "
                    "que acordarse de llamar. Medido el 2026-08-08: **27** componentes de "
                    "`web/src` usan `StateFrame` y sólo **14** tienen la prueba de los cuatro "
                    "estados; y hay **al menos 12 componentes que pintan dato de servidor "
                    "FUERA de `StateFrame`** (`KpiStrip`, `MapPanel`, `Topbar`, `SiteCard`, "
                    "`UpsGauge`, `SyncBadge`…), cada uno con su propio `S/D` a mano. El bug de "
                    "`T-2.59` fue exactamente eso. La única cita posible vive en la matriz de "
                    "Playwright, que **no bloquea un merge** — y aun así nunca exige un "
                    "estado `stale`."
                ),
            ),
            Afirmacion(
                "RO-7.b",
                "La consola SOC rotula el dato viejo en vez de pintarlo como fresco.",
                (
                    Evidencia(
                        "web/src/features/console/DetailPanel.test.tsx",
                        "M-6: flota vieja se rotula stale, no se pinta como fresca",
                        "Flota de hace 10 min ⇒ la tarjeta dice DATOS RETENIDOS.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-7.c",
                "El panel del gabinete no pinta una medición de hace dos horas como viva.",
                (
                    Evidencia(
                        "edge/tests/test_local_api_panel.py",
                        "test_feature_vieja_no_se_pinta_como_medicion_viva",
                        "Con `age_s=7200` las barras dicen S/D y la brújula estampa SIN SEÑAL "
                        "DEL SENSOR.",
                        apagable="skipif",
                        garantia_ci="run: node --version",
                    ),
                ),
            ),
            Afirmacion(
                "RO-7.d",
                "La app móvil sirve la copia vieja con su edad, nunca como dato fresco.",
                (
                    Evidencia(
                        "mobile/src/ui/StateFrame.test.tsx",
                        "stale: contenido VIEJO con banner DATOS RETENIDOS + edad honesta",
                        "El contenido viejo se pinta bajo `state-stale` con la edad real.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-7.e",
                "La tira de KPI de `/fleet` dice S/D cuando no hay dato, jamás cero.",
                (
                    Evidencia(
                        "web/src/features/fleet/FleetPage.test.tsx",
                        "sin dato (%s) los KPI dicen S/D, no CERO",
                        "Con la consulta en error 503 o cargando, los cuatro KPI dicen S/D.",
                    ),
                ),
            ),
        ),
    ),
    Requisito(
        "RO-8",
        nota=(
            "Cinco controles en una sola frase, y hay que puntuarlos por separado: firma, "
            "MFA, rate-limit, nonce y ack. **El MFA es el único de los cinco sin una sola "
            "línea de prueba en ninguna capa.**"
        ),
        afirmaciones=(
            Afirmacion(
                "RO-8.a",
                "Una firma inválida ni ejecuta ni ackea.",
                (
                    Evidencia(
                        "edge/tests/test_dispatch.py",
                        "test_bad_signature_neither_executes_nor_acks",
                        "Payload manipulado sin refirmar: ni ack ni actuador.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-8.b",
                "La nube firma con la clave del gabinete concreto, no con una compartida.",
                (
                    Evidencia(
                        "api/tests/api/test_commands_router.py",
                        "test_each_gateway_signs_with_its_own_key",
                        "La firma queda atada a la clave del gateway destinatario.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-8.c",
                "El endpoint de comando exige MFA.",
                (),
                hueco=(
                    "**Cero cobertura en cualquier capa.** No hay comprobación de claim "
                    "`acr`/`amr`/`auth_time` en la petición: el docstring de "
                    "`api/src/takab_api/routers/commands.py` documenta el control como "
                    '*delegado* al pool de Cognito (`mfa_configuration = "ON"`, '
                    "`infra/terraform/modules/identity/main.tf`). Eso es una **suposición, "
                    "no un control**: el módulo `identity` es el único de los cuatro sin "
                    "`.tftest.hcl`, así que una deriva de la configuración del pool a "
                    "`OPTIONAL` no la detecta nadie, y un token emitido por cualquier camino "
                    "que no pase por TOTP entra sin que la aplicación lo note. Es el hueco más "
                    "grave de la matriz: la regla de oro 8 dice «sin excepción» sobre la "
                    "superficie que abre válvulas de gas."
                ),
            ),
            Afirmacion(
                "RO-8.d",
                "Hay rate-limit por usuario y sitio.",
                (
                    Evidencia(
                        "api/tests/api/test_commands_router.py",
                        "test_rate_limit_user_site_429",
                        "Con el límite en 2/min, el tercer POST es 429 y no se publica.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-8.e",
                "Hay rate-limit por sitio, independiente del usuario.",
                (),
                hueco=(
                    "`command_rate_site_per_min` está implementado "
                    "(`api/src/takab_api/commands/service.py`) y **no lo prueba nadie**: "
                    "sólo se prueba el límite usuario+sitio. Dos operadores coordinados "
                    "agotan el presupuesto del sitio sin que ningún test lo vea."
                ),
            ),
            Afirmacion(
                "RO-8.f",
                "Un nonce ya visto se rechaza, en el edge y en la nube.",
                (
                    Evidencia(
                        "edge/tests/test_dispatch.py",
                        "test_replayed_nonce_rejected_silently",
                        "El comando byte-idéntico reenviado produce un solo ack.",
                    ),
                    Evidencia(
                        "api/tests/api/test_command_intent.py",
                        "test_intencion_firmada_feliz_y_replay_rechazado",
                        "En la nube, el replay exacto del intento es 409.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-8.g",
                "El rechazo por replay queda AUDITADO.",
                (),
                hueco=(
                    "Se rechaza pero no se apunta. En el edge el camino de replay sólo emite "
                    "`log.warning` (no hay sumidero de auditoría); en la nube el 409 sale sin "
                    "llamada a auditoría y el test comprueba únicamente el código de estado. "
                    "**Un atacante que sondee con comandos repetidos es invisible en el "
                    "`audit_log`** — que es donde se investigaría el incidente. "
                    "`api/tests/commands/test_ack_ingest.py"
                    "::test_wrong_gateway_is_rejected_with_audit` "
                    "sí audita, pero un *ack* falsificado, no un replay de comando: no cuenta."
                ),
            ),
            Afirmacion(
                "RO-8.h",
                "Hay ack de ejecución y un comando sin ack nunca se reporta como ejecutado.",
                (
                    Evidencia(
                        "api/tests/commands/test_sync.py",
                        "test_expires_stale_pending_commands",
                        "Pasado el TTL, `pending` pasa a `expired` con «sin ack dentro del TTL».",
                    ),
                    Evidencia(
                        "api/tests/commands/test_ack_ingest.py",
                        "test_late_ack_does_not_revive_expired",
                        "Un ack que llega tarde no resucita el comando vencido.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-8.i",
                "Un comando viejo con firma válida se rechaza (TTL de la firma).",
                (
                    Evidencia(
                        "edge/tests/test_dispatch.py",
                        "test_expired_command_rejected_silently",
                        "Firmado con `ts = ahora-120 s` y TTL de 30 s: cero acks.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-8.j",
                "La emisión de un comando queda auditada.",
                (
                    Evidencia(
                        "api/tests/api/test_commands_router.py",
                        "test_issue_command_signs_publishes_and_persists",
                        "El verbo `command_issued` aparece en `audit_log` del tenant.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-8.k",
                "Un comando DENEGADO (403/409/429/503) queda auditado.",
                (),
                hueco=(
                    "Sólo se audita el camino feliz. Ningún test cubre la auditoría de una "
                    "denegación, y para el 429 y el 409 no hay ni siquiera llamada a "
                    "auditoría en el código. Junto con `RO-8.g`: **la bitácora de la "
                    "superficie más sensible del sistema registra lo que salió bien y calla "
                    "lo que se intentó.**"
                ),
            ),
        ),
    ),
    Requisito(
        "RO-9",
        nota=(
            "Es la regla de oro con la brecha más limpia entre lo declarado y lo verificado: "
            "está escrita en tres documentos, clasificada como invariante permanente en "
            "`BLUEPRINT §14`… y **no la sostiene ni un test**."
        ),
        afirmaciones=(
            Afirmacion(
                "RO-9.a",
                "El enlace edge→nube nunca publica forma de onda cruda en continuo.",
                (),
                hueco=(
                    "**Nada lo impide ni lo detecta.** No hay assert sobre un conjunto CERRADO "
                    "de topics publicados, ninguno sobre volumen o tasa, y ninguno que diga "
                    "que un `WaveformPacket` jamás se entrega a `CloudConnector.publish`. "
                    "Añadir hoy un publicador continuo de crudo **no rompería un solo test**. "
                    "Lo más parecido que existe protege la superficie del cliente "
                    "(`web/src/features/triage/model.test.ts`, `mobile/.../panel.test.tsx`: no "
                    "se ofrece pedir el crudo), no el enlace. Como la regla es una restricción "
                    "de costo y de red, su violación se descubriría en la factura."
                ),
            ),
            Afirmacion(
                "RO-9.b",
                "El miniSEED crudo sube a S3 SÓLO en eventos confirmados.",
                (),
                hueco=(
                    "La compuerta existe en el código (`EdgeSupervisor` sólo encola "
                    "evidencia con tier "
                    "`RESTRICTED`/`EVACUATE_OR_HOLD`) y **la dirección «sólo» no la prueba "
                    "nadie**: todos los tests de evidencia recorren el camino del evento "
                    "confirmado hacia adelante y comprueban que funciona. Ninguno comprueba "
                    "que un tier `normal` produce cero PUT. Bajar el umbral por accidente "
                    "convierte esto en el streaming continuo que la regla 9 prohíbe, sin rojo."
                ),
            ),
        ),
    ),
    Requisito(
        "RO-10",
        afirmaciones=(
            Afirmacion(
                "RO-10.a",
                "El motor de reglas registra una vez por transición de tier, no por evaluación.",
                (
                    Evidencia(
                        "edge/tests/test_rules.py",
                        "test_tier_transition_logged_once_per_change",
                        "Tres evaluaciones con una repetida producen exactamente 2 registros.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-10.b",
                "La salud registra por cambio discreto, no por deriva continua.",
                (
                    Evidencia(
                        "edge/tests/test_health.py",
                        "test_transition_logged_only_on_discrete_change",
                        "La deriva de 25→30 °C bajo umbral no emite; los dos cambios de estado sí.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-10.c",
                "La salud del dispositivo llega por latido periódico y etiquetado como tal.",
                (
                    Evidencia(
                        "edge/tests/test_health.py",
                        "test_heartbeat_thread_emits_periodic_snapshots",
                        "Con `heartbeat_s=0.05` salen ≥3 instantáneas por temporizador.",
                    ),
                    Evidencia(
                        "api/tests/test_ingest_handlers.py",
                        "test_health_default_reason_is_heartbeat",
                        "En la nube, una salud sin motivo se persiste como `heartbeat`.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-10.d",
                "En la nube, `rule_evaluations` no gana filas en estado estable.",
                (),
                hueco=(
                    "La propiedad se prueba en el edge al nivel del registro, nunca al nivel "
                    "de la tabla. De hecho **no hay escritor de `rule_evaluations` en "
                    "`api/src`** —sólo lectores en `queries/mobile.py` y `ws/hub.py`—, "
                    "así que hoy la regla se cumple por ausencia de código, no por una "
                    "guarda. El día que se escriba el ingestor, nada avisará si escribe por "
                    "intervalo."
                ),
            ),
        ),
    ),
    Requisito(
        "RO-11",
        afirmaciones=(
            Afirmacion(
                "RO-11.a",
                "Una regla de retención que borre filas de una tabla de compliance se "
                "rechaza, y se rechaza ANTES de borrar nada.",
                (
                    Evidencia(
                        "api/tests/test_privacy_retention.py",
                        "test_una_regla_que_borra_filas_de_una_tabla_protegida_es_rechazada",
                        "Parametrizado sobre las cinco tablas protegidas: `RetentionUnsafe` y "
                        "conteo idéntico antes/después.",
                    ),
                    Evidencia(
                        "api/tests/test_privacy_retention.py",
                        "test_el_rechazo_ocurre_en_el_preflight_antes_de_cualquier_conteo",
                        "El plan entero aborta en el preflight.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-11.b",
                "Ni saltándose el guard puede el job borrar evidencia: lo impide la propia base.",
                (
                    Evidencia(
                        "api/tests/test_privacy_retention.py",
                        "test_ni_saltandose_el_guard_puede_el_job_borrar_evidencia",
                        "`DELETE` crudo en la sesión del job ⇒ 42501 o P0001 (trigger "
                        "append-only).",
                    ),
                ),
            ),
            Afirmacion(
                "RO-11.c",
                "ARCO anonimiza al titular sin perder una sola fila.",
                (
                    Evidencia(
                        "api/tests/test_privacy_erasure.py",
                        "test_arco_anonimiza_al_titular_sin_perder_una_sola_fila",
                        "Censo de filas sobre 9 tablas idéntico antes y después.",
                    ),
                ),
            ),
            Afirmacion(
                "RO-11.d",
                "El hecho sobrevive a la anonimización: el check-in sigue contando.",
                (
                    Evidencia(
                        "api/tests/test_privacy_erasure.py",
                        "test_el_checkin_anonimizado_sigue_contando_para_el_incidente",
                        "El conteo del incidente no cambia; la geometría precisa sí se anula.",
                    ),
                ),
            ),
        ),
    ),
)


# --- Invariantes y diferido (`BLUEPRINT §14`) ------------------------------

_INV = (
    Requisito(
        "INV-T-MINUS",
        afirmaciones=(
            Afirmacion(
                "INV-T-MINUS.a",
                "Ninguna superficie muestra una cuenta regresiva.",
                (
                    Evidencia(
                        "mobile/src/features/alert/CrisisView.test.tsx",
                        "sasmex: SIN magnitud, SIN ETA, SIN cuenta regresiva "
                        "(test que FALLA si aparecen)",
                        "Serializa el árbol renderizado entero y exige que no case `/T-[0-9]/`; "
                        "el cronómetro visible es ascendente.",
                    ),
                    Evidencia(
                        "edge/tests/test_local_api.py",
                        "test_index_has_no_external_resources",
                        "El HTML del panel no contiene `T-MINUS` ni `countdown`.",
                    ),
                ),
            ),
        ),
        nota=(
            "Sólo el test móvil escanea el árbol completo; el resto son asertos sobre "
            "elementos concretos. Un componente nuevo con cuenta regresiva pasaría todo "
            "menos el móvil."
        ),
    ),
    Requisito(
        "INV-magnitud preliminar",
        afirmaciones=(
            Afirmacion(
                "INV-magnitud.a",
                "Ninguna superficie muestra una magnitud preliminar; el banner MVP dice "
                "PROTÉJASE y nada más.",
                (
                    Evidencia(
                        "web/src/features/console/AlertBanner.test.tsx",
                        "banner MVP: PROTÉJASE + sitio + EVENT_ID + PGA MAX; sin magnitud ni "
                        "T-MINUS",
                        "El banner dice exactamente «ALERTA SÍSMICA · PROTÉJASE» y no case "
                        "`/M\\s*\\d\\.\\d/` ni `T-MINUS`.",
                    ),
                    Evidencia(
                        "mobile/src/features/alert/CrisisView.test.tsx",
                        "sasmex: SIN magnitud, SIN ETA, SIN cuenta regresiva "
                        "(test que FALLA si aparecen)",
                        "Mismo escaneo de árbol completo contra `/magnitud/i`.",
                    ),
                ),
            ),
        ),
    ),
    Requisito(
        "INV-streaming crudo continuo",
        nota="Es la regla de oro 9 vista desde el blueprint. Su estado es el de `RO-9`.",
        afirmaciones=(
            Afirmacion(
                "INV-streaming.a",
                "No se sube forma de onda cruda en continuo a la nube.",
                (),
                hueco=(
                    "Igual que `RO-9.a`: la prohibición está declarada en tres documentos y "
                    "**no la sostiene ningún test**. Que sea `[INVARIANTE]` —una tarea futura "
                    "que lo proponga «se rechaza sin discusión»— hace la ausencia más "
                    "llamativa, no menos: es la única viñeta de `§14` cuya violación sería "
                    "silenciosa en el CI."
                ),
            ),
        ),
    ),
    Requisito(
        "INV-IA en la ruta de disparo",
        afirmaciones=(
            Afirmacion(
                "INV-IA.a",
                "El proceso que dispara actuadores no puede cargar una dependencia de IA.",
                (
                    Evidencia(
                        "edge/tests/test_gpio_process.py",
                        "test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada",
                        "Lista blanca *fail-closed* sobre el grafo real de importación del "
                        "proceso de la sirena.",
                    ),
                ),
            ),
            Afirmacion(
                "INV-IA.b",
                "El motor de decisión de tier (`edge/takab_edge/rules/`) tampoco puede.",
                (),
                hueco=(
                    "La guarda de importación existe sólo para el proceso `gpio`. `rules/` "
                    "—el código que decide el tier y, con el opt-in de `RO-1.g`, dispara— no "
                    "tiene lista blanca equivalente. Es un hueco de alcance, no de "
                    "intención: el mecanismo ya está escrito y le falta el segundo objetivo."
                ),
            ),
        ),
    ),
    Requisito(
        "DIF-mini-ShakeMap",
        nota=(
            "Único DIFERIDO de `§14`: no es una prohibición permanente sino trabajo aplazado "
            "a `T-3.09`. Se lista para que el documento de entrega pueda decir qué NO hace el "
            "sistema."
        ),
        afirmaciones=(
            Afirmacion(
                "DIF-shakemap.a",
                "La consola no promete una escala de intensidad que no existe.",
                (
                    Evidencia(
                        "web/src/features/console/MapPanel.test.tsx",
                        "NO pinta bandas de intensidad: ni capas MMI ni una leyenda que "
                        "prometa una escala inexistente",
                        "Ninguna capa de MapLibre empieza por `mmi` ni hay leyenda "
                        "«INTENSIDAD MMI».",
                    ),
                ),
            ),
        ),
    ),
    Requisito(
        "INV-Shake OS",
        afirmaciones=(
            Afirmacion(
                "INV-shakeos.a",
                "No se despliega nada al Shake ni se asume que corra código nuestro: la "
                "relación es leer SeedLink y nada más.",
                (),
                hueco=(
                    "Cero enforcement ejecutable. «No se toca el Shake OS» aparece en cinco "
                    "documentos y en ningún test: nada comprueba que el despliegue no escriba "
                    "en el Shake ni que el edge sólo hable con él por SeedLink. El riesgo es "
                    "de garantía con el proveedor, y el aviso llegaría en el sitio del "
                    "cliente."
                ),
            ),
        ),
    ),
)


# --- Gates físicos y de despliegue (`RUNBOOK-auditoria-cierre §10`) --------
#
# Ningún test de software cierra estos gates: piden hardware o una cuenta AWS. Se listan
# porque una matriz de entrega que sólo hable de lo automatizable le vende al cliente la
# impresión de que no queda nada por acreditar presencialmente. Donde existe la mitad de
# software, se cita — y `G-03` es la demostración viva del criterio 2: sus tres tests EXISTEN
# y el censo los saca como SIN COBERTURA porque un `skipif` de socket los apaga en CI.

_GATES = tuple(
    Requisito(gid, no_automatizable=texto, afirmaciones=afirms)
    for gid, texto, afirms in (
        (
            "G-01",
            "Pide `sudo reboot` en un Pi físico con el gabinete armado y leer el journal.",
            (),
        ),
        (
            "G-02",
            "Pide cortar la energía del Pi y comprobar que la sirena suena por la ruta "
            "eléctrica. Por definición mide lo que pasa cuando el software no está.",
            (),
        ),
        (
            "G-03",
            "Pide 24 h de SeedLink continuo y un power-cycle físico del Shake.",
            (
                Afirmacion(
                    "G-03.a",
                    "El Shake entrega 100 sps y el stream se sostiene sin reconectar.",
                    (
                        Evidencia(
                            "edge/tests/test_seedlink_hardware.py",
                            "test_real_shake_streams_100sps",
                            "Contra el Shake real.",
                            apagable="skipif",
                        ),
                    ),
                    hueco=(
                        "El test existe y **en CI nunca corre**: su `pytestmark` es un "
                        "`skipif` de alcanzabilidad por socket al Shake, que un runner de "
                        "GitHub jamás cumple. Está censado en "
                        "`edge/tests/test_hardware_gates.py::GATES_HARDWARE` justo para que "
                        "el verde del job no se lea como acreditación (T-2.63)."
                    ),
                ),
                Afirmacion(
                    "G-03.b",
                    "El resume por número de secuencia da cero pérdida tras un hueco.",
                    (
                        Evidencia(
                            "edge/tests/test_seedlink_hardware.py",
                            "test_real_shake_backfills_via_seqnum_resume",
                            "Contra el Shake real.",
                            apagable="skipif",
                        ),
                    ),
                    hueco="Mismo `skipif` de socket: no acredita nada en CI.",
                ),
            ),
        ),
        (
            "G-04",
            "Pide recepción SASMEX real (o prueba CIRES) con el radio WR-1 conectado.",
            (),
        ),
        ("G-05", "Pide un publish desde el SOC a un gabinete físico y ver `in_sync`.", ()),
        (
            "G-06",
            "Pide un simulacro en un sitio real con cascada de notificación real.",
            (),
        ),
        ("G-07", "Pide re-emitir un comando capturado contra el gabinete físico.", ()),
        ("G-08", "Pide una flota comercial y una ventana de carga contra AWS.", ()),
        (
            "G-09",
            "Pide ejecutar los procedimientos A, B y C contra AWS y medir el RTO real "
            "(ventana `T-2.74`, bloqueada por `T-2.73.a`).",
            (),
        ),
        (
            "G-10",
            "Pide el panel LAN del Pi real y un login por rol contra el pool de Cognito.",
            (),
        ),
    )
)


REGISTRO: tuple[Requisito, ...] = _RO + _INV + _GATES


# ===========================================================================
# 5 · El veredicto se CALCULA
# ===========================================================================

CUBIERTO = "CUBIERTO"
SIN_COBERTURA = "SIN COBERTURA"
PARCIAL = "PARCIAL"


def garantia_cumplida(ev: Evidencia) -> bool:
    """¿El workflow trae el paso que impide el salto declarado en `garantia_ci`?"""
    if not ev.garantia_ci:
        return False
    return ev.garantia_ci in _texto_workflow(_suite_de(ev.archivo).workflow)


@dataclass
class EvidenciaResuelta:
    evidencia: Evidencia
    linea: int
    apagable_real: str | None

    @property
    def cita(self) -> str:
        return f"{self.evidencia.archivo}:{self.linea}"

    @property
    def neutralizado(self) -> bool:
        """Puede saltarse, pero el CI garantiza que en su corrida no se salta."""
        return self.apagable_real is not None and garantia_cumplida(self.evidencia)

    @property
    def acredita(self) -> bool:
        if self.evidencia.tipo != COMPORTAMIENTO:
            return False
        return self.apagable_real is None or self.neutralizado


@dataclass
class AfirmacionResuelta:
    afirmacion: Afirmacion
    evidencias: list[EvidenciaResuelta] = field(default_factory=list)

    @property
    def estado(self) -> str:
        return CUBIERTO if any(e.acredita for e in self.evidencias) else SIN_COBERTURA

    @property
    def motivo(self) -> str:
        """Por qué no cuenta como cubierta. Derivado, no tecleado."""
        if self.estado == CUBIERTO:
            return ""
        if not self.evidencias:
            return "sin test"
        if all(e.evidencia.tipo == DOCUMENTAL for e in self.evidencias):
            return "sólo evidencia documental"
        motivos = sorted({e.apagable_real for e in self.evidencias if e.apagable_real})
        return f"sólo tests que no corren ({'; '.join(motivos)})" if motivos else "sin prueba útil"


def resolver() -> list[tuple[Requisito, list[AfirmacionResuelta]]]:
    out: list[tuple[Requisito, list[AfirmacionResuelta]]] = []
    for req in REGISTRO:
        filas: list[AfirmacionResuelta] = []
        for af in req.afirmaciones:
            fila = AfirmacionResuelta(af)
            for ev in af.evidencias:
                loc = localiza(ev.archivo, ev.test)
                fila.evidencias.append(EvidenciaResuelta(ev, loc.linea, loc.apagable))
            filas.append(fila)
        out.append((req, filas))
    return out


def rollup(filas: list[AfirmacionResuelta]) -> str:
    if not filas:
        return SIN_COBERTURA
    cubiertas = sum(1 for f in filas if f.estado == CUBIERTO)
    if cubiertas == len(filas):
        return CUBIERTO
    return SIN_COBERTURA if cubiertas == 0 else PARCIAL


def es_gate(req: Requisito) -> bool:
    return req.rid.startswith("G-")


# ===========================================================================
# 6 · El documento se GENERA
# ===========================================================================


def _titulo_de(req: Requisito) -> str:
    if req.rid.startswith("RO-"):
        return reglas_de_oro()[req.rid]
    if es_gate(req):
        return gates_fisicos()[req.rid]
    return invariantes()[req.rid]


def _fuente_de(req: Requisito) -> str:
    if req.rid.startswith("RO-"):
        return "`CLAUDE.md §2`"
    if es_gate(req):
        return "`RUNBOOK-auditoria-cierre §10`"
    return "`BLUEPRINT §14`"


def _cabecera(resuelto: list[tuple[Requisito, list[AfirmacionResuelta]]]) -> Iterator[str]:
    soft = [(r, f) for r, f in resuelto if not es_gate(r)]
    gates = [(r, f) for r, f in resuelto if es_gate(r)]
    afs = [f for _, filas in soft for f in filas]
    cub = sum(1 for f in afs if f.estado == CUBIERTO)
    vs = [rollup(f) for _, f in soft]

    yield "# Matriz requisito → test — TAKAB Ailert"
    yield ""
    yield (
        "> **Generado, no escrito a mano.** Lo produce "
        "`api/tests/test_matriz_trazabilidad.py` a partir de tres fuentes "
        "(`CLAUDE.md §2`, `BLUEPRINT §14`, `RUNBOOK-auditoria-cierre §10`) y de la "
        "resolución por AST de cada test citado. Para regenerarlo:"
    )
    yield ">"
    yield ">     python api/tests/test_matriz_trazabilidad.py --escribir"
    yield ">"
    yield (
        "> El `archivo:línea` es **derivado**: el ancla de cada cita es el NOMBRE del test y "
        "la línea se recalcula en cada corrida. Si un test citado desaparece o se renombra, "
        "la suite del `api` se pone en rojo y este documento deja de poder generarse."
    )
    yield ""
    yield "## Cómo leer los veredictos"
    yield ""
    yield (
        f"- **`{CUBIERTO}`** — hay al menos un test que (a) existe, (b) **no** puede saltarse, "
        "(c) ejercita el código en vez de sólo cruzar documentos y (d) corre en un job que "
        "bloquea el merge."
    )
    yield (
        f"- **`{PARCIAL}`** — el requisito se parte en varias afirmaciones y sólo algunas "
        "están cubiertas. Las que no, salen listadas debajo de su tabla con lo que implican."
    )
    yield (
        f"- **`{SIN_COBERTURA}`** — ninguna afirmación tiene prueba que valga. **Éste es el "
        "contenido con valor del documento.** Una matriz sin huecos es una matriz que miente."
    )
    yield ""
    yield (
        "**Un test que se salta no es cobertura.** Es la lección de `T-2.63` (cinco tests de "
        "hardware saltándose en silencio con el job en verde) y de `T-2.58` (67 tests del "
        "panel saltados por falta de `node`). Aquí un `skipif` en un test citado degrada su "
        "fila automáticamente. Lo mismo vale para la matriz de Playwright de `web/e2e/`: es "
        "`workflow_dispatch` y `continue-on-error` **a propósito**, así que su verde informa "
        "pero no acredita."
    )
    yield ""
    yield (
        "La única excepción es el sello 🔒: un test que *puede* saltarse pero cuyo salto el "
        "workflow hace imposible con un paso propio y citado (el `node --version` que "
        "`T-2.58` añadió). Si ese paso desaparece del workflow, la suite se pone en rojo y "
        "la fila cae sola a `SIN COBERTURA`."
    )
    yield ""
    yield "## Resumen"
    yield ""
    yield "| Requisitos de software | Requisitos | Afirmaciones |"
    yield "|---|---:|---:|"
    yield f"| `{CUBIERTO}` | {vs.count(CUBIERTO)} | {cub} |"
    yield f"| `{PARCIAL}` | {vs.count(PARCIAL)} | — |"
    yield f"| `{SIN_COBERTURA}` | {vs.count(SIN_COBERTURA)} | {len(afs) - cub} |"
    yield f"| **Total** | **{len(vs)}** | **{len(afs)}** |"
    yield ""
    yield (
        f"Y **{len(gates)} gates físicos / de despliegue** que ningún test de software puede "
        "cerrar: piden hardware en sitio o una cuenta AWS. Se listan al final para que el "
        "documento de entrega no dé la impresión de que no queda nada por acreditar "
        "presencialmente."
    )
    yield ""


def _sello(e: EvidenciaResuelta) -> str:
    """La etiqueta que acompaña a una cita: por qué cuenta o por qué no."""
    partes: list[str] = []
    if e.neutralizado:
        partes.append(
            f"🔒 *lleva `{e.apagable_real}`, pero el CI lo impide con `{e.evidencia.garantia_ci}`*"
        )
    elif e.apagable_real:
        partes.append(f"⚠️ *no corre: {e.apagable_real}*")
    if e.evidencia.tipo == DOCUMENTAL:
        partes.append("📄 *documental*")
    return "".join(f"<br>{p}" for p in partes)


def _fila_markdown(fila: AfirmacionResuelta) -> str:
    af = fila.afirmacion
    if fila.evidencias:
        pruebas = "<br>".join(
            f"`{e.cita}`<br>`{e.evidencia.test}`" + _sello(e) for e in fila.evidencias
        )
        demuestra = "<br>".join(e.evidencia.demuestra for e in fila.evidencias)
    else:
        pruebas = demuestra = "—"
    marca = f"`{fila.estado}`" + (f"<br><sub>{fila.motivo}</sub>" if fila.motivo else "")
    return f"| {af.aid} | {af.texto} | {marca} | {pruebas} | {demuestra} |"


def _bloque(req: Requisito, filas: list[AfirmacionResuelta]) -> list[str]:
    out = [
        f"### {req.rid} · {_titulo_de(req)}",
        "",
        f"**Fuente:** {_fuente_de(req)} · **Veredicto:** `{rollup(filas)}`",
        "",
    ]
    if req.nota:
        out += [f"> {req.nota}", ""]
    if req.no_automatizable:
        out += [f"> **No lo cierra ningún test:** {req.no_automatizable}", ""]
    if filas:
        out += [
            "| # | Afirmación | Veredicto | Prueba (`archivo:línea`) | Qué demuestra |",
            "|---|---|---|---|---|",
        ]
        out += [_fila_markdown(f) for f in filas]
        out.append("")
    huecos = [f for f in filas if f.estado == SIN_COBERTURA]
    if huecos:
        out += [
            f"- **`{SIN_COBERTURA}` · {f.afirmacion.aid}** ({f.motivo}) — {f.afirmacion.hueco}"
            for f in huecos
        ]
        out.append("")
    return out


def render() -> str:
    resuelto = resolver()
    lineas = list(_cabecera(resuelto))
    grupos = (
        ("## Reglas de oro (`CLAUDE.md §2`)", lambda r: r.rid.startswith("RO-")),
        (
            "## Invariantes y diferido (`BLUEPRINT §14`)",
            lambda r: r.rid.startswith(("INV-", "DIF-")),
        ),
        ("## Gates físicos y de despliegue (`RUNBOOK-auditoria-cierre §10`)", es_gate),
    )
    for encabezado, filtro in grupos:
        seleccion = [(r, f) for r, f in resuelto if filtro(r)]
        if not seleccion:
            continue
        lineas += [encabezado, ""]
        for req, filas in seleccion:
            lineas += _bloque(req, filas)
    lineas += [
        "---",
        "",
        "## Qué NO garantiza esta matriz",
        "",
        "Está entera en el archivo que la genera "
        "(`api/tests/test_matriz_trazabilidad.py`, sección final). En corto:",
        "",
        "- **La semántica la decide un humano.** El generador comprueba que el test exista, "
        "que no se salte y que un job bloqueante lo corra; que además *demuestre* lo que la "
        "fila dice, no lo comprueba nadie automáticamente.",
        "- **La descomposición en afirmaciones es un juicio editorial.** Las once reglas, los "
        "seis invariantes y los diez gates se derivan de su fuente; partirlos en `a`/`b`/`c` "
        "no. Una afirmación que nadie escribió no aparece como hueco.",
        "- **`CUBIERTO` no dice «bien cubierto».** Dice que hay al menos una prueba viva. Un "
        "requisito con una prueba superficial sale igual de verde que uno con quince.",
        "",
    ]
    return "\n".join(lineas).rstrip() + "\n"


# ===========================================================================
# 7 · Las guardas
# ===========================================================================


def test_el_censo_de_reglas_de_oro_es_el_que_declara_claude_md() -> None:
    """Añadir o quitar una regla de oro obliga a tratarla aquí. Nada de copias."""
    declaradas = set(reglas_de_oro())
    assert len(declaradas) == 11, (
        f"`CLAUDE.md §2` ya no declara 11 reglas de oro sino {len(declaradas)}: {declaradas}. "
        "Si el cambio es legítimo, la matriz tiene que tratar la regla nueva."
    )
    en_matriz = {r.rid for r in REGISTRO if r.rid.startswith("RO-")}
    assert en_matriz == declaradas, (
        "La matriz no cubre exactamente las reglas de oro que declara `CLAUDE.md §2`.\n"
        f"  sin fila en la matriz: {sorted(declaradas - en_matriz)}\n"
        f"  en la matriz y ya no en la fuente: {sorted(en_matriz - declaradas)}"
    )


def test_el_censo_de_invariantes_es_el_que_declara_el_blueprint() -> None:
    declarados = set(invariantes())
    assert len(declarados) == 6, (
        f"`BLUEPRINT §14` ya no declara 6 viñetas clasificadas sino {len(declarados)}: "
        f"{declarados}."
    )
    en_matriz = {r.rid for r in REGISTRO if r.rid.startswith(("INV-", "DIF-"))}
    assert en_matriz == declarados, (
        "La matriz no cubre exactamente los invariantes de `BLUEPRINT §14`.\n"
        f"  sin fila: {sorted(declarados - en_matriz)}\n"
        f"  huérfanos: {sorted(en_matriz - declarados)}"
    )


def test_el_censo_de_gates_es_el_que_declara_el_runbook_de_auditoria() -> None:
    declarados = set(gates_fisicos())
    assert len(declarados) == 10, (
        f"`RUNBOOK-auditoria-cierre §10` ya no declara 10 gates sino {len(declarados)}."
    )
    en_matriz = {r.rid for r in REGISTRO if es_gate(r)}
    assert en_matriz == declarados, (
        "La matriz no cubre exactamente los gates del registro.\n"
        f"  sin fila: {sorted(declarados - en_matriz)}\n"
        f"  huérfanos: {sorted(en_matriz - declarados)}"
    )


def test_cada_test_citado_existe_con_ese_nombre() -> None:
    """**Criterio 3.** Borra un test citado y esto se pone rojo señalando la fila."""
    rotas: list[str] = []
    for req in REGISTRO:
        for af in req.afirmaciones:
            for ev in af.evidencias:
                try:
                    localiza(ev.archivo, ev.test)
                except CitaRota as exc:
                    rotas.append(f"{af.aid}: {ev.archivo} :: {exc}")
    assert not rotas, (
        "La matriz cita pruebas que ya no existen. Una cita rota es la forma más cara de "
        "mentira de un documento de trazabilidad: dice que algo está demostrado y señala al "
        "vacío.\n  " + "\n  ".join(rotas) + "\n"
        "  Arregla la cita (el ancla es el NOMBRE del test) o baja la fila a SIN COBERTURA "
        "explicando qué se perdió."
    )


def test_lo_apagable_declarado_es_lo_que_ve_el_ast() -> None:
    """Ponerle un `skipif` a un test citado como incondicional tiene que doler."""
    discrepan: list[str] = []
    for req in REGISTRO:
        for af in req.afirmaciones:
            for ev in af.evidencias:
                real = localiza(ev.archivo, ev.test).apagable
                if (real is None) != (ev.apagable is None):
                    discrepan.append(
                        f"{af.aid} · {ev.archivo}::{ev.test} — declarado {ev.apagable!r}, "
                        f"el árbol dice {real!r}"
                    )
    assert not discrepan, (
        "Una cita declara mal si su prueba puede no ejecutarse:\n  "
        + "\n  ".join(discrepan)
        + "\n  Si alguien le puso un `skipif` a un test citado, la fila deja de estar "
        "cubierta: declara `apagable=` y escribe el `hueco`."
    )


def test_toda_garantia_de_ci_declarada_sigue_en_su_workflow() -> None:
    """Quitar el paso que impide un salto vuelve a apagar la prueba que se apoyaba en él.

    Es el defecto de `T-2.58` reintroducido: el `skipif` de `node` sigue ahí, el paso
    `node --version` desaparece, los tests del panel se saltan otra vez EN SILENCIO y el job
    sigue verde. Aquí, además, la matriz habría seguido publicando `CUBIERTO`.
    """
    rotas = [
        f"{af.aid} · {ev.archivo}::{ev.test} — {ev.garantia_ci!r} ya no está en "
        f"`{_suite_de(ev.archivo).workflow}`"
        for req in REGISTRO
        for af in req.afirmaciones
        for ev in af.evidencias
        if ev.garantia_ci and not garantia_cumplida(ev)
    ]
    assert not rotas, (
        "Garantías de CI que ya no existen; las filas que se apoyaban en ellas dejan de "
        "estar cubiertas:\n  " + "\n  ".join(rotas)
    )


def test_una_garantia_de_ci_solo_vale_si_hay_algo_que_garantizar() -> None:
    """Una garantía sobre un test que no puede saltarse es texto muerto que engaña al lector."""
    sobrantes = [
        f"{af.aid} · {ev.archivo}::{ev.test}"
        for req in REGISTRO
        for af in req.afirmaciones
        for ev in af.evidencias
        if ev.garantia_ci and localiza(ev.archivo, ev.test).apagable is None
    ]
    assert not sobrantes, (
        f"Estas citas declaran una garantía de CI y su test ya no se puede saltar: "
        f"{sobrantes}. Borra la garantía."
    )


def test_toda_afirmacion_sin_cobertura_declara_lo_que_implica() -> None:
    """Un hueco mudo es peor que un hueco: parece un descuido de formato."""
    mudas = [
        f"{af.afirmacion.aid} ({af.motivo})"
        for _, filas in resolver()
        for af in filas
        if af.estado == SIN_COBERTURA and not af.afirmacion.hueco.strip()
    ]
    assert not mudas, (
        "Afirmaciones sin cobertura y sin explicar qué implica el hueco: "
        f"{mudas}\n  El valor de esta matriz son los huecos; uno sin consecuencia escrita "
        "no le sirve a nadie."
    )


def test_ninguna_afirmacion_cubierta_arrastra_un_hueco_viejo() -> None:
    """El texto del hueco tiene que morir cuando llega la prueba que lo cierra."""
    rancias = [
        af.afirmacion.aid
        for _, filas in resolver()
        for af in filas
        if af.estado == CUBIERTO and af.afirmacion.hueco.strip()
    ]
    assert not rancias, (
        f"Estas afirmaciones ya están cubiertas y siguen arrastrando texto de hueco: "
        f"{rancias}. Bórralo en el mismo commit que trae la prueba."
    )


def test_todo_gate_dice_por_que_ningun_test_lo_cierra() -> None:
    faltan = [r.rid for r in REGISTRO if es_gate(r) and not r.no_automatizable.strip()]
    assert not faltan, (
        f"Gates listados sin decir por qué no los cierra el software: {faltan}. Sin esa "
        "frase, un `SIN COBERTURA` de gate se confunde con un defecto de cobertura."
    )


def test_los_jobs_de_ci_declarados_existen_en_su_workflow() -> None:
    """Si el job desaparece o se renombra, la matriz no puede seguir diciendo «lo corre CI»."""
    perdidos = [
        f"{s.raiz} → {s.workflow} :: {s.job_ci!r}"
        for s in SUITES
        if f"name: {s.job_ci}" not in _texto_workflow(s.workflow)
    ]
    assert not perdidos, (
        "Suites que apuntan a un job de CI que ya no existe con ese nombre:\n  "
        + "\n  ".join(perdidos)
        + "\n  Mientras esto no cuadre, la columna de veredictos afirma algo que no se "
        "puede comprobar."
    )


def test_la_matriz_sabe_cual_es_la_suite_que_no_bloquea() -> None:
    """Control del detector de «suite no bloqueante»: sin él, `web/e2e` pasaría por gate.

    Estado verificado el 2026-08-08: `ci.yml` dispara en `pull_request`, `e2e.yml` es
    `workflow_dispatch` a propósito (ver su cabecera). Si esto cambia, cambia la conclusión
    de las filas que citan Playwright — no el número que hace pasar el test.
    """
    por_workflow = {s.workflow: bloquea_el_merge(s) for s in SUITES}
    assert por_workflow == {"ci.yml": True, "e2e.yml": False}, (
        f"El disparador de los workflows cambió: {por_workflow}. Si `e2e.yml` pasó a correr "
        "en cada PR, sus tests ya acreditan y hay que revisar los huecos que se apoyan en "
        "que no lo hacían (`RO-7.a`)."
    )


def test_el_archivo_de_matriz_es_el_que_deriva_el_registro() -> None:
    """Drift gate, igual que el del SDK: el `.md` publicado no puede irse por su cuenta."""
    esperado = render()
    assert MATRIZ.is_file(), (
        f"Falta `{MATRIZ.relative_to(REPO)}`. Genéralo con:\n"
        "    python api/tests/test_matriz_trazabilidad.py --escribir"
    )
    actual = MATRIZ.read_text(encoding="utf-8")
    if actual == esperado:
        return
    esperadas, actuales = esperado.splitlines(), actual.splitlines()
    primera = next(
        (
            i
            for i in range(max(len(esperadas), len(actuales)))
            if esperadas[i : i + 1] != actuales[i : i + 1]
        ),
        0,
    )
    raise AssertionError(
        "`MATRIZ-REQUISITO-TEST.md` ya no es lo que deriva el registro. Suele ser un test "
        "citado que cambió de línea; también puede ser que alguien editara el documento a "
        "mano, que es justo lo que este gate impide.\n"
        f"  primera diferencia en la línea {primera + 1}:\n"
        f"    derivado: {esperadas[primera : primera + 1]}\n"
        f"    en disco: {actuales[primera : primera + 1]}\n"
        "  Regenera con:  python api/tests/test_matriz_trazabilidad.py --escribir"
    )


def test_el_conteo_del_resumen_no_esta_tecleado() -> None:
    """La cabecera de `TASKS.md` decía «9 de 9» con 134 tareas dentro. Aquí no puede pasar."""
    resuelto = resolver()
    soft = [f for r, filas in resuelto if not es_gate(r) for f in filas]
    cub = sum(1 for f in soft if f.estado == CUBIERTO)
    texto = render()
    assert f"| **Total** | **{len([1 for r, _ in resuelto if not es_gate(r)])}** " in texto
    assert f"| `{CUBIERTO}` | " in texto
    assert texto.count(f"`{SIN_COBERTURA}` · ") == len(soft) - cub + sum(
        1 for r, filas in resuelto if es_gate(r) for f in filas if f.estado == SIN_COBERTURA
    ), "el detalle de huecos no cuadra con el conteo del resumen"


# ===========================================================================
# 8 · Controles del resolutor
# ===========================================================================
#
# Sin esto, un resolutor roto vuelve VACÍAS todas las guardas de arriba y la suite se pone
# verde afirmando que 60 citas están sanas. Es la avería que `T-2.63` documentó: el escáner
# que siempre dice «no hay problema».

_MODULO = """
import pytest

pytestmark = pytest.mark.asyncio


def test_normal():
    assert True


@pytest.mark.skipif(True, reason="x")
def test_con_skipif():
    assert True


@pytest.mark.perf
def test_de_perf():
    assert True


def test_se_salta_desde_dentro():
    pytest.skip("no hay hardware")


class TestAgrupado:
    def test_dentro_de_clase(self):
        assert True
"""

_MODULO_APAGADO_ENTERO = """
import pytest

pytestmark = pytest.mark.skipif(True, reason="sin socket")


def test_de_hardware():
    assert True
"""


@pytest.mark.parametrize(
    "nombre,apagable",
    (
        ("test_normal", None),
        ("test_con_skipif", "skipif"),
        ("test_de_perf", "perf"),
        ("test_se_salta_desde_dentro", "skip"),
        ("test_dentro_de_clase", None),
    ),
)
def test_el_resolutor_python_ve_lo_que_apaga_un_test(nombre: str, apagable: str | None) -> None:
    assert _localiza_python(_MODULO, nombre).apagable == apagable


def test_el_resolutor_python_ve_el_pytestmark_del_modulo() -> None:
    assert _localiza_python(_MODULO_APAGADO_ENTERO, "test_de_hardware").apagable == "skipif"


def test_el_resolutor_python_no_encuentra_lo_que_no_existe() -> None:
    with pytest.raises(CitaRota):
        _localiza_python(_MODULO, "test_que_alguien_borro")


def test_el_resolutor_python_da_la_linea_del_def() -> None:
    assert _MODULO.splitlines()[_localiza_python(_MODULO, "test_normal").linea - 1].startswith(
        "def test_normal"
    )


_TSX = """
describe("grupo", () => {
  it("caso vivo", () => {});
  it.skip("caso apagado", () => {});
  it.each([
    ["a", { error: "falló (503)" }],
    ["b", { loading: true }],
  ])("caso parametrizado", (x, y) => {});
});

describe.skip("grupo apagado", () => {
  it("caso heredando el apagón", () => {});
});

test.describe("bloque de playwright", () => {
  test("caso de playwright", async () => {});
});
"""


@pytest.mark.parametrize(
    "titulo,apagable",
    (
        ("caso vivo", None),
        ("caso apagado", "skip"),
        ("caso parametrizado", None),
        ("caso heredando el apagón", "skip"),
        ("caso de playwright", None),
    ),
)
def test_el_resolutor_typescript_ve_lo_que_apaga_un_caso(titulo: str, apagable: str | None) -> None:
    assert _localiza_typescript(_TSX, titulo).apagable == apagable


def test_el_resolutor_typescript_no_confunde_un_describe_con_un_test() -> None:
    """`test.describe("X")` no es un test llamado `X`. Si lo fuera, una cita al bloque
    entero pasaría por cita a una prueba."""
    with pytest.raises(CitaRota):
        _localiza_typescript(_TSX, "bloque de playwright")


def test_el_resolutor_typescript_no_encuentra_lo_que_no_existe() -> None:
    with pytest.raises(CitaRota):
        _localiza_typescript(_TSX, "caso que alguien renombró")


def test_el_resolutor_typescript_da_la_linea_del_it() -> None:
    linea = _localiza_typescript(_TSX, "caso parametrizado").linea
    assert "caso parametrizado" in _TSX.splitlines()[linea - 1]


def test_el_resolutor_ve_apagado_un_test_de_hardware_de_verdad() -> None:
    """Control contra el árbol real, no contra una cadena de este archivo.

    Los cinco tests del registro de `T-2.63` llevan un `pytestmark = skipif` de socket. Si
    el resolutor dejara de verlo, `G-03` se publicaría como CUBIERTO — el falso verde exacto
    que aquella tarea existió para matar.
    """
    loc = localiza("edge/tests/test_seedlink_hardware.py", "test_real_shake_streams_100sps")
    assert loc.apagable == "skipif"


def test_el_resolutor_ve_vivo_un_test_normal_de_verdad() -> None:
    """Y la dirección contraria: un detector que dijera «apagado» a todo también miente."""
    loc = localiza("api/tests/test_rls_isolation.py", "test_app_cannot_read_other_tenant")
    assert loc.apagable is None


def test_una_cita_a_un_archivo_fuera_de_toda_suite_es_un_error() -> None:
    with pytest.raises(AssertionError, match="no cuelga de ninguna raíz"):
        _suite_de("scripts/algo_que_no_corre.py")


# ===========================================================================
# INVENTARIO DE LO QUE ESTE ARCHIVO **NO** CUBRE (medido el 2026-08-08)
# ===========================================================================
#
# Un punto ciego documentado es un activo; uno que se cree cerrado es el defecto. Nada de
# esto debería sorprender a quien lea un verde de esta suite.
#
# M1. **La semántica no se comprueba.** Que `test_app_cannot_read_other_tenant` demuestre
#     `RO-5.c` es un juicio humano escrito en `demuestra=`. Lo mecánico es que exista, que no
#     se salte y que un job bloqueante lo corra. Un test renombrado a algo que ya no hace lo
#     que dice pasa por aquí sin ruido.
#
# M2. **La descomposición en afirmaciones es editorial.** Las once reglas, las seis viñetas y
#     los diez gates se derivan; partirlos en `a`/`b`/`c` no. Un requisito partido en pocas
#     afirmaciones sale más verde que el mismo requisito partido fino. La lista se escribió
#     buscando los huecos a propósito, no para llenar de verdes — pero nada lo obliga.
#
# M3. **`CUBIERTO` no gradúa.** Una prueba superficial y quince exhaustivas dan el mismo
#     color. La matriz no mide profundidad, mide existencia.
#
# M4. **El detector de apagado no ve todas las formas.** Ve `pytestmark`, decoradores,
#     `pytest.skip`/`importorskip`/`xfail` en el cuerpo, `unittest.skipIf`, la marca `perf` y
#     `it.skip`/`describe.skip`/`it.todo`. NO ve: un `skip` decidido dentro de un fixture o de
#     un `conftest.py`, un `skipif` cuya condición se importa de otro módulo, un `it()` cuyo
#     título se construye por concatenación o interpolación, ni `it("x", { skip: true })`.
#     `edge/tests/test_hardware_gates.py` sí tiene el censo AST completo para el edge; aquí no
#     se replicó porque esta matriz sólo mira los ~60 tests que cita, no los 320 del árbol.
#
# M5. **«Lo corre el CI» se deriva del `on:` del workflow, no de la corrida.** Si un job
#     existe, dispara en `pull_request` y aun así el paso concreto está deshabilitado o
#     `continue-on-error`, esto no lo ve. Sólo `e2e.yml` está clasificado como no bloqueante
#     hoy, y por su disparador.
#
# M6. **Nada verifica que el test citado PASE.** Un test citado que estuviera fallando
#     dejaría la matriz idéntica: el rojo lo daría su propia suite, no ésta.
#
# M7. **`tipo="documental"` es una declaración, no una medición.** Nadie comprueba que un test
#     marcado como de comportamiento toque de verdad el código. Hoy no hay ninguna evidencia
#     documental en el registro justamente porque ninguna acreditaría nada.
#
# M8. **La matriz cubre reglas, invariantes y gates — no funcionalidad.** Que la consola liste
#     incidentes o que el PDF salga bien no tiene fila aquí. Eso vive en los criterios de
#     aceptación de `TASKS.md`, que se descartaron como fuente por las razones del docstring.


if __name__ == "__main__":  # pragma: no cover - utilidad de regeneración
    if "--escribir" in sys.argv:
        MATRIZ.write_text(render(), encoding="utf-8")
        print(f"escrito {MATRIZ}")
    else:
        sys.stdout.write(render())
