"""T-2.78.a · La credencial de guardia: se enseña una vez, se revoca en el acto.

Lo que se mide aquí no es "el CRUD funciona": es que **el secreto no vive en la
base** y que **revocar surte efecto de verdad**, ejercido contra la misma función
que usa la superficie pública. Una revocación que no se comprueba contra
`app_ops_alert_ack` es una columna con una fecha.
"""

from __future__ import annotations

import os

import psycopg
import pytest

from takab_api.ops import oncall
from takab_api.ops.alerts import hash_ack_token


def _dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://takab:takab_dev@localhost:5433/takab"
    )
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def conn():
    with psycopg.connect(_dsn(), row_factory=psycopg.rows.dict_row) as c:
        c.execute("TRUNCATE ops_alert_notices, ops_oncall_contacts CASCADE")
        c.commit()
        yield c
        c.execute("TRUNCATE ops_alert_notices, ops_oncall_contacts CASCADE")
        c.commit()


def _acusa(conn: psycopg.Connection, secreto: str) -> bool:
    """¿Esa credencial la reconoce la MISMA función que usa el endpoint?"""
    fila = conn.execute(
        "SELECT o_token_ok FROM app_ops_alert_ack(%s)", (hash_ack_token(secreto),)
    ).fetchone()
    conn.rollback()
    return bool(fila["o_token_ok"])


def test_el_secreto_no_queda_en_la_base(conn) -> None:
    """Se enseña UNA vez, al acuñarlo. Quien lea la tabla entera no puede acusar
    en nombre de nadie."""
    _id, secreto = oncall.issue(conn, label="Guardia primaria", days=90)

    fila = conn.execute("SELECT label, token_hash FROM ops_oncall_contacts").fetchone()
    assert fila["token_hash"] == hash_ack_token(secreto)
    assert secreto not in fila["token_hash"]
    assert secreto not in fila["label"]
    # Y no hay ninguna otra columna donde se haya colado.
    volcado = conn.execute("SELECT to_jsonb(c)::text AS t FROM ops_oncall_contacts c").fetchone()[
        "t"
    ]
    assert secreto not in volcado


def test_la_credencial_recien_acuñada_SI_vale(conn) -> None:
    """No-vacuidad de las dos de abajo: si acuñar no sirviera, 'revocada no vale'
    y 'caducada no vale' saldrían verdes midiendo la nada."""
    _id, secreto = oncall.issue(conn, label="Guardia primaria", days=90)
    assert _acusa(conn, secreto) is True


def test_revocar_surte_efecto_EN_LA_FUNCION_del_endpoint(conn) -> None:
    contact_id, secreto = oncall.issue(conn, label="El que se fue", days=90)
    assert _acusa(conn, secreto) is True

    assert oncall.revoke(conn, contact_id=contact_id) == "El que se fue"
    assert _acusa(conn, secreto) is False

    # Revocar dos veces es un no-op, igual que revocar algo que no existe: una
    # credencial no se "des-revoca" ni se puede sondear por la respuesta.
    assert oncall.revoke(conn, contact_id=contact_id) is None
    assert oncall.revoke(conn, contact_id="00000000-0000-0000-0000-000000000000") is None


def test_una_credencial_CADUCADA_deja_de_valer_sola(conn) -> None:
    """La caducidad es lo que impide que la lista de guardia de hace dos años
    siga pudiendo acusar sin que nadie haya hecho nada."""
    _id, secreto = oncall.issue(conn, label="La de hace un año", days=1)
    conn.execute("UPDATE ops_oncall_contacts SET expires_at = now() - interval '1 day'")
    assert _acusa(conn, secreto) is False


def test_dos_credenciales_no_se_parecen(conn) -> None:
    _a, uno = oncall.issue(conn, label="A", days=30)
    _b, otro = oncall.issue(conn, label="B", days=30)
    assert uno != otro
    assert _acusa(conn, uno) and _acusa(conn, otro)


def test_listar_dice_quien_sigue_vigente(conn) -> None:
    vivo, _s1 = oncall.issue(conn, label="Vigente", days=30)
    muerto, _s2 = oncall.issue(conn, label="Revocada", days=30)
    oncall.revoke(conn, contact_id=muerto)

    por_id = {str(f["contact_id"]): f for f in oncall.listar(conn)}
    assert por_id[vivo]["vigente"] is True
    assert por_id[muerto]["vigente"] is False
    assert por_id[muerto]["revoked_at"] is not None
