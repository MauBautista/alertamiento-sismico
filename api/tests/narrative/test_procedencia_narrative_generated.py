"""T-7.26 · `narrative_generated`: el registro de procedencia de la IA, por fin con guarda.

Es la fila que contesta, meses después y ante quien pregunte, cómo se produjo la prosa
de un dictamen firmado: qué proveedor, qué modelo, con qué instrucciones, qué devolvió,
cuánto costó y —si no redactó la IA— por qué no. `audit_log` no se poda nunca (regla de
oro 11), así que esta fila es permanente; que fuera correcta dependía de que nadie la
rompiera sin darse cuenta, y **no tenía ni una prueba en todo el repositorio**.

Cuánto la nombraba nadie, re-medido sobre el último commit —que es el estado de antes de
esta ficha— con `git grep -c narrative_generated 3a72ac1`: **dos sitios de código**
(`narrative/base.py` y `routers/reports.py`), **cuatro líneas en dos documentos**
(`TASKS.md` ×3 y `PLAN-PROTOTIPO-FUNCIONAL.md` ×1) y **cero tests**.

⚠️ Aquí ponía «tres sitios de código y tres de documentación, medido con grep antes de
escribir esto», y el grep no daba eso. Re-medido y escrito lo que salió: una cifra con
procedencia falsa es peor que ninguna cifra, porque invita a no volver a medir.

Dos cosas se fijan aquí:

1. **La fila se escribe, con el `tenant_id` del incidente y colgada de la evidencia.**
2. **Control negativo: con la clave IRRESOLUBLE el reporte SALE y DICE que la narrativa
   está degradada.** No 500, no silencio: 201 con su papel y su razón escrita.

⚠️ El punto 2 **no es el criterio 4 de la ficha**, aunque se escribió como si lo fuera.
El criterio dice «con la clave REVOCADA», que es otro camino: una clave revocada existe,
se lee, viaja en la cabecera y vuelve con un `401` — o sea que recorre el cliente HTTP
entero. Un secreto irresoluble ni siquiera abre un socket. El criterio literal lo cierra
`test_degradacion_declarada.py::test_con_la_clave_REVOCADA_el_papel_dice_NARRATIVA_DEGRADADA`;
lo de aquí es el caso del primer día en la nube, que también hace falta.

El censo de claves se DERIVA de los campos de `Narrative`. Enumerarlas a mano es
exactamente cómo un campo nuevo de procedencia acabaría sin llegar nunca a la bitácora.
"""

from __future__ import annotations

import dataclasses
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from moto import mock_aws
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.narrative.base import MOTIVO_CLAVE_ILEGIBLE, Narrative
from takab_api.narrative.prompts import SECTION_TITLES, prompt_version
from takab_api.routers.reports import router as reports_router

BUCKET = "takab-dev-evidence"
_REGION = "us-east-2"


@contextmanager
def _espia_del_papel():  # noqa: ANN202
    """Todo lo que el render pasó por `text_of` DURANTE la petición.

    El PDF acaba en moto-S3 y del PDF no se raspa texto (doctrina del repositorio): lo
    que demuestra el espía es que la llamada que imprime el aviso SE HIZO con ese texto.
    Se monta alrededor del `client.post` porque aquí el render corre DENTRO del router,
    no en el test.

    ⚠️ La BASE, no la subclase: misma nota que en
    `tests/documentos/test_membrete_compartido.py`.
    """
    from takab_api.documentos.membrete import MembretePDF  # noqa: PLC0415

    visto: list[str] = []
    original = MembretePDF.text_of

    def espia(self: MembretePDF, value: str) -> str:
        visto.append(value)
        return original(self, value)

    MembretePDF.text_of = espia  # type: ignore[method-assign]
    try:
        yield visto
    finally:
        MembretePDF.text_of = original  # type: ignore[method-assign]


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(reports_router)
    return application


def _env_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_EVIDENCE_BUCKET", BUCKET)
    monkeypatch.setenv("TAKAB_API_AWS_REGION", _REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", _REGION)


def _make_bucket() -> None:
    import boto3

    boto3.client("s3", region_name=_REGION).create_bucket(
        Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": _REGION}
    )


async def _fila_de_procedencia(tenant_id: str) -> dict:
    async with get_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT actor, object, meta FROM audit_log "
                        "WHERE verb = 'narrative_generated' AND tenant_id = CAST(:t AS uuid) "
                        "ORDER BY ts DESC LIMIT 1"
                    ),
                    {"t": tenant_id},
                )
            )
            .mappings()
            .first()
        )
    assert row is not None, "no se escribió la fila de procedencia de la narrativa"
    return dict(row)


# ── el censo de claves, DERIVADO ──────────────────────────────────────────────


def test_la_procedencia_lleva_TODOS_los_campos_de_la_narrativa() -> None:
    """Un campo nuevo en `Narrative` que no llegue a la bitácora pone esto en rojo.

    `sections` es la excepción declarada: a la fila van los TÍTULOS, no la prosa —el
    texto ya queda congelado en el PDF, que es evidencia con sha256, y duplicarlo en
    una tabla que no se poda jamás sería guardar el documento dos veces.
    """
    campos = {f.name for f in dataclasses.fields(Narrative)}
    prov = Narrative(sections=(("Resumen ejecutivo", "x"),), provider="deterministic").provenance()
    faltan = campos - set(prov)
    assert not faltan, f"campos de Narrative sin llegar a la auditoría: {faltan}"
    assert prov["sections"] == ["Resumen ejecutivo"]


def test_la_procedencia_declara_la_version_del_prompt_y_el_hash_de_la_salida() -> None:
    """Los dos campos que la ficha pide por su nombre."""
    prov = Narrative(sections=(), provider="openrouter").provenance()
    assert "prompt_version" in prov and "output_sha256" in prov


# ── la fila, escrita por el router de verdad ──────────────────────────────────


async def test_el_verbo_se_ESCRIBE_con_la_procedencia_de_la_prosa(
    client, make_incident, make_dictamen, monkeypatch
) -> None:
    _env_bucket(monkeypatch)
    with mock_aws():
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        await make_dictamen(au.DB_TENANT_PRIV, iid, status="inhabit_monitor")
        tok = au.make_token("inspector", tenant=au.DB_TENANT_PRIV)
        r = await client.post(f"/incidents/{iid}/report", headers=au.bearer(tok))
        assert r.status_code == 201, r.text

    fila = await _fila_de_procedencia(au.DB_TENANT_PRIV)
    assert fila["object"].startswith("evidence:"), "la procedencia cuelga del PDF que describe"
    assert fila["actor"].startswith("user:")
    meta = fila["meta"]
    assert meta["provider"] == "deterministic"
    assert meta["sections"] == list(SECTION_TITLES)
    # Con la perilla apagada no hubo prompt ni salida, y la fila lo dice en vez de
    # fingir que se consultó a un modelo.
    assert meta["degraded_reason"] is None
    assert meta["prompt_version"] is None and meta["output_sha256"] is None


async def test_con_la_clave_IRRESOLUBLE_el_reporte_sale_y_DICE_que_esta_degradado(
    client, make_incident, monkeypatch
) -> None:
    """El control negativo de la ficha, extremo a extremo.

    El secreto no existe (moto responde `ResourceNotFoundException`, que es la misma
    forma que un `AccessDenied` del primer día en la nube). Lo que se exige: 201 con su
    PDF, y la razón escrita tanto en la bitácora como en el papel.

    ⚠️ Esto último lo prometía el docstring y el test solo miraba la bitácora: el PDF
    se subía a moto-S3 y nadie lo abría — la cadena 'NARRATIVA DEGRADADA' no aparecía en
    todo el fichero. Era el documento desmintiéndose cuatro líneas más abajo, que es
    justo lo que este repositorio caza. Hoy el espía del render lo mide.
    """
    _env_bucket(monkeypatch)
    monkeypatch.setenv("TAKAB_API_OPENROUTER_ENABLED", "true")
    monkeypatch.setenv("TAKAB_API_OPENROUTER_MODEL", "anthropic/claude-sonnet-5")
    monkeypatch.setenv("TAKAB_API_OPENROUTER_SECRET_ID", "takab/dev/openrouter")
    monkeypatch.delenv("TAKAB_API_OPENROUTER_API_KEY", raising=False)
    with mock_aws(), _espia_del_papel() as dibujado:
        _make_bucket()
        iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        tok = au.make_token("inspector", tenant=au.DB_TENANT_PRIV)
        r = await client.post(f"/incidents/{iid}/report", headers=au.bearer(tok))
        assert r.status_code == 201, r.text

    # EL PAPEL. Lo que lee quien recibe el dictamen, no lo que sabe la base.
    papel = "\n".join(dibujado)
    assert "NARRATIVA DEGRADADA" in papel, "el PDF salió sin declarar que la IA no redactó"
    assert MOTIVO_CLAVE_ILEGIBLE in papel, "«degradada» a secas no dice dónde está el fallo"

    meta = (await _fila_de_procedencia(au.DB_TENANT_PRIV))["meta"]
    assert meta["provider"] == "deterministic"
    assert MOTIVO_CLAVE_ILEGIBLE in (meta["degraded_reason"] or "")
    assert meta["sections"] == list(SECTION_TITLES), "la prosa determinista salió igual"
    # No se consultó a ningún modelo: no hay prompt que versionar ni salida que sellar.
    assert meta["prompt_version"] is None and meta["output_sha256"] is None
    assert prompt_version(), "la versión existe; lo que no hay es llamada"
