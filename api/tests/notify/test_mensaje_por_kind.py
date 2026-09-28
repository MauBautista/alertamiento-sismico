"""[T-9.43] El correo del SOC decía «Solicitud de dictamen» cuando la brigada no acusó.

Defecto medido leyendo el código el 2026-09-28: `orchestrator._message` trataba
TODA acción que no fuera `damage_people_at_risk` como `dictamen_request`. El aviso
de `_enqueue_panic_ack_timeout` (`tactical_ack_timeout`) llegaba al SOC como «Se
solicita un dictamen de habitabilidad para X · Solicitado por: system» — el
operador leía una petición de papeleo donde había una brigada que no contestó.

El arreglo es una tabla CERRADA por kind, y lo que la hace cerrada son dos cosas
que se prueban aquí:

* **un kind desconocido LANZA** (`ValueError`) en vez de caer en una rama por
  omisión — que es exactamente cómo nació el defecto;
* **el censo se DERIVA de las SQL del orquestador**: qué kinds anclan un job de
  email (las consultas que eligen acciones con `WHERE a.kind = '…'` y los INSERT
  que las crean, en las funciones que encolan con `_INSERT_ACTION_JOB_SQL`). Un
  kind nuevo que ancle un correo sin rama en la tabla pone esto en rojo, y una
  rama que ya no ancla nada también.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from takab_api.notify import orchestrator as O
from takab_api.notify.providers import cuerpo_email

_FUENTE = Path(O.__file__)

_SELECCION = re.compile(r"^WHERE\s+a\.kind\s*=\s*'([a-z_]+)'", re.MULTILINE)
_INSERCION = re.compile(
    r"INSERT INTO incident_actions\s*\([^)]*\)\s*VALUES\s*\([^,]+,\s*[^,]+,\s*'([a-z_]+)'"
)


def _constantes() -> dict[str, str]:
    arbol = ast.parse(_FUENTE.read_text(encoding="utf-8"))
    fuera: dict[str, str] = {}
    for nodo in arbol.body:
        # El VALOR se lee del módulo importado y no del árbol: así cuenta también
        # una constante construida (`f"…"`, `.format(canal=…)`), ya resuelta.
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
            destino = nodo.targets[0]
            if isinstance(destino, ast.Name):
                valor = getattr(O, destino.id, None)
                if isinstance(valor, str):
                    fuera[destino.id] = valor
    return fuera


def kinds_que_anclan_un_correo() -> set[str]:
    """Los kinds de acción que acaban en un job `email` con `action_id`, del FUENTE."""
    constantes = _constantes()
    arbol = ast.parse(_FUENTE.read_text(encoding="utf-8"))
    kinds: set[str] = set()
    for nodo in arbol.body:
        if not isinstance(nodo, ast.FunctionDef):
            continue
        nombres = {n.id for n in ast.walk(nodo) if isinstance(n, ast.Name)}
        if "_INSERT_ACTION_JOB_SQL" not in nombres:
            continue
        for nombre in nombres & set(constantes):
            sql = constantes[nombre]
            kinds |= set(_SELECCION.findall(sql)) | set(_INSERCION.findall(sql))
    return kinds


def _fila(kind: str, **payload: object) -> dict:
    return {
        "incident_id": "0f0a0000-0000-0000-0000-000000000001",
        "site_id": "0f0a0000-0000-0000-0000-0000000000aa",
        "site_name": "Hospital General",
        "site_code": "HG-01",
        "severity": "critical",
        "trigger": "manual",
        "state": "open",
        "opened_at": datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        "event_id": None,
        "action_id": "0f0a0000-0000-0000-0000-0000000000bb",
        "action_kind": kind,
        "action_actor": "system",
        "action_payload": payload,
    }


# ------------------------------------------------------------------ el censo


def test_el_censo_no_esta_ciego() -> None:
    """Deriva al menos los tres que ya existían: si no, mediría la nada."""
    assert {"dictamen_request", "damage_people_at_risk", "tactical_ack_timeout"} <= (
        kinds_que_anclan_un_correo()
    )


def test_cada_kind_que_ancla_un_correo_tiene_su_rama_y_ninguna_sobra() -> None:
    derivados = kinds_que_anclan_un_correo()
    tabla = set(O.MENSAJE_POR_KIND)
    assert derivados == tabla, (
        f"kinds que anclan un correo sin rama: {sorted(derivados - tabla)}; "
        f"ramas que ya no ancla nadie: {sorted(tabla - derivados)}"
    )


def test_un_kind_desconocido_LANZA_y_no_cae_en_una_rama_por_omision() -> None:
    with pytest.raises(ValueError, match="kind_inventado"):
        O._message(_fila("kind_inventado"))  # noqa: SLF001


def test_cada_kind_tiene_titular_PROPIO() -> None:
    titulares = {k: O._message(_fila(k))["headline"] for k in O.MENSAJE_POR_KIND}  # noqa: SLF001
    assert len(set(titulares.values())) == len(titulares), titulares
    assert all("Hospital General" in t for t in titulares.values())


# ------------------------------------------------------------------ la brigada no acusó


def test_el_correo_de_la_brigada_NO_es_una_solicitud_de_dictamen() -> None:
    mensaje = O._message(_fila("tactical_ack_timeout", timeout_s=120, tactical_acks=0))  # noqa: SLF001
    assert mensaje["kind"] == "tactical_ack_timeout"
    assert mensaje["headline"] == "TAKAB Ailert · La brigada no acusó · Hospital General"
    assert "requested_by" not in mensaje

    cuerpo = cuerpo_email(mensaje)
    assert cuerpo.splitlines()[0] == (
        "Se activó una alerta de pánico en Hospital General y ningún brigadista acusó "
        "en 120 s. Decida si hay que avisar a todo el inmueble."
    )
    assert "dictamen" not in cuerpo.lower()
    assert "Solicitado por" not in cuerpo


def test_la_solicitud_de_dictamen_sigue_siendo_la_de_siempre() -> None:
    mensaje = O._message(  # noqa: SLF001
        _fila("dictamen_request", requested_by="user:ana", note="grieta en el muro"),
        base_url="https://consola.example",
    )
    assert mensaje["headline"] == "TAKAB Ailert · Solicitud de dictamen · Hospital General"
    assert mensaje["requested_by"] == "user:ana"
    assert mensaje["link"].endswith("/triage?incident=0f0a0000-0000-0000-0000-000000000001")
