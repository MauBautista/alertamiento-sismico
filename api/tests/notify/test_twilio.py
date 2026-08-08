"""SMS real por Twilio (T-2.76). CERO red: todo contra ``httpx.MockTransport``.

Los tres criterios de la ficha, más lo que la ficha no dice y cuesta dinero o
vidas: qué pasa SIN credenciales, qué significa exactamente un ``queued``, y por
qué un reintento puede duplicar un SMS en el peor momento.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from takab_api.notify.plan import CASCADE_ORDER
from takab_api.notify.providers import NotifyError, SimulatedProvider, is_simulated
from takab_api.notify.twilio import (
    TWILIO_LIMITS,
    TWILIO_MAX_VALIDITY_S,
    TWILIO_MIN_VALIDITY_S,
    TwilioSmsProvider,
    build_sms_provider,
    compose_sms_body,
    is_delivery_confirmed,
    messages_per_budget,
    resolve_validity_period_s,
    sms_deadline_headroom,
    sms_segments,
    to_gsm7,
)
from takab_api.settings import Settings

MESSAGE = {
    "incident_id": "11111111-0000-0000-0000-000000000001",
    "severity": "critical",
    "site_name": "Torre A",
    "site_code": "TA-01",
    "headline": "TAKAB Ailert · Incidente critical · Torre A",
}
TARGET = {"to": "+525522222222"}

_SID = "ACffffffffffffffffffffffffffffffff"
_TOKEN = "f0ffffffffffffffffffffffffffffff"


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "notify_sms_account_sid": _SID,
        "notify_sms_auth_token": _TOKEN,
        "notify_sms_from": "+525599999999",
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


class _Twilio:
    """Twilio de mentira: cuenta peticiones y devuelve lo que se le diga."""

    def __init__(self, *responses: httpx.Response) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(response, Exception):  # pragma: no cover - defensivo
            raise response
        return response

    @property
    def calls(self) -> int:
        return len(self.requests)

    def form(self, index: int = 0) -> dict[str, str]:
        raw = self.requests[index].content.decode()
        return dict(pair.split("=", 1) for pair in raw.split("&") if pair)


def _created(status: str = "queued", *, sid: str = "SM1", code: int = 201) -> httpx.Response:
    return httpx.Response(code, json={"sid": sid, "status": status, "num_segments": "1"})


class _Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _provider(handler, *, clock=None, **kw) -> TwilioSmsProvider:
    settings = _settings(**kw)
    return TwilioSmsProvider(
        account_sid=settings.notify_sms_account_sid,
        auth_token=settings.notify_sms_auth_token,
        from_number=settings.notify_sms_from,
        messaging_service_sid=settings.notify_sms_messaging_service_sid,
        timeout_s=settings.notify_sms_timeout_s,
        validity_period_s=resolve_validity_period_s(settings.notify_sms_validity_period_s),
        status_callback_url=settings.notify_sms_status_callback_url,
        transport=httpx.MockTransport(handler),
        clock=clock,
    )


# --- criterio 1 · misma interfaz, orquestador intacto -------------------------


def test_twilio_cumple_el_contrato_notifyprovider() -> None:
    """Un ``send(target, message)`` y un ``simulated`` declarado. Nada más."""
    provider = _provider(_Twilio(_created()))
    assert is_simulated(provider) is False
    assert callable(provider.send)


def test_el_orquestador_no_sabe_que_existe_twilio() -> None:
    """No-vacuidad del criterio 1: si mañana alguien mete una rama ``if channel
    == 'sms'`` en el orquestador, esto se pone rojo. Es la única forma de
    comprobar «el orquestador NO cambia» que no dependa de mirar el diff."""
    from pathlib import Path

    import takab_api.notify.orchestrator as orch

    fuente = Path(orch.__file__).read_text(encoding="utf-8")
    assert "twilio" not in fuente.lower()
    # Una rama por canal se escribe con el nombre entrecomillado (así están las
    # de 'webhook' y 'push'). Que no exista ninguna con 'sms' es la prueba de
    # que el canal se enchufó por el contrato y no por un caso especial.
    assert '"sms"' not in fuente and "'sms'" not in fuente
    assert '"push"' in fuente  # no-vacuidad: así se ve una rama por canal


# --- criterio 2 · SIN CREDENCIALES el canal cae a simulado, jamás a sent ------


def test_sin_credenciales_el_canal_sms_es_simulado() -> None:
    """El invariante que T-2.75 compró por las malas, una capa más abajo."""
    provider = build_sms_provider(Settings())
    assert isinstance(provider, SimulatedProvider)
    assert is_simulated(provider) is True


def test_credenciales_a_medias_no_ascienden_el_canal_a_real(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Media credencial es CERO credencial: sin token no se entrega nada. Y no
    calla — un canal que se cree real y no lo es es peor que uno apagado."""
    caplog.set_level(logging.ERROR, logger="takab_api.notify")
    provider = build_sms_provider(_settings(notify_sms_auth_token=""))
    assert is_simulated(provider) is True
    assert any("A MEDIAS" in r.getMessage() for r in caplog.records)


def test_con_credenciales_completas_el_canal_asciende_a_real() -> None:
    """No-vacuidad del test anterior: con las tres piezas SÍ sube a Twilio."""
    assert isinstance(build_sms_provider(_settings()), TwilioSmsProvider)
    assert isinstance(
        build_sms_provider(_settings(notify_sms_from="", notify_sms_messaging_service_sid="MG1")),
        TwilioSmsProvider,
    )


def test_el_hint_del_simulado_nombra_las_variables_que_faltan() -> None:
    hint = build_sms_provider(Settings()).hint  # type: ignore[union-attr]
    assert "TAKAB_API_NOTIFY_SMS_ACCOUNT_SID" in hint
    assert "TAKAB_API_NOTIFY_SMS_AUTH_TOKEN" in hint


# --- criterio 2 · límites DECLARADOS, no descubiertos en la factura -----------


def test_los_limites_estan_declarados_con_su_fuente() -> None:
    """Fijados aquí para que un cambio de precio o de tasa sea un test rojo y no
    una sorpresa en la factura. Fuentes verificadas el 2026-08-07 (docstring)."""
    assert TWILIO_LIMITS.cost_per_segment_usd == pytest.approx(0.1819)
    assert TWILIO_LIMITS.sender_mps == pytest.approx(1.0)
    assert TWILIO_LIMITS.queue_ttl_default_s == 36000
    assert TWILIO_MIN_VALIDITY_S == 1
    assert TWILIO_MAX_VALIDITY_S == 36000
    assert "twilio.com" in TWILIO_LIMITS.source


def test_el_presupuesto_de_la_cuenta_se_traduce_a_mensajes() -> None:
    """$50/mes NO son «muchos» SMS: son 274. Escrito, no descubierto."""
    assert messages_per_budget(50.0) == 274


def test_el_plazo_de_sms_solo_es_alcanzable_para_un_puñado_de_mensajes() -> None:
    """El límite de tasa contra el SLA. La ventana se DERIVA del plan (posición
    del sms en la cascada × step), no se copia a mano: si alguien reordena la
    cascada, este número se mueve solo."""
    holgura = sms_deadline_headroom(Settings())
    assert holgura.position == CASCADE_ORDER.index("sms")
    assert holgura.window_s == pytest.approx(10.0)  # t0+20 → deadline t0+30
    assert holgura.max_segments == 10
    assert holgura.reachable is True


def test_el_plazo_se_declara_INALCANZABLE_si_la_ventana_no_da() -> None:
    """No-vacuidad: con el deadline por debajo del escalón, la ventana es
    negativa y el canal lo DICE en vez de prometer un SLA que no cumple."""
    holgura = sms_deadline_headroom(Settings(notify_sms_deadline_s=5.0))
    assert holgura.window_s < 0
    assert holgura.max_segments == 0
    assert holgura.reachable is False


# --- coste por mensaje: el que se paga de verdad, no el de la tabla -----------


def test_un_mensaje_normal_cuesta_un_solo_segmento() -> None:
    cuenta = sms_segments("TAKAB Ailert: incidente critical en Torre A")
    assert cuenta.encoding == "GSM-7"
    assert cuenta.segments == 1
    assert cuenta.cost_usd == pytest.approx(0.1819)


def test_un_solo_acento_fuera_de_GSM7_MULTIPLICA_el_coste() -> None:
    """El hallazgo que no está en la ficha: «ALERTA SÍSMICA» lleva una Í que NO
    existe en GSM-7 (la É sí, la Ñ también) ⇒ el SMS ENTERO pasa a UCS-2 y el
    segmento baja de 160 a 70 caracteres. Un carácter, el doble de factura; y
    como el MPS de Twilio se cuenta en SEGMENTOS, el doble de plazo también."""
    texto = "ALERTA SISMICA - PROTEJASE. Incidente critical en Torre Ambar, revise la consola."
    assert sms_segments(texto).segments == 1
    con_acento = sms_segments(texto.replace("SISMICA", "SÍSMICA"))
    assert con_acento.encoding == "UCS-2"
    assert con_acento.segments == 2
    assert con_acento.cost_usd == pytest.approx(2 * 0.1819)
    # Y en el caso peor —un mensaje que llena justo el segmento GSM-7 de 160—
    # el mismo texto acentuado son TRES segmentos: 160/67 = 3.
    lleno = "A" * 159 + "B"
    assert sms_segments(lleno).segments == 1
    assert sms_segments("Á" + lleno[1:]).segments == 3


def test_el_cuerpo_compuesto_es_GSM7_y_cabe_en_un_segmento() -> None:
    """Por eso el cuerpo se pliega a GSM-7 antes de salir."""
    cuenta = sms_segments(compose_sms_body(MESSAGE))
    assert cuenta.encoding == "GSM-7"
    assert cuenta.segments == 1


@pytest.mark.parametrize(
    "nombre",
    [
        "Torre Ámbar",  # acentos que NO están en GSM-7
        "Hospital 🏥 Central",  # emoji (par sustituto en UTF-16)
        "医院",  # fuera de todo alfabeto latino
        "Sede " + "Muy Larga " * 40,  # desborda el segmento por longitud
        "«Torre» — Ñandú, ¿piso 3?",  # comillas tipográficas y raya
    ],
)
def test_ningun_nombre_de_sitio_rompe_el_segmento_ni_la_codificacion(nombre: str) -> None:
    """Derivado, no enumerado: la garantía se comprueba contra el ALFABETO
    GSM-7, así que vale para el carácter que nadie ha visto todavía."""
    cuenta = sms_segments(compose_sms_body({**MESSAGE, "headline": f"Incidente en {nombre}"}))
    assert cuenta.encoding == "GSM-7"
    assert cuenta.segments == 1


def test_el_plegado_a_gsm7_conserva_el_texto_legible() -> None:
    """No-vacuidad del plegado: no vale devolver cadena vacía y cantar victoria."""
    assert to_gsm7("ALERTA SÍSMICA · PROTÉJASE") == "ALERTA SISMICA PROTÉJASE"
    assert to_gsm7("Ñandú") == "Ñandu"  # Ñ y ñ SÍ están en GSM-7; ú no


def test_el_cuerpo_conserva_el_identificador_del_incidente() -> None:
    """Aunque el nombre del sitio sea kilométrico, el id sobrevive: es lo que el
    operador teclea en la consola. Se trunca el nombre, nunca la referencia."""
    body = compose_sms_body({**MESSAGE, "headline": "Incidente en " + "X" * 300})
    assert MESSAGE["incident_id"][:8] in body


# --- publicado ≠ entregado ----------------------------------------------------


def test_un_queued_no_es_una_entrega_confirmada() -> None:
    """El corazón de la tarea. Twilio contesta ``queued``; la ÚNICA palabra suya
    que significa «llegó al teléfono» es ``delivered``, y esa no viaja en la
    respuesta del POST — llega por webhook, que aquí no existe todavía."""
    assert is_delivery_confirmed("queued") is False
    assert is_delivery_confirmed("accepted") is False
    assert is_delivery_confirmed("sending") is False
    assert is_delivery_confirmed("sent") is False  # «sent» de Twilio ≠ entregado
    assert is_delivery_confirmed("delivered") is True


def test_el_envio_aceptado_lo_dice_en_el_log_sin_llamarlo_entregado(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="takab_api.notify")
    twilio = _Twilio(_created("queued"))
    _provider(twilio).send(TARGET, MESSAGE)

    linea = next(r.getMessage() for r in caplog.records if "twilio" in r.getMessage())
    assert "queued" in linea
    assert "NO confirmada" in linea
    assert "entregado" not in linea.lower().replace("no confirmada", "")


def test_el_recibo_guarda_estado_coste_y_segmentos() -> None:
    provider = _provider(_Twilio(_created("queued", sid="SM777")))
    provider.send(TARGET, MESSAGE)
    recibo = provider.last_receipt
    assert recibo is not None
    assert recibo.sid == "SM777"
    assert recibo.status == "queued"
    assert recibo.delivery_confirmed is False
    assert recibo.segments == 1
    assert recibo.cost_usd == pytest.approx(0.1819)


def test_un_estado_terminal_de_fallo_en_la_respuesta_es_un_fallo() -> None:
    with pytest.raises(NotifyError, match="failed"):
        _provider(_Twilio(_created("failed"))).send(TARGET, MESSAGE)


def test_un_estado_DESCONOCIDO_se_trata_como_la_peor_causa() -> None:
    """Lo que enumera se queda ciego ante el siguiente caso: un estado que Twilio
    invente mañana no se presume bueno — se escala al canal siguiente."""
    with pytest.raises(NotifyError, match="desconocido"):
        _provider(_Twilio(_created("teleported"))).send(TARGET, MESSAGE)


def test_un_2xx_sin_sid_no_cuenta_como_envio() -> None:
    respuesta = httpx.Response(201, json={"status": "queued"})
    with pytest.raises(NotifyError, match="sid"):
        _provider(_Twilio(respuesta)).send(TARGET, MESSAGE)


# --- la petición que sale -----------------------------------------------------


def test_la_peticion_lleva_validity_period_y_no_el_default_de_diez_horas() -> None:
    """Sin esto, un SMS de sismo puede aterrizar 10 HORAS después (cola por
    defecto de Twilio). Un aviso de terremoto de anteayer es ruido puro."""
    twilio = _Twilio(_created())
    _provider(twilio).send(TARGET, MESSAGE)
    form = twilio.form()
    assert form["ValidityPeriod"] == "300"
    assert int(form["ValidityPeriod"]) < TWILIO_LIMITS.queue_ttl_default_s
    assert form["To"] == "%2B525522222222"
    assert form["From"] == "%2B525599999999"


def test_el_messaging_service_sustituye_al_from_cuando_se_configura() -> None:
    twilio = _Twilio(_created())
    _provider(twilio, notify_sms_from="", notify_sms_messaging_service_sid="MG9").send(
        TARGET, MESSAGE
    )
    form = twilio.form()
    assert form["MessagingServiceSid"] == "MG9"
    assert "From" not in form


def test_el_status_callback_solo_viaja_si_hay_endpoint() -> None:
    """Hoy no hay endpoint (ficha aparte): el parámetro NO se manda vacío, que
    haría que Twilio publicara contra una URL inexistente."""
    twilio = _Twilio(_created())
    _provider(twilio).send(TARGET, MESSAGE)
    assert "StatusCallback" not in twilio.form()

    otro = _Twilio(_created())
    _provider(otro, notify_sms_status_callback_url="https://api.takab.mx/hooks/sms").send(
        TARGET, MESSAGE
    )
    assert "StatusCallback" in otro.form()


def test_la_peticion_va_autenticada_con_basic_auth() -> None:
    twilio = _Twilio(_created())
    _provider(twilio).send(TARGET, MESSAGE)
    assert twilio.requests[0].headers["authorization"].startswith("Basic ")
    assert _SID in str(twilio.requests[0].url)


def test_validity_period_fuera_del_rango_de_twilio_se_ajusta_y_grita(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="takab_api.notify")
    assert resolve_validity_period_s(0) == TWILIO_MIN_VALIDITY_S
    assert resolve_validity_period_s(999_999) == TWILIO_MAX_VALIDITY_S
    assert len([r for r in caplog.records if "ValidityPeriod" in r.getMessage()]) == 2
    assert resolve_validity_period_s(300) == 300  # no-vacuidad: lo válido no grita


# --- coste acotado por construcción: este canal NO hace fan-out ---------------


def test_el_canal_sms_se_niega_a_abanicar() -> None:
    """El tope de gasto de este canal no es una cifra: es que sea IMPOSIBLE
    mandar cientos de SMS. Un destino = un mensaje por incidente."""
    twilio = _Twilio(_created())
    provider = _provider(twilio)
    for destino in ({"to": ["+5255111", "+5255222"]}, {"to": "+5255111,+5255222"}, {"to": ""}, {}):
        with pytest.raises(NotifyError):
            provider.send(destino, MESSAGE)  # type: ignore[arg-type]
    assert twilio.calls == 0  # ni una sola petición: se para antes de gastar


# --- reintentos: publicado dos veces es un SMS duplicado en el peor momento ---


def test_el_provider_no_reintenta_por_dentro() -> None:
    """Twilio ya reintenta contra la operadora y el orquestador ya reintenta con
    backoff. Una tercera capa invisible multiplicaría los duplicados."""
    twilio = _Twilio(httpx.Response(500, json={"message": "boom"}))
    with pytest.raises(NotifyError):
        _provider(twilio).send(TARGET, MESSAGE)
    assert twilio.calls == 1


def test_un_fallo_AMBIGUO_no_se_reenvia_al_mismo_incidente() -> None:
    """Twilio no ofrece clave de idempotencia, así que la pone el dominio:
    (destino, incidente). Un 5xx pudo haber creado el mensaje ⇒ el segundo
    intento NO sale, escala al canal siguiente. Peor causa por defecto."""
    twilio = _Twilio(httpx.Response(500, json={}))
    provider = _provider(twilio)
    with pytest.raises(NotifyError):
        provider.send(TARGET, MESSAGE)
    with pytest.raises(NotifyError, match="duplicado"):
        provider.send(TARGET, MESSAGE)
    assert twilio.calls == 1


def test_un_timeout_tambien_es_ambiguo() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    provider = _provider(handler)
    with pytest.raises(NotifyError):
        provider.send(TARGET, MESSAGE)
    with pytest.raises(NotifyError, match="duplicado"):
        provider.send(TARGET, MESSAGE)


def test_un_RECHAZO_explicito_si_permite_reintentar() -> None:
    """No-vacuidad de la guarda: un 4xx demuestra que el mensaje NO se creó, así
    que bloquear el reintento sería callar sin motivo. Sale otra vez."""
    twilio = _Twilio(httpx.Response(400, json={"code": 21211, "message": "To inválido"}))
    provider = _provider(twilio)
    for _ in range(2):
        with pytest.raises(NotifyError):
            provider.send(TARGET, MESSAGE)
    assert twilio.calls == 2


def test_un_estado_failed_no_bloquea_el_reintento() -> None:
    """Un ``failed`` explícito dice que ese mensaje no llegará a ningún teléfono:
    no hay duplicado posible, luego no hay nada que bloquear."""
    twilio = _Twilio(_created("failed"))
    provider = _provider(twilio)
    for _ in range(2):
        with pytest.raises(NotifyError):
            provider.send(TARGET, MESSAGE)
    assert twilio.calls == 2


def test_un_envio_aceptado_bloquea_el_reenvio_del_mismo_incidente() -> None:
    twilio = _Twilio(_created())
    provider = _provider(twilio)
    provider.send(TARGET, MESSAGE)
    with pytest.raises(NotifyError, match="duplicado"):
        provider.send(TARGET, MESSAGE)
    assert twilio.calls == 1


def test_otro_incidente_al_mismo_numero_si_sale() -> None:
    """No-vacuidad: la guarda es por (destino, incidente), no un mute global."""
    twilio = _Twilio(_created())
    provider = _provider(twilio)
    provider.send(TARGET, MESSAGE)
    provider.send(TARGET, {**MESSAGE, "incident_id": "22222222-0000-0000-0000-000000000002"})
    assert twilio.calls == 2


def test_la_guarda_caduca_con_la_ventana_de_validez() -> None:
    """El TTL se DERIVA del ValidityPeriod: pasado ese instante Twilio ya
    descartó el mensaje encolado, así que un reenvío no puede duplicar nada
    vivo. Y evita que el worker residente acumule claves para siempre."""
    reloj = _Reloj()
    twilio = _Twilio(_created())
    provider = _provider(twilio, clock=reloj)
    provider.send(TARGET, MESSAGE)
    reloj.t += 299
    with pytest.raises(NotifyError, match="duplicado"):
        provider.send(TARGET, MESSAGE)
    reloj.t += 2
    provider.send(TARGET, MESSAGE)
    assert twilio.calls == 2
    assert provider.pending_keys == 1  # la vieja se purgó, no se acumula


# --- regla de oro 6 · el token no se escapa ------------------------------------


def test_el_token_no_aparece_en_errores_ni_en_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="takab_api.notify")
    twilio = _Twilio(httpx.Response(401, json={"message": f"auth failed for {_TOKEN}"}))
    with pytest.raises(NotifyError) as err:
        _provider(twilio).send(TARGET, MESSAGE)
    assert _TOKEN not in str(err.value)
    assert all(_TOKEN not in r.getMessage() for r in caplog.records)


def test_el_constructor_no_toca_la_red() -> None:
    """Un constructor no puede hacer E/S falible: construir el provider con el
    transporte reventado no debe impedir arrancar el worker."""

    def handler(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("el constructor no debe hacer peticiones")

    provider = _provider(handler)
    assert provider.last_receipt is None


def test_el_registro_de_providers_usa_twilio_cuando_hay_credenciales() -> None:
    """El enchufe real: ``build_providers`` (lo que arranca el worker)."""
    from takab_api.notify.providers import build_providers

    assert isinstance(build_providers(_settings())["sms"], TwilioSmsProvider)
    assert is_simulated(build_providers(Settings())["sms"]) is True


def test_el_arranque_declara_coste_tasa_y_tope(caplog: pytest.LogCaptureFixture) -> None:
    """Criterio 2 literal: DECLARADOS, no descubiertos en la factura. El único
    momento en que un humano mira es el arranque, así que se dice ahí."""
    caplog.set_level(logging.INFO, logger="takab_api.notify")
    build_sms_provider(_settings())
    linea = next(r.getMessage() for r in caplog.records if "0.1819" in r.getMessage())
    assert "MPS" in linea
    assert "274" in linea  # el tope mensual traducido a mensajes
    assert "ValidityPeriod" in linea
