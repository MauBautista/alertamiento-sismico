"""Fixtures compartidos — todo corre sin hardware (gpiozero MockFactory).

Además (T-2.63) contabiliza los tests que el `skipif` de alcanzabilidad del
Raspberry Shake puede apagar, y lo dice en voz alta al final de cada corrida:
un job verde que se saltó el gate #3 en silencio no debe poder leerse como
acreditación. Ver `tests/test_hardware_gates.py` para el registro y el porqué.
"""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Callable, Iterator
from pathlib import Path, PurePosixPath

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory
from takab_edge.config import EdgeSettings, load_settings


@pytest.fixture(autouse=True)
def mock_pin_factory() -> Iterator[None]:
    """Aísla el estado de pines por test con una MockFactory fresca."""
    previous = Device.pin_factory
    Device.pin_factory = MockFactory()
    try:
        yield
    finally:
        Device.pin_factory.reset()
        Device.pin_factory = previous


@pytest.fixture(autouse=True)
def cerrojo_de_pines_por_test(tmp_path: Path) -> Iterator[None]:
    """[T-2.70.a·D1.1] Cada test es un GABINETE distinto: su propio cerrojo.

    [T-2.70.a·D2/P2] Y su propio SOCKET, por la misma razón y en el mismo sitio:
    dos tests que compartieran el socket derivado de dev (uno por `gateway_id`,
    y casi todos usan `gw-dev-0001`) se pisarían el archivo si uno dejara un
    servidor vivo. Va aquí y no en un fixture nuevo a propósito — ver la trampa
    de `monkeypatch` documentada abajo: añadir un autouse cambia el orden de
    teardown y ya tumbó cinco tests de `test_pin_factory.py`.
    OJO con la longitud: `AF_UNIX` corta la ruta en ~108 bytes y el `tmp_path`
    de pytest ya gasta ~60; por eso el nombre del archivo es corto.

    El dueño de los pines toma un `flock` EXCLUSIVO sobre `gpio_lock_file` al
    arrancar, y `flock` colisiona **incluso entre dos descriptores del mismo
    proceso** (medido: `BlockingIOError`). Sin esto, todos los tests que no
    tocan `gateway_id` caerían en el MISMO cerrojo derivado de dev y el segundo
    controlador de cada corrida moriría.

    OJO — este fixture es también un PUNTO CIEGO, y ya escondió un defecto: con
    él puesto, la suite entera no mide nunca el arranque que ven `make edge` y
    `demo/gabinete.py`, que no tienen fixture ninguno. Los tests que lo apagan a
    propósito viven en `test_gpio_ownership.py` (sección B1) y son los que
    obligan a que el default derivado sea arrancable fuera del Pi.

    Va por ENTORNO y no sólo en el fixture `settings` a propósito: hay tests que
    construyen su config con `load_settings()`/`EdgeSettings()` por dentro
    (`test_config.py`, `test_dispatch.py`…) y subprocesos que la cargan de cero
    (`test_gpio_process.py`), y el entorno los alcanza a todos — `os.environ` se
    hereda. `tmp_path` es único por test, así que dos tests jamás se pisan; dos
    controladores DEL MISMO test sí comparten cerrojo, que es exactamente la
    semántica real (un gabinete, unos pines, un dueño).

    NO usa `monkeypatch` A PROPÓSITO, y es una trampa MEDIDA: pedirlo desde el
    primer fixture autouse adelanta la construcción de `monkeypatch` y con ella
    RETRASA su `undo()` hasta después del teardown de `mock_pin_factory`, que
    entonces encuentra una pin factory ajena (`_FakeLGPIO`, o `None`) y revienta
    en `.reset()`. Cinco tests de `test_pin_factory.py` cayeron así por añadir un
    fixture que no tiene nada que ver con pines. Guardar y restaurar el entorno a
    mano no toca ese orden.
    """
    rutas = {
        "TAKAB_EDGE_GPIO_LOCK_PATH": str(tmp_path / "gpio.lock"),
        "TAKAB_EDGE_GPIO_SOCKET_PATH": str(tmp_path / "g.sock"),
    }
    previos = {clave: os.environ.get(clave) for clave in rutas}
    os.environ.update(rutas)
    try:
        yield
    finally:
        for clave, previo in previos.items():
            if previo is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = previo


@pytest.fixture
def settings(tmp_path: Path) -> EdgeSettings:
    # Puerto 0 = efímero: el dashboard LAN no colisiona entre tests ni con servicios reales.
    # `gpio_lock_path` explícito además del entorno de arriba: quien lea este fixture
    # tiene que ver que el cerrojo de pines está aislado, sin ir a buscarlo.
    return load_settings().model_copy(
        update={
            "local_api_port": 0,
            "gpio_lock_path": str(tmp_path / "gpio.lock"),
            "gpio_socket_path": str(tmp_path / "g.sock"),
        }
    )  # dev_mode=True por defecto


@pytest.fixture
def supervisor(settings: EdgeSettings):
    """Supervisor construido y arrancado, sin fuente SeedLink automática."""
    from takab_edge.supervisor import EdgeSupervisor

    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.start()
    try:
        yield sup
    finally:
        sup.stop()


# ---------------------------------------------------------------------------
# Gate #3 · hardware: que el skip deje de ser mudo (T-2.63)
# ---------------------------------------------------------------------------
#
# El censo es ESTÁTICO (AST) a propósito: no importa los módulos gated, así que no
# vuelve a pagar la sonda de socket de `_reachable()` (0.6 s por archivo) y da el
# mismo resultado se colecten o no. Ver `tests/test_hardware_gates.py`.

_TESTS_DIR = Path(__file__).resolve().parent

#: Llamadas que delatan una sonda de alcanzabilidad de red.
#:
#: `urlopen`/`urlretrieve` están porque el ringserver del Shake también contesta por
#: HTTP: una sonda escrita con `urlopen` apaga exactamente el mismo gate que una de
#: socket, y la auditoría de F5 midió que esa forma devolvía `set()`.
_LLAMADAS_DE_RED = frozenset(
    {"create_connection", "connect", "connect_ex", "getaddrinfo", "urlopen", "urlretrieve"}
)

#: Sondas que sólo cuentan CON su módulo delante: `get` a secas es cualquier cosa,
#: `httpx.get` es una sonda al ringserver. Se comparan contra el nombre punteado.
#:
#: `subprocess.run(['nc', '-z', …])` queda FUERA a propósito y está documentado en
#: `test_formas_que_el_censo_AST_no_puede_ver`: `subprocess.run` aparece en
#: `test_local_api_panel.py` (lanza node) y en el propio archivo de gates, así que
#: tratarlo como red haría que el censo "acreditara" tests que no tocan el Shake.
_LLAMADAS_DE_RED_PUNTEADAS = frozenset(
    {
        "httpx.get",
        "httpx.head",
        "httpx.request",
        "httpx.Client",
        "requests.get",
        "requests.head",
        "requests.request",
        "requests.Session",
        "aiohttp.request",
    }
)

#: Nombres de marca que apagan un test por condición: pytest y unittest se escriben
#: casi igual y apagan exactamente lo mismo — sólo cambia una `I`.
_MARCAS_CONDICIONALES = frozenset({"skipif", "skipIf"})

#: Endpoint por defecto del Shake — los mismos valores que leen los módulos gated.
_SHAKE_HOST = os.environ.get("TAKAB_SHAKE_HOST", "192.168.3.92")
_SHAKE_PORT = os.environ.get("TAKAB_SHAKE_PORT", "18000")

_RE_ENDPOINT = re.compile(r"no alcanzable en (\S+)")
_RE_PARAMS = re.compile(r"\[.*\]$")

#: Olor textual a red — con LÍMITES de palabra: `\bconnect\b` no casa con "reconnects"
#: (y `\bhttp\b` tampoco casa con "httpx", por eso los clientes van nombrados aparte).
_RE_OLOR_DE_RED = re.compile(
    r"\b(?:socket|urllib|http|httpx|requests|aiohttp|" + "|".join(sorted(_LLAMADAS_DE_RED)) + r")\b"
)

#: Texto sin el cual un archivo NO puede apagar un test por condición. `allow_module_level`
#: está porque `pytest.skip(…, allow_module_level=True)` apaga el módulo entero sin
#: escribir jamás la palabra «skipif», y el atajo anterior lo daba por inofensivo.
_MARCADORES_DE_APAGADO = ("skipif", "skipIf", "allow_module_level")
#: `from X import …` / `from .X import …` sin parsear (el parse es lo caro).
_RE_FROM_IMPORT = re.compile(r"^\s*from\s+(\.*)([\w.]*)\s+import\b", re.MULTILINE)


def _nombre_llamado(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _nombre_punteado(func: ast.expr) -> str:
    """`httpx.get` a partir de `Attribute(Name('httpx'), 'get')`; "" si no es plano."""
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return ""


def _nombres_de_target(target: ast.expr) -> list[str]:
    """Nombres que ata UN target de asignación, desempaquetado incluido."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple | ast.List):
        return [nombre for elemento in target.elts for nombre in _nombres_de_target(elemento)]
    return []


def _nombres_asignados(nodo: ast.AST) -> set[str]:
    """Todo nombre que se ata en cualquier parte de `nodo` (para teñir un `try` entero)."""
    nombres: set[str] = set()
    for hijo in ast.walk(nodo):
        if isinstance(hijo, ast.Assign):
            for target in hijo.targets:
                nombres.update(_nombres_de_target(target))
        elif isinstance(hijo, ast.AnnAssign):
            nombres.update(_nombres_de_target(hijo.target))
    return nombres


class _Contexto:
    """Lo que hay que saber de UN archivo para leer sus `skipif` (F5).

    El censo original sólo reconocía la forma exacta de los dos archivos reales
    —sonda llamada dentro de la propia expresión del `skipif`—. La auditoría midió
    que `SHAKE_UP = _reachable(...)` + `skipif(not SHAKE_UP)`, que está a UNA línea
    de `test_signal_hardware.py`, devolvía `set()`: el gate se apagaba y el censo
    seguía diciendo «5/5». Por eso aquí hay tres vocabularios, no uno.
    """

    def __init__(
        self,
        alias: dict[str, str],
        llamables: set[str],
        valores: set[str],
        marcas: set[str],
    ) -> None:
        #: `from socket import create_connection as abrir` → {'abrir': 'create_connection'}
        self.alias = alias
        #: funciones que abren la conexión (`_reachable`, y quien la llame a su vez)
        self.llamables = llamables
        #: nombres cuyo VALOR sale de una sonda (`SHAKE_UP = _reachable(...)`)
        self.valores = valores
        #: alias de marca (`SIN_HW = pytest.mark.skipif(...)`) usados como `@SIN_HW`
        self.marcas = marcas


class _Inventario:
    """Todo lo que el censo necesita de un archivo, recogido en UNA sola pasada.

    Medido: con una función por vocabulario (alias, imports, llamadas, asignaciones)
    eran 4 recorridos completos del árbol más un punto fijo que volvía a recorrerlo,
    y el censo pasaba de 6.1 ms a 44 ms. Esta pasada única lo devuelve a ~7 ms. El
    punto fijo se hace después sobre el grafo de nombres, que ya no toca AST.
    """

    def __init__(self) -> None:
        #: nombre local → nombre original de cada `from X import a as b`
        self.alias: dict[str, str] = {}
        self.imports: list[ast.ImportFrom] = []
        #: función → nombres que llama (contando las funciones que la envuelven)
        self.llamadas: dict[str, set[str]] = {}
        #: `([nombres], valor)` de cada asignación, a cualquier profundidad
        self.asignaciones: list[tuple[list[str], ast.expr]] = []
        #: `try` completos: si en el `try` se abre una conexión, lo que sale de él
        #: (por el `except`) ES el veredicto de la sonda aunque nadie lo asigne.
        self.tries: list[ast.Try] = []


def _apuntar_asignacion(inv: _Inventario, targets: list[ast.expr], valor: ast.expr) -> None:
    """Anota una asignación emparejando elemento a elemento cuando se puede.

    `SHAKE_UP, ENDPOINT = _reachable(…), 'h:1'` empareja, y así `ENDPOINT` no queda
    teñido de sonda sin serlo; si las formas no casan, se tiñe el grupo entero (que
    es el lado seguro: el censo prefiere mirar de más que dejar un gate mudo).
    """
    if len(targets) == 1 and isinstance(targets[0], ast.Tuple | ast.List):
        elementos = targets[0].elts
        if isinstance(valor, ast.Tuple | ast.List) and len(valor.elts) == len(elementos):
            for elemento, sub_valor in zip(elementos, valor.elts, strict=True):
                _apuntar_asignacion(inv, [elemento], sub_valor)
            return
    nombres = [nombre for target in targets for nombre in _nombres_de_target(target)]
    if nombres:
        inv.asignaciones.append((nombres, valor))


def _inventariar(arbol: ast.Module) -> _Inventario:
    inv = _Inventario()

    def visitar(nodo: ast.AST, duenos: tuple[str, ...]) -> None:
        if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
            duenos = (*duenos, nodo.name)
            inv.llamadas.setdefault(nodo.name, set())
        elif isinstance(nodo, ast.Call):
            # El punteado sólo se anota si YA es una sonda conocida (`httpx.get`): si
            # no, el nombre a secas basta y el conjunto no engorda por cada `x.y()`.
            punteado = _nombre_punteado(nodo.func)
            nombre = (
                punteado if punteado in _LLAMADAS_DE_RED_PUNTEADAS else _nombre_llamado(nodo.func)
            )
            if nombre:
                for dueno in duenos:
                    inv.llamadas[dueno].add(nombre)
        elif isinstance(nodo, ast.ImportFrom):
            inv.imports.append(nodo)
            for entrada in nodo.names:
                inv.alias[entrada.asname or entrada.name] = entrada.name
        elif isinstance(nodo, ast.Assign):
            _apuntar_asignacion(inv, nodo.targets, nodo.value)
        elif isinstance(nodo, ast.AnnAssign):
            if nodo.value is not None:
                _apuntar_asignacion(inv, [nodo.target], nodo.value)
        elif isinstance(nodo, ast.Try):
            inv.tries.append(nodo)
        for hijo in ast.iter_child_nodes(nodo):
            visitar(hijo, duenos)

    visitar(arbol, ())
    return inv


def _es_llamada_de_red(nodo: ast.Call, ctx: _Contexto) -> bool:
    if _nombre_punteado(nodo.func) in _LLAMADAS_DE_RED_PUNTEADAS:
        return True
    nombre = _nombre_llamado(nodo.func)
    if not nombre:
        return False
    return ctx.alias.get(nombre, nombre) in _LLAMADAS_DE_RED or nombre in ctx.llamables


def _expr_usa_sonda(expr: ast.AST, ctx: _Contexto, *, cadenas: bool = False) -> bool:
    """¿La expresión toca la red, llama a una sonda o LEE un valor que salió de una?"""
    for nodo in ast.walk(expr):
        if isinstance(nodo, ast.Call) and _es_llamada_de_red(nodo, ctx):
            return True
        if isinstance(nodo, ast.Name) and nodo.id in ctx.valores:
            return True
        if cadenas and isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            # pytest EVALÚA `skipif("<expr>")` como código, así que el censo también
            # tiene que leerlo. Un `reason=` normal revienta el parse y se ignora solo.
            try:
                interno = ast.parse(nodo.value, mode="eval")
            except SyntaxError:
                continue
            if _expr_usa_sonda(interno, ctx):  # sin `cadenas`: un nivel basta y no cicla
                return True
    return False


def _ruta_de_modulo(modulo: str, nivel: int, ruta: Path, base: Path) -> Path | None:
    """Archivo del árbol de tests al que apunta un `from X import …`, si existe.

    Mudar la sonda a un helper (`from _sondas import shake_arriba`) la hacía invisible
    para el censo; el import es la única pista y hay que seguirla.
    """
    if not modulo:
        return None
    partes = modulo.split(".")
    if nivel:
        raices = [ruta.parents[nivel - 1]] if nivel <= len(ruta.parents) else []
    else:
        raices = [ruta.parent, base]
    for raiz in raices:
        candidato = raiz.joinpath(*partes).with_suffix(".py")
        if candidato.is_file() and candidato != ruta:
            return candidato
    return None


def _ruta_de_modulo_hermano(nodo: ast.ImportFrom, ruta: Path, base: Path) -> Path | None:
    return _ruta_de_modulo(nodo.module or "", nodo.level, ruta, base)


def _huele_a_red(fuente: str, ruta: Path, base: Path, vistos: set[Path], saltos: int = 2) -> bool:
    """Filtro TEXTUAL previo al parse: ¿puede este archivo gatear por red?

    Existe por coste medido, no por elegancia: `test_local_api_panel.py` tiene 1141
    líneas y un `skipif` de `node` — parsearlo e inventariarlo cuesta 12 ms de los
    24 que llegó a costar el censo entero. El filtro que había («`socket` no está en
    el texto») ERA parte del agujero: dejaba fuera `urlopen` y la sonda mudada a un
    módulo auxiliar. Éste usa límites de palabra (`\\bconnect\\b` NO casa con
    "reconnects", que es justo lo que aparece en ese archivo) y, si no huele a red,
    sigue los `from X import` hasta 2 saltos por si la sonda vive en el helper.
    """
    if _RE_OLOR_DE_RED.search(fuente):
        return True
    if saltos <= 0:
        return False
    for puntos, modulo in _RE_FROM_IMPORT.findall(fuente):
        origen = _ruta_de_modulo(modulo, len(puntos), ruta, base)
        if origen is None or origen in vistos:
            continue
        try:
            texto = origen.read_text(encoding="utf-8")
        except OSError:
            continue
        if _huele_a_red(texto, origen, base, vistos | {origen}, saltos - 1):
            return True
    return False


def _sondas_importadas(
    inv: _Inventario, ruta: Path, base: Path, vistos: set[Path]
) -> tuple[set[str], set[str]]:
    """`(invocables, valores)` locales que vienen de OTRO archivo del árbol.

    Los valores son la mitad que faltaba: del helper no siempre se importa la
    FUNCIÓN (`from _sondas import shake_arriba`), muchas veces se importa la
    constante ya resuelta (`from _sondas import SHAKE_UP`), y esa forma se escapaba.
    """
    invocables: set[str] = set()
    valores: set[str] = set()
    for nodo in inv.imports:
        origen = _ruta_de_modulo_hermano(nodo, ruta, base)
        if origen is None or origen in vistos:
            continue
        ajenas_invocables, ajenos_valores = _sondas_de_archivo(origen, base, vistos | {origen})
        for entrada in nodo.names:
            local = entrada.asname or entrada.name
            if entrada.name in ajenas_invocables:
                invocables.add(local)
            if entrada.name in ajenos_valores:
                valores.add(local)
    return invocables, valores


def _cerrar_sondas(inv: _Inventario, ctx: _Contexto) -> set[str]:
    """Funciones que acaban abriendo una conexión, directa o EN CADENA.

    Punto fijo sobre el grafo de llamadas ya inventariado: `def _shake_up(): return
    _reachable(...)` es una sonda tanto como `_reachable`, y el orden en que estén
    escritas no puede decidir si el censo las ve.
    """
    cambio = True
    while cambio:
        cambio = False
        for nombre, llamados in inv.llamadas.items():
            if nombre in ctx.llamables:
                continue
            if any(
                ctx.alias.get(llamado, llamado) in _LLAMADAS_DE_RED
                or llamado in _LLAMADAS_DE_RED_PUNTEADAS
                or llamado in ctx.llamables
                for llamado in llamados
            ):
                ctx.llamables.add(nombre)
                cambio = True
    return ctx.llamables


def _valores_de_sonda(inv: _Inventario, ctx: _Contexto) -> set[str]:
    """Nombres cuyo valor viene de una sonda — incluida la negación intermedia.

    Punto fijo por lo mismo que `_sondas_llamables`: `SIN_SHAKE = not SHAKE_UP`
    encadena, y el censo no puede depender de en qué línea se escribió cada cosa.

    Los `try` entran aquí porque hay una forma en que la sonda no devuelve nada a
    nadie: se abre el socket a pelo y el veredicto viaja por el flujo de control
    (`try: connect(); UP = True / except OSError: UP = False`). Ahí no hay ninguna
    asignación cuyo VALOR sea la sonda, así que se tiñe lo que el `try` decide.
    """
    # Los `try` se resuelven UNA vez y fuera del punto fijo: lo que los hace sonda es
    # que en el `try` haya una LLAMADA de red, y las llamadas ya están cerradas por
    # `_cerrar_sondas` antes de entrar aquí — no dependen de `ctx.valores`, que es lo
    # único que crece en el bucle. Dentro del bucle costaba ~14 ms medidos, porque
    # cada vuelta re-recorría el árbol de cada `try`.
    for nodo_try in inv.tries:
        if any(
            isinstance(hijo, ast.Call) and _es_llamada_de_red(hijo, ctx)
            for sentencia in nodo_try.body
            for hijo in ast.walk(sentencia)
        ):
            ctx.valores |= _nombres_asignados(nodo_try)

    cambio = True
    while cambio:
        cambio = False
        for nombres, valor in inv.asignaciones:
            pendientes = [n for n in nombres if n not in ctx.valores]
            if pendientes and _expr_usa_sonda(valor, ctx):
                ctx.valores.update(pendientes)
                cambio = True
    return ctx.valores


def _skipif_usa_sonda(expr: ast.expr, ctx: _Contexto) -> bool:
    """¿La expresión contiene un `…skipif(<condición que depende de una sonda>)`?

    `unittest.skipIf` cuenta igual: apaga el mismo test por la misma razón y sólo se
    escribe con una `I` — un `TestCase` con esa marca dejaba el gate mudo.
    """
    for nodo in ast.walk(expr):
        if isinstance(nodo, ast.Call) and _nombre_llamado(nodo.func) in _MARCAS_CONDICIONALES:
            if _expr_usa_sonda(nodo, ctx, cadenas=True):
                return True
    return False


def _skip_de_modulo_entero(nodo: ast.If, ctx: _Contexto) -> bool:
    """`if not <sonda>: pytest.skip(…, allow_module_level=True)` — apaga el archivo.

    No lleva la palabra «skipif» en ninguna parte, así que ni el atajo textual ni el
    recorrido de decoradores lo veían. Se exige que la CONDICIÓN dependa de una sonda:
    un `pytest.skip` por versión de Python no es un gate de hardware.
    """
    if not _expr_usa_sonda(nodo.test, ctx, cadenas=True):
        return False
    for hijo in ast.walk(nodo):
        if (
            isinstance(hijo, ast.Call)
            and _nombre_llamado(hijo.func) == "skip"
            and any(clave.arg == "allow_module_level" for clave in hijo.keywords)
        ):
            return True
    return False


def _es_marca_gated(expr: ast.expr, ctx: _Contexto) -> bool:
    """Un `skipif` inline O un alias de marca (`@SIN_HW`, `pytestmark = [SIN_HW]`)."""
    if _skipif_usa_sonda(expr, ctx):
        return True
    return any(isinstance(n, ast.Name) and n.id in ctx.marcas for n in ast.walk(expr))


def _cuerpos_hijos(nodo: ast.stmt, prefijo: tuple[str, ...]):
    """Bloques donde pytest SIGUE colectando tests, con el prefijo de id que les toca."""
    if isinstance(nodo, ast.ClassDef):
        if nodo.name.startswith("Test"):
            yield nodo.body, (*prefijo, nodo.name)
    elif isinstance(nodo, ast.If):
        yield nodo.body, prefijo
        yield nodo.orelse, prefijo
    elif isinstance(nodo, ast.Try):
        yield nodo.body, prefijo
        yield nodo.orelse, prefijo
        yield nodo.finalbody, prefijo
        for manejador in nodo.handlers:
            yield manejador.body, prefijo


def _ids_de_tests(cuerpo: list[ast.stmt], archivo: str, prefijo: tuple[str, ...]) -> set[str]:
    """Todos los ids de test que pytest colectaría bajo `cuerpo`."""
    ids: set[str] = set()
    for nodo in cuerpo:
        if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef) and nodo.name.startswith(
            "test"
        ):
            ids.add("::".join((archivo, *prefijo, nodo.name)))
        for sub_cuerpo, sub_prefijo in _cuerpos_hijos(nodo, prefijo):
            ids |= _ids_de_tests(sub_cuerpo, archivo, sub_prefijo)
    return ids


def _es_pytestmark(nodo: ast.stmt) -> bool:
    if isinstance(nodo, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in nodo.targets)
    if isinstance(nodo, ast.AnnAssign):
        return isinstance(nodo.target, ast.Name) and nodo.target.id == "pytestmark"
    return False


def _gates_en_cuerpo(
    cuerpo: list[ast.stmt], archivo: str, prefijo: tuple[str, ...], ctx: _Contexto
) -> set[str]:
    """Ids apagados por un `skipif` de red dentro de `cuerpo` (recursivo).

    Recursivo y no `arbol.body`: el decorador puede estar en un MÉTODO, y entonces el
    id lleva el nombre de la clase — por eso se arrastra `prefijo` en vez de usar
    `ast.walk` a secas, que ve el nodo pero pierde de quién cuelga.
    """
    for nodo in cuerpo:
        # 1) `pytestmark = …skipif(…)` → apaga TODO lo que cuelgue de este cuerpo
        #    (módulo entero, o la clase si el `pytestmark` está dentro de ella).
        if _es_pytestmark(nodo):
            valor = getattr(nodo, "value", None)
            if valor is not None and _es_marca_gated(valor, ctx):
                return _ids_de_tests(cuerpo, archivo, prefijo)
        # 1 bis) `if not <sonda>: pytest.skip(…, allow_module_level=True)` → lo mismo,
        #        pero sin escribir «skipif» en ningún sitio.
        if isinstance(nodo, ast.If) and _skip_de_modulo_entero(nodo, ctx):
            return _ids_de_tests(cuerpo, archivo, prefijo)

    ids: set[str] = set()
    for nodo in cuerpo:
        # 2) decorador sobre un test, un método o una clase → apaga sólo eso.
        if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and any(
            _es_marca_gated(dec, ctx) for dec in nodo.decorator_list
        ):
            ids |= _ids_de_tests([nodo], archivo, prefijo)
            continue
        for sub_cuerpo, sub_prefijo in _cuerpos_hijos(nodo, prefijo):
            ids |= _gates_en_cuerpo(sub_cuerpo, archivo, sub_prefijo, ctx)
    return ids


def _contexto_del_archivo(inv: _Inventario, ruta: Path, base: Path, vistos: set[Path]) -> _Contexto:
    ctx = _Contexto(alias=inv.alias, llamables=set(), valores=set(), marcas=set())
    invocables, valores = _sondas_importadas(inv, ruta, base, vistos)
    ctx.llamables |= invocables
    ctx.valores |= valores
    _cerrar_sondas(inv, ctx)
    _valores_de_sonda(inv, ctx)
    ctx.marcas = {
        nombre
        for nombres, valor in inv.asignaciones
        for nombre in nombres
        if _skipif_usa_sonda(valor, ctx)
    }
    return ctx


def _sondas_de_archivo(ruta: Path, base: Path, vistos: set[Path]) -> tuple[set[str], set[str]]:
    """`(invocables, valores)` de un módulo auxiliar: quién sondea y qué guarda el veredicto.

    Las dos mitades salen de UN solo parse a propósito: leer el helper dos veces (una
    por las funciones y otra por las constantes) doblaba el coste del salto.
    """
    try:
        inv = _inventariar(ast.parse(ruta.read_text(encoding="utf-8")))
    except (OSError, SyntaxError):
        return set(), set()
    ctx = _Contexto(alias=inv.alias, llamables=set(), valores=set(), marcas=set())
    invocables, valores = _sondas_importadas(inv, ruta, base, vistos)
    ctx.llamables |= invocables
    ctx.valores |= valores
    _cerrar_sondas(inv, ctx)
    _valores_de_sonda(inv, ctx)
    return ctx.llamables, ctx.valores


def _gates_del_archivo(ruta: Path, base: Path) -> set[str]:
    fuente = ruta.read_text(encoding="utf-8")
    # Dos atajos baratos antes del parse: sin nada que apague un test no hay gate, y
    # sin olor a red tampoco (ver `_huele_a_red` — sigue los imports, así que la sonda
    # mudada a un helper ya no se escapa por aquí).
    if not any(marca in fuente for marca in _MARCADORES_DE_APAGADO) or not _huele_a_red(
        fuente, ruta, base, {ruta}
    ):
        return set()
    arbol = ast.parse(fuente)
    ctx = _contexto_del_archivo(_inventariar(arbol), ruta, base, {ruta})
    if not (ctx.llamables or ctx.valores or ctx.marcas or ctx.alias.keys() & _LLAMADAS_DE_RED):
        return set()
    return _gates_en_cuerpo(arbol.body, ruta.relative_to(base).as_posix(), (), ctx)


def censar_gates_de_socket(directorio: Path | None = None) -> set[str]:
    """Ids de todos los tests que un `skipif` de alcanzabilidad de red puede apagar.

    Formato del id: `[subdir/]archivo.py::test_x` (o `…::TestClase::test_x`), relativo
    al directorio censado y por tanto estable frente a desde dónde se invoque pytest.
    """
    base = Path(directorio) if directorio is not None else _TESTS_DIR
    ids: set[str] = set()
    # `rglob`, no `glob`: un `tests/hardware/test_x.py` es exactamente igual de capaz
    # de apagar el gate #3, y con `glob` no existía para el censo.
    #
    # Los DOS patrones de `python_files` (por defecto `test_*.py *_test.py`, y
    # `edge/pyproject.toml` no lo pisa): un `shake_hardware_test.py` lo COLECTA pytest
    # y el censo no lo miraba siquiera. Un solo recorrido filtrando por nombre, no dos
    # `rglob`: recorrer el árbol dos veces costaba más que el filtro.
    for ruta in sorted(base.rglob("*.py")):
        nombre = ruta.name
        if nombre.startswith("test_") or nombre.endswith("_test.py"):
            ids |= _gates_del_archivo(ruta, base)
    return ids


def construir_resumen_gate(
    *, total: int, seleccionados: int, saltados: int, endpoint: str | None
) -> str:
    """Línea de cierre del gate #3. NUNCA pone el job en rojo: sólo lo hace innegable."""
    if total == 0:
        return ""
    destino = endpoint or f"{_SHAKE_HOST}:{_SHAKE_PORT}"
    if seleccionados == 0:
        return (
            f"GATE #3 (hardware): 0/{total} SELECCIONADOS en esta corrida — "
            "esta suite NO acredita el gate #3."
        )
    if saltados == 0 and seleccionados == total:
        return f"GATE #3 (hardware): {total}/{total} EJECUTADOS contra el Shake real."
    if saltados == total:
        return (
            f"GATE #3 (hardware): {total}/{total} tests SALTADOS — Shake no alcanzable "
            f"en {destino}. Esta suite NO acredita el gate #3."
        )
    return (
        f"GATE #3 (hardware): {saltados}/{total} SALTADOS y {seleccionados - saltados}/{total} "
        f"ejecutados ({seleccionados}/{total} seleccionados; Shake en {destino}). "
        "Esta suite NO acredita el gate #3 completo."
    )


def _id_corto(nodeid: str) -> str:
    """`tests/test_x.py::test_y[param]` → `test_x.py::test_y`.

    Recorta hasta el último componente `tests/`, NO al nombre de archivo: desde que el
    censo baja a los subdirectorios (`rglob`), `tests/hardware/test_x.py` tiene que
    seguir cruzándose con el id censado `hardware/test_x.py`.
    """
    partes = str(nodeid).split("::")
    if not partes:
        return nodeid
    trozos = PurePosixPath(partes[0].replace("\\", "/")).parts
    if "tests" in trozos:
        trozos = trozos[len(trozos) - trozos[::-1].index("tests") :]
    partes[0] = "/".join(trozos)
    partes[-1] = _RE_PARAMS.sub("", partes[-1])
    return "::".join(partes)


def contar_gates_en_stats(
    stats: dict[str, list], gated: set[str]
) -> tuple[set[str], set[str], str | None]:
    """`(vistos, saltados, endpoint)` de los tests gated, leídos de los REPORTES.

    Se cuenta desde los reportes y no desde la colección para que el conteo sobreviva
    a `-k` y a pytest-xdist (el controlador recibe los reportes de los workers, pero
    no su estado de colección). Equivocarse hacia arriba es lo peligroso: diría
    «5/5 EJECUTADOS» sin haber tocado el Shake.

    Por eso el discriminante es `when`, que sólo tienen los reportes: `stats` también
    guarda ITEMS bajo `deselected` (un test que `-k` apagó y JAMÁS corrió) y objetos
    de warning sin `nodeid`.
    """
    vistos: set[str] = set()
    saltados: set[str] = set()
    endpoint: str | None = None
    for categoria, entradas in stats.items():
        for entrada in entradas:
            if not hasattr(entrada, "when"):  # item deseleccionado o warning, no reporte
                continue
            corto = _id_corto(getattr(entrada, "nodeid", "") or "")
            if corto not in gated:
                continue
            vistos.add(corto)
            if categoria != "skipped":
                continue
            saltados.add(corto)
            if endpoint is None:
                hallado = _RE_ENDPOINT.search(str(getattr(entrada, "longrepr", "")))
                endpoint = hallado.group(1) if hallado else None
    return vistos, saltados, endpoint


# ---------------------------------------------------------------------------
# Capa 2 · la red que no depende de la sintaxis (F5)
# ---------------------------------------------------------------------------
#
# El censo de arriba es reconocimiento de PATRONES: reduce el agujero, no lo cierra.
# La auditoría de F5 midió 8 formas de escribir el mismo gate que el censo original
# no veía; se cerraron, pero siempre habrá una novena — y hay formas que ningún AST
# puede ver, como `pytest.skip()` llamado en caliente dentro del cuerpo o desde un
# fixture.
#
# Esta segunda red no mira código: mira los REPORTES de la corrida. Cada test saltado
# tiene que estar DECLARADO (archivo + motivo); cualquier otro pone el build en rojo.
# Es syntax-agnostic por construcción y cumple las tres condiciones del encargo:
#
#   (a) un skip nuevo sin declarar rompe el build — código de salida 1, que es lo
#       único que CI mira (imprimir no rompe nada: ese fue el fallo de T-2.58);
#   (b) lo declarado pasa en verde, así que no es un freno de mano;
#   (c) el veredicto NO depende del hardware: lo declarado PUEDE saltarse, no TIENE
#       que saltarse. Por eso no se compara contra un número esperado de skips —
#       "5 saltados" en CI y "0 saltados" en el gabinete son ambos correctos.


class SkipDeclarado:
    """Permiso explícito para que UN archivo se salte por UN motivo concreto.

    Con `ids`, el permiso además es NOMINAL: sólo esos tests pueden acogerse a él.
    Sin `ids`, vale para todo el archivo (es lo que toca cuando el skip apaga un
    módulo entero y la lista sería la de todos sus tests, como el panel con `node`).
    """

    def __init__(self, archivo: str, motivo: str, porque: str, ids: tuple[str, ...] = ()) -> None:
        self.archivo = archivo
        self.motivo = re.compile(motivo)
        self.porque = porque
        #: sub-ids (`test_x`, o `TestClase::test_x`) con permiso nominal; () = todos.
        self.ids = ids

    def casa(self, id_corto: str, motivo: str) -> bool:
        partes = id_corto.split("::")
        if partes[0] != self.archivo or not self.motivo.search(motivo):
            return False
        return not self.ids or "::".join(partes[1:]) in self.ids


#: Los ÚNICOS skips que esta suite tiene permitido tener.
#:
#: El archivo forma parte de la declaración a propósito: copiar el `skipif` del Shake
#: a un `test_gpio_hardware.py` nuevo —escrito de una forma que el censo AST no
#: reconozca— es exactamente el agujero que quedaba abierto, y aquí no cuela.
#:
#: Los dos archivos del gate #3 van además NOMINADOS (`ids`) porque si no quedaba un
#: hueco JUSTO ENTRE LAS DOS CAPAS: un sexto test añadido a `test_signal_hardware.py`
#: con un `skipif` escrito de una forma que el AST no reconoce dejaba mudas a las dos
#: a la vez — la capa 1 seguía censando 5 y su test de igualdad pasaba, y la capa 2 lo
#: daba por declarado porque el archivo y el motivo eran los de siempre.
#: `test_hardware_gates.py` cruza esta lista contra `GATES_HARDWARE` para que no
#: puedan divergir.
SKIPS_DECLARADOS: tuple[SkipDeclarado, ...] = (
    SkipDeclarado(
        archivo="test_signal_hardware.py",
        motivo=r"Raspberry Shake no alcanzable en \S+ \(gate #3 hardware\)",
        porque="gate #3: valida features contra traza REAL; sin Shake no hay traza.",
        ids=(
            "test_features_algorithm_matches_obspy_on_real_trace",
            "test_compute_features_on_real_packet_is_sane",
        ),
    ),
    SkipDeclarado(
        archivo="test_seedlink_hardware.py",
        motivo=r"Raspberry Shake no alcanzable en \S+ \(gate #3 hardware\)",
        porque="G-03: 100 sps, lag y resume por seqnum sólo se miden contra el Shake.",
        ids=(
            "test_real_shake_streams_100sps",
            "test_lag_del_shake_llega_a_ser_bajo",
            "test_real_shake_backfills_via_seqnum_resume",
        ),
    ),
    SkipDeclarado(
        archivo="test_local_api_panel.py",
        motivo=r"node no está en el PATH",
        porque=(
            "el panel se renderiza con node; CI lo instala y lo verifica con "
            "`node --version` desde T-2.58, así que aquí saltar es la excepción."
        ),
    ),
)


def _motivo_del_skip(reporte: object) -> str:
    """Texto del `reason` de un reporte saltado.

    `longrepr` de un skip es la tupla `(archivo, línea, "Skipped: <motivo>")`; de un
    `pytest.skip()` en caliente, la misma forma. Se normaliza para poder declararlo.
    """
    longrepr = getattr(reporte, "longrepr", "")
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        texto = str(longrepr[2])
    else:
        texto = str(longrepr)
    return texto.removeprefix("Skipped: ").strip()


def skips_no_declarados(stats: dict[str, list]) -> list[tuple[str, str]]:
    """`(id, motivo)` de cada test saltado que NADIE declaró. Vacío = todo en regla.

    Se lee de `stats["skipped"]`: `xfailed` tiene su propia categoría y no es un skip.
    Los parametrizados colapsan a un id corto para que 67 casos del panel no impriman
    67 líneas idénticas.
    """
    huerfanos: set[tuple[str, str]] = set()
    for reporte in stats.get("skipped", []):
        if not hasattr(reporte, "when"):  # item deseleccionado o warning, no reporte
            continue
        corto = _id_corto(getattr(reporte, "nodeid", "") or "")
        motivo = _motivo_del_skip(reporte)
        if any(declarado.casa(corto, motivo) for declarado in SKIPS_DECLARADOS):
            continue
        huerfanos.add((corto, motivo))
    return sorted(huerfanos)


# ---------------------------------------------------------------------------
# [T-2.70.a·D2/P2] Censo de VARIANTES COLECTADAS (guarda de conformidad)
# ---------------------------------------------------------------------------
#
# `tests/test_gpio_conformance.py` exige que TODO test suyo corra contra las dos
# costuras. La guarda original leía `inspect.signature(...)` sobre las funciones
# del módulo, y una firma no sabe distinguir «pide el fixture» de «lo pisa»: un
# `@parametrize("enlace", [...])` que SOMBREA el fixture aparecía conforme y
# jamás instanciaba las variantes `local`/`ipc`; y un método dentro de una clase
# `TestX` no era `inspect.isfunction`, así que ni se miraba. Con esas dos vías
# coladas: 62 passed y la guarda muda.
#
# Esto mide lo que pytest COLECTÓ de verdad. Va en `pytest_itemcollected` —no en
# `pytest_collection_modifyitems`— porque ese hook corre ANTES de la deselección
# por `-k`/`-m`: el censo es el mismo se filtre la corrida o no.

#: `{nombre del test: {variante del fixture `enlace` observada, …}}` por módulo.
VARIANTES_COLECTADAS: dict[str, dict[str, set]] = {}

#: Marca del ítem que no lleva parámetro `enlace` ninguno. Un objeto propio y no
#: `None`, que es un valor que alguien podría parametrizar de verdad.
SIN_ENLACE = "«sin el fixture `enlace`»"


def pytest_itemcollected(item) -> None:  # noqa: ANN001 — firma del hook
    """Anota, por módulo y test, con qué variante de `enlace` se colectó cada ítem."""
    try:
        modulo = item.nodeid.split("::", 1)[0].rsplit("/", 1)[-1]
        nombre = getattr(item, "originalname", None) or item.name.split("[", 1)[0]
        params = getattr(getattr(item, "callspec", None), "params", {}) or {}
        variante = params.get("enlace", SIN_ENLACE)
        if not isinstance(variante, (str, int, float, bool, type(None))):
            variante = repr(variante)  # una variante inhashable no puede tumbar la colección
        VARIANTES_COLECTADAS.setdefault(modulo, {}).setdefault(nombre, set()).add(variante)
    except Exception:  # noqa: BLE001 — un censo jamás impide colectar la suite
        return


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001 — firma del hook
    """Pone la corrida en ROJO si se saltó algo que nadie declaró.

    Aquí y no en `pytest_terminal_summary` porque el resumen sólo IMPRIME: `wrap_session`
    devuelve `session.exitstatus` justo después de llamar a este hook, así que éste es
    el punto donde un skip mudo puede dejar de ser un job verde. Sólo escala desde 0:
    si la corrida ya estaba roja, no se le pisa el motivo original.
    """
    try:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is None or not skips_no_declarados(reporter.stats):
            return
        if session.exitstatus == 0:
            session.exitstatus = 1
    except Exception:  # nunca reventar por la guardia
        return


def pytest_terminal_summary(terminalreporter) -> None:
    """Cierre de cada corrida: cuántos gates de hardware se apagaron, con nombre.

    `terminalreporter` va sin anotar a propósito: su tipo vive en `_pytest.terminal`,
    que es privado.
    """
    try:
        gated = censar_gates_de_socket()
        vistos, saltados, endpoint = contar_gates_en_stats(terminalreporter.stats, gated)
        linea = construir_resumen_gate(
            total=len(gated),
            seleccionados=len(vistos),
            saltados=len(saltados),
            endpoint=endpoint,
        )
        if linea:
            acreditado = "EJECUTADOS" in linea
            terminalreporter.write_line(linea, bold=True, green=acreditado, yellow=not acreditado)

        huerfanos = skips_no_declarados(terminalreporter.stats)
        if not huerfanos:
            return
        terminalreporter.write_line(
            f"SKIP NO DECLARADO: {len(huerfanos)} test(s) se saltaron sin permiso "
            "(corrida en ROJO, código de salida 1):",
            bold=True,
            red=True,
        )
        for corto, motivo in huerfanos:
            terminalreporter.write_line(f"  - {corto} — {motivo}", red=True)
        terminalreporter.write_line(
            "Declara cada uno en SKIPS_DECLARADOS (tests/conftest.py) diciendo POR QUÉ "
            "puede saltarse, o quítale el skip.",
            red=True,
        )
    except Exception:  # el resumen jamás puede tumbar una corrida
        return


@pytest.fixture(scope="session")
def censo_gates_hardware() -> set[str]:
    """Censo real de la suite `edge` (lo que hay HOY en `tests/`)."""
    return censar_gates_de_socket()


@pytest.fixture(scope="session")
def escanear_gates_socket() -> Callable[..., set[str]]:
    """El escáner en crudo, para probarlo contra árboles de mentira (`tmp_path`)."""
    return censar_gates_de_socket


@pytest.fixture(scope="session")
def skips_huerfanos() -> Callable[..., list[tuple[str, str]]]:
    """El clasificador de la capa 2, para probarlo con reportes de mentira."""
    return skips_no_declarados


@pytest.fixture(scope="session")
def skips_declarados() -> tuple[SkipDeclarado, ...]:
    return SKIPS_DECLARADOS


@pytest.fixture(scope="session")
def resumen_gate_hardware() -> Callable[..., str]:
    return construir_resumen_gate


@pytest.fixture(scope="session")
def contar_gates_hardware() -> Callable[..., tuple[set[str], set[str], str | None]]:
    return contar_gates_en_stats
