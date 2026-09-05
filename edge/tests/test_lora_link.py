"""LoraLink (T-2.33): registry por heartbeat, repeat-until-ack y transiciones.

Transporte simulado en proceso (cero radio): la pérdida de paquetes es
DETERMINISTA (``drop_next``) y los heartbeats se inyectan cuando el guion lo
pide. Los tiempos de reintento se encogen para que la suite vuele.
"""

from __future__ import annotations

import time

import pytest
from simulators.lora import FakeSecondaryCabinet, SimulatedLoraTransport
from takab_edge.config import LoraConfig, SecondaryCabinet, load_settings
from takab_edge.lora import LoraLink
from takab_edge.lora import frame as fr

SITE_KEY = b"clave-lora-de-sitio-0123456789ab"


def _settings(**lora_over):
    defaults = {
        "enabled": True,
        "heartbeat_s": 60.0,
        "heartbeat_timeout_factor": 3.0,
        "alarm_retry_max": 5,
        "alarm_retry_s": 0.05,
        "secondaries": [
            SecondaryCabinet(id=258, name="AZOTEA-NORTE", zone="Torre B"),
            SecondaryCabinet(id=259, name="PATIO-SUR", zone="Patio"),
        ],
    }
    return load_settings().model_copy(update={"lora": LoraConfig(**{**defaults, **lora_over})})


def _wait(condition, timeout_s: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


@pytest.fixture
def link():
    transport = SimulatedLoraTransport()
    cab1 = transport.attach(FakeSecondaryCabinet(SITE_KEY, 258, battery_mv=3870))
    cab2 = transport.attach(FakeSecondaryCabinet(SITE_KEY, 259, battery_mv=4020))
    lora = LoraLink(_settings(), transport, SITE_KEY)
    lora.start()
    try:
        yield lora, transport, cab1, cab2
    finally:
        lora.stop()


def _sec(lora: LoraLink, cab_id: int) -> dict:
    return next(s for s in lora.snapshot()["secondaries"] if s["id"] == cab_id)


def test_heartbeat_updates_registry(link):
    lora, transport, cab1, _cab2 = link
    assert _sec(lora, 258)["link"] == "never"
    transport.deliver(cab1.heartbeat())
    row = _sec(lora, 258)
    assert row["link"] == "online"
    assert row["battery_mv"] == 3870
    assert row["rssi_dbm"] == pytest.approx(-92.0)
    assert row["snr_db"] == pytest.approx(7.5)
    assert row["age_s"] is not None and row["age_s"] < 5.0


def test_propagate_activate_reaches_all_and_acks(link):
    lora, _transport, cab1, cab2 = link
    lora.propagate("activate", siren=True, strobe=True)
    assert _wait(lambda: cab1.alarm_active and cab2.alarm_active)
    assert _wait(lambda: _sec(lora, 258)["acked"] is True and _sec(lora, 259)["acked"] is True)
    assert cab1.flags_seen & fr.FLAG_SIREN and cab1.flags_seen & fr.FLAG_STROBE
    assert _sec(lora, 258)["alarm_active"] is True


def test_lost_frames_retry_until_ack(link):
    lora, transport, cab1, _cab2 = link
    transport.drop_next(2)  # el aire se come los 2 primeros downlinks
    lora.propagate("activate", siren=True)
    assert _wait(lambda: cab1.alarm_active)
    assert _wait(lambda: _sec(lora, 258)["acked"] is True)
    # hubo reintentos: se emitieron MÁS tramas de las que llegaron
    assert len(transport.sent) > 2


def test_retry_cap_leaves_sin_ack_visible():
    transport = SimulatedLoraTransport()
    cab = transport.attach(FakeSecondaryCabinet(SITE_KEY, 258))
    lora = LoraLink(
        _settings(alarm_retry_max=3, secondaries=[SecondaryCabinet(id=258)]), transport, SITE_KEY
    )
    lora.start()
    try:
        transport.drop_next(999)  # enlace muerto
        lora.propagate("activate", siren=True)
        assert _wait(lambda: len(transport.sent) >= 3)
        time.sleep(0.2)  # margen: no debe emitir más allá del tope
        assert len(transport.sent) == 3
        assert _sec(lora, 258)["acked"] is False
        assert cab.alarm_active is False
    finally:
        lora.stop()


def test_propagate_clear_releases_secondaries(link):
    lora, _transport, cab1, _cab2 = link
    lora.propagate("activate", siren=True, strobe=True)
    assert _wait(lambda: cab1.alarm_active)
    lora.propagate("clear")
    assert _wait(lambda: not cab1.alarm_active)
    assert _wait(lambda: _sec(lora, 258)["alarm_active"] is False)


def test_heartbeat_timeout_marks_offline_and_recovers():
    transport = SimulatedLoraTransport()
    cab = transport.attach(FakeSecondaryCabinet(SITE_KEY, 258))
    lora = LoraLink(
        _settings(
            heartbeat_s=0.05,
            heartbeat_timeout_factor=1.0,
            secondaries=[SecondaryCabinet(id=258, name="AZOTEA")],
        ),
        transport,
        SITE_KEY,
    )
    lora.start()
    try:
        transport.deliver(cab.heartbeat())
        assert _sec(lora, 258)["link"] == "online"
        assert _wait(lambda: _sec(lora, 258)["link"] == "offline")  # ENLACE PERDIDO
        transport.deliver(cab.heartbeat())
        assert _sec(lora, 258)["link"] == "online"  # recupera con el siguiente latido
    finally:
        lora.stop()


def test_forged_and_replayed_uplinks_are_ignored(link):
    lora, transport, cab1, _cab2 = link
    hb = cab1.heartbeat()
    transport.deliver(hb)
    first_age = _sec(lora, 258)["age_s"]
    tampered = bytearray(hb)
    tampered[13] = 0xFF  # inflar batería sin re-firmar
    transport.deliver(bytes(tampered))
    transport.deliver(hb)  # replay exacto (misma sesión, mismo seq)
    assert _sec(lora, 258)["battery_mv"] == 3870
    assert first_age is not None


def test_propagate_never_blocks(link):
    lora, _transport, _cab1, _cab2 = link
    started = time.monotonic()
    lora.propagate("activate", siren=True)
    assert time.monotonic() - started < 0.05  # encola y regresa


def test_lifecycle_is_idempotent():
    transport = SimulatedLoraTransport()
    lora = LoraLink(_settings(), transport, SITE_KEY)
    lora.start()
    lora.start()
    assert transport.opened is True
    lora.stop()
    lora.stop()
    assert transport.opened is False


# ── [T-5.25] El silencio alcanza a TODO el inmueble ──────────────────────────
#
# El silencio del operador estaba bien resuelto en el gabinete que lo recibe:
# corta la sirena, corta el voceo, deja el estrobo, no toca gas ni puertas.
# Y no salía de ahí. El principal propagaba la ACTIVACIÓN por radio y **solo el
# cierre de alerta** propagaba la orden inversa; el silencio, no. El operador
# callaba el suyo y **el edificio seguía sonando**.
#
# Es el mismo riesgo de credibilidad que motivó la ruta de hardware: una sirena
# que nadie puede callar durante una falsa alarma quema la obediencia a la
# siguiente alerta — y la siguiente puede ser la de verdad.
#
# Estos tests miden el ESTADO ELÉCTRICO de los dos nodos (`siren_on`/`strobe_on`
# del ESP32 simulado), no la orden que salió por la antena. La distinción no es
# escrupulosidad: una orden enviada que el nodo rechaza deja el relé cerrado, y
# es exactamente así como «se silenció el edificio» puede ser mentira.


def _acked(cab, lora, cab_id) -> bool:
    return _sec(lora, cab_id)["acked"] is True


def test_el_silencio_llega_a_LOS_DOS_nodos(link):
    """El fallo de la ficha, medido en los relés de ambos."""
    lora, _t, cab1, cab2 = link
    lora.propagate("activate", siren=True, strobe=True)
    assert _wait(lambda: cab1.siren_on and cab2.siren_on), "la alarma no sonó en los dos"

    lora.propagate("silence")

    assert _wait(lambda: not cab1.siren_on and not cab2.siren_on), (
        "el operador silenció el principal y los secundarios SIGUEN SONANDO: es "
        f"el defecto que esta ficha cierra (sirenas: {cab1.siren_on}, {cab2.siren_on})"
    )


def test_el_silencio_calla_lo_audible_y_NADA_MAS(link):
    """«Solo el silencio»: el estrobo sigue y la alerta sigue viva en cada nodo.

    Un silencio que apagara el estrobo convertiría callar la sirena en **borrar
    la alerta** para quien está en el edificio, que es peor que no poder callarla.
    Y `alarm_active` tiene que sobrevivir: es lo que sostiene la protección no
    audible del nodo y lo que hace que un CLEAR posterior signifique algo.
    """
    lora, _t, cab1, cab2 = link
    lora.propagate("activate", siren=True, strobe=True)
    assert _wait(lambda: cab1.siren_on and cab2.siren_on)

    lora.propagate("silence")
    assert _wait(lambda: not cab1.siren_on and not cab2.siren_on)

    for cab in (cab1, cab2):
        assert cab.strobe_on, "el silencio apagó el estrobo: eso ya no es silenciar, es borrar"
        assert cab.alarm_active, "el silencio bajó la alerta del nodo: solo el CLEAR hace eso"


def test_una_alarma_NUEVA_vuelve_a_sonar_en_todos(link):
    """Como en el principal: silenciar no inhibe la siguiente alerta.

    Es la mitad que hace aceptable el silencio. Si callar dejara sordo al edificio
    para lo que venga después, el botón sería un peligro y nadie debería tocarlo.
    """
    lora, _t, cab1, cab2 = link
    lora.propagate("activate", siren=True, strobe=True)
    assert _wait(lambda: cab1.siren_on and cab2.siren_on)
    lora.propagate("silence")
    assert _wait(lambda: not cab1.siren_on and not cab2.siren_on)

    lora.propagate("activate", siren=True, strobe=True)

    assert _wait(lambda: cab1.siren_on and cab2.siren_on), (
        "tras un silencio, una alarma NUEVA ya no suena en los secundarios: el "
        "silencio dejó sordo al edificio"
    )


def test_el_silencio_no_se_lo_traga_la_SUMA_de_flags(link):
    """La trampa que obligó a un tipo de mensaje propio, medida.

    Dos `ALARM_ACT` seguidos SUMAN flags a propósito (los comandos de red llegan
    por canal separado). Si el silencio viajara como un `ALARM_ACT` sin el bit de
    sirena, el `merged |= pending["flags"]` del emisor le volvería a poner la
    sirena que acababa de quitar — y con una orden aún sin ACK, ni siquiera haría
    falta que el nodo colaborara.
    """
    lora, _t, cab1, cab2 = link
    lora.propagate("activate", siren=True, strobe=True)
    lora.propagate("silence")

    # La orden pendiente es el SILENCIO: lo SUSTITUYÓ, no se sumó a él.
    assert _wait(lambda: _sec(lora, 258)["pending"] == "silence"), (
        "la activación se comió al silencio en la cola del emisor"
    )
    # Se espera a que el silencio LLEGUE: `not siren_on` es cierto desde el
    # principio y esperar sobre eso no espera a nada (pasó al escribirlo).
    llego = lambda c: bool(c.received) and c.received[-1].msg_type == fr.SILENCE  # noqa: E731
    assert _wait(lambda: llego(cab1) and llego(cab2), timeout_s=2.0), "el silencio no llegó"
    for cab in (cab1, cab2):
        assert not cab.siren_on, "el nodo sigue sonando tras recibir el silencio"
        ultima = cab.received[-1]
        assert ultima.msg_type == fr.SILENCE, f"la última orden no fue el silencio: {ultima}"
        assert not ultima.flags & fr.FLAG_SIREN, (
            "el silencio llegó al nodo CON el bit de sirena puesto: eso enciende en vez de callar"
        )


def test_un_nodo_que_no_CONFIRMA_se_declara_en_el_panel(link):
    """Silenciar cuatro de cinco no es silenciar, y el panel tiene que decirlo.

    `SIN ACK` a secas no bastaba: no distingue un test perdido —da igual— de un
    SILENCIO que no llegó, que significa que ese nodo **sigue sonando** mientras
    el operador cree que calló el edificio. Por eso viaja también QUÉ orden es la
    que no se confirmó.
    """
    lora, transport, cab1, cab2 = link
    lora.propagate("activate", siren=True, strobe=True)
    assert _wait(lambda: cab1.siren_on and cab2.siren_on)

    # El 259 se queda sordo: ni una sola de las repeticiones le llega.
    transport.deaf.add(259)
    lora.propagate("silence")

    assert _wait(lambda: not cab1.siren_on), "el nodo alcanzable no se silenció"
    assert _wait(lambda: _sec(lora, 259)["acked"] is False, timeout_s=3.0), (
        "el nodo que no confirmó el silencio no se declara: el panel dejaría creer "
        "que el edificio entero está callado"
    )
    fila = _sec(lora, 259)
    assert fila["pending"] == "silence", (
        "el panel sabe que algo no se confirmó pero no QUÉ: con `SIN ACK` a secas, "
        f"un silencio perdido se lee igual que un test perdido. Trae: {fila['pending']!r}"
    )
    assert cab2.siren_on, "el guion no reproduce el caso: el nodo sordo debería seguir sonando"
    assert _sec(lora, 258)["acked"] is True, "el nodo alcanzable debería haber confirmado"
