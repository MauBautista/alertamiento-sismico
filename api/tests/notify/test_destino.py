"""Qué se puede enseñar de un destinatario, y qué no (T-5.15).

**Allowlist por forma, no denylist**, por la misma razón que
`narrative/redact.py`: un canal nuevo mañana trae una forma de `target` que
nadie previó, y con una denylist saldría entero por omisión — con el número de
teléfono dentro. Aquí lo que no se reconoce **no sale y lo dice**.

La que más importa de todas: **la URL de un webhook ES la credencial**. Un
`https://hooks.example.com/T00/B00/xoxbSECRETO` no se puede enseñar en una
pantalla de consola porque quien lo lea puede publicar en ese canal. Sale el
host y nada más.
"""

from __future__ import annotations

import pytest

from takab_api.notify.destino import DESCONOCIDO, resumen_destino


def test_correo_deja_ver_el_buzon_sin_dictarlo():
    r = resumen_destino("email", {"to": ["ops@cliente.com", "seguridad@cliente.com"]})
    assert r.kind == "correo"
    assert r.count == 2
    # El dominio entero (identifica a la organización) + la inicial del buzón:
    # suficiente para saber si le llegó a `ops@` o a `seguridad@`, y no para
    # teclearlo.
    assert r.hint == "o***@cliente.com, s***@cliente.com"
    assert "ops@cliente.com" not in r.hint


def test_correo_de_uno_solo_en_cadena_tambien_vale():
    assert resumen_destino("email", {"to": "ops@cliente.com"}).count == 1


def test_telefono_ensena_solo_las_ultimas_cuatro():
    r = resumen_destino("sms", {"to": "+525512345678"})
    assert (r.kind, r.count, r.hint) == ("telefono", 1, "+••••••••5678")
    assert "5512345678" not in r.hint


def test_el_prefijo_de_pais_NO_se_deduce_del_largo():
    """La primera versión lo dedujo, y mentía con `+1` y con `+351`.

    El ancho del prefijo varía por país y aquí no hay de dónde sacarlo. Un
    prefijo inventado en una pantalla de evidencia es peor que un dígito menos.
    """
    assert resumen_destino("sms", {"to": "+15551234567"}).hint == "+•••••••4567"
    assert resumen_destino("sms", {"to": "+351911234567"}).hint == "+••••••••4567"


def test_whatsapp_es_el_mismo_criterio_que_sms():
    assert resumen_destino("whatsapp", {"to": "+525512345678"}).hint == "+••••••••5678"


@pytest.mark.parametrize("corto", ["+52", "1234", ""])
def test_un_telefono_demasiado_corto_no_se_ensena_a_medias(corto):
    """Enmascarar mal es peor que no enmascarar: se calla entero."""
    r = resumen_destino("sms", {"to": corto})
    assert r.hint == "•••" and r.count == 1


def test_el_webhook_ensena_EL_HOST_Y_NADA_MAS():
    """La ruta de un webhook es la credencial. Es la aserción central del módulo."""
    r = resumen_destino(
        "webhook", {"url": "https://hooks.example.com/services/T000/B000/xoxbSECRETO"}
    )
    assert r.kind == "webhook"
    assert r.hint == "hooks.example.com"
    assert "xoxbSECRETO" not in r.hint and "services" not in r.hint


def test_el_webhook_con_credenciales_en_la_autoridad_tampoco_las_ensena():
    # `changeme` y no una contraseña de aspecto real: el barrido de la regla de
    # oro 6 (`infra/scripts/tests/test_secret_scan.sh`) caza `uri-con-contrasena`
    # en el árbol entero, y tenía razón en marcarlo. Su convención declarada para
    # un valor que NO es real es exactamente esta palabra — declararlo en
    # PERMITIDOS habría sido engordar una lista de excepciones para un fixture.
    r = resumen_destino("webhook", {"url": "https://usuario:changeme@hooks.example.com/x"})
    assert r.hint == "hooks.example.com"
    assert "changeme" not in r.hint and "usuario" not in r.hint


def test_el_push_no_lleva_PII_y_sale_tal_cual():
    r = resumen_destino(
        "push", {"site_id": "7a000000-0000-0000-0000-0000000000a1", "push_class": "CRISIS"}
    )
    assert r.kind == "dispositivos"
    assert "CRISIS" in r.hint
    # Un sitio no es una persona: el identificador del inmueble sí puede salir.
    assert "7a000000" in r.hint


def test_lo_que_NO_se_reconoce_no_sale_Y_LO_DICE():
    """La propiedad que hace segura la lista: el canal de mañana no filtra sola."""
    r = resumen_destino("telepatia", {"to": "+525512345678", "cerebro": "izquierdo"})
    assert r.kind == DESCONOCIDO
    assert r.hint == ""
    assert r.unrecognised is True


def test_una_forma_rara_en_un_canal_conocido_tampoco_pasa():
    """Reconocer el canal no basta: la FORMA también tiene que encajar."""
    r = resumen_destino("email", {"destinatarios": ["ops@cliente.com"]})
    assert r.kind == DESCONOCIDO and r.hint == "" and r.unrecognised is True


def test_un_target_vacio_no_es_un_destinatario():
    r = resumen_destino("email", {})
    assert r.kind == DESCONOCIDO and r.count is None


def test_ningun_resumen_repite_un_dato_de_contacto_completo():
    """Barrido: por cada forma conocida, el original NO puede estar en el resumen."""
    casos = [
        ("email", {"to": ["ops@cliente.com"]}, "ops@cliente.com"),
        ("sms", {"to": "+525512345678"}, "525512345678"),
        ("whatsapp", {"to": "+525512345678"}, "525512345678"),
        ("webhook", {"url": "https://h.example.com/secreto"}, "secreto"),
    ]
    assert len(casos) == 4, "una forma conocida sin caso en el barrido"
    for canal, target, secreto in casos:
        r = resumen_destino(canal, target)
        assert secreto not in r.hint, f"{canal} filtra el dato completo"
