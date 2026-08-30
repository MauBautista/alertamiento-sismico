"""Ingesta de clips y capturas de CCTV contra Postgres real (T-3.11.b).

Lo que se prueba aquí es lo que `D-14` exige y ninguna prueba unitaria alcanza: que la
salida de vídeo **deje constancia en `audit_log`**, y que la deje **una sola vez** aunque
SQS reentregue el objeto — que lo hace, por diseño at-least-once.
"""

from __future__ import annotations

import hashlib
import io
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.backfill.objects import process_s3_object
from takab_api.ingest.handlers import Outcome
from takab_api.settings import Settings

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
BUCKET = "takab-dev-evidence"
DESDE = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
HASTA = DESDE + timedelta(seconds=660)
_FMT = "%Y%m%dT%H%M%SZ"


def _dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL).replace(
        "postgresql+psycopg://", "postgresql://"
    )


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put(self, bucket: str, key: str, body: bytes) -> None:
        self.objects[(bucket, key)] = body

    def get_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803 — firma boto3
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


class _Escena:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self.tenant = str(uuid.uuid4())
        self.site = str(uuid.uuid4())
        self.incident = str(uuid.uuid4())
        self.event_uuid = str(uuid.uuid4())
        self.s3 = _FakeS3()

    def seed(self) -> None:
        c = self.conn
        c.execute("RESET ROLE")
        c.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'CCTV Test')",
            (self.tenant, self.tenant[:8]),
        )
        c.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography)",
            (self.site, self.tenant, f"CC-{self.site[:8]}"),
        )
        c.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at, "
            "severity, trigger) VALUES (%s,%s,%s,%s,%s,'critical','sasmex')",
            (self.incident, self.event_uuid, self.tenant, self.site, DESDE),
        )
        c.commit()
        c.execute("SET ROLE takab_ingest")  # paridad con el worker real

    def subir(self, cuerpo: bytes, *, clip: bool = True, evento: str | None = None) -> str:
        sha = hashlib.sha256(cuerpo).hexdigest()
        ev = evento or self.event_uuid
        if clip:
            nombre = f"cctv-{DESDE:{_FMT}}_{HASTA:{_FMT}}-{sha}.mp4"
        else:
            nombre = f"still-{DESDE:{_FMT}}-{sha}.jpg"
        key = f"evidence/{self.tenant}/{ev}/{nombre}"
        self.s3.put(BUCKET, key, cuerpo)
        return key

    def procesar(self, key: str):
        return process_s3_object(
            self.conn, BUCKET, key, registry=None, settings=Settings(), s3_client=self.s3
        )

    def contar(self, tabla: str) -> int:
        return self.conn.execute(
            f"SELECT count(*) FROM {tabla} WHERE tenant_id = %s",
            (self.tenant,),  # noqa: S608
        ).fetchone()["count"]

    def egresos(self) -> list[dict]:
        return self.conn.execute(
            "SELECT verb, actor, object, meta FROM audit_log "
            "WHERE tenant_id = %s AND verb = 'cctv_egress' ORDER BY ts",
            (self.tenant,),
        ).fetchall()


@pytest.fixture
def escena() -> Iterator[_Escena]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    sc = _Escena(conn)
    try:
        sc.seed()
        yield sc
    finally:
        conn.rollback()
        conn.execute("RESET ROLE")
        conn.execute("SET session_replication_role = 'replica'")
        for tabla in ("cctv_stills", "cctv_clips", "audit_log", "incidents", "sites", "tenants"):
            col = "tenant_id"
            conn.execute(f"DELETE FROM {tabla} WHERE {col} = %s", (sc.tenant,))  # noqa: S608
        conn.commit()
        conn.close()


# ------------------------------------------------------------- camino feliz


def test_el_clip_se_registra_con_SU_ventana(escena: _Escena) -> None:
    """La ventana sale de la key: es lo único que la notificación de S3 puede ver."""
    escena.procesar(escena.subir(b"un clip"))
    fila = escena.conn.execute(
        "SELECT started_at, ended_at, sha256, size_bytes FROM cctv_clips WHERE tenant_id = %s",
        (escena.tenant,),
    ).fetchone()
    assert fila["started_at"] == DESDE
    assert fila["ended_at"] == HASTA
    assert fila["size_bytes"] == len(b"un clip")


def test_la_captura_va_a_su_tabla_y_no_a_la_de_clips(escena: _Escena) -> None:
    escena.procesar(escena.subir(b"un jpeg", clip=False))
    assert escena.contar("cctv_stills") == 1
    assert escena.contar("cctv_clips") == 0


# ------------------------------------------- la auditoría que exige D-14


def test_la_salida_de_video_DEJA_constancia_en_audit_log(escena: _Escena) -> None:
    """«La salida de vídeo queda auditada igual que un comando de actuador» (D-14).

    Sin esta fila, la única constancia de que salieron imágenes de personas sería el propio
    objeto — que la política de retención está OBLIGADA a borrar."""
    key = escena.subir(b"un clip")
    escena.procesar(key)
    filas = escena.egresos()
    assert len(filas) == 1
    fila = filas[0]
    assert fila["actor"] == "system:backfill"
    assert fila["object"] == key
    assert fila["meta"]["kind"] == "clip"
    assert fila["meta"]["incident_id"] == escena.incident
    assert fila["meta"]["size_bytes"] == len(b"un clip")


def test_una_REENTREGA_no_dice_que_el_video_salio_dos_veces(escena: _Escena) -> None:
    """SQS entrega at-least-once. Sin el `RETURNING`, la segunda entrega escribiría una
    segunda fila de egreso y el registro afirmaría una salida que no ocurrió."""
    key = escena.subir(b"un clip")
    primero = escena.procesar(key)
    segundo = escena.procesar(key)
    assert primero.outcome is Outcome.OK
    assert segundo.outcome is Outcome.OK  # idempotente, no un error
    assert escena.contar("cctv_clips") == 1
    assert len(escena.egresos()) == 1


def test_la_captura_se_audita_declarando_que_es_una_captura(escena: _Escena) -> None:
    escena.procesar(escena.subir(b"un jpeg", clip=False))
    assert escena.egresos()[0]["meta"]["kind"] == "still"


# --------------------------------------------------------- lo que se rechaza


def test_un_objeto_cuyo_hash_no_cuadra_no_se_registra_NI_se_audita(escena: _Escena) -> None:
    """Si el contenido no es el que la key declara, no hay nada que auditar: no es el
    objeto que se autorizó a subir."""
    key = escena.subir(b"un clip")
    escena.s3.put(BUCKET, key, b"otra cosa")  # alguien cambió el contenido
    resultado = escena.procesar(key)
    assert resultado.outcome is Outcome.REJECT
    assert escena.contar("cctv_clips") == 0
    assert escena.egresos() == []


def test_un_clip_de_un_incidente_que_aun_no_existe_se_REINTENTA_no_se_tira(
    escena: _Escena,
) -> None:
    """El clip tarda once minutos en cortarse y puede subir antes de que el evento se haya
    ingerido si el gabinete estuvo sin red. Un REJECT mandaría a la DLQ evidencia buena."""
    resultado = escena.procesar(escena.subir(b"x", evento=str(uuid.uuid4())))
    assert resultado.outcome is Outcome.RETRY


def test_una_key_con_tenant_ajeno_no_alcanza_el_incidente(escena: _Escena) -> None:
    """Las FK de Postgres no comparan tenant: sin esta comprobación una key ajena
    alcanzaría el espacio de otro cliente."""
    key = escena.subir(b"x")
    ajena = key.replace(escena.tenant, str(uuid.uuid4()), 1)
    escena.s3.put(BUCKET, ajena, b"x")
    assert escena.procesar(ajena).outcome is Outcome.REJECT
