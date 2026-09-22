"""T-7.26 · La degradación SE DECLARA, y `build_narrative` no lanza JAMÁS.

Dos defectos medidos en el reconocimiento, y la doctrina que los une: **un fallback
no puede ser `ok`**. Un PDF con prosa determinista es un PDF correcto; un PDF con
prosa determinista que no dice que la redacción asistida falló es un PDF que MIENTE
sobre cómo se produjo, y es evidencia ante Protección Civil.

1. **El cinturón exterior devolvía el determinista sin razón.** Medido antes de
   tocar nada: un proveedor que lanza `RuntimeError` daba
   `provider="deterministic", degraded_reason=None`, o sea que el PDF no imprimía
   «NARRATIVA DEGRADADA» por esa vía. El camino más grave de la misma familia era
   el secreto: `resolve_api_key` se tragaba cualquier excepción y devolvía cadena
   vacía, así que **un `AccessDenied` al leer la clave se veía exactamente igual
   que tener la IA apagada** — que es lo que pasa en la nube el primer día,
   mientras el rol de la instancia no tiene permiso.

2. **`build_narrative` prometía no lanzar y era falso.** `facts_from`, las dos
   llamadas de cuota, `select_provider` y el propio respaldo determinista quedaban
   fuera del `try`. Medido: `build_narrative(model(channels=None), Settings())`
   lanzaba `TypeError` desde `redact.py` y la excepción salía a `generate_report`:
   **un dato raro del incidente impedía exportar el dictamen entero.** La doctrina
   contraria ya está escrita en este repositorio para el CCTV y para la cuota: un
   fallo de la prosa no puede impedir que se genere el papel.

   ⚠️ Aquí se citaba `opened_at=None`, y era el ejemplo equivocado: con ESE modelo la
   exportación se cae igual —`membrete.seal` → `fpdf.set_creation_date` →
   `TypeError: date should be a datetime`—, que es el SELLO del documento pidiendo su
   fecha, no la prosa. O sea que la guarda que se llamaba «NO impide exportar el
   dictamen» nunca renderizaba y, con su propio dato, la exportación seguía cayendo.
   Hoy la guarda RENDERIZA, y lo hace con un dato raro que sí deja salir el papel.

Lo que estos tests NO relajan: **estar apagado no es una degradación.** Es la
configuración pedida, y marcarla llenaría de avisos un documento correcto.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from takab_api.narrative import build_narrative, select_provider
from takab_api.narrative.base import (
    MOTIVO_CLAVE_ILEGIBLE,
    MOTIVO_CUOTA_ILEGIBLE,
    MOTIVO_PROVEEDOR,
    MOTIVO_PROVEEDOR_CREDENCIAL,
    MOTIVO_PROVEEDOR_ESTADO,
    MOTIVO_PROVEEDOR_MUDO,
    MOTIVO_SIN_CLAVE,
    MOTIVO_SIN_HECHOS,
    SUFIJO_DETERMINISTA,
    Narrative,
)
from takab_api.narrative.deterministic import DeterministicProvider
from takab_api.narrative.openrouter import (
    CODIGO_CLAVE_SIN_FORMA,
    CODIGO_SECRETO_SIN_CLAVE,
    _tiene_forma_de_clave,
    resolve_api_key,
)
from takab_api.settings import Settings
from tests.dictamen.test_pdf import model

SECRETO = "takab/dev/openrouter"


def _encendido(**over) -> Settings:
    base = {
        "openrouter_enabled": True,
        "openrouter_model": "algun/modelo",
        "openrouter_api_key": "sk-test",
    }
    return Settings(**{**base, **over})


class _Explota:
    """Proveedor de red que revienta. No es `DeterministicProvider` a propósito:
    así pasa el filtro de `_sale_a_la_red` y ejerce el camino cobrable."""

    name = "explota"

    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc or RuntimeError("boom del proveedor")

    async def generate(self, req):  # noqa: ANN001, ANN202, ARG002
        raise self._exc


# ── 1. lo que NO es una degradación ───────────────────────────────────────────


async def test_apagado_no_es_una_degradacion() -> None:
    """La configuración que se despliega hoy. Marcar esto sería ruido."""
    out = await build_narrative(model(), Settings())
    assert out.provider == "deterministic"
    assert out.degraded_reason is None


async def test_encendido_sin_slug_de_modelo_tampoco() -> None:
    """Sin slug no hay a quién llamar, y no tenerlo es la decisión declarada en
    `settings.py`: un identificador de modelo hardcodeado caduca en silencio."""
    elegido = select_provider(_encendido(openrouter_model=""))
    assert isinstance(elegido.provider, DeterministicProvider)
    assert elegido.degraded_reason is None


# ── 2. lo que SÍ lo es: encendido pero no pude ────────────────────────────────


def test_un_secreto_que_no_se_puede_leer_DICE_por_que() -> None:
    """El caso del primer día en la nube: el rol de la instancia sin permiso.

    Se conserva el código de error de AWS (`AccessDeniedException`) y NO el mensaje:
    el mensaje de botocore trae el ARN y la cuenta, y esto acaba impreso en un PDF
    que sale de la organización.
    """

    class SM:
        def get_secret_value(self, SecretId: str) -> dict:  # noqa: N803, ARG002
            raise _ClientError("AccessDeniedException")

    ajustes = _encendido(openrouter_api_key="", openrouter_secret_id=SECRETO)
    clave = resolve_api_key(ajustes, client=SM())
    assert clave.api_key == ""
    assert clave.error == "AccessDeniedException"


class _ClientError(Exception):
    """Doble de `botocore.exceptions.ClientError`: lo que importa es la forma de
    `response`, que es de donde sale el código sin arrastrar el ARN."""

    def __init__(self, code: str) -> None:
        super().__init__(f"An error occurred ({code}) ... arn:aws:iam::634882473845:role/x")
        self.response = {"Error": {"Code": code}}


def test_la_clave_ilegible_ELIGE_determinista_y_lo_declara(monkeypatch) -> None:
    class SM:
        def get_secret_value(self, SecretId: str) -> dict:  # noqa: N803, ARG002
            raise _ClientError("AccessDeniedException")

    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: SM())
    elegido = select_provider(_encendido(openrouter_api_key="", openrouter_secret_id=SECRETO))
    assert isinstance(elegido.provider, DeterministicProvider)
    assert MOTIVO_CLAVE_ILEGIBLE in (elegido.degraded_reason or "")
    assert "AccessDeniedException" in (elegido.degraded_reason or "")


async def test_la_clave_ilegible_LLEGA_al_PDF(monkeypatch) -> None:
    """Sin esto lo anterior sería decorativo: lo que imprime el papel es
    `narrative.degraded_reason`, no lo que sepa `select_provider`."""

    class SM:
        def get_secret_value(self, SecretId: str) -> dict:  # noqa: N803, ARG002
            raise _ClientError("AccessDeniedException")

    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: SM())
    out = await build_narrative(
        model(), _encendido(openrouter_api_key="", openrouter_secret_id=SECRETO)
    )
    assert out.provider == "deterministic"
    assert MOTIVO_CLAVE_ILEGIBLE in (out.degraded_reason or "")
    assert len(out.sections) == 6, "la prosa determinista sale igual"


async def test_encendido_SIN_clave_configurada_tambien_se_declara() -> None:
    """Distinto del anterior: aquí no hubo secreto que leer, alguien encendió la
    perilla y no configuró ningún origen de clave. Sigue siendo «encendido pero no
    pude», que es lo contrario de «apagado a propósito»."""
    out = await build_narrative(model(), _encendido(openrouter_api_key=""))
    assert out.provider == "deterministic"
    assert MOTIVO_SIN_CLAVE in (out.degraded_reason or "")


async def test_un_proveedor_que_revienta_DICE_por_que() -> None:
    """El defecto D1 tal cual se midió: antes daba `degraded_reason=None`."""
    out = await build_narrative(model(), Settings(), provider=_Explota())
    assert out.provider == "deterministic"
    assert MOTIVO_PROVEEDOR in (out.degraded_reason or "")
    assert "RuntimeError" in (out.degraded_reason or ""), "qué reventó, no solo que reventó"
    assert len(out.sections) == 6


# ── 3. `build_narrative` no lanza JAMÁS ───────────────────────────────────────


async def test_un_dato_raro_del_incidente_NO_impide_exportar_el_dictamen() -> None:
    """El defecto tal cual se midió, **y medido hasta donde duele: el PDF.**

    ⚠️ Esta guarda se paraba en `build_narrative` y por eso no valía: el defecto que la
    ficha cierra se llama «un dato raro del incidente impide exportar el dictamen
    entero», así que lo que hay que ejercer es la EXPORTACIÓN, no la función de en
    medio. Con el dato que citaba (`opened_at=None`) la exportación seguía cayendo — en
    `fpdf`, por el sello del documento, que es otro defecto y no es de esta capa (ver
    `test_el_dato_que_rompe_el_SELLO_...`). Aquí se usa `channels=None`, que revienta
    `redact.facts_from` igual y deja salir el papel.

    Sin hechos no hay ninguna de las seis secciones que redactar —todas se derivan de
    ellos—, así que lo que sale es UNA sección que dice que no hubo prosa y por qué. Un
    §16 ausente y mudo sería el vacío sin causa que la regla de oro 7 prohíbe.
    """
    from takab_api.dictamen.pdf import render  # noqa: PLC0415
    from takab_api.narrative import apply_narrative  # noqa: PLC0415
    from tests.dictamen.test_avisos_impresos import _texto_dibujado  # noqa: PLC0415

    m = model(channels=None)
    out = await build_narrative(m, Settings())
    assert isinstance(out, Narrative)
    assert out.provider == "deterministic"
    assert MOTIVO_SIN_HECHOS in (out.degraded_reason or "")
    assert "TypeError" in (out.degraded_reason or "")
    assert len(out.sections) == 1, "una sección que declara la ausencia, no cero"
    # ⚠️ Y NO promete lo que no hay: el sufijo «; texto determinista» que llevan los
    # demás motivos sería el documento desmintiéndose tres líneas más abajo, donde el
    # §16 tiene una sola sección y ninguna de las seis. (Lo tuvo durante una vuelta.)
    assert SUFIJO_DETERMINISTA not in (out.degraded_reason or "")

    # Y AHORA lo que da nombre al test: el dictamen SE EXPORTA.
    apply_narrative(m, out)
    pdf = render(m, "technical")
    assert pdf[:4] == b"%PDF" and len(pdf) > 10_000, "el dictamen tiene que salir igual"
    dibujado = _texto_dibujado(m, "technical")
    assert "NARRATIVA DEGRADADA" in dibujado
    assert MOTIVO_SIN_HECHOS in dibujado, "y el papel dice POR QUÉ no hubo prosa"


async def test_el_dato_que_rompe_el_SELLO_no_es_de_esta_capa_y_se_deja_dicho() -> None:
    """`opened_at=None` degrada la prosa **y aun así el PDF no sale** — por otra cosa.

    Se conserva como guarda porque es la frontera de responsabilidad de esta capa, y
    porque era el ejemplo que los tres docstrings de la ficha citaban para afirmar lo
    contrario. Lo que mide:

    * la prosa NO lanza (el cinturón del tramo «redactar los hechos» funciona), y
    * la exportación se cae en `membrete.seal` → `fpdf.set_creation_date`, pidiendo la
      fecha de creación del documento. Es el SELLO, no la narrativa: otro defecto, con
      otro nombre, fuera del ámbito de T-7.26.

    El día que alguien arregle el sello, este test se pone rojo y hay que venir a
    borrarlo — que es exactamente lo que se quiere de una frontera escrita.
    """
    from takab_api.dictamen.pdf import render  # noqa: PLC0415
    from takab_api.narrative import apply_narrative  # noqa: PLC0415

    m = model(opened_at=None)
    out = await build_narrative(m, Settings())
    assert MOTIVO_SIN_HECHOS in (out.degraded_reason or ""), "la prosa sí degrada"

    apply_narrative(m, out)
    with pytest.raises(TypeError, match="date should be a datetime") as exc:
        render(m, "technical")
    assert _marco_que_revienta(exc)[1] == "set_creation_date", (
        "la frontera dice que se cae en el SELLO; si cambia de sitio, hay que reescribirla"
    )


def _marco_que_revienta(excinfo) -> tuple[str, str]:  # noqa: ANN001
    """Fichero y función DONDE se cayó de verdad, no dónde se pidió el PDF.

    Una frontera que solo dijera «`render` lanza `TypeError`» valdría igual para los
    dos defectos de abajo y para el siguiente — y entonces no sería una frontera, sería
    una excusa. Lo que la hace morder es el NOMBRE del sitio.
    """
    marco = excinfo.traceback[-1]
    return (Path(str(marco.path)).name, marco.name)


async def test_el_dato_que_rompe_la_FORMA_DE_ONDA_no_es_de_esta_capa_y_se_deja_dicho() -> None:
    """`evidence=None`: **la prosa degrada bien y el papel se cae igual — por otra cosa.**

    Es la misma familia que `opened_at=None` de aquí abajo, y hace falta decirlo aparte
    porque se arregla en otro sitio: la prosa hace exactamente lo que T-7.26 le pide
    —degradar con su razón y dejar salir el documento— y quien tumba la exportación es
    `dictamen/pdf.py::_raw_section`, que recorre `m.evidence` para saber si CONSTA un
    miniSEED en la custodia y da por hecho que hay lista que recorrer.

    Medido (ver el `assert` de abajo, que lo fija): `TypeError: 'NoneType' object is not
    iterable` en `pdf.py::_raw_section`. **No es de esta ficha y no se arregla a
    escondidas**: queda fichado para que alguien le ponga número, igual que el sello.

    El día que se arregle, este test se pone rojo y hay que venir a borrarlo — que es
    exactamente lo que se quiere de una frontera escrita.
    """
    from takab_api.dictamen.pdf import render  # noqa: PLC0415
    from takab_api.narrative import apply_narrative  # noqa: PLC0415

    m = model(evidence=None)
    out = await build_narrative(m, Settings())

    # 1 · LA PROSA CUMPLE. Degrada, lo dice, y no arrastra la promesa que no puede pagar.
    assert out.provider == "deterministic"
    assert MOTIVO_SIN_HECHOS in (out.degraded_reason or "")
    assert "TypeError" in (out.degraded_reason or ""), "y con la causa, que es un código"
    assert SUFIJO_DETERMINISTA not in (out.degraded_reason or "")

    # 2 · EL PAPEL SE CAE, y en un sitio con nombre que NO es esta capa.
    apply_narrative(m, out)
    with pytest.raises(TypeError, match="'NoneType' object is not iterable") as exc:
        render(m, "technical")
    assert _marco_que_revienta(exc) == ("pdf.py", "_raw_section"), (
        "si se cae en otro sitio, la frontera de arriba ya no describe este defecto"
    )


async def test_el_papel_IMPRIME_la_narrativa_degradada() -> None:
    """El criterio 4 de la ficha, medido donde se lee: en el texto que dibuja el PDF."""
    from takab_api.narrative import apply_narrative  # noqa: PLC0415
    from tests.dictamen.test_avisos_impresos import _texto_dibujado  # noqa: PLC0415

    m = model()
    apply_narrative(m, await build_narrative(m, Settings(), provider=_Explota()))
    dibujado = _texto_dibujado(m, "technical")
    assert "NARRATIVA DEGRADADA" in dibujado
    # Y con la RAZÓN, no solo con el rótulo: «degradada» a secas no le dice a nadie si
    # falló el proveedor, si se acabó la cuota o si nunca hubo clave — y son tres cosas
    # que se arreglan en tres sitios distintos.
    assert MOTIVO_PROVEEDOR in dibujado and "RuntimeError" in dibujado


async def test_si_la_cuota_no_se_puede_LEER_se_degrada_en_vez_de_lanzar(monkeypatch) -> None:
    """La lectura de cuota estaba fuera del `try`. Un error de la base al leer
    `ai_spend` tumbaba la exportación entera del dictamen."""

    async def revienta(*a, **k):  # noqa: ANN002, ANN003, ANN202, ARG001
        raise RuntimeError("la base dijo que no")

    monkeypatch.setattr("takab_api.narrative.leer_estado", revienta)
    out = await build_narrative(
        model(), Settings(), provider=_Explota(), conn=object(), tenant_id="t-1"
    )
    assert out.provider == "deterministic"
    assert MOTIVO_CUOTA_ILEGIBLE in (out.degraded_reason or "")


# ── 3.bis la CLAVE REVOCADA: el control negativo literal del criterio 4 ───────
#
# El criterio 4 de T-7.26 dice «con la clave REVOCADA el reporte dice NARRATIVA
# DEGRADADA». Lo que la suite probaba era «el secreto no se pudo leer», que es OTRO
# camino y ni siquiera abre un socket: se queda en `resolve_api_key`. Una clave
# revocada existe, se lee, viaja en la cabecera y vuelve con un 401 — o sea que recorre
# `select_provider` → `OpenRouterProvider` → `_post` → `raise_for_status` entero.
#
# Se ejerce por la costura de transporte de `build_narrative`, que es lo que permite
# medir el camino que el despliegue enciende de verdad sin clave y sin red.


def _transporte(status: int, cuerpo: dict):  # noqa: ANN202
    import httpx  # noqa: PLC0415

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(status, json=cuerpo)

    return httpx.MockTransport(handler)


#: Lo que OpenRouter devuelve de verdad con una clave revocada.
_401_DE_OPENROUTER = {"error": {"message": "User not found.", "code": 401}}
CLAVE_REVOCADA = "sk-or-v1-revocada-0000"


async def test_con_la_clave_REVOCADA_el_papel_dice_NARRATIVA_DEGRADADA() -> None:
    """Criterio 4, por el camino que nombra la ficha y hasta el texto que se dibuja."""
    from takab_api.narrative import apply_narrative  # noqa: PLC0415
    from tests.dictamen.test_avisos_impresos import _texto_dibujado  # noqa: PLC0415

    m = model()
    out = await build_narrative(
        m,
        _encendido(openrouter_api_key=CLAVE_REVOCADA),
        transport=_transporte(401, _401_DE_OPENROUTER),
    )
    assert out.provider == "deterministic"
    assert len(out.sections) == 6, "la prosa determinista sale igual"

    apply_narrative(m, out)
    dibujado = _texto_dibujado(m, "technical")
    assert "NARRATIVA DEGRADADA" in dibujado
    assert MOTIVO_PROVEEDOR_CREDENCIAL in dibujado, "y el papel dice QUÉ falló"
    assert "HTTP 401" in dibujado


async def test_el_papel_NO_dice_que_el_proveedor_callo_cuando_contesto_401() -> None:
    """La frase conservadora-pero-falsa que quedaba, y por qué importa.

    Con la clave revocada el motivo era «el proveedor no respondió (HTTPStatusError)» y
    el proveedor SÍ respondió — con un 401, y rápido. Quien leyera eso iría a mirar la
    red; el problema está en el secreto. Es el mismo defecto que esta ficha corrigió en
    la cuota, donde «agotada» se separó de «no había».
    """
    out = await build_narrative(
        model(),
        _encendido(openrouter_api_key=CLAVE_REVOCADA),
        transport=_transporte(401, _401_DE_OPENROUTER),
    )
    razon = out.degraded_reason or ""
    assert MOTIVO_PROVEEDOR_MUDO not in razon, "respondió: decir que calló manda a la red"
    assert MOTIVO_PROVEEDOR_CREDENCIAL in razon


async def test_un_500_NO_se_lee_como_un_problema_de_clave() -> None:
    """El control positivo del anterior: sin él, «siempre la clave» pasaría igual."""
    out = await build_narrative(
        model(),
        _encendido(openrouter_api_key="sk-buena"),
        transport=_transporte(500, {"error": "boom"}),
    )
    razon = out.degraded_reason or ""
    assert MOTIVO_PROVEEDOR_CREDENCIAL not in razon
    assert MOTIVO_PROVEEDOR_ESTADO in razon and "HTTP 500" in razon


async def test_la_clave_revocada_NO_se_imprime_en_el_papel() -> None:
    """Un secreto en un documento que sale de la organización es una fuga, y este es
    el único camino en el que la clave está EN MEMORIA cuando se compone el motivo."""
    from takab_api.narrative import apply_narrative  # noqa: PLC0415
    from tests.dictamen.test_avisos_impresos import _texto_dibujado  # noqa: PLC0415

    m = model()
    apply_narrative(
        m,
        await build_narrative(
            m,
            _encendido(openrouter_api_key=CLAVE_REVOCADA),
            transport=_transporte(401, _401_DE_OPENROUTER),
        ),
    )
    dibujado = _texto_dibujado(m, "technical")
    assert CLAVE_REVOCADA not in dibujado
    assert "sk-" not in dibujado, "ni la clave ni nada que se le parezca"


async def test_el_motivo_del_secreto_ILEGIBLE_no_arrastra_el_ARN(monkeypatch) -> None:
    """La otra fuga posible, por el otro camino: el mensaje de botocore trae el ARN y
    el número de cuenta. Lo que viaja al papel es el CÓDIGO."""
    from takab_api.narrative import apply_narrative  # noqa: PLC0415
    from tests.dictamen.test_avisos_impresos import _texto_dibujado  # noqa: PLC0415

    class SM:
        def get_secret_value(self, SecretId: str) -> dict:  # noqa: N803, ARG002
            raise _ClientError("AccessDeniedException")

    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: SM())
    m = model()
    apply_narrative(
        m,
        await build_narrative(m, _encendido(openrouter_api_key="", openrouter_secret_id=SECRETO)),
    )
    dibujado = _texto_dibujado(m, "technical")
    assert "AccessDeniedException" in dibujado, "el código sí, que es lo que sirve"
    assert "arn:aws" not in dibujado and "634882473845" not in dibujado


# ── 4. la trampa del cobro: se cobra por el RESULTADO, no por el elegido ──────


async def test_no_se_cobra_una_llamada_que_el_proveedor_DEGRADO(monkeypatch) -> None:
    """`cobrable` decía si se PUEDE gastar; quien decide si se COBRA es el resultado.

    Si OpenRouter no responde devuelve prosa determinista y `cost_usd=None`, y
    `acumular` se llamaba igual: `ai_spend.calls` acababa diciendo «la IA redactó
    40 veces» de un mes en el que el proveedor estuvo caído. El intento fallido no
    se pierde — queda en `audit_log` (`narrative_generated`) con su razón, que es
    donde se puede leer POR QUÉ falló.
    """
    from takab_api.narrative.quota import EstadoCuota  # noqa: PLC0415

    cobros: list[float | None] = []

    async def leer(*a, **k):  # noqa: ANN002, ANN003, ANN202, ARG001
        return EstadoCuota("2026-09", 0.0, 0, 5.0, exhausted=False)

    async def cobrar(*a, cost_usd=None, **k):  # noqa: ANN002, ANN003, ANN202, ARG001
        cobros.append(cost_usd)
        return 0.0, False

    monkeypatch.setattr("takab_api.narrative.leer_estado", leer)
    monkeypatch.setattr("takab_api.narrative.acumular", cobrar)

    class Degrada:
        name = "openrouter"

        async def generate(self, req):  # noqa: ANN001, ANN202, ARG002
            return Narrative(sections=(), provider="deterministic", degraded_reason="cayó")

    await build_narrative(model(), Settings(), provider=Degrada(), conn=object(), tenant_id="t-1")
    assert cobros == [], "se cobró una llamada que no redactó nada"


async def test_una_redaccion_de_VERDAD_si_se_cobra(monkeypatch) -> None:
    """El control positivo del anterior: sin él, «no cobrar nunca» pasaría igual."""
    from takab_api.narrative.quota import EstadoCuota  # noqa: PLC0415

    cobros: list[float | None] = []

    async def leer(*a, **k):  # noqa: ANN002, ANN003, ANN202, ARG001
        return EstadoCuota("2026-09", 0.0, 0, 5.0, exhausted=False)

    async def cobrar(*a, cost_usd=None, **k):  # noqa: ANN002, ANN003, ANN202, ARG001
        cobros.append(cost_usd)
        return 0.0, False

    monkeypatch.setattr("takab_api.narrative.leer_estado", leer)
    monkeypatch.setattr("takab_api.narrative.acumular", cobrar)

    class Redacta:
        name = "openrouter"

        async def generate(self, req):  # noqa: ANN001, ANN202, ARG002
            return Narrative(
                sections=(("Resumen ejecutivo", "x"),), provider="openrouter", cost_usd=0.0042
            )

    await build_narrative(model(), Settings(), provider=Redacta(), conn=object(), tenant_id="t-1")
    assert cobros == [pytest.approx(0.0042)]


# ---------------------------------------------------------------------------
# [2026-09-22] La clave que NO es una clave
# ---------------------------------------------------------------------------
#
# El caso real, y costó dos rondas de medición contra la nube: el secreto
# `takab/dev/openrouter` llevaba desde el 2026-09-21 con un valor que nunca fue una
# clave —el marcador de posición de la documentación, pegado tal cual—, el sistema salía
# a la red, OpenRouter devolvía 401 y el papel decía «el proveedor no aceptó la clave».
# Cierto, y apuntando al sitio equivocado: quien lo lee revisa cuotas y permisos del
# proveedor cuando lo que hay es un marcador dentro del secreto.
#
# Las otras dos superficies que deberían haberlo delatado miran otra cosa: el censo de
# conformidad comprueba que el secreto EXISTA y que el rol pueda LEERLO, y
# `consultar_vision` pregunta a `GET /models`, que es PÚBLICO (medido: 200 sin cabecera
# de auth). `resolve_api_key` es la única que ve el valor, así que le toca a ella.


@pytest.mark.parametrize(
    "valor,es_clave",
    [
        # Lo que hay que cazar: el marcador de la propia documentación.
        ("sk-or-...", False),
        ("sk-or-…", False),
        ("pega-aqui-tu-clave", False),
        ("sk-or-corta", False),
        # Una clave de OTRO emisor pegada por error.
        ("sk-ant-api03-" + "x" * 40, False),
        # Y lo que tiene que PASAR: una clave con la forma del emisor. Que esté
        # revocada o sin crédito NO se decide aquí — eso es un 401 legítimo del
        # proveedor y tiene que llegar al papel como tal.
        ("sk-or-v1-" + "a" * 64, True),
        ("  sk-or-v1-" + "b" * 64 + "  ", True),
    ],
)
def test_una_cadena_que_no_puede_ser_clave_se_distingue_de_una_clave_rechazada(
    valor: str, es_clave: bool
) -> None:
    """Laxa a propósito: descarta lo imposible, no valida lo posible.

    Apretarla de más convertiría «la cuenta no tiene crédito» en «tu secreto está mal»,
    que es el mismo defecto en la otra dirección.
    """
    assert _tiene_forma_de_clave(valor) is es_clave


def test_el_marcador_de_posicion_NO_sale_a_la_red_y_lo_dice_con_su_codigo() -> None:
    """Conducta, no forma: con un marcador dentro, `resolve_api_key` devuelve vacío y un
    código PROPIO — así el papel no acusa al proveedor de algo que no hizo."""

    class _SM:
        def get_secret_value(self, SecretId: str) -> dict:  # noqa: N803 - lo fija boto3
            return {"SecretString": json.dumps({"api_key": "sk-or-..."})}

    s = Settings(openrouter_secret_id="takab/dev/openrouter", openrouter_api_key="")
    clave = resolve_api_key(s, client=_SM())
    assert clave.api_key == ""
    assert clave.error == CODIGO_CLAVE_SIN_FORMA
    # Y lo que NO puede pasar: que se confunda con «el secreto no trae api_key».
    assert clave.error != CODIGO_SECRETO_SIN_CLAVE
