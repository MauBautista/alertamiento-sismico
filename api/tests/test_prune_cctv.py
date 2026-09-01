"""T-3.10 · La poda del vídeo, con sus DOS mitades y su orden.

QUÉ SE MIDE AQUÍ Y POR QUÉ ASÍ
──────────────────────────────
La ficha pide dos cosas y la segunda es la difícil:

1. la poda va en **job propio**, no como `RetentionRule`;
2. **las dos mitades, y las dos se reportan**: un `s3_key` en `NULL` no borra los
   bytes. *«Un plan que anula la referencia y deja la imagen es peor que ninguno,
   porque se declara cumplido.»*

Un test que solo comprobara el camino feliz haría pasar el criterio 2 sin probarlo:
con S3 respondiendo bien, cualquier orden de las dos mitades sale verde. Por eso la
sección B ejerce **el fallo de S3**, que es donde los dos órdenes se separan, y la C
ejerce la carrera que produce un huérfano.

LA TRAMPA QUE ESTE ARCHIVO EXISTE PARA CAZAR
────────────────────────────────────────────
El bucket de evidencia está **versionado**. Un `delete_object` sin `VersionId` no
borra un byte: pone un delete marker y deja la versión anterior como *noncurrent*.
El objeto desaparece de un `GET` —así que un test que compruebe «ya no se puede
leer» pasa— y **los bytes siguen ahí**. Es exactamente el fallo que la ficha nombra,
disfrazado de éxito. La sección A lo mide contra un S3 real (moto) **con versionado
encendido**, y comprueba las dos direcciones: que el borrado ingenuo deja el cuerpo,
y que el nuestro no.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import boto3
import psycopg
import pytest
from moto import mock_aws

from takab_api.ops import prune_cctv
from takab_api.privacy.retention import RetentionUnsafe
from takab_api.routers._s3 import delete_all_versions
from takab_api.settings import Settings

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
BUCKET = "takab-test-evidence"
AHORA = datetime.now(UTC)


def _dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL).replace(
        "postgresql+psycopg://", "postgresql://"
    )


# ===========================================================================
# A · EL BUCKET ESTÁ VERSIONADO, Y ESO CAMBIA QUÉ SIGNIFICA "BORRAR"
# ===========================================================================


@pytest.fixture
def s3_versionado() -> Iterator[Settings]:
    """Un bucket con versionado ENCENDIDO, que es como está el de evidencia."""
    with mock_aws():
        cli = boto3.client("s3", region_name="us-east-2")
        cli.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )
        cli.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        yield Settings(evidence_bucket=BUCKET, aws_region="us-east-2")


def _versiones(key: str) -> int:
    """Cuántas versiones con CUERPO quedan de esa key (delete markers no cuentan)."""
    resp = boto3.client("s3", region_name="us-east-2").list_object_versions(
        Bucket=BUCKET, Prefix=key
    )
    return sum(1 for v in resp.get("Versions", ()) if v["Key"] == key)


def test_el_delete_INGENUO_deja_los_bytes_vivos_en_un_bucket_versionado(
    s3_versionado: Settings,
) -> None:
    """El control negativo, y es el que justifica todo lo demás.

    Si esto fallara —si `delete_object` sí borrara— `delete_all_versions` sería
    complejidad sin motivo y habría que quitarla. Mientras pase, la ficha tiene razón:
    la forma obvia de borrar **se declara cumplida y no cumple**.
    """
    cli = boto3.client("s3", region_name="us-east-2")
    cli.put_object(Bucket=BUCKET, Key="evidence/t/e/clip.mp4", Body=b"personas evacuando")

    cli.delete_object(Bucket=BUCKET, Key="evidence/t/e/clip.mp4")

    with pytest.raises(cli.exceptions.ClientError):  # el GET ya no lo ve...
        cli.get_object(Bucket=BUCKET, Key="evidence/t/e/clip.mp4")
    assert _versiones("evidence/t/e/clip.mp4") == 1, (
        "…y sin embargo el cuerpo sigue ahí. Ése es el fallo entero de la ficha."
    )


def test_delete_all_versions_DESTRUYE_el_cuerpo_y_no_solo_lo_esconde(
    s3_versionado: Settings,
) -> None:
    cli = boto3.client("s3", region_name="us-east-2")
    key = "evidence/t/e/clip.mp4"
    cli.put_object(Bucket=BUCKET, Key=key, Body=b"v1")
    cli.put_object(Bucket=BUCKET, Key=key, Body=b"v2")  # dos versiones vivas
    cli.delete_object(Bucket=BUCKET, Key=key)  # y un delete marker encima

    assert delete_all_versions(s3_versionado, key) == 3  # dos cuerpos + el marcador
    assert _versiones(key) == 0
    assert cli.list_object_versions(Bucket=BUCKET, Prefix=key).get("DeleteMarkers", []) == []


def test_la_poda_de_una_key_no_se_lleva_por_delante_a_su_VECINA(
    s3_versionado: Settings,
) -> None:
    """`Prefix` no es igualdad: `clip.mp4` casa con `clip.mp4.bak`.

    Sin el filtro por key exacta, podar un clip destruiría objetos que nadie mandó
    borrar — y los contaría como trabajo bien hecho.
    """
    cli = boto3.client("s3", region_name="us-east-2")
    cli.put_object(Bucket=BUCKET, Key="evidence/t/e/clip.mp4", Body=b"el que se poda")
    cli.put_object(Bucket=BUCKET, Key="evidence/t/e/clip.mp4.bak", Body=b"el que NO")

    assert delete_all_versions(s3_versionado, "evidence/t/e/clip.mp4") == 1
    assert _versiones("evidence/t/e/clip.mp4.bak") == 1


# ===========================================================================
# La escena de base de datos
# ===========================================================================


class _Escena:
    """Un tenant propio con incidente, clips y capturas. No toca el seed compartido."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self.tenant = str(uuid.uuid4())
        self.site = str(uuid.uuid4())
        self.incident = str(uuid.uuid4())
        self.borrados: list[str] = []

    def seed(self) -> None:
        c = self.conn
        c.execute("RESET ROLE")
        c.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Poda de vídeo')",
            (self.tenant, self.tenant[:8]),
        )
        c.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography)",
            (self.site, self.tenant, f"PV-{self.site[:8]}"),
        )
        c.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at, "
            "severity, trigger) VALUES (%s,%s,%s,%s,%s,'critical','sasmex')",
            (self.incident, str(uuid.uuid4()), self.tenant, self.site, AHORA),
        )
        c.commit()

    # ---------------------------------------------------------------- altas

    def clip(self, *, hace_dias: float, key: str | None = None) -> str:
        """Un clip cuya GRABACIÓN terminó hace `hace_dias`."""
        fin = AHORA - timedelta(days=hace_dias)
        clip_id = str(uuid.uuid4())
        s3_key = key or f"evidence/{self.tenant}/{clip_id}/cctv.mp4"
        self.conn.execute(
            "INSERT INTO cctv_clips (clip_id, tenant_id, incident_id, s3_key, sha256, "
            "size_bytes, started_at, ended_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                clip_id,
                self.tenant,
                self.incident,
                s3_key,
                uuid.uuid4().hex * 2,
                1024,
                fin - timedelta(seconds=660),
                fin,
            ),
        )
        self.conn.commit()
        return clip_id

    def captura(self, *, hace_dias: float) -> str:
        still_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO cctv_stills (still_id, tenant_id, incident_id, role, s3_key, "
            "sha256, captured_at) VALUES (%s,%s,%s,'drip',%s,%s,%s)",
            (
                still_id,
                self.tenant,
                self.incident,
                f"evidence/{self.tenant}/{still_id}/still.jpg",
                uuid.uuid4().hex * 2,
                AHORA - timedelta(days=hace_dias),
            ),
        )
        self.conn.commit()
        return still_id

    # -------------------------------------------------------------- lectura

    def s3_key_de(self, tabla: str, pk: str, row_id: str) -> str | None:
        self.conn.execute("RESET ROLE")
        return self.conn.execute(
            f"SELECT s3_key FROM {tabla} WHERE {pk} = %s",  # noqa: S608 — literales del test
            (row_id,),
        ).fetchone()[0]

    def purgado_en(self, tabla: str, pk: str, row_id: str) -> datetime | None:
        self.conn.execute("RESET ROLE")
        return self.conn.execute(
            f"SELECT purged_at FROM {tabla} WHERE {pk} = %s",  # noqa: S608
            (row_id,),
        ).fetchone()[0]

    def bitacora(self) -> list[tuple]:
        self.conn.execute("RESET ROLE")
        return self.conn.execute(
            "SELECT actor, object, meta FROM audit_log "
            "WHERE tenant_id = %s AND verb = %s ORDER BY ts",
            (self.tenant, prune_cctv.VERBO),
        ).fetchall()

    # ------------------------------------------------------------ borradores

    def borrador_ok(self, _settings: Settings, key: str) -> int:
        self.borrados.append(key)
        return 1

    def borrador_denegado(self, _settings: Settings, key: str) -> int:
        raise RuntimeError(f"AccessDenied: el rol no puede borrar {key}")

    # ------------------------------------------------------------- la corrida

    def correr(self, **kwargs) -> prune_cctv.Informe:
        kwargs.setdefault("borrar", self.borrador_ok)
        kwargs.setdefault("settings", Settings(evidence_bucket=BUCKET))
        informe = prune_cctv.run(self.conn, **kwargs)
        self.conn.commit()
        return informe


@pytest.fixture
def escena() -> Iterator[_Escena]:
    conn = psycopg.connect(_dsn(), autocommit=False)
    sc = _Escena(conn)
    try:
        sc.seed()
        yield sc
    finally:
        conn.rollback()
        conn.execute("RESET ROLE")
        conn.execute("SET session_replication_role = 'replica'")
        for tabla in ("cctv_stills", "cctv_clips", "audit_log", "incidents", "sites", "tenants"):
            conn.execute(f"DELETE FROM {tabla} WHERE tenant_id = %s", (sc.tenant,))  # noqa: S608
        conn.commit()
        conn.close()


VENTANA = {"cctv_clips": 30, "cctv_stills": 30}


# ===========================================================================
# B · LAS DOS MITADES, Y SU ORDEN
# ===========================================================================


def test_la_poda_destruye_los_BYTES_y_ANULA_la_referencia(escena: _Escena) -> None:
    clip = escena.clip(hace_dias=60)

    informe = escena.correr(apply=True, days=VENTANA)

    assert len(informe.completos) == 1
    assert informe.ok
    assert escena.borrados == [f"evidence/{escena.tenant}/{clip}/cctv.mp4"]
    assert escena.s3_key_de("cctv_clips", "clip_id", clip) is None
    assert escena.purgado_en("cctv_clips", "clip_id", clip) is not None


def test_si_S3_SE_NIEGA_la_fila_NO_se_anula(escena: _Escena) -> None:
    """El corazón de la ficha, y lo único que separa los dos órdenes posibles.

    Con los bytes vivos, una referencia anulada sería la mentira exacta que T-3.10
    describe: la base diría `PURGADO` y la imagen de las personas seguiría en S3.
    """
    clip = escena.clip(hace_dias=60)

    informe = escena.correr(apply=True, days=VENTANA, borrar=escena.borrador_denegado)

    assert len(informe.fallidos) == 1
    assert not informe.completos
    assert "AccessDenied" in (informe.fallidos[0].error or "")
    assert escena.s3_key_de("cctv_clips", "clip_id", clip) is not None, (
        "la referencia sobrevive porque el objeto sobrevive: es lo correcto"
    )
    assert escena.purgado_en("cctv_clips", "clip_id", clip) is None
    assert not informe.ok


def test_lo_que_NO_se_pudo_borrar_no_deja_constancia_de_podado(escena: _Escena) -> None:
    """Una bitácora que dijera `cctv_purge` de un objeto vivo sería peor que ninguna."""
    escena.clip(hace_dias=60)
    escena.correr(apply=True, days=VENTANA, borrar=escena.borrador_denegado)
    assert escena.bitacora() == []


def test_un_fallo_no_detiene_la_poda_de_los_demas(escena: _Escena) -> None:
    """Veinte clips vencidos y uno que S3 rechaza: los otros diecinueve se podan.

    Abortar la corrida entera dejaría diecinueve imágenes vivas por culpa de una.
    """
    malo = f"evidence/{escena.tenant}/rechazado/cctv.mp4"
    escena.clip(hace_dias=60, key=malo)
    buenos = [escena.clip(hace_dias=60) for _ in range(3)]

    def selectivo(_s: Settings, key: str) -> int:
        if key == malo:
            raise RuntimeError("AccessDenied")
        escena.borrados.append(key)
        return 1

    informe = escena.correr(apply=True, days=VENTANA, borrar=selectivo)

    assert len(informe.completos) == 3
    assert len(informe.fallidos) == 1
    for clip in buenos:
        assert escena.s3_key_de("cctv_clips", "clip_id", clip) is None


# ===========================================================================
# C · EL HUÉRFANO SE DECLARA, NO SE CUENTA COMO ÉXITO
# ===========================================================================


def test_un_HUERFANO_se_declara_en_vez_de_contarse_como_completo(escena: _Escena) -> None:
    """Bytes destruidos y fila sin anular: el desenlace tolerable, y aun así se dice.

    Se provoca la carrera real: otra sesión anula la clave entre el borrado en S3 y el
    `UPDATE`. El `AND s3_key = …` de la sentencia hace que toque cero filas, y el job
    lo cuenta como huérfano en vez de suponer que su `UPDATE` funcionó.
    """
    clip = escena.clip(hace_dias=60)

    def borrar_y_pisar(_s: Settings, key: str) -> int:
        otra = psycopg.connect(_dsn(), autocommit=True)
        try:
            otra.execute(
                "UPDATE cctv_clips SET s3_key = NULL, purged_at = now() WHERE clip_id = %s",
                (clip,),
            )
        finally:
            otra.close()
        return 1

    informe = escena.correr(apply=True, days=VENTANA, borrar=borrar_y_pisar)

    assert len(informe.huerfanos) == 1
    assert not informe.completos
    assert not informe.ok, "un huérfano tiene que salir del cero de la corrida limpia"


def test_un_fallo_de_BASE_tras_destruir_los_bytes_es_un_huerfano_no_un_crash(
    escena: _Escena,
) -> None:
    """La conexión se cae justo después de que S3 borre. Los bytes ya no existen.

    Si esa excepción subiera, se perdería la única noticia de que ese objeto se
    destruyó **y** los objetivos siguientes se quedarían sin procesar, con su imagen
    viva. Se declara huérfano y la corrida continúa.

    Va sobre una conexión propia: la de la escena tiene que sobrevivir para limpiar.
    """
    escena.clip(hace_dias=60)
    propia = psycopg.connect(_dsn(), autocommit=False)

    def borrar_y_tumbar_la_conexion(_s: Settings, _key: str) -> int:
        propia.close()
        return 1

    try:
        informe = prune_cctv.run(
            propia,
            settings=Settings(evidence_bucket=BUCKET),
            apply=True,
            days=VENTANA,
            borrar=borrar_y_tumbar_la_conexion,
        )
    finally:
        propia.close()

    assert len(informe.huerfanos) == 1
    assert informe.huerfanos[0].bytes_borrados
    assert not informe.ok


# ===========================================================================
# D · EL SIMULACRO ES LA AUTORIZACIÓN
# ===========================================================================


def test_el_simulacro_censa_y_no_destruye_ni_un_byte(escena: _Escena) -> None:
    clip = escena.clip(hace_dias=60)

    informe = escena.correr(days=VENTANA)  # sin --apply

    assert informe.mode == prune_cctv.SIMULACRO
    assert len(informe.objetivos) == 1
    assert informe.podados == ()
    assert escena.borrados == []
    assert escena.s3_key_de("cctv_clips", "clip_id", clip) is not None


def test_sin_plazo_configurado_la_tabla_queda_DESHABILITADA(escena: _Escena) -> None:
    """El default de producción: el cron se despliega antes de decidir los plazos."""
    escena.clip(hace_dias=3650)

    informe = escena.correr(apply=True, days={"cctv_clips": None, "cctv_stills": None})

    assert set(informe.disabled) == {"cctv_clips", "cctv_stills"}
    assert informe.objetivos == ()
    assert escena.borrados == []


@pytest.mark.parametrize("crudo", ["", "  ", "treinta", "-1", "0"])
def test_un_plazo_mal_tecleado_DESHABILITA_en_vez_de_caer_a_un_default(crudo: str) -> None:
    """Un default silencioso aquí destruye imágenes antes de tiempo. Sin red."""
    assert (
        prune_cctv.dias_configurados(
            prune_cctv.CLIPS, {"": crudo} | {prune_cctv.CLIPS.env_var: crudo}
        )
        is None
    )


# ===========================================================================
# E · EL RELOJ
# ===========================================================================


def test_el_reloj_cuenta_desde_la_GRABACION_no_desde_el_registro(escena: _Escena) -> None:
    """Un gabinete sin enlace sube su clip días después. La fila nace tarde; la imagen no.

    Contar desde `created_at` le regalaría a esa imagen un plazo que nadie autorizó.
    """
    viejo = escena.clip(hace_dias=60)  # grabado hace 60 d, registrado AHORA
    reciente = escena.clip(hace_dias=1)

    informe = escena.correr(days=VENTANA)

    assert [o.row_id for o in informe.objetivos] == [viejo]
    assert reciente not in [o.row_id for o in informe.objetivos]


def test_clips_y_capturas_llevan_PLAZOS_INDEPENDIENTES(escena: _Escena) -> None:
    clip = escena.clip(hace_dias=45)
    escena.captura(hace_dias=45)

    informe = escena.correr(days={"cctv_clips": 30, "cctv_stills": 90})

    assert [o.row_id for o in informe.objetivos] == [clip]
    assert informe.ventanas["cctv_stills"] == 90


def test_la_captura_tambien_se_poda_por_su_propio_reloj(escena: _Escena) -> None:
    still = escena.captura(hace_dias=200)
    informe = escena.correr(apply=True, days={"cctv_clips": None, "cctv_stills": 90})
    assert len(informe.completos) == 1
    assert escena.s3_key_de("cctv_stills", "still_id", still) is None


# ===========================================================================
# F · IDEMPOTENCIA
# ===========================================================================


def test_la_segunda_corrida_no_ve_nada(escena: _Escena) -> None:
    """`s3_key IS NOT NULL` es la idempotencia: no hay que llevar cuentas aparte."""
    escena.clip(hace_dias=60)
    escena.correr(apply=True, days=VENTANA)

    segunda = escena.correr(apply=True, days=VENTANA)

    assert segunda.objetivos == ()
    assert len(escena.borrados) == 1


# ===========================================================================
# G · LO QUE EL JOB LE DEMUESTRA A POSTGRES ANTES DE TOCAR NADA
# ===========================================================================


def test_el_job_NO_CORRE_si_la_rendija_de_poda_esta_deshabilitada(escena: _Escena) -> None:
    """Un trigger apagado sigue en el catálogo: la garantía se cae SIN AVISAR.

    Sin `cctv_purge_guard` en UPDATE, el `UPDATE` de este job podría reescribir
    cualquier columna de una tabla append-only. Por eso se comprueba `tgenabled` en
    cada corrida y la ausencia aborta.
    """
    escena.clip(hace_dias=60)
    escena.conn.execute("RESET ROLE")
    escena.conn.execute("ALTER TABLE cctv_clips DISABLE TRIGGER trg_cctv_clips_purge_guard")
    escena.conn.commit()
    try:
        with pytest.raises(RetentionUnsafe, match="rendija de poda NO está activa"):
            escena.correr(apply=True, days=VENTANA)
    finally:
        escena.conn.rollback()
        escena.conn.execute("RESET ROLE")
        escena.conn.execute("ALTER TABLE cctv_clips ENABLE TRIGGER trg_cctv_clips_purge_guard")
        escena.conn.commit()

    assert escena.borrados == [], "abortar significa no destruir un solo byte"


def test_el_job_corre_degradado_y_lo_demuestra(escena: _Escena) -> None:
    """El DSN de estos tests es SUPERUSER y BYPASSRLS. El job no corre con eso."""
    informe = escena.correr(days=VENTANA)
    assert informe.role == "takab_app"
    assert not informe.superuser
    assert not informe.bypassrls
    assert informe.rendija == {"cctv_clips": True, "cctv_stills": True}


def test_el_job_NO_PUEDE_borrar_la_fila_aunque_quiera(escena: _Escena) -> None:
    """La poda destruye la imagen; el HECHO sobrevive. Y no es disciplina: es la base.

    `cctv_clips` es append-only por dos capas —`REVOKE DELETE` y el trigger— y este
    test las ejerce desde el rol con el que corre el job.
    """
    clip = escena.clip(hace_dias=60)
    escena.conn.execute("RESET ROLE")
    escena.conn.execute("SET ROLE takab_app")
    with pytest.raises(psycopg.Error):
        escena.conn.execute("DELETE FROM cctv_clips WHERE clip_id = %s", (clip,))
    escena.conn.rollback()
    escena.conn.execute("RESET ROLE")


def test_el_plan_no_nombra_ninguna_tabla_de_COMPLIANCE(escena: _Escena) -> None:
    """El vídeo NO hereda la exención de poda de la evidencia — ni al revés.

    Puro y sin base de datos: el plan de este job no puede alcanzar a las cinco tablas
    que la regla de oro 11 protege. Si alguien añadiera `evidence_objects` aquí, esto
    se pone rojo antes de que el job llegue a la base.
    """
    from takab_api.privacy.retention import COMPLIANCE_ANCHOR

    assert not {t.tabla for t in prune_cctv.PLAN_DE_VIDEO} & set(COMPLIANCE_ANCHOR)


# ===========================================================================
# H · LA CONSTANCIA
# ===========================================================================


def test_cada_objeto_podado_deja_fila_en_audit_log(escena: _Escena) -> None:
    """`audit_log` no se poda jamás: cuando el objeto ya no exista, esta fila será la
    única constancia de que existió y de que se destruyó."""
    clip = escena.clip(hace_dias=60)
    escena.correr(apply=True, days=VENTANA)

    filas = escena.bitacora()
    assert len(filas) == 1
    actor, objeto, meta = filas[0]
    assert actor == prune_cctv.ACTOR
    assert objeto == f"evidence/{escena.tenant}/{clip}/cctv.mp4"
    assert meta["kind"] == "clip"
    assert meta["row_id"] == clip


def test_el_informe_separa_los_TRES_desenlaces(escena: _Escena) -> None:
    """Un total único confundiría «la imagen ya no existe» con «la imagen sigue ahí»."""
    malo = f"evidence/{escena.tenant}/rechazado/cctv.mp4"
    escena.clip(hace_dias=60, key=malo)
    escena.clip(hace_dias=60)

    def selectivo(_s: Settings, key: str) -> int:
        if key == malo:
            raise RuntimeError("AccessDenied")
        return 1

    informe = escena.correr(apply=True, days=VENTANA, borrar=selectivo)
    salida = prune_cctv.render(informe)

    assert "COMPLETOS" in salida and "HUÉRFANOS" in salida and "FALLIDOS" in salida
    assert "la imagen SIGUE AHÍ" in salida
    assert prune_cctv._informe_json(informe)["ok"] is False
