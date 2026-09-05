"""La subida del clip y las capturas (T-3.11.b).

El orden es lo que se prueba: pedir grant → PUT → borrar. Borrar antes de que el PUT
confirme perdería la única copia; no borrar después llenaría la microSD de la que arranca
el camino de vida.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from takab_edge.cctv.cliente import ClienteCctv
from takab_edge.cctv.onvif import Fuentes
from takab_edge.config.settings import CctvConfig
from takab_edge.security import SecurityManager

T0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
FUENTES = Fuentes(rtsp_principal="rtsp://c/main", rtsp_substream="rtsp://c/sub", snapshot=None)


class _Nube:
    """Doble del gabinete + S3: registra los grants pedidos y los PUT hechos."""

    def __init__(self, *, da_grant: bool = True, put_ok: bool = True) -> None:
        self.da_grant = da_grant
        self.put_ok = put_ok
        self.grants: list[dict] = []
        self.puts: list[tuple[str, int, str]] = []

    def pedir(self, **kw) -> dict | None:
        self.grants.append(kw)
        return (
            {"url": "https://s3/presigned", "key": "evidence/t/e/cctv-x.mp4"}
            if self.da_grant
            else None
        )

    def put(self, url: str, datos: bytes, tipo: str) -> bool:
        self.puts.append((url, len(datos), tipo))
        return self.put_ok


def _cliente(tmp: Path, nube: _Nube | None, **cfg) -> ClienteCctv:
    return ClienteCctv(
        config=CctvConfig(**cfg),
        fuentes=FUENTES,
        directorio=tmp,
        leer_status=lambda: {"test_mode": {"active": True}},  # sin disparos: solo subida
        correr=lambda cmd: 0,
        reloj=lambda: T0,
        pedir_grant=nube.pedir if nube else None,
        subir=nube.put if nube else None,
    )


def _sembrar_clip(tmp: Path, contenido: bytes = b"videobytes") -> Path:
    pend = tmp / "pendientes"
    pend.mkdir(parents=True, exist_ok=True)
    clip = pend / "clip-20260829T120000Z-ev-aaa.mp4"
    clip.write_bytes(contenido)
    clip.with_suffix(".json").write_text(
        json.dumps(
            {
                "event_id": "ev-aaa",
                "desde": (T0 - timedelta(seconds=60)).isoformat(),
                "hasta": (T0 + timedelta(seconds=600)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    return clip


def _sembrar_captura(tmp: Path) -> Path:
    pend = tmp / "pendientes"
    pend.mkdir(parents=True, exist_ok=True)
    jpg = pend / "still-20260829T121500Z-ev-aaa.jpg"
    jpg.write_bytes(b"jpegbytes")
    return jpg


# ------------------------------------------------------------- sin conexión


def test_sin_subidor_no_se_sube_nada_y_no_se_pierde_nada(tmp_path: Path) -> None:
    """Es el modo con el que un gabinete graba sin nube: todo queda en disco."""
    clip = _sembrar_clip(tmp_path)
    _cliente(tmp_path, None).paso()
    assert clip.exists()


def test_sin_grant_el_clip_SIGUE_pendiente(tmp_path: Path) -> None:
    """Sin enlace es exactamente cuando hay sismos: la evidencia no se tira."""
    clip = _sembrar_clip(tmp_path)
    nube = _Nube(da_grant=False)
    _cliente(tmp_path, nube).paso()
    assert clip.exists()
    assert nube.puts == []


def test_si_el_PUT_falla_el_clip_SIGUE_pendiente(tmp_path: Path) -> None:
    clip = _sembrar_clip(tmp_path)
    nube = _Nube(put_ok=False)
    _cliente(tmp_path, nube).paso()
    assert clip.exists()
    assert clip.with_suffix(".json").exists()


def test_a_la_primera_negativa_se_para_y_no_se_intentan_los_demas(tmp_path: Path) -> None:
    """Si la nube no da grant es que no hay enlace; insistir con los otros nueve solo
    gasta el tick."""
    pend = tmp_path / "pendientes"
    pend.mkdir(parents=True)
    for i in range(4):
        (pend / f"clip-2026082{i}T120000Z-ev-{i}.mp4").write_bytes(b"x")
        (pend / f"clip-2026082{i}T120000Z-ev-{i}.json").write_text(
            json.dumps({"event_id": f"ev-{i}", "desde": T0.isoformat(), "hasta": T0.isoformat()}),
            encoding="utf-8",
        )
    nube = _Nube(da_grant=False)
    _cliente(tmp_path, nube).paso()
    assert len(nube.grants) == 1


# ------------------------------------------------------------- camino feliz


def test_el_clip_se_sube_y_se_borra_CON_su_metadato(tmp_path: Path) -> None:
    clip = _sembrar_clip(tmp_path)
    nube = _Nube()
    _cliente(tmp_path, nube).paso()
    assert not clip.exists()
    assert not clip.with_suffix(".json").exists()
    assert nube.puts == [("https://s3/presigned", len(b"videobytes"), "video/mp4")]


def test_el_grant_pide_el_sha256_DE_LOS_BYTES_REALES(tmp_path: Path) -> None:
    """La key lo lleva dentro, así que un sha inventado haría que la nube rechazara el
    objeto al comparar el hash — y el clip se perdería creyendo que subió."""
    contenido = b"un clip de verdad"
    _sembrar_clip(tmp_path, contenido)
    nube = _Nube()
    _cliente(tmp_path, nube).paso()
    assert nube.grants[0]["sha256"] == hashlib.sha256(contenido).hexdigest()


def test_el_grant_del_clip_lleva_su_ventana_y_su_evento(tmp_path: Path) -> None:
    _sembrar_clip(tmp_path)
    nube = _Nube()
    _cliente(tmp_path, nube).paso()
    g = nube.grants[0]
    assert g["mode"] == "cctv_clip"
    assert g["event_id"] == "ev-aaa"
    assert g["ts_from"] == T0 - timedelta(seconds=60)
    assert g["ts_to"] == T0 + timedelta(seconds=600)


def test_la_captura_saca_evento_e_instante_de_SU_NOMBRE(tmp_path: Path) -> None:
    """No llevan JSON al lado a propósito: son cientos por incidente y un sidecar por cada
    una multiplicaría los inodos sin añadir nada que el nombre no tenga."""
    jpg = _sembrar_captura(tmp_path)
    nube = _Nube()
    _cliente(tmp_path, nube).paso()
    g = nube.grants[0]
    assert g["mode"] == "cctv_still"
    assert g["event_id"] == "ev-aaa"
    assert g["ts_from"] == g["ts_to"] == datetime(2026, 8, 29, 12, 15, 0, tzinfo=UTC)
    assert not jpg.exists()
    assert nube.puts[0][2] == "image/jpeg"


def test_un_clip_sin_metadato_no_se_sube_a_ciegas(tmp_path: Path) -> None:
    pend = tmp_path / "pendientes"
    pend.mkdir(parents=True)
    huerfano = pend / "clip-20260829T120000Z-ev-x.mp4"
    huerfano.write_bytes(b"x")
    nube = _Nube()
    _cliente(tmp_path, nube).paso()
    assert huerfano.exists()
    assert nube.grants == []


# ------------------------------------------------- la firma del grant (HMAC)


def test_el_dominio_cctv_esta_SEPARADO_del_de_comandos_y_config() -> None:
    """Una firma de comando no puede valer como petición de grant ni al revés."""
    s = SecurityManager(hmac_key=b"clave-de-sitio")
    cuerpo = b'{"mode":"cctv_clip"}'
    firma = s.sign_cctv(cuerpo)
    assert s.verify_cctv(cuerpo, firma)
    assert not s.verify_cctv(cuerpo, s.sign_config(cuerpo, 1))
    assert not s.verify_cctv(cuerpo, s.sign_catalog(cuerpo, 1))


def test_la_firma_cubre_el_cuerpo_EXACTO() -> None:
    s = SecurityManager(hmac_key=b"clave-de-sitio")
    firma = s.sign_cctv(b'{"sha256":"aaa"}')
    assert not s.verify_cctv(b'{"sha256":"bbb"}', firma)


def test_sin_firma_se_rechaza() -> None:
    s = SecurityManager(hmac_key=b"clave-de-sitio")
    assert not s.verify_cctv(b"{}", "")
