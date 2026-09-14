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


def test_el_relleno_de_la_MIGRACION_corre_con_el_rol_de_la_nube(sitio) -> None:
    """⚠️ En la nube la migración NO corre como superusuario.

    `incidents` tiene `FORCE ROW LEVEL SECURITY`: con FORCE, ni el dueño de la
    tabla se salta las políticas. En local la migración corre como superusuario
    (BYPASSRLS) y el relleno toca todas las filas; en la nube corre como
    `takab_migrator`, sin `app.tenant_id` puesto, y el mismo `UPDATE` afecta a
    **cero filas en silencio**. El despliegue del 2026-09-14 murió justo ahí, en
    el `SET NOT NULL` — que es lo único que lo delataba.

    Esto ejercita el bloque REAL de la migración con el rol REAL de la nube y
    comprueba las dos mitades: que ese rol **puede** ejecutarlo, y que deja el
    `FORCE` como estaba. Endurecer o ablandar la RLS de una tabla como efecto
    colateral de añadir una columna sería peor que el defecto original.
    """
    relleno = _sql_de_la_migracion("_RELLENO")
    assert "NO FORCE ROW LEVEL SECURITY" in relleno, (
        "el relleno no aparta la RLS: con `takab_migrator` no vería ni una fila"
    )
    antes = _forzada(sitio)
    assert antes, "el test no mide nada si `incidents` no tiene FORCE"

    # Se fabrica el estado PREVIO a la migración: una fila sin estampa. Hay que
    # apagar el disparador (que la restauraría) y soltar el NOT NULL; todo va
    # dentro de la transacción del test, que se deshace al terminar.
    ev = _abrir(sitio, "sasmex")
    sitio.execute("ALTER TABLE incidents ALTER COLUMN opened_trigger DROP NOT NULL")
    sitio.execute(_sql_de_la_migracion("_SIN_DISPARADOR"))
    sitio.execute("UPDATE incidents SET opened_trigger = NULL WHERE event_uuid = %s", (ev,))
    assert _campos(sitio, ev)[1] is None, "no se pudo fabricar el estado previo"

    sitio.execute("SET ROLE takab_migrator")  # el rol REAL de la nube, sin BYPASSRLS
    try:
        sitio.execute(relleno)  # el bloque REAL de la migración
    finally:
        sitio.execute("RESET ROLE")

    assert _campos(sitio, ev)[1] == "sasmex", (
        "el relleno no vio la fila: en la nube dejaría el campo de auditoría con huecos "
        "y el despliegue moriría en el SET NOT NULL"
    )
    assert _forzada(sitio) is antes, "la migración dejó la RLS de `incidents` cambiada"


def _sql_de_la_migracion(nombre: str) -> str:
    """Carga `0063_*.py` por RUTA: un fichero que empieza por dígito no se importa."""
    import importlib.util
    from pathlib import Path

    ruta = Path(__file__).resolve().parents[1] / "migrations/versions/0063_disparo_de_apertura.py"
    spec = importlib.util.spec_from_file_location("mig0063", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, nombre)


def _forzada(conn) -> bool:
    return conn.execute(
        "SELECT relforcerowsecurity FROM pg_class WHERE oid = 'incidents'::regclass"
    ).fetchone()[0]
