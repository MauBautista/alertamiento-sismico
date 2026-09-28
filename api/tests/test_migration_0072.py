"""T-9.20 · D-42 — la 0072 canoniza la configuración VIVA de roles (solo DML).

``push_tokens.role`` y ``user_zone_assignments.role`` deciden hoy a quién suena un
push y quién sale en el directorio del inmueble: son configuración viva, no
historia, así que pasan del rol viejo a su canónico. La historia (bitácora,
acciones, dictámenes) NO se toca, y la 0072 tampoco la nombra.

Idempotente (invariante 0002+): correrla dos veces deja lo mismo.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import psycopg

from conftest import SITE_A, TENANT_A, reset, use

_RUTA = Path(__file__).resolve().parents[1] / "migrations/versions/0072_roles_canonicos.py"


def _mig():
    spec = importlib.util.spec_from_file_location("m0072", _RUTA)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _correr(conn: psycopg.Connection) -> None:
    """Como el DUEÑO de las tablas (``takab_migrator``, el usuario de Alembic), NO como
    superusuario: las dos llevan ``FORCE ROW LEVEL SECURITY`` y un ``UPDATE`` sin
    contexto de app actualiza CERO filas sin quejarse (lo midió la 0050). Correrlo
    como superusuario aprobaría la versión rota."""
    use(conn, "takab_migrator")
    for sentencia in _mig().CANONIZAR:
        conn.execute(sentencia)
    reset(conn)


def _sembrar(conn: psycopg.Connection) -> dict[str, str]:
    conn.execute("RESET ROLE")
    subs = {r: str(uuid.uuid4()) for r in ("soc_operator", "security_guard", "building_admin")}
    subs["inspector"] = str(uuid.uuid4())
    subs["occupant"] = str(uuid.uuid4())
    for rol, sub in subs.items():
        conn.execute(
            "INSERT INTO push_tokens (tenant_id, user_sub, platform, token, site_id, role) "
            "VALUES (%s, %s, 'android', %s, %s, %s)",
            (TENANT_A, sub, f"tok-{sub}", SITE_A, rol),
        )
        conn.execute(
            "INSERT INTO user_zone_assignments (user_id, tenant_id, site_id, role) "
            "VALUES (%s, %s, %s, %s)",
            (sub, TENANT_A, SITE_A, rol),
        )
    # Una fila anterior a la 0071, sin rol: se queda en NULL (no se inventa nada).
    conn.execute(
        "INSERT INTO push_tokens (tenant_id, user_sub, platform, token, site_id) "
        "VALUES (%s, %s, 'ios', 'tok-sin-rol', %s)",
        (TENANT_A, str(uuid.uuid4()), SITE_A),
    )
    return subs


def _roles(conn: psycopg.Connection, subs: dict[str, str]) -> dict[str, tuple[str, str]]:
    out = {}
    for rol, sub in subs.items():
        pt = conn.execute("SELECT role FROM push_tokens WHERE user_sub = %s", (sub,)).fetchone()
        za = conn.execute(
            "SELECT role FROM user_zone_assignments WHERE user_id = %s", (sub,)
        ).fetchone()
        out[rol] = (pt[0], za[0])
    return out


ESPERADO = {
    "soc_operator": ("tenant_admin", "tenant_admin"),
    "security_guard": ("brigadista", "brigadista"),
    "building_admin": ("brigadista", "brigadista"),
    "inspector": ("inspector", "inspector"),
    "occupant": ("occupant", "occupant"),
}


def test_0072_canoniza_push_tokens_y_asignaciones(seeded: psycopg.Connection) -> None:
    subs = _sembrar(seeded)
    _correr(seeded)
    assert _roles(seeded, subs) == ESPERADO
    sin_rol = seeded.execute("SELECT role FROM push_tokens WHERE token = 'tok-sin-rol'").fetchone()
    assert sin_rol == (None,)


def test_0072_es_idempotente(seeded: psycopg.Connection) -> None:
    subs = _sembrar(seeded)
    _correr(seeded)
    primera = _roles(seeded, subs)
    _correr(seeded)
    assert _roles(seeded, subs) == primera == ESPERADO


def test_0072_no_toca_la_historia() -> None:
    """Solo las dos tablas vivas; ninguna sentencia nombra bitácora ni acciones."""
    texto = " ".join(_mig().CANONIZAR).lower()
    for tabla in ("audit_log", "incident_actions", "dictamens", "damage_reports"):
        assert tabla not in texto
    for s in _mig().CANONIZAR:
        cabeza = s.lstrip().upper()
        assert cabeza.startswith("UPDATE") or cabeza.startswith("SELECT SET_CONFIG"), s


def test_0072_deja_el_contexto_de_app_como_lo_encontro(seeded: psycopg.Connection) -> None:
    """Declara ``app.role`` interno para pasar la RLS y lo devuelve a vacío: si Alembic
    corre varias migraciones en una transacción, la siguiente no hereda un superadmin."""
    _correr(seeded)
    assert seeded.execute("SELECT current_setting('app.role', true)").fetchone() in (
        ("",),
        (None,),
    )


def test_0072_el_mapeo_es_el_de_D42() -> None:
    """Copia congelada en la migración (T-9.81 quitará los alias del código, y una
    migración no puede cambiar de significado cuando cambia la app)."""
    from takab_api.auth.roles import ALIAS_HEREDADOS

    assert _mig().MAPEO == ALIAS_HEREDADOS
