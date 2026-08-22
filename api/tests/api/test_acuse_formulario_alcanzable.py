"""[T-2.161] El formulario de acuse tiene que poder ENVIARSE donde se sirve.

Su `action` era `/ops/alerts/ack`, una ruta ABSOLUTA. La consola publica la API
bajo `/api`, así que la página se pinta en `https://host/api/ops/alerts/ack` y al
enviar el navegador va a `https://host/ops/alerts/ack` — que no es la API: es el
SPA, y devuelve 405.

Medido el 2026-08-22 durante el ensayo cronometrado de `T-2.78`: el acuse **nunca
llegó al servidor**. El aviso pasó a `sin_acuse` sin que nadie pudiera evitarlo.

Un `action` vacío hace que el formulario se envíe **a la URL que lo sirvió**, sea
cual sea el prefijo. Es la única forma que no depende de saber dónde está montada
la API — y el endpoint no puede saberlo: lo decide un proxy que vive en otro
repositorio mental.
"""

from __future__ import annotations

from takab_api.routers import ops_alerts


def test_el_formulario_no_fija_una_ruta_absoluta() -> None:
    """Una ruta absoluta rompe en cuanto la API vive tras un prefijo."""
    assert 'action="/ops/alerts/ack"' not in ops_alerts._FORMULARIO, (
        "el `action` absoluto envía el POST fuera del prefijo bajo el que se sirve "
        "la API: la página se pinta pero el acuse no llega al servidor"
    )


def test_el_formulario_se_envia_a_su_propia_url() -> None:
    """`action=""` posta a la URL actual, con prefijo o sin él."""
    assert 'action=""' in ops_alerts._FORMULARIO


def test_sigue_siendo_un_post_con_el_campo_que_el_endpoint_lee() -> None:
    """La guarda de arriba no puede pasar rompiendo el formulario."""
    assert 'method="post"' in ops_alerts._FORMULARIO
    assert 'name="token"' in ops_alerts._FORMULARIO
    assert 'type="password"' in ops_alerts._FORMULARIO, (
        "el campo debe seguir siendo `password`: no se pinta en pantalla ni entra "
        "en el historial del navegador"
    )
