"""T-2.113 · La evidencia forense se registra de forma IDEMPOTENTE.

Declarada como hueco por T-2.108: la cola offline reintenta, y el registro no
era idempotente. El defecto real medido aquí es peor que "una fila duplicada":

- ``POST /incidents/{id}/evidence`` generaba el ``evidence_id`` en el servidor,
  así que el cliente NO podía repetir el mismo registro.
- Y como ``uq_evidence_incident_sha256`` ya existe, el reintento de la MISMA
  foto chocaba contra el índice único: el cliente recibía un error de contrato,
  la cola lo marcaba ``failed`` (4xx ⇒ no recuperable) y **la fila quedaba en la
  base sin su blob en S3 para siempre** — evidencia registrada que jamás
  verifica (``verified=false``). Ese es el huérfano.

Regla de oro 3: nada se duplica al reconectar. Y regla de oro 5: aceptar un id
del cliente NO puede convertirse en una puerta entre incidentes ni entre
tenants — un ``DO NOTHING`` silencioso ante un id ajeno sería un fallo de
aislamiento disfrazado de idempotencia.
"""

from __future__ import annotations

import hashlib
import uuid

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from tests.api.test_mobile_core import _brig, _seed_zone_and_code

pytestmark = pytest.mark.anyio

BUCKET = "takab-evidence-idem-test"
_REGION = "us-east-2"


@pytest.fixture(autouse=True)
def _occupants_pool(monkeypatch: pytest.MonkeyPatch):
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


def _env_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_EVIDENCE_BUCKET", BUCKET)
    monkeypatch.setenv("TAKAB_API_AWS_REGION", _REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)


def _make_bucket() -> None:
    boto3.client("s3", region_name=_REGION).create_bucket(
        Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": _REGION}
    )


def _brig2(site_scope: str = au.DB_SITE_PRIV2) -> str:
    """Brigadista del OTRO tenant (fuga cross-tenant)."""
    return au.make_token(
        "brigadista",
        tenant=au.DB_TENANT_PRIV2,
        user_id=str(uuid.uuid4()),
        surface="mobile",
        site_scope=site_scope,
    )


async def _rows(incident_id: str) -> list[tuple[str, str, str]]:
    engine = get_engine()
    async with engine.begin() as conn:
        return [
            (str(r.evidence_id), r.s3_key, r.sha256)
            for r in (
                await conn.execute(
                    text(
                        "SELECT evidence_id, s3_key, sha256 FROM evidence_objects "
                        "WHERE incident_id = CAST(:i AS uuid) AND kind = 'photo'"
                    ),
                    {"i": incident_id},
                )
            ).all()
        ]


async def _row_count(evidence_id: str) -> int:
    engine = get_engine()
    async with engine.begin() as conn:
        return (
            await conn.execute(
                text("SELECT count(*) FROM evidence_objects WHERE evidence_id = CAST(:e AS uuid)"),
                {"e": evidence_id},
            )
        ).scalar_one()


async def test_reintento_de_la_cola_no_duplica_ni_deja_huerfana(
    base_data, make_incident, monkeypatch
) -> None:
    """CRITERIO · registrar dos veces el MISMO item no duplica fila.

    Y —lo que hace útil el arreglo— el reintento vuelve a recibir un
    ``upload_url`` sobre el MISMO ``s3_key``: la foto que no llegó a subirse en
    el primer intento sí sube en el segundo, en vez de quedarse la fila sin
    blob para siempre.
    """
    _env_bucket(monkeypatch)
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    photo = b"\xff\xd8\xff\xe0jpeg-con-marca-horneada"
    sha = hashlib.sha256(photo).hexdigest()
    evidence_id = str(uuid.uuid4())  # lo genera la COLA del dispositivo

    with mock_aws():
        _make_bucket()
        async with au.client_for(create_app()) as client:
            tok = _brig()
            body = {"evidence_id": evidence_id, "sha256": sha, "content_type": "image/jpeg"}

            primero = await client.post(
                f"/incidents/{incident_id}/evidence", json=body, headers=au.bearer(tok)
            )
            assert primero.status_code == 201, primero.text
            assert primero.json()["evidence_id"] == evidence_id

            # El PUT a S3 falló (o murió la red): la cola reintenta con el
            # MISMO id, que es justo el punto de la ficha.
            segundo = await client.post(
                f"/incidents/{incident_id}/evidence", json=body, headers=au.bearer(tok)
            )
            assert segundo.status_code == 200, segundo.text
            assert segundo.json()["evidence_id"] == evidence_id
            assert segundo.json()["upload_url"], "el reintento debe poder subir el blob"

    filas = await _rows(incident_id)
    assert len(filas) == 1, f"el reintento duplicó la evidencia: {filas}"
    assert filas[0][0] == evidence_id


async def test_el_reintento_apunta_al_mismo_objeto_de_s3(
    base_data, make_incident, monkeypatch
) -> None:
    """El ``s3_key`` es DETERMINISTA por evidencia: el segundo presignado sube
    al mismo objeto que verifica la fila (si no, la fila apuntaría a un key
    vacío y ``verify`` diría ``verified=false`` para siempre)."""
    _env_bucket(monkeypatch)
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    photo = b"\xff\xd8\xff\xe0otra-foto-forense"
    sha = hashlib.sha256(photo).hexdigest()
    evidence_id = str(uuid.uuid4())

    with mock_aws():
        _make_bucket()
        s3 = boto3.client("s3", region_name=_REGION)
        async with au.client_for(create_app()) as client:
            tok = _brig()
            body = {"evidence_id": evidence_id, "sha256": sha}
            await client.post(
                f"/incidents/{incident_id}/evidence", json=body, headers=au.bearer(tok)
            )
            # …el PUT del primer intento se pierde. Segundo intento:
            segundo = await client.post(
                f"/incidents/{incident_id}/evidence", json=body, headers=au.bearer(tok)
            )
            assert segundo.status_code == 200

            filas = await _rows(incident_id)
            assert len(filas) == 1
            s3.put_object(Bucket=BUCKET, Key=filas[0][1], Body=photo)

            ver = await client.post(f"/evidence/{evidence_id}/verify", headers=au.bearer(tok))
            assert ver.status_code == 200, ver.text
            assert ver.json()["verified"] is True


async def test_un_id_de_otro_incidente_no_se_traga_en_silencio(
    base_data, make_incident, monkeypatch
) -> None:
    """El id ajeno del MISMO tenant ⇒ 409, jamás ``DO NOTHING`` silencioso.

    Un ``DO NOTHING`` que devolviera 200 con la fila existente entregaría el
    ``evidence_id`` (y un PUT presignado) de la evidencia de OTRO incidente: no
    es idempotencia, es escritura cruzada. Y tampoco se crea fila nueva.
    """
    _env_bucket(monkeypatch)
    await _seed_zone_and_code()
    inc_a = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    inc_b = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    sha_a = hashlib.sha256(b"foto-del-incidente-A").hexdigest()
    sha_b = hashlib.sha256(b"foto-del-incidente-B").hexdigest()
    evidence_id = str(uuid.uuid4())

    with mock_aws():
        _make_bucket()
        async with au.client_for(create_app()) as client:
            tok = _brig()
            primero = await client.post(
                f"/incidents/{inc_a}/evidence",
                json={"evidence_id": evidence_id, "sha256": sha_a},
                headers=au.bearer(tok),
            )
            assert primero.status_code == 201

            colision = await client.post(
                f"/incidents/{inc_b}/evidence",
                json={"evidence_id": evidence_id, "sha256": sha_b},
                headers=au.bearer(tok),
            )
            assert colision.status_code == 409, colision.text

    assert await _rows(inc_b) == [], "no se crea fila en el incidente ajeno"
    assert len(await _rows(inc_a)) == 1
    assert await _row_count(evidence_id) == 1


async def test_un_id_de_otro_tenant_no_filtra_ni_sobrescribe(
    base_data, make_incident, monkeypatch
) -> None:
    """CRUCE DE TENANTS (regla de oro 5): el id de la evidencia de otro cliente
    ⇒ 409 sin cuerpo, sin ``s3_key`` y sin fila nueva. El 409 no distingue
    "existe en otro tenant" de "existe en otro incidente": el atacante tendría
    que acertar un UUIDv4 para llegar siquiera a ver ese 409."""
    _env_bucket(monkeypatch)
    await _seed_zone_and_code()
    inc_priv = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    inc_priv2 = await make_incident(au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2)
    sha = hashlib.sha256(b"foto-del-otro-cliente").hexdigest()
    evidence_id = str(uuid.uuid4())

    with mock_aws():
        _make_bucket()
        async with au.client_for(create_app()) as client:
            ajeno = await client.post(
                f"/incidents/{inc_priv2}/evidence",
                json={"evidence_id": evidence_id, "sha256": sha},
                headers=au.bearer(_brig2()),
            )
            assert ajeno.status_code == 201, ajeno.text

            # El vecino intenta reusar ESE id en SU propio incidente.
            intruso = await client.post(
                f"/incidents/{inc_priv}/evidence",
                json={"evidence_id": evidence_id, "sha256": sha},
                headers=au.bearer(_brig()),
            )
            assert intruso.status_code == 409, intruso.text
            assert "s3_key" not in intruso.text
            assert "upload_url" not in intruso.text

    assert await _rows(inc_priv) == [], "no se crea fila con el id de otro tenant"
    assert await _row_count(evidence_id) == 1, "la evidencia del otro tenant sigue intacta y sola"


async def test_mismo_id_con_otra_huella_es_conflicto(base_data, make_incident, monkeypatch) -> None:
    """Mismo ``evidence_id``, mismo incidente, SHA-256 distinto ⇒ 409.

    La tabla es append-only: no se puede corregir la huella guardada. Devolver
    un PUT presignado aquí dejaría subir un blob que ya no corresponde a lo
    declarado y ensuciaría la cadena de custodia (§2.3)."""
    _env_bucket(monkeypatch)
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    evidence_id = str(uuid.uuid4())

    with mock_aws():
        _make_bucket()
        async with au.client_for(create_app()) as client:
            tok = _brig()
            await client.post(
                f"/incidents/{incident_id}/evidence",
                json={
                    "evidence_id": evidence_id,
                    "sha256": hashlib.sha256(b"original").hexdigest(),
                },
                headers=au.bearer(tok),
            )
            otra = await client.post(
                f"/incidents/{incident_id}/evidence",
                json={"evidence_id": evidence_id, "sha256": hashlib.sha256(b"otra").hexdigest()},
                headers=au.bearer(tok),
            )
            assert otra.status_code == 409, otra.text

    filas = await _rows(incident_id)
    assert len(filas) == 1
    assert filas[0][2] == hashlib.sha256(b"original").hexdigest()


async def test_sin_id_de_cliente_la_misma_foto_sigue_siendo_una_sola_fila(
    base_data, make_incident, monkeypatch
) -> None:
    """Compatibilidad hacia atrás: un cliente viejo (sin ``evidence_id``) que
    re-registra la MISMA foto del MISMO incidente choca contra el índice único
    ``uq_evidence_incident_sha256`` que ya existía. Antes eso reventaba con un
    error de contrato y la fila se quedaba sin blob; ahora resuelve a la fila
    existente y devuelve un PUT presignado válido."""
    _env_bucket(monkeypatch)
    await _seed_zone_and_code()
    incident_id = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    sha = hashlib.sha256(b"cliente-viejo").hexdigest()

    with mock_aws():
        _make_bucket()
        async with au.client_for(create_app()) as client:
            tok = _brig()
            uno = await client.post(
                f"/incidents/{incident_id}/evidence",
                json={"sha256": sha},
                headers=au.bearer(tok),
            )
            assert uno.status_code == 201, uno.text
            dos = await client.post(
                f"/incidents/{incident_id}/evidence",
                json={"sha256": sha},
                headers=au.bearer(tok),
            )
            assert dos.status_code == 200, dos.text
            assert dos.json()["evidence_id"] == uno.json()["evidence_id"]
            assert dos.json()["upload_url"]

    assert len(await _rows(incident_id)) == 1
