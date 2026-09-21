"""T-7.26 · El glosario de motivos cubre TODOS los motivos, y el sufijo no miente.

El glosario de `narrative/base.py` nació diciendo que los motivos viven juntos «para
que los tests los citen por su nombre en vez de por un trozo de frase que se
desincroniza al primer retoque de redacción». **Cubría la mitad.** Los tres que produce
`openrouter.py` —el camino que corre en producción— seguían siendo literales sueltos,
con otra ortografía y sin `SUFIJO_DETERMINISTA`, y los tests los citaban justamente por
un trozo de frase. Resultado medido en el papel, con las dos vías de degradación sobre
el mismo modelo:

    vía build_narrative:      'el proveedor de redacción falló (RuntimeError); texto determinista'
    vía OpenRouterProvider:   'el proveedor no respondió (HTTPStatusError)'     ← sin sufijo

Dos vocabularios para el mismo hecho en un documento que sale ante Protección Civil.

Lo que este fichero fija, y por qué cada cosa:

1. **Ningún motivo se teclea en el sitio.** Se comprueba sobre el AST de los módulos,
   no con un censo enumerado a mano — enumerar a mano es exactamente cómo se llegó a
   «la mitad». La guarda trae su propio control positivo: si el detector dejara de
   detectar, se pondría roja sola.

   ⚠️ **2ª vuelta: el detector prometía en su nombre más de lo que medía.** Solo veía
   el literal cuando era ARGUMENTO DIRECTO, así que bastaba una variable de por medio
   para evadirlo entero — medido: con la frase del glosario tecleada a mano una línea
   antes y pasada por variable, `_motivos_tecleados` devolvía `[]`. Un censo que se
   esquiva moviendo una cadena a una variable no es un censo. Hoy sigue los NOMBRES por
   el árbol, con sus ámbitos y sus parámetros, y la misma evasión lo pone rojo
   (`test_el_detector_NO_SE_EVADE_...`, parametrizado con las dos formas medidas).
2. **El sufijo «; texto determinista» dice la verdad** también por el camino del
   proveedor remoto (el de `TRAMOS` lo cubre por el otro lado).
3. **La causa es un código, nunca una frase ni un mensaje ajeno.** Es la regla que
   `motivo_con_causa` tiene escrita y que una rama incumplía.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from takab_api.narrative import base
from takab_api.narrative.base import (
    MOTIVO_GUARDRAIL,
    MOTIVO_PROVEEDOR_MUDO,
    MOTIVO_RESPUESTA_ILEGIBLE,
    SUFIJO_DETERMINISTA,
    NarrativeRequest,
    motivo_con_causa,
)
from takab_api.narrative.openrouter import (
    CODIGO_SECRETO_SIN_CLAVE,
    OpenRouterProvider,
    resolve_api_key,
)
from takab_api.narrative.prompts import SECTION_TITLES
from takab_api.narrative.redact import facts_from
from takab_api.settings import Settings
from tests.dictamen.test_pdf import model
from tests.narrative.test_redact import BASIS

_PAQUETE = Path(base.__file__).parent
#: `base.py` es el glosario: es el único sitio donde una frase de motivo es un literal.
_GLOSARIO = "base.py"

#: Dónde puede aterrizar un motivo. Son las dos puertas por las que una razón de
#: degradación llega a `Narrative.degraded_reason` y de ahí al §16 del PDF.
_PUERTAS = ("_degradar", "_degraded")
_CAMPO = "degraded_reason"

#: Nodos que abren ámbito propio. `_nodos_del_ambito` los devuelve pero no entra en
#: ellos: cada función se recorre con su propio diccionario de nombres, porque un
#: parámetro llamado `reason` NO es una frase tecleada aunque el módulo tenga arriba
#: otro `reason = "…"` que sí lo sea.
_AMBITOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

#: Una cadena es PROSA si tiene alguna letra. `f"{MOTIVO_X} ({causa})"` no teclea
#: ninguna frase —solo paréntesis y un espacio— y es justo como `narrative/__init__.py`
#: compone los dos motivos que no pueden llevar el sufijo. Exigir letras es lo que
#: separa «componer con el glosario» de «escribir una frase nueva aquí».
_PROSA = re.compile(r"[^\W\d_]")


def _nodos_del_ambito(cuerpo: list[ast.stmt]) -> Iterator[ast.AST]:
    """Todos los nodos de este ámbito, SIN descender a los ámbitos anidados.

    Los anidados salen igual —hay que recorrerlos aparte, con sus parámetros— pero no
    se abren aquí.
    """
    pendientes: list[ast.AST] = list(cuerpo)
    while pendientes:
        nodo = pendientes.pop()
        yield nodo
        if not isinstance(nodo, _AMBITOS):
            pendientes.extend(ast.iter_child_nodes(nodo))


def _posicion(nodo: ast.AST) -> tuple[int, int]:
    return (getattr(nodo, "lineno", 0), getattr(nodo, "col_offset", 0))


def _parametros(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    a = fn.args
    nombres = {p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)}
    return nombres | {p.arg for p in (a.vararg, a.kwarg) if p is not None}


def _es_frase(nodo: ast.AST, tecleados: set[str]) -> bool:
    """¿Esta expresión es una frase TECLEADA en este módulo?

    Lo es el literal con letras, lo es la f-string que aporte prosa propia
    (`f"guardrail: {x}"` es una frase con un hueco), lo es la concatenación o el método
    de cadena de cualquiera de los dos… **y lo es un nombre que este mismo módulo ató a
    una de esas cosas**. Eso último es lo que faltaba.

    Lo que NO es una frase: un nombre importado del glosario, un parámetro, un atributo
    ajeno, el resultado de `motivo_con_causa`/`motivo_guardrail` — y una f-string que
    solo aporte separadores (`f"{MOTIVO_X} ({causa})"`), porque ahí la prosa sigue
    viniendo del glosario y sigue siendo citable por su nombre.
    """
    if isinstance(nodo, ast.Constant):
        return isinstance(nodo.value, str) and bool(_PROSA.search(nodo.value))
    if isinstance(nodo, ast.JoinedStr):
        return any(_es_frase(parte, tecleados) for parte in nodo.values)
    if isinstance(nodo, ast.FormattedValue):
        return _es_frase(nodo.value, tecleados)
    if isinstance(nodo, ast.Name):
        return nodo.id in tecleados
    if isinstance(nodo, ast.BinOp):  # "a" + X  ·  "a %s" % X
        return _es_frase(nodo.left, tecleados) or _es_frase(nodo.right, tecleados)
    if isinstance(nodo, ast.Attribute):  # "a".upper  ·  motivo.removesuffix
        return _es_frase(nodo.value, tecleados)
    if isinstance(nodo, ast.Call):  # "a".format(x)  ·  motivo.removesuffix(s)
        return isinstance(nodo.func, ast.Attribute) and _es_frase(nodo.func, tecleados)
    if isinstance(nodo, ast.IfExp):  # frase if cond else otra
        return _es_frase(nodo.body, tecleados) or _es_frase(nodo.orelse, tecleados)
    if isinstance(nodo, ast.BoolOp):  # x or "frase"
        return any(_es_frase(v, tecleados) for v in nodo.values)
    return False


def _recorrer(cuerpo: list[ast.stmt], heredados: set[str], hallazgos: list) -> None:
    """Un ámbito: primero qué nombres quedan atados a una frase, después las puertas.

    La primera pasada va **en orden de fichero**: quien manda es la ÚLTIMA atadura, que
    es la que va a estar viva en la puerta. Al revés, un `motivo = fila[...]` posterior
    quedaría tapado por la frase muerta de arriba y el censo marcaría de más.
    """
    tecleados = set(heredados)
    for nodo in sorted(_nodos_del_ambito(cuerpo), key=_posicion):
        if isinstance(nodo, ast.Assign):
            destinos, valor = nodo.targets, nodo.value
        elif isinstance(nodo, ast.AnnAssign):
            destinos, valor = [nodo.target], nodo.value
        else:
            continue
        for destino in destinos:
            if not isinstance(destino, ast.Name):
                continue
            if valor is not None and _es_frase(valor, tecleados):
                tecleados.add(destino.id)
            else:
                # Reasignar a algo que no es prosa DESATA el nombre: si el módulo hace
                # `motivo = fila["degraded_reason"]`, ya no es una frase tecleada aquí.
                tecleados.discard(destino.id)

    for nodo in _nodos_del_ambito(cuerpo):
        if isinstance(nodo, ast.Call):
            objetivo = nodo.func
            nombre = getattr(objetivo, "attr", None) or getattr(objetivo, "id", None)
            if nombre in _PUERTAS and len(nodo.args) >= 2 and _es_frase(nodo.args[1], tecleados):
                hallazgos.append((nodo.lineno, ast.unparse(nodo.args[1])[:70]))
            for kw in nodo.keywords:
                if kw.arg == _CAMPO and _es_frase(kw.value, tecleados):
                    hallazgos.append((nodo.lineno, ast.unparse(kw.value)[:70]))
        elif isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
            # Los parámetros SOMBREAN: `def _degraded(self, req, reason)` recibe un
            # nombre que no es prosa aunque arriba haya otro igual que sí lo sea.
            _recorrer(nodo.body, tecleados - _parametros(nodo), hallazgos)
        elif isinstance(nodo, ast.ClassDef):
            _recorrer(nodo.body, tecleados, hallazgos)


def _motivos_tecleados(fuente: str) -> list[tuple[int, str]]:
    """Los motivos escritos en el sitio en vez de declarados con nombre, con su línea.

    Mira el AST y no el texto: un `grep` de comillas caza los comentarios, los
    docstrings y las cadenas de cualquier otra cosa. Lo que se busca es concreto —lo que
    acaba en `degraded_reason`— y eso solo lo sabe el árbol.

    ⚠️ Y lo sigue **por los nombres**, que es donde la primera versión no llegaba: solo
    veía el literal cuando era ARGUMENTO DIRECTO, así que bastaba una variable de por
    medio para evadir el censo entero. Medido antes de tocarlo: con la frase tecleada
    una línea antes y pasada por variable, `_motivos_tecleados` devolvía `[]`. Un censo
    que se esquiva moviendo una cadena a una variable no es un censo, y su nombre —«ningún
    motivo se teclea FUERA del glosario»— prometía justamente lo que no medía.
    """
    hallazgos: list[tuple[int, str]] = []
    _recorrer(ast.parse(fuente).body, set(), hallazgos)
    return sorted(hallazgos)


def test_el_detector_DETECTA(  # el control positivo de la guarda de abajo
) -> None:
    """Sin esto, un detector roto pasaría por un módulo limpio. Ya pasó en este
    repositorio: «un censo que nace ciego a su propio defecto»."""
    sucio = (
        "def f(req):\n"
        "    return self._degraded(req, 'el proveedor no respondió')\n"
        "def g(req, exc):\n"
        "    return Narrative(sections=(), degraded_reason=f'guardrail: {exc}')\n"
    )
    limpio = (
        "def f(req):\n"
        "    return self._degraded(req, MOTIVO_PROVEEDOR_MUDO)\n"
        "def g(req, exc):\n"
        "    return Narrative(sections=(), degraded_reason=motivo_guardrail(exc))\n"
    )
    assert len(_motivos_tecleados(sucio)) == 2, "el detector no ve un motivo tecleado"
    assert _motivos_tecleados(limpio) == [], "el detector marca un motivo que sí está declarado"


#: **La evasión, tal cual se midió.** La frase del glosario tecleada a mano una línea
#: antes y entregada a la puerta por una variable. Con el detector de la 1ª vuelta esto
#: devolvía `[]`: el censo entero se esquivaba con un `motivo = …` de por medio.
_EVASION = (
    "def f(self, req):\n"
    "    motivo = 'el proveedor de redacción no respondió'\n"
    "    return self._degraded(req, motivo)\n"
)

#: La misma evasión por el otro lado: la frase entra por el `keyword`, no por el
#: argumento posicional, y además compuesta a trozos.
_EVASION_POR_PARTES = (
    "def g(exc):\n"
    "    cabeza = 'el proveedor de redacción'\n"
    "    motivo = cabeza + ' no aceptó la clave'\n"
    "    return Narrative(sections=(), degraded_reason=motivo)\n"
)


@pytest.mark.parametrize(
    "fuente", [_EVASION, _EVASION_POR_PARTES], ids=["por variable", "por partes"]
)
def test_el_detector_NO_SE_EVADE_moviendo_la_frase_a_una_variable(fuente: str) -> None:
    """El nombre de la guarda de abajo dice «ningún motivo se teclea» y eso es lo que
    tiene que medir: no «ningún motivo se teclea como argumento directo»."""
    assert _motivos_tecleados(fuente), "la frase está tecleada una línea antes y el censo no la ve"


@pytest.mark.parametrize(
    ("fuente", "por_que"),
    [
        pytest.param(
            "def f(self, req, reason):\n    return self._degraded(req, reason)\n",
            "un parámetro no es una frase tecleada",
            id="parámetro",
        ),
        pytest.param(
            "reason = 'una frase cualquiera de otra cosa'\n"
            "def f(self, req, reason):\n"
            "    return self._degraded(req, reason)\n",
            "el parámetro SOMBREA al nombre del módulo",
            id="parámetro que sombrea",
        ),
        pytest.param(
            "def f(self, req, elegido):\n    return self._degraded(req, elegido.degraded_reason)\n",
            "un atributo ajeno no es prosa de este módulo",
            id="atributo",
        ),
        pytest.param(
            "def f(req, exc):\n"
            "    motivo = f'{MOTIVO_SIN_HECHOS} ({type(exc).__name__})'\n"
            "    return Narrative(sections=(), degraded_reason=motivo)\n",
            "componer con el glosario y un paréntesis no es teclear una frase",
            id="f-string sin prosa propia",
        ),
        pytest.param(
            "def f(self, req, fila):\n"
            "    motivo = 'algo tecleado'\n"
            "    motivo = fila['degraded_reason']\n"
            "    return self._degraded(req, motivo)\n",
            "reasignar a algo que no es prosa desata el nombre",
            id="reasignado",
        ),
    ],
)
def test_el_detector_NO_MARCA_lo_que_sí_está_declarado(fuente: str, por_que: str) -> None:
    """El control negativo. Un censo que marca de más se acaba desactivando, y entonces
    no vigila nada — el mismo final que uno que se evade."""
    assert _motivos_tecleados(fuente) == [], por_que


def test_ningun_motivo_se_teclea_FUERA_del_glosario() -> None:
    """Lo que el nombre promete, sobre el paquete entero y **siguiendo los nombres**.

    Lo que pasa el censo, y por qué: una constante importada del glosario, un parámetro,
    un atributo ajeno, `motivo_con_causa(...)` / `motivo_guardrail(...)` y una f-string
    que solo aporte separadores sobre constantes del glosario. Lo que no pasa: una frase
    con letras escrita aquí, llegue a la puerta directamente o por variable.

    `quota.py` es la excepción declarada en `base.py` —sus dos motivos viven pegados a
    los dos números de los que se derivan— y no la ejerce este censo por otra razón:
    allí los motivos se DEVUELVEN (`EstadoCuota.motivo`), no se entregan a una puerta.
    Quien los pasa es `narrative/__init__.py`, y allí ya son un nombre importado.
    """
    sucios: dict[str, list[tuple[int, str]]] = {}
    for fichero in sorted(_PAQUETE.glob("*.py")):
        if fichero.name == _GLOSARIO:
            continue
        hallados = _motivos_tecleados(fichero.read_text(encoding="utf-8"))
        if hallados:
            sucios[fichero.name] = hallados
    assert not sucios, (
        "motivos tecleados en el sitio en vez de declarados con nombre "
        f"(el PDF acaba con dos vocabularios para el mismo hecho): {sucios}"
    )


# ── el sufijo, por el camino del proveedor remoto ─────────────────────────────

FACTS = facts_from(model(verdict_basis=BASIS))
_BUENAS = {t: "texto de la sección." for t in SECTION_TITLES}


def _provider(handler) -> OpenRouterProvider:  # noqa: ANN001
    ajustes = Settings(
        openrouter_enabled=True, openrouter_model="algun/modelo", openrouter_api_key="sk-test"
    )
    return OpenRouterProvider(ajustes, api_key="sk-test", transport=httpx.MockTransport(handler))


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("tardó demasiado", request=request)


def _401(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
    return httpx.Response(401, json={"error": {"message": "User not found.", "code": 401}})


def _ilegible(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
    return httpx.Response(200, json={"choices": [{"message": {"content": "esto no es JSON"}}]})


def _descartada(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
    import json  # noqa: PLC0415

    intrusa = {**_BUENAS, "Qué se midió": "El pico fue de 0.99 g."}
    return httpx.Response(
        200, json={"choices": [{"message": {"content": json.dumps({"sections": intrusa})}}]}
    )


@pytest.mark.parametrize(
    "handler",
    [_timeout, _401, _ilegible, _descartada],
    ids=["mudo", "401", "ilegible", "guardrail"],
)
async def test_el_sufijo_del_proveedor_remoto_DICE_LA_VERDAD(handler) -> None:  # noqa: ANN001
    """Las cuatro degradaciones del camino de producción prometen respaldo **y lo hay**.

    Las tres de `openrouter.py` no lo prometían: salían sin sufijo mientras devolvían
    las seis secciones deterministas, o sea callando una verdad en vez de diciéndola.
    """
    out = await _provider(handler).generate(NarrativeRequest(facts=FACTS, model="m"))
    razon = out.degraded_reason or ""
    assert razon, "un fallback no puede ser `ok`"
    assert len(out.sections) == 6, "el respaldo determinista sí salió"
    assert razon.endswith(SUFIJO_DETERMINISTA), f"promete menos de lo que hay: {razon!r}"


async def test_los_motivos_del_proveedor_remoto_SON_los_del_glosario() -> None:
    """Citados por su nombre, no por un trozo de frase — que es lo que el glosario
    prometía y no se podía cumplir mientras vivieran fuera de él."""
    mudo = await _provider(_timeout).generate(NarrativeRequest(facts=FACTS, model="m"))
    ilegible = await _provider(_ilegible).generate(NarrativeRequest(facts=FACTS, model="m"))
    rechazada = await _provider(_descartada).generate(NarrativeRequest(facts=FACTS, model="m"))
    assert MOTIVO_PROVEEDOR_MUDO in (mudo.degraded_reason or "")
    assert (ilegible.degraded_reason or "") == MOTIVO_RESPUESTA_ILEGIBLE
    assert (rechazada.degraded_reason or "").startswith(f"{MOTIVO_GUARDRAIL}:")


# ── la causa es un CÓDIGO, no una frase ───────────────────────────────────────

#: Lo que `motivo_con_causa` documenta que recibe: un nombre corto que escribimos o
#: elegimos nosotros. Se permite el espacio de `HTTP 401` y nada más.
_CAUSA = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*(?: [0-9]{3})?$")


@pytest.mark.parametrize(
    ("ajustes", "cliente", "esperado"),
    [
        pytest.param(
            {"openrouter_secret_id": "takab/dev/openrouter"},
            "revienta",
            "RuntimeError",
            id="el secreto no se puede leer",
        ),
        pytest.param(
            {"openrouter_secret_id": "takab/dev/openrouter"},
            "vacio",
            CODIGO_SECRETO_SIN_CLAVE,
            id="el secreto existe y no trae la clave",
        ),
    ],
)
def test_el_error_de_la_clave_es_un_CODIGO_citable(ajustes, cliente, esperado) -> None:  # noqa: ANN001
    """`ClaveOpenRouter.error` viaja a `motivo_con_causa` y de ahí al papel.

    Por la rama del secreto sin `api_key` devolvía una frase entera en castellano («el
    secreto no trae la clave 'api_key'»). No filtraba nada —la escribíamos nosotros—,
    pero dejaba sin cumplir la regla escrita de `motivo_con_causa`, y una regla que se
    cumple «casi siempre» no se puede vigilar ni citar por su nombre.
    """
    import json  # noqa: PLC0415

    class SM:
        def get_secret_value(self, SecretId: str) -> dict:  # noqa: N803, ARG002
            if cliente == "revienta":
                raise RuntimeError("sin permisos")
            return {"SecretString": json.dumps({"otra_cosa": "x"})}

    s = Settings(openrouter_enabled=True, openrouter_model="m", openrouter_api_key="", **ajustes)
    clave = resolve_api_key(s, client=SM())
    assert clave.api_key == ""
    assert clave.error == esperado
    assert _CAUSA.match(clave.error or ""), f"la causa no es un código citable: {clave.error!r}"
    # Y lo que acaba en el papel lleva el código dentro y promete el respaldo que hay.
    en_el_papel = motivo_con_causa("la clave no se pudo leer", clave.error or "")
    assert f"({esperado})" in en_el_papel and en_el_papel.endswith(SUFIJO_DETERMINISTA)
