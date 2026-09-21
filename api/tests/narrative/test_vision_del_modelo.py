"""T-7.27 · Que el modelo declare que SABE VER, antes de mandarle una fotografía.

`D-32` lo puso como condición: «el modelo tiene que declarar que admite imágenes y, si
no, la capa cae al determinista y lo dice». La comprobación es `GET /api/v1/models` y
el campo `architecture.input_modalities`.

**Por qué no basta con mandarlas y ver qué pasa.** Un modelo sin visión no devuelve un
error limpio: unos proveedores ignoran la parte de imagen y redactan como si no
existiera —y entonces el documento lleva prosa que dice haber visto lo que nadie miró—,
otros devuelven un 400 que el papel imprime como «el proveedor respondió con error». Las
dos salidas son peores que comprobarlo una vez.

**Una vez por proceso.** El catálogo es un hecho del modelo, no del incidente: se
consulta la primera vez que hace falta y se recuerda. Lo que NO se recuerda es un fallo
de red —eso es del momento— porque cachearlo dejaría la IA apagada hasta el siguiente
despliegue por un timeout de un martes.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from takab_api.narrative import build_narrative
from takab_api.narrative.base import (
    MOTIVO_PROVEEDOR_CREDENCIAL,
    MOTIVO_PROVEEDOR_ESTADO,
    MOTIVO_PROVEEDOR_MUDO,
    MOTIVO_SIN_VISION,
    MOTIVO_VISION_ILEGIBLE,
    NarrativeRequest,
)
from takab_api.narrative.deterministic import sections_for
from takab_api.narrative.openrouter import (
    CODIGO_CATALOGO_SIN_LISTA,
    CODIGO_MODELO_NO_LISTADO,
    CODIGO_SIN_MODALIDAD_DE_IMAGEN,
    OpenRouterProvider,
    _huellas,
)
from takab_api.narrative.prompts import SECTION_TITLES, rotulo_de_foto
from takab_api.narrative.redact import facts_from, imagenes_de
from takab_api.settings import Settings
from tests.narrative.grabado import (
    CATALOGO_CON_VISION,
    CATALOGO_SIN_VISION,
    CHAT_CON_IMAGEN,
    MODELO,
    enrutar,
)
from tests.narrative.test_lo_que_ve_la_ia import LUGAR, MARCA, _con_danos
from tests.narrative.test_redact import BASIS


def _ajustes(**over) -> Settings:
    base = {
        "openrouter_enabled": True,
        "openrouter_model": MODELO,
        "openrouter_api_key": "sk-or-v1-de-prueba",
    }
    return Settings(**{**base, **over})


def _proveedor(handler) -> OpenRouterProvider:
    return OpenRouterProvider(
        _ajustes(), api_key="sk-or-v1-de-prueba", transport=httpx.MockTransport(handler)
    )


def _chat_grabado(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
    return httpx.Response(200, json=CHAT_CON_IMAGEN)


# ── el catálogo ───────────────────────────────────────────────────────────────


async def test_un_modelo_que_DECLARA_imagenes_pasa() -> None:
    vistas: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistas.append(request)
        return httpx.Response(200, json=CATALOGO_CON_VISION)

    vision = await _proveedor(handler).admite_imagenes()
    assert vision.admite is True and vision.motivo is None
    assert vistas[0].method == "GET" and vistas[0].url.path.endswith("/models")
    assert vistas[0].headers["Authorization"] == "Bearer sk-or-v1-de-prueba"


async def test_un_modelo_SIN_imagenes_se_declara_y_no_se_le_manda_nada() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, json=CATALOGO_SIN_VISION)

    vision = await _proveedor(handler).admite_imagenes()
    assert vision.admite is False
    assert MOTIVO_SIN_VISION in (vision.motivo or "")
    assert CODIGO_SIN_MODALIDAD_DE_IMAGEN in (vision.motivo or "")


async def test_un_slug_QUE_NO_ESTA_en_el_catalogo_no_se_da_por_bueno() -> None:
    """Es el caso del slug caducado, que `openrouter.py` dejó escrito como pendiente:
    «un default hardcodeado caducaría en silencio». Aquí deja de ser silencioso."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, json={"data": [{"id": "otro/modelo", "architecture": {}}]})

    vision = await _proveedor(handler).admite_imagenes()
    assert vision.admite is False
    assert CODIGO_MODELO_NO_LISTADO in (vision.motivo or "")


@pytest.mark.parametrize(
    ("handler", "motivo", "causa"),
    [
        pytest.param(
            lambda r: httpx.Response(500, text="boom"),
            MOTIVO_PROVEEDOR_ESTADO,
            "HTTP 500",
            id="el proveedor está caído",
        ),
        pytest.param(
            lambda r: httpx.Response(401, json={"error": {"message": "No auth"}}),
            MOTIVO_PROVEEDOR_CREDENCIAL,
            "HTTP 401",
            id="la clave está revocada",
        ),
        pytest.param(
            lambda r: httpx.Response(200, text="esto no es JSON"),
            MOTIVO_VISION_ILEGIBLE,
            "JSONDecodeError",
            id="el catálogo contestó algo ininteligible",
        ),
        pytest.param(
            lambda r: httpx.Response(200, json={"modelos": []}),
            MOTIVO_VISION_ILEGIBLE,
            CODIGO_CATALOGO_SIN_LISTA,
            id="el catálogo no trae lista",
        ),
    ],
)
async def test_un_catalogo_que_no_se_puede_leer_DEGRADA_con_su_causa(
    handler, motivo: str, causa: str
) -> None:
    """**El catálogo NO estrena vocabulario.** Es una petición al mismo proveedor, así
    que un 401 sigue siendo «no aceptó la clave» y un 500, «respondió con error»
    (T-7.26). Lo contrario mandaría a quien lee el papel a mirar el catálogo con la
    clave revocada, que es exactamente el defecto que aquella ficha cerró.

    `MOTIVO_VISION_ILEGIBLE` queda para lo que de verdad es otra cosa: el proveedor
    contestó 200 y lo que dijo no se puede interpretar.
    """
    vision = await _proveedor(handler).admite_imagenes()
    assert vision.admite is False
    assert motivo in (vision.motivo or ""), vision.motivo
    assert causa in (vision.motivo or ""), vision.motivo


# ── la memoria: una vez por proceso, y solo de lo que es un hecho ────────────


async def test_el_catalogo_se_consulta_UNA_VEZ_por_proceso() -> None:
    llamadas: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        llamadas.append(1)
        return httpx.Response(200, json=CATALOGO_CON_VISION)

    p = _proveedor(handler)
    assert (await p.admite_imagenes()).admite
    assert (await p.admite_imagenes()).admite
    assert len(llamadas) == 1, "el catálogo se pregunta en cada dictamen"


async def test_un_FALLO_de_red_NO_se_recuerda() -> None:
    """Cachear un timeout dejaría la IA apagada hasta el siguiente despliegue. El
    catálogo es un hecho del modelo; un timeout es del momento."""
    estado = {"caido": True}

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        if estado["caido"]:
            return httpx.Response(503, text="no disponible")
        return httpx.Response(200, json=CATALOGO_CON_VISION)

    p = _proveedor(handler)
    assert (await p.admite_imagenes()).admite is False
    estado["caido"] = False
    assert (await p.admite_imagenes()).admite is True, "el fallo se quedó cacheado"


# ── de punta a punta, por el camino que enciende el despliegue ───────────────


async def test_SIN_VISION_el_dictamen_sale_determinista_y_NADIE_llama_al_chat() -> None:
    """El fail-open de la ficha: cae al determinista **y lo dice**. Y el control que
    importa para `D-32`: por este camino no sale ni una fotografía."""
    rutas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        rutas.append(request.url.path)
        return httpx.Response(200, json=CATALOGO_SIN_VISION)

    out = await build_narrative(
        _con_danos(verdict_basis=BASIS),
        _ajustes(),
        transport=httpx.MockTransport(handler),
    )
    assert out.provider == "deterministic"
    assert MOTIVO_SIN_VISION in (out.degraded_reason or "")
    assert len(out.sections) == 6, "el respaldo determinista sale entero"
    assert all(r.endswith("/models") for r in rutas), f"se llamó al chat igualmente: {rutas}"
    assert out.photos_sent == (), "se anotaron fotos que no salieron"


async def test_CON_VISION_las_fotos_viajan_como_contenido_multimodal() -> None:
    """El camino entero, con la respuesta grabada: catálogo → chat con imagen → prosa.

    Lo que se mira del cuerpo es lo que `D-32` acota: que la imagen va como parte
    `image_url` con un `data:` de JPEG, que esos bytes son EXACTAMENTE los que la
    allowlist de `redact.imagenes_de` autorizó, y que el EXIF del teléfono no está
    dentro.

    ⚠️ **La aserción del EXIF era VACUA y aquí está la corrección.** Hacía
    `json.dumps(cuerpo)` y buscaba las cadenas del EXIF; la imagen viaja en base64, así
    que esas cadenas ASCII no pueden aparecer literalmente por mucho que estén dentro.
    Medido: con una derivada fabricada CON el EXIF, `MARCA in crudo` daba `False` y la
    aserción pasaba con la fuga dentro. Ahora se DECODIFICA el base64 y se mide ahí.
    """
    m = _con_danos(verdict_basis=BASIS)
    autorizada = imagenes_de(m)[0]
    cuerpos: list[dict] = []

    def chat(request: httpx.Request) -> httpx.Response:
        cuerpos.append(json.loads(request.content))
        return httpx.Response(200, json=CHAT_CON_IMAGEN)

    out = await build_narrative(m, _ajustes(), transport=httpx.MockTransport(enrutar(chat)))

    assert out.provider == "openrouter", out.degraded_reason
    assert out.degraded_reason is None
    cuerpo = cuerpos[0]
    partes = cuerpo["messages"][1]["content"]
    assert isinstance(partes, list), "el mensaje de usuario siguió siendo texto plano"
    assert partes[0]["type"] == "text"
    imagenes = [p for p in partes if p["type"] == "image_url"]
    assert len(imagenes) == 1
    url = imagenes[0]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    bytes_reales = base64.b64decode(url.split(",", 1)[1])
    assert bytes_reales == autorizada.jpeg, "viajó algo distinto de lo que se autorizó"
    assert bytes_reales != m.danos[0].fotos[0].jpeg, (
        "viajó la derivada del papel tal cual, con la marca de agua a la vista"
    )
    # EN LOS BYTES DE LA IMAGEN, no en el JSON que la lleva en base64.
    assert MARCA.encode() not in bytes_reales and LUGAR.encode() not in bytes_reales, (
        "el EXIF del teléfono viajó dentro de la imagen"
    )


async def test_cada_imagen_va_PRECEDIDA_de_su_rotulo() -> None:
    """«Di de qué reporte es cada una» le pide al modelo algo que no puede saber si el
    rótulo no va delante — y lo que hace un modelo al que se le pide lo que no puede
    saber es inventárselo. La prueba anterior contaba las partes `image_url` y miraba
    que la primera fuera texto: se podía borrar la línea del rótulo y quedaba verde.
    """
    m = _con_danos(2, verdict_basis=BASIS)
    cuerpos: list[dict] = []

    def chat(request: httpx.Request) -> httpx.Response:
        cuerpos.append(json.loads(request.content))
        return httpx.Response(200, json=CHAT_CON_IMAGEN)

    await build_narrative(m, _ajustes(), transport=httpx.MockTransport(enrutar(chat)))
    partes = cuerpos[0]["messages"][1]["content"]
    indices = [i for i, p in enumerate(partes) if p["type"] == "image_url"]
    assert len(indices) == 2, "el fixture no llevó dos fotografías: la guarda sería vacua"
    for n, i in enumerate(indices, start=1):
        previa = partes[i - 1]
        assert previa["type"] == "text", f"la imagen {n} no lleva texto delante"
        assert previa["text"] == rotulo_de_foto(n, 1), (
            f"la imagen {n} va precedida de {previa['text']!r} y no de su rótulo"
        )


async def test_la_procedencia_ANOTA_que_fotos_salieron_de_la_nube() -> None:
    """Sin esto no hay forma de contestar «¿qué fotografías se mandaron a un tercero?»,
    que es justo la pregunta que deja abierta el consentimiento contractual pendiente
    de `D-32`. Van las HUELLAS, no los bytes: `audit_log` no se poda nunca."""
    m = _con_danos(verdict_basis=BASIS)

    out = await build_narrative(
        m, _ajustes(), transport=httpx.MockTransport(enrutar(_chat_grabado))
    )
    (huella,) = out.photos_sent
    assert huella.impreso == m.danos[0].fotos[0].sha256_impreso, "se perdió el vínculo con el papel"
    assert huella.enviado == imagenes_de(m)[0].sha256_enviado
    assert out.provenance()["photos_sent"] == [
        {"enviado": huella.enviado, "impreso": huella.impreso}
    ]


async def test_sin_fotos_el_mensaje_sigue_siendo_TEXTO_PLANO() -> None:
    """Un incidente sin fotografías no paga la forma multimodal: el cuerpo es el de
    antes, que es lo que ya sabían interpretar todos los proveedores."""
    cuerpos: list[dict] = []

    def chat(request: httpx.Request) -> httpx.Response:
        cuerpos.append(json.loads(request.content))
        prosa = json.dumps({"sections": dict(sections_for(facts_from(_modelo_sin_fotos())))})
        return httpx.Response(200, json={"choices": [{"message": {"content": prosa}}]})

    out = await build_narrative(
        _modelo_sin_fotos(), _ajustes(), transport=httpx.MockTransport(enrutar(chat))
    )
    assert out.provider == "openrouter", out.degraded_reason
    assert isinstance(cuerpos[0]["messages"][1]["content"], str)


def _modelo_sin_fotos():
    from tests.dictamen.test_pdf import model  # noqa: PLC0415

    return model(verdict_basis=BASIS)


def test_los_hechos_y_las_imagenes_CUENTAN_LO_MISMO() -> None:
    """La invariante que impide que el prompt mienta sobre sí mismo: el número que los
    hechos declaran es el de la tupla que se adjunta, porque sale de ella."""
    m = _con_danos(2)
    imagenes = imagenes_de(m)
    req = NarrativeRequest(facts=facts_from(m, imagenes=imagenes), model=MODELO, images=imagenes)
    assert req.facts.photos_attached == len(req.images) == 2


# ── [T-7.27·A] qué fotografías se anotan como SALIDAS, y en qué ramas ────────
#
# `photos_sent` es el único registro que contesta «¿qué fotografías se mandaron a un
# tercero?» —la pregunta que deja abierta el consentimiento pendiente de `D-32`— y va a
# `audit_log`, que por la regla de oro 11 no se poda nunca. Dos defectos medidos: se
# anotaba en ramas en las que el socket no llegaba a abrirse (afirmando una transferencia
# que no ocurrió, CONTRA el comentario que hay tres líneas más abajo en el mismo fichero),
# y al vaciar `_huellas` solo caía UNA prueba, la del camino feliz — o sea que en las
# ramas degradadas, que es donde más falta hace saber qué salió, no había nada.


def _con_imagenes(m) -> NarrativeRequest:
    imagenes = imagenes_de(m)
    assert imagenes, "el fixture no trae fotografías: la guarda sería vacua"
    return NarrativeRequest(facts=facts_from(m, imagenes=imagenes), model=MODELO, images=imagenes)


def _proveedor_directo(handler) -> OpenRouterProvider:
    return OpenRouterProvider(_ajustes(), api_key="sk-test", transport=httpx.MockTransport(handler))


def _ilegible(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
    return httpx.Response(200, text="esto no es el sobre que se esperaba")


def _guardrail(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
    prosa = json.dumps({"sections": {t: "El pico fue de 0.99 g." for t in SECTION_TITLES}})
    return httpx.Response(200, json={"choices": [{"message": {"content": prosa}}]})


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(
            lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("tardó", request=r)),
            id="se mandó y no contestó (ReadTimeout)",
        ),
        pytest.param(lambda r: httpx.Response(500, text="boom"), id="se mandó y contestó mal"),
        pytest.param(_ilegible, id="se mandó y volvió basura"),
        pytest.param(_guardrail, id="se mandó y el guardrail la descartó"),
    ],
)
async def test_en_las_ramas_DEGRADADAS_se_anota_lo_que_si_salio(handler) -> None:
    """En las cuatro la petición SÍ se emitió: las fotografías cruzaron la frontera y el
    registro tiene que decirlo, tanto o más que en el camino feliz."""
    req = _con_imagenes(_con_danos(verdict_basis=BASIS))
    out = await _proveedor_directo(handler).generate(req)
    assert out.provider == "deterministic", "el fixture no llegó a degradar"
    assert out.photos_sent == _huellas(req), (
        "una petición que SÍ salió no anotó las fotografías que llevaba"
    )
    assert out.photos_sent, "la aserción de arriba compara dos vacíos"


@pytest.mark.parametrize(
    "excepcion",
    [
        pytest.param(httpx.ConnectError, id="ConnectError · DNS o rechazo"),
        pytest.param(httpx.ConnectTimeout, id="ConnectTimeout"),
    ],
)
async def test_si_el_SOCKET_no_se_abre_no_se_anota_ninguna_fotografia(excepcion) -> None:
    """El defecto que contradecía al comentario del propio fichero: `_huellas` se
    llamaba en la rama de fallo sin mirar de qué fallo se trataba. Con un `ConnectError`
    no sale un solo byte de la nube, y quedaba escrito —en un registro que no se poda
    nunca— que unas fotografías de evidencia habían viajado a otro país."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise excepcion("no hay a quién conectarse", request=request)

    req = _con_imagenes(_con_danos(verdict_basis=BASIS))
    out = await _proveedor_directo(handler).generate(req)
    assert out.provider == "deterministic"
    assert out.photos_sent == (), "se anotó una transferencia que no ocurrió"
    assert MOTIVO_PROVEEDOR_MUDO in (out.degraded_reason or "")


async def test_la_MISMA_fotografia_en_dos_reportes_se_anota_UNA_vez() -> None:
    """`photos_sent` contesta *cuáles* salieron, no cuántas veces: una misma fotografía
    puede estar en dos reportes de daño del mismo incidente."""
    import dataclasses  # noqa: PLC0415

    m = _con_danos(verdict_basis=BASIS)
    m.danos.append(dataclasses.replace(m.danos[0], report_id="rep-2"))
    req = _con_imagenes(m)
    assert len(req.images) == 2, "el fixture no repitió la fotografía"
    out = await _proveedor_directo(_chat_grabado).generate(req)
    assert len(out.photos_sent) == 1, f"la misma huella se anotó dos veces: {out.photos_sent}"
