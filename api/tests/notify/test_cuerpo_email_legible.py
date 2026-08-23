"""[T-2.157] El cuerpo del correo lo lee una PERSONA, no un parser.

Hasta esta ficha el cuerpo era ``json.dumps(message, indent=2)``: catorce claves
ordenadas alfabéticamente, con la nota del solicitante —lo único que un inspector
necesita leer a las 3 de la mañana— enterrada entre dos UUID.

Es la misma familia que `T-2.104`: la lógica era correcta y lo que llegaba a la
persona no comunicaba. Aquello lo destapó una alerta mal titulada en la app; esto
lo destapó AWS al pedir «ejemplos del correo que planeas enviar, para asegurarnos
de que es contenido de calidad que los destinatarios quieran recibir».
"""

from __future__ import annotations

import json

from takab_api.notify.providers import cuerpo_email

_DICTAMEN = {
    "source": "takab-ailert",
    "incident_id": "0f0a5f2e-7b1a-4c9e-9a44-2c0f1d8e3b77",
    "site_id": "b3c1e0a2-11d4-4f77-9a02-7c5e2f9a1b30",
    "site_name": "Hospital General · Torre B",
    "site_code": "HGT-B",
    "severity": "alta",
    "trigger": "sasmex",
    "state": "open",
    "opened_at": "2026-08-22T14:03:11",
    "event_id": "evt-2026-08-22-0007",
    "headline": "TAKAB Ailert · Solicitud de dictamen · Hospital General · Torre B",
    "kind": "dictamen_request",
    "requested_by": "coordinador.pc@cliente.example",
    "note": "Grietas visibles en muro de escalera norte.",
    "link": "https://consola.example/triage?incident=0f0a5f2e",
}


def test_el_cuerpo_NO_es_un_volcado_json() -> None:
    """La guarda de raíz: si alguien vuelve a `json.dumps` esto se pone rojo."""
    cuerpo = cuerpo_email(_DICTAMEN)

    assert not cuerpo.lstrip().startswith("{"), cuerpo[:120]
    try:
        json.loads(cuerpo)
    except (ValueError, TypeError):
        pass
    else:  # pragma: no cover - solo se alcanza si vuelve el volcado
        raise AssertionError("el cuerpo del correo volvió a ser JSON parseable")


def test_la_nota_de_quien_lo_pide_se_lee_sin_buscarla() -> None:
    """Lo ÚNICO que un inspector necesita leer no puede ir enterrado.

    Se exige en la PRIMERA MITAD del cuerpo: que aparezca no basta —también
    aparecía en el JSON, en la novena clave por orden alfabético.
    """
    cuerpo = cuerpo_email(_DICTAMEN)
    nota = "Grietas visibles en muro de escalera norte."

    assert nota in cuerpo
    assert cuerpo.index(nota) < len(cuerpo) // 2, "la nota quedó en la mitad de abajo"


def test_el_sitio_y_lo_que_se_pide_van_antes_que_los_identificadores() -> None:
    """Un UUID no es información para el destinatario: es para soporte, y va al pie."""
    cuerpo = cuerpo_email(_DICTAMEN)

    assert cuerpo.index("Hospital General · Torre B") < cuerpo.index(_DICTAMEN["incident_id"]), (
        "el identificador aparece antes que el nombre del inmueble"
    )


def test_el_enlace_al_triage_esta_presente_cuando_lo_hay() -> None:
    assert _DICTAMEN["link"] in cuerpo_email(_DICTAMEN)


def test_sin_enlace_no_se_inventa_uno() -> None:
    """Regla de oro 7 aplicada al correo: lo que no se sabe no se rellena."""
    sin_link = {k: v for k, v in _DICTAMEN.items() if k != "link"}
    cuerpo = cuerpo_email(sin_link)

    assert "http" not in cuerpo, "se coló un enlace que el mensaje no traía"


def test_el_origen_se_nombra_por_lo_que_ES_y_no_se_atribuye_a_SASMEX() -> None:
    """[T-2.104] Un incidente que NO es de SASMEX no puede presentarse como suyo.

    Aquel defecto llegó a un teléfono porque el titular estaba escrito a fuego
    para las cuatro fuentes. El cuerpo del correo no puede repetirlo.
    """
    local = dict(_DICTAMEN, trigger="rules", severity="warning")
    cuerpo = cuerpo_email(local)

    assert "SASMEX" not in cuerpo.upper()

    oficial = cuerpo_email(dict(_DICTAMEN, trigger="sasmex"))
    assert "SASMEX" in oficial.upper()


def test_un_incidente_simple_sin_accion_tambien_se_lee() -> None:
    """El caso más frecuente no puede ser el peor tratado."""
    simple = {
        k: v for k, v in _DICTAMEN.items() if k not in {"kind", "requested_by", "note", "link"}
    }
    simple["headline"] = "TAKAB Ailert · Incidente alta · Hospital General · Torre B"
    cuerpo = cuerpo_email(simple)

    assert not cuerpo.lstrip().startswith("{")
    assert "Hospital General · Torre B" in cuerpo
    assert cuerpo.strip(), "cuerpo vacío"


def test_personas_en_riesgo_dice_QUE_pasa_antes_que_cualquier_dato() -> None:
    """La prioridad máxima del SOC no puede leerse como un incidente más."""
    riesgo = dict(
        _DICTAMEN,
        kind="damage_people_at_risk",
        headline="TAKAB Ailert · PERSONAS EN RIESGO · Hospital General · Torre B",
        reported_by="brigada@cliente.example",
    )
    riesgo.pop("requested_by", None)
    cuerpo = cuerpo_email(riesgo)

    assert "PERSONAS EN RIESGO" in cuerpo.upper()
    assert cuerpo.upper().index("PERSONAS EN RIESGO") < len(cuerpo) // 3
