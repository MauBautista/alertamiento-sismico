"""[T-9.35 · D-43] La baja de sensores fantasma toca SOLO fantasmas, y deja huella.

`infra/scripts/retira_sensores_fantasma.sh` entra a la base de la NUBE con el
superusuario y escribe. Lo que lo hace seguro está en su SQL, así que aquí se corre
ESE SQL —extraído del guion, no una copia— con `psql` contra la base de pruebas:

* sin `--aplicar` no cambia nada (ROLLBACK);
* con `--aplicar` retira el fantasma y SÓLO el fantasma: no el calibrado, no el que
  tiene una fila de features, no el de un sitio que no se nombró;
* cada baja deja su fila `sensor_retire` en `audit_log` con quién y por qué;
* un código de sitio repetido entre tenants, sin `--tenant`, aborta sin tocar nada.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

REPO = Path(__file__).resolve().parents[2]
GUION = REPO / "infra" / "scripts" / "retira_sensores_fantasma.sh"
DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@localhost:5433/takab"


def _dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL).replace(
        "postgresql+psycopg://", "postgresql://"
    )


def _sql() -> str:
    m = re.search(r"<<'SQL'\n(.*?)\nSQL\n", GUION.read_text(), re.S)
    assert m, "no encontré el heredoc SQL del guion"
    return m.group(1)


def _corre(sitios: str, *, aplicar: bool, tenant: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "psql", _dsn(), "-v", "ON_ERROR_STOP=1", "-X", "-q",
            "-v", f"sitios={sitios}", "-v", f"tenant={tenant}",
            "-v", "actor=ops:test@pytest", "-v", f"aplicar={1 if aplicar else 0}",
        ],
        input=_sql(), text=True, capture_output=True, check=False, timeout=60,
    )  # fmt: skip


# ------------------------------------------------------------------ guardas del texto


def test_sin_sitios_no_corre() -> None:
    r = subprocess.run(["bash", str(GUION)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 2
    assert "no hay «todos»" in r.stderr


def test_por_defecto_ROLLBACK_y_la_escritura_solo_con_aplicar() -> None:
    sql = _sql()
    assert "\\if :aplicar" in sql and "COMMIT;" in sql and "ROLLBACK;" in sql
    assert sql.index("\\if :aplicar") < sql.index("COMMIT;")
    assert "APLICAR=0" in GUION.read_text()


def test_reutiliza_el_tunel_de_siempre() -> None:
    assert "infra/scripts/lib/tunel.sh" in GUION.read_text()


# ------------------------------------------------------------------ el SQL de verdad


@pytest.fixture
def escena():
    if shutil.which("psql") is None:
        pytest.skip("sin cliente psql en esta máquina")
    conn = psycopg.connect(_dsn(), autocommit=True)
    sufijo = uuid.uuid4().hex[:8]
    tenant, otro_tenant = str(uuid.uuid4()), str(uuid.uuid4())
    sitio, otro_sitio = str(uuid.uuid4()), str(uuid.uuid4())
    codigo, otro_codigo = f"fant-{sufijo}", f"fant-otro-{sufijo}"
    conn.execute(
        "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Fantasmas'),(%s,%s,'Otro')",
        (tenant, f"t-{sufijo}", otro_tenant, f"t2-{sufijo}"),
    )
    for sid, tid, code in ((sitio, tenant, codigo), (otro_sitio, tenant, otro_codigo)):
        conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES (%s,%s,%s,'S',"
            " ST_SetSRID(ST_MakePoint(-98.2,19.0),4326)::geography)",
            (sid, tid, code),
        )
    sensores = {}
    for nombre, site, cal, status in (
        ("fantasma", sitio, None, "active"),
        ("calibrado", sitio, "StationXML AM.TEST", "active"),
        ("con_datos", sitio, None, "active"),
        ("retirado", sitio, None, "retired"),
        ("fantasma_ajeno", otro_sitio, None, "active"),
    ):
        sensores[nombre] = conn.execute(
            "INSERT INTO sensors (tenant_id, site_id, kind, model, serial, status,"
            " calibration_source) VALUES (%s,%s,'structural','RS4D',%s,%s,%s) RETURNING sensor_id",
            (tenant, site, f"{nombre}-{sufijo}", status, cal),
        ).fetchone()[0]
    conn.execute(
        "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel, pga_g)"
        " VALUES (%s,%s,%s,%s,'ENZ',0.001)",
        (datetime(2026, 9, 1, tzinfo=UTC), tenant, sitio, sensores["con_datos"]),
    )
    try:
        yield conn, codigo, otro_codigo, sensores
    finally:
        conn.execute("SET session_replication_role = 'replica'")
        conn.execute("DELETE FROM waveform_features_1s WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM audit_log WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sensors WHERE tenant_id = %s", (tenant,))
        conn.execute("DELETE FROM sites WHERE tenant_id IN (%s,%s)", (tenant, otro_tenant))
        conn.execute("DELETE FROM tenants WHERE tenant_id IN (%s,%s)", (tenant, otro_tenant))
        conn.execute("SET session_replication_role = 'origin'")
        conn.close()


def _estado(conn, sensores: dict) -> dict[str, str]:
    return {
        n: conn.execute("SELECT status FROM sensors WHERE sensor_id = %s", (s,)).fetchone()[0]
        for n, s in sensores.items()
    }


def _bajas(conn, sensores: dict) -> list[tuple]:
    ids = [f"sensor:{s}" for s in sensores.values()]
    return conn.execute(
        "SELECT object, actor, meta->>'motivo' FROM audit_log"
        " WHERE verb = 'sensor_retire' AND object = ANY(%s)",
        (ids,),
    ).fetchall()


def test_sin_aplicar_no_cambia_nada(escena) -> None:
    conn, codigo, _, sensores = escena
    antes = _estado(conn, sensores)
    r = _corre(codigo, aplicar=False)
    assert r.returncode == 0, r.stderr
    assert "fantasma-" in r.stdout and "ROLLBACK" in r.stdout
    assert _estado(conn, sensores) == antes
    assert _bajas(conn, sensores) == []


def test_con_aplicar_retira_SOLO_el_fantasma_del_sitio_nombrado(escena) -> None:
    conn, codigo, _, sensores = escena
    r = _corre(codigo, aplicar=True)
    assert r.returncode == 0, r.stderr
    assert _estado(conn, sensores) == {
        "fantasma": "retired",
        "calibrado": "active",
        "con_datos": "active",
        "retirado": "retired",
        "fantasma_ajeno": "active",
    }
    [(objeto, actor, motivo)] = _bajas(conn, sensores)
    assert objeto == f"sensor:{sensores['fantasma']}"
    assert actor == "ops:test@pytest"
    assert "fantasma" in motivo


def test_repetirlo_no_hace_nada_mas(escena) -> None:
    conn, codigo, _, sensores = escena
    assert _corre(codigo, aplicar=True).returncode == 0
    assert _corre(codigo, aplicar=True).returncode == 0
    assert len(_bajas(conn, sensores)) == 1


def test_un_codigo_repetido_entre_tenants_sin_tenant_aborta(escena) -> None:
    conn, codigo, _, sensores = escena
    # Otro cliente con un sitio del MISMO código.
    t2 = conn.execute(
        "SELECT tenant_id FROM tenants WHERE code LIKE 't2-%%' ORDER BY code DESC LIMIT 1"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO sites (tenant_id, code, name, geom) VALUES (%s,%s,'Duplicado',"
        " ST_SetSRID(ST_MakePoint(-99.1,19.4),4326)::geography)",
        (t2, codigo),
    )
    antes = _estado(conn, sensores)
    r = _corre(codigo, aplicar=True)
    assert r.returncode != 0
    assert "acota con --tenant" in r.stderr
    assert _estado(conn, sensores) == antes
