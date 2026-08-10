"""[T-2.75.a] ``GET /notify/channels`` — a quién le pregunta la consola.

T-2.75 enseñó al orquestador a no decir "enviado" sin proveedor real, y el grito
de arranque lo deja escrito en el log del worker. Pero la consola rotulaba
«SIMULADO en el MVP» como TEXTO ESTÁTICO, así que el día que T-2.76.a/T-2.77.a
carguen credenciales el canal será real **y el rótulo seguirá diciendo que es
simulado**: la regla de oro 7 al revés — un operador que necesita avisar por SMS
leería que no sirve y buscaría otra vía.

La causa raíz no era el rótulo: era que **no había a quién preguntar**. Este
endpoint es ese alguien, y su respuesta se DERIVA del registro que construye
``build_providers()`` — el mismo que arranca el worker—, jamás de una lista de
canales escrita a mano.

La costura con la consola es ``shared/fixtures/notify-channels.json``: aquí se
comprueba que el endpoint produce EXACTAMENTE esos bytes; en
``web/src/features/tenants/NotificationChannels.test.tsx`` se comprueba que esos
mismos bytes son los que pintan REAL o SIMULADO. Mover un provider de simulado a
real cambia esta respuesta ⇒ obliga a mover el fichero ⇒ cambia lo que pinta la
consola, sin tocar una línea de la web.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

import auth_utils as au
from takab_api.auth.matrix import ROLE_ACTION_MATRIX, roles_with_action
from takab_api.main import create_app
from takab_api.notify.providers import build_providers, is_simulated
from takab_api.settings import Settings

_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "shared" / "fixtures" / "notify-channels.json"

# Credenciales de mentira (mismo patrón que ``tests/notify/test_twilio.py``): el
# canal asciende a real por TENER las tres piezas, no por que sean válidas.
_SID = "AC00000000000000000000000000000000"
_TOKEN = "token-de-mentira-para-el-test"
_FROM = "+525599999999"

# Todo lo que decide la realidad de un canal. Se BORRA del entorno antes de cada
# escenario: si la máquina que corre los tests tuviera una credencial exportada,
# el escenario "sin credenciales" dejaría de serlo y el fixture bailaría.
_NOTIFY_ENV = (
    "TAKAB_API_NOTIFY_EMAIL_FROM",
    "TAKAB_API_NOTIFY_SMS_ACCOUNT_SID",
    "TAKAB_API_NOTIFY_SMS_AUTH_TOKEN",
    "TAKAB_API_NOTIFY_SMS_FROM",
    "TAKAB_API_NOTIFY_SMS_MESSAGING_SERVICE_SID",
    "TAKAB_API_NOTIFY_WHATSAPP_PHONE_NUMBER_ID",
    "TAKAB_API_NOTIFY_WHATSAPP_ACCESS_TOKEN",
    "TAKAB_API_NOTIFY_WHATSAPP_GRAPH_VERSION",
    "TAKAB_API_PUSH_APNS_APPLICATION_ARN",
    "TAKAB_API_PUSH_FCM_APPLICATION_ARN",
)


def _fixture() -> dict[str, Any]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _NOTIFY_ENV:
        monkeypatch.delenv(name, raising=False)


def _app_sin_credenciales(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """La app tal cual arranca hoy: ni SMS ni WhatsApp ni SES configurados."""
    _clean_env(monkeypatch)
    return create_app()


def _app_con_sms_real(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """La app del día después de T-2.76.a: Twilio con sus tres piezas."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("TAKAB_API_NOTIFY_SMS_ACCOUNT_SID", _SID)
    monkeypatch.setenv("TAKAB_API_NOTIFY_SMS_AUTH_TOKEN", _TOKEN)
    monkeypatch.setenv("TAKAB_API_NOTIFY_SMS_FROM", _FROM)
    return create_app()


async def _get(app: FastAPI, *, role: str = "tenant_admin") -> Any:
    async with au.client_for(app) as client:
        return await client.get(
            "/notify/channels",
            headers={"Authorization": f"Bearer {au.make_token(role)}"},
        )


# --- criterio 1 · el dato sale del REGISTRO, no de una lista -------------------


async def test_los_canales_son_los_del_registro_no_una_lista_escrita_a_mano(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El conjunto de canales que declara el endpoint es EL DEL REGISTRO.

    Si mañana alguien enchufa un sexto canal en ``build_providers`` y no lo
    declara aquí, este test se pone rojo: el canal nuevo no puede quedarse
    invisible para la consola, porque invisible se pinta ``S/D`` para siempre
    y nadie se entera de que no entrega nada.
    """
    app = _app_sin_credenciales(monkeypatch)
    response = await _get(app)
    assert response.status_code == 200

    esperado = build_providers(Settings())
    assert {c["channel"] for c in response.json()["channels"]} == set(esperado)


async def test_cada_canal_dice_lo_que_dice_su_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``simulated`` se lee del provider (``is_simulated``), canal por canal."""
    app = _app_sin_credenciales(monkeypatch)
    response = await _get(app)

    registro = build_providers(Settings())
    dicho = {c["channel"]: c["simulated"] for c in response.json()["channels"]}
    assert dicho == {canal: is_simulated(p) for canal, p in registro.items()}


# --- criterio 3 · de simulado a real, y la consola lo nota ---------------------


async def test_sin_credenciales_la_respuesta_es_LA_DEL_FIXTURE(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Escenario de HOY, byte a byte. Es la mitad de la costura con la consola."""
    app = _app_sin_credenciales(monkeypatch)
    response = await _get(app)
    assert response.json() == _fixture()["escenarios"]["sin_credenciales"]


async def test_con_credenciales_el_sms_ASCIENDE_y_la_respuesta_cambia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Escenario del día después de T-2.76.a, también byte a byte.

    Éste es el criterio 3: **nada de la web se toca** y aun así lo que la
    consola pinta para SMS pasa de SIMULADO a REAL, porque el fichero que la
    consola renderiza en su test es este mismo, y aquí se comprueba que lo
    produce el registro de verdad.
    """
    sin = await _get(_app_sin_credenciales(monkeypatch))
    con = await _get(_app_con_sms_real(monkeypatch))

    assert con.json() == _fixture()["escenarios"]["sms_con_credenciales"]
    assert con.json() != sin.json()

    def sms(payload: dict) -> dict:
        return next(c for c in payload["channels"] if c["channel"] == "sms")

    assert sms(sin.json())["simulated"] is True
    assert sms(con.json())["simulated"] is False
    # Y NADA más se mueve: ascender el SMS no vuelve real al vecino de al lado.
    assert [c for c in con.json()["channels"] if c["channel"] != "sms"] == [
        c for c in sin.json()["channels"] if c["channel"] != "sms"
    ]


async def test_el_fixture_declara_los_dos_escenarios_y_nada_mas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La costura no crece sola: dos escenarios, y los dos verificados arriba."""
    assert set(_fixture()["escenarios"]) == {"sin_credenciales", "sms_con_credenciales"}


# --- autorización · la acción la declara la matriz, no este router ------------


async def test_los_roles_permitidos_son_EXACTAMENTE_los_de_la_matriz(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ni un rol enumerado a mano: la frontera es ``edit_thresholds`` (T-2.79.e)."""
    app = _app_sin_credenciales(monkeypatch)
    permitidos = set(roles_with_action("edit_thresholds"))
    assert permitidos, "la acción debe existir en la matriz"

    for role in ROLE_ACTION_MATRIX:
        response = await _get(app, role=role)
        esperado = 200 if role in permitidos else 403
        assert response.status_code == esperado, f"{role} → {response.status_code}"


async def test_sin_token_no_se_contesta(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_sin_credenciales(monkeypatch)
    async with au.client_for(app) as client:
        response = await client.get("/notify/channels")
    assert response.status_code == 401
