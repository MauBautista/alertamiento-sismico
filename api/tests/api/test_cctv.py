"""T-3.12.c · `GET /incidents/{id}/cctv` y la descarga del clip.

Los tres estados que este endpoint tiene que saber distinguir —sin cámara, con clip y sin
análisis, con análisis— se ven igual si no se pregunta, y significan cosas opuestas: «este
edificio no tiene CCTV» frente a «lo tiene y no grabó» frente a «grabó y nadie miró».
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.routers.cctv import router as cctv_router
from takab_api.schemas.cctv import ANALISIS_PENDIENTE, NO_CCTV

_T0 = datetime(2026, 8, 30, 10, 0, 0, tzinfo=UTC)


def _token(role: str = "soc_operator", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


@pytest.fixture(autouse=True)
def _montar(app):
    app.include_router(cctv_router)
    return app


async def _camara(tenant: str, site: str) -> str:
    async with get_engine().begin() as conn:
        fila = await conn.execute(
            text(
                "INSERT INTO cameras (tenant_id, site_id, name, enabled) "
                "VALUES (:t, :s, 'punto de reunión', true) RETURNING camera_id"
            ),
            {"t": tenant, "s": site},
        )
        return str(fila.scalar_one())


async def _clip(tenant: str, incidente: str, *, podado: bool = False) -> str:
    async with get_engine().begin() as conn:
        fila = await conn.execute(
            text(
                "INSERT INTO cctv_clips (tenant_id, incident_id, s3_key, sha256, "
                " size_bytes, started_at, ended_at, coverage) "
                "VALUES (:t, :i, :k, :h, 1024, :a, :b, 0.98) RETURNING clip_id"
            ),
            {
                "t": tenant,
                "i": incidente,
                "k": f"evidence/{tenant}/ev/cctv-x.mp4",
                "h": "a" * 64,
                "a": _T0 - timedelta(seconds=60),
                "b": _T0 + timedelta(seconds=600),
            },
        )
        clip = str(fila.scalar_one())
        if podado:
            await conn.execute(
                text("UPDATE cctv_clips SET s3_key = NULL, purged_at = now() WHERE clip_id = :c"),
                {"c": clip},
            )
        return clip


async def _metricas(tenant: str, incidente: str, **campos) -> None:
    base = {
        "t50_s": 30.0,
        "t90_s": 50.0,
        "peak_n": 40,
        "peak_at": _T0 + timedelta(seconds=50),
        "reentry_start_at": _T0 + timedelta(seconds=90),
        "dictamen_lag_s": 200.0,
        "reentry_lag_s": -110.0,
        "checkin_count": 44,
    }
    base.update(campos)
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO cctv_evacuation_metrics (incident_id, provenance, tenant_id, "
                " t50_s, t90_s, peak_n, peak_at, reentry_start_at, dictamen_lag_s, "
                " reentry_lag_s, checkin_count) "
                "VALUES (:i,'final',:t,:t50,:t90,:pk,:pat,:rs,:dl,:rl,:cc)"
            ),
            {
                "i": incidente,
                "t": tenant,
                "t50": base["t50_s"],
                "t90": base["t90_s"],
                "pk": base["peak_n"],
                "pat": base["peak_at"],
                "rs": base["reentry_start_at"],
                "dl": base["dictamen_lag_s"],
                "rl": base["reentry_lag_s"],
                "cc": base["checkin_count"],
            },
        )


async def _get(client, incidente: str, token=None):
    return await client.get(f"/incidents/{incidente}/cctv", headers=token or _token())


# ------------------------------------------------------------- los tres estados


async def test_sin_camara_lo_DICE_y_no_pinta_una_seccion_vacia(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    body = (await _get(client, iid)).json()
    assert body["con_camara"] is False
    assert body["estado"] == NO_CCTV


async def test_con_clip_y_sin_analisis_dice_PENDIENTE_y_no_un_cero(client, make_incident) -> None:
    """Un fallback no puede ser `ok`. Hoy es el caso normal: el Lambda de conteo espera
    ventana AWS."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    await _camara(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _clip(au.DB_TENANT_PRIV, iid)
    body = (await _get(client, iid)).json()
    assert body["estado"] == ANALISIS_PENDIENTE
    assert body["evacuacion"] is None
    assert len(body["clips"]) == 1 and body["clips"][0]["disponible"] is True


async def test_con_camara_y_sin_clip_no_es_lo_mismo_que_sin_camara(client, make_incident) -> None:
    """«Este edificio no tiene CCTV» y «lo tiene y no grabó» son fallos distintos."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    await _camara(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    body = (await _get(client, iid)).json()
    assert body["con_camara"] is True
    assert body["estado"] != NO_CCTV and "sin clip" in body["estado"]


# ------------------------------------------------------------------ las métricas


async def test_las_metricas_llegan_con_su_veredicto_en_PALABRAS(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    await _camara(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _clip(au.DB_TENANT_PRIV, iid)
    await _metricas(au.DB_TENANT_PRIV, iid)
    evac = (await _get(client, iid)).json()["evacuacion"]
    assert evac["t90_s"] == 50.0
    # La latencia negativa NO es un número en una tabla: es un hallazgo de seguridad.
    assert evac["reingreso_antes_del_dictamen"] is True
    assert "sin certificación de habitabilidad" in evac["veredicto_reingreso"]


async def test_la_sacudida_del_SISMOMETRO_viaja_al_lado_de_t90(client, make_incident) -> None:
    """No sale de la cámara. El dato útil no es ninguno de los dos por separado."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "UPDATE incidents SET max_pga_g = 0.187, max_pgv_cms = 12.4 WHERE incident_id = :i"
            ),
            {"i": iid},
        )
    await _metricas(au.DB_TENANT_PRIV, iid)
    correlacion = (await _get(client, iid)).json()["evacuacion"]["correlacion"]
    assert "PGA 0.187 g" in correlacion and "50 s" in correlacion


async def test_el_aforo_y_el_pase_de_lista_se_cruzan_sin_promediarse(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    await _metricas(au.DB_TENANT_PRIV, iid)
    d = (await _get(client, iid)).json()["discrepancia"]
    assert (d["aforo_camara"], d["checkins"], d["diferencia"]) == (40, 44, -4)
    assert "MÁS en el pase de lista" in d["lectura"]
    assert "promedio" not in d


# ------------------------------------------------------------- las cuatro capturas


async def test_los_cuatro_papeles_SIEMPRE_salen_aunque_no_haya_foto(client, make_incident) -> None:
    """Una fila ausente se confunde con una sección que no se generó."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    capturas = (await _get(client, iid)).json()["capturas"]
    assert [c["papel"] for c in capturas] == ["pre", "egress", "peak", "reentry"]
    assert all(c["still_id"] is None and c["razon"] for c in capturas)


# ------------------------------------------------- la poda y la cadena de custodia


async def test_un_clip_PODADO_conserva_su_huella_y_sus_horas(client, make_incident) -> None:
    """El hecho sobrevive, la imagen no: el reporte puede seguir verificándose contra un
    objeto que ya no existe."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    await _clip(au.DB_TENANT_PRIV, iid, podado=True)
    clip = (await _get(client, iid)).json()["clips"][0]
    assert clip["disponible"] is False
    assert clip["purged_at"] is not None
    assert clip["sha256"] == "a" * 64
    assert clip["started_at"] is not None


async def test_descargar_un_clip_podado_da_410_y_no_404(client, make_incident) -> None:
    """Un 404 diría «nunca hubo nada», que es falso y borra la cadena de custodia."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    clip = await _clip(au.DB_TENANT_PRIV, iid, podado=True)
    resp = await client.post(f"/cctv/clips/{clip}/download", headers=_token())
    assert resp.status_code == 410
    assert "retención de vídeo" in resp.json()["detail"]


# ------------------------------------------------------------------ los permisos


async def test_el_inspector_ve_las_metricas_pero_NO_descarga_el_clip(client, make_incident) -> None:
    """`B.4`: ver vídeo no es ver telemetría. Un perito estructural no necesita once
    minutos de caras para decir si el edificio es habitable."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    clip = await _clip(au.DB_TENANT_PRIV, iid)
    inspector = _token("inspector")
    assert (await _get(client, iid, inspector)).status_code == 200
    resp = await client.post(f"/cctv/clips/{clip}/download", headers=inspector)
    assert resp.status_code == 403


async def test_gobierno_no_ve_ni_las_metricas(client, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_T0)
    resp = await _get(client, iid, _token("gov_operator"))
    assert resp.status_code == 403


async def test_un_incidente_de_otro_tenant_da_404_y_no_403(client, make_incident) -> None:
    """Un 403 confirmaría que existe."""
    ajeno = await make_incident(au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2, opened_at=_T0)
    assert (await _get(client, ajeno)).status_code == 404
