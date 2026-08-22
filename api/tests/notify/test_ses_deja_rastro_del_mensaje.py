"""[T-2.160] El `MessageId` de SES tiene que quedar en la base.

El mecanismo ya existía: `notification_jobs.provider_message_id` y
`provider_message_id(provider)`, genérico por diseño —lee `.last_receipt.message_id`
sin saber de canales—. SES no lo alimentaba, y su comentario decía por qué:

    «Un provider sin recibo —SES, el webhook firmado— devuelve cadena vacía [...]
     No hay nada que casar donde no hay callback.»

Era cierto. **Deja de serlo** en cuanto el configuration set publica sus eventos a
un destino consultable: entonces el `MessageId` es exactamente la llave que une lo
que dice la base con lo que dice SES.

Sin esa llave, la pregunta «¿le llegó la solicitud al inspector?» solo se puede
responder con «SES no se quejó» — que es lo que costó media sesión de diagnóstico
el 2026-08-22.
"""

from __future__ import annotations

import pytest
from moto import mock_aws

from takab_api.notify.providers import SesEmailProvider, provider_message_id

_REGION = "us-east-2"
_MENSAJE = {"headline": "TAKAB Ailert · Incidente alta · Torre A", "severity": "alta"}


def _credenciales(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)


def test_un_envio_deja_su_message_id_donde_el_orquestador_lo_busca(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La costura ya existía y era genérica: solo faltaba que SES la usara."""
    _credenciales(monkeypatch)
    with mock_aws():
        import boto3

        boto3.client("ses", region_name=_REGION).verify_email_identity(
            EmailAddress="alertas@takab.mx"
        )
        provider = SesEmailProvider(sender="alertas@takab.mx", region=_REGION)
        provider.send({"to": ["ops@example.mx"]}, _MENSAJE)

        assert provider_message_id(provider), (
            "el envío no dejó `MessageId`: sin él, la evidencia de la base y la de "
            "SES no se pueden cruzar y «¿llegó este correo?» no tiene respuesta"
        )


def test_sin_haber_enviado_nada_no_se_inventa_un_identificador() -> None:
    """Regla de oro 7: lo que no ocurrió no deja rastro."""
    provider = SesEmailProvider(sender="alertas@takab.mx", region=_REGION)

    assert provider_message_id(provider) == ""


def test_un_envio_fallido_no_deja_el_id_del_anterior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El recibo viejo sobreviviendo a un envío fallido ataría el job EQUIVOCADO.

    Es la misma familia que el `alert_latched` de `T-2.28`: un estado que no se
    limpia y contamina la lectura siguiente. Aquí sería peor — la base afirmaría
    que un correo que nunca salió tiene el identificador de otro que sí.
    """
    _credenciales(monkeypatch)
    with mock_aws():
        import boto3

        from takab_api.notify.providers import NotifyError

        boto3.client("ses", region_name=_REGION).verify_email_identity(
            EmailAddress="alertas@takab.mx"
        )
        provider = SesEmailProvider(sender="alertas@takab.mx", region=_REGION)
        provider.send({"to": ["ops@example.mx"]}, _MENSAJE)
        primero = provider_message_id(provider)
        assert primero

        with pytest.raises(NotifyError):
            provider.send({"to": []}, _MENSAJE)  # sin destinatarios

        assert provider_message_id(provider) != primero, (
            "el recibo del envío anterior sobrevivió a uno fallido: la base ataría "
            "el job al identificador de otro mensaje"
        )
