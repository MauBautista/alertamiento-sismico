"""El acta del reflejo (T-5.22): la cifra de venta, como artefacto.

`contacto SASMEX → relé` está medido dos veces con hardware real y esa cifra es
la más citada del producto. Su evidencia eran **ocho documentos con el número
escrito a mano**: un cliente que pidiera la evidencia recibía un archivo de
texto. Esto es el acta — y lo que se fija aquí es que **no pueda mentir**.
"""

from __future__ import annotations

import json

import pytest
from takab_edge.audit.reflejo import MAX_ACTAS, ActaDeReflejo, ActaDeReflejoStore
from takab_edge.contracts import ActuatorChannel

CANALES = {"siren": True, "strobe": True, "gas_valve": False}


def _acta(**over) -> ActaDeReflejo:
    base = {
        "medido_en": "2026-09-03T12:00:00+00:00",
        "latencia_s": 0.00416,
        "gateway_id": "gw-dev-0001",
        "fw_version": "1.2.3",
        "es_prueba": False,
        "canales": CANALES,
    }
    base.update(over)
    return ActaDeReflejo(**base)


def test_el_acta_guarda_la_latencia_Y_EL_ESTADO_DE_LOS_CANALES(tmp_path):
    """Es lo que convierte el número en evidencia.

    «Tardó 4 ms» es una afirmación; «tardó 4 ms **y estos relés quedaron así**»
    es una medición que alguien puede discutir.
    """
    store = ActaDeReflejoStore(tmp_path / "reflejo.jsonl")
    assert store.registrar(_acta()) is True

    guardada = store.ultima()
    assert guardada is not None
    assert guardada["latencia_ms"] == 4.16
    assert guardada["canales"] == CANALES
    assert guardada["gateway_id"] == "gw-dev-0001"
    assert guardada["fw_version"] == "1.2.3"


def test_sin_actas_NO_devuelve_ceros(tmp_path):
    """Un `0.0 ms` sería la mejor latencia del catálogo y una mentira."""
    resumen = ActaDeReflejoStore(tmp_path / "vacio.jsonl").resumen()
    assert resumen == {"total": 0, "ultima": None, "mejor_ms": None, "peor_ms": None}


def test_el_resumen_publica_el_PEOR_caso_y_no_solo_el_mejor(tmp_path):
    """Publicar solo la mejor es cómo una cifra de venta deja de describir el producto."""
    store = ActaDeReflejoStore(tmp_path / "r.jsonl")
    for s in (0.00416, 0.0665, 0.0121):
        store.registrar(_acta(latencia_s=s))

    resumen = store.resumen()
    assert resumen["total"] == 3
    assert resumen["mejor_ms"] == 4.16
    assert resumen["peor_ms"] == 66.5


def test_un_pulso_de_PRUEBA_no_entra_en_la_cifra(tmp_path):
    """Un acta de prueba no acredita nada del camino real.

    Se guarda —es historial del aparato— pero no cuenta para la cifra que se
    cita: mezclarlas sería el mismo defecto con otro disfraz.
    """
    store = ActaDeReflejoStore(tmp_path / "r.jsonl")
    store.registrar(_acta(latencia_s=0.0665))
    store.registrar(_acta(latencia_s=0.0001, es_prueba=True))

    assert len(store.actas()) == 2, "el acta de prueba también se guarda"
    assert store.resumen()["total"] == 1
    assert store.resumen()["mejor_ms"] == 66.5, "la prueba se coló en la cifra"


def test_el_acta_SOBREVIVE_al_reinicio(tmp_path):
    """Un registro en memoria no es evidencia: un reinicio lo borra."""
    ruta = tmp_path / "r.jsonl"
    ActaDeReflejoStore(ruta).registrar(_acta())
    assert ActaDeReflejoStore(ruta).resumen()["total"] == 1


def test_el_fichero_no_crece_sin_fin_y_conserva_LO_ULTIMO(tmp_path):
    store = ActaDeReflejoStore(tmp_path / "r.jsonl")
    for i in range(MAX_ACTAS + 20):
        store.registrar(_acta(latencia_s=i / 1000))

    actas = store.actas()
    assert len(actas) == MAX_ACTAS
    # Se recorta por el principio: lo último medido es lo que se cita.
    assert actas[-1]["latencia_ms"] == (MAX_ACTAS + 19)


def test_una_linea_CORRUPTA_no_invalida_las_demas(tmp_path):
    ruta = tmp_path / "r.jsonl"
    store = ActaDeReflejoStore(ruta)
    store.registrar(_acta())
    ruta.write_text(ruta.read_text(encoding="utf-8") + "{esto no es json\n", encoding="utf-8")

    assert len(store.actas()) == 1, "una línea rota se lleva por delante el acta entera"


def test_registrar_JAMAS_lanza_aunque_el_disco_falle(tmp_path):
    """El camino de vida no se cae porque el acta no se pueda escribir."""
    # Un directorio donde debería ir el fichero: escribir es imposible.
    ruta = tmp_path / "ocupado"
    ruta.mkdir()
    store = ActaDeReflejoStore(ruta)

    assert store.registrar(_acta()) is False
    assert store.fallos == 1
    assert store.resumen()["total"] == 0


def test_el_acta_es_JSON_por_linea_legible_sin_el_codigo(tmp_path):
    """Un cliente que pida la evidencia tiene que poder abrirla sin nosotros."""
    ruta = tmp_path / "r.jsonl"
    ActaDeReflejoStore(ruta).registrar(_acta())
    linea = ruta.read_text(encoding="utf-8").strip()
    assert json.loads(linea)["latencia_ms"] == 4.16


# ── el acta se levanta de verdad, en el flanco ─────────────────────────────
#
# ⚠️ El acta vive donde la bitácora: un directorio DERIVADO Y ESTABLE, no un
# `mkdtemp` — es la lección de `T-2.67.b`, y es lo que hace que sobreviva a un
# reinicio del Pi. En tests eso significa que **se acumula entre corridas**, así
# que cada uno empieza vaciándola. Vaciarla aquí y no cambiarle la ruta es
# deliberado: probar contra una ruta de usar y tirar sería probar otra cosa.


@pytest.fixture
def acta_limpia(supervisor):  # noqa: ANN001
    supervisor.acta_reflejo.path.unlink(missing_ok=True)
    return supervisor


def test_un_flanco_del_WR1_DEJA_ACTA(acta_limpia):  # noqa: ANN001
    supervisor = acta_limpia
    """De punta a punta: el contacto se cierra y queda un artefacto con fecha."""
    supervisor.gpio.simulate_sasmex(active=True)

    resumen = supervisor.acta_reflejo.resumen()
    assert resumen["total"] == 1, "el flanco no dejó acta"
    ultima = resumen["ultima"]
    assert ultima["latencia_ms"] > 0
    assert ultima["gateway_id"] == supervisor.settings.gateway_id
    # Los canales del reflejo quedaron escritos, energizados.
    assert ultima["canales"]["siren"] is True
    assert ultima["canales"]["strobe"] is True


def test_ABRIR_el_contacto_no_levanta_acta(acta_limpia):  # noqa: ANN001
    supervisor = acta_limpia
    """La apertura no es un reflejo: su latencia no significa nada."""
    supervisor.gpio.simulate_sasmex(active=True)
    supervisor.gpio.simulate_sasmex(active=False)
    assert supervisor.acta_reflejo.resumen()["total"] == 1


def test_el_acta_sobrevive_a_que_el_disco_falle(acta_limpia, monkeypatch):  # noqa: ANN001
    supervisor = acta_limpia
    """El camino de vida no se cae porque no se pueda escribir el acta."""
    monkeypatch.setattr(
        supervisor.acta_reflejo,
        "registrar",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("disco lleno")),
    )
    supervisor.gpio.simulate_sasmex(active=True)
    # Y el reflejo ocurrió igual: sirena y estrobo energizados.
    assert supervisor.gpio.relay_state(ActuatorChannel.SIREN).energized is True
