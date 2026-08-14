"""T-2.77.b · El vocabulario del desenlace TARDÍO, sin HTTP y sin base.

Aquí vive lo que se puede probar en microsegundos y sin nada delante: la
verificación de firma de los dos proveedores, el parseo de sus cuerpos y el
ORDEN de los estados. El endpoint público —que es donde esto se convierte en
superficie de ataque— tiene su propio fichero contra Postgres real
(``tests/api/test_notify_webhooks.py``).

La firma es la ÚNICA autenticación de esta superficie: no hay Cognito detrás
porque quien llama es Twilio o Meta. Por eso estas pruebas no son cosmética de
cobertura: son el candado.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import inspect
from datetime import UTC, datetime

from takab_api.notify import callbacks as cb

_TOKEN = "3l-t0k3n-d3-tw1l10"
_APP_SECRET = "3l-s3cr3t0-d3-m3ta"
_URL = "https://takab.example.mx/api/notify/webhooks/twilio"


# =============================================================================
# FIRMA DE TWILIO
# =============================================================================


def _twilio_sig(url: str, params: dict[str, str], token: str = _TOKEN) -> str:
    """La receta de Twilio, reimplementada AQUÍ a mano.

    A propósito no se llama a la función del código: un test que firma con la
    misma función que verifica solo demuestra que el módulo es consistente
    consigo mismo, no que hable el idioma de Twilio.
    """
    data = url + "".join(k + params[k] for k in sorted(params))
    mac = hmac.new(token.encode(), data.encode(), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


def test_la_firma_de_twilio_se_calcula_sobre_url_mas_parametros_ordenados() -> None:
    params = {"MessageSid": "SM123", "MessageStatus": "delivered", "AccountSid": "AC1"}
    assert cb.verify_twilio_signature(
        auth_token=_TOKEN, url=_URL, params=params, signature=_twilio_sig(_URL, params)
    )


def test_un_parametro_cambiado_invalida_la_firma_de_twilio() -> None:
    """El caso que importa: alguien intercepta un callback real y le cambia el
    estado a ``delivered``. La firma es sobre los PARÁMETROS, no sobre el SID."""
    params = {"MessageSid": "SM123", "MessageStatus": "failed"}
    firma = _twilio_sig(_URL, params)
    mentira = {**params, "MessageStatus": "delivered"}
    assert not cb.verify_twilio_signature(
        auth_token=_TOKEN, url=_URL, params=mentira, signature=firma
    )


def test_la_firma_de_twilio_esta_atada_a_la_URL() -> None:
    """La URL entra en el material firmado: una firma capturada en otra ruta no
    vale aquí. Por eso la URL sale de la CONFIGURACIÓN y no de las cabeceras."""
    params = {"MessageSid": "SM123", "MessageStatus": "delivered"}
    firma = _twilio_sig("https://otro.example.mx/hook", params)
    assert not cb.verify_twilio_signature(
        auth_token=_TOKEN, url=_URL, params=params, signature=firma
    )


def test_sin_token_configurado_ninguna_firma_de_twilio_es_valida() -> None:
    """Fail-closed: sin secreto no se valida NADA. Aceptar por no poder
    comprobar sería exactamente 'cualquiera marca entregado lo que no salió'."""
    params = {"MessageSid": "SM123", "MessageStatus": "delivered"}
    assert not cb.verify_twilio_signature(
        auth_token="", url=_URL, params=params, signature=_twilio_sig(_URL, params, token="")
    )


def test_firma_de_twilio_vacia_o_basura_no_pasa() -> None:
    params = {"MessageSid": "SM1"}
    for firma in ("", "   ", "no-es-base64-!!", base64.b64encode(b"corto").decode()):
        assert not cb.verify_twilio_signature(
            auth_token=_TOKEN, url=_URL, params=params, signature=firma
        )


# =============================================================================
# FIRMA DE META
# =============================================================================


def _meta_sig(body: bytes, secret: str = _APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_la_firma_de_meta_es_hmac_sha256_del_cuerpo_CRUDO() -> None:
    body = b'{"object":"whatsapp_business_account","entry":[]}'
    assert cb.verify_meta_signature(app_secret=_APP_SECRET, body=body, header=_meta_sig(body))


def test_un_byte_distinto_en_el_cuerpo_invalida_la_firma_de_meta() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    assert not cb.verify_meta_signature(
        app_secret=_APP_SECRET, body=body + b" ", header=_meta_sig(body)
    )


def test_meta_sin_prefijo_sha256_no_pasa() -> None:
    body = b"{}"
    crudo = hmac.new(_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert not cb.verify_meta_signature(app_secret=_APP_SECRET, body=body, header=crudo)


def test_sin_app_secret_configurado_ninguna_firma_de_meta_es_valida() -> None:
    body = b"{}"
    assert not cb.verify_meta_signature(app_secret="", body=body, header=_meta_sig(body, ""))


# =============================================================================
# TIEMPO CONSTANTE · el detalle que no se ve en una prueba de comportamiento
# =============================================================================


def test_las_dos_comparaciones_de_firma_usan_compare_digest() -> None:
    """Un ``==`` sobre un HMAC filtra el prefijo correcto por temporización.

    No se puede medir con un reloj en una suite (el ruido se come la señal), así
    que se lee la FUENTE: es el único sitio donde una prueba estructural dice más
    que una de comportamiento. Y de paso queda escrito que ``==`` está prohibido
    aquí, no solo desaconsejado.
    """
    fuente = inspect.getsource(cb)
    assert "compare_digest" in fuente
    for funcion in (cb.verify_twilio_signature, cb.verify_meta_signature):
        cuerpo = inspect.getsource(funcion)
        assert "compare_digest" in cuerpo, f"{funcion.__name__} no compara en tiempo constante"
        assert "==" not in cuerpo.replace("!=", ""), (
            f"{funcion.__name__} compara con == : filtra el prefijo por temporización"
        )


# =============================================================================
# PARSEO · TWILIO
# =============================================================================


def test_del_formulario_de_twilio_sale_un_evento_con_su_sid_y_su_estado() -> None:
    eventos = cb.parse_twilio_form({"MessageSid": "SM9", "MessageStatus": "delivered"})
    assert [(e.channel, e.message_id, e.status) for e in eventos] == [("sms", "SM9", "delivered")]


def test_twilio_acepta_los_nombres_antiguos_SmsSid_SmsStatus() -> None:
    """Twilio manda los dos juegos de campos según la antigüedad del callback."""
    eventos = cb.parse_twilio_form({"SmsSid": "SM9", "SmsStatus": "undelivered"})
    assert [(e.message_id, e.status) for e in eventos] == [("SM9", "undelivered")]


def test_un_formulario_sin_sid_no_produce_evento() -> None:
    assert cb.parse_twilio_form({"MessageStatus": "delivered"}) == []
    assert cb.parse_twilio_form({"MessageSid": "SM1"}) == []


def test_twilio_arrastra_el_codigo_de_error_al_detalle() -> None:
    (evento,) = cb.parse_twilio_form(
        {"MessageSid": "SM9", "MessageStatus": "undelivered", "ErrorCode": "30003"}
    )
    assert "30003" in evento.detail


# =============================================================================
# PARSEO · META
# =============================================================================


def _meta_payload(*statuses: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {"messaging_product": "whatsapp", "statuses": list(statuses)},
                    }
                ],
            }
        ],
    }


def test_del_cuerpo_de_meta_salen_todos_los_estados_del_lote() -> None:
    payload = _meta_payload(
        {"id": "wamid.AAA", "status": "sent", "timestamp": "1900000000"},
        {"id": "wamid.BBB", "status": "delivered", "timestamp": "1900000005"},
    )
    eventos = cb.parse_meta_payload(payload)
    assert [(e.channel, e.message_id, e.status) for e in eventos] == [
        ("whatsapp", "wamid.AAA", "sent"),
        ("whatsapp", "wamid.BBB", "delivered"),
    ]
    assert eventos[1].at == datetime.fromtimestamp(1900000005, tz=UTC)


def test_un_cuerpo_de_meta_que_no_trae_estados_no_produce_eventos() -> None:
    """Meta manda por el MISMO webhook los mensajes entrantes. No son desenlaces
    de nada nuestro y no pueden tocar un job."""
    entrante = _meta_payload()
    entrante["entry"][0]["changes"][0]["value"] = {"messages": [{"from": "5255", "id": "wamid.X"}]}
    assert cb.parse_meta_payload(entrante) == []


def test_un_cuerpo_de_meta_deforme_no_revienta() -> None:
    """Superficie pública: un cuerpo firmado pero absurdo no puede tumbar el
    proceso. Se ignora y ya."""
    for basura in (None, [], "texto", {"entry": "no-es-lista"}, {"entry": [{"changes": 7}]}):
        assert cb.parse_meta_payload(basura) == []


def test_meta_arrastra_el_error_al_detalle() -> None:
    payload = _meta_payload(
        {
            "id": "wamid.CCC",
            "status": "failed",
            "timestamp": "1900000000",
            "errors": [{"code": 131026, "title": "Message undeliverable"}],
        }
    )
    (evento,) = cb.parse_meta_payload(payload)
    assert "131026" in evento.detail


# =============================================================================
# EL ORDEN DE LOS ESTADOS · reenvíos y callbacks fuera de orden
# =============================================================================


def test_solo_delivered_y_read_cuentan_como_entrega() -> None:
    """Criterio literal de la ficha, y la regla la ponen los providers: este
    módulo la REUSA (``is_delivery_confirmed``), no la reinventa."""
    for status in ("delivered", "read"):
        assert cb.is_delivered("sms", status)
        assert cb.is_delivered("whatsapp", status)
    for status in ("queued", "sent", "accepted", "held_for_quality_assessment", "sending"):
        assert not cb.is_delivered("sms", status)
        assert not cb.is_delivered("whatsapp", status)


def test_la_regla_de_entrega_sale_de_los_providers_no_de_una_copia() -> None:
    from takab_api.notify import twilio as tw
    from takab_api.notify import whatsapp as wa

    assert cb.is_delivered("sms", "delivered") is tw.is_delivery_confirmed("delivered")
    assert cb.is_delivered("whatsapp", "read") is wa.is_delivery_confirmed("read")


def test_failed_y_undelivered_son_no_entrega_declarada() -> None:
    assert cb.is_undelivered("sms", "failed")
    assert cb.is_undelivered("sms", "undelivered")
    assert cb.is_undelivered("sms", "canceled")
    assert cb.is_undelivered("whatsapp", "failed")
    assert not cb.is_undelivered("sms", "delivered")


def test_delivered_pisa_a_sent_pero_sent_NO_pisa_a_delivered() -> None:
    """El caso de la ficha: un ``delivered`` seguido de un ``sent`` retrasado no
    puede hacer retroceder el estado."""
    assert "sent" in cb.outranked_by("delivered")
    assert "delivered" not in cb.outranked_by("sent")


def test_un_estado_JAMAS_se_pisa_a_si_mismo() -> None:
    """Es lo que hace inerte un REENVÍO: el proveedor reintenta el mismo
    callback y el segundo no cambia nada."""
    for status in cb.KNOWN_STATUSES:
        assert status not in cb.outranked_by(status)


def test_read_es_lo_mas_alto_y_pisa_a_delivered() -> None:
    assert "delivered" in cb.outranked_by("read")
    assert "read" not in cb.outranked_by("delivered")


def test_un_fallo_tardio_pisa_a_sent_pero_no_a_una_entrega_confirmada() -> None:
    """Un job ``sent`` que recibe ``failed`` tiene que acabar en rojo; pero una
    entrega ya CONFIRMADA es un hecho ocurrido y no la borra un fallo posterior."""
    assert "sent" in cb.outranked_by("failed")
    assert "delivered" not in cb.outranked_by("failed")
    assert "read" not in cb.outranked_by("undelivered")


def test_un_estado_desconocido_no_tiene_rango_y_no_pisa_a_nadie() -> None:
    """El default ante lo desconocido es no tocar nada: un estado que Twilio o
    Meta inventen mañana no puede degradar ni ascender un job."""
    assert cb.rank("estado_que_nadie_ha_visto") is None
    assert cb.outranked_by("estado_que_nadie_ha_visto") == ()
