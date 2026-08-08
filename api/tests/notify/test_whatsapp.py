"""WhatsApp Business por PLANTILLA PREAPROBADA (T-2.77). CERO red: MockTransport.

Los tres criterios de la ficha —plantillas versionadas en el repo, degradación
explícita cuando Meta rechaza o pausa, y evidencia de entrega como los demás
canales— más lo que la ficha no dice y decide si alguien recibe el aviso: qué
significa exactamente un ``accepted``, qué pasa si Meta recategoriza la
plantilla, y por qué sin opt-in registrado este canal se niega a hablar.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from takab_api.notify.providers import NotifyError, SimulatedProvider, is_simulated
from takab_api.notify.whatsapp import (
    BODY_MAX_CHARS,
    TEMPLATES_DIR,
    UTILITY_TTL_MAX_S,
    UTILITY_TTL_MIN_S,
    WHATSAPP_HINT,
    TemplateCatalog,
    WhatsAppTemplateProvider,
    build_whatsapp_provider,
    fold_parameter,
    is_delivery_confirmed,
    render_parameters,
    template_digest,
)
from takab_api.settings import Settings

MESSAGE = {
    "incident_id": "11111111-0000-0000-0000-000000000001",
    "severity": "critical",
    "site_name": "Torre A",
    "site_code": "TA-01",
    "headline": "TAKAB Ailert · Incidente critical · Torre A",
}
#: El destino LLEVA el opt-in: WhatsApp solo permite contactar a quien lo dio.
TARGET = {"to": "+525511111111", "opt_in": {"at": "2026-08-01T12:00:00Z"}}

_PHONE_ID = "123456789012345"
_TOKEN = "EAAGf0ffffffffffffffffffffffffffffffffff"
_VERSION = "v23.0"


# --- utilidades ---------------------------------------------------------------


def _aprobar(tmp_path: Path, **cambios: object) -> Path:
    """Copia los artefactos REALES del repo con el sello de aprobación puesto.

    Los tests del camino feliz no pueden usar el artefacto tal cual está en el
    repo: hoy nadie lo ha mandado a Meta, así que su estado es ``PENDING`` y el
    canal está caído A PROPÓSITO. Aquí se simula el día después de la
    aprobación, sin tocar el texto —el digest tiene que seguir cuadrando—.
    """
    destino = tmp_path / f"plantillas-{len(list(tmp_path.iterdir()))}"
    destino.mkdir()
    for src in sorted(TEMPLATES_DIR.glob("*.json")):
        doc = json.loads(src.read_text(encoding="utf-8"))
        doc.update(cambios)
        doc["approval"] = {
            "status": "APPROVED",
            "approved_digest": template_digest(doc["template"]),
            "meta_template_id": "1234567890",
            "reviewed_at": "2026-08-07T00:00:00Z",
        }
        (destino / src.name).write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    return destino


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "notify_whatsapp_phone_number_id": _PHONE_ID,
        "notify_whatsapp_access_token": _TOKEN,
        "notify_whatsapp_graph_version": _VERSION,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


class _Meta:
    """Meta de mentira: cuenta peticiones y devuelve lo que se le diga."""

    def __init__(self, *responses: httpx.Response) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]

    @property
    def calls(self) -> int:
        return len(self.requests)

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content.decode())


def _accepted(status: str = "accepted", *, wamid: str = "wamid.HBg1") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "messaging_product": "whatsapp",
            "contacts": [{"input": "525511111111", "wa_id": "525511111111"}],
            "messages": [{"id": wamid, "message_status": status}],
        },
    )


def _error(code: int, *, http: int = 400, message: str = "boom") -> httpx.Response:
    return httpx.Response(
        http, json={"error": {"message": message, "code": code, "type": "OAuthException"}}
    )


class _Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _provider(handler, tmp_path: Path, *, clock=None, **kw) -> WhatsAppTemplateProvider:
    settings = _settings(notify_whatsapp_templates_dir=str(_aprobar(tmp_path)), **kw)
    provider = build_whatsapp_provider(
        settings, transport=httpx.MockTransport(handler), clock=clock
    )
    assert isinstance(provider, WhatsAppTemplateProvider)
    return provider


# =============================================================================
# CRITERIO 1 · plantillas aprobadas y VERSIONADAS EN EL REPO
# =============================================================================


def test_el_repo_trae_al_menos_una_plantilla_versionada() -> None:
    """El artefacto existe y es un fichero de texto que se revisa en un diff."""
    artefactos = sorted(TEMPLATES_DIR.glob("*.json"))
    assert artefactos, f"no hay ningún artefacto de plantilla en {TEMPLATES_DIR}"


def test_el_artefacto_es_EXACTAMENTE_el_payload_de_alta_de_meta() -> None:
    """El bloque ``template`` se manda tal cual a ``POST /message_templates``.

    Por eso el formato es JSON y no YAML ni un literal de Python: si el fichero
    del repo no es *literalmente* lo que se le envía a Meta, hay una traducción
    en medio, y una traducción es exactamente donde el texto aprobado y el texto
    del repo se separan sin que nadie lo note.
    """
    for ruta in sorted(TEMPLATES_DIR.glob("*.json")):
        doc = json.loads(ruta.read_text(encoding="utf-8"))
        plantilla = doc["template"]
        # Los campos que documenta la API de alta de plantillas de Meta.
        assert set(plantilla) <= {
            "name",
            "language",
            "category",
            "components",
            "parameter_format",
            "message_send_ttl_seconds",
            "allow_category_change",
        }, f"{ruta.name} trae un campo que la API de alta de Meta no acepta"
        assert {"name", "language", "category", "components"} <= set(plantilla)


def test_el_nombre_de_la_plantilla_respeta_la_regla_de_meta() -> None:
    """Meta: «lowercase alphanumeric and underscores only». Un nombre inválido
    no se descubre en el despliegue: se descubre al pedir la aprobación, semanas
    después, cuando ya no queda margen."""
    catalogo = TemplateCatalog.load(TEMPLATES_DIR)
    assert catalogo.templates
    for plantilla in catalogo.templates:
        assert plantilla.name.islower()
        assert plantilla.name.replace("_", "").isalnum()


def test_una_alerta_de_sismo_JAMAS_puede_ser_categoria_MARKETING() -> None:
    """No es estética: si la plantilla acaba en MARKETING, el destinatario que
    haya rechazado marketing deja de recibirla (Meta devuelve 131050) — y lo que
    se pierde es el aviso de un terremoto. La categoría correcta es UTILITY, que
    es donde Meta pone «public safety / crisis response»."""
    for plantilla in TemplateCatalog.load(TEMPLATES_DIR).templates:
        assert plantilla.category == "UTILITY", plantilla.name


def test_el_ttl_de_la_plantilla_cabe_en_el_rango_de_utility() -> None:
    """Un aviso de sismo que aterriza mañana es ruido. El TTL de Meta se fija AL
    CREAR la plantilla (no al enviar), así que vive en el artefacto y no en un
    ajuste de entorno. Rango documentado de utility: 30 s .. 12 h."""
    for plantilla in TemplateCatalog.load(TEMPLATES_DIR).templates:
        assert UTILITY_TTL_MIN_S <= plantilla.ttl_s <= UTILITY_TTL_MAX_S
        assert plantilla.ttl_s <= 900, "un aviso sísmico no puede vivir horas en cola"


def test_cada_hueco_del_texto_tiene_su_binding_y_ninguno_sobra() -> None:
    """La cuenta de parámetros se DERIVA del texto aprobado, no se declara dos
    veces. Añadir un {{4}} al cuerpo sin decir de dónde sale pone esto rojo aquí
    y no en Meta con un 132000 («parameter count mismatch») durante un sismo."""
    for plantilla in TemplateCatalog.load(TEMPLATES_DIR).templates:
        huecos = plantilla.placeholders
        assert huecos == tuple(range(1, len(huecos) + 1)), f"{plantilla.name}: huecos sin orden"
        assert len(plantilla.bindings) == len(huecos)


def test_el_cuerpo_cabe_en_el_limite_de_meta() -> None:
    """Máximo documentado del componente body: 1024 caracteres."""
    for plantilla in TemplateCatalog.load(TEMPLATES_DIR).templates:
        assert len(plantilla.body) <= BODY_MAX_CHARS


# --- el candado que hace que cambiar el texto EXIJA volver a aprobar ----------


def test_la_plantilla_del_repo_HOY_no_esta_aprobada_y_por_eso_el_canal_esta_caido() -> None:
    """Nadie la ha mandado a Meta todavía. El repo lo DICE en vez de suponerlo:
    ``PENDING`` ⇒ inservible ⇒ el canal se declara simulado. Esto no es un
    defecto de esta tarea: es el criterio 2 funcionando desde el minuto cero."""
    catalogo = TemplateCatalog.load(TEMPLATES_DIR)
    assert catalogo.usable == ()
    for plantilla in catalogo.templates:
        assert plantilla.usable is False
        assert "PENDING" in plantilla.unusable_reason


def test_tocar_el_texto_de_una_plantilla_aprobada_la_DESAPRUEBA(tmp_path: Path) -> None:
    """El corazón del criterio 1. Meta guarda el texto que aprobó; nosotros solo
    mandamos el NOMBRE. Así que editar el cuerpo en el repo sin volver a pasar
    por Meta no cambia lo que llega al teléfono: crea una mentira silenciosa
    entre lo que el repo dice y lo que la gente lee.

    El sello de aprobación es el digest del bloque que Meta revisó. Cambiar una
    coma mueve el digest y la plantilla deja de estar aprobada AL INSTANTE.
    """
    directorio = _aprobar(tmp_path)
    ruta = next(directorio.glob("*.json"))
    assert TemplateCatalog.load(directorio).usable, "no-vacuidad: aprobada de salida"

    doc = json.loads(ruta.read_text(encoding="utf-8"))
    cuerpo = doc["template"]["components"][0]
    cuerpo["text"] = cuerpo["text"] + " Gracias."
    ruta.write_text(json.dumps(doc, ensure_ascii=False, indent=2))

    catalogo = TemplateCatalog.load(directorio)
    assert catalogo.usable == ()
    assert "digest" in catalogo.templates[0].unusable_reason


def test_un_artefacto_ilegible_no_tumba_el_worker(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Un JSON roto se salta con un ERROR ruidoso. Reventar aquí dejaría al
    worker sin arrancar y, con él, sin NINGÚN canal de aviso."""
    caplog.set_level(logging.ERROR, logger="takab_api.notify")
    directorio = _aprobar(tmp_path)
    (directorio / "roto.json").write_text("{ esto no es json", encoding="utf-8")

    catalogo = TemplateCatalog.load(directorio)
    assert catalogo.usable, "las sanas siguen sirviendo"
    assert any("roto.json" in r.getMessage() for r in caplog.records)


# =============================================================================
# CRITERIO 2 · degradación explícita: EL CANAL CAE, NO FINGE
# =============================================================================


def test_sin_credenciales_el_canal_es_simulado() -> None:
    """El invariante que T-2.75 compró por las malas, una capa más abajo."""
    provider = build_whatsapp_provider(Settings())
    assert isinstance(provider, SimulatedProvider)
    assert is_simulated(provider) is True


@pytest.mark.parametrize(
    "falta",
    [
        "notify_whatsapp_phone_number_id",
        "notify_whatsapp_access_token",
        "notify_whatsapp_graph_version",
    ],
)
def test_credenciales_a_medias_no_ascienden_el_canal(
    falta: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Media credencial es cero credencial, y grita. La versión de Graph cuenta
    como credencial porque va EN LA RUTA y Meta retira versiones: un default
    adivinado se convierte en 400 el día que caduca."""
    caplog.set_level(logging.ERROR, logger="takab_api.notify")
    provider = build_whatsapp_provider(_settings(**{falta: ""}))
    assert is_simulated(provider) is True
    assert any("A MEDIAS" in r.getMessage() for r in caplog.records)


def test_el_hint_nombra_las_variables_que_faltan() -> None:
    hint = build_whatsapp_provider(Settings()).hint  # type: ignore[union-attr]
    assert hint == WHATSAPP_HINT
    assert "TAKAB_API_NOTIFY_WHATSAPP_PHONE_NUMBER_ID" in hint
    assert "TAKAB_API_NOTIFY_WHATSAPP_ACCESS_TOKEN" in hint


def test_con_credenciales_pero_SIN_plantilla_aprobada_el_canal_se_declara_simulado() -> None:
    """El caso que da nombre al criterio 2, y el estado real de hoy. Hay token,
    hay número, hay red — y aun así NADIE puede recibir nada, porque WhatsApp no
    deja improvisar texto. El canal no finge: se declara simulado, el
    orquestador escribe ``notify_simulated`` y escala al SMS."""
    provider = build_whatsapp_provider(_settings())
    assert isinstance(provider, WhatsAppTemplateProvider)
    assert is_simulated(provider) is True
    assert "plantilla" in provider.hint.lower()


def test_con_la_plantilla_aprobada_el_canal_asciende_a_real(tmp_path: Path) -> None:
    """No-vacuidad del test anterior: el día que Meta apruebe, sube solo."""
    provider = build_whatsapp_provider(
        _settings(notify_whatsapp_templates_dir=str(_aprobar(tmp_path)))
    )
    assert isinstance(provider, WhatsAppTemplateProvider)
    assert is_simulated(provider) is False


def test_una_plantilla_REJECTED_deja_el_canal_caido(tmp_path: Path) -> None:
    """Meta rechaza plantillas por política y por calidad. Rechazada = el canal
    no tiene con qué hablar. Ni texto libre (Meta lo rechaza fuera de la ventana
    de servicio) ni otra plantilla: cae, y lo dice."""
    directorio = _aprobar(tmp_path)
    ruta = next(directorio.glob("*.json"))
    doc = json.loads(ruta.read_text(encoding="utf-8"))
    doc["approval"]["status"] = "REJECTED"
    ruta.write_text(json.dumps(doc, ensure_ascii=False, indent=2))

    provider = build_whatsapp_provider(_settings(notify_whatsapp_templates_dir=str(directorio)))
    assert is_simulated(provider) is True


@pytest.mark.parametrize("estado", ["PENDING", "PAUSED", "DISABLED", "IN_APPEAL", "LIMIT_EXCEEDED"])
def test_solo_APPROVED_sirve_todo_lo_demas_cae(tmp_path: Path, estado: str) -> None:
    """Derivado, no enumerado: sirve ``APPROVED`` y punto. Los otros nueve
    estados del enum de Meta —y el décimo que invente mañana— caen solos."""
    directorio = _aprobar(tmp_path)
    ruta = next(directorio.glob("*.json"))
    doc = json.loads(ruta.read_text(encoding="utf-8"))
    doc["approval"]["status"] = estado
    ruta.write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    assert TemplateCatalog.load(directorio).usable == ()


# --- Meta PAUSA la plantilla EN CALIENTE, en mitad de un incidente ------------


def test_un_132015_pausa_la_plantilla_y_TUMBA_el_canal(tmp_path: Path) -> None:
    """El escenario que da nombre al criterio 2. Meta pausa una plantilla por
    baja calidad SIN avisar (error 132015). El envío falla —hasta ahí, normal—
    pero además la plantilla queda EN CUARENTENA, así que el canal entero se
    declara simulado para el siguiente incidente en vez de seguir estrellándose
    contra una plantilla muerta y llamándolo «fallo transitorio»."""
    meta = _Meta(_error(132015, message="Template is paused"))
    provider = _provider(meta, tmp_path)
    assert is_simulated(provider) is False

    with pytest.raises(NotifyError, match="132015"):
        provider.send(TARGET, MESSAGE)

    assert is_simulated(provider) is True  # el canal CAE
    assert provider.quarantined


def test_cualquier_error_132xxx_es_culpa_de_la_plantilla(tmp_path: Path) -> None:
    """Derivado por FAMILIA, no por lista: 132015 (pausada), 132016
    (deshabilitada), 132001 (no existe o no aprobada), 132007 (viola política),
    132000 (número de parámetros)... y el 132xxx que Meta añada mañana. Todos
    significan lo mismo: con ESTA plantilla no se puede hablar, y reintentar
    solo empeora la calificación de calidad."""
    for code in (132000, 132001, 132005, 132007, 132012, 132015, 132016, 132099):
        provider = _provider(_Meta(_error(code)), tmp_path)
        with pytest.raises(NotifyError):
            provider.send(TARGET, MESSAGE)
        assert is_simulated(provider) is True, f"{code} debería tumbar el canal"


def test_un_error_que_NO_es_de_plantilla_no_tumba_el_canal(tmp_path: Path) -> None:
    """No-vacuidad de la cuarentena: un 131026 («unable to deliver message») es
    problema de ESE destinatario, no de la plantilla. Tumbar el canal entero por
    un número mal escrito sería el error simétrico."""
    provider = _provider(_Meta(_error(131026)), tmp_path)
    with pytest.raises(NotifyError):
        provider.send(TARGET, MESSAGE)
    assert is_simulated(provider) is False
    assert not provider.quarantined


def test_un_message_status_paused_en_un_200_tambien_tumba_el_canal(tmp_path: Path) -> None:
    """Trampa fina de esta API: Meta puede responder **200** y decir dentro que
    el mensaje quedó ``paused``. Un ``if response.is_success: return`` lo habría
    contado como enviado. HTTP 200 ≠ mensaje en camino."""
    provider = _provider(_Meta(_accepted("paused")), tmp_path)
    with pytest.raises(NotifyError, match="paused"):
        provider.send(TARGET, MESSAGE)
    assert is_simulated(provider) is True


# =============================================================================
# CRITERIO 3 · evidencia de entrega, con el mismo rasero que los demás canales
# =============================================================================


def test_nada_de_lo_que_devuelve_el_POST_es_una_entrega(tmp_path: Path) -> None:
    """El corazón de la tarea, heredado de T-2.76. Los tres valores que Meta
    documenta para ``message_status`` en la respuesta del POST son ``accepted``,
    ``held_for_quality_assessment`` y ``paused``, y NINGUNO significa «llegó al
    teléfono»: ``accepted`` es «aceptado por WhatsApp y en proceso». La palabra
    ``delivered`` solo llega después, por webhook, que aquí no existe todavía."""
    for status in ("accepted", "held_for_quality_assessment", "paused", "sent"):
        assert is_delivery_confirmed(status) is False
    assert is_delivery_confirmed("delivered") is True  # no-vacuidad
    assert is_delivery_confirmed("read") is True


def test_el_envio_aceptado_lo_dice_en_el_log_sin_llamarlo_entregado(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="takab_api.notify")
    _provider(_Meta(_accepted()), tmp_path).send(TARGET, MESSAGE)

    linea = next(r.getMessage() for r in caplog.records if "wamid" in r.getMessage())
    assert "accepted" in linea
    assert "NO confirmada" in linea
    assert "entregado" not in linea.lower()


def test_el_recibo_guarda_wamid_estado_y_plantilla(tmp_path: Path) -> None:
    """Evidencia igual que los demás canales: el identificador con el que Meta
    conocerá el desenlace tardío (``wamid``) queda guardado desde el minuto uno,
    para que el día del webhook haya con qué casar el job."""
    provider = _provider(_Meta(_accepted(wamid="wamid.XYZ")), tmp_path)
    provider.send(TARGET, MESSAGE)
    recibo = provider.last_receipt
    assert recibo is not None
    assert recibo.wamid == "wamid.XYZ"
    assert recibo.status == "accepted"
    assert recibo.delivery_confirmed is False
    assert recibo.category == "UTILITY"


def test_un_held_for_quality_assessment_no_cuenta_como_enviado(tmp_path: Path) -> None:
    """Meta lo retuvo para evaluarlo. Puede salir o no; nadie lo sabe. El
    default ante lo desconocido es la peor causa: se escala al canal siguiente
    en vez de dar por avisado a un humano que quizá no lo esté."""
    with pytest.raises(NotifyError, match="held_for_quality_assessment"):
        _provider(_Meta(_accepted("held_for_quality_assessment")), tmp_path).send(TARGET, MESSAGE)


def test_un_message_status_DESCONOCIDO_se_trata_como_la_peor_causa(tmp_path: Path) -> None:
    """Lo que enumera se queda ciego ante el siguiente caso."""
    with pytest.raises(NotifyError, match="teleported"):
        _provider(_Meta(_accepted("teleported")), tmp_path).send(TARGET, MESSAGE)


def test_un_200_sin_wamid_no_cuenta_como_envio(tmp_path: Path) -> None:
    respuesta = httpx.Response(200, json={"messaging_product": "whatsapp", "messages": []})
    with pytest.raises(NotifyError, match="wamid"):
        _provider(_Meta(respuesta), tmp_path).send(TARGET, MESSAGE)


# =============================================================================
# LA PETICIÓN QUE SALE
# =============================================================================


def test_la_peticion_es_un_template_y_JAMAS_texto_libre(tmp_path: Path) -> None:
    """WhatsApp no deja improvisar: fuera de la ventana de servicio de 24 h la
    plantilla es el ÚNICO tipo de mensaje que se puede enviar. Y como aquí el
    destinatario nunca escribió primero, la ventana está SIEMPRE cerrada."""
    meta = _Meta(_accepted())
    _provider(meta, tmp_path).send(TARGET, MESSAGE)

    body = meta.body()
    assert body["messaging_product"] == "whatsapp"
    assert body["recipient_type"] == "individual"
    assert body["type"] == "template"
    assert "text" not in body, "un cuerpo de texto libre sería rechazado por Meta (131047)"
    assert body["template"]["name"]
    assert body["template"]["language"]["code"] == "es_MX"


def test_la_peticion_va_a_la_ruta_versionada_del_numero(tmp_path: Path) -> None:
    meta = _Meta(_accepted())
    _provider(meta, tmp_path).send(TARGET, MESSAGE)
    url = str(meta.requests[0].url)
    assert url == f"https://graph.facebook.com/{_VERSION}/{_PHONE_ID}/messages"
    assert meta.requests[0].headers["authorization"] == f"Bearer {_TOKEN}"


def test_los_parametros_van_en_orden_y_completos(tmp_path: Path) -> None:
    """Los valores salen del artefacto, no de un diccionario paralelo: si el
    binding dice que {{1}} es el nombre del sitio, {{1}} ES el nombre del sitio.
    Mandar de menos o de más es un 132000 de Meta."""
    meta = _Meta(_accepted())
    provider = _provider(meta, tmp_path)
    provider.send(TARGET, MESSAGE)

    componentes = meta.body()["template"]["components"]
    cuerpo = next(c for c in componentes if c["type"] == "body")
    valores = [p["text"] for p in cuerpo["parameters"]]
    assert all(p["type"] == "text" for p in cuerpo["parameters"])
    assert valores[0] == "Torre A"
    assert len(valores) == len(provider.catalog.usable[0].bindings)


def test_un_campo_ausente_del_mensaje_no_manda_un_hueco_vacio(tmp_path: Path) -> None:
    """Meta rechaza parámetros mal formados (132012) y un hueco en blanco en un
    aviso de sismo es peor que un aviso genérico. Cada binding trae su relleno."""
    meta = _Meta(_accepted())
    _provider(meta, tmp_path).send(TARGET, {"incident_id": "abc"})
    valores = [p["text"] for p in meta.body()["template"]["components"][0]["parameters"]]
    assert all(v.strip() for v in valores)


@pytest.mark.parametrize(
    "nombre",
    [
        "Torre\nÁmbar",  # salto de línea: 132012 esperando
        "Hospital \t\t Central",  # tabuladores
        "Sede " + "Muy Larga " * 200,  # desborda el cuerpo de 1024
        "Torre\u200b\x00\u00ad Cero",  # invisibles: zero-width, NUL, guion blando
        "医院 🏥",  # fuera del latino
    ],
)
def test_ningun_nombre_de_sitio_rompe_el_cuerpo_ni_los_parametros(
    tmp_path: Path, nombre: str
) -> None:
    """Derivado del catálogo de caracteres, no de una lista de casos: se tira
    todo lo que Unicode clasifica como control/formato y se colapsa el espacio,
    así que vale para el carácter que nadie ha visto todavía. Y el cuerpo
    RENDERIZADO sigue cabiendo en los 1024 de Meta."""
    meta = _Meta(_accepted())
    provider = _provider(meta, tmp_path)
    provider.send(TARGET, {**MESSAGE, "site_name": nombre})

    plantilla = provider.catalog.usable[0]
    valores = [p["text"] for p in meta.body()["template"]["components"][0]["parameters"]]
    assert all("\n" not in v and "\t" not in v for v in valores)
    assert all(v == v.strip() and v for v in valores)
    assert len(plantilla.render(valores)) <= BODY_MAX_CHARS


def test_el_plegado_conserva_el_texto_legible() -> None:
    """No-vacuidad del plegado: no vale devolver cadena vacía y cantar victoria.
    A diferencia del SMS (GSM-7), aquí los acentos SÍ se conservan: WhatsApp es
    UTF-8 y se factura por mensaje entregado, no por segmento."""
    assert fold_parameter("Torre Ámbar", 100) == "Torre Ámbar"
    assert fold_parameter("  Torre \n\n Ámbar  ", 100) == "Torre Ámbar"
    assert fold_parameter("A" * 50, 10) == "A" * 10


def test_la_referencia_del_incidente_sobrevive_a_un_nombre_kilometrico(tmp_path: Path) -> None:
    """Se recorta el nombre del sitio, nunca la referencia: es lo que el
    operador teclea en la consola."""
    meta = _Meta(_accepted())
    provider = _provider(meta, tmp_path)
    provider.send(TARGET, {**MESSAGE, "site_name": "X" * 4000})
    valores = [p["text"] for p in meta.body()["template"]["components"][0]["parameters"]]
    assert MESSAGE["incident_id"][:8] in valores[-1]


def test_render_parameters_falla_ruidosamente_si_falta_un_binding(tmp_path: Path) -> None:
    """No-vacuidad de la derivación: si el texto y los bindings se desincronizan
    en caliente, no se manda un mensaje con un hueco — se para."""
    plantilla = TemplateCatalog.load(_aprobar(tmp_path)).usable[0]
    roto = plantilla.__class__(**{**plantilla.__dict__, "bindings": plantilla.bindings[:-1]})
    with pytest.raises(NotifyError, match="parámetros"):
        render_parameters(roto, MESSAGE)


# =============================================================================
# OPT-IN · WhatsApp solo permite hablarle a quien lo consintió
# =============================================================================


def test_sin_opt_in_registrado_el_canal_se_niega_a_hablar(tmp_path: Path) -> None:
    """Hallazgo de esta tarea, y no es burocracia: la política de WhatsApp
    Business condiciona CUALQUIER contacto a un opt-in previo, y enviar sin él
    no rebota un mensaje — degrada la calidad del número y puede tumbar el canal
    para TODOS los tenants a la vez. Así que sin constancia no sale, y queda
    ``notify_failed`` en rojo en la consola: evidencia, no silencio."""
    meta = _Meta(_accepted())
    provider = _provider(meta, tmp_path)
    for destino in (
        {"to": "+525511111111"},
        {"to": "+525511111111", "opt_in": {}},
        {"to": "+525511111111", "opt_in": {"at": ""}},
    ):
        with pytest.raises(NotifyError, match="opt-in"):
            provider.send(destino, MESSAGE)
    assert meta.calls == 0  # ni una petición: se para antes de incumplir


def test_con_opt_in_fechado_si_sale(tmp_path: Path) -> None:
    """No-vacuidad. Y la fecha no es adorno: un consentimiento sin instante no
    se puede probar anterior al mensaje, así que no es un consentimiento."""
    meta = _Meta(_accepted())
    _provider(meta, tmp_path).send(TARGET, MESSAGE)
    assert meta.calls == 1


def test_este_canal_tampoco_hace_fan_out(tmp_path: Path) -> None:
    """Como el SMS: la guardia del SOC, no el altavoz de los ocupantes. Y aquí
    además cada destinatario extra necesita su PROPIO opt-in."""
    meta = _Meta(_accepted())
    provider = _provider(meta, tmp_path)
    for destino in ({"to": ["+5255111", "+5255222"]}, {"to": "+5255111,+5255222"}, {"to": ""}, {}):
        with pytest.raises(NotifyError):
            provider.send(destino, MESSAGE)  # type: ignore[arg-type]
    assert meta.calls == 0


def test_el_opt_in_viaja_desde_el_rule_set_hasta_el_provider() -> None:
    """El opt-in se configura junto al destino y tiene que LLEGAR: si
    ``resolve_destinations`` lo tirara por el camino, el provider se negaría a
    enviar siempre y el canal estaría caído sin que nadie supiera por qué."""
    from takab_api.notify.config import resolve_destinations

    opt_in = {"at": "2026-08-01T12:00:00Z", "evidence": "alta firmada"}
    destinos = resolve_destinations(
        {"notifications": {"whatsapp": {"to": "+52551", "opt_in": opt_in}}}
    )
    assert destinos["whatsapp"] == {"to": "+52551", "opt_in": opt_in}
    # No-vacuidad: sin opt-in el destino sigue existiendo (para que el fallo se
    # VEA como notify_failed y no como un canal que desaparece en silencio).
    assert resolve_destinations({"notifications": {"whatsapp": {"to": "+52551"}}})["whatsapp"] == {
        "to": "+52551"
    }


# =============================================================================
# REINTENTOS · un aviso de sismo duplicado en mitad de una evacuación
# =============================================================================


def test_el_provider_no_reintenta_por_dentro(tmp_path: Path) -> None:
    meta = _Meta(httpx.Response(500, json={}))
    with pytest.raises(NotifyError):
        _provider(meta, tmp_path).send(TARGET, MESSAGE)
    assert meta.calls == 1


def test_un_fallo_AMBIGUO_no_se_reenvia_al_mismo_incidente(tmp_path: Path) -> None:
    """Meta no documenta clave de idempotencia en este endpoint, así que la pone
    el dominio: (destino, incidente). Un 5xx pudo haber creado el mensaje."""
    meta = _Meta(httpx.Response(500, json={}))
    provider = _provider(meta, tmp_path)
    with pytest.raises(NotifyError):
        provider.send(TARGET, MESSAGE)
    with pytest.raises(NotifyError, match="duplicado"):
        provider.send(TARGET, MESSAGE)
    assert meta.calls == 1


def test_un_rechazo_explicito_de_destinatario_si_permite_reintentar(tmp_path: Path) -> None:
    """No-vacuidad de la guarda: un 4xx demuestra que no se creó nada."""
    meta = _Meta(_error(131026))
    provider = _provider(meta, tmp_path)
    for _ in range(2):
        with pytest.raises(NotifyError):
            provider.send(TARGET, MESSAGE)
    assert meta.calls == 2


def test_la_guarda_caduca_con_el_ttl_de_la_plantilla(tmp_path: Path) -> None:
    """El TTL se DERIVA de la propia plantilla (``message_send_ttl_seconds``),
    no de un número mágico: pasado ese instante Meta ya descartó lo encolado,
    luego no queda nada vivo que duplicar."""
    reloj = _Reloj()
    meta = _Meta(_accepted())
    provider = _provider(meta, tmp_path, clock=reloj)
    ttl = provider.catalog.usable[0].ttl_s

    provider.send(TARGET, MESSAGE)
    reloj.t += ttl - 1
    with pytest.raises(NotifyError, match="duplicado"):
        provider.send(TARGET, MESSAGE)
    reloj.t += 2
    provider.send(TARGET, MESSAGE)
    assert meta.calls == 2
    assert provider.pending_keys == 1


def test_otro_incidente_al_mismo_numero_si_sale(tmp_path: Path) -> None:
    meta = _Meta(_accepted())
    provider = _provider(meta, tmp_path)
    provider.send(TARGET, MESSAGE)
    provider.send(TARGET, {**MESSAGE, "incident_id": "22222222-0000-0000-0000-000000000002"})
    assert meta.calls == 2


# =============================================================================
# HIGIENE · el token, el arranque y el enchufe
# =============================================================================


def test_el_token_no_aparece_en_errores_ni_en_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="takab_api.notify")
    meta = _Meta(_error(190, http=401, message=f"invalid token {_TOKEN}"))
    with pytest.raises(NotifyError) as err:
        _provider(meta, tmp_path).send(TARGET, MESSAGE)
    assert _TOKEN not in str(err.value)
    assert all(_TOKEN not in r.getMessage() for r in caplog.records)


def test_el_constructor_no_toca_la_red(tmp_path: Path) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("el constructor no debe hacer peticiones")

    provider = _provider(handler, tmp_path)
    assert provider.last_receipt is None


def test_el_arranque_declara_plantilla_categoria_ttl_y_que_no_hay_entrega(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """El único momento en que un humano mira es el arranque. Ahí se dice qué
    plantilla se usa, en qué categoría (que decide coste y entregabilidad) y que
    un ``notify_sent`` de este canal significa ACEPTADO, no entregado."""
    caplog.set_level(logging.INFO, logger="takab_api.notify")
    build_whatsapp_provider(_settings(notify_whatsapp_templates_dir=str(_aprobar(tmp_path))))
    mensajes = [r.getMessage() for r in caplog.records]
    arranque = next(m for m in mensajes if "whatsapp" in m and "UTILITY" in m)
    assert "es_MX" in arranque
    assert any("NO hay confirmación de entrega" in m for m in mensajes)


def test_el_registro_de_providers_usa_whatsapp_cuando_hay_plantilla(tmp_path: Path) -> None:
    """El enchufe real: ``build_providers`` (lo que arranca el worker)."""
    from takab_api.notify.providers import build_providers

    settings = _settings(notify_whatsapp_templates_dir=str(_aprobar(tmp_path)))
    assert isinstance(build_providers(settings)["whatsapp"], WhatsAppTemplateProvider)
    assert is_simulated(build_providers(Settings())["whatsapp"]) is True


def test_el_orquestador_no_sabe_que_existe_whatsapp_cloud() -> None:
    """No-vacuidad del «el orquestador NO cambia»: si alguien mete una rama
    ``if channel == 'whatsapp'``, esto se pone rojo. Es la única comprobación de
    esa promesa que no depende de mirar el diff. Espejo del test de T-2.76."""
    from pathlib import Path as _Path

    import takab_api.notify.orchestrator as orch

    fuente = _Path(orch.__file__).read_text(encoding="utf-8")
    # Una rama por canal se escribe con el nombre ENTRECOMILLADO (así están las
    # de 'webhook' y 'push'). Que no exista ninguna con 'whatsapp' es la prueba
    # de que el canal se enchufó por el contrato y no por un caso especial. El
    # nombre suelto sí aparece: la prosa de T-2.75 narra el bug del simulado.
    assert '"whatsapp"' not in fuente and "'whatsapp'" not in fuente
    assert "graph.facebook" not in fuente.lower()
    assert "plantilla" not in fuente.lower()
    assert '"push"' in fuente  # no-vacuidad: así se ve una rama por canal
