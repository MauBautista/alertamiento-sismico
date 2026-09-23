"""[T-8.12 · A-080 · A-208] Generar un PDF NO congela el event loop.

`generate_report` y `drill_report` son `async def`, pero llamaban EN LÍNEA al
render de fpdf2 (CPU pura) y a boto3 síncrono (`put_object`, `presign_get`, y
`get_object` para cada foto y el miniSEED dentro del builder). La API corre con
UN solo worker (`deploy/cloud/docker-compose.yml`): mientras duraba el render se
congelaban el WebSocket de la consola, `/health` y el sondeo que la app hace cada
5 s en crisis. El patrón correcto ya estaba en el repo
(`commands/service.py:118`, `anyio.to_thread.run_sync`).

## Cómo se demuestra, y por qué así

Con COMPORTAMIENTO, no con una lectura del fuente: se hace LENTO lo síncrono
—un `time.sleep` dentro del render y de la subida— y, mientras la petición
corre, una corrutina concurrente anota cuánto tarda cada vuelta del loop. Con el
render en el loop, esa corrutina se queda parada todo el `sleep` y además todo
el render de verdad; en un hilo, sigue girando. Medido contra el código de antes
(`HEAD` de `5857c12`, 2026-09-23), con 0.6 s de sueño en el render y otros 0.6 en
la subida: el loop se quedó parado **1.74 s** generando el dictamen y **1.53 s**
exportando el simulacro —el medio segundo que sobra es el render real del
modelo de prueba, en el loop—. El cliente es ASGI en proceso, así que la app y
la corrutina comparten el MISMO loop, que es justo la situación del worker único.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import FastAPI
from moto import mock_aws

import auth_utils as au
from takab_api.main import create_app
from takab_api.routers import drills as drills_mod
from takab_api.routers import reports as reports_mod
from takab_api.routers.commands import get_publisher
from takab_api.routers.drills import router as drills_router
from takab_api.routers.reports import router as reports_router
from tests.api.test_commands_router import (  # noqa: F401  (fixtures por nombre)
    KEY,
    THING,
    _FakePublisher,
    gateway,
    publisher,
)

pytestmark = pytest.mark.asyncio

BUCKET = "takab-dev-evidence"
_REGION = "us-east-2"
#: Lo que se hace esperar a cada llamada síncrona. Y el hueco máximo tolerado en
#: el loop: bastante por encima de una vuelta normal, bastante por debajo del
#: sueño, para que la prueba no dependa de lo rápida que sea la máquina.
_SUENO_S = 0.6
_HUECO_MAX_S = 0.3


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.include_router(reports_router)
    application.include_router(drills_router)
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))
    monkeypatch.setenv("TAKAB_API_EVIDENCE_BUCKET", BUCKET)
    monkeypatch.setenv("TAKAB_API_AWS_REGION", _REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)


def _bucket() -> None:
    import boto3

    boto3.client("s3", region_name=_REGION).create_bucket(
        Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": _REGION}
    )


def _lento(funcion):  # noqa: ANN001, ANN202
    def envuelta(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        time.sleep(_SUENO_S)
        return funcion(*args, **kwargs)

    return envuelta


async def _mide_el_loop(peticion) -> tuple[object, float]:  # noqa: ANN001
    """Corre `peticion` mientras una corrutina mide el hueco MÁS LARGO del loop."""
    parada = asyncio.Event()
    huecos: list[float] = []

    async def latido() -> None:
        ultimo = time.monotonic()
        while True:
            await asyncio.sleep(0.01)
            ahora = time.monotonic()
            huecos.append(ahora - ultimo)
            ultimo = ahora
            # Se mira DESPUÉS de anotar: la vuelta que despierta tras el bloqueo
            # es justo la que trae el hueco, y no se puede perder.
            if parada.is_set():
                return

    tarea = asyncio.create_task(latido())
    await asyncio.sleep(0)  # que el latido esté girando ANTES de empezar
    try:
        respuesta = await peticion
    finally:
        parada.set()
        await tarea
    # No-vacuidad: el latido tiene que haber dado al menos una vuelta COMPLETA. No
    # se le pide un número de vueltas: con el loop bloqueado da sólo dos o tres,
    # y es justo el caso que el hueco de abajo tiene que poder contar.
    assert huecos, "el latido no llegó a girar: la medida no dice nada"
    return respuesta, max(huecos)


async def test_generar_el_DICTAMEN_no_congela_el_loop(client, make_incident, monkeypatch) -> None:
    monkeypatch.setattr(reports_mod, "render", _lento(reports_mod.render))
    monkeypatch.setattr(reports_mod, "put_object", _lento(reports_mod.put_object))
    with mock_aws():
        _bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        tok = au.bearer(au.make_token("inspector", tenant=au.DB_TENANT_PRIV))
        r, hueco = await _mide_el_loop(client.post(f"/incidents/{iid}/report", headers=tok))
    assert r.status_code == 201, r.text
    assert hueco < _HUECO_MAX_S, (
        f"el loop se quedó parado {hueco:.2f} s mientras se generaba el dictamen: el "
        "render o la subida a S3 corren DENTRO del event loop del único worker"
    )


async def test_exportar_el_SIMULACRO_no_congela_el_loop(
    client, gateway, publisher, monkeypatch
) -> None:
    monkeypatch.setattr(drills_mod, "render_drill_report", _lento(drills_mod.render_drill_report))
    monkeypatch.setattr(drills_mod, "put_object", _lento(drills_mod.put_object))
    tok = au.bearer(au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV, site_scope="*"))
    with mock_aws():
        _bucket()
        creado = await client.post(
            "/drills",
            json={"site_ids": [au.DB_SITE_PRIV], "duration_s": 120, "note": "trimestral"},
            headers=tok,
        )
        assert creado.status_code == 201, creado.text
        did = creado.json()["drill_id"]
        r, hueco = await _mide_el_loop(client.post(f"/drills/{did}/report", headers=tok))
    assert r.status_code == 201, r.text
    assert hueco < _HUECO_MAX_S, (
        f"el loop se quedó parado {hueco:.2f} s mientras se exportaba el simulacro"
    )
