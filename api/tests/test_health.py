from fastapi.testclient import TestClient

from takab_api.main import app

client = TestClient(app)


def test_health_returns_ok(monkeypatch):
    monkeypatch.delenv("TAKAB_API_BUILD_SHA", raising=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    # Sin la variable, el build se declara DESCONOCIDO en vez de inventar una versión.
    assert resp.json() == {"status": "ok", "build": "unknown"}


def test_health_reports_deployed_build(monkeypatch):
    """El health debe decir QUÉ COMMIT está vivo.

    Hasta ahora respondía `{"status":"ok"}` fijo y `version` estaba hardcodeada a
    "0.1.0", así que la única forma de saber qué corría en la nube era entrar por SSM
    a leer `/etc/takab/deploy.env`. Costó no darse cuenta de que la nube llevaba 82
    commits de retraso: la API móvil de Fase 2 no estaba desplegada y el síntoma
    aparecía como un 401 en el login del móvil.
    """
    monkeypatch.setenv("TAKAB_API_BUILD_SHA", "8f385fb")
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "build": "8f385fb"}
