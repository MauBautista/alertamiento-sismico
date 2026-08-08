"""Aislamiento cross-tenant de ``compliance_labels`` (T-2.82 · regla de oro 5).

La tabla llega del schema con ``ENABLE`` + ``FORCE ROW LEVEL SECURITY`` y **dos
políticas**: ``cl_read`` (tenant propio ∪ interno TAKAB ∪ rama gov) y ``cl_admin``
(escritura SOLO para identidades internas TAKAB). Se prueba conectando como
``takab_app`` y como ``takab_migrator`` —el DUEÑO— porque ``FORCE`` es lo único que
sujeta al dueño, y ninguno de los dos protege del superusuario (``BYPASSRLS`` va por
delante): leer una bandera no probaría nada.

El hallazgo que estos tests dejan escrito: ``cl_admin`` **no filtra por tenant**
(``USING (app_is_takab_internal())`` a secas). La base no detiene a un superadmin que
escriba en el cliente equivocado — el ``tenant_id`` explícito de la ruta es la única
cerradura, exactamente el patrón que ``routers/_common.INTERNAL_ROLES`` documenta.
"""

from __future__ import annotations

import json

import psycopg
import pytest

from conftest import GOV_AGENCY, TENANT_A, TENANT_B, TENANT_G, use

_DOC_A = json.dumps(
    {
        "version": 1,
        "items": [
            {"key": "internal_protocol", "claim": "Protocolo A", "reference": "Manual A, §1"}
        ],
    }
)
_DOC_B = json.dumps(
    {
        "version": 1,
        "items": [
            {"key": "internal_protocol", "claim": "Protocolo B", "reference": "Manual B, §1"}
        ],
    }
)
_DOC_G = json.dumps(
    {
        "version": 1,
        "items": [
            {"key": "internal_protocol", "claim": "Protocolo G", "reference": "Manual G, §1"}
        ],
    }
)


@pytest.fixture
def labelled(seeded: psycopg.Connection) -> psycopg.Connection:
    """Una fila de etiquetas por tenant, sembrada como superusuario (bypassa RLS)."""
    seeded.execute("RESET ROLE")
    for tenant, doc in ((TENANT_A, _DOC_A), (TENANT_B, _DOC_B), (TENANT_G, _DOC_G)):
        seeded.execute(
            "INSERT INTO compliance_labels (tenant_id, labels) VALUES (%s, %s::jsonb)",
            (tenant, doc),
        )
    return seeded


def _claims(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute("SELECT labels->'items'->0->>'claim' FROM compliance_labels").fetchall()
    return {r[0] for r in rows}


# --- Lectura ------------------------------------------------------------------


@pytest.mark.parametrize("app_role", ["tenant_admin", "soc_operator", "inspector"])
def test_un_rol_de_cliente_solo_ve_las_etiquetas_de_su_tenant(
    labelled: psycopg.Connection, app_role: str
) -> None:
    use(labelled, "takab_app", tenant=TENANT_A, app_role=app_role)
    assert _claims(labelled) == {"Protocolo A"}


def test_el_vecino_ve_las_suyas_y_no_las_del_otro(labelled: psycopg.Connection) -> None:
    """Dos tenants, dos respuestas distintas: sin este segundo caso, el test de arriba
    pasaría también con una política que devolviera SIEMPRE la fila del tenant A."""
    use(labelled, "takab_app", tenant=TENANT_B, app_role="tenant_admin")
    assert _claims(labelled) == {"Protocolo B"}


def test_el_cliente_no_puede_leer_por_id_las_etiquetas_ajenas(
    labelled: psycopg.Connection,
) -> None:
    use(labelled, "takab_app", tenant=TENANT_B, app_role="tenant_admin")
    n = labelled.execute(
        "SELECT count(*) FROM compliance_labels WHERE tenant_id = %s", (TENANT_A,)
    ).fetchone()
    assert n[0] == 0, "el tenant B no puede leer las afirmaciones normativas del tenant A"


@pytest.mark.parametrize("app_role", ["takab_superadmin", "takab_support"])
def test_los_internos_takab_ven_las_de_todos(labelled: psycopg.Connection, app_role: str) -> None:
    use(labelled, "takab_app", tenant=TENANT_A, app_role=app_role)
    assert _claims(labelled) == {"Protocolo A", "Protocolo B", "Protocolo G"}


def test_gov_ve_las_del_tenant_compartido_y_solo_esas(labelled: psycopg.Connection) -> None:
    """``cl_read`` incluye la rama ``app_gov_can_see``: protección civil lee el marco
    declarado del cliente que se abrió a gobierno, y de ningún otro.

    El gov_operator entra con el tenant de SU agencia (que no es cliente): así la
    visibilidad depende solo de la rama gov, no de ``tenant_id = app_tenant_id()``.
    """
    use(labelled, "takab_app", tenant=GOV_AGENCY, app_role="gov_operator")
    assert _claims(labelled) == {"Protocolo G"}


def test_el_dueno_de_la_tabla_tambien_queda_aislado(labelled: psycopg.Connection) -> None:
    """``takab_migrator`` es OWNER: sin ``FORCE`` saltaría la RLS entera."""
    use(labelled, "takab_migrator", tenant=TENANT_B, app_role="tenant_admin")
    assert _claims(labelled) == {"Protocolo B"}


# --- Escritura ----------------------------------------------------------------


def _try_update(conn: psycopg.Connection, tenant: str, doc: str) -> int:
    return conn.execute(
        "UPDATE compliance_labels SET labels = %s::jsonb WHERE tenant_id = %s", (doc, tenant)
    ).rowcount


@pytest.mark.parametrize("app_role", ["tenant_admin", "soc_operator", "inspector", "gov_operator"])
def test_ningun_rol_de_cliente_reescribe_sus_propias_etiquetas(
    labelled: psycopg.Connection, app_role: str
) -> None:
    """Escritura INTERNA hasta ratificar el marco citable (comentario del DDL ·
    GATE-LEGAL). Ni siquiera el dueño del tenant redacta su propia afirmación.

    OJO — el UPDATE **no lanza**: ninguna política lo alcanza, así que la fila no es
    visible *para escribir* y Postgres actualiza 0 filas EN SILENCIO. Un
    ``pytest.raises`` aquí sería la aserción fuerte que no caza nada; lo que hay que
    exigir es que no se movió nada y que el texto guardado sigue siendo el mismo.
    """
    use(labelled, "takab_app", tenant=TENANT_A, app_role=app_role)
    assert _try_update(labelled, TENANT_A, _DOC_B) == 0
    use(labelled, "takab_app", tenant=TENANT_A, app_role="takab_superadmin")
    assert _claims(labelled) == {"Protocolo A", "Protocolo B", "Protocolo G"}


@pytest.mark.parametrize("app_role", ["tenant_admin", "soc_operator"])
def test_un_rol_de_cliente_tampoco_estrena_su_fila(
    seeded: psycopg.Connection, app_role: str
) -> None:
    """Sin fila previa (el estado real de hoy: nadie carga la tabla), el INSERT
    tampoco pasa: ``cl_admin`` es la ÚNICA política con ``WITH CHECK``."""
    use(seeded, "takab_app", tenant=TENANT_A, app_role=app_role)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(
            "INSERT INTO compliance_labels (tenant_id, labels) VALUES (%s, '{}'::jsonb)",
            (TENANT_A,),
        )


@pytest.mark.parametrize("app_role", ["takab_superadmin", "takab_support"])
def test_los_internos_takab_si_escriben(labelled: psycopg.Connection, app_role: str) -> None:
    use(labelled, "takab_app", tenant=TENANT_A, app_role=app_role)
    labelled.execute(
        "UPDATE compliance_labels SET labels = %s::jsonb WHERE tenant_id = %s",
        (_DOC_B, TENANT_A),
    )
    assert _claims(labelled) == {"Protocolo B", "Protocolo G"}


def test_cl_admin_NO_acota_por_tenant_y_por_eso_la_ruta_debe_nombrarlo(
    labelled: psycopg.Connection,
) -> None:
    """Hallazgo, no deseo: la política de escritura es ``app_is_takab_internal()`` a
    secas. Un interno con ``app.tenant_id`` del cliente A escribe la fila del cliente B
    sin que la base se queje. La API tiene que tomar el tenant de la RUTA y auditarlo;
    no puede confiar en que la base lo detenga (mismo patrón que ``INTERNAL_ROLES``).
    """
    use(labelled, "takab_app", tenant=TENANT_A, app_role="takab_superadmin")
    labelled.execute(
        "UPDATE compliance_labels SET labels = %s::jsonb WHERE tenant_id = %s",
        (_DOC_A, TENANT_B),
    )
    fila = labelled.execute(
        "SELECT labels->'items'->0->>'claim' FROM compliance_labels WHERE tenant_id = %s",
        (TENANT_B,),
    ).fetchone()
    assert fila[0] == "Protocolo A"


def test_el_dueno_de_la_tabla_no_escribe_sin_ser_interno(labelled: psycopg.Connection) -> None:
    """``FORCE`` sujeta también al OWNER: sin ser interno de aplicación, 0 filas."""
    use(labelled, "takab_migrator", tenant=TENANT_A, app_role="tenant_admin")
    assert _try_update(labelled, TENANT_A, _DOC_B) == 0
    use(labelled, "takab_app", tenant=TENANT_A, app_role="takab_superadmin")
    assert _claims(labelled) == {"Protocolo A", "Protocolo B", "Protocolo G"}
