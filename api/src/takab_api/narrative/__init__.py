"""Capa narrativa del dictamen (T-2.42): prosa que RODEA al veredicto.

El punto de entrada es ``build_narrative``. Elige proveedor por configuración y devuelve
siempre una ``Narrative`` — nunca lanza, nunca devuelve ``None``. Un dictamen sin prosa
sigue siendo un dictamen válido; un dictamen que no se puede exportar, no.

Por qué esta capa no puede tocar el veredicto (regla de oro 1):

1. ``Narrative`` no tiene campo de veredicto: no hay dónde ponerlo.
2. ``narrative/`` no importa ``dictamen.rules`` ni ``dictamen.service``: no puede
   siquiera invocar al motor que dictamina.
3. ``pdf.render`` produce el mismo veredicto con o sin prosa.

Las tres son contract-tests (``tests/narrative/test_contract.py``), no promesas escritas.

[T-7.26] LAS DOS PROMESAS DE ESTE MÓDULO, QUE ERAN FALSAS
---------------------------------------------------------

**«Nunca lanza».** Lo prometía este mismo docstring y no era cierto: ``facts_from``,
las dos llamadas de cuota, ``select_provider`` y el propio respaldo determinista vivían
FUERA del ``try``. Medido: ``build_narrative(model(channels=None), Settings())`` lanzaba
``TypeError`` desde ``redact.py`` y la excepción salía a ``generate_report`` — o sea que
**un dato raro del incidente impedía exportar el dictamen entero**. Hoy el cinturón
envuelve TODOS los tramos (``TRAMOS``) y cada uno tiene su degradación declarada; la
guarda lo mide **renderizando el PDF**, no parándose en esta función.

⚠️ El ejemplo que se citaba aquí era ``opened_at=None``, y era el ejemplo equivocado:
con ese modelo la exportación se cae igual, pero **más abajo y por su cuenta** —
``membrete.seal(m.opened_at)`` → ``fpdf.set_creation_date`` → ``TypeError: date should
be a datetime``. Es el SELLO del documento pidiendo su fecha, no la prosa; es otro
defecto, con otro nombre, y no es de esta capa. Citarlo aquí hacía que la frase «ya no
impide exportar» fuera falsa justamente para el dato que la ilustraba. Re-medido sobre
el modelo de ``tests/dictamen/test_pdf.py``: con ``channels=None`` / ``actions=None`` /
``dictamens=None`` el PDF sale — 103 762, 104 305 y 104 056 bytes, o sea **104 kB**
decimales y 101–102 KiB.

⚠️ Y la unidad no es pedantería: aquí se escribió primero «≈104 KB», luego «102 KB los
tres» y una refutación de la primera cifra que el dato no sostenía. Las dos eran LA
MISMA medición en unidades distintas, y refutar una medición correcta es peor que no
citarla: manda a quien venga detrás a buscar un cambio que nunca ocurrió.

⚠️ ``evidence=None`` es la MISMA familia que ``opened_at``: la prosa degrada como debe y
el papel se cae igual, en ``dictamen/pdf.py::_raw_section``. Otro defecto, otro sitio,
fuera de esta ficha — y con guarda que lo fija:
``tests/narrative/test_degradacion_declarada.py::test_el_dato_que_rompe_la_FORMA_DE_ONDA_...``.

**«Un fallback no puede ser `ok`».** El cinturón exterior devolvía el determinista
**sin estampar ``degraded_reason``**, así que el PDF no imprimía «NARRATIVA DEGRADADA»
por esa vía. Y la confusión más cara estaba un paso antes: un secreto ilegible se veía
igual que la IA apagada. Ahora son dos cosas distintas y se llaman distinto:

* **APAGADO a propósito** (sin flag, sin slug) — no es degradación, no lleva motivo.
* **ENCENDIDO PERO NO PUDE** (clave irresoluble, proveedor caído, cuota, tope) — sí lo
  es, y va al papel con su razón.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from takab_api.narrative.base import (
    MOTIVO_CLAVE_ILEGIBLE,
    MOTIVO_CUOTA_ILEGIBLE,
    MOTIVO_ELECCION,
    MOTIVO_PROVEEDOR,
    MOTIVO_RESPALDO_CAIDO,
    MOTIVO_SIN_CLAVE,
    MOTIVO_SIN_HECHOS,
    SUFIJO_DETERMINISTA,
    Narrative,
    NarrativeFacts,
    NarrativeProvider,
    NarrativeRequest,
    motivo_con_causa,
)
from takab_api.narrative.deterministic import NAME as DETERMINISTA
from takab_api.narrative.deterministic import DeterministicProvider
from takab_api.narrative.quota import MOTIVO_AGOTADA, acumular, leer_estado
from takab_api.narrative.redact import facts_from
from takab_api.settings import Settings

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncConnection

    from takab_api.dictamen.model import ReportModel

log = logging.getLogger("takab_api.narrative")

__all__ = [
    "Narrative",
    "NarrativeFacts",
    "NarrativeProvider",
    "NarrativeRequest",
    "ProveedorElegido",
    "apply_narrative",
    "build_narrative",
    "TRAMOS",
    "facts_from",
    "select_provider",
]

#: Título de la única sección que sale cuando no hubo ni hechos que redactar. Es un
#: título de los seis a propósito: el que existe justamente para nombrar lo que falta.
TITULO_LIMITACIONES = "Limitaciones y datos ausentes"

#: [T-7.26·2ª vuelta] Los tramos de ``build_narrative`` que pueden fallar. Medido sobre
#: el último commit (``git show 3a72ac1:api/src/takab_api/narrative/__init__.py``), la
#: función tenía **un solo ``try``**, alrededor de ``chosen.generate``: **uno de los
#: seis**. ``select_provider`` vivía fuera de todo ``try`` y el respaldo determinista se
#: llamaba desnudo — o sea, el mismo modo de fallo que la ficha vino a cerrar, recreado
#: un nivel más abajo.
#:
#: Es una tupla y no una frase en prosa porque ``test_nunca_lanza.py`` **se parametriza
#: sobre ella**: dar de alta un tramo aquí sin escribir su sabotaje deja la suite en
#: rojo, que es lo contrario de lo que pasó con el número escrito a mano.
TRAMOS: tuple[str, ...] = (
    "elegir proveedor",
    "redactar los hechos",
    "leer la cuota",
    "llamar al proveedor",
    "cobrar",
    "el respaldo determinista",
)


@dataclass(frozen=True, slots=True)
class ProveedorElegido:
    """Quién va a redactar, con qué modelo y —si hubo que renunciar— por qué.

    El tercer campo es la razón de ser de este objeto: mientras ``select_provider``
    devolvía una tupla de dos, **la renuncia no tenía dónde viajar** y el motivo se
    perdía entre la decisión y el papel.
    """

    provider: NarrativeProvider
    model: str
    #: ``None`` cuando el determinista es lo que se pidió (IA apagada). Con texto,
    #: cuando la IA estaba encendida y no se pudo usar.
    degraded_reason: str | None = None


def select_provider(settings: Settings, *, transport: Any | None = None) -> ProveedorElegido:
    """Proveedor activo, slug de modelo y motivo de degradación. Por defecto, determinista.

    Tres condiciones para salir a la red, todas necesarias: el flag encendido, un slug
    de modelo y una clave resoluble. **Las dos primeras que falten no son una
    degradación** — son la configuración pedida, y por eso no marcan el PDF.

    La tercera sí lo es, y es la que se confundía: quien enciende la perilla y pone un
    slug ESTÁ PIDIENDO redacción asistida. Que no haya clave no es lo que pidió; es que
    no se pudo. Eso va al papel.

    ``transport`` es la **costura de pruebas**, y existe por un agujero medido: sin ella
    esta función construía ``OpenRouterProvider`` sin transporte inyectable, así que
    **el camino que el despliegue enciende de verdad no se podía ejercer entero**. Toda
    prueba del camino feliz construía el proveedor a mano, y la cadena que pide el
    criterio 3 de la ficha —``usage.cost`` → ``Narrative.cost_usd`` → ``acumular`` →
    ``ai_spend.spent_usd``— quedaba probada por mitades con dobles en los dos extremos.
    Lo que no se puede ejercer, no está defendido.
    """
    if not settings.openrouter_enabled or not settings.openrouter_model:
        return ProveedorElegido(DeterministicProvider(), "")

    from takab_api.narrative.openrouter import (  # noqa: PLC0415 - solo si está encendido
        OpenRouterProvider,
        resolve_api_key,
    )

    clave = resolve_api_key(settings)
    if not clave.api_key:
        motivo = (
            motivo_con_causa(MOTIVO_CLAVE_ILEGIBLE, clave.error)
            if clave.error
            else MOTIVO_SIN_CLAVE
        )
        log.warning("narrative: %s", motivo)
        return ProveedorElegido(DeterministicProvider(), "", degraded_reason=motivo)
    return ProveedorElegido(
        OpenRouterProvider(settings, api_key=clave.api_key, transport=transport),
        settings.openrouter_model,
    )


async def build_narrative(
    model: ReportModel,
    settings: Settings | None = None,
    *,
    provider: NarrativeProvider | None = None,
    damage_counts: dict[str, int] | None = None,
    conn: AsyncConnection | None = None,
    tenant_id: str | None = None,
    actor: str | None = None,
    transport: Any | None = None,
) -> Narrative:
    """Prosa del dictamen. **Nunca lanza**: un fallo aquí degrada, no rompe la evidencia.

    Los tramos que pueden fallar están enumerados en ``TRAMOS`` y **todos** tienen su
    cinturón y su motivo. Ninguno de ellos puede impedir que se genere el papel — es la
    misma doctrina que el CCTV y que el miniSEED: un fallo de una sección degrada esa
    sección, jamás la exportación.

    ⚠️ Antes de esta ficha el cinturón era **uno de los seis** tramos (ver ``TRAMOS``):
    faltaban ``select_provider`` —fuera de todo ``try``— y el propio respaldo
    determinista dentro de ``_degradar``. Por eso el censo es hoy una tupla sobre la que
    se parametriza la guarda, y no un número escrito en una frase: un número en prosa se
    queda viejo sin ponerse rojo, que es exactamente lo que le pasó al anterior.

    ``transport`` es la costura de pruebas de ``select_provider`` — ver allí por qué
    existe. En producción va a ``None`` y ``httpx`` usa el suyo; con ``provider``
    explícito se ignora, porque entonces el proveedor ya viene armado por el llamador.

    [T-5.18] Con `conn` y `tenant_id`, ADEMÁS cobra contra la cuota mensual del
    cliente. Agotada, se cae al determinista **y se declara** — jamás se falla la
    exportación: el PDF es una superficie de vida y un tope de gasto no puede
    convertirse en una negación de evidencia.

    Sin los dos argumentos no hay cuota que cobrar y el comportamiento es
    exactamente el de antes. Es lo que mantiene fuera del camino a los tests y a
    cualquier llamador que no tenga transacción.
    """
    s = settings or Settings()
    if provider is not None:
        elegido = ProveedorElegido(provider, s.openrouter_model)
    else:
        # ── tramo «elegir proveedor» ─────────────────────────────────────────
        # Lee ajustes y SALE A SECRETS MANAGER. Vivía fuera de todo `try`, así que un
        # boto3 que reviente por su cuenta —no el `get_secret_value`, que ya está
        # cubierto, sino el cliente al construirse— tumbaba la exportación entera.
        try:
            elegido = select_provider(s, transport=transport)
        except Exception as exc:  # noqa: BLE001
            log.exception("narrative: no se pudo elegir el proveedor de redacción")
            elegido = ProveedorElegido(
                DeterministicProvider(),
                "",
                degraded_reason=motivo_con_causa(MOTIVO_ELECCION, type(exc).__name__),
            )

    # ── tramo «redactar los hechos» ──────────────────────────────────────────
    try:
        req = NarrativeRequest(
            facts=facts_from(model, damage_counts=damage_counts), model=elegido.model
        )
    except Exception as exc:  # noqa: BLE001 - sin hechos no hay prosa, pero sí dictamen
        log.exception("narrative: no se pudieron redactar los hechos del incidente")
        return _sin_hechos(exc)

    # La renuncia de configuración se estampa ya: el elegido es el determinista y lo
    # que falta es decir por qué no fue el otro.
    if elegido.degraded_reason:
        return await _degradar(req, elegido.degraded_reason)

    cobrable = conn is not None and tenant_id is not None and _sale_a_la_red(elegido.provider)
    if cobrable:
        # ── tramo «leer la cuota» ────────────────────────────────────────────
        try:
            estado = await leer_estado(
                conn,  # type: ignore[arg-type]
                tenant_id,  # type: ignore[arg-type]
                cap_usd=s.ai_monthly_cap_usd,
                actor=actor,
            )
        except Exception as exc:  # noqa: BLE001
            # Sin saber cuánto se lleva gastado no se sale a la red: fail-closed hacia
            # el determinista. ⚠️ Esto puede dejar la transacción del request abortada
            # —una consulta fallida envenena la transacción entera— y entonces la
            # exportación caerá por su cuenta y con su propio nombre. Lo que NO puede
            # pasar es que caiga con el nombre de la prosa.
            log.exception("narrative: no se pudo leer la cuota de IA; se degrada")
            return await _degradar(req, motivo_con_causa(MOTIVO_CUOTA_ILEGIBLE, type(exc).__name__))
        if estado.exhausted:
            log.warning(
                "narrative: la cuota de IA no permite la llamada (%s: %.4f/%.2f USD)"
                " → determinista",
                estado.period,
                estado.spent_usd,
                estado.cap_usd,
            )
            # ⚠️ Nunca un `or ""`: un corte SIN motivo deja el PDF cortando y callando,
            # que es exactamente el defecto que esta ficha vino a cerrar. `exhausted`
            # implica motivo —la propiedad lo deriva de los mismos dos números que
            # decidieron el corte—, y si algún día dejara de implicarlo, la frase
            # conservadora sigue siendo verdadera: la cuota no permitió la llamada.
            return await _degradar(req, estado.motivo or MOTIVO_AGOTADA)

    # ── tramo «llamar al proveedor» ──────────────────────────────────────────
    try:
        narrativa = await elegido.provider.generate(req)
    except Exception as exc:  # noqa: BLE001 - último cinturón: la exportación sale igual
        log.warning("narrative: el proveedor %r lanzó (%s); se degrada", elegido.provider, exc)
        return await _degradar(req, motivo_con_causa(MOTIVO_PROVEEDOR, type(exc).__name__))

    # ── tramo «cobrar» ───────────────────────────────────────────────────────
    if cobrable and _hubo_redaccion_cobrable(narrativa):
        # Se cobra DESPUÉS: el coste solo se conoce al volver del proveedor. El
        # desbordamiento máximo del tope es una llamada, y está declarado en
        # `narrative/quota.py`.
        try:
            await acumular(
                conn,  # type: ignore[arg-type]
                tenant_id,  # type: ignore[arg-type]
                cost_usd=narrativa.cost_usd,
                cap_usd=s.ai_monthly_cap_usd,
                warn_at=s.ai_warn_at,
                actor=actor,
            )
        except Exception:  # noqa: BLE001
            # La prosa ya está y es buena: descartarla porque la contabilidad falló
            # sería tirar el trabajo que ya se pagó. Se grita en el log —el gasto sin
            # registrar es dinero perdido de vista— y la narrativa sale tal cual.
            log.exception("narrative: no se pudo registrar el gasto de IA (la prosa SÍ salió)")
    return narrativa


def _sin_hechos(exc: Exception) -> Narrative:
    """Ni siquiera hubo hechos que redactar. Sale UNA sección que lo dice.

    Cero secciones sería peor que esto y no por poco: ``pdf._narrative_section`` se va
    de vacío si la narrativa está vacía, y entonces el §16 desaparece **sin una línea
    que explique por qué** — ni siquiera la de «NARRATIVA DEGRADADA», que se imprime
    dentro de esa misma sección. Un apartado que desaparece en silencio es exactamente
    el vacío sin causa que la regla de oro 7 prohíbe.
    """
    # ⚠️ SIN el sufijo «; texto determinista» de `motivo_con_causa`: aquí NO hay texto
    # determinista que ofrecer —las seis secciones se derivan de los hechos que no se
    # pudieron componer— y prometerlo en el pie del §16 sería el documento desmintiéndose
    # a sí mismo tres líneas más abajo.
    motivo = f"{MOTIVO_SIN_HECHOS} ({type(exc).__name__})"
    cuerpo = (
        "No fue posible redactar la prosa de este dictamen: no se pudieron componer los "
        f"hechos del incidente ({type(exc).__name__}). El veredicto, las mediciones y la "
        "cadena de custodia de este documento NO dependen de esta sección y se imprimen "
        "igual."
    )
    return Narrative(
        sections=((TITULO_LIMITACIONES, cuerpo),),
        provider=DETERMINISTA,
        degraded_reason=motivo,
    )


async def _degradar(req: NarrativeRequest, motivo: str) -> Narrative:
    """Prosa determinista CON su razón. La razón es lo que no se puede olvidar aquí.

    ── tramo «el respaldo determinista» ──

    ⚠️ Por aquí pasan TODAS las degradaciones, y la llamada al respaldo estaba desnuda:
    si el determinista fallaba, la excepción salía a ``generate_report`` y se llevaba
    por delante la exportación — **el mismo modo de fallo que esta ficha vino a cerrar,
    recreado un nivel más abajo**. El respaldo del respaldo es decirlo.
    """
    try:
        base = await DeterministicProvider().generate(req)
    except Exception as exc:  # noqa: BLE001
        log.exception("narrative: el respaldo determinista también falló")
        return _sin_respaldo(motivo, exc)
    return replace(base, degraded_reason=motivo)


def _sin_respaldo(motivo: str, exc: Exception) -> Narrative:
    """Falló la redacción Y falló el respaldo. Sale UNA sección que lo dice.

    ⚠️ Lo que no se puede hacer aquí es arrastrar el motivo tal cual: los motivos que
    ofrecen respaldo acaban en «; texto determinista» y **ese texto ya no existe**.
    Dejarlo sería el pie del §16 desmintiendo a la sección tres líneas más abajo, que es
    exactamente el defecto de forma que esta ficha persigue. Se le quita el sufijo y se
    encadena la segunda causa.
    """
    sin_promesa = motivo.removesuffix(SUFIJO_DETERMINISTA)
    razon = f"{sin_promesa}; {MOTIVO_RESPALDO_CAIDO} ({type(exc).__name__})"
    cuerpo = (
        "No fue posible redactar la prosa de este dictamen ni con el motor determinista "
        f"({type(exc).__name__}). El veredicto, las mediciones y la cadena de custodia de "
        "este documento NO dependen de esta sección y se imprimen igual."
    )
    return Narrative(
        sections=((TITULO_LIMITACIONES, cuerpo),),
        provider=DETERMINISTA,
        degraded_reason=razon,
    )


def _sale_a_la_red(provider: NarrativeProvider) -> bool:
    """¿Este proveedor cuesta dinero? El determinista no, y cobrarle una llamada
    llenaría el contador de ceros y el `calls` de mentiras."""
    return not isinstance(provider, DeterministicProvider)


def _hubo_redaccion_cobrable(narrativa: Narrative) -> bool:
    """[T-7.26] ¿Se cobra ESTA narrativa? Lo decide el RESULTADO, no el elegido.

    `cobrable` dice si se PUEDE gastar. Quien decide si se cobra es lo que volvió: si
    OpenRouter no respondió, su propio fail-open devuelve prosa determinista con
    `cost_usd=None`, y `acumular` se llamaba igual — `ai_spend.calls` acababa diciendo
    «la IA redactó 40 veces» de un mes en el que el proveedor estuvo caído.

    El intento fallido no se pierde: queda en `audit_log` (`narrative_generated`) con su
    `degraded_reason`, que es donde se puede leer POR QUÉ falló. Un número en
    `ai_spend` no habría dicho eso.

    Se cuenta la llamada aunque el coste venga a `None` mientras la prosa sea del
    proveedor remoto: hay modelos que no reportan `usage.cost`, y descartar esa fila
    dejaría el contador mintiendo en el otro sentido.
    """
    return narrativa.provider != DETERMINISTA


def apply_narrative(model: ReportModel, narrative: Narrative) -> None:
    """Cuelga la prosa del modelo. El veredicto del modelo NO se toca."""
    model.narrative = list(narrative.sections)
    model.narrative_provider = narrative.provider
    model.narrative_degraded = narrative.degraded_reason
