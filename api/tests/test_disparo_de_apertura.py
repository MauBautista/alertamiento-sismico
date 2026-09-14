"""[T-7.36] `incidents.opened_trigger`: qué ABRIÓ el incidente, no qué lo escaló.

`incidents.trigger` **no es el disparo de apertura**: el UPSERT de la ingesta lo
sobrescribe con el de la última escalada, y `summary` se fusiona perdiendo el
valor viejo. Hasta esta ficha **ningún sitio del esquema guardaba con qué se
abrió** — y el dictamen, que es un documento con peso legal, lo presentaba como
el origen y calculaba desde él el tiempo de aviso ganado.

Las dos direcciones del error son reales y opuestas, y las dos se prueban aquí:

* umbral local abre · SASMEX escala ⇒ el papel **inflaba** el aviso ganado,
  atribuyéndole a SASMEX segundos anteriores a que SASMEX dijera nada;
* SASMEX abre · cuórum escala ⇒ el papel **negaba** un aviso que sí existió.

La estampa la pone la BASE. Hay decenas de sitios que insertan en `incidents`
—migraciones, sembradores, arneses, tests— y un campo de auditoría que cada
escritor tiene que acordarse de rellenar acaba con huecos justo en la fila que
importaba.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg
import pytest

TENANT = "d0000000-0000-0000-0000-000000000001"
SITE = "d1000000-0000-0000-0000-000000000000"


@pytest.fixture
def sitio(conn: psycopg.Connection) -> psycopg.Connection:
    conn.execute("RESET ROLE")
    conn.execute(
        "INSERT INTO tenants (tenant_id, code, name) VALUES (%s, 'tenant-dev', 'TAKAB Dev') "
        "ON CONFLICT DO NOTHING",
        (TENANT,),
    )
    conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s, %s, 'site-dev', 'Sitio Dev', "
        "ST_SetSRID(ST_MakePoint(-98.2063, 19.0414), 4326)::geography) ON CONFLICT DO NOTHING",
        (SITE, TENANT),
    )
    return conn


def _abrir(conn: psycopg.Connection, trigger: str, **extra: object) -> str:
    """Abre un incidente como lo hace la ingesta, SIN nombrar `opened_trigger`."""
    event_uuid = extra.pop("event_uuid", None) or str(uuid.uuid4())
    conn.execute(
        "INSERT INTO incidents (event_uuid, tenant_id, site_id, opened_at, severity, state, "
        "trigger, summary) VALUES (%s, %s, %s, %s, 'warning', 'open', %s, '{}'::jsonb)",
        (event_uuid, TENANT, SITE, datetime.now(UTC), trigger),
    )
    return event_uuid


def _campos(conn: psycopg.Connection, event_uuid: str) -> tuple[str, str]:
    row = conn.execute(
        "SELECT trigger, opened_trigger FROM incidents WHERE event_uuid = %s", (event_uuid,)
    ).fetchone()
    return row[0], row[1]


def test_el_disparo_de_apertura_se_estampa_SIN_que_el_escritor_lo_nombre(sitio) -> None:
    """Ningún `INSERT INTO incidents` del repositorio menciona la columna."""
    ev = _abrir(sitio, "local_threshold")
    assert _campos(sitio, ev) == ("local_threshold", "local_threshold")


def test_una_escalada_NO_toca_el_disparo_de_apertura(sitio) -> None:
    """El caso que inflaba el aviso ganado: abre el umbral local, escala SASMEX.

    `opened_at` se queda en el del umbral. Si el papel atribuye ese instante a
    SASMEX, presenta como aviso ganado segundos que transcurrieron antes de que
    SASMEX dijera nada.
    """
    ev = _abrir(sitio, "local_threshold")
    sitio.execute(
        "UPDATE incidents SET trigger = 'sasmex', severity = 'critical' WHERE event_uuid = %s",
        (ev,),
    )
    assert _campos(sitio, ev) == ("sasmex", "local_threshold")


def test_el_caso_CONTRARIO_tambien_se_conserva(sitio) -> None:
    """Abre SASMEX, escala el cuórum: sin esta columna el papel NEGABA el aviso."""
    ev = _abrir(sitio, "sasmex")
    sitio.execute("UPDATE incidents SET trigger = 'quorum' WHERE event_uuid = %s", (ev,))
    assert _campos(sitio, ev) == ("quorum", "sasmex")


def test_un_escritor_NO_puede_declarar_un_origen_distinto_del_suyo(sitio) -> None:
    """Un campo de auditoría que el emisor rellena no audita al emisor.

    El disparador la COPIA de `trigger`, no la lee del INSERT: da igual lo que
    mande quien escribe.
    """
    ev = str(uuid.uuid4())
    sitio.execute(
        "INSERT INTO incidents (event_uuid, tenant_id, site_id, opened_at, severity, state, "
        "trigger, opened_trigger, summary) VALUES (%s, %s, %s, %s, 'warning', 'open', "
        "'local_threshold', 'sasmex', '{}'::jsonb)",
        (ev, TENANT, SITE, datetime.now(UTC)),
    )
    assert _campos(sitio, ev) == ("local_threshold", "local_threshold")


def test_reescribirla_a_PROPOSITO_tampoco_funciona(sitio) -> None:
    """Inmutable: ni queriendo, ni por descuido en un `UPDATE … SET` amplio."""
    ev = _abrir(sitio, "sasmex")
    sitio.execute(
        "UPDATE incidents SET opened_trigger = 'manual', trigger = 'manual' WHERE event_uuid = %s",
        (ev,),
    )
    assert _campos(sitio, ev) == ("manual", "sasmex")


def test_no_queda_ni_una_fila_SIN_estampa(sitio) -> None:
    """El relleno de la migración cubrió lo que ya existía, y el NOT NULL cierra
    la puerta a que nazca una fila sin ella."""
    assert (
        sitio.execute("SELECT count(*) FROM incidents WHERE opened_trigger IS NULL").fetchone()[0]
        == 0
    )
