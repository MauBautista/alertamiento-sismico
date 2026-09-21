"""Esqueleto compartido por los dos proveedores (T-2.42).

Las secciones son las mismas se redacten como se redacten: así el documento tiene la
misma forma con o sin asistencia automatizada, y el guardrail puede exigirlas.
"""

from __future__ import annotations

import hashlib
import json

from takab_api.narrative.base import NarrativeFacts

#: Títulos y orden. El guardrail rechaza una respuesta a la que le falte cualquiera.
SECTION_TITLES: tuple[str, ...] = (
    "Resumen ejecutivo",
    "Qué pasó",
    "Qué se midió",
    "Por qué este veredicto",
    "Qué hacer ahora",
    "Limitaciones y datos ausentes",
)

SYSTEM = """\
Redactas las secciones en prosa de un dictamen preliminar de alertamiento sísmico \
para Protección Civil en México. Escribes en español neutro, en tercera persona, con \
frases cortas y sin adornos.

El veredicto ya está decidido por un motor de reglas determinista y te llega en los \
hechos. Tu trabajo es explicarlo, no revisarlo: no propongas otro estado, no digas que \
el dictamen debería cambiar y no sugieras que la evidencia apunta a otra conclusión. Si \
algo te parece inconsistente, dilo como una limitación en la última sección.

No inventes ninguna cifra. Usa exclusivamente los valores que aparecen en los hechos, \
con las mismas unidades y los mismos decimales. Si un dato no está, escribe que no está \
y por qué; nunca lo estimes, nunca escribas un cero en su lugar.

Devuelve únicamente un objeto JSON con la forma {"sections": {"<título>": "<texto>"}}, \
con exactamente los títulos que se listan abajo y en ese orden. Cada texto es uno o dos \
párrafos de prosa corrida, sin viñetas ni markdown.

Títulos:\
"""


def system_prompt() -> str:
    """El prompt de sistema completo.

    Se concatena en vez de interpolar: el propio prompt contiene llaves (el ejemplo de
    JSON), y un `.format` las leería como campos de reemplazo. Un cambio inocente en la
    redacción volvería a romperlo.
    """
    return SYSTEM + "\n" + "\n".join(f"- {t}" for t in SECTION_TITLES)


#: El encuadre de lo que se le manda al modelo. Es constante —y no una f-string
#: suelta— para que entre en la versión del prompt: reencuadrar los hechos como
#: «hipótesis» cambiaría lo que el modelo cree que está leyendo sin que nada lo
#: registrara.
USER_PREFIX = "Hechos del incidente:"


def user_prompt(facts: NarrativeFacts) -> str:
    """Los hechos redactados, tal cual, como JSON.

    Se manda el objeto entero en vez de una plantilla en prosa para que el proveedor no
    reciba ninguna interpretación previa: lo que hay es lo que se midió.
    """
    from dataclasses import asdict  # noqa: PLC0415 - local: evita coste en import

    payload = json.dumps(asdict(facts), ensure_ascii=False, indent=2, sort_keys=True)
    return f"{USER_PREFIX}\n\n{payload}"


def prompt_version() -> str:
    """[T-7.26] Versión del prompt, **derivada del propio texto de las plantillas**.

    La ficha pide registrar con qué instrucciones se redactó cada dictamen. Un número
    de versión tecleado a mano cumple el campo y no cumple el propósito: se queda viejo
    al primer retoque de redacción, y a partir de ahí dos documentos con la misma
    «versión» se pidieron con prompts distintos. Derivándola del hash de las plantillas,
    **nadie puede cambiar el prompt sin que la versión cambie** — que es la única forma
    de que este campo signifique algo el día que haya que auditar por qué un documento
    dice lo que dice.

    Entran las TRES piezas que el modelo llega a leer como instrucción: el prompt de
    sistema, los títulos exigidos y el encuadre de los hechos. NO entran los hechos:
    cambian en cada incidente y la versión dejaría de identificar a la plantilla.

    Sin caché a propósito: son unos microsegundos de sha256 una vez por dictamen, y una
    versión memorizada al importar sería mentira en cuanto un test —o un parche en
    caliente— tocara una plantilla.
    """
    material = "\n".join((system_prompt(), USER_PREFIX))
    return "p" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
