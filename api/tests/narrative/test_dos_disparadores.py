"""T-9.02 · La prosa tiene que poder decir «se abrió por umbral local y escaló a SASMEX».

Visto en el ensayo 2 (2026-09-24): el PDF decía que la sirena la había disparado el
umbral local. Ahí la ingesta SÍ había escalado el `trigger` —el golpe quedó en `watch` y
el SASMEX subió el tier—, así que el error era de la prosa: el modelo recibe
`opened_trigger` y `trigger` como dos claves JSON sin nada que le diga cuál es cuál, y
con dos nombres casi iguales lo que hace un modelo es escoger uno. (El empate de tier,
que sí dejaba el `trigger` sin escalar, es un caso razonado que cierra la ingesta.) La vía
determinista ya los distingue (`deterministic._que_paso`); la de la IA tiene que recibir
los DOS y la instrucción de leerlos.
"""

from __future__ import annotations

import json

from takab_api.narrative.deterministic import sections_for
from takab_api.narrative.prompts import USER_PREFIX, system_prompt, user_prompt
from takab_api.narrative.redact import facts_from
from tests.dictamen.test_pdf import model

ENSAYO_2 = {"opened_trigger": "local_threshold", "trigger": "sasmex"}


def _hechos_enviados(**over) -> dict:
    texto = user_prompt(facts_from(model(**over)))
    assert texto.startswith(USER_PREFIX)
    return json.loads(texto[len(USER_PREFIX) :])


def test_el_hecho_del_prompt_lleva_los_DOS_disparadores() -> None:
    hechos = _hechos_enviados(**ENSAYO_2)
    assert hechos["opened_trigger"] == "local_threshold", "el modelo no sabe con qué se abrió"
    assert hechos["trigger"] == "sasmex", "el modelo no sabe a qué escaló"


def test_sin_escalada_los_dos_coinciden_y_no_se_inventa_una() -> None:
    """No-vacuidad: la prueba de arriba no pasa porque los dos campos valgan siempre
    lo mismo que el modelo de prueba trae por defecto."""
    hechos = _hechos_enviados(opened_trigger="sasmex", trigger="sasmex")
    assert hechos["opened_trigger"] == hechos["trigger"] == "sasmex"


def test_el_prompt_de_sistema_dice_cual_es_cual() -> None:
    """Las dos claves, nombradas, y la regla de lectura: la apertura NO es la escalada."""
    s = system_prompt()
    assert "`opened_trigger`" in s and "`trigger`" in s, (
        "el prompt no nombra las dos claves: el modelo elegirá una por parecido"
    )
    bajo = s.lower()
    assert "se abrió" in bajo and "escal" in bajo, (
        "el prompt no le dice al modelo que distinga la apertura de la escalada"
    )


def test_la_via_determinista_del_ensayo_2_dice_las_dos_cosas() -> None:
    """La otra mitad del contrato: si la IA se degrada, el texto de respaldo tampoco
    atribuye al umbral local lo que ya es SASMEX."""
    que_paso = dict(sections_for(facts_from(model(**ENSAYO_2))))["Qué pasó"]
    assert "umbral instrumental" in que_paso
    assert "escaló" in que_paso and "SASMEX" in que_paso
