import pytest
from fastapi.testclient import TestClient

from takab_api import health as health_mod
from takab_api.main import app
from takab_api.ops import schema_version as sv

client = TestClient(app)


@pytest.fixture(autouse=True)
def _esquema_neutro(monkeypatch):
    """Estos tests miran el COMMIT; el esquema se fija para que no dependa de la base.

    Sin esto, `/health` abriría una conexión real y el veredicto de estos dos tests
    dependería de si el Postgres local está arriba — que es exactamente el tipo de
    test que un día sale rojo por algo que no está probando.
    """

    async def _al_dia():
        return sv.comparar("0001_x", "0001_x")

    monkeypatch.setattr(health_mod, "estado_del_esquema", _al_dia)


def test_health_returns_ok(monkeypatch):
    monkeypatch.delenv("TAKAB_API_BUILD_SHA", raising=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    # Sin la variable, el build se declara DESCONOCIDO en vez de inventar una versión.
    assert resp.json()["status"] == "ok"
    assert resp.json()["build"] == "unknown"


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
    assert resp.json()["build"] == "8f385fb"


# ---- [T-2.153] la deriva de esquema, que es la que muerde en silencio ---------


def test_el_health_declara_las_DOS_revisiones_y_las_COMPARA(monkeypatch):
    """Declararlas sin compararlas es dar el dato al humano que ya no está mirando."""

    async def _al_dia():
        return sv.comparar("0046_privacy_subject_sealing", "0046_privacy_subject_sealing")

    monkeypatch.setattr(health_mod, "estado_del_esquema", _al_dia)
    esquema = client.get("/health").json()["esquema"]
    assert esquema["aplicada"] == "0046_privacy_subject_sealing"
    assert esquema["esperada"] == "0046_privacy_subject_sealing"
    assert esquema["estado"] == sv.AL_DIA
    assert esquema["pendientes"] == 0


def test_un_esquema_ATRASADO_lo_dice_y_dice_CUANTO(monkeypatch):
    """El caso real del 2026-08-21, reproducido: nube en `0038`, repo en `0046`.

    Son las revisiones exactas que se midieron, y el `8` es el número que nadie tuvo:
    de haberlo publicado, la media hora de diagnóstico habría sido un vistazo.
    """

    async def _atrasada():
        return sv.comparar("0038_privacy_erasure_on_behalf", "0046_privacy_subject_sealing")

    monkeypatch.setattr(health_mod, "estado_del_esquema", _atrasada)
    body = client.get("/health").json()
    assert body["status"] == "ok", (
        "un esquema viejo NO puede tumbar el health: es un problema de datos, no un "
        "proceso muerto, y reiniciaría en bucle un contenedor sano"
    )
    assert body["esquema"]["estado"] == sv.ATRASADA
    assert body["esquema"]["pendientes"] == 8


def test_no_poder_preguntar_NO_es_estar_al_dia(monkeypatch):
    """El estado que de verdad importa, y el que es fácil perder al «simplificar».

    Con la base caída —o sin permiso sobre `alembic_version`, que en la nube es del
    rol migrador y no de la app— lo honesto es `desconocida`. Colapsarlo a `al_dia`
    sería un fallback presentándose como `ok`: el defecto de `T-2.152`, aquí otra vez.
    """

    async def _sin_respuesta():
        return sv.comparar(None, "0046_privacy_subject_sealing")

    monkeypatch.setattr(health_mod, "estado_del_esquema", _sin_respuesta)
    esquema = client.get("/health").json()["esquema"]
    assert esquema["estado"] == sv.DESCONOCIDA
    assert esquema["estado"] != sv.AL_DIA
    assert esquema["aplicada"] is None
    assert esquema["pendientes"] is None


def test_la_base_POR_DELANTE_de_la_imagen_tampoco_es_al_dia(monkeypatch):
    """Pasa al revertir la imagen sin revertir el esquema, y es peligroso al revés:
    el código viejo no conoce lo que hay debajo. Se sabe que DIFIEREN, así que no es
    `desconocida`; y no se puede contar cuánto, así que `pendientes` es `None`."""

    async def _adelantada():
        return sv.comparar("9999_del_futuro", "0046_privacy_subject_sealing")

    monkeypatch.setattr(health_mod, "estado_del_esquema", _adelantada)
    esquema = client.get("/health").json()["esquema"]
    assert esquema["estado"] == sv.ADELANTADA
    assert esquema["pendientes"] is None


def test_la_cabeza_ESPERADA_sale_de_las_migraciones_que_la_imagen_TRAE() -> None:
    """Sin mocks: la cabeza se deriva de los ficheros reales, no de una constante.

    Si alguien la clavara a mano, este test seguiría verde el día que naciera una
    migración nueva — y el health mentiría justo cuando hace falta.
    """
    esperada = sv.revision_esperada()
    assert esperada is not None, "no se pudo derivar la cabeza: el health diría `desconocida`"
    # Los scripts viven en `versions/`; `_dir_migraciones()` devuelve el directorio
    # que alembic espera como `script_location`, que es el padre.
    ficheros = list((sv._dir_migraciones() / "versions").glob("*.py"))
    assert len(ficheros) > 40, f"solo se vieron {len(ficheros)} migraciones: la ruta está mal"
    assert any(f.stem == esperada for f in ficheros), (
        f"la cabeza {esperada!r} no corresponde a ningún fichero de migración"
    )
