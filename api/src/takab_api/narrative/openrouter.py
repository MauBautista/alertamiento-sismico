"""Proveedor OpenRouter (T-2.42) — apagado por defecto, encendido POR CONFIGURACIÓN.

Se entregó completo para que encenderlo fuera una decisión de configuración y no un
proyecto. **En T-7.26 se enciende en el entorno `dev` desde el despliegue**
(``TAKAB_API_OPENROUTER_ENABLED``, ``_MODEL``, ``_SECRET_ID``); el default del código
sigue siendo apagado y así se queda: con ``openrouter_enabled=False`` y sin slug de
modelo este módulo no abre un socket, y eso lo defiende un test.

⚠️ [T-7.26] **Apagado y «encendido pero no pude» dejaron de ser lo mismo.** Antes,
cualquier fallo al resolver la clave devolvía cadena vacía y el sistema se comportaba
igual que si nadie hubiera pedido IA — de modo que un ``AccessDenied`` sobre el secreto
(lo que pasa en la nube el primer día) salía como un dictamen normal. Ahora
``resolve_api_key`` devuelve el fallo con nombre y ``select_provider`` lo declara en el
papel. Ver ``narrative/__init__.py``.

Tres propiedades que no son negociables aquí:

- **Fail-open total.** Cualquier fallo —red, timeout, 4xx, JSON roto, guardrail—
  degrada al proveedor determinista con su razón, que se imprime en el PDF. Una
  exportación de evidencia no puede caerse porque un tercero esté caído.
- **Sin reintentos.** Un timeout de 8 s ya es mucho dentro de un request HTTP que está
  generando evidencia; reintentar solo multiplica la espera del operador.
- **El guardrail descarta, no corrige.** Si la respuesta intenta imponer un estado, se
  inventa una medición o le falta una sección, se tira entera. Media respuesta
  "arreglada" sería justo el tipo de dato a medias que la regla de oro 7 prohíbe.

**Sin slug de modelo por defecto.** Vacío ⇒ determinista. El día que se encienda, el
slug se verifica contra ``GET /api/v1/models`` de OpenRouter antes de configurarlo: un
default hardcodeado aquí caducaría en silencio.

⚠️ **Y ese día llegó sin la verificación.** T-7.26 enciende el slug desde el despliegue
y nadie lo ha contrastado contra ``/api/v1/models`` — hace falta la clave real y salida
a la red, así que queda pendiente de ``GATE-AWS``. Lo que SÍ está cubierto entretanto es
que un slug caducado no pase por un fallo de red: OpenRouter responde 400 y el papel
imprime «el proveedor de redacción respondió con error (HTTP 400)», no «no respondió».
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Any

from takab_api.dictamen.model import STATUS_LABELS
from takab_api.narrative.base import (
    MOTIVO_PETICION_ENORME,
    MOTIVO_PROVEEDOR_CREDENCIAL,
    MOTIVO_PROVEEDOR_ESTADO,
    MOTIVO_PROVEEDOR_MUDO,
    MOTIVO_RESPUESTA_ILEGIBLE,
    MOTIVO_SIN_VISION,
    MOTIVO_VISION_ILEGIBLE,
    HuellaEnviada,
    Narrative,
    NarrativeFacts,
    NarrativeRequest,
    motivo_con_causa,
    motivo_guardrail,
)
from takab_api.narrative.deterministic import NAME as DETERMINISTA
from takab_api.narrative.deterministic import sections_for
from takab_api.narrative.prompts import (
    INSTRUCCION_FOTOS,
    SECTION_TITLES,
    prompt_version,
    rotulo_de_foto,
    system_prompt,
    user_prompt,
)
from takab_api.narrative.redact import PRESUPUESTO_FOTOS_BYTES
from takab_api.settings import Settings

log = logging.getLogger("takab_api.narrative")

NAME = "openrouter"

#: Techo de la respuesta completa. Seis secciones de prosa no pasan de aquí; más largo
#: es señal de que el proveedor se fue por otro lado.
MAX_TOTAL_CHARS = 9000
MAX_OUTPUT_TOKENS = 1600

#: Mediciones que la prosa puede citar. Cualquier otro número con unidad es inventado.
_MEASUREMENT = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(g|cm/s)\b")
_TOLERANCE = 1e-6

#: [T-7.27] La magnitud, que NO la mide este sistema: sale del catálogo del SSN y solo
#: existe si hay línea de catálogo.
#:
#: ⚠️ [T-7.27·A] La versión anterior —`(?:M|MAGNITUD|magnitud)\s*=?\s*(\d…)`— dejaba
#: pasar seis de ocho formulaciones naturales, MEDIDO: exigía el número pegado al
#: token, así que «magnitud DE 7.1», «magnitud estimada de 7.1» y «magnitud momento de
#: 7.1» escapaban enteras; y no casaba con `Mw`, que es la notación estándar del
#: SSN/USGS y la forma más probable de todas. Ahora se admiten los sufijos de escala
#: (`Mw`, `Mww`, `Ms`, `mb`→`Mb`, `ML`, `Md`) y los conectores que un redactor escribe
#: entre el token y la cifra.
_ESCALA = r"(?:[Mm]agnitud(?:es)?|MAGNITUD(?:ES)?|M(?:ww|w|s|b|L|d|e)?)"
#: `de`, `momento de`, `estimada de`, `=`, `:`… Entre el token y la cifra puede ir
#: cualquier ristra de estas palabras, y ninguna cambia lo que la frase afirma.
_CONECTOR = (
    r"(?:\s*[=:])?\s*"
    r"(?:(?i:de|del|momento|estimada|estimado|local|aproximada"
    r"|máxima|maxima|preliminar|cercana|alrededor|unos|unas)\s+)*"
)
_MAGNITUD = re.compile(_ESCALA + _CONECTOR + r"(\d+(?:\.\d+)?)")
#: La palabra suelta, para el caso en que la cifra va escrita con letras («magnitud
#: siete punto uno»). Sin línea de catálogo no hay magnitud que citar de ninguna forma,
#: así que ahí la mención basta para descartar; con línea, no se toca.
_MAGNITUD_PALABRA = re.compile(r"\bmagnitud(?:es)?\b", re.IGNORECASE)
#: Qué distingue una magnitud de un identificador con una `M` delante. «El Módulo M 3
#: quedó sin revisar» disparaba el guardrail entero, que es marcar de más sobre prosa
#: verdadera — y un guardrail que marca de más se acaba desactivando. Una magnitud lleva
#: decimales, o la frase habla de un sismo; un módulo, ni una cosa ni la otra.
_HABLA_DE_SISMO = re.compile(r"sismo|terremoto|magnitud|escala|cat[aá]logo|SSN", re.IGNORECASE)

#: [T-7.27] Lo que no se puede afirmar sin una fila que lo sostenga. Se mira POR FRASE
#: y se exige sujeto + verbo, no la palabra suelta: «Ninguna estación corroboró el
#: evento» es exactamente lo que el texto determinista escribe cuando no hay red, y un
#: guardrail que lo rechazara pondría al respaldo en contra del proveedor que respalda.
#:
#: ⚠️ [T-7.27·A] `no` y `sin` son las dos palabras más comunes del castellano, y con la
#: exención por FRASE ENTERA bastaba una de ellas en cualquier posición para desactivar
#: la guarda: «Tres estaciones detectaron el arribo **sin** retraso» y «La estación 3
#: corroboró el evento, aunque **no** se registró su pico» pasaban las dos, MEDIDO. La
#: negación solo exime cuando GOBIERNA la afirmación, o sea cuando va delante de ella
#: (ver `_afirma_sin_respaldo`).
_NEGACION = re.compile(r"\b(no|ni|ning[uú]n\w*|sin|nadie|tampoco|nunca|jam[aá]s)\b", re.IGNORECASE)
_SUJETO_ESTACION = re.compile(r"estaci[oó]n\w*", re.IGNORECASE)
_VERBO_DETECCION = re.compile(
    r"detect\w*|corrobor\w*|registr\w*|midi\w*|super[óo]\w*", re.IGNORECASE
)
_SUJETO_FOTO = re.compile(r"fotograf\w*|im[aá]gen\w*|\bfoto\b", re.IGNORECASE)
#: `aparec\w*` y `document\w*` faltaban, y son los dos verbos naturales: «en la foto
#: **aparece** una columna agrietada», «las fotografías **documentan** daño». Sin ellos
#: la guarda cazaba la frase exacta de su propia prueba y poco más.
_VERBO_OBSERVACION = re.compile(
    r"muestr\w*|se (?:observ|aprecia|ve|distingue|advierte)\w*|visible\w*|revela\w*"
    r"|aparec\w*|document\w*|refleja\w*|capta\w*",
    re.IGNORECASE,
)
#: [T-7.27·A] Citar una estación POR SU ORDEN («la estación 2»). El orden es lo ÚNICO
#: con lo que la prosa puede nombrar una fila —el prompt de sistema se lo dice—, así que
#: un orden que no existe en la tabla es una fila inventada. Esta guarda cubre el estado
#: que la otra no veía: `station_count > 0` con la tabla vacía, que es alcanzable en
#: producción (son dos consultas independientes del builder) y en el que la condición
#: anterior se apagaba entera.
_ORDEN_DE_ESTACION = re.compile(
    r"\bestaci[oó]n(?:es)?\s+(?:n[uú]mero\s+)?(\d{1,3})\b", re.IGNORECASE
)
#: «4 estaciones». La cifra va DELANTE, y por eso es otro patrón y no el mismo.
_CONTEO_DE_ESTACIONES = re.compile(r"\b(\d{1,3})\s+estaci[oó]n", re.IGNORECASE)
#: Fin de frase. La unidad de análisis es la frase porque la negación gobierna la suya
#: y no la del párrafo.
_FRASE = re.compile(r"(?<=[.;:!?])\s+|\n+")

#: [T-7.27·A] Lo que NO puede volver del proveedor, pase lo que pase.
#:
#: `guard` miraba secciones, veredicto ajeno, cifras y afirmaciones sin fila, y NADA de
#: lo que el texto devuelto pudiera llevar dentro. Es un camino de vuelta que esta ficha
#: abre —el modelo ve fotografías— y que nadie vigilaba: la prosa se usa verbatim y
#: acaba en un PDF firmado. Se vigilan los dos identificadores exactos que la allowlist
#: de `redact.py` existe para retener, que son además los dos que el móvil hornea en el
#: píxel de cada fotografía de evidencia.
#:
#: Un par de coordenadas decimales con cuatro o más decimales: es la forma con la que
#: `watermark.ts::fmtGps` las dibuja, y ningún hecho redactado lleva nada parecido.
_COORDENADAS = re.compile(r"-?\d{1,3}\.\d{4,}\s*[,;]\s*-?\d{1,3}\.\d{4,}")
#: Una ristra hexadecimal larga: un `sub` de Cognito, un `event_id`, una clave de S3.
#: Se exige que MEZCLE cifras y letras a-f para no marcar una fecha (`20260921`) ni una
#: palabra castellana: marcar de más sobre prosa verdadera es cómo muere un guardrail.
_HEX_LARGO = re.compile(r"\b(?=[0-9a-fA-F]*[0-9])(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{8,}\b")

#: [T-7.27] Margen para todo lo que NO son fotos: el prompt de sistema, los hechos
#: serializados y el sobre JSON. Medido en `tests/narrative/test_peso_del_prompt.py`
#: sobre el peor caso —seis fotos, red entera, cronología y daños—, que es el único
#: incidente en el que esta cota puede llegar a importar.
MARGEN_TEXTO_BYTES = 64 * 1024

#: Cota superior del cuerpo de la petición, **derivada** del presupuesto de las fotos:
#: base64 son 4 bytes por cada 3. Tecleada, se quedaría vieja el día que alguien suba
#: la calidad de las derivadas — y un prompt que no cabe falla justo en el incidente
#: más cargado, que es el que importa y el que nadie tiene delante mientras programa.
TOPE_PETICION_BYTES = math.ceil(PRESUPUESTO_FOTOS_BYTES * 4 / 3) + MARGEN_TEXTO_BYTES


def _allowed_measurements(facts: NarrativeFacts) -> set[float]:
    """Valores con unidad que aparecen en los hechos, redondeados como se imprimen."""
    raw: list[float | None] = [facts.peak_pga_g, facts.peak_pgv_cms]
    # [T-7.27] Y las de la tabla por estación. Sin esto, la prosa que cita BIEN el
    # `0.012 g` de la estación 2 se descartaba por inventada: el dato que esta ficha
    # añade habría sido una degradación permanente en cuanto el modelo lo usara.
    for e in facts.stations:
        raw += [e.peak_pga_g, e.umbral_pga_g]
    basis = facts.basis if isinstance(facts.basis, dict) else {}
    for block in ("evidence", "params"):
        for value in (basis.get(block) or {}).values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                raw.append(float(value))
    allowed: set[float] = set()
    for value in raw:
        if value is None:
            continue
        allowed.add(float(value))
        # La prosa cita con los decimales del documento: 0.0812 se imprime "0.081".
        allowed.update(round(float(value), digits) for digits in (0, 1, 2, 3))
    return allowed


def guard(sections: dict[str, str], facts: NarrativeFacts) -> str | None:
    """Razón por la que se descarta la respuesta, o ``None`` si es aceptable."""
    faltantes = [t for t in SECTION_TITLES if not (sections.get(t) or "").strip()]
    if faltantes:
        return f"secciones ausentes o vacías: {', '.join(faltantes)}"
    sobrantes = [t for t in sections if t not in SECTION_TITLES]
    if sobrantes:
        return f"secciones no previstas: {', '.join(sorted(sobrantes))}"

    texto = "\n".join(sections[t] for t in SECTION_TITLES)
    if len(texto) > MAX_TOTAL_CHARS:
        return f"respuesta demasiado larga ({len(texto)} caracteres)"

    propio = facts.verdict_label
    ajenos = sorted(
        {label for label in STATUS_LABELS.values() if label != propio and label in texto}
        | {
            status
            for status in STATUS_LABELS
            if status != facts.verdict_status and re.search(rf"\b{status}\b", texto)
        }
    )
    if ajenos:
        return f"menciona un veredicto distinto del dictaminado: {', '.join(ajenos)}"

    permitidas = _allowed_measurements(facts)
    inventadas = sorted(
        {
            f"{m.group(1)} {m.group(2)}"
            for m in _MEASUREMENT.finditer(texto)
            if not any(abs(float(m.group(1)) - a) <= _TOLERANCE for a in permitidas)
        }
    )
    if inventadas:
        return f"cita mediciones que no están en los hechos: {', '.join(inventadas)}"

    # [T-7.27] La magnitud no la mide este sistema. Viene del catálogo del SSN y solo
    # existe si hay línea de catálogo; sin ella, cualquier «M 7.1» es un número puesto
    # en un documento que se firma.
    linea = facts.catalog_line or ""
    del_catalogo = {m.group(1) for m in _MAGNITUD.finditer(linea)}
    magnitudes = sorted(_magnitudes_citadas(texto) - del_catalogo)
    if magnitudes:
        return f"cita una magnitud que no está en la línea de catálogo: {', '.join(magnitudes)}"
    # Y la que va escrita con letras, que no tiene cifra que comparar («magnitud siete
    # punto uno»). Solo se descarta cuando NO hay línea de catálogo: con ella, «la
    # magnitud del catálogo» es una frase legítima y marcarla sería marcar de más. La
    # negación exime la frase ENTERA aquí —y no por posición, como en las guardas de
    # abajo— a propósito: lo único que se caza es una cifra escrita con letras, que es
    # raro, y «no hay magnitud de catálogo» es frecuente. La polaridad del error barato
    # manda.
    if not linea:
        for frase in _FRASE.split(texto):
            limpia = frase.strip()
            if _MAGNITUD_PALABRA.search(limpia) and not _NEGACION.search(limpia):
                return f"cita una magnitud sin línea de catálogo de la que venga: «{limpia[:120]}»"

    # [T-7.27] Y no se afirma sin fila. Las dos familias comparten regla porque
    # comparten el modo de fallo: el modelo rellena con lo verosímil lo que no tiene.
    ordenes = {str(e.orden) for e in facts.stations}
    inventadas = sorted({m.group(1) for m in _ORDEN_DE_ESTACION.finditer(texto)} - ordenes)
    if inventadas:
        return f"cita estaciones que no están en la tabla: {', '.join(inventadas)}"
    # Y el CONTEO, solo cuando no hay tabla: sin filas, «en 3 de las 4 estaciones» no se
    # puede sostener, así que cualquier cifra que no sea la del conteo es inventada. Con
    # tabla NO se aplica, porque ahí hablar de un subconjunto es legítimo y marcarlo sería
    # marcar de más. ⚠️ Lo que esto no caza es la cifra escrita con letras («Tres
    # estaciones…»): para eso haría falta un analizador de números en castellano, y un
    # guardrail a medias es preferible a uno que se inventa la mitad.
    if not facts.stations and facts.station_count:
        cifras = sorted({m.group(1) for m in _CONTEO_DE_ESTACIONES.finditer(texto)})
        ajenas = [c for c in cifras if c != str(facts.station_count)]
        if ajenas:
            return (
                f"cita un número de estaciones que no es el del conteo "
                f"({facts.station_count}): {', '.join(ajenas)}"
            )
    if not facts.stations and not facts.station_count:
        culpable = _afirma_sin_respaldo(texto, _SUJETO_ESTACION, _VERBO_DETECCION)
        if culpable:
            return f"afirma una detección de estaciones sin fila que la sostenga: «{culpable}»"
    if not facts.photos_attached:
        culpable = _afirma_sin_respaldo(texto, _SUJETO_FOTO, _VERBO_OBSERVACION)
        if culpable:
            return f"describe una fotografía sin fila que la sostenga: «{culpable}»"

    # [T-7.27·A] Y lo último, porque es lo que ninguna de las anteriores mira: que la
    # prosa que VUELVE no traiga un identificador que nunca salió de aquí.
    return _trae_identificadores(texto, facts)


def _magnitudes_citadas(texto: str) -> set[str]:
    """Las magnitudes que la prosa cita, sin confundirlas con un identificador.

    La forma con letra suelta (`M 3`) es ambigua: puede ser una magnitud o el nombre de
    un módulo, un eje o una sala. Se cuenta como magnitud cuando lleva decimales —una
    magnitud del SSN siempre los lleva— o cuando la frase habla de un sismo. La forma
    con la palabra entera (`magnitud 7`) nunca es ambigua.
    """
    citadas: set[str] = set()
    for frase in _FRASE.split(texto):
        habla_de_sismo = bool(_HABLA_DE_SISMO.search(frase))
        for m in _MAGNITUD.finditer(frase):
            cifra = m.group(1)
            explicita = m.group(0).lower().startswith("magnitud")
            if explicita or "." in cifra or habla_de_sismo:
                citadas.add(cifra)
    return citadas


def _trae_identificadores(texto: str, facts: NarrativeFacts) -> str | None:
    """¿Vuelve en la prosa algo que la allowlist retuvo? (`T-7.27·A`.)

    Los hex que la prosa PUEDE citar son los del folio y los de la línea de catálogo:
    el folio es el nombre público del documento y la prosa tiene que poder nombrarlo.
    Cualquier otra ristra larga que mezcle cifras y letras a-f no ha salido de los
    hechos, y lo único parecido que el modelo ha podido ver es el `sub` del operador
    dibujado en una fotografía.
    """
    par = _COORDENADAS.search(texto)
    if par:
        return f"devuelve un par de coordenadas que no está en los hechos: «{par.group(0)}»"
    permitidos = set()
    for fuente in (facts.folio, facts.catalog_line, facts.rule_set_version):
        permitidos |= {h.lower() for h in _HEX_LARGO.findall(fuente or "")}
    ajenos = sorted({h.lower() for h in _HEX_LARGO.findall(texto)} - permitidos)
    if ajenos:
        return f"devuelve identificadores que no están en los hechos: {', '.join(ajenos)}"
    return None


def _afirma_sin_respaldo(texto: str, sujeto: re.Pattern, verbo: re.Pattern) -> str | None:
    """La primera frase que afirma algo de `sujeto` con `verbo` y sin negación.

    Se devuelve la frase —recortada— y no solo un `True`: la razón acaba impresa en el
    §16 del PDF, y «el guardrail descartó la respuesta» sin decir qué frase la descartó
    obliga a adivinar contra el log del proveedor.

    ⚠️ [T-7.27·A] **La negación tiene que ir DELANTE de lo que niega.** Eximir la frase
    entera por contener `no` o `sin` en cualquier posición dejaba la guarda apagada ante
    la prosa hedgeada, que es justo la que escribe un modelo: «…detectaron el arribo sin
    retraso» quedaba exenta por el `sin` del final. Se compara contra la posición del
    sujeto y del verbo, que es donde vive la afirmación.
    """
    for frase in _FRASE.split(texto):
        limpia = frase.strip()
        if not limpia:
            continue
        s = sujeto.search(limpia)
        v = verbo.search(limpia)
        if not (s and v):
            continue
        neg = _NEGACION.search(limpia)
        if neg and neg.start() < max(s.start(), v.start()):
            continue
        return limpia[:120]
    return None


@dataclass(frozen=True, slots=True)
class ClaveOpenRouter:
    """Resultado de buscar la clave. **La ausencia y el fallo NO son lo mismo.**

    Antes de T-7.26 esto devolvía una cadena, y vacía significaba las dos cosas a la
    vez: «no hay nada configurado» y «lo hay pero no pude leerlo». Con esa confusión, un
    ``AccessDenied`` sobre el secreto —lo que pasa en la nube el primer día, mientras el
    rol de la instancia no tiene permiso— se veía exactamente igual que tener la IA
    apagada, y el PDF salía con prosa determinista **sin declarar nada**.
    """

    api_key: str
    #: Código del fallo (``AccessDeniedException``…), o ``None`` si no hubo fallo. Con
    #: ``api_key`` vacía y ``error`` a ``None``, lo que pasa es que no se configuró
    #: ningún origen de clave.
    error: str | None = None


#: El secreto existe y se leyó, pero no trae `api_key`. Es un CÓDIGO y no la frase que
#: había antes («el secreto no trae la clave 'api_key'»): `ClaveOpenRouter.error` viaja
#: a `motivo_con_causa`, cuya regla es que la causa es un nombre corto y jamás un
#: mensaje. La frase no filtraba nada —la escribíamos nosotros—, pero dejaba la regla
#: escrita sin cumplir por una rama, y una regla que se cumple «casi siempre» no se
#: puede vigilar. El papel lo imprime igual de legible: «… la clave no se pudo leer
#: (SecretoSinApiKey); texto determinista».
CODIGO_SECRETO_SIN_CLAVE = "SecretoSinApiKey"


def _codigo_de(exc: Exception) -> str:
    """Nombre corto de la causa, NUNCA el mensaje.

    El de botocore es del tipo «An error occurred (AccessDeniedException) … not
    authorized to perform secretsmanager:GetSecretValue on resource arn:aws:…:634…»: se
    lleva por delante el ARN y el número de cuenta, y esto acaba impreso en un dictamen
    que sale de la organización.
    """
    respuesta = getattr(exc, "response", None)
    if isinstance(respuesta, dict):
        codigo = (respuesta.get("Error") or {}).get("Code")
        if codigo:
            return str(codigo)
    return type(exc).__name__


def resolve_api_key(settings: Settings, *, client: Any | None = None) -> ClaveOpenRouter:
    """Clave inline (dev) o de Secrets Manager (producción). Sin clave ⇒ no se llama a nadie.

    Espejo del patrón de ``commands/keys.py``: el secreto nunca vive en el repo ni en la
    imagen, y su ausencia es fail-closed hacia el proveedor determinista. Lo que cambia
    en T-7.26 es que el fallo **vuelve con nombre**, para que quien decide (
    ``select_provider``) pueda declararlo en el papel.
    """
    if settings.openrouter_api_key:
        return ClaveOpenRouter(settings.openrouter_api_key)
    if not settings.openrouter_secret_id:
        return ClaveOpenRouter("")
    try:
        sm = client
        if sm is None:  # pragma: no cover - requiere AWS real
            import boto3  # noqa: PLC0415 - import perezoso: solo en producción

            sm = boto3.client("secretsmanager", region_name=settings.aws_region)
        raw = sm.get_secret_value(SecretId=settings.openrouter_secret_id)["SecretString"]
        payload = json.loads(raw)
        clave = str(payload.get("api_key") or "")
    except Exception as exc:  # noqa: BLE001 - un secreto irresoluble degrada, no rompe
        log.warning("narrative: no se pudo resolver la clave de OpenRouter: %s", _codigo_de(exc))
        return ClaveOpenRouter("", error=_codigo_de(exc))
    if not clave:
        # El secreto existe y se leyó, pero no trae `api_key`. Es un fallo de contenido
        # y no una ausencia de configuración: quien lo creó creyó que estaba puesto.
        return ClaveOpenRouter("", error=CODIGO_SECRETO_SIN_CLAVE)
    return ClaveOpenRouter(clave)


#: El modelo está en el catálogo y no declara la modalidad de imagen. Es un hecho del
#: modelo: hasta que se cambie el slug no hay nada que esperar.
CODIGO_SIN_MODALIDAD_DE_IMAGEN = "SinModalidadDeImagen"
#: El slug ni siquiera aparece en el catálogo. Es el caso del **slug caducado**, que
#: este módulo tenía escrito como riesgo desde T-2.42 («un default hardcodeado caducaría
#: en silencio») y que hasta hoy solo se notaba como un `HTTP 400` al redactar.
CODIGO_MODELO_NO_LISTADO = "ModeloNoListado"
#: El catálogo respondió 200 y el cuerpo no trae la lista de modelos. Es un fallo de
#: CONTENIDO, no de transporte, y por eso no se confunde con que el proveedor esté
#: caído: el que está mal es el sobre, no el cable.
CODIGO_CATALOGO_SIN_LISTA = "SinListaDeModelos"


class _CatalogoIlegible(Exception):
    """El catálogo contestó y no se pudo interpretar. Lleva el CÓDIGO como mensaje."""


@dataclass(frozen=True, slots=True)
class Vision:
    """¿Puede este modelo ver una fotografía? Y si no, por qué no.

    El motivo va dentro y no lo compone quien pregunta: son dos hechos distintos —el
    modelo no admite imágenes / no se pudo comprobar— y separarlos es lo que impide
    repetir el defecto de T-7.26, donde «no respondió» y «respondió que no» eran la
    misma frase y mandaban a depurar al sitio equivocado.
    """

    admite: bool
    motivo: str | None = None


#: Lo sabido del catálogo, por `(base_url, slug)`. **Solo se recuerdan las respuestas
#: DEFINITIVAS**: que un modelo admita imágenes es un hecho suyo y se puede memorizar;
#: que hoy no se haya podido leer el catálogo es del momento, y cachearlo dejaría la
#: redacción asistida apagada hasta el siguiente despliegue por un timeout de un martes.
_VISION_SABIDA: dict[tuple[str, str], Vision] = {}


def olvidar_vision() -> None:
    """Vacía lo recordado. Para los tests y para un reinicio en caliente: sin esto, el
    orden de ejecución decidiría cuántas veces se pregunta al catálogo."""
    _VISION_SABIDA.clear()


def _causa_http(exc: Exception) -> str:
    """`HTTP 500` cuando hubo respuesta, el tipo de la excepción cuando no la hubo.

    Misma regla que `motivo_con_causa`: un NOMBRE corto nuestro, nunca el mensaje de
    una librería ajena, porque esto se imprime en un documento que sale de la
    organización.
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return f"HTTP {status}" if isinstance(status, int) else type(exc).__name__


async def consultar_vision(
    settings: Settings, *, api_key: str, transport: Any | None = None
) -> Vision:
    """¿Declara el modelo configurado que admite imágenes? (`D-32`, criterio 1.)

    **Por qué se pregunta en vez de mandarlas y ver qué pasa.** Un modelo sin visión no
    falla limpio: unos proveedores ignoran la parte de imagen y redactan igual —y
    entonces el documento lleva prosa que dice haber visto lo que nadie miró—, otros
    devuelven un 400 que el papel imprime como «el proveedor respondió con error». Las
    dos salidas son peores que un `GET` al catálogo.

    Se paga **una vez por proceso** (ver `_VISION_SABIDA`). Engancharla además al
    arranque de la API es una línea en el `lifespan`, fuera de este módulo: aquí lo que
    importa es que ningún dictamen la pague dos veces ni se salte la comprobación.
    """
    clave = (settings.openrouter_base_url, settings.openrouter_model)
    recordada = _VISION_SABIDA.get(clave)
    if recordada is not None:
        return recordada
    try:
        catalogo = await _pedir_catalogo(settings, api_key=api_key, transport=transport)
    except _CatalogoIlegible as exc:
        # El proveedor contestó: lo que no se pudo es entender lo que dijo.
        log.warning("narrative: catálogo de modelos ilegible: %s", exc)
        return Vision(False, motivo_con_causa(MOTIVO_VISION_ILEGIBLE, str(exc)))
    except Exception as exc:  # noqa: BLE001 - fail-open: la evidencia sale igual
        # ⚠️ Aquí NO se estrena vocabulario. El catálogo es una petición al MISMO
        # proveedor, así que un 401 es «no aceptó la clave» y un 500 es «respondió con
        # error», exactamente como si hubiera fallado al redactar (`_motivo_del_fallo`,
        # T-7.26). Decir «no se pudo comprobar si el modelo admite imágenes (HTTP 401)»
        # sería técnicamente cierto y operativamente inútil: con la clave revocada
        # mandaría a quien lee el papel a mirar el catálogo en vez del secreto, que es
        # el defecto que T-7.26 vino a cerrar.
        log.warning("narrative: no se pudo leer el catálogo de modelos: %s", _causa_http(exc))
        return Vision(False, _motivo_del_fallo(exc))

    fila = next(
        (f for f in catalogo if isinstance(f, dict) and f.get("id") == settings.openrouter_model),
        None,
    )
    if fila is None:
        veredicto = Vision(False, motivo_con_causa(MOTIVO_SIN_VISION, CODIGO_MODELO_NO_LISTADO))
    else:
        modalidades = (fila.get("architecture") or {}).get("input_modalities") or []
        veredicto = (
            Vision(True)
            if "image" in modalidades
            else Vision(False, motivo_con_causa(MOTIVO_SIN_VISION, CODIGO_SIN_MODALIDAD_DE_IMAGEN))
        )
    _VISION_SABIDA[clave] = veredicto
    return veredicto


async def _pedir_catalogo(
    settings: Settings, *, api_key: str, transport: Any | None = None
) -> list:
    import httpx  # noqa: PLC0415 - import perezoso: el camino apagado no lo paga

    kwargs: dict[str, Any] = {"timeout": settings.openrouter_timeout_s}
    if transport is not None:
        kwargs["transport"] = transport
    async with httpx.AsyncClient(**kwargs) as client:
        resp = await client.get(
            f"{settings.openrouter_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "TAKAB Ailert"},
        )
        resp.raise_for_status()
        try:
            datos = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise _CatalogoIlegible(type(exc).__name__) from exc
    if not isinstance(datos, dict) or not isinstance(datos.get("data"), list):
        # Sin lista de modelos no se puede afirmar que el modelo admita imágenes, y lo
        # que no se puede afirmar no se da por bueno: `D-32` pide una DECLARACIÓN.
        raise _CatalogoIlegible(CODIGO_CATALOGO_SIN_LISTA)
    return datos["data"]


def contenido_de_usuario(req: NarrativeRequest) -> str | list[dict]:
    """El mensaje de usuario: texto, o texto + fotografías si las hay (`D-32`).

    **Sin imágenes devuelve la cadena de siempre**, no una lista de una parte: un
    incidente sin fotografías no tiene por qué pagar una forma que algunos proveedores
    tratan distinto, y así el camino que ya estaba probado sigue siendo el mismo.

    Los bytes son los que le llegan en `req.images`, y llegan ya derivados, verificados
    y **con la banda de la marca de agua tapada** por `redact.imagenes_de`. Aquí no se
    abre ninguna imagen ni se re-encoda nada: esta función compone el sobre, y el día
    que decidiera por su cuenta qué píxeles manda, la huella que la procedencia anota
    (`ImagenAdjunta.sha256_enviado`) dejaría de ser la de lo que salió.
    """
    texto = user_prompt(req.facts)
    if not req.images:
        return texto
    partes: list[dict] = [{"type": "text", "text": f"{texto}\n\n{INSTRUCCION_FOTOS}"}]
    for n, imagen in enumerate(req.images, start=1):
        # El rótulo va ANTES de su imagen: es lo único que le dice al modelo de qué
        # reporte es la que viene, y sin eso «di de qué reporte es cada una» le pide
        # algo que no puede saber.
        partes.append({"type": "text", "text": rotulo_de_foto(n, imagen.reporte)})
        b64 = base64.b64encode(imagen.jpeg).decode("ascii")
        partes.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    return partes


def cuerpo_de(req: NarrativeRequest) -> dict:
    """El cuerpo JSON de la petición. Se compone aparte de mandarlo para poder MEDIRLO
    sin salir a la red — ver `tests/narrative/test_peso_del_prompt.py`."""
    return {
        "model": req.model,
        "messages": [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": contenido_de_usuario(req)},
        ],
        "max_tokens": MAX_OUTPUT_TOKENS,
        "response_format": {"type": "json_object"},
        "usage": {"include": True},
    }


def _content_of(payload: dict) -> str | None:
    """El texto de la respuesta, o ``None`` si el sobre no tiene la forma esperada.

    No lanza a propósito: se llama ANTES del ``try`` que interpreta, porque el hash de
    la salida tiene que existir aunque el contenido resulte ilegible.
    """
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return content if isinstance(content, str) else None


def _sha256_de(content: str | None) -> str | None:
    """Huella de la salida. ``None`` si no volvió nada: fingir el hash de una salida
    que no existe sería inventarse evidencia."""
    if content is None:
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _parse(content: str | None) -> dict[str, str]:
    """Secciones del JSON de respuesta. Tolera el ```json de algunos modelos."""
    if content is None:
        raise ValueError("la respuesta no trae contenido")
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    data = json.loads(text)
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, dict):
        raise ValueError("la respuesta no trae un objeto 'sections'")
    return {str(k): str(v) for k, v in sections.items()}


def _motivo_del_fallo(exc: Exception) -> str:
    """Por qué no hubo prosa del proveedor. **«No respondió» y «respondió que no» no
    son lo mismo, y confundirlos manda a depurar al sitio equivocado.**

    Medido con la clave revocada: OpenRouter devuelve un ``401`` —o sea que respondió,
    y rápido— y el papel imprimía «el proveedor no respondió (HTTPStatusError)». Quien
    leyera eso iría a mirar la red; el problema estaba en el secreto. Es el mismo tipo
    de frase conservadora-pero-falsa que esta ficha corrigió en la cuota («agotada»
    contra «no había»).

    El estado HTTP entra en la causa porque es el dato que decide a dónde ir: 401/403
    al secreto, 400 al slug del modelo, 5xx a esperar. Sale de ``response.status_code``,
    que solo tienen las excepciones que SÍ traen respuesta (``HTTPStatusError``); un
    timeout o un fallo de DNS no lo tienen y caen en «no respondió», que entonces es
    verdad.
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if not isinstance(status, int):
        return motivo_con_causa(MOTIVO_PROVEEDOR_MUDO, type(exc).__name__)
    if status in (401, 403):
        return motivo_con_causa(MOTIVO_PROVEEDOR_CREDENCIAL, f"HTTP {status}")
    return motivo_con_causa(MOTIVO_PROVEEDOR_ESTADO, f"HTTP {status}")


#: [T-7.27·A] Fallos en los que **el socket no llega a abrirse**, por su nombre de clase
#: —`httpx` no se importa aquí, que es import perezoso a propósito—. En ninguno de ellos
#: salió un solo byte de la nube, así que anotar fotografías enviadas sería escribir una
#: transferencia que no ocurrió en un registro que la regla de oro 11 no poda nunca.
#: `ReadTimeout` NO está: ahí la petición sí se emitió y lo que faltó fue la respuesta.
_SIN_SOCKET = frozenset(
    {"ConnectError", "ConnectTimeout", "ProxyError", "UnsupportedProtocol", "InvalidURL"}
)


def _salieron_las_fotos(exc: Exception) -> bool:
    """¿La petición llegó a emitirse, pese al fallo?

    El comentario de `generate` ya decía la regla —«anotarlo antes diría que unas
    fotografías viajaron cuando el socket pudo no abrirse siquiera»— y la rama de fallo,
    veinte líneas antes, llamaba a `_huellas` en exactamente ese caso.
    """
    return type(exc).__name__ not in _SIN_SOCKET


def _huellas(req: NarrativeRequest) -> tuple[HuellaEnviada, ...]:
    """Las huellas de las fotografías que iban en la petición.

    Van las DOS de cada una —la de los bytes que salieron y la de la derivada que
    imprime el papel— porque desde el tapado de la marca de agua no son el mismo número:
    ver `HuellaEnviada`.

    Se DEDUPLICA por lo enviado, conservando el orden: la misma fotografía puede estar
    en dos reportes de daño del mismo incidente, y entonces salía dos veces en un
    registro cuya única pregunta es *cuáles* salieron, no cuántas veces.
    """
    vistas: set[str] = set()
    salida: list[HuellaEnviada] = []
    for i in req.images:
        if i.sha256_enviado in vistas:
            continue
        vistas.add(i.sha256_enviado)
        salida.append(HuellaEnviada(enviado=i.sha256_enviado, impreso=i.sha256))
    return tuple(salida)


class OpenRouterProvider:
    """Cliente HTTP de OpenRouter con degradación total al determinista."""

    name = NAME

    def __init__(self, settings: Settings, *, api_key: str = "", transport: Any | None = None):
        self._settings = settings
        self._api_key = api_key
        self._transport = transport

    async def admite_imagenes(self) -> Vision:
        """Lo que `build_narrative` pregunta antes de dejar que este proveedor corra.

        Vive como método —y no como función suelta— porque la clave y el transporte los
        tiene el proveedor: quien decide no los conoce, y pasárselos por parámetro
        habría metido el secreto en la firma de `build_narrative`.
        """
        return await consultar_vision(
            self._settings, api_key=self._api_key, transport=self._transport
        )

    async def generate(self, req: NarrativeRequest) -> Narrative:
        started = time.monotonic()
        # [T-7.26] La versión se calcula ANTES de salir y acompaña a la respuesta pase
        # lo que pase: que el prompt se mandó es un hecho aunque no vuelva nada.
        version = prompt_version()
        # [T-7.27·A] El cuerpo se compone UNA vez —el base64 de seis fotografías no es
        # gratis— y se MIDE antes de emitirlo. `TOPE_PETICION_BYTES` era hasta hoy una
        # cota declarada que nadie leía en producción.
        cuerpo = cuerpo_de(req)
        pesa = len(json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"))
        if pesa > TOPE_PETICION_BYTES:
            log.warning(
                "narrative: la petición pesa %s B y el tope es %s B; se degrada",
                pesa,
                TOPE_PETICION_BYTES,
            )
            return self._degraded(
                req,
                motivo_con_causa(MOTIVO_PETICION_ENORME, f"{pesa} B"),
                prompt_version=version,
            )
        try:
            payload = await self._post(cuerpo)
        except Exception as exc:  # noqa: BLE001 - fail-open: la evidencia sale igual
            log.warning("narrative: OpenRouter falló (%s); se degrada a determinista", exc)
            return self._degraded(
                req,
                _motivo_del_fallo(exc),
                prompt_version=version,
                # ⚠️ Solo si la petición LLEGÓ A SALIR. Ver `_salieron_las_fotos`.
                photos_sent=_huellas(req) if _salieron_las_fotos(exc) else (),
            )

        elapsed_ms = int((time.monotonic() - started) * 1000)
        # [T-7.26] El hash es de lo que devolvió el modelo, TAL CUAL: antes de parsear,
        # antes del guardrail y antes de recortar. Si la respuesta se descarta es cuando
        # más falta hace — es el único rastro de qué se propuso, contable contra el log
        # del proveedor.
        content = _content_of(payload)
        salida = _sha256_de(content)
        # [T-7.27] Lo que SALIÓ de la nube en esta petición. Se anota aquí —y no al
        # componer el cuerpo— porque a partir de este punto la petición ya se emitió:
        # anotarlo antes diría que unas fotografías viajaron cuando el socket pudo no
        # abrirse siquiera.
        fotos = _huellas(req)
        try:
            sections = _parse(content)
        except Exception as exc:  # noqa: BLE001
            log.warning("narrative: respuesta de OpenRouter ilegible: %s", exc)
            return self._degraded(
                req,
                MOTIVO_RESPUESTA_ILEGIBLE,
                prompt_version=version,
                output_sha256=salida,
                photos_sent=fotos,
            )

        rejected = guard(sections, req.facts)
        if rejected:
            log.warning("narrative: guardrail descartó la respuesta — %s", rejected)
            return self._degraded(
                req,
                motivo_guardrail(rejected),
                prompt_version=version,
                output_sha256=salida,
                photos_sent=fotos,
            )

        usage = payload.get("usage") or {}
        return Narrative(
            sections=tuple((t, sections[t].strip()) for t in SECTION_TITLES),
            provider=NAME,
            model=payload.get("model") or req.model,
            latency_ms=elapsed_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=usage.get("cost"),
            prompt_version=version,
            output_sha256=salida,
            photos_sent=fotos,
        )

    async def _post(self, cuerpo: dict) -> dict:
        import httpx  # noqa: PLC0415 - import perezoso: el camino apagado no lo paga

        s = self._settings
        kwargs: dict[str, Any] = {"timeout": s.openrouter_timeout_s}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.post(
                f"{s.openrouter_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    # Cortesía de OpenRouter: identifica la app en su consola.
                    "X-Title": "TAKAB Ailert",
                },
                json=cuerpo,
            )
            resp.raise_for_status()
            return resp.json()

    def _degraded(
        self,
        req: NarrativeRequest,
        reason: str,
        *,
        prompt_version: str | None = None,
        output_sha256: str | None = None,
        photos_sent: tuple[HuellaEnviada, ...] = (),
    ) -> Narrative:
        # ⚠️ La constante, no la cadena. `narrative._hubo_redaccion_cobrable` decide SI
        # SE COBRA comparando `provider` contra `deterministic.NAME`: con el literal
        # tecleado aquí, la decisión de dinero dependía de que dos cadenas escritas en
        # dos ficheros distintos siguieran coincidiendo.
        return Narrative(
            sections=sections_for(req.facts),
            provider=DETERMINISTA,
            model=req.model or None,
            degraded_reason=reason,
            prompt_version=prompt_version,
            output_sha256=output_sha256,
            photos_sent=photos_sent,
        )
