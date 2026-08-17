"""[T-2.147.a] La clase de push del PÁNICO: alta prioridad y NO sísmica.

Las dos clases que había no sirven, y por razones opuestas:

  · ``CRISIS`` va por el canal ``seismic_alert``, con el tono sísmico y el sonido
    crítico. Vestir de sismo una activación manual es **exactamente el defecto de
    T-2.104**, donde la app tituló «ALERTA SÍSMICA SASMEX» algo que SASMEX no
    había dicho. El tono del SASMEX es el sonido que la población ya asocia a
    evacuar: usarlo para que dos personas llamen a la brigada es mentir con un
    sonido.
  · ``OPS`` va en prioridad **normal**. A las 3 a.m. no despierta a nadie, que es
    justo lo único que este push tiene que conseguir (`D-05`).

Un pánico es **alta prioridad y no es un sismo**. Las dos cosas a la vez, y
ninguna clase existente lo decía.
"""

from __future__ import annotations

import json

import pytest

from takab_api.notify.push import (
    PUSH_CLASS_CRISIS,
    PUSH_CLASS_OPS,
    PUSH_CLASS_PANIC,
    build_push_payload,
)


def _payload(push_class: str) -> dict:
    return build_push_payload(
        push_class=push_class,
        site_id="7c500000-0000-0000-0000-00000000015d",
        incident_id="7c500000-0000-0000-0000-0000000000a1",
        phase="building_alarm",
    )


def _apns(push_class: str) -> dict:
    return json.loads(_payload(push_class)["APNS"])


def _android(push_class: str) -> dict:
    return json.loads(_payload(push_class)["GCM"])["android"]


def test_el_panico_despierta_como_una_crisis() -> None:
    """Alta prioridad en las dos plataformas: es lo único que tiene que lograr.

    Si esto se degradara a `normal`, el push llegaría cuando el teléfono
    decidiera —que de madrugada puede ser por la mañana— y la brigada se
    enteraría por el sondeo de la app, que es justo lo que `D-05` compra evitar.
    """
    assert _android(PUSH_CLASS_PANIC)["priority"] == "high", (
        "el push de pánico salió en prioridad normal: no despierta a nadie, y "
        "entonces no añade nada sobre el sondeo de 30 s de la app"
    )
    assert _apns(PUSH_CLASS_PANIC)["aps"]["interruption-level"] == "time-sensitive", (
        "sin `time-sensitive` el push no atraviesa el modo concentración de iOS"
    )


def test_el_panico_NO_se_disfraza_de_sismo() -> None:
    """LA PROPIEDAD QUE JUSTIFICA LA CLASE. Es la lección de T-2.104.

    El canal de Android y el sonido de iOS son lo que una persona reconoce ANTES
    de leer nada. Si el pánico los comparte con el sismo, el teléfono afirma
    «sismo» por su cuenta y ningún texto de abajo lo desmiente — que fue
    literalmente el defecto: titular sísmico sobre una fuente que no lo era.
    """
    canal_panico = _android(PUSH_CLASS_PANIC)["notification"]["channel_id"]
    canal_sismo = _android(PUSH_CLASS_CRISIS)["notification"]["channel_id"]
    assert canal_panico != canal_sismo, (
        f"el pánico usa el canal de Android del sismo ({canal_panico!r}): el "
        "teléfono lo anunciaría con el tono que la población asocia a evacuar"
    )

    sonido_panico = _apns(PUSH_CLASS_PANIC)["aps"]["sound"]
    sonido_sismo = _apns(PUSH_CLASS_CRISIS)["aps"]["sound"]
    assert sonido_panico != sonido_sismo, (
        "el pánico suena igual que el sismo en iOS: mismo problema por el otro sistema"
    )
    assert not (isinstance(sonido_panico, dict) and sonido_panico.get("critical")), (
        "el pánico pide sonido CRÍTICO de Apple: ese entitlement se solicitó para "
        "alertamiento sísmico (GATE-STORE), y gastarlo en una activación manual "
        "es la clase de uso que hace que Apple lo revoque"
    )


def test_el_texto_visible_no_dice_sismo() -> None:
    """El lockscreen es lo único que se lee dormido, y es texto FIJO.

    No basta con cambiar canal y sonido: si el título sigue diciendo «ALERTA
    SÍSMICA», la mentira viaja igual. Se asserta el TEXTO, que es la lección de
    T-2.104: un componente presentacional puede llevar una mentira a fuego que
    ninguna prueba de la lógica alcanza.
    """
    texto = json.dumps(_apns(PUSH_CLASS_PANIC)["aps"]["alert"]).upper()
    assert "SÍSMIC" not in texto and "SISMIC" not in texto, (
        f"el texto del push de pánico nombra un sismo que no ocurrió: {texto}"
    )
    assert "SISMO" not in texto, f"idem: {texto}"


def test_las_tres_clases_siguen_siendo_distintas() -> None:
    """No-vacuidad: si dos clases colapsaran, los asserts de arriba no medirían."""
    payloads = {c: _payload(c) for c in (PUSH_CLASS_CRISIS, PUSH_CLASS_OPS, PUSH_CLASS_PANIC)}
    serializados = {json.dumps(p, sort_keys=True) for p in payloads.values()}
    assert len(serializados) == 3, "dos clases de push producen el MISMO mensaje"


def test_una_clase_desconocida_sigue_tronando() -> None:
    """El default-deny del constructor: nada de caer a CRISIS por descuido.

    Caer a una clase por defecto sería el modo de fallo peor: un push mal
    etiquetado que suena a sismo.
    """
    with pytest.raises(ValueError, match="clase de push desconocida"):
        _payload("NO_EXISTE")
