"""Contract-test docs↔código (T-2.61): la documentación no puede mentir sobre el repo.

Precedente y hogar: ``api/tests/auth/test_matrix.py`` ya es un contract-test docs↔código
(la matriz de `RBAC-TAKAB.md` contra `auth/matrix.py`). Este archivo extiende la idea a las
afirmaciones de estado: marcadores de decisión que se quedaron pegados después de ratificar,
tareas que se declaran cerradas por otra que sigue abierta, y una cabecera de backlog que
lleva meses contando mal.

**Por qué existe.** Las cinco mentiras que este archivo caza estaban vivas el 2026-08-05:
la cabecera de `TASKS.md` declaraba "9 de 9 tareas en verde" con 134 tareas en el archivo;
el marcador del gate #5 seguía marcado como "confirmar" **tres líneas por encima de su propia
ratificación** (las dos dentro de `T-1.22`); T-2.57 declaraba "Cierra T-1.47" mientras T-1.47
seguía en `[~]`; RBAC listaba como PENDIENTE un disparador que lleva implementado desde
T-1.27; y la app móvil seguía siendo "fase posterior" con la Fase 2 entera mergeada.

Los números de línea envejecen; los IDs de tarea no. Este archivo cita por ID a propósito.

Hereda el fixture de sesión ``_migrated`` (``conftest.py:57``) sin usarlo: no toca la DB,
solo el árbol de archivos. Coste cero.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

TASKS = REPO / "takab-docs" / "TASKS.md"
RBAC = REPO / "takab-docs" / "RBAC-TAKAB.md"
BLUEPRINT = REPO / "takab-docs" / "BLUEPRINT-TECNICO-TAKAB.md"
PLAN_MAESTRO = REPO / "takab-docs" / "PLAN-MAESTRO-TAKAB.md"
CLAUDE_MD = REPO / "CLAUDE.md"
AUTO_POPUP = REPO / "web" / "src" / "features" / "console" / "useAutoPopup.ts"
RUNBOOK_BACKUP = REPO / "takab-docs" / "runbooks" / "RUNBOOK-backup-restore-db.md"
TF_DB_VARS = REPO / "infra" / "terraform" / "modules" / "database" / "variables.tf"
TF_OBSERVABILITY = REPO / "infra" / "terraform" / "modules" / "observability" / "main.tf"

#: Los documentos que `CLAUDE.md §5` declara fuente de verdad del proyecto. Es donde una
#: afirmación falsa **gobierna**: quien lea aquí no va a ir a comprobarla al código.
DOCS_DE_GOBIERNO = (CLAUDE_MD, TASKS, BLUEPRINT, PLAN_MAESTRO, RBAC)

#: Directorios que no son fuente de verdad de nada (generados, dependencias, o
#: referencia visual congelada a propósito — ver `PLAN-MAESTRO §2 R11`).
SKIP_DIRS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".turbo",
        ".venv",
        "__pycache__",
        "android",
        "build",
        "coverage",
        "dist",
        "graphify-out",
        "htmlcov",
        "node_modules",
        "playwright-report",
        "test-results",
        "venv",
    }
)
SKIP_PATHS = frozenset({REPO / "takab-docs" / "design"})

TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".sql",
        ".tf",
        ".tfvars",
        ".yml",
        ".yaml",
        ".sh",
        ".toml",
        ".txt",
        ".html",
        ".css",
    }
)


def _es_otro_checkout(d: Path) -> bool:
    """¿`d` es un checkout de git DISTINTO del que estamos auditando?

    Un worktree anidado (`git worktree add`) o un submódulo llevan su propio `.git`
    —fichero en el worktree, directorio en el submódulo— y su contenido pertenece a
    OTRA rama. Escanearlo hace que este censo mida código que no es el de esta rama.

    Se deriva de la estructura en vez de enumerar rutas: `.claude/worktrees/` es solo
    el sitio donde el harness los pone hoy, y el siguiente aparecerá en otro lado.
    """
    return (d / ".git").exists()


def _repo_text_files(root: Path = REPO) -> list[Path]:
    """Todos los archivos de texto del repo menos generados, dependencias y este test."""
    me = Path(__file__).resolve()
    out: list[Path] = []
    stack = [root]
    while stack:
        d = stack.pop()
        for entry in d.iterdir():
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in SKIP_DIRS or entry in SKIP_PATHS:
                    continue
                if _es_otro_checkout(entry):
                    continue
                stack.append(entry)
            elif entry.suffix in TEXT_SUFFIXES and entry.resolve() != me:
                out.append(entry)
    return out


def _hits(marker: str) -> list[str]:
    """`archivo:línea` de cada ocurrencia del marcador en el repo."""
    found: list[str] = []
    for path in _repo_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if marker not in text:
            continue
        for n, line in enumerate(text.splitlines(), start=1):
            if marker in line:
                found.append(f"{path.relative_to(REPO)}:{n}")
    return sorted(found)


# ---------------------------------------------------------------------------
# 1 · Marcadores de decisión que ya se ratificaron y siguen pegados
# ---------------------------------------------------------------------------

#: Cada entrada: (marcador, por qué está muerto).
DEAD_MARKERS = (
    (
        "SUPUESTO plan-maestro-01 #5",
        "el gate #5 se ratificó el 2026-07-06 (`TASKS.md` T-1.22): REST + WS nativo, SIN "
        "GraphQL. Un supuesto ratificado no se sigue etiquetando 'confirmar/override'.",
    ),
    (
        "SUPUESTO #5",
        "mismo gate #5, otra grafía. Estuvo etiquetado 'confirmar' TRES LÍNEAS por encima "
        "de su propia ratificación en `TASKS.md`.",
    ),
    (
        "[SUPUESTO — confirmar/override: si faltaba un 11º rol",
        "el conteo 10-vs-11 roles se ratificó el 2026-07-09 en T-1.45 "
        "(`PLAN-MAESTRO-TAKAB.md:59-65`): 10 roles; las identidades máquina no son roles RBAC.",
    ),
)


@pytest.mark.parametrize("marker,razon", DEAD_MARKERS, ids=lambda v: v[:28])
def test_no_quedan_marcadores_de_decision_ya_ratificada(marker: str, razon: str) -> None:
    hits = _hits(marker)
    assert not hits, (
        f"Marcador muerto todavía vivo en el repo: {marker!r}\n"
        f"  Por qué está muerto: {razon}\n"
        f"  Ocurrencias ({len(hits)}):\n    " + "\n    ".join(hits)
    )


# ---------------------------------------------------------------------------
# 1-bis · Generalización: NINGÚN gate ratificado sigue etiquetado como supuesto
# ---------------------------------------------------------------------------
#
# `DEAD_MARKERS` es una lista de **grafías concretas**, y por construcción solo ve las que
# alguien se acordó de escribir en ella. Enumeraba las dos del gate #5 y la del 11º rol, así
# que era **ciega a los gates #4 y #6** — ratificados el 2026-07-09 en `T-1.45` y todavía
# etiquetados "confirmar/override" en cinco sitios el 2026-08-05, uno de ellos `CLAUDE.md`,
# que se carga en CADA sesión. El gate #6 es el del proceso `gpio`: el que toca la sirena.
#
# Lo de abajo no enumera grafías: **deriva el censo de gates ratificados del propio
# `PLAN-MAESTRO §3`** y cruza contra cualquier `[SUPUESTO … #N …]` del repo. Añadir un gate
# nuevo, o ratificar uno abierto, no exige tocar este archivo. `DEAD_MARKERS` se conserva
# porque es más estricto donde sí llega (repo entero, marcador exacto): las dos capas
# cuestan lo mismo y fallan por motivos distintos.

_SECCION_GATES = "## 3. Decisiones incorporadas y decision-gates"

#: Fila de la tabla de decision-gates: `| #N <decisión> | <estado adoptado> | <gate> |`.
GATE_FILA_RE = re.compile(r"^\|\s*#(?P<n>\d+)\s(?P<fila>.*)$", re.M)

#: Qué cuenta como "ratificado" en esa tabla. Las cuatro grafías que usa hoy:
#: `[RATIFICADO …]` (#4/#5/#6/#7), "parámetros RATIFICADOS" (#2), "Gate cumplido" y
#: "Gate cerrado". Deliberadamente NO cuenta "Gate de Fase 3" (#9) ni "Soft-gate: …" (#1),
#: ni "Hard-gate SOLO para aceptación" (#3), ni "Soft-gate T-1.21" (#8) — esos cuatro
#: siguen abiertos con razón y no deben salir en rojo.
_RATIFICADO_RE = re.compile(
    r"\[RATIFICADO|\bRATIFICAD[AO]S?\b|Gate (?:cumplido|cerrado)|Soft-gate CERRADO"
)

#: Marcador de supuesto que nombra su gate. `[^\]]` come saltos de línea a propósito:
#: `BLUEPRINT:157` y `:483` parten el marcador en dos renglones de blockquote.
SUPUESTO_RE = re.compile(r"\[SUPUESTO[^\]]*?#(?P<n>\d+)[^\]]*\]")

#: Salvoconducto: una línea que **ya dice** que aquello se ratificó o se resolvió está
#: citando su propia historia, no declarando algo pendiente. `RBAC-TAKAB.md:223` es el caso
#: real: `**[RESUELTO 2026-07-15 · T-2.00]** (era `[SUPUESTO #7 plan-maestro]`)`.
_YA_RESUELTO_RE = re.compile(r"RATIFICAD|RESUELTO|ratificad")

#: Framing de "esto sigue pendiente". Es lo que convierte un marcador en una mentira cuando
#: el gate ya se cerró, y por eso se persigue en TODO el repo, no solo en los documentos.
_PENDIENTE_RE = re.compile(r"confirmar|override|pendiente", re.I)


def _gates_ratificados() -> dict[int, str]:
    """{nº de gate: fila} de los gates que `PLAN-MAESTRO §3` da por cerrados."""
    text = PLAN_MAESTRO.read_text(encoding="utf-8")
    i = text.find(_SECCION_GATES)
    assert i != -1, (
        f"`PLAN-MAESTRO-TAKAB.md` ya no tiene la sección {_SECCION_GATES!r}. Es de donde "
        "sale el censo de gates ratificados; sin ella este test no puede decidir nada."
    )
    j = text.find("\n## ", i + 1)
    seccion = text[i:] if j == -1 else text[i:j]
    return {
        int(m.group("n")): m.group("fila").strip()
        for m in GATE_FILA_RE.finditer(seccion)
        if _RATIFICADO_RE.search(m.group("fila"))
    }


def _supuestos(text: str) -> list[tuple[int, int, str, str]]:
    """[(gate, línea, marcador, línea completa)] de cada `[SUPUESTO … #N …]` del texto."""
    out: list[tuple[int, int, str, str]] = []
    for m in SUPUESTO_RE.finditer(text):
        ini = text.rfind("\n", 0, m.start()) + 1
        fin = text.find("\n", m.start())
        out.append(
            (
                int(m.group("n")),
                text.count("\n", 0, m.start()) + 1,
                " ".join(m.group(0).split()),
                text[ini : len(text) if fin == -1 else fin],
            )
        )
    return out


def test_el_censo_de_gates_ratificados_es_el_que_declara_el_plan() -> None:
    """Control del parser: si se rompe, los dos tests de abajo se vuelven vacíos en silencio.

    Estado verificado contra `PLAN-MAESTRO §3` el 2026-08-05. Si esta lista cambia es porque
    una decisión se ratificó (o se reabrió) — actualízala **con esa decisión**, no para que
    el test pase.
    """
    ratificados = set(_gates_ratificados())
    abiertos = {1, 3, 8, 9}
    assert ratificados == {2, 4, 5, 6, 7}, (
        f"El censo de gates ratificados salió {sorted(ratificados)}; se esperaba [2, 4, 5, 6, 7].\n"
        f"  Los gates {sorted(abiertos)} siguen abiertos con razón (marco normativo, hardware "
        "real,\n  feed CIRES/SSN y la política de IA de Fase 3) y NO deben contarse como "
        "cerrados."
    )
    assert not (ratificados & abiertos), (
        f"Gates dados por ratificados y por abiertos a la vez: {sorted(ratificados & abiertos)}"
    )


def test_ningun_gate_ratificado_sigue_etiquetado_como_supuesto_en_los_documentos() -> None:
    """En los documentos canónicos, `[SUPUESTO #N]` significa "pendiente de ratificar".

    Lo dice la convención en `PLAN-MAESTRO:11` y lo repite `CLAUDE.md §5` ("supuestos
    `[SUPUESTO plan-maestro-01]` **pendientes de ratificar**"). Con el gate ya cerrado, el
    marcador manda a quien lo lea a reabrir un diseño que está congelado desde T-1.8.
    """
    ratificados = _gates_ratificados()
    fallos: list[str] = []
    for path in DOCS_DE_GOBIERNO:
        text = path.read_text(encoding="utf-8")
        for gate, linea, marcador, texto_linea in _supuestos(text):
            if gate not in ratificados or _YA_RESUELTO_RE.search(texto_linea):
                continue
            fallos.append(
                f"{path.relative_to(REPO)}:{linea}: «{marcador}» — el gate #{gate} está "
                f"ratificado: {ratificados[gate][:96]}…"
            )
    assert not fallos, (
        "Gates ya ratificados que los documentos canónicos siguen presentando como supuestos:\n"
        "  " + "\n  ".join(fallos) + "\n"
        "  Propágalo como se hizo con el #5: sustituye el marcador por "
        "`[RATIFICADO <fecha> · <tarea> · gate #N]`\n"
        "  citando la decisión que ya existe en `PLAN-MAESTRO §3`."
    )


def test_ningun_marcador_de_gate_ratificado_pide_confirmacion_en_el_repo() -> None:
    """Repo entero: un gate cerrado no se etiqueta "confirmar/override" en ningún archivo."""
    ratificados = _gates_ratificados()
    fallos: list[str] = []
    for path in _repo_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "[SUPUESTO" not in text:
            continue
        for gate, linea, marcador, texto_linea in _supuestos(text):
            if gate not in ratificados or _YA_RESUELTO_RE.search(texto_linea):
                continue
            if _PENDIENTE_RE.search(marcador):
                fallos.append(f"{path.relative_to(REPO)}:{linea}: «{marcador}» (gate #{gate})")
    assert not fallos, (
        "Marcadores que piden confirmar un gate que ya se ratificó:\n  "
        + "\n  ".join(fallos)
        + "\n  Un supuesto ratificado no se sigue etiquetando 'confirmar/override': quien lo "
        "lea\n  cree que puede overridearlo, y el #6 es el del proceso que toca la sirena."
    )


def test_ningun_gate_ratificado_sigue_marcado_como_supuesto_en_el_codigo() -> None:
    """El código tampoco: un `[SUPUESTO #N]` pelado miente igual que uno que pide confirmación.

    Los dos tests de arriba dejaban un hueco justo entre ellos: el primero solo mira los
    cinco documentos de gobierno, y el segundo recorre el repo pero solo se queja si el
    marcador dice literalmente "confirmar/override". Un `[SUPUESTO plan-maestro-01 #4]`
    pelado en `edge/` pasaba por los dos.

    No era teórico. El 2026-08-05 sobrevivían cuatro, y uno estaba en
    `edge/takab_edge/gpio/__init__.py`: el proceso que toca la sirena, marcado como diseño
    abierto seis días después de que T-1.45 lo congelara. La convención la fija
    `PLAN-MAESTRO:11` y la repite `CLAUDE.md §5` — `[SUPUESTO]` significa *pendiente de
    ratificar*, así que en un módulo del camino crítico invita a rediseñarlo.

    Esta capa es la ancha (cualquier marcador, todo el repo) y las de arriba son las
    específicas. Se conservan las tres a propósito: fallan por motivos distintos y con
    mensajes distintos, y la que enumera es más precisa donde llega.
    """
    ratificados = _gates_ratificados()
    fallos: list[str] = []
    for path in _repo_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "[SUPUESTO" not in text:
            continue
        for gate, linea, marcador, texto_linea in _supuestos(text):
            if gate not in ratificados or _YA_RESUELTO_RE.search(texto_linea):
                continue
            fallos.append(f"{path.relative_to(REPO)}:{linea}: «{marcador}» (gate #{gate})")
    assert not fallos, (
        "Gates ya ratificados que el repo sigue marcando como supuestos:\n  "
        + "\n  ".join(fallos)
        + "\n  Sustitúyelo por `[RATIFICADO <fecha> · <tarea> · gate #N]` citando la decisión\n"
        "  que ya existe en `PLAN-MAESTRO §3`. Un marcador pelado no es más inocente que uno\n"
        "  que pide confirmación: dice lo mismo, solo que sin decirlo."
    )


# ---------------------------------------------------------------------------
# 2 · La app móvil dejó de ser "fase posterior" cuando la Fase 2 se mergeó
# ---------------------------------------------------------------------------


def test_rbac_no_llama_fase_posterior_a_ninguna_superficie() -> None:
    """`mobile/` está COMPLETA y mergeada (T-2.00…T-2.14, `TASKS.md` T-1.31)."""
    text = RBAC.read_text(encoding="utf-8")
    hits = [
        f"RBAC-TAKAB.md:{n}: {line.strip()}"
        for n, line in enumerate(text.splitlines(), start=1)
        if "fase posterior" in line
    ]
    assert not hits, (
        "`RBAC-TAKAB.md` sigue etiquetando superficies como 'fase posterior'.\n"
        "  La app móvil está COMPLETA y mergeada desde la Fase 2 (T-2.00…T-2.14); el propio\n"
        "  `TASKS.md` T-1.31 dice 'CUBIERTA POR LA FASE 2 COMPLETA'. Un rol cuya superficie\n"
        "  se anuncia como futura se lee como un rol sin producto.\n"
        "  Ocurrencias:\n    " + "\n    ".join(hits)
    )


# ---------------------------------------------------------------------------
# 3 · Cruce real docs↔código: el pop-up de waveform
# ---------------------------------------------------------------------------

_S8_START = "## 8. PENDIENTES"
_S8_RESUELTOS = "### Salidos de PENDIENTES"
_POPUP = "pop-up automático de waveform"
_POPUP_CONST = "STALTA_THRESHOLD = 3.5"


def _seccion_8() -> tuple[str, str]:
    """(abiertos, resueltos) de `RBAC-TAKAB.md §8`."""
    text = RBAC.read_text(encoding="utf-8")
    i = text.find(_S8_START)
    assert i != -1, f"`RBAC-TAKAB.md` ya no tiene la sección {_S8_START!r}"
    j = text.find("\n## ", i + 1)
    seccion = text[i:] if j == -1 else text[i:j]
    k = seccion.find(_S8_RESUELTOS)
    return (seccion, "") if k == -1 else (seccion[:k], seccion[k:])


def test_el_popup_de_waveform_no_puede_estar_pendiente_y_escrito_a_la_vez() -> None:
    """Uno de los dos miente: o RBAC §8 lo lista pendiente, o el archivo existe."""
    implementado = AUTO_POPUP.exists() and _POPUP_CONST in AUTO_POPUP.read_text(encoding="utf-8")
    abiertos, resueltos = _seccion_8()
    ruta = "web/src/features/console/useAutoPopup.ts"

    if implementado:
        assert _POPUP not in abiertos, (
            f"`RBAC-TAKAB.md §8` lista el {_POPUP} como PENDIENTE, pero `{ruta}` existe con\n"
            f"  `{_POPUP_CONST}` — implementado en T-1.27. La documentación miente: sácalo de\n"
            "  la lista de abiertos y cita el archivo bajo "
            f"{_S8_RESUELTOS!r}."
        )
        assert ruta in resueltos, (
            f"`RBAC-TAKAB.md §8` no cita `{ruta}` en {_S8_RESUELTOS!r}.\n"
            "  Sacar algo de pendientes sin decir DÓNDE quedó implementado deja el hueco\n"
            "  igual de invisible que antes."
        )
    else:
        assert ruta not in resueltos, (
            f"`RBAC-TAKAB.md §8` declara implementado el {_POPUP} citando `{ruta}`,\n"
            f"  pero ese archivo no existe o ya no define `{_POPUP_CONST}`.\n"
            "  Miente la documentación en el otro sentido: el código se fue y el doc no."
        )


# ---------------------------------------------------------------------------
# 4 · La cabecera de TASKS.md cuadra con el conteo real
# ---------------------------------------------------------------------------

#: Encabezado de tarea. Es la ÚNICA definición de "una tarea" en este archivo.
TASK_HEADER_RE = re.compile(r"^### \[(?P<estado>.)\] (?P<id>T-[0-9]+\.[0-9A-Za-z.]+)", re.M)

#: Declaración de la cabecera. Ver la nota "Conteo de tareas" al inicio de `TASKS.md`.
DECL_RE = re.compile(
    r"\*\*Conteo de tareas[^*]*:\*\*\s*total \*\*(?P<total>\d+)\*\*"
    r".*?`\[x\]` \*\*(?P<hechas>\d+)\*\*"
    r".*?`\[~\]` \*\*(?P<parciales>\d+)\*\*"
    r".*?`\[ \]` \*\*(?P<abiertas>\d+)\*\*",
    re.S,
)


def _tareas() -> list[tuple[str, str]]:
    """[(estado, id)] en orden de aparición."""
    text = TASKS.read_text(encoding="utf-8")
    return [(m.group("estado"), m.group("id")) for m in TASK_HEADER_RE.finditer(text)]


def test_la_cabecera_de_tasks_declara_el_conteo_real() -> None:
    """El assert que mata la mentira de raíz.

    La cabecera decía "9 de 9 tareas en verde" con 134 tareas en el archivo — 36 tareas de
    retraso. Este test impone la obligación permanente: **toda tarea que se cierre o se abra
    actualiza la cabecera en el mismo commit.** Está documentado en el propio `TASKS.md`
    para que el siguiente no lo viva como fricción arbitraria.
    """
    text = TASKS.read_text(encoding="utf-8")
    m = DECL_RE.search(text)
    assert m, (
        "`TASKS.md` no declara su conteo en la cabecera.\n"
        "  Formato esperado (una sola línea):\n"
        "    **Conteo de tareas:** total **N** · `[x]` **N** · `[~]` **N** · `[ ]` **N**"
    )
    dicho = {k: int(v) for k, v in m.groupdict().items()}

    tareas = _tareas()
    real = {
        "total": len(tareas),
        "hechas": sum(1 for e, _ in tareas if e == "x"),
        "parciales": sum(1 for e, _ in tareas if e == "~"),
        "abiertas": sum(1 for e, _ in tareas if e == " "),
    }
    assert dicho == real, (
        "La cabecera de `TASKS.md` no cuadra con los encabezados `^### [.]` del archivo.\n"
        f"  declarado: {dicho}\n"
        f"  real:      {real}\n"
        "  Actualiza la cabecera en el MISMO commit que cambia el estado de una tarea."
    )
    assert real["total"] == real["hechas"] + real["parciales"] + real["abiertas"], (
        f"Hay encabezados con un estado que no es `x`, `~` ni ` `: {real}.\n"
        "  Estados permitidos: `[x]` hecha · `[~]` parcial · `[ ]` abierta."
    )


# ---------------------------------------------------------------------------
# 5 · Coherencia de cierres cruzados
# ---------------------------------------------------------------------------

#: Un `"` (o `«`, `“`) pegado delante —con o sin las negritas en medio— marca una **cita**,
#: no una declaración: `TASKS.md` narra citando literalmente declaraciones ajenas
#: (`T-1.47` cita el `**Cierra T-1.47**` de T-2.57, y `T-2.61` lo vuelve a citar). Son tres
#: lookbehinds porque Python solo admite lookbehind de **ancho fijo**: uno por cada largo
#: posible del prefijo (`"`, `"*`, `"**`).
_NO_ES_CITA = r'(?<!["«“])(?<!["«“]\*)(?<!["«“]\*\*)'

#: Declaración de cierre — un **hecho consumado** sobre otra tarea, en las dos direcciones:
#: activa ("yo cierro a T-B") y pasiva ("esto quedó cerrado por T-B"). Las dos imponen lo
#: mismo: si el bloque que lo declara está `[x]`, la tarea nombrada tiene que estar `[x]`.
#:
#:   RECONOCE                              NO RECONOCE (a propósito)
#:   **Cierra T-1.47.**                    se cierra en T-2.64 (en curso)  ← futuro, no hecho
#:   Cierra T-2.60.  (sin negritas)        "**Cierra T-1.47**"             ← cita
#:   CERRADO por T-2.64                    "**Cierra `T-1.47`**"           ← cita con backticks
#:   cerrada por T-2.57                    **Depende de:** T-2.59          ← dependencia
#:   Cierra `T-1.44`.   (backticks)        cierra la fase 2.3              ← sin ID de tarea
#:   CERRADO por `T-2.64`                  cierra Fase E · cierra el gate  ← ídem
#:   quedó cerrado en T-1.40               Cierra la mitad de US-20        ← ídem
#:   CERRADA en T-1.38                     Cierra los cuatro `[ ]`         ← ídem
#:   cerrado **en** T-1.44
#:
#: **La trampa que esto viene a matar:** hasta el 2026-08-05 el patrón era
#: `\*\*Cierra (T-…)\.\*\*` — solo la activa **y con negritas**. Con él, T-2.59 (`[x]`)
#: declaraba "**CERRADO por T-2.64**" con T-2.64 en `[ ]` y la suite daba **7 passed**.
#: Un regex que solo ve una de las grafías es un test que da permiso, no cobertura.
#:
#: **Segunda ronda (2026-08-05, misma sesión).** Tres sondas más pasaban en VERDE siendo
#: mentira, y las tres son el estilo dominante del propio archivo:
#:   1. el **ID entre backticks** — `TASKS.md:4364` ya escribe "Lo cierra `T-2.74`";
#:   2. la pasiva con backticks — "CERRADO por `T-2.64`";
#:   3. la **preposición `en`** — `TASKS.md:1107` escribe "quedó cerrado en T-1.40" y
#:      `:868` "LIMITACIÓN CERRADA en T-1.38".
#: `en` obliga a distinguir el pretérito del futuro: "cerrado **en** T-X" es un hecho
#: consumado y cuenta; "se cierra **en** T-X (en curso)" es una promesa y no cuenta. Por eso
#: `en`/`por` cuelgan solo del participio (`cerrad[ao]s?`) y nunca de `cierra`, que exige el
#: ID pegado detrás.
#:
#: El ID **no puede terminar en punto**: `**Cierra T-1.44.**` lleva el punto de la frase
#: pegado, y una clase `[0-9A-Za-z.]+` golosa se lo traga y produce `T-1.44.`, que no existe
#: como encabezado. El patrón viejo se libraba por accidente (exigía `\.\*\*` detrás); este
#: no puede, así que lo dice explícito. Sigue aceptando subtareas: `T-2.60.a`.
_ID_TAREA = r"T-[0-9]+\.[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*"

#: Activa (`cierra T-X`) y pasiva (`cerrado por/en T-X`), con o sin negritas de por medio.
_VERBO_DE_CIERRE = r"cierra|cerrad[ao]s?\s+(?:\*\*)?(?:por|en)(?:\*\*)?"

CIERRA_RE = re.compile(
    _NO_ES_CITA + r"(?:\*\*)?\b(?i:" + _VERBO_DE_CIERRE + r")\s+`?(?P<id>" + _ID_TAREA + ")`?"
)

#: (línea real o realista, IDs que el regex DEBE extraer). Las seis primeras salen tal cual
#: de `TASKS.md`; las cinco últimas son las que **no** deben contar. Esta tabla es lo único
#: que impide que el patrón se vuelva a quedar ciego sin que nadie lo note: el escaneo de
#: `TASKS.md` se pone verde en cuanto la mentira se corrige, la tabla no.
FORMAS_DE_CIERRE = (
    ("- **Componente:** infra · **Depende de:** — · **Cierra T-1.44.**", ["T-1.44"]),
    ("        **Cierra T-1.47.**", ["T-1.47"]),
    ("Esta tarea cierra T-2.60 y nada más.", ["T-2.60"]),
    ("- **Anotado — CERRADO por T-2.64 (2026-08-05):** numeración duplicada", ["T-2.64"]),
    ("### [x] T-1.47 · Datos reales (purga verificada, cerrada por T-2.57)", ["T-2.57"]),
    ("El soft-gate #2 queda CERRADO por T-1.46.", ["T-1.46"]),
    # --- los tres puntos ciegos medidos el 2026-08-05 (verdes siendo mentira) ---
    ("- **Componente:** infra · **Depende de:** — · **Cierra `T-1.44`.**", ["T-1.44"]),
    ("- **Anotado — CERRADO por `T-2.64` (2026-08-05):** numeración duplicada", ["T-2.64"]),
    ("- [x] El patrón #28 quedó cerrado **en** T-1.44 (`_safe()`) — verificado ahí.", ["T-1.44"]),
    ("> **`G-09` no está en esta fase.** Lo cierra `T-2.74` (Fase 2.6).", ["T-2.74"]),
    ("> **[LIMITACIÓN CERRADA en T-1.38: resolución por gabinete]**", ["T-1.38"]),
    # --- y las que NO deben contar ---
    ("- **Anotado — se cierra en T-2.64 (en curso, 2026-08-05):** numeración", []),
    ('T-2.57 declaraba *"Cierra T-1.47"* con evidencia medida', []),
    ('que declara textualmente "**Cierra T-1.47**":', []),
    ('esto decía **"CERRADO por T-2.64"** — presente-abierto a propósito', []),
    ('la cita "**Cierra `T-1.47`**" tampoco cuenta con backticks', []),
    ("- **Componente:** web + edge (panel) · **Depende de:** T-2.59", []),
    ("Esto cierra la fase 2.3 entera.", []),
    # Las nueve formas en prosa del `TASKS.md` real que deben seguir ciegas: cierran algo
    # que no es una tarea (una fase, una historia de usuario, un gate, unas casillas). El
    # reauditor midió CERO falsos positivos con ellas; romperlas es la regresión más cara
    # de este patrón, porque un falso rojo se "arregla" acotando el regex.
    ("### [x] T-1.14 · Simulador de sismo — **[A10]** · COMPLETA · cierra Fase E", []),
    ("- **Componente:** api · Cierra la mitad de escritura de **US-20**.", []),
    ("> **T-2.23 cierra la fase (decisión de Mauricio, 2026-07-29).**", []),
    ("Cierra los cuatro `[ ]` que T-2.58 dejó documentados y **no** cerró.", []),
    ("**lag mediano ~0.4 s** — cierra el gate #3 de latencia y confirma que el", []),
)


@pytest.mark.parametrize("linea,esperado", FORMAS_DE_CIERRE, ids=lambda v: str(v)[:34])
def test_cierra_re_ve_la_pasiva_y_la_no_negrita_y_no_ve_las_citas(
    linea: str, esperado: list[str]
) -> None:
    """El patrón reconoce las cuatro grafías de cierre y ninguna de las cuatro trampas."""
    visto = [m.group("id") for m in CIERRA_RE.finditer(linea)]
    assert visto == esperado, (
        f"`CIERRA_RE` no lee esta línea como toca:\n    {linea}\n"
        f"  esperado: {esperado}\n  visto:    {visto}\n"
        "  Ver la tabla RECONOCE/NO RECONOCE sobre el patrón. Ampliarlo es fácil; el riesgo\n"
        "  es el contrario: acotarlo hasta volver a dejar una grafía invisible."
    )


def _bloques() -> dict[str, tuple[str, str]]:
    """{id: (estado, cuerpo)} de cada tarea de `TASKS.md`."""
    text = TASKS.read_text(encoding="utf-8")
    marcas = list(TASK_HEADER_RE.finditer(text))
    out: dict[str, tuple[str, str]] = {}
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(text)
        out[m.group("id")] = (m.group("estado"), text[m.start() : fin])
    return out


#: Casilla de criterio dentro de una ficha: `  - [x] ...` / `  - [ ] ...`.
CRITERIO_RE = re.compile(r"^  - \[(?P<estado>[x ~])\] ", re.M)


def test_una_tarea_cerrada_no_deja_TODOS_sus_criterios_sin_marcar() -> None:
    """Una ficha `[x]` con **cero** de sus N criterios marcados es contabilidad sin hacer.

    Lo destapó la matriz de trazabilidad (T-2.84) contando el archivo entero: de 442
    criterios bajo tareas `[x]`, 34 seguían sin marcar, y **cinco tareas cerradas
    tenían sus criterios ENTEROS en `[ ]`** — T-2.61, T-2.62, T-2.63, T-2.64 y T-2.69.
    Las cinco estaban de verdad hechas; lo que faltaba era el registro. Y un registro
    que no se lleva es el que produjo la cabecera que decía «9 de 9 tareas en verde»
    con 134 tareas dentro.

    **La variante ingenua —«toda tarea `[x]` tiene TODOS sus criterios `[x]`»— sería
    un test nacido en rojo sin razón**, y está descartada a propósito: T-2.57 está
    `[x]` con cuatro `[ ]` **deliberados**, bajo un epígrafe que declara que son
    pendientes de AWS. Esa mezcla es una declaración, no un olvido.

    Lo que no puede ser una declaración es el **cero**: si nadie marcó ni uno, nadie
    revisó. Por eso el umbral es «al menos uno», que distingue el olvido del matiz.
    """
    fallos: list[str] = []
    for tid, (estado, cuerpo) in _bloques().items():
        if estado != "x":
            continue
        marcas = [m.group("estado") for m in CRITERIO_RE.finditer(cuerpo)]
        if marcas and not any(m in "x~" for m in marcas):
            fallos.append(f"{tid}: {len(marcas)} criterios, NINGUNO marcado")
    assert not fallos, (
        "Tareas cerradas cuya contabilidad no se llevó:\n  "
        + "\n  ".join(fallos)
        + "\n  Marcar la ficha y no sus criterios deja el archivo afirmando dos cosas a la\n"
        "  vez. Si algún criterio sigue realmente pendiente, márcalo como tal y dilo —\n"
        "  eso es una declaración; cero de N es un descuido."
    )


def test_una_tarea_hecha_no_puede_cerrar_una_tarea_abierta() -> None:
    """Una tarea `[x]` no declara cerrado —ni cerrada por— nada que siga abierto.

    Falló de verdad **dos veces**:
      1. T-2.57 declaraba "Cierra T-1.47" con evidencia medida (`site-sim activos = 0`,
         2026-08-04) mientras T-1.47 seguía en `[~]` diciendo que los 20 `site-sim-*`
         "SIGUEN en la DB viva" — forma **activa**, la que el patrón original sí veía;
      2. T-2.59 (`[x]`) declaraba "**CERRADO por T-2.64 (2026-08-05)**" con T-2.64 en
         `[ ] · EN CURSO` — forma **pasiva**, invisible para aquel patrón.

    Las dos direcciones imponen la misma condición y por eso comparten assert: da igual
    quién cierra a quién, un hecho consumado no puede colgar de una tarea abierta.
    """
    bloques = _bloques()
    fallos: list[str] = []
    for tid, (estado, cuerpo) in bloques.items():
        if estado != "x":
            continue
        for m in CIERRA_RE.finditer(cuerpo):
            objetivo = m.group("id")
            declaracion = m.group(0).strip()
            if objetivo not in bloques:
                fallos.append(f"{tid} declara «{declaracion}», y {objetivo} no existe en TASKS.md")
            elif bloques[objetivo][0] != "x":
                fallos.append(
                    f"{tid} está `[x]` y declara «{declaracion}», "
                    f"pero {objetivo} sigue en `[{bloques[objetivo][0]}]`"
                )
    assert not fallos, (
        "Cierres cruzados incoherentes:\n  "
        + "\n  ".join(fallos)
        + "\n  Si la otra tarea sigue abierta, la redacción honesta es futura "
        "('se cierra en T-X, en curso'), no pretérita."
    )


# ---------------------------------------------------------------------------
# 6 · La ruta al cierre no se contradice consigo misma
# ---------------------------------------------------------------------------
#
# La ironía que da origen a esta sección: la tarea escrita para que el repo dejara de mentir
# sobre sí mismo (T-2.61) introdujo **dos afirmaciones nuevas incompatibles**, ambas en
# negrita y a 465 líneas de distancia:
#
#   «Ninguna tarea de los Bloques I, II o IV depende de que un gate cierre para empezar.»
#   «No empieza antes de que el Bloque II esté cerrado y `G-04` acreditado.» (preámbulo del
#    Bloque IV, y con razón de seguridad explícita)
#
# Quien planifique el Bloque IV concluye lo contrario según cuál lea primero. Estos tests
# leen la ruta como un grafo, no como prosa.

RUTA_INICIO = "# RUTA AL CIERRE DEL PROYECTO"
RUTA_FIN = "\n## RUTA CRÍTICA"

BLOQUE_RE = re.compile(r"^## BLOQUE (?P<num>[IVX]+)\b.*$", re.M)
GATE_RE = re.compile(r"\bG-\d{2}\b")
DEPENDE_RE = re.compile(r"\*\*Depende de:\*\*(?P<lista>[^·\n]*)")
TASK_ID_RE = re.compile(_ID_TAREA)
REGLA_ANCLA = "**Regla de ordenación"

#: El Bloque III **es** el carril de gates: que su preámbulo nombre gates es su definición,
#: no una precondición. Excluirlo evita convertir la premisa de la regla en su violación.
BLOQUE_DE_GATES = "III"


def _ruta() -> str:
    text = TASKS.read_text(encoding="utf-8")
    i = text.find(RUTA_INICIO)
    assert i != -1, f"`TASKS.md` ya no contiene la sección {RUTA_INICIO!r}"
    j = text.find(RUTA_FIN, i)
    return text[i:] if j == -1 else text[i:j]


def _preambulos_de_bloque() -> dict[str, str]:
    """{numeral: preámbulo} — el texto entre `## BLOQUE n` y su primera `## Fase`.

    Es donde vive la precondición de un bloque entero, que es exactamente la clase de
    afirmación que ninguna tarea individual declara y que por eso nadie cruzaba con la regla.
    """
    ruta = _ruta()
    out: dict[str, str] = {}
    for m in BLOQUE_RE.finditer(ruta):
        resto = ruta[m.end() :]
        k = resto.find("\n## ")
        out[m.group("num")] = resto if k == -1 else resto[:k]
    return out


def _plano(texto: str) -> str:
    """Un solo renglón. `TASKS.md` envuelve a 100 columnas y las frases se parten.

    Medido: la regla dice "Ninguna tarea de\\nlos Bloques I, II o IV", y buscar la frase sin
    normalizar daba un **falso verde por ausencia** — el test no encontraba la regla y se
    quejaba del formato en vez de la contradicción.
    """
    return re.sub(r"\s+", " ", texto)


def _parrafo_de_la_regla() -> str:
    """La regla de ordenación completa (en un renglón), hasta el `---` que la cierra."""
    ruta = _ruta()
    i = ruta.find(REGLA_ANCLA)
    assert i != -1, (
        f"`TASKS.md` ya no declara la {REGLA_ANCLA!r}. Si se borró a propósito, este test "
        "sobra; si se movió, muévelo con su ancla."
    )
    j = ruta.find("\n---", i)
    return _plano(ruta[i:] if j == -1 else ruta[i:j])


def test_la_regla_de_ordenacion_no_exime_a_un_bloque_que_espera_un_gate() -> None:
    regla = _parrafo_de_la_regla()
    m = re.search(r"Ninguna tarea de los Bloques (?P<lista>[^.]*?) depende", regla)
    assert m, (
        "La regla de ordenación ya no dice a qué bloques exime.\n"
        "  Formato esperado: 'Ninguna tarea de los Bloques I o II depende de que un gate "
        "cierre para empezar.'"
    )
    eximidos = set(re.findall(r"\b(?:IV|III|II|I|V)\b", m.group("lista")))

    con_gate = {
        num: sorted(set(GATE_RE.findall(pre)))
        for num, pre in _preambulos_de_bloque().items()
        if num != BLOQUE_DE_GATES and GATE_RE.search(pre)
    }

    choque = sorted(eximidos & set(con_gate))
    assert not choque, (
        "La regla de ordenación se contradice con el preámbulo de un bloque que sí espera "
        "un gate:\n"
        + "\n".join(f"  Bloque {n}: su preámbulo nombra {con_gate[n]}" for n in choque)
        + "\n  La regla los declara EXIMIDOS de esperar a un gate. Las dos están en negrita\n"
        "  y la del bloque tiene razón de seguridad: gana la del bloque. Acota la lista de\n"
        "  la regla y escribe la excepción con su razón."
    )

    for num, gates in sorted(con_gate.items()):
        assert f"Bloque {num}" in regla, (
            f"El Bloque {num} espera a {gates} y la regla de ordenación no lo menciona.\n"
            "  Una excepción que solo vive 400 líneas más abajo es la que produjo esta "
            "contradicción."
        )
        faltan = [g for g in gates if g not in regla]
        assert not faltan, (
            f"La regla nombra al Bloque {num} pero no dice qué gate lo bloquea: falta {faltan}."
        )


def _bloque_por_tarea() -> dict[str, str]:
    """{id de tarea: numeral del bloque} dentro de la ruta al cierre."""
    ruta = _ruta()
    marcas = [(m.start(), m.group("num")) for m in BLOQUE_RE.finditer(ruta)]
    out: dict[str, str] = {}
    for m in TASK_HEADER_RE.finditer(ruta):
        actual = None
        for pos, num in marcas:
            if pos >= m.start():
                break
            actual = num
        if actual is not None:
            out[m.group("id")] = actual
    return out


#: Encabezado de fase dentro de la ruta al cierre.
FASE_RE = re.compile(r"^## Fase (?P<num>[0-9]+(?:\.[0-9]+)+)\b.*$", re.M)

#: `**Depende de:** Fases 2.3–2.8` — una tarea puede colgar de **fases enteras**, no solo de
#: tareas. Era el cuarto punto ciego, y estructural: `T-2.84` (Bloque II) declara así su
#: dependencia de los Bloques I y II, y el cruce **no existía** para el test porque
#: `TASK_ID_RE` solo ve `T-…`. El guion puede ser `–` (en dash, el que usa el archivo), `—`
#: o `-`.
DEP_FASE_RE = re.compile(r"Fases?\s+(?P<a>[0-9]+\.[0-9]+)(?:\s*[–—-]\s*(?P<b>[0-9]+\.[0-9]+))?")


def _clave_de_fase(num: str) -> tuple[int, ...]:
    """`"2.10"` → `(2, 10)`. Comparar como float pondría la Fase 2.10 **antes** de la 2.3."""
    return tuple(int(x) for x in num.split("."))


def _bloque_por_fase() -> dict[str, str]:
    """{número de fase: numeral del bloque} dentro de la ruta al cierre."""
    ruta = _ruta()
    marcas = [(m.start(), m.group("num")) for m in BLOQUE_RE.finditer(ruta)]
    out: dict[str, str] = {}
    for m in FASE_RE.finditer(ruta):
        actual = None
        for pos, num in marcas:
            if pos >= m.start():
                break
            actual = num
        if actual is not None:
            out[m.group("num")] = actual
    return out


def _bloque_por_nodo() -> dict[str, str]:
    """{tarea **o** `Fase N.M`: numeral del bloque}."""
    out = _bloque_por_tarea()
    out.update({f"Fase {n}": b for n, b in _bloque_por_fase().items()})
    return out


def _dependencias_de_la_ruta() -> list[tuple[str, str]]:
    """[(tarea, nodo del que depende)] declarados con `**Depende de:**`.

    El nodo es una tarea (`T-2.78`) o una fase entera (`Fase 2.3`), porque el archivo usa
    las dos formas y solo la primera estaba cubierta.
    """
    ruta = _ruta()
    fases = _bloque_por_fase()
    marcas = list(TASK_HEADER_RE.finditer(ruta))
    pares: list[tuple[str, str]] = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(ruta)
        cuerpo = ruta[m.start() : fin]
        for d in DEPENDE_RE.finditer(cuerpo):
            lista = d.group("lista")
            pares += [(m.group("id"), dep) for dep in TASK_ID_RE.findall(lista)]
            for f in DEP_FASE_RE.finditer(lista):
                lo = _clave_de_fase(f.group("a"))
                hi = _clave_de_fase(f.group("b")) if f.group("b") else lo
                pares += [
                    (m.group("id"), f"Fase {n}") for n in fases if lo <= _clave_de_fase(n) <= hi
                ]
    return pares


def test_toda_dependencia_que_cruza_de_bloque_esta_declarada_en_el_preambulo() -> None:
    """Un cruce entre bloques que solo consta en la ficha de una tarea es un cruce invisible.

    El caso medido: `T-2.94` (Bloque III, gates `G-06`/`G-08`) declara `Depende de: T-2.78`,
    que es del Bloque II — mientras el preámbulo del Bloque III decía "**no espera** al
    Bloque II". El cruce es legítimo (un simulacro con cascada de notificación REAL no se
    acredita con canales simulados), lo que faltaba era escribirlo donde se planifica.

    Segundo caso, invisible hasta el 2026-08-05: `T-2.84` declara `Depende de: Fases 2.3–2.8`,
    y las Fases 2.3/2.4 son del Bloque I. El cruce Bloque II→Bloque I existía desde que se
    escribió la ruta y **no lo veía nadie**, porque el test solo sabía leer IDs `T-…`.
    """
    bloque = _bloque_por_nodo()
    preambulos = _preambulos_de_bloque()
    fallos: list[str] = []
    for tid, dep in _dependencias_de_la_ruta():
        origen, destino = bloque.get(tid), bloque.get(dep)
        if origen is None or destino is None or origen == destino:
            continue
        if tid not in preambulos.get(origen, ""):
            fallos.append(
                f"{tid} (Bloque {origen}) depende de {dep} (Bloque {destino}) y el preámbulo "
                f"del Bloque {origen} no lo dice"
            )
    assert not fallos, (
        "Cruces entre bloques sin declarar:\n  "
        + "\n  ".join(fallos)
        + "\n  Escríbelo en el preámbulo del bloque, nombrando la tarea y su razón."
    )


# ---------------------------------------------------------------------------
# 6-bis · La RUTA CRÍTICA no puede contradecir a la lista de la RUTA CRÍTICA
# ---------------------------------------------------------------------------
#
# Misma forma que el bloqueante original de esta sección —afirmación categórica contra
# dependencia declarada— y esta vez a **18 líneas** de distancia, no a 465:
#
#   `G-04 ∧ G-02 ∧ T-2.89 ∧ T-2.96 ∧ **T-2.74** ∧ notificación real (**T-2.75→T-2.78**)`
#   «Es el único bloque cuyo retraso retrasa el proyecto entero.» (dicho del Bloque III)
#
# `T-2.74` y `T-2.75`…`T-2.78` son del **Bloque II**: dos de los seis ítems de la ruta crítica
# viven fuera del bloque declarado único, así que un retraso del Bloque II retrasa el proyecto
# por definición. Y lo refuerza la excepción 2 de la propia regla de ordenación: `T-2.94`
# (Bloque III) espera a `T-2.78` (Bloque II), o sea que el Bloque II arrastra hasta un gate.

RUTA_CRITICA_INICIO = "## RUTA CRÍTICA"

#: El bloque cercado que enuncia la ruta. Es la declaración canónica; la prosa que lo rodea
#: la comenta. Leer solo de aquí evita que un comentario nuevo se cuele como ítem de la ruta.
_FORMULA_RE = re.compile(r"```\n(?P<formula>[^`]*?)\n```", re.S)

#: Afirmación de exclusividad. El `(?<!no )` deja pasar la forma negada ("**no** es el único
#: bloque…"), que es la redacción honesta cuando la ruta sale del bloque.
EXCLUSIVIDAD_RE = re.compile(r"(?<!no )es el único bloque", re.I)


def _seccion_ruta_critica() -> str:
    text = TASKS.read_text(encoding="utf-8")
    i = text.find(RUTA_CRITICA_INICIO)
    assert i != -1, f"`TASKS.md` ya no contiene la sección {RUTA_CRITICA_INICIO!r}"
    j = text.find("\n## ", i + 1)
    return text[i:] if j == -1 else text[i:j]


def _tareas_de_la_ruta_critica() -> dict[str, list[str]]:
    """{numeral de bloque: [tareas de la ruta crítica que viven en él]}."""
    seccion = _seccion_ruta_critica()
    m = _FORMULA_RE.search(seccion)
    assert m, (
        "La `RUTA CRÍTICA` ya no enuncia su fórmula en un bloque cercado. Si cambió de "
        "formato, muévele el ancla a este test; si desapareció, este test sobra."
    )
    bloque = _bloque_por_tarea()
    out: dict[str, list[str]] = {}
    for tid in sorted(set(TASK_ID_RE.findall(m.group("formula")))):
        out.setdefault(bloque.get(tid, "(fuera de la ruta al cierre)"), []).append(tid)
    assert out, "La fórmula de la ruta crítica no nombra ninguna tarea."
    return out


def test_la_ruta_critica_no_declara_exclusivo_a_un_bloque_del_que_se_sale() -> None:
    por_bloque = _tareas_de_la_ruta_critica()
    seccion = _seccion_ruta_critica()

    for m in EXCLUSIVIDAD_RE.finditer(seccion):
        previos = list(re.finditer(r"Bloque (?P<num>[IVX]+)", seccion[: m.start()]))
        cual = previos[-1].group("num") if previos else "(sin bloque nombrado)"
        ajenas = {n: t for n, t in por_bloque.items() if n != cual}
        assert not ajenas, (
            f"La `RUTA CRÍTICA` declara que el Bloque {cual} «es el único bloque cuyo retraso "
            "retrasa el proyecto»,\n"
            "  pero su propia fórmula nombra tareas de otros bloques:\n"
            + "\n".join(f"    Bloque {n}: {', '.join(t)}" for n, t in sorted(ajenas.items()))
            + "\n  Una afirmación de exclusividad no sobrevive a una dependencia declarada 18 "
            "líneas más arriba.\n"
            "  La redacción honesta enumera los bloques que la ruta toca; si aun así hay uno "
            "que se\n  agenda primero, dilo por su razón (plazo, dueño humano), no por "
            "exclusividad."
        )

    faltan = [n for n in por_bloque if not re.search(rf"Bloque {n}\b", seccion)]
    assert not faltan, (
        f"La `RUTA CRÍTICA` nombra tareas de los bloques {faltan} y no menciona esos bloques: "
        f"{ {n: por_bloque[n] for n in faltan} }.\n"
        "  Quien lea la ruta tiene que ver de qué bloques depende sin ir a buscarlo 600 líneas "
        "más arriba."
    )


# ---------------------------------------------------------------------------
# 7 · Censo de gates: ninguno se queda sin dueño
# ---------------------------------------------------------------------------

FASE_GATES_RE = re.compile(r"^## (?P<fase>Fase [0-9.]+) · Gates físicos (?P<rango>.*)$", re.M)
CUBRE_RE = re.compile(r"\*\*Cubre (?P<lista>[^*]+)\*\*")


def _fase_de_gates() -> tuple[str, list[str], str]:
    """(título, gates del rango declarado en el título, nota de la fase hasta la 1ª tarea)."""
    ruta = _ruta()
    m = FASE_GATES_RE.search(ruta)
    assert m, "`TASKS.md` ya no tiene la fase de gates físicos con su rango en el título."
    extremos = GATE_RE.findall(m.group("rango"))
    assert len(extremos) == 2, (
        f"El título de la fase de gates no declara un rango legible: {m.group('rango')!r}"
    )
    lo, hi = (int(g.split("-")[1]) for g in extremos)
    resto = ruta[m.end() :]
    k = resto.find("\n### ")
    return m.group("fase"), [f"G-{n:02d}" for n in range(lo, hi + 1)], resto[: max(k, 0)]


def _cobertura_de_gates() -> dict[str, list[str]]:
    """{gate: [tareas que declaran cubrirlo]}."""
    ruta = _ruta()
    marcas = list(TASK_HEADER_RE.finditer(ruta))
    out: dict[str, list[str]] = {}
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(ruta)
        for c in CUBRE_RE.finditer(ruta[m.start() : fin]):
            for gate in GATE_RE.findall(c.group("lista")):
                out.setdefault(gate, []).append(m.group("id"))
    return out


def test_cada_gate_tiene_exactamente_una_tarea_que_lo_cubre() -> None:
    """`G-09` vivía fuera del censo: la fase se titula `G-01`…`G-10` y solo cubría nueve.

    `G-09` (restore real con RTO medido) lo cierra `T-2.74`, que vive en el Bloque II
    porque es una ventana AWS sobre software que sí controlamos, no una sesión con manos
    en el gabinete. Es un cruce legítimo — y por eso hay que escribirlo, no deducirlo.
    """
    fase, esperados, _ = _fase_de_gates()
    cobertura = _cobertura_de_gates()

    huerfanos = [g for g in esperados if g not in cobertura]
    assert not huerfanos, (
        f"Gates que la {fase} promete y ninguna tarea declara cubrir: {huerfanos}\n"
        "  Un gate sin tarea es un gate que se cierra el día que alguien se acuerde.\n"
        "  Decláralo con `**Cubre `G-XX`.**` en la tarea que lo acredita."
    )
    duplicados = {g: t for g, t in cobertura.items() if len(t) > 1}
    assert not duplicados, (
        f"Gates con más de un dueño declarado: {duplicados}\n"
        "  Dos dueños es ninguno: cada gate se marca una vez, en un sitio."
    )
    sobrantes = sorted(set(cobertura) - set(esperados))
    assert not sobrantes, f"Tareas que dicen cubrir gates fuera del rango de la {fase}: {sobrantes}"


def test_los_gates_que_se_cierran_fuera_de_su_fase_estan_anotados_en_ella() -> None:
    fase, esperados, nota = _fase_de_gates()
    _, _, _ = fase, esperados, nota  # legibilidad del mensaje de abajo
    cobertura = _cobertura_de_gates()
    bloque = _bloque_por_tarea()
    fuera = {
        gate: tareas[0]
        for gate, tareas in sorted(cobertura.items())
        if bloque.get(tareas[0]) != BLOQUE_DE_GATES
    }
    faltan = [
        f"{gate} lo cubre {tarea} (Bloque {bloque.get(tarea)}) y la nota de la {fase} no lo dice"
        for gate, tarea in fuera.items()
        if gate not in nota or tarea not in nota
    ]
    assert not faltan, (
        "Gates que se cierran fuera del carril de gates sin dejar rastro donde se buscan:\n  "
        + "\n  ".join(faltan)
        + f"\n  Quien lea la {fase} tiene que encontrar ahí los diez, aunque sea para que le "
        "digan dónde está el que falta."
    )


# ---------------------------------------------------------------------------
# 8 · La spec del panel del gabinete no puede declarar hex que el código ya no usa
# ---------------------------------------------------------------------------
#
# `takab-docs/design/` está en SKIP_PATHS para el escaneo de marcadores: es referencia
# visual congelada. **Este archivo es la excepción**, y por eso se cita explícito:
# `TASKS.md` lo declara entrada de diseño normativa de T-2.15…T-2.23 ("§5.1 congelada",
# "invariantes de §9 que el código NO puede renegociar") y el panel se verificó contra él
# con un checklist 44/44. Una spec normativa con un hex muerto manda mal a quien la obedezca.
#
# Caso medido (2026-08-05): la spec declaraba `--tk-fg-3 #6F7E8F` después de que T-2.64 lo
# subiera a `#8A9CB1` por contraste AA (3.48:1 → 5.14:1 sobre `--tk-surface-1`).

SPEC_PANEL = REPO / "takab-docs" / "design" / "edge-panel" / "ESPECIFICACION-PANEL-GABINETE.md"
TOKENS_CSS = REPO / "shared" / "design-tokens" / "css" / "tokens.css"

_VALOR_RE = re.compile(r"#[0-9A-Fa-f]{6}\b|rgba\([^)]*\)")
_TOKEN_RE = re.compile(r"--tk-[a-z0-9-]+")


def _seccion_color_de_la_spec() -> str:
    """La parte **declarativa** de la §10.1: tabla de superficies, texto, acento y semáforo.

    Se cae dos cosas a propósito:
      - los bloques cercados (```): las sombras son compuestas (`0 0 0 1px #FF5252, …`) y no
        son pares token↔hex;
      - las citas en bloque (`>`): son **comentario** —la razón de un cambio, la historia de
        un token retirado— y nombran hex viejos justamente para explicar por qué murieron.
        Confundir la nota con la declaración hacía que el propio texto que documenta el
        arreglo se leyera como el defecto (medido al escribirlo: 3 falsos desalineados).
    """
    text = SPEC_PANEL.read_text(encoding="utf-8")
    i = text.find("### 10.1 · Color")
    assert i != -1, "La spec del panel ya no tiene la §10.1 de color."
    j = text.find("\n### ", i + 1)
    seccion = re.sub(r"```.*?```", " ", text[i:] if j == -1 else text[i:j], flags=re.S)
    return "\n".join(ln for ln in seccion.splitlines() if not ln.lstrip().startswith(">"))


def _pares_declarados() -> list[tuple[str, str]]:
    """[(token, valor)] de la §10.1.

    Regla de emparejamiento: **cada valor pertenece a todos los tokens que aparecen desde
    el valor anterior**. Cubre las dos formas que usa la spec —fila de tabla con alias
    (`--tk-surface-0` / `--tk-navy-900` | `#0E2336`) y prosa (`--tk-fg-3 #6F7E8F`)— y
    descarta sola las que no son pares (hover/press/tintes, que van sin token).
    """
    texto = _seccion_color_de_la_spec()
    pares: list[tuple[str, str]] = []
    cursor = 0
    for m in _VALOR_RE.finditer(texto):
        for t in _TOKEN_RE.finditer(texto[cursor : m.start()]):
            pares.append((t.group(0), m.group(0)))
        cursor = m.end()
    return pares


def test_la_spec_del_panel_declara_los_hex_que_el_codigo_usa_hoy() -> None:
    css = TOKENS_CSS.read_text(encoding="utf-8")
    real = {
        m.group("tok"): m.group("val").strip()
        for m in re.finditer(r"(?P<tok>--tk-[a-z0-9-]+)\s*:\s*(?P<val>[^;]+);", css)
    }

    def norm(v: str) -> str:
        return re.sub(r"\s+", "", v).lower()

    desalineados = [
        f"{tok}: la spec dice `{val}` y `shared/design-tokens/css/tokens.css` usa `{real[tok]}`"
        for tok, val in _pares_declarados()
        if tok in real and norm(val) != norm(real[tok])
    ]
    assert not desalineados, (
        "La spec normativa del panel declara colores que el código ya no usa:\n  "
        + "\n  ".join(desalineados)
        + "\n  Actualiza la spec **con la razón del cambio** (no solo el hex): quien la lea "
        "dentro de un año\n  necesita saber por qué subió, o lo volverá a bajar."
    )


# ---------------------------------------------------------------------------
# 9 · El blueprint GOBIERNA: no puede atribuirle al sistema algo que no existe
# ---------------------------------------------------------------------------
#
# `CLAUDE.md §5`: "Ante cualquier ambigüedad de arquitectura, este documento gobierna". Por eso
# una mentira aquí es la más cara del repo: nadie va a ir a comprobarla al código, porque el
# documento es la autoridad. El caso medido el 2026-08-05: el blueprint declaraba GraphQL en
# **siete** sitios —incluido `api/  # backend cloud (FastAPI + GraphQL)  [existe]`, que es una
# afirmación de existencia literal— con **cero** ocurrencias de `graphql|strawberry|ariadne|
# graphene` en `api/src/`, `api/pyproject.toml` y `web/package.json`. El gate #5 había
# ratificado REST + WS nativo el 2026-07-06 y la nota de §5.5 solo desactivaba **el bullet
# inmediatamente anterior**.
#
# El mecanismo es general y se auto-apaga: se cruza el nombre de la tecnología contra su
# huella real en el código. El día que `T-3.15` implemente GraphQL, estos tests se callan
# solos sin que nadie los edite.

#: {tecnología: (huella que demuestra su presencia REAL, raíces donde tendría que vivir)}.
#: Las raíces son **manifiestos y fuente**, nunca documentación: un doc que se cita a sí mismo
#: como prueba de que algo existe es exactamente el defecto que esto viene a cazar.
TECNOLOGIAS = {
    "GraphQL": (
        re.compile(r"graphql|strawberry|ariadne|graphene", re.I),
        (REPO / "api" / "src", REPO / "api" / "pyproject.toml", REPO / "web" / "package.json"),
    ),
    "FastAPI": (
        re.compile(r"fastapi", re.I),
        (REPO / "api" / "src", REPO / "api" / "pyproject.toml"),
    ),
    "MapLibre": (
        re.compile(r"maplibre", re.I),
        (REPO / "web" / "src", REPO / "web" / "package.json"),
    ),
    "TimescaleDB": (re.compile(r"timescaledb", re.I), (REPO / "db",)),
    "PostGIS": (re.compile(r"postgis", re.I), (REPO / "db",)),
    "BACnet": (re.compile(r"bacpypes|BAC0|bacnet", re.I), (REPO / "edge",)),
}

#: Control de que el detector no está roto en ninguna de las dos direcciones. Un escáner que
#: siempre dice "sí" vuelve vacuos los tests de abajo; uno que siempre dice "no" los vuelve
#: absurdamente estrictos. Ninguna de las dos averías se ve en el resultado del test que
#: importa, así que se mide aquí.
PRESENCIA_ESPERADA = (
    ("GraphQL", False),
    ("FastAPI", True),
    ("MapLibre", True),
    ("TimescaleDB", True),
    ("PostGIS", True),
    ("BACnet", True),
)

#: Manifiestos que no son `.md`/`.py`/`.ts` y aun así son prueba de dependencia real.
_MANIFIESTOS = TEXT_SUFFIXES | {".json", ".lock"}

#: Una línea que nombra una tecnología ausente **y dice que no está** no es una mentira: es
#: la nota que documenta por qué no está. `deck` porque el blueprint cita literalmente el deck
#: de producto (§5.5, §7); `T-3.15` porque ahí vive el pos-MVP.
#:
#: El salvoconducto se evalúa **por línea, no por párrafo**, y eso es deliberado: la avería
#: original fue exactamente un párrafo que desactivaba a su vecino por proximidad. Cada línea
#: que nombre una tecnología ausente tiene que decirlo ella misma.
_SALVOCONDUCTO_RE = re.compile(
    r"RATIFICADO|deck|pos-MVP|T-3\.15|diferid|fuera de alcance|no se implementa"
    r"|ausente|no construid|sin implementar|descartad",
    re.I,
)


def _grep(patron: re.Pattern[str], *raices: Path) -> str | None:
    """`archivo:línea` del primer acierto de `patron` bajo `raices`, o `None`.

    **Se salta este archivo a propósito.** `TECNOLOGIAS` escribe `graphql` en un regex y
    `api/tests/` cuelga de `api/`: sin esta línea, el test se cita a sí mismo como prueba de
    que GraphQL existe. Es el falso verde perfecto — el test que se acredita con su propio
    texto.
    """
    me = Path(__file__).resolve()
    pendientes = list(raices)
    while pendientes:
        p = pendientes.pop()
        if p.is_symlink() or not p.exists():
            continue
        if p.is_dir():
            if p.name not in SKIP_DIRS:
                pendientes.extend(p.iterdir())
            continue
        if p.suffix not in _MANIFIESTOS or p.resolve() == me:
            continue
        try:
            texto = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(texto.splitlines(), start=1):
            if patron.search(line):
                return f"{p.relative_to(REPO)}:{n}"
    return None


def _presente(tech: str) -> str | None:
    patron, raices = TECNOLOGIAS[tech]
    return _grep(patron, *raices)


@pytest.mark.parametrize("tech,esperado", PRESENCIA_ESPERADA, ids=lambda v: str(v))
def test_el_detector_de_presencia_distingue_lo_que_esta_de_lo_que_no(
    tech: str, esperado: bool
) -> None:
    donde = _presente(tech)
    assert bool(donde) is esperado, (
        f"`{tech}`: el detector dice {'presente en ' + donde if donde else 'AUSENTE'} y la "
        f"tabla espera {'presente' if esperado else 'ausente'}.\n"
        "  Si es porque el mundo cambió (p. ej. `T-3.15` implementó GraphQL), actualiza la\n"
        "  tabla **y quita los salvoconductos del blueprint** en el mismo commit. Si no,\n"
        "  el escáner está roto y los dos tests de abajo están mintiendo en verde."
    )


def test_el_blueprint_no_atribuye_al_sistema_una_tecnologia_que_el_codigo_no_tiene() -> None:
    """Cada línea que nombra una tecnología ausente necesita decir que está ausente."""
    text = BLUEPRINT.read_text(encoding="utf-8")
    fallos: list[str] = []
    for tech in TECNOLOGIAS:
        if _presente(tech):
            continue
        for n, line in enumerate(text.splitlines(), start=1):
            if tech.lower() in line.lower() and not _SALVOCONDUCTO_RE.search(line):
                fallos.append(f"BLUEPRINT-TECNICO-TAKAB.md:{n} [{tech}]: {line.strip()[:110]}")
    assert not fallos, (
        "El documento que GOBIERNA la arquitectura nombra como parte del sistema tecnologías "
        "que no están en el código:\n  "
        + "\n  ".join(fallos)
        + "\n  Distingue lo que el DECK describía de lo que el sistema ES. Si la línea cita el "
        "deck,\n  dilo en la propia línea (como hace la nota de §5.5); si describe el sistema, "
        "corrígela."
    )


#: Renglón del árbol del monorepo en `BLUEPRINT §11`: `  ruta/   # descripción   [marcador]`.
ARBOL_RE = re.compile(r"^ {2}(?P<ruta>[\w./-]+/)\s+#\s*(?P<desc>.*)$", re.M)
_SECCION_ARBOL = "## 11. Estructura del monorepo"


def _arbol_del_blueprint() -> list[tuple[str, str]]:
    text = BLUEPRINT.read_text(encoding="utf-8")
    i = text.find(_SECCION_ARBOL)
    assert i != -1, f"`BLUEPRINT-TECNICO-TAKAB.md` ya no tiene {_SECCION_ARBOL!r}."
    j = text.find("\n## ", i + 1)
    seccion = text[i:] if j == -1 else text[i:j]
    filas = [(m.group("ruta"), m.group("desc")) for m in ARBOL_RE.finditer(seccion)]
    assert filas, "El árbol de `BLUEPRINT §11` dejó de parsearse: 0 filas."
    return filas


def test_el_arbol_del_blueprint_dice_la_verdad_sobre_lo_que_existe() -> None:
    """`[existe]` y "aún no existe" son afirmaciones comprobables, no decoración.

    Caso medido: `.github/workflows/` seguía anotado *"se crea en T-1.2 — aún no existe"*
    con `ci.yml` y `e2e.yml` dentro y el CI corriendo en cada PR desde hace un mes.
    """
    fallos: list[str] = []
    for ruta, desc in _arbol_del_blueprint():
        destino = REPO / ruta
        if "[existe]" in desc and not destino.exists():
            fallos.append(f"{ruta} se declara `[existe]` y no está en el árbol de archivos")
        if "aún no existe" in desc and destino.exists():
            fallos.append(f"{ruta} se declara 'aún no existe' y SÍ está: {destino}")
        for tech in TECNOLOGIAS:
            if tech.lower() not in desc.lower():
                continue
            if not _grep(TECNOLOGIAS[tech][0], destino):
                fallos.append(f"{ruta} se describe con `{tech}` y no hay rastro de eso bajo {ruta}")
    assert not fallos, (
        "El árbol de `BLUEPRINT §11` no coincide con el repo:\n  "
        + "\n  ".join(fallos)
        + "\n  Es el sitio del blueprint donde la afirmación es literalmente 'esto existe'."
    )


# ---------------------------------------------------------------------------
# 10 · No se deroga por sección lo que es prohibición, no diferido
# ---------------------------------------------------------------------------
#
# `BLUEPRINT §14` se titula "Fuera de alcance / **diferido** explícito" y contiene seis
# viñetas, pero **cinco de las seis son INVARIANTES** según la sección "INVARIANTES" de
# `TASKS.md` ("una tarea futura que proponga cualquiera de estas cosas **se rechaza sin
# discusión**"): T-MINUS, magnitud preliminar, streaming crudo, IA en la ruta determinista y
# tocar el Shake OS. La única realmente diferida es el mini-ShakeMap.
#
# `T-3.09` pedía como primer criterio "**derogar explícitamente** `BLUEPRINT §14` y
# `CLAUDE.md §8`". Cumplido al pie de la letra, eso deroga de un plumazo cuatro prohibiciones
# de seguridad —incluida "IA en la ruta determinista de disparo", que es la regla de oro 1—
# para poder construir un mapa. La orden tiene que nombrar la **viñeta**, no la sección.

_SECCION_14 = "## 14. Fuera de alcance / diferido explícito"

#: Clasificación explícita por viñeta: `[INVARIANTE · <clave>]` o `[DIFERIDO · <clave>]`.
#: La clave es lo que una tarea tiene que nombrar para poder derogar esa viñeta y solo esa.
CLASE_14_RE = re.compile(r"\[(?P<clase>INVARIANTE|DIFERIDO) · (?P<clave>[^\]]+)\]")

#: La viñeta entera, no su primera línea: el archivo envuelve a 100 columnas y la
#: clasificación cae a menudo en el segundo renglón. Leer solo la primera daba "0 viñetas
#: clasificadas" con las seis clasificadas — un rojo que apuntaba al sitio equivocado.
VINETA_14_RE = re.compile(r"^- \*\*.+?(?=\n- |\n\n|\Z)", re.M | re.S)

#: Una orden de derogación: nombra el verbo y la sección.
_DEROGA_RE = re.compile(r"derog\w*", re.I)


def _viñetas_del_14() -> list[tuple[str, str | None, str | None]]:
    """[(línea, clase, clave)] de cada viñeta de `BLUEPRINT §14`."""
    text = BLUEPRINT.read_text(encoding="utf-8")
    i = text.find(_SECCION_14)
    assert i != -1, f"`BLUEPRINT-TECNICO-TAKAB.md` ya no tiene {_SECCION_14!r}."
    j = text.find("\n## ", i + 1)
    seccion = text[i:] if j == -1 else text[i:j]
    out: list[tuple[str, str | None, str | None]] = []
    for m in VINETA_14_RE.finditer(seccion):
        c = CLASE_14_RE.search(m.group(0))
        out.append((m.group(0), c.group("clase") if c else None, c.group("clave") if c else None))
    assert out, "`BLUEPRINT §14` dejó de parsearse: 0 viñetas."
    return out


def test_cada_vineta_del_blueprint_14_declara_si_es_prohibicion_o_diferido() -> None:
    """Sin clasificar, "§14" se lee como un bloque homogéneo de cosas aplazadas. No lo es."""
    viñetas = _viñetas_del_14()
    sin_clase = [ln.strip()[:96] for ln, clase, _ in viñetas if clase is None]
    assert not sin_clase, (
        "Viñetas de `BLUEPRINT §14` sin clasificar:\n  "
        + "\n  ".join(sin_clase)
        + "\n  Marca cada una `[INVARIANTE · <clave>]` (prohibición: se rechaza sin discusión) "
        "o\n  `[DIFERIDO · <clave>]` (aplazada: se puede retomar derogándola por su nombre)."
    )
    clases = {clase for _, clase, _ in viñetas}
    assert clases == {"INVARIANTE", "DIFERIDO"}, (
        f"`BLUEPRINT §14` clasificó todo como {clases}. Si de verdad ya no queda ninguna de "
        "las dos\n  clases, este test sobra; mientras haya mezcla, la distinción es lo que "
        "impide derogarlas juntas."
    )


def test_ninguna_tarea_manda_derogar_la_seccion_entera_de_los_invariantes() -> None:
    """La viñeta se nombra **en la orden**, no en cualquier parte del bloque.

    Medido con mutación dirigida: buscar la clave en el bloque entero daba VERDE con la orden
    original intacta, porque **el título de `T-3.09` ya dice "Mini-ShakeMap"**. Un test que se
    conforma con el título acredita el criterio equivocado. Se busca por trozo —cada criterio
    `- [ ]` y cada párrafo por separado— para que la clave tenga que estar donde se ordena.
    """
    diferidos = [k for _, c, k in _viñetas_del_14() if c == "DIFERIDO"]
    invariantes = [k for _, c, k in _viñetas_del_14() if c == "INVARIANTE"]
    fallos: list[str] = []
    for tid, (_, cuerpo) in _bloques().items():
        for trozo in re.split(r"\n\s*\n|\n(?=\s*- \[)", cuerpo):
            plano = _plano(trozo)
            if not (_DEROGA_RE.search(plano) and "§14" in plano):
                continue
            if not any(k.lower() in plano.lower() for k in diferidos):
                fallos.append(
                    f"{tid} · «{plano.strip()[:80]}…» manda derogar `BLUEPRINT §14` sin nombrar "
                    f"ninguna viñeta diferida ({diferidos})"
                )
            elif "INVARIANTE" not in cuerpo:
                fallos.append(
                    f"{tid} manda derogar dentro de `BLUEPRINT §14` sin decir que "
                    f"{len(invariantes)} de sus viñetas son INVARIANTES ({invariantes}) y no "
                    "se tocan"
                )
    assert not fallos, (
        "Órdenes de derogación que se llevarían por delante prohibiciones de seguridad:\n  "
        + "\n  ".join(fallos)
        + "\n  `BLUEPRINT §14` no es una lista homogénea de diferidos: casi toda ella son "
        "INVARIANTES\n  (`TASKS.md`, sección INVARIANTES: 'se rechaza sin discusión'). "
        "Deroga la viñeta, no la sección."
    )


# ---------------------------------------------------------------------------
# 10.bis · El censo mide ESTA rama, no un checkout ajeno
# ---------------------------------------------------------------------------
#
# Caso medido el 2026-08-08: una sesión murió dejando un `git worktree` vivo en
# `.claude/worktrees/t2-70a-d1/`, que es un checkout COMPLETO del monorepo **dentro** del
# monorepo. `_repo_text_files()` descendió a él y encontró los marcadores literales que
# esta misma suite lleva dentro (`[SUPUESTO #4]`, `[SUPUESTO plan-maestro-01 #6]`, …), que
# ahí no son marcadores muertos: son las cadenas que el test busca.
#
# Resultado: **5 tests en rojo denunciando ficheros que no son de esta rama.** El censo se
# excluye a sí mismo por ruta exacta (`entry.resolve() != me`), y una copia en otro
# checkout tiene otra ruta, así que la autoexclusión no la cubría.
#
# El arreglo no enumera `.claude/worktrees/`: deriva la propiedad estructural —un checkout
# ajeno lleva su propio `.git`—, porque el sitio donde el harness pone los worktrees es una
# convención de hoy y el siguiente aparecerá en otro lado.


def _finge_un_worktree(raiz: Path, nombre: str, contenido: str) -> Path:
    """Un checkout anidado creíble: su propio `.git` (fichero, como los worktrees reales)."""
    d = raiz / nombre
    (d / "takab-docs").mkdir(parents=True)
    (d / ".git").write_text("gitdir: /otro/lado/.git/worktrees/x\n", encoding="utf-8")
    (d / "takab-docs" / "TASKS.md").write_text(contenido, encoding="utf-8")
    return d


def test_el_censo_no_desciende_a_un_checkout_anidado(tmp_path: Path) -> None:
    """Un worktree dentro del repo es de OTRA rama: su contenido no es evidencia de esta."""
    (tmp_path / "takab-docs").mkdir()
    propio = tmp_path / "takab-docs" / "TASKS.md"
    propio.write_text("archivo de esta rama\n", encoding="utf-8")
    ajeno = _finge_un_worktree(tmp_path, "worktree-vecino", "[SUPUESTO #4] de otra rama\n")

    censados = _repo_text_files(tmp_path)

    assert propio in censados, "el censo debe seguir viendo los ficheros de esta rama"
    assert (ajeno / "takab-docs" / "TASKS.md") not in censados, (
        "el censo descendió a un checkout anidado: sus marcadores no son de esta rama y "
        "pondrían en rojo tests que no tienen nada que ver con el código auditado."
    )


def test_el_censo_no_confunde_un_directorio_normal_con_un_checkout(tmp_path: Path) -> None:
    """No vacuo: sin `.git` dentro, el mismo árbol SÍ se censa. Prueba que la guardia
    discrimina por la propiedad estructural y no por el nombre del directorio."""
    (tmp_path / "worktree-vecino" / "takab-docs").mkdir(parents=True)
    normal = tmp_path / "worktree-vecino" / "takab-docs" / "TASKS.md"
    normal.write_text("subdirectorio corriente, no un checkout\n", encoding="utf-8")

    assert normal in _repo_text_files(tmp_path)


# ---------------------------------------------------------------------------
# 11 · Un blockquote no puede tragarse valores normativos
# ---------------------------------------------------------------------------
#
# CommonMark aplica **continuación laxa** (*lazy continuation*): una línea de párrafo que va
# pegada a un blockquote, sin línea en blanco de por medio y sin su propio `>`, se renderiza
# **dentro** del blockquote. Es invisible en el diff y en el editor, y solo se ve al render.
#
# Caso medido el 2026-08-05 en `ESPECIFICACION-PANEL-GABINETE.md §10.2`: una nota `>` que
# terminaba en *"esto es deuda declarada, no permiso."* iba seguida sin línea en blanco de
# `**Interlineado:**`, `**Tracking:**`, `**Espaciado:**` y `**Radios:**`. Cuatro declaraciones
# **normativas** de una spec que `TASKS.md` declara entrada de diseño obligatoria pasaron a
# leerse como parte de una nota de deuda. La deuda se puede ignorar; la norma no.

#: Una declaración normativa: la línea abre con `**Clave:**`. Es la forma que usa la spec para
#: todo lo que el código debe obedecer (tamaños, interlineado, radios, espaciado).
DECLARACION_RE = re.compile(r"^\*\*[^*]+:\*\*")

#: Constructos que **interrumpen** un párrafo en CommonMark y por tanto cortan la
#: continuación laxa: encabezado ATX, cerca de código, regla horizontal, ítem de lista.
_INTERRUMPE_RE = re.compile(r"(?:#{1,6} |```|~~~|---|\*\*\*|___|[-*+] |\d+[.)] )")


def _tragadas_por_un_blockquote(texto: str) -> list[tuple[int, str]]:
    """[(línea, contenido)] de las declaraciones normativas absorbidas por un `>` vecino."""
    dentro = False
    out: list[tuple[int, str]] = []
    for n, linea in enumerate(texto.splitlines(), start=1):
        s = linea.lstrip()
        if s.startswith(">"):
            dentro = True
            continue
        if not s or _INTERRUMPE_RE.match(s):
            dentro = False
            continue
        if dentro and DECLARACION_RE.match(linea):
            out.append((n, linea.strip()))
    return out


@pytest.mark.parametrize(
    "path", (*DOCS_DE_GOBIERNO, SPEC_PANEL), ids=lambda p: p.name if hasattr(p, "name") else str(p)
)
def test_ningun_valor_normativo_queda_dentro_de_un_blockquote_por_descuido(path: Path) -> None:
    tragadas = _tragadas_por_un_blockquote(path.read_text(encoding="utf-8"))
    assert not tragadas, (
        f"Declaraciones normativas absorbidas por un blockquote en `{path.relative_to(REPO)}`:\n  "
        + "\n  ".join(f"{path.name}:{n}: {linea[:96]}" for n, linea in tragadas)
        + "\n  Continuación laxa de CommonMark: el `>` de arriba se las traga porque no hay "
        "línea en blanco\n  entre la nota y la declaración. Mete la línea en blanco. Si de "
        "verdad va dentro de la nota,\n  ponle su propio `>` para que se vea en el diff."
    )


# ===========================================================================
# INVENTARIO DE LO QUE ESTE ARCHIVO **NO** CUBRE (medido el 2026-08-05)
# ===========================================================================
#
# Un punto ciego documentado es un activo. Uno que se cree cerrado es el defecto que este
# archivo lleva tres rondas persiguiendo: un test que da permiso en vez de cobertura. Lo de
# abajo está medido, no supuesto, y ninguna de estas líneas debería sorprender a nadie que
# lea un verde de esta suite.
#
# --- Huecos con nombre y apellido (defectos vivos, no limitaciones de diseño) ------------
#
# N1. **`edge/` sigue etiquetando como supuestos dos gates ratificados.** Cuatro sitios:
#     `edge/takab_edge/actuators/__init__.py:3` y `edge/takab_edge/config/settings.py:405`
#     (`[SUPUESTO plan-maestro-01 #4]`), `edge/takab_edge/gpio/__init__.py:3`
#     (`[SUPUESTO plan-maestro-01 #6]`) y `edge/tests/test_actuators.py:59` (`[SUPUESTO #4]`).
#     `test_ningun_gate_ratificado_sigue_etiquetado_como_supuesto_en_los_documentos` mira solo
#     `DOCS_DE_GOBIERNO`, y el repo-wide solo caza el framing "confirmar/override", que ahí no
#     aparece. **Quedaron fuera por alcance de la ronda, no porque estén bien**: el gate #6 es
#     justo el del módulo `gpio`. Ampliar `DOCS_DE_GOBIERNO` a esos cuatro archivos convierte
#     esto en rojo el día que se puedan tocar.
#
# N2. **21 tareas de los Bloques IV y V no declaran `**Componente:**` ni `**Depende de:**`**
#     (`T-3.01`…`T-3.16` y `T-4.01`…`T-4.05`), mientras todas las de I–III sí. Como
#     `_dependencias_de_la_ruta` solo lee lo declarado, **ningún cruce de bloque que nazca en
#     IV o V puede detectarse**. No se inventaron las fichas que faltan: escribir dependencias
#     que nadie ha decidido sería fabricar hechos, que es la avería que esto persigue.
#
# N3. **Los preámbulos de los Bloques I y V miden 0 caracteres.** El Bloque II tenía 0 hasta
#     esta ronda y por eso el cruce `T-2.84`→Fases 2.3/2.4 podía estar "sin declarar" sin que
#     nadie lo notara. Mientras midan 0, ningún cruce entrante a I o V puede estar declarado
#     donde el test lo busca — el rojo llegaría, pero apuntando a un sitio que no existe.
#
# --- Límites de forma: grafías que siguen invisibles -------------------------------------
#
# L1. **`CIERRA_RE` no ve las formas negadas ni interrogativas** ("no se cierra `T-X`",
#     "¿cierra `T-X`?"): darían **falso positivo**, no falso negativo. Hoy no aparecen ninguna
#     vez en `TASKS.md` y el fallo sería hacia el lado ruidoso, que es el seguro.
#
# L2. **`CIERRA_RE` solo conoce el verbo "cerrar".** "Lo resuelve `T-X`", "queda absorbida por
#     `T-X`", "`T-2.64` → `T-2.59`" declaran lo mismo y no los ve. La tabla `FORMAS_DE_CIERRE`
#     es el sitio donde añadirlos: primero la fila, luego el patrón.
#
# L3. **`EXCLUSIVIDAD_RE` solo conoce la grafía "es el único bloque".** "Solo el Bloque III
#     puede retrasar…", "ningún otro bloque…" vuelven a quedar ciegos. Es la misma clase de
#     ceguera que tenía `DEAD_MARKERS` antes de esta ronda; no se generalizó porque la
#     afirmación es prosa libre y no hay censo del que derivarla, como sí lo hay para gates.
#
# L4. **`DEPENDE_RE` corta la lista en el primer `·`.** Hoy es correcto (el `·` separa campos:
#     `Depende de: X · Origen: Y`), pero una lista de dependencias separada por `·` perdería
#     todo menos la primera.
#
# L5. **El detector de continuación laxa solo mira declaraciones `**Clave:**`.** Una tabla,
#     una viñeta o un párrafo de prosa absorbidos por un blockquote no se detectan.
#
# ---------------------------------------------------------------------------
# El RPO del runbook de backup sale de la configuración, no de una promesa
# ---------------------------------------------------------------------------
#
# T-2.72 pedía un RPO "derivable de la configuración, no de una promesa". Terraform lo deriva
# de los atributos del recurso de alarma y lo publica como `rpo_seconds`. Pero el sitio donde
# el proyecto DECLARA su RPO —donde va a mirarlo un humano— es el runbook, y ahí la cifra
# vuelve a ser un número tecleado a mano. Ese es el eslabón que este test cierra.
#
# No es hipotético: hasta el 2026-08-08 el §2 de ese runbook decía "RPO actual ≤ 24 h" y
# "objetivos PROPUESTOS: RPO ≤ 15 min" con el PITR ya escrito en el terraform. Una cifra
# obsoleta en el documento de gobierno vale menos que ninguna: quien la lea no va a ir a
# comprobarla al `.tf`.
#
# LA DERIVACIÓN, que es la parte que hay que entender antes de tocar los números:
#
#     RPO = umbral_de_la_alarma + period × evaluation_periods
#
# El primer término es obvio. El segundo NO es adorno y por eso se comprueba: CloudWatch no
# avisa al cruzar el umbral, avisa tras `evaluation_periods` periodos SEGUIDOS por encima, y
# durante esos minutos se sigue acumulando WAL que no está en S3. Tomar solo el umbral sería
# el mismo error que tomar `archive_timeout`, un escalón más arriba: confundir el caso feliz
# de la detección con el peor caso.
_RPO_RUNBOOK_RE = re.compile(r"^### RPO: (\d+) s ", re.M)
_MAX_AGE_RE = re.compile(r'variable "wal_archive_max_age_s".*?^\s*default\s*=\s*(\d+)', re.S | re.M)
_ALARM_RE = re.compile(
    r'resource "aws_cloudwatch_metric_alarm" "wal_archive_stalled".*?^\}', re.S | re.M
)


def _atributo_numerico(bloque: str, nombre: str) -> int:
    match = re.search(rf"^\s*{nombre}\s*=\s*(\d+)\s*$", bloque, re.M)
    assert match, f"la alarma `wal_archive_stalled` ya no declara `{nombre}` como literal"
    return int(match.group(1))


def test_el_rpo_del_runbook_de_backup_es_el_que_deriva_el_terraform() -> None:
    runbook = RUNBOOK_BACKUP.read_text(encoding="utf-8")
    declarado = _RPO_RUNBOOK_RE.search(runbook)
    assert declarado, (
        "El runbook de backup ya no declara su RPO en la forma `### RPO: <n> s `. "
        "Ese encabezado es el ancla de este test: si cambia la redacción, cambia también "
        "`_RPO_RUNBOOK_RE` — no borres el ancla y dejes la cifra suelta."
    )

    umbral = _MAX_AGE_RE.search(TF_DB_VARS.read_text(encoding="utf-8"))
    assert umbral, "no se pudo leer el default de `wal_archive_max_age_s`: el test estaría vacío"

    alarma = _ALARM_RE.search(TF_OBSERVABILITY.read_text(encoding="utf-8"))
    assert alarma, (
        "no se encontró el recurso `aws_cloudwatch_metric_alarm.wal_archive_stalled`: "
        "sin la alarma, `rpo_seconds` no describe nada y el RPO del runbook es una promesa"
    )
    bloque = alarma.group(0)
    derivado = int(umbral.group(1)) + _atributo_numerico(bloque, "period") * _atributo_numerico(
        bloque, "evaluation_periods"
    )

    assert int(declarado.group(1)) == derivado, (
        "El RPO que declara `RUNBOOK-backup-restore-db.md` §2 no es el que deriva la "
        "configuración.\n"
        f"  runbook:  {declarado.group(1)} s\n"
        f"  terraform: {derivado} s  (umbral {umbral.group(1)} + period × evaluation_periods)\n"
        "  El runbook es donde un humano BUSCA el RPO. Una cifra tecleada que ya no cuadra "
        "con la alarma que la sostiene es exactamente la 'promesa' que T-2.72 existía para "
        "eliminar. Actualiza el runbook en el MISMO commit que mueva los números."
    )


def test_el_rpo_declarado_se_apoya_en_una_alarma_que_no_puede_callarse() -> None:
    """La derivación del RPO es MENTIRA si el silencio de la métrica no alarma.

    Si el publicador de `WalArchiveAgeSeconds` muere, la métrica desaparece. Con `missing` o
    `notBreaching` la alarma se quedaría callada para siempre y el RPO pasaría a ser
    ilimitado — el runbook seguiría anunciando 900 s con el archivado parado hace semanas.
    Los tests de terraform ya lo exigen en dos archivos; esto ata el tercer extremo: que el
    NÚMERO PUBLICADO en el documento de gobierno dependa de esa decisión y no la sobreviva.
    """
    alarma = _ALARM_RE.search(TF_OBSERVABILITY.read_text(encoding="utf-8"))
    assert alarma, "no se encontró la alarma `wal_archive_stalled`"
    assert 'treat_missing_data  = "breaching"' in alarma.group(0), (
        "La alarma del archivado dejó de estar en `breaching`. El RPO que publica el runbook "
        "se apoya en que la AUSENCIA de la métrica alarme: sin eso, el publicador puede morir "
        "y el silencio pasa por salud."
    )


# --- Límites de fondo: qué clase de verdad se está comprobando ---------------------------
#
# F1. **`TECNOLOGIAS` es una lista de seis, no un descubridor.** Una tecnología inventada de
#     cero en el blueprint (gRPC, Kafka, NATS) no la ve nadie hasta que alguien la añade al
#     registro. Y la presencia se mide **por nombre en manifiesto o fuente**, no por uso real:
#     una dependencia declarada y jamás importada cuenta como presente.
#
# F2. **`_bloques()` atribuye el preámbulo de una fase a la tarea que la precede.** Por eso el
#     rojo de la Fase 3.1 salió firmado por `T-3.05`. Falla hacia el lado estricto (más rojo,
#     no menos), pero el ID del mensaje puede apuntar a la tarea equivocada.
#
# F3. **Esto cruza documentos entre sí y contra el árbol de archivos; no contra la realidad.**
#     Que `PLAN-MAESTRO §3` diga que un gate está ratificado no prueba que la decisión se
#     tomara, igual que un `[x]` no prueba que la tarea funcione. Lo único que se garantiza es
#     que **el repositorio no se contradice a sí mismo**.
#
# F4. **`takab-docs/design/` sigue en `SKIP_PATHS`** salvo la spec del panel, y de la spec
#     solo se leen §10.1 (color) y las declaraciones tragadas por blockquotes. El hex retirado
#     `#6F7E8F` sigue vivo en `design/edge-panel/uploads/…` y en `design/**/colors_and_type.css`
#     **a propósito**: es referencia visual congelada (`PLAN-MAESTRO §2 R11`) y `uploads/` es
#     el original subido — un archivo que se corrige deja de ser el original.
#
# F5. **La cabecera de conteo se verifica contra `^### [.] T-…`, que es la definición de
#     "tarea" de este archivo.** Una tarea escrita con otro encabezado no existe para el
#     conteo ni para los cierres cruzados.
#
# F6. **El cruce del RPO ata el runbook a los DEFAULTS del `.tf`, no al valor aplicado.** Si
#     `envs/dev` pasara un `wal_archive_max_age_s` distinto del default de `modules/database`,
#     este test seguiría verde comparando contra el default y el runbook publicaría un número
#     que la cuenta real no tiene. Quien vigila esa costura es la `precondition` de
#     `envs/dev/outputs.tf` — y esa **solo se evalúa en el `apply`** (`validate` no mira
#     preconditions, y meter un plan de ese entorno en CI choca con el `profile` cableado en
#     `providers.tf`). O sea: entre los dos se cubre el camino entero, pero el último tramo no
#     lo comprueba nadie hasta la ventana HUMANO-AWS de `T-2.74`.
#
# F7. **Y ata el número, no la realidad.** Que el runbook, las variables y la alarma digan 900
#     no prueba que se esté archivando un solo WAL. Eso lo dice la alarma en AWS, y hasta el
#     `apply` de `T-2.74` no lo dice nadie.


# ---------------------------------------------------------------------------
# 6 · El hueco H-2 se declara con el número que se puede contar
# ---------------------------------------------------------------------------
#
# `H-2` es un bloqueo de ENTREGA: el manual manda avisar a un teléfono de soporte
# que no existe. Dos documentos lo declaraban «unas 25 veces» / «~25 veces» y la
# cuenta real era **52 menciones, 36 de ellas la orden literal**. No es un desliz
# de redacción: es la exposición del hueco contada a menos de la mitad, y decide
# cuánto corre quien lo lee.
#
# Se torció por el motivo de siempre —un número tecleado a mano el día que se
# escribió, junto a un manual que siguió creciendo—, así que la corrección no es
# poner 52: es DERIVARLO. Misma doctrina que
# `test_la_cabecera_de_tasks_declara_el_conteo_real`.

MANUAL = REPO / "takab-docs" / "MANUAL-OPERACION-TAKAB.md"
PENDIENTES = REPO / "takab-docs" / "PENDIENTES-MAURICIO.md"

#: Cómo cita cada documento la cuenta. El grupo `n` es lo que se contrasta.
_CITAS_DE_SOPORTE = (
    (TASKS, r"«avisa a soporte» \*\*(?P<n>\d+) veces\*\*", "ordenes"),
    (TASKS, r"menciona a soporte \*\*(?P<n>\d+)\*\* en\s*\n?>?\s*total", "menciones"),
    (PENDIENTES, r"el manual cita \*\*(?P<n>\d+) veces\*\*", "menciones"),
    (PENDIENTES, r"(?P<n>\d+) de ellas como la orden literal", "ordenes"),
)


def _cuentas_del_manual() -> dict[str, int]:
    texto = MANUAL.read_text(encoding="utf-8")
    return {
        "menciones": len(re.findall(r"soporte", texto, re.I)),
        "ordenes": len(re.findall(r"avisa a soporte", texto, re.I)),
    }


def test_los_documentos_declaran_las_menciones_de_soporte_que_el_manual_tiene() -> None:
    real = _cuentas_del_manual()
    assert real["ordenes"] > 0, (
        "el manual ya no manda «avisa a soporte» ni una vez: si el hueco H-2 se cerró de "
        "verdad, retira también estas declaraciones y este test."
    )
    for doc, patron, clave in _CITAS_DE_SOPORTE:
        m = re.search(patron, doc.read_text(encoding="utf-8"))
        assert m is not None, (
            f"{doc.name} ya no declara las {clave} de soporte con la forma esperada "
            f"({patron!r}). El hueco H-2 se cita con un número contable, no con un «unas N»."
        )
        dicho = int(m.group("n"))
        assert dicho == real[clave], (
            f"{doc.name} dice {dicho} {clave} de soporte y el manual tiene {real[clave]}. "
            "H-2 es un bloqueo de entrega: contarlo por lo bajo hace que quien lo lea corra "
            "menos de lo que debería. Actualiza el número en el mismo commit que toque el manual."
        )
