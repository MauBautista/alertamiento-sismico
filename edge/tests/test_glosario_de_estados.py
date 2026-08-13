"""[T-2.85.b] EL PANEL Y LA CONSOLA HABLAN EL MISMO IDIOMA — lado del panel.

El panel del gabinete decía `NO CONTESTA`, `DATO RETENIDO`, `S/D`. La consola de
la nube decía `OPERATIVO`, `DEGRADADO`, `SIN ENLACE`. Quien opera mira LAS DOS
pantallas —primero el panel en el sitio, luego la consola desde el SOC, o al
revés en plena madrugada— y cada traducción que hace de cabeza bajo presión es
un sitio donde se equivoca.

**El glosario vive en `shared/glossary/estados.json`.** Es JSON y no un módulo
porque el panel NO PUEDE IMPORTAR NADA: se sirve como un único archivo estático
desde un Pi sin build ni red. Las dos superficies salen de él por DERIVACIÓN
COMPROBADA — la consola lo copia en `web/src/features/fleet/estadoGlosario.ts`
y un test lo compara por igualdad; el panel lleva sus literales en el HTML y lo
comprueba este censo. Mismo patrón, y por la misma razón física, que
`shared/design-tokens/tokens.json` (ver `test_local_api_panel.py`).

**Lo que hace este censo** es lo que hace que dure: no comprueba dos o tres
palabras conocidas, sino que ninguna frase del panel hable de uno de los ejes
del glosario con OTRA palabra. `detecta` son las raíces del eje; toda frase en
mayúsculas que contenga una raíz tiene que contener también un término canónico.
El día que alguien escriba `DATOS CONGELADOS`, `NO RESPONDE` o `FUERA DE LÍNEA`,
esto se pone rojo y le obliga a usar la palabra que ya existe — o a añadirla al
glosario con su razón, que es justo la conversación que hay que tener.

Las excepciones se comparan por IGUALDAD. Una que puede crecer sola no es una
excepción, es un agujero.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[2]
_GLOSARIO = _RAIZ / "shared" / "glossary" / "estados.json"
_INDEX = _RAIZ / "edge" / "takab_edge" / "local_api" / "index.html"

#: Frase en MAYÚSCULAS: es la forma en que este panel rotula estado. La prosa en
#: minúsculas de las tarjetas no compite con el vocabulario.
_MAYUS = re.compile(r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9/·()+.\-]*(?:[ ][A-ZÁÉÍÓÚÑ0-9/·()+.\-]+)*")


def _glosario() -> dict:
    return json.loads(_GLOSARIO.read_text("utf-8"))


def frases_del_panel() -> set[str]:
    """Toda frase en mayúsculas del panel, EXCLUIDOS los datos de demo.

    La exclusión es la lección de T-2.85.a: los literales de las escenas `?demo=`
    no son un camino de render, y contarlos daría por bueno un vocabulario que
    nadie ve nunca. El bloque de demo se delimita por sus dos funciones frontera,
    y que se haya delimitado de verdad lo comprueba `test_el_barrido_encuentra…`.
    """
    html = _INDEX.read_text("utf-8")
    lineas = html.splitlines()
    i0 = next(i for i, ln in enumerate(lineas) if ln.startswith("function baseStatus()"))
    i1 = next(i for i, ln in enumerate(lineas) if ln.startswith("function demoWaveAmp("))
    fuera_de_demo = "\n".join(lineas[:i0] + lineas[i1:])

    frases: set[str] = set()
    for m in re.finditer(r"'([^'\n]*)'|\"([^\"\n]*)\"", fuera_de_demo):
        texto = m.group(1) or m.group(2) or ""
        frases |= {p.strip(" ·-.") for p in _MAYUS.findall(texto)}
    # …y el texto del propio marcado (los banners viven ahí, no en el script).
    marcado = re.sub(r"<!--[\s\S]*?-->", "", html[: html.index("<script>")])
    marcado = re.sub(r"<[^>]+>", "\n", marcado)
    frases |= {p.strip(" ·-.") for p in _MAYUS.findall(marcado)}
    return {f for f in frases if f and any(c.isalpha() for c in f)}


#: FRASES DEL PANEL QUE TOCAN UNA RAÍZ Y NO SON ESTADO — con su razón.
#:
#: Igualdad, no contención: quien añada una tiene que escribir por qué su frase
#: no está hablando del eje cuya raíz contiene.
NO_SON_ESTADO: dict[str, str] = {
    "CATÁLOGO NO DISPONIBLE · SIN DATOS EN CACHÉ": (
        "Predica sobre el CONTENIDO de la caché del catálogo sísmico del SSN, no "
        "sobre un dato del gabinete. El catálogo es información de contexto: su "
        "ausencia no degrada nada de lo que protege el edificio."
    ),
    "DESCARTADA · SIN DATOS EN EL RING": (
        "Desenlace de UNA evidencia concreta: el sismo se pidió al búfer circular "
        "y ya no quedaban muestras. Es un hecho del pasado sobre un fichero, no el "
        "estado presente de un dato en pantalla."
    ),
    "PRUEBA DE ACTUADORES NO DISPONIBLE EN ESTE ARRANQUE": (
        "Prosa de la tarjeta. El ESTADO lo lleva su píldora, que dice "
        "`S/D · SIN MÓDULO DE PRUEBA` con el término del glosario."
    ),
    "RESPALDO DE EVIDENCIA NO DISPONIBLE EN ESTE ARRANQUE": (
        "Igual: la píldora de evidencia dice `S/D · SIN MÓDULO DE RESPALDO`."
    ),
    "PENDIENTE ILEGIBLE": (
        "Un FICHERO de evidencia que no se puede leer (JSON corrupto en disco). No "
        "es una pieza muda: el gabinete contesta perfectamente, y la acción es "
        "borrar el fichero, no llamar por la sirena."
    ),
    "PENDIENTES ILEGIBLES": ("Plural del anterior."),
}


# ------------------------------------------------------- guardas del censo


def test_el_barrido_encuentra_el_panel_y_lo_separa_de_la_demo():
    """Si el barrido no encuentra nada, todo lo de abajo es un verde falso."""
    frases = frases_del_panel()
    assert len(frases) > 150, f"el barrido solo halló {len(frases)} frases"
    # Sí ve el vocabulario real…
    assert "NO CONTESTA" in frases
    assert "S/D" in frases
    # …y NO ve lo que solo existe en los datos de demo (`?demo=`).
    assert "DRILL-2026-0730-01" not in frases


def test_el_glosario_declara_los_dos_lados_de_cada_eje():
    """Un eje sin ningún término no gobierna nada; uno con un lado en `null`
    tiene que decir POR QUÉ no existe al otro lado."""
    ejes = _glosario()["ejes"]
    assert len(ejes) >= 8
    for nombre, d in ejes.items():
        assert d["panel"] or d["consola"], f"{nombre}: eje sin ningún término"
        assert d["detecta"], f"{nombre}: eje sin raíces de detección"
        if d["panel"] is None:
            assert d.get("solo_en_la_consola_porque"), (
                f"{nombre}: no existe en el panel y no dice por qué. Aplanar una "
                "diferencia legítima es peor que tener dos vocabularios."
            )
        if d["consola"] is None:
            assert d.get("solo_en_el_panel_porque"), (
                f"{nombre}: no existe en la consola y no dice por qué."
            )


# --------------------------------------------------------------- el censo


def intrusas(frases: set[str], ejes: dict) -> dict[str, str]:
    """`frase → eje` de las que hablan de un eje sin usar su término canónico."""
    fuera: dict[str, str] = {}
    for nombre, d in ejes.items():
        canonicos = [t for t in (d["panel"], d["consola"]) if t]
        for f in frases:
            if any(r in f for r in d["detecta"]) and not any(c in f for c in canonicos):
                fuera[f] = nombre
    return fuera


@pytest.mark.parametrize(
    ("frase", "eje"),
    [
        ("DATOS CONGELADOS DESDE 04:12", "vejez"),
        ("EL MÓDULO NO RESPONDE", "pieza_muda"),
        ("GABINETE FUERA DE LÍNEA", "enlace_nube"),
        ("ESTACIÓN DADA DE BAJA", "baja_administrativa"),
        ("TEMPERATURA SIN DATO", "ausencia"),
    ],
)
def test_el_analizador_caza_un_sinonimo_recien_estrenado(frase, eje):
    """La prueba del propio censo: sin esto, un verde no significa nada.

    Cada una de estas frases es una forma PLAUSIBLE de decir algo que el
    glosario ya nombra. Son sintéticas a propósito: si el analizador solo
    supiera reconocer las palabras que hoy están en el panel, no protegería de
    nada el día que alguien escriba la suya.
    """
    assert intrusas({frase}, _glosario()["ejes"]) == {frase: eje}


@pytest.mark.parametrize(
    "frase",
    ["RELÉS · NO CONTESTA", "EDAD S/D", "DATO RETENIDO DESDE 04:12:07 UTC", "3 SIN ENLACE"],
)
def test_el_analizador_no_acusa_a_quien_usa_el_termino_del_glosario(frase):
    """Un término canónico CALIFICADO por su sujeto sigue siendo el término."""
    assert intrusas({frase}, _glosario()["ejes"]) == {}


def test_ninguna_frase_del_panel_estrena_un_literal_fuera_del_glosario():
    """Toda frase que hable de un eje lo dice con la palabra del glosario."""
    ejes = _glosario()["ejes"]
    intrusas_medidas = intrusas(frases_del_panel(), ejes)
    detalle = "\n".join(
        f"  · {f!r} habla del eje «{eje}» y no usa {ejes[eje]['panel'] or ejes[eje]['consola']!r}"
        for f, eje in sorted(intrusas_medidas.items())
        if f not in NO_SON_ESTADO
    )
    assert sorted(intrusas_medidas) == sorted(NO_SON_ESTADO), (
        "EL PANEL ESTRENÓ UN LITERAL DE ESTADO FUERA DEL GLOSARIO "
        f"(`{_GLOSARIO.relative_to(_RAIZ)}`). O usa el término que ya existe —la "
        "consola lo usa y quien opera mira las dos pantallas—, o añádelo al "
        "glosario con su razón, o decláralo en `NO_SON_ESTADO` explicando por qué "
        f"no es estado.\n{detalle}"
    )


#: Los ejes que el glosario dice que el panel SÍ habla. Los demás no se saltan:
#: no existen para esta superficie, y un skip los dejaría pareciendo cubiertos.
_EJES_DEL_PANEL = sorted(e for e, d in _glosario()["ejes"].items() if d["panel"])


@pytest.mark.parametrize("eje", _EJES_DEL_PANEL)
def test_el_panel_usa_de_verdad_el_termino_que_el_glosario_le_asigna(eje):
    """Un glosario que nombra un término que la pantalla no dice es papel mojado."""
    d = _glosario()["ejes"][eje]
    assert any(d["panel"] in f for f in frases_del_panel()), (
        f"el glosario asigna «{d['panel']}» al panel para el eje «{eje}» y el "
        "panel no lo dice en ninguna parte"
    )


def test_las_divergencias_estan_declaradas_con_su_arreglo_exacto():
    """Lo que todavía NO está unificado se declara, con el fichero y la línea.

    Igualdad contra la lista de ejes: una divergencia no puede aparecer sin que
    el eje exista, y cada una lleva quién es su dueño — las dos abiertas hoy caen
    fuera de esta superficie (`StateFrame` y el productor de la nube)."""
    g = _glosario()
    for div in g["divergencias"]:
        assert div["eje"] in g["ejes"], f"divergencia sobre un eje que no existe: {div['eje']}"
        for clave in ("panel", "consola", "arreglo", "dueno", "por_que_sigue_abierta"):
            assert div.get(clave), f"divergencia {div['eje']} sin `{clave}`"
        assert div["panel"] != div["consola"], (
            f"{div['eje']}: declarada como divergencia y los dos términos son iguales"
        )
    assert {d["eje"] for d in g["divergencias"]} == {"vejez", "pieza_muda"}, (
        "las divergencias abiertas cambiaron: si arreglaste una, borra su entrada "
        "del glosario; si apareció otra, decláralas todas"
    )
