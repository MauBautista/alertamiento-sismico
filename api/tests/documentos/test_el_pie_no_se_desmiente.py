"""[T-7.42] El pie y el cuerpo del MISMO papel no pueden decirse cosas contrarias.

Medido antes de esta ficha: el dictamen imprimía en el pie de **todas** sus
páginas «SIN HUELLA DE CONTENIDO · ESTE DOCUMENTO NO AFIRMA DATOS», mientras su
portada imprimía «HASH DE CONTENIDO <sha256>» y mandaba verificarlo. Y el reporte
de simulacro llevaba la misma frase a cuatro renglones de un §4 que dice
**ACREDITA** qué gabinetes acusaron y en cuánto tiempo.

La causa era una sola: `MembretePDF.__init__` acepta `huella=` y **nadie se lo
pasaba**. Un parámetro que nadie pasa.

## Por qué esto no existía y hacía falta

No es que la guarda fuera débil: es que **las tres que había veían cada una la
mitad**, y ninguna cruzaba el pie con el cuerpo del mismo render.

* Una comprobaba que la cadena «SHA-256 DEL CONTENIDO» estuviera **en el fichero
  fuente** del membrete — verde aunque nadie la imprimiera jamás.
* Otra medía el **ancho** de una línea que ningún documento real dibujaba.
* La tercera aceptaba **cualquiera de las dos frases** con un `or`, así que la
  contradicción le daba igual.

Cada una correcta; el conjunto, ciego. Es «un censo que enumera a mano acaba
divergiendo» aplicado a las aserciones.

## La regla, derivada

Cada subclase de `MembretePDF` declara si **afirma datos**. Lo que afirma datos
imprime su huella; lo que no, declara la ausencia. No hay lista de exentos: la
propiedad viaja con la clase, como ya viaja `tipo`.
"""

from __future__ import annotations

import re

import pytest

from takab_api.documentos.membrete import MembretePDF
from tests.documentos.espia import espia_del_render
from tests.documentos.test_censo_fpdf import _descendientes, _todos_los_modulos

#: Un sha256 tal como lo imprime el pie.
_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")

AUSENCIA = "SIN HUELLA DE CONTENIDO"
ROTULO = "SHA-256 DEL CONTENIDO"


def _documentos() -> dict[str, tuple[type, callable]]:
    """Cada documento del sistema con su render REAL.

    Se cruza contra el censo derivado de subclases más abajo: una clase nueva sin
    entrada aquí pone el test en rojo, que es lo que impide que el próximo
    documento nazca con el pie desmintiéndose.
    """
    from takab_api.dictamen.layout import TakabPDF
    from takab_api.dictamen.pdf import render
    from takab_api.documentos.hoja import _Hoja, hoja_en_blanco
    from takab_api.drill_report import ReportePDF
    from takab_api.drill_report import render as render_simulacro
    from tests.api.test_drill_report import _rep
    from tests.dictamen.test_pdf import model

    return {
        "dictamen-tecnico": (TakabPDF, lambda: render(model(), "technical")),
        "dictamen-ejecutivo": (TakabPDF, lambda: render(model(), "executive")),
        "reporte-de-simulacro": (ReportePDF, lambda: render_simulacro(_rep())),
        "hoja-en-blanco": (_Hoja, hoja_en_blanco),
    }


def _capturado(render):
    with espia_del_render() as cap:
        render()
    return cap


# ───────────────────────────────────────────── el censo, antes que las aserciones


def test_el_censo_de_documentos_esta_COMPLETO() -> None:
    """Derivado de las subclases reales, no de esta lista.

    ⚠️ Hace falta importar todo el paquete primero: sin eso el barrido sólo ve lo
    que otro test haya importado antes, y el resultado depende del orden de la
    suite.
    """
    modulos = _todos_los_modulos()
    assert len(modulos) > 50, f"el barrido sólo importó {len(modulos)} módulos"

    clases = {c for c in _descendientes(MembretePDF) if c.__module__.startswith("takab_api.")}
    assert len(clases) >= 3, f"el censo sólo vio {len(clases)} subclases de MembretePDF"

    cubiertas = {clase for clase, _ in _documentos().values()}
    huerfanas = sorted(c.__qualname__ for c in clases - cubiertas)
    assert not huerfanas, (
        "hay documentos sin render registrado en esta suite, así que nadie comprueba "
        f"si su pie se contradice con su cuerpo: {huerfanas}"
    )


def test_cada_documento_DECLARA_si_afirma_datos() -> None:
    """La propiedad viaja con la clase, como `tipo`. Sin lista de exentos."""
    clases = {c for c in _descendientes(MembretePDF) if c.__module__.startswith("takab_api.")}
    sin_declarar = sorted(c.__qualname__ for c in clases if "afirma_datos" not in vars(c))
    assert not sin_declarar, (
        "hay subclases de MembretePDF que no declaran si afirman datos. Sin esa "
        "declaración no se puede decir si su pie debe imprimir una huella o "
        f"declarar su ausencia: {sin_declarar}"
    )


# ────────────────────────────────── la contradicción, cruzando pie y cuerpo


@pytest.mark.parametrize("nombre", sorted(_documentos()))
def test_el_pie_NO_contradice_al_CUERPO(nombre: str) -> None:
    """Las dos mitades del MISMO render, que es lo que ninguna guarda cruzaba.

    Si el cuerpo afirma una huella de contenido, el pie tiene que imprimir ESA
    MISMA. Y si el pie declara la ausencia, el cuerpo no puede estar imprimiendo
    un hash — ni diciendo que acredita nada.
    """
    clase, render = _documentos()[nombre]
    cap = _capturado(render)
    pie = cap.membrete
    cuerpo = cap.texto

    if clase.afirma_datos:
        assert AUSENCIA not in pie, (
            f"{nombre} AFIRMA datos y su pie dice «{AUSENCIA} · ESTE DOCUMENTO NO "
            "AFIRMA DATOS» en todas sus páginas: el papel se desmiente a sí mismo"
        )
        del_pie = _HEX64.findall(pie)
        assert del_pie, f"{nombre} afirma datos y su pie no imprime ninguna huella"
        assert ROTULO in pie, "la huella del pie va sin rótulo: no se sabe qué número es"
    else:
        assert AUSENCIA in pie, (
            f"{nombre} no afirma datos y su pie no lo declara: un hueco donde va una "
            "huella se lee como un descuido, no como una ausencia"
        )
        assert not _HEX64.findall(pie), f"{nombre} declara la ausencia y aun así imprime un hash"
        assert not _HEX64.findall(cuerpo), (
            f"{nombre} declara en el pie que NO afirma datos, y su cuerpo imprime "
            "un hash de 64 hex: ésa es exactamente la contradicción que esta ficha "
            "vino a cerrar, sólo que con los papeles cambiados"
        )


@pytest.mark.parametrize(
    "nombre", sorted(n for n, (c, _) in _documentos().items() if c.afirma_datos)
)
def test_el_hash_del_pie_es_EL_MISMO_que_el_del_cuerpo(nombre: str) -> None:
    """Dos números distintos bajo el mismo rótulo sería peor que ninguno.

    El invariante es que no haya DOS huellas de contenido distintas en el mismo
    papel, no que el cuerpo imprima una: el dictamen la lleva además en la
    portada porque un perito la busca ahí, y el reporte de simulacro sólo en el
    pie, que sale en todas sus páginas. Las dos formas son honestas; lo que no lo
    sería es que discreparan.
    """
    _clase, render = _documentos()[nombre]
    cap = _capturado(render)
    del_pie = set(_HEX64.findall(cap.membrete))
    del_cuerpo = set(_HEX64.findall(cap.texto))
    assert del_pie, f"{nombre} afirma datos y su pie no imprime huella"
    if not del_cuerpo:
        return  # El cuerpo no la repite: no hay nada que pueda contradecirse.
    assert del_pie & del_cuerpo, (
        f"{nombre}: el pie imprime {sorted(del_pie)} y el cuerpo {sorted(del_cuerpo)}, "
        "y no coinciden en ninguno. Dos huellas distintas del mismo papel no se "
        "pueden verificar: el lector no sabe cuál es la buena"
    )


def test_la_huella_del_pie_se_REPITE_en_todas_las_paginas() -> None:
    """Un dictamen se cita por páginas sueltas, y una página suelta sin huella no
    se puede casar con su registro."""
    from takab_api.dictamen.pdf import render
    from tests.dictamen.test_pdf import model

    cap = _capturado(lambda: render(model()))
    paginas = len([1 for chrome, v in cap.fragmentos if chrome and ROTULO in v])
    assert paginas >= 3, (
        f"la huella sale en {paginas} pies; el dictamen tiene al menos 3 páginas y "
        "cada una tiene que poder casarse con su registro por sí sola"
    )


# ───────────────────────────────────────── y lo que el pie dice del INSTANTE


def test_el_pie_del_dictamen_lleva_el_INSTANTE_del_suceso() -> None:
    """El segundo cable suelto que esta ficha encontró.

    `sellado=` tampoco llegaba, así que los 62 mm de la columna derecha del pie
    —medidos y reservados en `T-7.21`— salían VACÍOS en todas las páginas de los
    dos dictámenes. Una hoja suelta no decía de qué sismo hablaba.
    """
    from takab_api.dictamen.pdf import render
    from tests.dictamen.test_pdf import model

    cap = _capturado(lambda: render(model()))
    assert "EVENTO" in cap.membrete, (
        "el pie del dictamen no dice el instante del suceso: una página suelta no "
        "dice de qué evento habla"
    )


# ──────────────────────────────────── y lo que el pie NO dice, por decisión


def test_NINGUN_pie_imprime_el_build() -> None:
    """Criterio 2 de la ficha, en su forma comprobable.

    La decisión y sus medidas están en `documentos/membrete.py`, decisión 4. Ésta
    es la guarda: derivada del render REAL de cada documento, no de una lista.
    """
    for nombre, (_clase, render) in _documentos().items():
        pie = _capturado(render).membrete
        assert "build" not in pie.lower(), (
            f"el pie de {nombre} imprime el build. La celda del sello tiene 62 mm "
            "y «EVENTO … UTC» ya ocupa 39: un abreviado de 10 caracteres se pisa "
            "con la huella, y `cell()` no envuelve. Ver la decisión 4 del módulo"
        )


def test_el_membrete_NO_ACEPTA_un_build_que_nadie_le_pasa() -> None:
    """Un parámetro que nadie pasa es la forma exacta del defecto de esta ficha.

    `huella=` llevaba así desde `T-7.21`: aceptado, documentado, y nunca pasado
    — y por eso el pie de todos los dictámenes decía «ESTE DOCUMENTO NO AFIRMA
    DATOS» mientras la portada imprimía el hash. Si `build=` vuelve, que vuelva
    con la aritmética del pie rehecha y con alguien que lo pase.
    """
    import inspect

    parametros = inspect.signature(MembretePDF.__init__).parameters
    assert "build" not in parametros, (
        "volvió `build=` a la firma del membrete. La decisión 4 del módulo lo "
        "descartó con medidas; si se revoca, hay que rehacer los anchos del pie"
    )


def test_DOS_exportaciones_del_MISMO_simulacro_dan_los_MISMOS_bytes() -> None:
    """Lo que sostiene la segunda razón de la decisión 4, medido.

    El reporte de simulacro se guardaba bajo una clave FIJA —
    `evidence/<tenant>/drills/<id>/reporte.pdf`, en `routers/drills.py`— y cada
    exportación **sobrescribía ese objeto** e insertaba una fila de evidencia
    nueva con el sha256 del archivo. [T-8.12 · A-142] Desde entonces la clave
    lleva ese sha256 (`…/<sha256>/reporte.pdf`), así que una exportación de bytes
    distintos ya no pisa a nadie; el determinismo sigue haciendo falta para que
    dos exportaciones del MISMO contenido caigan en la MISMA clave —y no dejen
    una fila de evidencia por cada despliegue—. Si algo del pie dependiera del
    despliegue —un `build`, la hora de generación—, cada exportación posterior
    produciría otro objeto del mismo simulacro sin que el contenido cambiara, y
    por la regla de oro 11 ninguno se poda nunca.
    """
    from takab_api.drill_report import render as render_simulacro
    from tests.api.test_drill_report import _rep

    assert render_simulacro(_rep()) == render_simulacro(_rep())


def test_donde_el_papel_manda_correr_sha256sum_DICE_sobre_QUE() -> None:
    """La tercera contradicción que encontró esta ficha, y la más silenciosa.

    La portada del pericial imprimía «HASH DE CONTENIDO <sha256>» y, cuatro
    milímetros debajo, «el SHA-256 de este archivo queda registrado… verifíquelo
    con sha256sum». Son DOS números distintos. Quien hiciera lo que el papel
    manda obtendría otro y concluiría que la evidencia no casa — que es peor que
    no haber invitado a verificar.

    Se acopla a la REDACCIÓN a propósito: es texto de un documento de evidencia,
    y reescribirlo tiene que pasar por aquí.
    """
    for nombre, (_clase, render) in _documentos().items():
        cuerpo = _capturado(render).texto
        if "sha256sum" not in cuerpo:
            continue
        assert "no este archivo" in cuerpo, (
            f"{nombre} manda correr sha256sum sin decir que el número impreso es "
            "el del CONTENIDO y no el del archivo: el lector que obedezca obtendrá "
            "otro hash y creerá que la evidencia no casa"
        )
