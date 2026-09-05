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
    el eje exista, y cada una lleva quién es su dueño — la que sigue abierta cae
    fuera de esta superficie (`StateFrame`, en la consola).

    **[2026-08-13] `pieza_muda` PAGADA.** El productor de la nube emitía
    `RELÉS ILEGIBLES` donde el panel dice `NO CONTESTA`; ahora emite
    `RELÉS · NO CONTESTA` (`api/src/takab_api/schemas/fleet.py`) y su entrada se
    borró aquí en el mismo cambio. **ESTA LISTA SOLO PUEDE BAJAR**, y por eso se
    compara por igualdad: una divergencia que sobrevive a su arreglo documenta
    un defecto que ya no existe y esconde el que sí queda.
    """
    g = _glosario()
    for div in g["divergencias"]:
        assert div["eje"] in g["ejes"], f"divergencia sobre un eje que no existe: {div['eje']}"
        for clave in ("panel", "consola", "arreglo", "dueno", "por_que_sigue_abierta"):
            assert div.get(clave), f"divergencia {div['eje']} sin `{clave}`"
        assert div["panel"] != div["consola"], (
            f"{div['eje']}: declarada como divergencia y los dos términos son iguales"
        )
    assert {d["eje"] for d in g["divergencias"]} == {"vejez"}, (
        "las divergencias abiertas cambiaron: si arreglaste una, borra su entrada "
        "del glosario; si apareció otra, decláralas todas"
    )


# ------------------------------------------------- el manual (T-2.85.b · §6.0)
#
# El manual de operación es la TERCERA copia del glosario, y la que lee una
# persona que no puede consultar el código. La §4 llevaba `DADO DE BAJA EN LA
# NUBE` cuando el banner del panel decía ya `RETIRADO EN LA NUBE`: exactamente
# el modo de fallo que esta ficha existe para cerrar, sólo que en papel. Una
# copia sin vigilar diverge; ésta ya lo había hecho.

_MANUAL = _RAIZ / "takab-docs" / "MANUAL-OPERACION-TAKAB.md"


@pytest.mark.parametrize("eje", sorted(_glosario()["ejes"]))
def test_el_manual_de_operacion_ensena_el_termino_de_cada_eje(eje):
    """§6.0 nombra los diez ejes con la palabra exacta de las dos pantallas.

    Se comprueban los DOS lados: el operador llama a soporte, y quien contesta
    mira la consola. Si el manual sólo enseñara el vocabulario del panel, la
    conversación seguiría siendo una traducción hecha de memoria.
    """
    texto = _MANUAL.read_text("utf-8")
    d = _glosario()["ejes"][eje]
    for lado in ("panel", "consola"):
        termino = d[lado]
        if termino:
            assert termino in texto, (
                f"el manual de operación no enseña «{termino}» ({lado}, eje «{eje}»). "
                "§6.0 es el único sitio donde un operador puede aprender este "
                "vocabulario; si el glosario cambia y el manual no, la persona que "
                "está frente al gabinete y la que mira la consola dejan de hablar igual."
            )


def test_el_manual_no_conserva_el_vocabulario_viejo_de_los_banners():
    """Los rótulos que el panel ya no dice tampoco pueden seguir en el manual.

    Medido: el manual mandaba buscar `📋 DADO DE BAJA EN LA NUBE`, un letrero
    que el panel dejó de pintar. Un manual que nombra un letrero inexistente
    hace dudar de la pantalla, que es lo último que debe pasar frente a un
    gabinete.
    """
    manual = _MANUAL.read_text("utf-8")
    panel = _INDEX.read_text("utf-8")
    huerfanos = [
        rotulo
        for rotulo in re.findall(r"`(📋|🧪|🔧|🔶|🔒)\s*([^`]+)`", manual)
        if (texto := rotulo[1].split(" · ")[0].strip()) and texto not in panel
    ]
    assert not huerfanos, "el manual nombra letreros que el panel ya no pinta:\n" + "\n".join(
        f"  · {e} {t}" for e, t in huerfanos
    )


# ===================================================================== T-5.03
#
# TITULARES DE ALERTA — el mismo evento, tres pantallas, una sola historia.
#
# Este bloque nace de un defecto que ocurrió DOS VECES. En T-2.104 la app titulaba
# «ALERTA SÍSMICA SASMEX» para las cuatro fuentes; se corrigió derivando el titular
# del `trigger`. La auditoría V1-COMERCIAL del 2026-09-02 lo encontró INTACTO al
# otro lado: la consola elegía el banner sólo por `severity` y llevaba sus dos
# textos escritos a fuego, así que un quórum de pánico —`trigger='manual'`,
# severidad crítica por D-11— salía en el videowall como «ALERTA SÍSMICA ·
# PROTÉJASE · EDGE · RS4D · REGLAS LOCALES EJECUTADAS» mientras la app, para ESE
# MISMO incidente, decía «NO ES UNA ALERTA SÍSMICA».
#
# Por qué el censo y no tres pruebas sueltas: cada superficie ya tenía la suya y
# las tres pasaban. Lo que no tenía prueba era la RELACIÓN entre ellas — y es donde
# vivía la mentira. Aquí se cruza el conjunto completo de triggers que la base
# admite contra lo que declara el glosario, y lo que declara el glosario contra lo
# que cada superficie escribe de verdad.

_SCHEMA = _RAIZ / "db" / "schema.sql"
_SUPERFICIES = {
    "consola": _RAIZ / "web" / "src" / "features" / "console" / "alertHeadline.ts",
    "movil": _RAIZ / "mobile" / "src" / "features" / "alert" / "source.ts",
    "panel": _INDEX,
}


def _titulares() -> dict:
    return _glosario()["titulares_de_alerta"]


def _triggers_de_la_base() -> set[str]:
    """El CHECK de `incidents.trigger`, leído del DDL — no de una lista a mano."""
    ddl = _SCHEMA.read_text("utf-8")
    m = re.search(r"trigger\s+text\s+NOT NULL\s+CHECK \(trigger IN \(([^)]*)\)\)", ddl)
    assert m, "`incidents.trigger` ya no declara su CHECK como se esperaba en db/schema.sql"
    return set(re.findall(r"'([a-z_]+)'", m.group(1)))


def test_el_glosario_cubre_exactamente_los_triggers_que_admite_la_base():
    """Ni uno de más, ni uno de menos. Por IGUALDAD, que es lo que hace que dure.

    Un quinto valor en el CHECK entra solo en este censo y sale rojo con su
    nombre hasta que alguien decida cómo se titula en las tres pantallas. Es la
    única forma de que el caso «trigger que nadie mapeó» no llegue a producción.
    """
    de_la_base = _triggers_de_la_base()
    assert len(de_la_base) >= 4, f"el CHECK se leyó corto: {de_la_base}"
    assert set(_titulares()["por_trigger"]) == de_la_base


@pytest.mark.parametrize("trigger", sorted(_titulares()["por_trigger"]))
def test_cada_superficie_escribe_de_verdad_el_titular_que_le_asigna_el_glosario(trigger):
    """El glosario no vale nada si nadie lo obedece: se comprueba en el fuente.

    `panel: null` es legítimo y no se salta en silencio — exige su razón escrita,
    igual que los ejes que sólo existen en una de las dos pantallas.
    """
    decl = _titulares()["por_trigger"][trigger]
    for superficie, ruta in _SUPERFICIES.items():
        termino = decl.get(superficie)
        if termino is None:
            assert decl.get("sin_termino_en_el_panel_porque"), (
                f"{trigger}/{superficie} no declara término y tampoco por qué no lo tiene"
            )
            continue
        assert termino in ruta.read_text("utf-8"), (
            f"el glosario le asigna a {superficie} el titular {termino!r} para "
            f"`trigger={trigger}` y {ruta.relative_to(_RAIZ)} no lo escribe"
        )


@pytest.mark.parametrize("trigger", sorted(_titulares()["por_trigger"]))
def test_lo_que_no_es_un_sismo_no_se_titula_como_un_sismo_en_ninguna_pantalla(trigger):
    """LA REGLA DURA, y la única que un test puede imponer sin discutir de estilo.

    Los textos PUEDEN diferir entre pantallas —un operador y un ocupante no leen
    lo mismo—; lo que no pueden es contradecirse sobre qué clase de cosa está
    ocurriendo. Este es el caso `manual` exacto que rompía.
    """
    decl = _titulares()["por_trigger"][trigger]
    if decl["es_sismica"]:
        return
    for superficie in _SUPERFICIES:
        termino = decl.get(superficie)
        if termino is None:
            continue
        for raiz in _titulares()["detecta_sismica"]:
            assert raiz not in termino, (
                f"`trigger={trigger}` no es sísmico y el titular de {superficie} "
                f"({termino!r}) usa {raiz!r}"
            )


def test_solo_el_contacto_del_wr1_se_lleva_el_nombre_del_servicio_oficial():
    """TAKAB **recibe** la alerta oficial, no la genera.

    Atribuirle a SASMEX una detección propia invierte el deslinde del documento
    de entrega: el día que el umbral local se dispare de más, el cliente culpa al
    servicio oficial. Es la razón por la que existe T-2.104, escrita como censo.
    """
    por_trigger = _titulares()["por_trigger"]
    oficiales = {t for t, d in por_trigger.items() if d["es_oficial"]}
    assert oficiales == {"sasmex"}, oficiales
    con_el_nombre = {
        t for t, d in por_trigger.items() if any("SASMEX" in (d.get(s) or "") for s in _SUPERFICIES)
    }
    assert con_el_nombre <= oficiales, (
        f"estos triggers se atribuyen a SASMEX sin serlo: {sorted(con_el_nombre - oficiales)}"
    )


def test_el_trigger_desconocido_no_cae_al_caso_sismico():
    """El default es lo que convierte un olvido en una afirmación falsa.

    Las dos superficies que pueden encontrarse un trigger no mapeado —la consola
    y el móvil— tienen que rotularlo, no adivinarlo.
    """
    desc = _titulares()["desconocido"]
    assert desc["es_sismica"] is False
    for superficie in ("consola", "movil"):
        termino = desc[superficie]
        for raiz in _titulares()["detecta_sismica"]:
            assert raiz not in termino, f"el default de {superficie} usa {raiz!r}: {termino!r}"
        assert termino in _SUPERFICIES[superficie].read_text("utf-8"), (
            f"{superficie} no escribe su titular de trigger desconocido"
        )
