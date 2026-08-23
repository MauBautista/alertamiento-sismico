"""[T-2.158] Un correo no puede prometer un enlace que el destinatario no abre.

`TAKAB_API_NOTIFY_WEB_BASE_URL` apunta a la consola del SOC, y en dev esa consola
admite UNA sola IP. Cada solicitud de dictamen decía «Atender en la consola» con
un enlace que solo podía abrir el operador de esa dirección.

El código no estaba mal —compone el enlace con el `console_url` que le den— y la
restricción por IP es deliberada. Lo que estaba mal es que **nada lo declaraba**:
el correo invitaba a pulsar. Es la regla de oro 7 fuera de la UI, presentar como
accionable lo que no lo es.

Quién puede alcanzar la consola lo sabe el DESPLIEGUE, no el código, así que se
declara: `TAKAB_API_NOTIFY_WEB_PUBLIC`.
"""

from __future__ import annotations

from takab_api.notify.providers import cuerpo_email
from takab_api.settings import Settings

_BASE = {
    "incident_id": "0f0a5f2e-7b1a-4c9e-9a44-2c0f1d8e3b77",
    "site_name": "Hospital General · Torre B",
    "site_code": "HGT-B",
    "severity": "alta",
    "trigger": "sasmex",
    "kind": "dictamen_request",
    "note": "Grietas visibles en muro de escalera norte.",
}


def test_el_ajuste_nace_en_FALSO() -> None:
    """El default seguro: si nadie lo declara, no se promete nada.

    Al revés —asumir alcanzable— el defecto vuelve en cada despliegue nuevo y no
    se nota hasta que alguien intenta pulsar, que es tarde.
    """
    assert Settings(notify_email_from="x@y.z").notify_web_public is False


#: La frase exacta, no la palabra «consola»: ésa ya sale en el pie del correo y
#: un test que la busque pasa por la razón equivocada. (Pasó en el primer intento
#: de escribir esto.)
_SIN_ENLACE = "Atienda este aviso desde la consola de TAKAB Ailert."


def test_sin_enlace_el_correo_DICE_que_hacer_en_vez_de_callar() -> None:
    """Quitar el enlace no puede dejar al inspector sin saber que debe actuar."""
    cuerpo = cuerpo_email(_BASE)

    assert "http" not in cuerpo
    assert _SIN_ENLACE in cuerpo, "se quitó el enlace y no se dijo qué hacer"


def test_con_enlace_se_incluye_y_es_el_que_se_dio() -> None:
    cuerpo = cuerpo_email(dict(_BASE, link="https://consola.example/triage?incident=0f0a"))

    assert "https://consola.example/triage?incident=0f0a" in cuerpo


def test_el_aviso_de_no_alcanzable_no_aparece_cuando_SI_hay_enlace() -> None:
    """No se acumulan las dos frases: una contradice a la otra."""
    cuerpo = cuerpo_email(dict(_BASE, link="https://consola.example/t"))

    assert _SIN_ENLACE not in cuerpo
    assert "https://consola.example/t" in cuerpo
