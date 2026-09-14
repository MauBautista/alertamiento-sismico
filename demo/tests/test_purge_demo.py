"""[T-7.10] La purga operativa: qué se lleva, qué NO, y que se pueda repetir.

Un script que borra en el entorno desplegado no se prueba mirándolo. Aquí se
ejecuta ENTERO contra una base efímera —clonada de la de tests— y se comprueba lo
que queda, lo que no, y que una segunda pasada no cambie nada.

Las tres guardas que importan, por orden de lo que costaría equivocarse:

1. **`audit_log` y `actuation_records` sobreviven.** Regla de oro 11: la bitácora
   de quién ordenó qué y la del gabinete no se podan. Si esta prueba se pone roja
   por ahí, el script está rompiendo un invariante del producto, no un test.
2. **La flota sobrevive.** Esta purga NO es la del 2026-07-10, que sí se llevó la
   flota sim. Aquí borrar un sitio dejaría al gabinete publicando contra un
   registro que ya no existe.
3. **Toda tabla del esquema está clasificada.** El script lleva dos listas y un
   censo que revienta si aparece una tercera categoría: «me la salté». Sin eso,
   una tabla nueva se conservaría por omisión y nadie se enteraría.
"""

from __future__ import annotations

import os
import re
import subprocess
import uuid
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[2]
_SCRIPT = _RAIZ / "db/maintenance/2026-09-14_purge_operativa_demo.sql"

_HOST, _PORT = "127.0.0.1", os.environ.get("TAKAB_PURGE_PORT", "5433")
_USUARIO, _CLAVE = "takab", "takab_dev"


# --------------------------------------------------------------------- estático
#
# Estas tres no necesitan base: leen el script. Son las que cazan el error de
# listar una tabla y olvidarse de tocarla, que no se ve leyendo por encima.


def _listas() -> tuple[set[str], set[str]]:
    texto = _SCRIPT.read_text(encoding="utf-8")

    def _bloque(nombre: str) -> set[str]:
        ini = texto.index(f"INSERT INTO {nombre} (t) VALUES")
        fin = texto.index(";", ini)
        return set(re.findall(r"\('(\w+)'\)", texto[ini:fin]))

    return _bloque("_purgar"), _bloque("_conservar")


def _tablas_borradas() -> set[str]:
    return set(re.findall(r"^DELETE FROM (\w+);", _SCRIPT.read_text(encoding="utf-8"), re.M))


def test_todo_lo_listado_para_purgar_SE_BORRA() -> None:
    """Listar una tabla y no tocarla deja el papel diciendo que se purgó."""
    purgar, _ = _listas()
    assert purgar - _tablas_borradas() == set(), (
        f"listadas en `_purgar` y sin `DELETE`: {sorted(purgar - _tablas_borradas())}"
    )


def test_NINGUN_delete_toca_lo_que_se_conserva() -> None:
    """La dirección cara del error. Aquí caerían `audit_log` o la flota."""
    _, conservar = _listas()
    assert _tablas_borradas() & conservar == set(), (
        f"el script borra tablas declaradas como conservadas: "
        f"{sorted(_tablas_borradas() & conservar)}"
    )


def test_las_bitacoras_y_la_flota_estan_en_la_lista_de_CONSERVAR() -> None:
    """Explícito, por si alguien reorganiza las listas: regla de oro 11 y flota."""
    _, conservar = _listas()
    for tabla in (
        "audit_log",
        "actuation_records",
        "privacy_consents",
        "privacy_notices",
        "privacy_erasures",
        "tenants",
        "sites",
        "gateways",
        "sensors",
        "user_profiles",
        "reference_earthquakes",
        "gateway_catalog_state",
    ):
        assert tabla in conservar, f"`{tabla}` dejó de estar protegida"


def test_las_dos_listas_no_se_solapan() -> None:
    purgar, conservar = _listas()
    assert purgar & conservar == set(), sorted(purgar & conservar)


# ----------------------------------------------------------------- sobre la base


def _psql(base: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "psql",
            f"postgresql://{_USUARIO}:{_CLAVE}@{_HOST}:{_PORT}/{base}",
            "-v",
            "ON_ERROR_STOP=1",
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )


def _cuenta(base: str, tabla: str) -> int:
    r = _psql(base, "-Atc", f"SELECT count(*) FROM {tabla}")
    assert r.returncode == 0, r.stderr
    return int(r.stdout.strip())


@pytest.fixture(scope="module")
def efimera():
    """Base efímera con el esquema REAL, migrada desde cero.

    No se clona de la base de tests: la propia sesión de pytest la tiene abierta
    y Postgres se niega a usar como plantilla una base con sesiones vivas
    («source database is being accessed by other users»). Migrar desde vacío
    cuesta unos segundos más y no depende de quién esté conectado — que es
    justamente lo que se quiere de una prueba que ejecuta un borrado.
    """
    nombre = f"takab_purga_{uuid.uuid4().hex[:8]}"
    creada = _psql("postgres", "-c", f"CREATE DATABASE {nombre}")
    if creada.returncode != 0:  # pragma: no cover - sin Postgres no hay nada que probar
        pytest.skip(f"no se pudo crear la base efímera: {creada.stderr.strip()[:160]}")
    try:
        migrada = subprocess.run(
            ["uv", "run", "python", "-m", "alembic", "upgrade", "head"],
            cwd=_RAIZ / "api",
            capture_output=True,
            text=True,
            timeout=900,
            env={
                **os.environ,
                "DATABASE_URL": (
                    f"postgresql+psycopg://{_USUARIO}:{_CLAVE}@{_HOST}:{_PORT}/{nombre}"
                ),
            },
        )
        assert migrada.returncode == 0, migrada.stderr[-2000:]
        yield nombre
    finally:
        _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)")


def _sembrar(base: str) -> None:
    """Un incidente con su familia y algo de telemetría, más lo que se conserva."""
    sql = """
    INSERT INTO tenants (tenant_id, code, name) VALUES
      ('d0000000-0000-0000-0000-000000000001','tenant-purga','Purga') ON CONFLICT DO NOTHING;
    INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES
      ('d1000000-0000-0000-0000-00000000p001'::uuid,'d0000000-0000-0000-0000-000000000001',
       'purga-1','Sitio purga', ST_SetSRID(ST_MakePoint(-98.2,19.0),4326)::geography)
      ON CONFLICT DO NOTHING;
    INSERT INTO incidents
      (event_uuid, tenant_id, site_id, opened_at, severity, state, trigger, summary)
      SELECT gen_random_uuid(),'d0000000-0000-0000-0000-000000000001',
             'd1000000-0000-0000-0000-00000000p001'::uuid, now(),
             'warning','open','sasmex','{}'::jsonb
      FROM generate_series(1,3);
    INSERT INTO audit_log (tenant_id, actor, verb, object, meta) VALUES
      ('d0000000-0000-0000-0000-000000000001','user:test','login','x','{}'::jsonb);
    """
    r = _psql(base, "-c", sql.replace("p001", "0001"))
    assert r.returncode == 0, r.stderr


def test_la_purga_se_lleva_lo_operativo_y_DEJA_la_bitacora(efimera: str) -> None:
    _sembrar(efimera)
    antes = {t: _cuenta(efimera, t) for t in ("incidents", "audit_log", "sites", "tenants")}
    assert antes["incidents"] >= 3, "la siembra no dejó incidentes que purgar"

    r = _psql(efimera, "-f", str(_SCRIPT))
    assert r.returncode == 0, r.stderr[-2000:]

    assert _cuenta(efimera, "incidents") == 0
    assert _cuenta(efimera, "waveform_features_1s") == 0
    assert _cuenta(efimera, "rule_evaluations") == 0
    # Regla de oro 11: la bitácora no se poda, y encima CRECE con la fila de la purga.
    assert _cuenta(efimera, "audit_log") == antes["audit_log"] + 1
    # Y la flota sigue en pie: esta purga no es la del 2026-07-10.
    assert _cuenta(efimera, "sites") == antes["sites"]
    assert _cuenta(efimera, "tenants") == antes["tenants"]


def test_repetirla_no_cambia_NADA_salvo_su_propia_huella(efimera: str) -> None:
    """Idempotencia: la segunda pasada afecta a 0 filas. La única que crece es la
    fila de auditoría de la purga, y el runbook dice ejecutarla una vez."""
    _sembrar(efimera)
    assert _psql(efimera, "-f", str(_SCRIPT)).returncode == 0
    tras_una = {t: _cuenta(efimera, t) for t in ("incidents", "sites", "audit_log")}

    r = _psql(efimera, "-f", str(_SCRIPT))
    assert r.returncode == 0, r.stderr[-2000:]

    assert _cuenta(efimera, "incidents") == tras_una["incidents"] == 0
    assert _cuenta(efimera, "sites") == tras_una["sites"]
    assert _cuenta(efimera, "audit_log") == tras_una["audit_log"] + 1


def test_una_tabla_SIN_CLASIFICAR_revienta_la_purga(efimera: str) -> None:
    """El censo, que es lo que impide que la próxima tabla se salve por omisión.

    Se crea una tabla que no está en ninguna de las dos listas y se comprueba que
    el script se niega **antes de borrar nada**: los incidentes siguen ahí.
    """
    _sembrar(efimera)
    antes = _cuenta(efimera, "incidents")
    assert _psql(efimera, "-c", "CREATE TABLE tabla_nueva_sin_clasificar (x int)").returncode == 0

    r = _psql(efimera, "-f", str(_SCRIPT))

    assert r.returncode != 0, "el censo dejó pasar una tabla sin clasificar"
    assert "tabla_nueva_sin_clasificar" in (r.stderr + r.stdout), r.stderr[-800:]
    assert _cuenta(efimera, "incidents") == antes, (
        "el script abortó DESPUÉS de borrar: la transacción no protegió nada"
    )
    # La base es de módulo: se deja como se encontró.
    assert _psql(efimera, "-c", "DROP TABLE tabla_nueva_sin_clasificar").returncode == 0
