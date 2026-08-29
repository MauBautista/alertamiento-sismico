"""Key canónica y enrutado de los objetos de CCTV (T-3.11.b).

Dos cosas se prueban aquí y las dos duelen si se rompen en silencio:

* que la key caiga bajo ``evidence/`` —el único prefijo que el bucket notifica—, y
* que la **ventana del clip** viaje dentro del nombre, porque quien registra el objeto es
  la notificación de S3 y solo ve la key.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from takab_api.backfill.grants import canonical_key
from takab_api.backfill.objects import _partir_nombre_cctv
from takab_api.ingest.handlers import GatewayCtx

THING = "gw-cctv-test"
TENANT = "d0000000-0000-0000-0000-0000000000aa"
SHA = "b" * 64
DESDE = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
HASTA = datetime(2026, 8, 29, 12, 11, 0, tzinfo=UTC)


def _ctx() -> GatewayCtx:
    return GatewayCtx(
        gateway_id=uuid.uuid4(),
        gateway_serial=THING,
        iot_thing=THING,
        tenant_id=uuid.UUID(TENANT),
        tenant_code="dev",
        site_id=uuid.uuid4(),
        site_code="site",
        sensors={},
    )


def _payload(mode: str, **extra) -> dict:
    base = {
        "mode": mode,
        "event_id": "ev-abc",
        "sha256": SHA,
        "ts_from": DESDE.isoformat(),
        "ts_to": HASTA.isoformat(),
    }
    base.update(extra)
    return base


# ------------------------------------------------------------- key canónica


def test_el_clip_cae_bajo_el_prefijo_QUE_EL_BUCKET_NOTIFICA() -> None:
    """Una key bajo `cctv/…` aterrizaría y no la ingestaría nadie: el objeto existiría y
    el incidente no se enteraría."""
    bucket, key, tipo = canonical_key(_payload("cctv_clip"), _ctx(), THING)
    assert key.startswith(f"evidence/{TENANT}/ev-abc/")
    assert bucket == "evidence_bucket"
    assert tipo == "video/mp4"


def test_la_ventana_del_clip_viaja_DENTRO_de_la_key() -> None:
    """Sin ella, la fila del clip tendría que inventarse un inicio y un fin — y un dato
    inventado en una tabla de evidencia es peor que un hueco."""
    _b, key, _t = canonical_key(_payload("cctv_clip"), _ctx(), THING)
    assert "20260829T120000Z_20260829T121100Z" in key
    assert key.endswith(f"-{SHA}.mp4")


def test_la_captura_lleva_UN_instante_y_no_una_ventana() -> None:
    _b, key, tipo = canonical_key(_payload("cctv_still"), _ctx(), THING)
    assert key.endswith(f"still-20260829T120000Z-{SHA}.jpg")
    assert tipo == "image/jpeg"


def test_el_mismo_contenido_y_la_misma_ventana_dan_la_MISMA_key() -> None:
    """La idempotencia no depende de que nadie reintente: SQS entrega at-least-once."""
    a = canonical_key(_payload("cctv_clip"), _ctx(), THING)[1]
    b = canonical_key(_payload("cctv_clip"), _ctx(), THING)[1]
    assert a == b


@pytest.mark.parametrize(
    "roto",
    [
        {"sha256": "no-es-un-sha"},
        {"sha256": ""},
        {"event_id": ""},
        {"ts_from": "ayer"},
        {"ts_to": None},
    ],
)
def test_un_request_incompleto_no_produce_key(roto: dict) -> None:
    """Fail-closed: sin key no hay grant, y el gabinete reintenta en vez de subir a un
    sitio inventado."""
    assert canonical_key(_payload("cctv_clip", **roto), _ctx(), THING) is None


# ------------------------------------------------- vuelta: parsear el nombre


def test_la_nube_recupera_la_ventana_que_ella_misma_escribio() -> None:
    """Ida y vuelta: es lo único que garantiza que las dos mitades no se separen."""
    _b, key, _t = canonical_key(_payload("cctv_clip"), _ctx(), THING)
    es_clip, inicio, fin, sha = _partir_nombre_cctv(key.rsplit("/", 1)[-1])
    assert es_clip is True
    assert (inicio, fin, sha) == (DESDE, HASTA, SHA)


def test_ida_y_vuelta_tambien_para_la_captura() -> None:
    _b, key, _t = canonical_key(_payload("cctv_still"), _ctx(), THING)
    es_clip, inicio, fin, sha = _partir_nombre_cctv(key.rsplit("/", 1)[-1])
    assert es_clip is False
    assert inicio == fin == DESDE
    assert sha == SHA


@pytest.mark.parametrize(
    "nombre",
    [
        "cctv-sinventana.mp4",
        "cctv-20260829T120000Z-abc.mp4",  # falta el segundo extremo
        "cctv-ayer_hoy-abc.mp4",
        "still-nofecha-abc.jpg",
        "otra-cosa.mp4",
        "cctv-20260829T120000Z_20260829T121100Z-abc.mkv",
    ],
)
def test_un_nombre_que_no_cuadra_se_rechaza_en_vez_de_adivinarse(nombre: str) -> None:
    assert _partir_nombre_cctv(nombre) is None


def test_el_miniseed_de_siempre_no_se_confunde_con_un_clip() -> None:
    """Comparten prefijo `evidence/`; lo que los separa es el nombre."""
    assert _partir_nombre_cctv(f"{SHA}.mseed") is None
