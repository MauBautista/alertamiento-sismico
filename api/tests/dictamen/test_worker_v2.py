"""Worker del dictamen ``dictamen-v2`` contra Postgres real (T-9.30/T-9.31 · D-43).

Reusa el escenario de ``test_service.py`` (tenant fresco, ``SET ROLE takab_ingest``,
BASE en 2032). Lo que se mide aquí es lo que la regla pura no puede medir: de
dónde sale la PGA (sensores ACTIVOS), la calibración de TODOS los activos, los
daños, la firma del sistema tras la gracia, que la prudencia sube sola y nunca
baja sin firma, y que dos escritores no bifurcan la cadena.
"""

# ruff: noqa: F811  (fixture de pytest importada por nombre)

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.dictamen.rules import RULE_SET_VERSION
from takab_api.dictamen.service import run_dictamen_pass
from takab_api.dictamen.sistema import SYSTEM_DICTAMEN_SIGNER_UUID
from takab_api.settings import Settings
from tests.dictamen.test_service import (  # noqa: F401  (fixture por nombre)
    BASE,
    NOW,
    _dsn,
    _Scenario,
    scenario,
)

GRACIA = Settings().dictamen_verde_gracia_s


def _run(conn: psycopg.Connection, now: datetime) -> list[str]:
    return run_dictamen_pass(conn, Settings(), now=now, lookback_s=300.0, settle_s=60.0)


def _sensor(
    sc: _Scenario, site: str, *, pga: float | None, calibrado: bool = True, status="active"
) -> str:
    sensor = str(uuid.uuid4())
    sc.conn.execute(
        "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model, status, "
        "calibration_source) VALUES (%s,%s,%s,'ground','RS4D',%s,%s)",
        (sensor, sc.tenant, site, status, "fabricante RS4D" if calibrado else None),
    )
    if pga is not None:
        sc.conn.execute(
            "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel, pga_g) "
            "VALUES (%s,%s,%s,%s,'ENZ',%s)",
            (BASE + timedelta(seconds=2), sc.tenant, site, sensor, pga),
        )
    sc.conn.commit()
    return sensor


def _caso(sc: _Scenario, *, pga: float | None = 0.01, severity: str = "info") -> dict:
    """Incidente con UN sensor estructural calibrado a ``pga``."""
    ids = sc.seed_incident(severity=severity, pga_g=pga)
    sc.conn.execute(
        "UPDATE sensors SET calibration_source = 'fabricante RS4D' WHERE sensor_id = %s",
        (ids["sensor"],),
    )
    sc.conn.commit()
    return ids


def _dano(sc: _Scenario, ids: dict, *keys: str) -> None:
    sc.conn.execute(
        "INSERT INTO damage_reports (tenant_id, incident_id, site_id, user_sub, categories) "
        "VALUES (%s,%s,%s,%s,%s::jsonb)",
        (
            sc.tenant,
            ids["incident"],
            ids["site"],
            str(uuid.uuid4()),
            json.dumps([{"key": k, "severity": "high"} for k in keys]),
        ),
    )
    sc.conn.commit()


def _tier(sc: _Scenario, ids: dict, tier: str, ts: datetime) -> None:
    sc.conn.execute(
        "INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, prev_tier, new_tier) "
        "VALUES (%s,%s,%s,%s,'normal',%s)",
        (ts, sc.tenant, ids["site"], str(uuid.uuid4()), tier),
    )
    sc.conn.commit()


def _cadena(sc: _Scenario, incident: str) -> list[dict]:
    return sc.conn.execute(
        "SELECT dictamen_id, status, band, signed_by, signature_kind, basis, "
        "supersedes_dictamen_id FROM dictamens WHERE incident_id = %s "
        "ORDER BY created_at, dictamen_id",
        (incident,),
    ).fetchall()


def _firmar_inspector(sc: _Scenario, incident: str, head: str, status: str, band: str) -> None:
    sc.conn.execute(
        "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, "
        "supersedes_dictamen_id, signature_kind, band, created_at) "
        "VALUES (%s,%s,%s,'{}'::jsonb,%s,%s,'inspector',%s, clock_timestamp())",
        (sc.tenant, incident, status, str(uuid.uuid4()), head, band),
    )
    sc.conn.commit()


# ------------------------------------------------------------------ bandas


def test_emite_v2_con_banda_y_sin_firma(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.07)
    _run(scenario.conn, NOW)
    [fila] = _cadena(scenario, ids["incident"])
    assert fila["band"] == "amarillo" and fila["status"] == "inhabit_monitor"
    assert fila["signed_by"] is None and fila["signature_kind"] is None
    assert fila["basis"]["rule_set_version"] == RULE_SET_VERSION == "dictamen-v2"


def test_sasmex_con_pga_baja_ya_no_es_rojo(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01, severity="critical")
    _run(scenario.conn, NOW)
    assert _cadena(scenario, ids["incident"])[0]["band"] == "verde"


def test_la_pga_es_el_MAXIMO_de_los_activos_y_un_retirado_no_cuenta(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01)
    _sensor(scenario, ids["site"], pga=0.07)  # activo, calibrado: manda
    _sensor(scenario, ids["site"], pga=0.5, calibrado=False, status="retired")  # no cuenta
    _run(scenario.conn, NOW)
    [fila] = _cadena(scenario, ids["incident"])
    assert fila["basis"]["evidence"]["pga_g"] == pytest.approx(0.07)
    assert fila["band"] == "amarillo"
    assert fila["basis"]["evidence"]["active_sensors"] == 2


def test_un_retirado_sin_calibrar_no_impide_el_verde(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01)
    _sensor(scenario, ids["site"], pga=None, calibrado=False, status="retired")
    _run(scenario.conn, NOW)
    assert _cadena(scenario, ids["incident"])[0]["band"] == "verde"


def test_un_activo_sin_calibrar_lleva_a_amarillo(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01)
    _sensor(scenario, ids["site"], pga=None, calibrado=False)
    _run(scenario.conn, NOW)
    fila = _cadena(scenario, ids["incident"])[0]
    assert fila["band"] == "amarillo"
    assert "sin_calibracion" in fila["basis"]["motivos"]


def test_sin_pga_es_amarillo(scenario: _Scenario) -> None:
    ids = scenario.seed_incident(severity="critical", pga_g=None)
    scenario.conn.execute(
        "UPDATE sensors SET calibration_source = 'x' WHERE sensor_id = %s", (ids["sensor"],)
    )
    scenario.conn.commit()
    _run(scenario.conn, NOW)
    fila = _cadena(scenario, ids["incident"])[0]
    assert fila["band"] == "amarillo"
    assert fila["basis"]["evidence"]["pga_source"] == "none"


def test_umbrales_de_rule_sets_dictamen_v2(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.07)
    scenario.conn.execute(
        "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, is_active, config) "
        "VALUES (%s,'site',%s,1,true,%s::jsonb)",
        (scenario.tenant, ids["site"], '{"dictamen_v2": {"verde_max_g": 0.08, "rojo_min_g": 0.2}}'),
    )
    scenario.conn.commit()
    _run(scenario.conn, NOW)
    fila = _cadena(scenario, ids["incident"])[0]
    assert fila["band"] == "verde"
    assert fila["basis"]["params"] == {"verde_max_g": 0.08, "rojo_min_g": 0.2}


# ------------------------------------------------------- firma del sistema


def test_verde_firmado_por_el_sistema_SOLO_tras_la_gracia(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)  # BASE+180: preliminar VERDE, gracia sin cumplir
    [pre] = _cadena(scenario, ids["incident"])
    assert pre["band"] == "verde" and pre["signed_by"] is None

    antes = BASE + timedelta(seconds=GRACIA - 1)
    assert _run(scenario.conn, antes) == []
    assert len(_cadena(scenario, ids["incident"])) == 1

    despues = BASE + timedelta(seconds=GRACIA + 1)
    creados = _run(scenario.conn, despues)
    assert len(creados) == 1
    pre2, firmado = _cadena(scenario, ids["incident"])
    assert firmado["signature_kind"] == "system"
    assert str(firmado["signed_by"]) == SYSTEM_DICTAMEN_SIGNER_UUID
    assert firmado["band"] == "verde" and firmado["status"] == "normal_operation"
    assert firmado["supersedes_dictamen_id"] == pre["dictamen_id"]
    assert firmado["basis"]["rule_set_version"] == "dictamen-v2"
    # idempotente
    assert _run(scenario.conn, despues + timedelta(seconds=30)) == []


def test_la_gracia_cuenta_desde_que_el_tier_vuelve_a_normal(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01)
    _tier(scenario, ids, "watch", BASE + timedelta(seconds=1))
    _run(scenario.conn, NOW)
    # tier sigue en watch mucho después: no se firma
    assert _run(scenario.conn, BASE + timedelta(seconds=2000)) == []
    _tier(scenario, ids, "normal", BASE + timedelta(seconds=2000))
    assert _run(scenario.conn, BASE + timedelta(seconds=2000 + GRACIA - 5)) == []
    assert len(_run(scenario.conn, BASE + timedelta(seconds=2000 + GRACIA + 5))) == 1


def test_con_un_reporte_de_dano_no_hay_verde_del_sistema(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)
    _dano(scenario, ids, "water_leak")
    _run(scenario.conn, BASE + timedelta(seconds=GRACIA + 1))
    cadena = _cadena(scenario, ids["incident"])
    assert [f["band"] for f in cadena] == ["verde", "amarillo"]
    assert all(f["signature_kind"] != "system" for f in cadena)


# ---------------------------------------------------- la prudencia sube sola


def test_dano_estructural_tras_verde_del_sistema_reabre_en_ROJO_sin_firmar(
    scenario: _Scenario,
) -> None:
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)
    _run(scenario.conn, BASE + timedelta(seconds=GRACIA + 1))
    assert _cadena(scenario, ids["incident"])[-1]["signature_kind"] == "system"
    # el incidente puede estar CERRADO: la re-evaluación dura 72 h
    scenario.conn.execute(
        "UPDATE incidents SET state = 'closed', closed_at = %s WHERE incident_id = %s",
        (BASE + timedelta(seconds=GRACIA + 2), ids["incident"]),
    )
    scenario.conn.commit()
    _dano(scenario, ids, "structural")
    _run(scenario.conn, BASE + timedelta(hours=30))
    cadena = _cadena(scenario, ids["incident"])
    ultimo = cadena[-1]
    assert ultimo["band"] == "rojo" and ultimo["status"] == "no_inhabit_inspect"
    assert ultimo["signed_by"] is None and ultimo["signature_kind"] is None
    assert ultimo["supersedes_dictamen_id"] == cadena[-2]["dictamen_id"]
    assert "dano:structural" in ultimo["basis"]["motivos"]


def test_dano_tras_firma_del_inspector_tambien_sube(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.07)
    _run(scenario.conn, NOW)
    [pre] = _cadena(scenario, ids["incident"])
    _firmar_inspector(scenario, ids["incident"], pre["dictamen_id"], "normal_operation", "verde")
    _dano(scenario, ids, "gas_leak")
    _run(scenario.conn, BASE + timedelta(hours=1))
    assert _cadena(scenario, ids["incident"])[-1]["band"] == "rojo"


def test_fuera_de_las_72_h_un_dano_no_reevalua(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)
    _dano(scenario, ids, "structural")
    assert _run(scenario.conn, BASE + timedelta(hours=73)) == []


def test_la_prudencia_NO_baja_sola(scenario: _Scenario) -> None:
    """Un AMARILLO sin firmar no se convierte en VERDE aunque la evidencia baje."""
    ids = _caso(scenario, pga=0.01)
    extra = _sensor(scenario, ids["site"], pga=None, calibrado=False)
    _run(scenario.conn, NOW)
    assert _cadena(scenario, ids["incident"])[0]["band"] == "amarillo"
    scenario.conn.execute(
        "UPDATE sensors SET calibration_source = 'x' WHERE sensor_id = %s", (extra,)
    )
    scenario.conn.commit()
    assert _run(scenario.conn, NOW + timedelta(seconds=30)) == []
    assert _run(scenario.conn, BASE + timedelta(seconds=GRACIA + 10)) == []
    assert [f["band"] for f in _cadena(scenario, ids["incident"])] == ["amarillo"]


def test_una_firma_inspector_rojo_nunca_se_corrige_sola(scenario: _Scenario) -> None:
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)
    [pre] = _cadena(scenario, ids["incident"])
    _firmar_inspector(scenario, ids["incident"], pre["dictamen_id"], "no_inhabit_inspect", "rojo")
    _dano(scenario, ids, "water_leak")
    assert _run(scenario.conn, BASE + timedelta(hours=2)) == []


# ---------------------------------------------------- la cadena no se bifurca


def test_la_cadena_no_se_bifurca_con_dos_escritores(scenario: _Scenario) -> None:
    """Un escritor (la firma) toma el incidente FOR UPDATE e inserta; el worker,
    en paralelo, tiene que esperar y encadenar su fila DETRÁS de la firma."""
    # Sin PGA (AMARILLO): el backfill no tiene nada que escribir y no toca la fila
    # del incidente, así que el ÚNICO punto de espera es el FOR UPDATE que se mide.
    ids = _caso(scenario, pga=None)
    _run(scenario.conn, NOW)
    [pre] = _cadena(scenario, ids["incident"])
    _dano(scenario, ids, "structural")

    otro = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    try:
        # La firma toma el incidente ANTES de que el worker lea la cabeza…
        otro.execute(
            "SELECT 1 FROM incidents WHERE incident_id = %s FOR UPDATE", (ids["incident"],)
        )
        worker = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
        worker.execute("SET ROLE takab_ingest")
        hilo = threading.Thread(target=_run, args=(worker, BASE + timedelta(hours=1)), daemon=True)
        hilo.start()
        time.sleep(0.8)  # …el worker ya está dentro de su pasada…
        # …y sólo entonces inserta y confirma. Sin el FOR UPDATE del worker, éste
        # habría leído `pre` como cabeza y su fila la supersedería: bifurcación.
        otro.execute(
            "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, "
            "supersedes_dictamen_id, signature_kind, band, created_at) "
            "VALUES (%s,%s,'inhabit_monitor','{}'::jsonb,%s,%s,'confirmation','amarillo', "
            "clock_timestamp())",
            (scenario.tenant, ids["incident"], str(uuid.uuid4()), pre["dictamen_id"]),
        )
        otro.commit()
        hilo.join(timeout=20)
        assert not hilo.is_alive(), "el worker no terminó"
        worker.close()
    finally:
        otro.close()

    cadena = _cadena(scenario, ids["incident"])
    sucedidos = [f["supersedes_dictamen_id"] for f in cadena if f["supersedes_dictamen_id"]]
    assert len(sucedidos) == len(set(sucedidos)), "dos filas suceden a la misma: bifurcada"
    assert cadena[-1]["band"] == "rojo"
    assert cadena[-1]["supersedes_dictamen_id"] == cadena[-2]["dictamen_id"]
    # [F3·r3] Una CONFIRMACIÓN (no una firma de inspector): sobre la del inspector el
    # daño anterior a su firma ya no sube (la firma humana no se deshace sola); sobre
    # una confirmación, un daño ROJO sí, porque la API no deja confirmar con uno.
    assert cadena[-2]["signature_kind"] == "confirmation"


def test_el_backfill_no_reescribe_un_pico_que_ya_tiene(scenario: _Scenario) -> None:
    """`pga_g` es `real` y `max_pga_g` `numeric`: 0.01 en real, guardado en numeric
    con 15 dígitos, quedaba MENOR que el mismo float8 y el `UPDATE` se repetía en
    cada pasada (y con él el NOTIFY al hub y un bloqueo de fila del incidente)."""
    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)

    def xmin() -> str:
        return scenario.conn.execute(
            "SELECT xmin::text AS x FROM incidents WHERE incident_id = %s", (ids["incident"],)
        ).fetchone()["x"]

    antes = xmin()
    scenario.conn.commit()
    _run(scenario.conn, NOW + timedelta(seconds=5))
    assert xmin() == antes, "el backfill reescribió el mismo pico"


# ------------------------------------- los daños se leen DENTRO del lock (F3·r2)


def test_un_dano_que_entra_tras_la_seleccion_impide_el_verde_del_sistema(
    scenario: _Scenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El reporte entra ENTRE la consulta de candidatos y el ``FOR UPDATE``: la
    decisión tiene que leerlo, no el conteo viejo de la selección."""
    from takab_api.dictamen import service

    ids = _caso(scenario, pga=0.01)
    _run(scenario.conn, NOW)
    original = service._dictaminar

    def intercalado(conn, settings, row, now):  # noqa: ANN001, ANN202
        otro = psycopg.connect(_dsn(), autocommit=True)
        try:
            otro.execute(
                "INSERT INTO damage_reports (tenant_id, incident_id, site_id, user_sub, "
                "categories) VALUES (%s,%s,%s,%s,%s::jsonb)",
                (
                    scenario.tenant,
                    ids["incident"],
                    ids["site"],
                    str(uuid.uuid4()),
                    json.dumps([{"key": "structural", "severity": "high"}]),
                ),
            )
        finally:
            otro.close()
        return original(conn, settings, row, now)

    monkeypatch.setattr(service, "_dictaminar", intercalado)
    _run(scenario.conn, BASE + timedelta(seconds=GRACIA + 1))
    cadena = _cadena(scenario, ids["incident"])
    assert all(f["signature_kind"] != "system" for f in cadena)
    assert cadena[-1]["band"] == "rojo" and cadena[-1]["signed_by"] is None


def test_una_confirmacion_posterior_al_dano_la_supera_un_ROJO(scenario: _Scenario) -> None:
    """AMARILLO → daño estructural → confirmación (más nueva que el daño) antes de la
    siguiente pasada: la pasada tiene que ver el daño igualmente y subir a ROJO."""
    ids = _caso(scenario, pga=0.07)
    _run(scenario.conn, NOW)
    [pre] = _cadena(scenario, ids["incident"])
    assert pre["band"] == "amarillo"
    _dano(scenario, ids, "structural")
    scenario.conn.execute(
        "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by, "
        "supersedes_dictamen_id, signature_kind, band, created_at) "
        "VALUES (%s,%s,'inhabit_monitor','{}'::jsonb,%s,%s,'confirmation','amarillo', "
        "clock_timestamp())",
        (scenario.tenant, ids["incident"], str(uuid.uuid4()), pre["dictamen_id"]),
    )
    scenario.conn.commit()
    assert len(_run(scenario.conn, BASE + timedelta(hours=1))) == 1
    cadena = _cadena(scenario, ids["incident"])
    assert cadena[-1]["band"] == "rojo" and cadena[-1]["signed_by"] is None
    assert cadena[-2]["signature_kind"] == "confirmation"
    # idempotente: la misma evidencia no vuelve a subir
    assert _run(scenario.conn, BASE + timedelta(hours=2)) == []
