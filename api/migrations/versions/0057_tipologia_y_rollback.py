"""T-5.16 · tipología cerrada de inmueble + rollback de rule_set

Dos cosas que la ficha pide y que la base tenía que sostener primero.

**1. `sites.building_type` deja de ser texto libre.** Era texto libre sin
catálogo, así que la etiqueta no significaba nada y no se podía ofrecer ninguna
banda desde ella. El `CHECK` enumera el catálogo de
`shared/schemas/tipologia_umbral.json`, y `test_tipologia_umbral.py` compara las
dos listas por igualdad: un tipo nuevo en el JSON sin su línea aquí sale rojo.

Lo que había escrito ANTES no se tira: se normaliza lo reconocible
(mayúsculas/acentos/plurales) y lo que no encaja pasa a `otro` **dejando el texto
original en `audit_log`**. Perder la captura de alguien en silencio para que
cuadre un `CHECK` es exactamente lo que la regla de oro 11 prohíbe.

**2. `rule_sets.rolled_back_to`.** El rollback CREA una versión nueva que declara
a cuál vuelve; jamás reescribe el histórico. La procedencia va en columna propia
y no dentro de `config` a propósito: `config` es el blob que se sincroniza al
gabinete, y meterle metadatos de gestión lo haría viajar hasta el Pi.

Revision ID: 0057_tipologia_y_rollback
Revises: 0056_gov_ack_bitacora
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0057_tipologia_y_rollback"
down_revision: str | None = "0056_gov_ack_bitacora"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Sinónimos que se reconocen sin preguntar. La clave se compara contra el texto
#: en minúsculas y sin acentos; lo que no esté aquí NO se adivina — se manda a
#: `otro` con su original guardado.
_SINONIMOS = {
    "hospital": "hospital",
    "hospitales": "hospital",
    "clinica": "hospital",
    "industrial": "industrial",
    "industriales": "industrial",
    "industria": "industrial",
    "planta": "industrial",
    "corporativo": "corporativo",
    "corporativos": "corporativo",
    "oficinas": "corporativo",
    "universidad": "universidad",
    "universidades": "universidad",
    "campus": "universidad",
    "escuela": "universidad",
    "gobierno": "gobierno",
    "otro": "otro",
}


def upgrade() -> None:
    conn = op.get_bind()

    # `unaccent` no está garantizada: se normaliza con translate, que sí lo está.
    conn.exec_driver_sql(
        """
        CREATE TEMP TABLE _tipos_norm (crudo text, norm text) ON COMMIT DROP;
        INSERT INTO _tipos_norm (crudo, norm)
        SELECT DISTINCT building_type,
               translate(lower(btrim(building_type)), 'áéíóúüñ', 'aeiouun')
          FROM sites WHERE building_type IS NOT NULL;
        """
    )

    for crudo, canonico in _SINONIMOS.items():
        conn.exec_driver_sql(
            "UPDATE sites s SET building_type = %s"
            "  FROM _tipos_norm n"
            " WHERE n.crudo = s.building_type AND n.norm = %s",
            (canonico, crudo),
        )

    # Lo que sigue sin encajar: se DEJA ESCRITO antes de reemplazarlo.
    conn.exec_driver_sql(
        """
        INSERT INTO audit_log (tenant_id, actor, verb, object, meta)
        SELECT s.tenant_id, 'system:migration:0057', 'site_building_type_normalizado',
               'site:' || s.site_id::text,
               jsonb_build_object('anterior', s.building_type, 'nuevo', 'otro',
                                  'por_que', 'texto libre fuera del catalogo de D-28')
          FROM sites s
         WHERE s.building_type IS NOT NULL
           AND s.building_type NOT IN
               ('hospital','industrial','corporativo','universidad','gobierno','otro')
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE sites SET building_type = 'otro'
         WHERE building_type IS NOT NULL
           AND building_type NOT IN
               ('hospital','industrial','corporativo','universidad','gobierno','otro')
        """
    )

    # NULL sigue permitido: un sitio puede no tener tipología declarada todavía,
    # y forzarlo a `otro` sería afirmar que alguien lo clasificó.
    conn.exec_driver_sql(
        """
        ALTER TABLE sites DROP CONSTRAINT IF EXISTS sites_building_type_check;
        ALTER TABLE sites ADD CONSTRAINT sites_building_type_check
          CHECK (building_type IN
                 ('hospital','industrial','corporativo','universidad','gobierno','otro'));
        """
    )

    conn.exec_driver_sql(
        "ALTER TABLE rule_sets ADD COLUMN IF NOT EXISTS rolled_back_to uuid "
        "REFERENCES rule_sets(rule_set_id)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("ALTER TABLE rule_sets DROP COLUMN IF EXISTS rolled_back_to")
    conn.exec_driver_sql("ALTER TABLE sites DROP CONSTRAINT IF EXISTS sites_building_type_check")
