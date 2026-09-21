"""Esqueleto compartido por los dos proveedores (T-2.42).

Las secciones son las mismas se redacten como se redacten: así el documento tiene la
misma forma con o sin asistencia automatizada, y el guardrail puede exigirlas.

[T-7.27] PROMPTS v2 — y por qué el texto cambió a la vez que los datos
----------------------------------------------------------------------

`D-32` le da al modelo cuatro cosas que antes no veía: la tabla por estación, la
cronología con sus horas, las categorías de daño y **las fotografías del brigadista**.
Mandarle los datos sin decirle que los tiene es pagar los tokens y recibir la prosa de
antes: un bloque que el modelo no sabe leer no se usa.

Y al ampliar lo que ve se abren dos formas nuevas de afirmar de más, que el prompt
prohíbe y el guardrail descarta (`openrouter.guard`) — porque una instrucción no es una
garantía:

* **la magnitud no es nuestra**: viene del catálogo del SSN y solo existe si hay línea
  de catálogo en los hechos;
* **una detección exige su fila**: sin tabla por estación no hubo estaciones que
  detectaran nada, y sin fotografía adjunta no hay nada que «se observe en la imagen».

La versión del prompt se DERIVA de este texto (`prompt_version`), así que cambiarlo aquí
la mueve sola: ningún dictamen puede quedar registrado con una versión que no es la que
se usó.
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

Los hechos traen, además del inmueble: la tabla por estación de la red (cada fila con su \
orden, su distancia, lo que midió y contra qué umbral), la cronología de lo que pasó \
—con los segundos transcurridos desde que se abrió el incidente y quién actuó, por \
clase: una persona, el gabinete o el sistema—, los reportes de daño de la brigada por \
rol y por categoría, y cuántas fotografías se adjuntan. Úsalos: son lo que distingue \
este informe de una plantilla.

Nombra a las estaciones por su orden en la tabla («la estación 2»), nunca por un nombre \
ni un código, porque no los tienes. A quien reporta un daño nómbralo por su rol. No \
digas que una estación detectó, corroboró o midió algo si no hay una fila que lo \
sostenga, y no describas una fotografía si no se te adjuntó ninguna.

La magnitud de un sismo no la mide este sistema: procede del catálogo del SSN y solo \
puedes citarla si aparece la línea de catálogo en los hechos, tal como está escrita. Sin \
esa línea, no hay magnitud que citar.

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

#: [T-7.27] El encuadre de las fotografías, que acompaña a las imágenes en el mismo
#: mensaje. Es texto que el modelo lee como instrucción, así que entra en la versión
#: del prompt igual que el resto: reencuadrar «fotografías de la inspección» como
#: «pruebas del estado del inmueble» cambiaría lo que el modelo cree que está mirando
#: sin que nada lo registrara.
#:
#: Dice las cuatro cosas que el modelo no puede deducir de la imagen: de dónde salen,
#: que puede haber más de las que ve, **que la franja inferior va tapada a propósito** y
#: que lo que escriba sobre ellas **no es el veredicto** — el veredicto ya está decidido
#: y llega en los hechos.
#:
#: ⚠️ [T-7.27·A] Lo de la franja no es cortesía. La fotografía sale con la banda de la
#: marca de agua forense tapada (`narrative/marca.py`), y un modelo al que no se le dice
#: hace lo de siempre: describir la franja negra como parte de la escena —«la imagen
#: aparece parcialmente oscurecida», «se observa un derrumbe en la parte inferior»— en
#: un documento que se firma. Decirlo es, además, la otra mitad de la honestidad que
#: `photos_available` ya le exige al prompt: el modelo tiene que saber que está viendo
#: una parte, tanto en número de fotografías como dentro de cada una.
INSTRUCCION_FOTOS = (
    "Las imágenes adjuntas son fotografías tomadas en sitio por la brigada durante la "
    "inspección de este incidente. Descríbelas solo por lo que se ve en ellas y di de "
    "qué reporte es cada una. Pueden no estar todas: los hechos dicen cuántas hay y "
    "cuántas se te adjuntan. Cada fotografía lleva la franja inferior TAPADA EN NEGRO "
    "antes de enviarse, porque ahí va impresa información de la persona que la tomó: "
    "esa franja no es parte de la escena, no la describas y no deduzcas nada de ella. "
    "Lo que observes en una fotografía NO dictamina nada: el veredicto ya está decidido "
    "y te llega en los hechos."
)


#: [T-7.27] El rótulo que precede a cada imagen. Va aparte y no dentro de la
#: instrucción porque cambia por foto, y entra en la versión del prompt porque es
#: TEXTO QUE EL MODELO LEE: sin él, «di de qué reporte es cada una» le pide algo que
#: no puede saber, y lo que hace un modelo al que se le pide lo que no puede saber es
#: inventárselo.
ROTULO_FOTO = "Fotografía {n} · reporte de daños {r}"


def rotulo_de_foto(n: int, reporte: int) -> str:
    return ROTULO_FOTO.format(n=n, r=reporte)


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

    ⚠️ [T-7.27·A] **El material se DERIVA del módulo; ya no se enumera.** Estaba escrito
    a mano —cuatro piezas nombradas una a una— y `T-7.27` añadió `ROTULO_FOTO` sin
    meterlo en la lista: se podía cambiar el texto que precede a cada fotografía, la
    versión no se movía, y un dictamen quedaba registrado con una versión que no era la
    que se usó, que es el defecto exacto que este campo existe para impedir. Un censo
    enumerado a mano acaba divergiendo; es la cuarta vez en este repositorio.

    Entra TODA constante de plantilla del módulo: cadenas y tuplas de cadenas con nombre
    en mayúsculas. NO entran los hechos: cambian en cada incidente y la versión dejaría
    de identificar a la plantilla.

    Sin caché a propósito: son unos microsegundos de sha256 una vez por dictamen, y una
    versión memorizada al importar sería mentira en cuanto un test —o un parche en
    caliente— tocara una plantilla.
    """
    material = "\n".join(f"{nombre}={texto}" for nombre, texto in piezas_del_prompt())
    return "p" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def piezas_del_prompt() -> tuple[tuple[str, str], ...]:
    """`(nombre, texto)` de cada plantilla de este módulo, en orden estable.

    Se lee del espacio de nombres del módulo EN CADA LLAMADA —y no de una lista
    congelada al importar— por dos razones: una plantilla nueva entra sola, y un
    `monkeypatch` sobre cualquiera de ellas mueve la versión, que es lo que permite
    que la guarda se parametrice sobre esta misma función en vez de repetir un test
    por pieza.
    """
    piezas: list[tuple[str, str]] = []
    for nombre, valor in sorted(globals().items()):
        if not nombre.isupper() or nombre.startswith("_"):
            continue
        if isinstance(valor, str):
            piezas.append((nombre, valor))
        elif isinstance(valor, tuple) and all(isinstance(v, str) for v in valor):
            piezas.append((nombre, "\n".join(valor)))
    return tuple(piezas)
