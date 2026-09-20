"""Exportación de evidencia (T-1.22 · B4): listado RLS + presigned + audit.

Reusa las fixtures de ``tests/api/conftest.py`` (entorno de auth, engine por
test, ``make_incident``, limpieza por TRUNCATE que ya incluye evidence_objects/
audit_log). Sobrescribe ``app`` para montar SOLO el router de exports (la
integración en main.py es de otra fase). S3 se mockea con moto.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from moto import mock_aws
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.exports import router as exports_router

pytestmark = pytest.mark.asyncio

BUCKET = "takab-dev-evidence"
_REGION = "us-east-2"


@pytest.fixture
def app() -> FastAPI:
    """Override del ``app`` del conftest: monta el router de exports."""
    application = create_app()
    application.include_router(exports_router)
    return application


async def _add_evidence(
    incident_id: str,
    tenant_id: str,
    *,
    kind: str = "miniseed",
    s3_key: str = "evidence/x/abc.mseed",
    sha256: str = "deadbeef",
) -> str:
    """⚠️ `sha256` es parámetro porque `uq_evidence_incident_sha256` es ÚNICO por
    `(incident_id, sha256)`: dos objetos del MISMO incidente con el sha a fuego
    chocan. Lo descubrió el censo de verbos por `kind`, que necesita los cuatro
    colgando de un solo incidente para poder comparar sus rótulos entre sí."""
    engine = get_engine()
    eid = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO evidence_objects (evidence_id, tenant_id, incident_id, "
                "kind, s3_key, sha256) VALUES (:e, :t, :i, :k, :key, :sha)"
            ),
            {
                "e": eid,
                "t": tenant_id,
                "i": incident_id,
                "k": kind,
                "key": s3_key,
                "sha": sha256,
            },
        )
    return eid


def _kinds_del_esquema() -> list[str]:
    """Los `kind` que `evidence_objects` admite, DERIVADOS del CHECK de `db/schema.sql`.

    No una lista aquí: el día que alguien añada un quinto `kind`, este censo lo
    exige con verbo propio en vez de dejarlo heredar el del vecino — que es
    exactamente como `photo` y `log` acabaron compartiendo `export_miniseed`.
    """
    sql = (Path(__file__).resolve().parents[3] / "db" / "schema.sql").read_text(encoding="utf-8")
    # ⚠️ Anclado al bloque de SU tabla: hay más columnas `kind` con CHECK en el
    # esquema y un patrón suelto se trae la primera que encuentre. Medido: sin
    # este ancla devolvía ['structural', 'ground'], que es de otra tabla.
    tabla = re.search(r"CREATE TABLE evidence_objects\s*\((.*?)\n\);", sql, re.S)
    assert tabla, "no se encontró `CREATE TABLE evidence_objects` en db/schema.sql"
    m = re.search(r"kind\s+text NOT NULL CHECK \(kind IN \(([^)]+)\)\)", tabla.group(1))
    assert m, "no se encontró el CHECK de `evidence_objects.kind` en db/schema.sql"
    kinds = re.findall(r"'([^']+)'", m.group(1))
    assert len(kinds) >= 4, f"el CHECK devolvió {kinds}: el censo estaría mirando casi nada"
    return kinds


async def _audit_verbs(tenant_id: str) -> list[str]:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text("SELECT verb FROM audit_log WHERE tenant_id = :t ORDER BY ts"),
                {"t": tenant_id},
            )
        ).all()
    return [r.verb for r in rows]


def _env_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_EVIDENCE_BUCKET", BUCKET)
    monkeypatch.setenv("TAKAB_API_AWS_REGION", _REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)


def _make_bucket() -> None:
    import boto3

    boto3.client("s3", region_name=_REGION).create_bucket(
        Bucket=BUCKET,
        CreateBucketConfiguration={"LocationConstraint": _REGION},
    )


async def test_list_evidence_scoped_to_tenant(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _add_evidence(iid, au.DB_TENANT_PRIV, kind="miniseed")

    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV)
    r = await client.get(f"/incidents/{iid}/evidence", headers=au.bearer(tok))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "miniseed"


async def test_list_evidence_cross_tenant_is_empty(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _add_evidence(iid, au.DB_TENANT_PRIV)

    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV2)
    r = await client.get(f"/incidents/{iid}/evidence", headers=au.bearer(tok))
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_list_evidence_mobile_surface_forbidden(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, surface="mobile")
    r = await client.get(f"/incidents/{iid}/evidence", headers=au.bearer(tok))
    assert r.status_code == 403


async def test_download_presigned_and_audits_miniseed(client, make_incident, monkeypatch) -> None:
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        key = "evidence/EVT-1/proof.mseed"
        ev = await _add_evidence(iid, au.DB_TENANT_PRIV, kind="miniseed", s3_key=key)

        tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
        r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
        assert r.status_code == 200
        body = r.json()
        assert body["expires_in"] == 300
        assert BUCKET in body["url"] and "proof.mseed" in body["url"]

    assert "download_miniseed" in await _audit_verbs(au.DB_TENANT_PRIV)


async def test_cada_kind_de_evidencia_deja_su_propio_verbo(
    client, make_incident, monkeypatch
) -> None:
    """[T-7.45] Descargar dice QUÉ se descargó, y no se disfraza de generar.

    El ternario que había tenía DOS ramas para CUATRO `kind`: `photo` y `log`
    caían los dos en `export_miniseed`, así que la cadena de custodia de una
    fotografía de daños quedaba rotulada como forma de onda. Y la rama del PDF
    usaba `export_pdf`, el verbo que el freno de `T-5.18` cuenta para decidir si
    deja GENERAR un dictamen — de ahí el 429 prematuro.

    Las tres afirmaciones se comprueban sobre la población DERIVADA del CHECK:
    cada `kind` deja verbo, ningún par lo comparte, y ninguno es un verbo de
    generación.
    """
    _env_bucket(monkeypatch)
    kinds = _kinds_del_esquema()
    #: Los verbos con los que se GENERA. Un rótulo de descarga que caiga aquí
    #: vuelve a gastar el techo del que genera, que es el defecto de la ficha.
    generacion = {"export_pdf", "export_drill_report"}

    verbos: dict[str, str] = {}
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
        for i, kind in enumerate(kinds):
            antes = set(await _audit_verbs(au.DB_TENANT_PRIV))
            ev = await _add_evidence(
                iid,
                au.DB_TENANT_PRIV,
                kind=kind,
                s3_key=f"evidence/EVT-1/objeto-{kind}",
                # sha distinto por objeto: `uq_evidence_incident_sha256` es único
                # por `(incident_id, sha256)` y los cuatro cuelgan del mismo.
                sha256=f"{i:064x}",
            )
            r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
            assert r.status_code == 200, f"no se pudo descargar un `{kind}`: {r.text}"
            nuevos = set(await _audit_verbs(au.DB_TENANT_PRIV)) - antes
            assert len(nuevos) == 1, f"descargar un `{kind}` dejó {nuevos or 'ningún verbo'}"
            verbos[kind] = nuevos.pop()

    repetidos = {v for v in verbos.values() if list(verbos.values()).count(v) > 1}
    assert not repetidos, (
        f"dos `kind` comparten verbo {sorted(repetidos)}: {verbos}. Entonces la bitácora no "
        "dice qué se descargó — una foto de daños no es una forma de onda"
    )
    colisiones = {k: v for k, v in verbos.items() if v in generacion}
    assert not colisiones, (
        f"descargar se audita con un verbo de GENERACIÓN: {colisiones}. Eso gasta el techo del "
        "freno de exportación sin ser lo que el freno protege (T-7.45)"
    )
    for kind, verbo in verbos.items():
        assert kind in verbo, f"el verbo `{verbo}` no dice que lo descargado era un `{kind}`"


async def test_download_gov_sees_gov_shared(client, make_incident, monkeypatch) -> None:
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_GOV, au.DB_SITE_GOV)
        ev = await _add_evidence(iid, au.DB_TENANT_GOV, kind="miniseed")
        tok = au.make_token("gov_operator", tenant=au.DB_TENANT_AGENCY)
        r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
        assert r.status_code == 200


async def test_download_gov_private_is_404(client, make_incident, monkeypatch) -> None:
    """gov_operator NO ve evidencia de un tenant privado → 404 (sin fuga)."""
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        ev = await _add_evidence(iid, au.DB_TENANT_PRIV, kind="miniseed")
        tok = au.make_token("gov_operator", tenant=au.DB_TENANT_AGENCY)
        r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
        assert r.status_code == 404


async def test_download_non_export_role_forbidden(client, make_incident, monkeypatch) -> None:
    _env_bucket(monkeypatch)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    ev = await _add_evidence(iid, au.DB_TENANT_PRIV)
    tok = au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV)
    r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
    assert r.status_code == 403


async def test_download_no_bucket_503(client, make_incident, monkeypatch) -> None:
    monkeypatch.delenv("TAKAB_API_EVIDENCE_BUCKET", raising=False)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    ev = await _add_evidence(iid, au.DB_TENANT_PRIV)
    tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
    r = await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))
    assert r.status_code == 503


# ═══════════════ [T-7.54] el freno propio de la descarga, en los DOS sentidos
#
# ⚠️ QUÉ PROTEGE, MEDIDO el 2026-09-20 sobre el bucket real y no supuesto: el
# objeto más grande es un miniSEED de 204 KB, una foto son 53 KB y el bucket
# ENTERO pesa 6.8 MB. A ~$0.09/GB, descargarlo completo mil veces cuesta menos de
# un dólar — así que un tope «contra el egreso de S3», que es lo que la ficha
# suponía, habría sido un número con aire de medido que no mide nada. Lo que este
# freno acota es la EXTRACCIÓN EN BLOQUE con un token robado.


async def _descargar(client, ev, tok):  # noqa: ANN001, ANN202
    return await client.post(f"/evidence/{ev}/download", headers=au.bearer(tok))


async def test_el_freno_de_descarga_CORTA_al_rebasar_el_techo(
    client, make_incident, monkeypatch
) -> None:
    """Que el tope existe y muerde."""
    _env_bucket(monkeypatch)
    monkeypatch.setenv("TAKAB_API_EVIDENCE_DOWNLOAD_RATE_USER_PER_MIN", "3")
    with mock_aws():
        _make_bucket()
        # CERRADO a propósito: un incidente EN CURSO no se frena nunca, y ése es
        # el caso del test de abajo.
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, state="closed")
        ev = await _add_evidence(iid, au.DB_TENANT_PRIV, kind="miniseed", s3_key="e/a.mseed")
        tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)

        codigos = [(await _descargar(client, ev, tok)).status_code for _ in range(5)]

    assert codigos[:3] == [200, 200, 200], f"el freno cortó antes de tiempo: {codigos}"
    assert codigos[3] == 429, f"el freno NO cortó al rebasar el techo: {codigos}"


async def test_el_freno_NO_cae_sobre_la_evidencia_de_un_incidente_EN_CURSO(
    client, make_incident, monkeypatch
) -> None:
    """⚠️ La mitad que de verdad importa, y la que este repositorio ya rompió dos veces.

    Es la doctrina que `T-5.18` tuvo que aplicarse a sí misma y que `T-7.45` vino
    a reparar: un tope de gasto que niega evidencia durante una emergencia es
    peor que no tener tope. Quien mira fotos de daños con el edificio evacuado no
    puede recibir un 429 por mirar deprisa.

    El techo se pone en 1 para que, sin la excepción, la SEGUNDA descarga fuera
    429. Con ella, las seis pasan.
    """
    _env_bucket(monkeypatch)
    monkeypatch.setenv("TAKAB_API_EVIDENCE_DOWNLOAD_RATE_USER_PER_MIN", "1")
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, state="open")
        ev = await _add_evidence(iid, au.DB_TENANT_PRIV, kind="photo", s3_key="e/dano.jpg")
        tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)

        codigos = [(await _descargar(client, ev, tok)).status_code for _ in range(6)]

    assert codigos == [200] * 6, (
        "el freno negó evidencia de un incidente ABIERTO. Es exactamente el "
        f"defecto que T-7.45 tuvo que reparar en el otro freno: {codigos}"
    )


async def test_el_freno_de_descarga_NO_gasta_el_techo_de_GENERAR(
    client, make_incident, monkeypatch
) -> None:
    """La razón por la que `T-7.45` los desacopló, fijada desde este lado.

    Antes, descargar escribía `export_pdf` y seis descargas devolvían 429 a la
    primera generación de dictamen. Los dos frenos cuentan poblaciones distintas
    y esta prueba lo ata: las descargas dejan `download_<kind>` y ni una sola
    fila `export_pdf`.
    """
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, state="closed")
        ev = await _add_evidence(iid, au.DB_TENANT_PRIV, kind="photo", s3_key="e/x.jpg")
        tok = au.make_token("takab_superadmin", tenant=au.DB_TENANT_PRIV)
        for _ in range(4):
            assert (await _descargar(client, ev, tok)).status_code == 200

    verbos = await _audit_verbs(au.DB_TENANT_PRIV)
    assert "download_photo" in verbos
    assert "export_pdf" not in verbos, "descargar volvió a gastar el techo de generar"
