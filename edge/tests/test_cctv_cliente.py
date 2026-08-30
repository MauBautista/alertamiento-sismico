"""La máquina de estados del cliente CCTV (T-3.11): anillo → clip → goteo.

Todo el I/O entra por constructor, así que aquí no hay cámara, ni ffmpeg, ni edge.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from takab_edge.cctv.cliente import ClienteCctv, Fase
from takab_edge.cctv.onvif import Fuentes
from takab_edge.cctv.recorder import SEGMENTO_S, nombre_de
from takab_edge.config.settings import CctvConfig

T0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
FUENTES = Fuentes(
    rtsp_principal="rtsp://takab:secreta@192.168.3.50/main",
    rtsp_substream="rtsp://takab:secreta@192.168.3.50/sub",
    snapshot="http://takab:secreta@192.168.3.50/snap.jpg",
)


class _Ffmpeg:
    """Doble de ffmpeg: registra los comandos y crea el fichero de salida."""

    def __init__(self, codigo: int = 0) -> None:
        self.codigo = codigo
        self.comandos: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> int:
        self.comandos.append(cmd)
        if self.codigo == 0:
            Path(cmd[-1]).write_bytes(b"\0" * 512)
        return self.codigo


def _status(*, tier: str = "evacuate_or_hold", event_id: str = "ev-1", at: datetime = T0) -> dict:
    return {
        "test_mode": {"active": False},
        "drill": {"active": False},
        "events": [
            {"at": at.isoformat(), "to_tier": tier, "source": "sasmex", "event_id": event_id}
        ],
    }


def _anillo(directorio: Path, desde: datetime, cuantos: int) -> None:
    for i in range(cuantos):
        (directorio / nombre_de(desde + timedelta(seconds=i * SEGMENTO_S))).write_bytes(
            b"\0" * 1024
        )


def _cliente(
    tmp_path: Path, ahora: list[datetime], estado: dict, ffmpeg: _Ffmpeg, **cfg
) -> ClienteCctv:
    return ClienteCctv(
        config=CctvConfig(**cfg),
        fuentes=FUENTES,
        directorio=tmp_path,
        leer_status=lambda: estado,
        correr=ffmpeg,
        reloj=lambda: ahora[0],
    )


# ------------------------------------------------------------------- ocioso


def test_sin_alerta_no_pasa_nada_pero_el_anillo_se_poda(tmp_path: Path) -> None:
    _anillo(tmp_path, T0 - timedelta(seconds=600), 60)
    reloj = [T0]
    c = _cliente(tmp_path, reloj, {"test_mode": {"active": False}}, _Ffmpeg(), ring_s=180.0)
    assert c.paso() is Fase.OCIOSO
    assert len(list(tmp_path.glob("seg-*.mp4"))) < 60  # podó lo viejo
    assert not list((tmp_path / "pendientes").glob("clip-*.mp4"))


def test_el_edge_caido_no_tumba_al_cliente_y_el_anillo_sigue(tmp_path: Path) -> None:
    """Que el panel no conteste es asunto del edge, no nuestro. Se sigue grabando."""

    def explota() -> dict:
        raise ConnectionRefusedError("el edge se está reiniciando")

    c = ClienteCctv(
        config=CctvConfig(),
        fuentes=FUENTES,
        directorio=tmp_path,
        leer_status=explota,
        correr=_Ffmpeg(),
        reloj=lambda: T0,
    )
    assert c.paso() is Fase.OCIOSO  # no lanza


# --------------------------------------------------------------------- clip


def test_el_clip_se_corta_cuando_su_ventana_ya_paso_entera(tmp_path: Path) -> None:
    """Cortarlo antes daría un fichero al que le falta el final del minuto que importa."""
    _anillo(tmp_path, T0 - timedelta(seconds=120), 90)  # cubre T0−120 .. T0+780
    reloj = [T0]
    ff = _Ffmpeg()
    c = _cliente(tmp_path, reloj, _status(), ff, clip_pre_s=60.0, clip_post_s=600.0)

    assert c.paso() is Fase.CLIP
    assert not list((tmp_path / "pendientes").glob("clip-*.mp4"))  # todavía no

    reloj[0] = T0 + timedelta(seconds=600)
    c.paso()
    clips = list((tmp_path / "pendientes").glob("clip-*.mp4"))
    assert len(clips) == 1 and "ev-1" in clips[0].name


def test_el_clip_recorta_exactamente_la_ventana_pedida(tmp_path: Path) -> None:
    _anillo(tmp_path, T0 - timedelta(seconds=120), 90)
    reloj = [T0]
    ff = _Ffmpeg()
    c = _cliente(tmp_path, reloj, _status(), ff, clip_pre_s=60.0, clip_post_s=600.0)
    c.paso()
    reloj[0] = T0 + timedelta(seconds=600)
    c.paso()
    cmd = next(x for x in ff.comandos if "-f" in x and "concat" in x)
    assert cmd[cmd.index("-t") + 1] == "660"  # 60 antes + 600 después


def test_el_metadato_NO_lleva_la_contrasena_de_la_camara(tmp_path: Path) -> None:
    """La URL RTSP trae usuario y clave, y ningún detector de PII del proyecto la reconoce:
    es una fuga que ningún censo ve."""
    _anillo(tmp_path, T0 - timedelta(seconds=120), 90)
    reloj = [T0]
    c = _cliente(tmp_path, reloj, _status(), _Ffmpeg(), clip_pre_s=60.0, clip_post_s=600.0)
    c.paso()
    reloj[0] = T0 + timedelta(seconds=600)
    c.paso()
    meta = next((tmp_path / "pendientes").glob("clip-*.json"))
    crudo = meta.read_text(encoding="utf-8")
    assert "secreta" not in crudo
    assert "takab:" not in crudo
    assert json.loads(crudo)["event_id"] == "ev-1"


def test_el_metadato_DECLARA_una_cobertura_incompleta(tmp_path: Path) -> None:
    """Un clip que dice cubrir T−60 s sin cubrirlo es una mentira en un reporte."""
    _anillo(tmp_path, T0 - timedelta(seconds=30), 70)  # solo 30 s de pre-roll de los 60
    reloj = [T0]
    c = _cliente(tmp_path, reloj, _status(), _Ffmpeg(), clip_pre_s=60.0, clip_post_s=600.0)
    c.paso()
    reloj[0] = T0 + timedelta(seconds=600)
    c.paso()
    meta = json.loads(
        next((tmp_path / "pendientes").glob("clip-*.json")).read_text(encoding="utf-8")
    )
    assert meta["cobertura"] < 1.0


def test_si_ffmpeg_falla_no_queda_un_clip_a_medias(tmp_path: Path) -> None:
    _anillo(tmp_path, T0 - timedelta(seconds=120), 90)
    reloj = [T0]
    c = _cliente(tmp_path, reloj, _status(), _Ffmpeg(codigo=1), clip_pre_s=60.0, clip_post_s=600.0)
    c.paso()
    reloj[0] = T0 + timedelta(seconds=600)
    c.paso()
    assert not list((tmp_path / "pendientes").glob("clip-*.mp4"))
    assert not list((tmp_path / "pendientes").glob("clip-*.json"))


def test_un_anillo_vacio_no_produce_clip_ni_revienta(tmp_path: Path) -> None:
    reloj = [T0]
    c = _cliente(tmp_path, reloj, _status(), _Ffmpeg(), clip_post_s=600.0)
    c.paso()
    reloj[0] = T0 + timedelta(seconds=600)
    c.paso()
    assert not list((tmp_path / "pendientes").glob("clip-*.mp4"))


def test_un_ring_s_menor_que_el_pre_roll_no_se_come_el_pre_roll(tmp_path: Path) -> None:
    """Configurar `ring_s=30` con `clip_pre_s=60` haría que la poda borrase el minuto
    anterior antes de que el clip pudiera usarlo. El suelo lo impide."""
    _anillo(tmp_path, T0 - timedelta(seconds=120), 90)
    reloj = [T0]
    c = _cliente(
        tmp_path, reloj, _status(), _Ffmpeg(), ring_s=30.0, clip_pre_s=60.0, clip_post_s=600.0
    )
    c.paso()
    quedan = list(tmp_path.glob("seg-*.mp4"))
    assert any(p.name <= nombre_de(T0 - timedelta(seconds=60)) for p in quedan)


# -------------------------------------------------------------------- goteo


def test_el_goteo_produce_capturas_al_ritmo_configurado(tmp_path: Path) -> None:
    _anillo(tmp_path, T0 - timedelta(seconds=120), 90)
    reloj = [T0]
    ff = _Ffmpeg()
    c = _cliente(
        tmp_path, reloj, _status(), ff, clip_pre_s=60.0, clip_post_s=600.0, still_interval_s=30.0
    )
    c.paso()
    reloj[0] = T0 + timedelta(seconds=600)
    assert c.paso() is Fase.GOTEO
    assert len(list((tmp_path / "pendientes").glob("still-*.jpg"))) == 1
    reloj[0] = T0 + timedelta(seconds=615)  # aún no toca
    c.paso()
    assert len(list((tmp_path / "pendientes").glob("still-*.jpg"))) == 1
    reloj[0] = T0 + timedelta(seconds=640)
    c.paso()
    assert len(list((tmp_path / "pendientes").glob("still-*.jpg"))) == 2


def test_el_goteo_usa_la_instantanea_si_la_camara_la_ofrece(tmp_path: Path) -> None:
    """Con `GetSnapshotUri` el goteo es un GET de un JPEG: cero decodificación de vídeo."""
    _anillo(tmp_path, T0 - timedelta(seconds=120), 90)
    reloj = [T0]
    ff = _Ffmpeg()
    c = _cliente(tmp_path, reloj, _status(), ff, clip_pre_s=60.0, clip_post_s=600.0)
    c.paso()
    reloj[0] = T0 + timedelta(seconds=600)
    c.paso()
    captura = next(x for x in ff.comandos if "-frames:v" in x)
    assert captura[captura.index("-i") + 1] == FUENTES.snapshot


def test_el_goteo_se_para_en_el_tope_y_cierra_la_sesion(tmp_path: Path) -> None:
    """Sin conteo local no se puede detectar el reingreso: lo ubica la nube en la serie."""
    _anillo(tmp_path, T0 - timedelta(seconds=120), 90)
    reloj = [T0]
    c = _cliente(
        tmp_path,
        reloj,
        _status(),
        _Ffmpeg(),
        clip_pre_s=60.0,
        clip_post_s=600.0,
        still_interval_s=30.0,
        max_stills=2,
    )
    c.paso()
    for n in (600, 640, 680):
        reloj[0] = T0 + timedelta(seconds=n)
        c.paso()
    assert c.sesion is None
    assert c.fase is Fase.OCIOSO
    assert len(list((tmp_path / "pendientes").glob("still-*.jpg"))) == 2


# ------------------------------------------------------------------ réplicas


def test_una_replica_cierra_la_sesion_anterior(tmp_path: Path) -> None:
    """La evidencia que importa es la de la réplica; dos goteos a la vez se pisarían."""
    _anillo(tmp_path, T0 - timedelta(seconds=120), 200)
    reloj = [T0]
    estado = _status()
    c = _cliente(tmp_path, reloj, estado, _Ffmpeg(), clip_pre_s=60.0, clip_post_s=600.0)
    c.paso()
    primera = c.sesion
    reloj[0] = T0 + timedelta(seconds=120)
    estado["events"] = _status(event_id="ev-2", at=reloj[0])["events"]
    c.paso()
    assert c.sesion is not None and c.sesion is not primera
    assert c.sesion.disparo.event_id == "ev-2"


def test_el_mismo_evento_no_reabre_sesion_tras_cerrarse(tmp_path: Path) -> None:
    _anillo(tmp_path, T0 - timedelta(seconds=120), 90)
    reloj = [T0]
    c = _cliente(
        tmp_path, reloj, _status(), _Ffmpeg(), clip_pre_s=60.0, clip_post_s=600.0, max_stills=1
    )
    c.paso()
    reloj[0] = T0 + timedelta(seconds=600)
    c.paso()
    assert c.sesion is None
    reloj[0] = T0 + timedelta(seconds=700)
    assert c.paso() is Fase.OCIOSO
    assert c.sesion is None


# ------------------------------------------------------------- cuota de clips


def test_los_clips_pendientes_no_pueden_llenar_la_microsd(tmp_path: Path) -> None:
    """Sin internet es exactamente cuando hay sismos, y esa tarjeta arranca el camino de vida."""
    pend = tmp_path / "pendientes"
    pend.mkdir()
    for i in range(9):
        (pend / f"clip-2026082{i}T000000Z-ev{i}.mp4").write_bytes(b"\0" * 100)
        (pend / f"clip-2026082{i}T000000Z-ev{i}.json").write_text("{}", encoding="utf-8")
    c = _cliente(tmp_path, [T0], {"test_mode": {"active": True}}, _Ffmpeg(), max_clips_pendientes=4)
    c.paso()
    assert len(list(pend.glob("clip-*.mp4"))) == 4
    assert len(list(pend.glob("clip-*.json"))) == 4  # el metadato se va con su clip


@pytest.mark.parametrize("modo", [{"active": True}, "basura", None])
def test_en_modo_prueba_no_se_abre_sesion_pase_lo_que_pase(tmp_path: Path, modo) -> None:
    estado = _status()
    estado["test_mode"] = modo
    c = _cliente(tmp_path, [T0], estado, _Ffmpeg())
    assert c.paso() is Fase.OCIOSO
    assert c.sesion is None


def test_la_poda_NO_se_come_el_material_del_clip_que_falta_por_cortar(tmp_path: Path) -> None:
    """El fallo que encontró el E2E, fijado aquí para que no vuelva.

    El clip abarca `clip_pre_s + clip_post_s` —660 s de fábrica— y el anillo dura `ring_s`
    —180—. Sin proteger la ventana de la sesión abierta, cuando llega el momento de
    recortar la poda ya se ha llevado los primeros ocho minutos: el clip sale con un 27 %
    de cobertura y lo declara honestamente, pero es un 27 % que nadie pidió.

    Los ocho tests unitarios de arriba pasaban igual porque todos cortaban el clip en un
    tick que aún no había podado tan atrás. Sólo recorrer la cadena entera lo enseñó.
    """
    _anillo(tmp_path, T0 - timedelta(seconds=180), 18 + 60)  # T0−180 .. T0+600
    reloj = [T0]
    c = _cliente(
        tmp_path, reloj, _status(), _Ffmpeg(), ring_s=180.0, clip_pre_s=60.0, clip_post_s=600.0
    )
    c.paso()  # abre sesión

    reloj[0] = T0 + timedelta(seconds=600)
    c.paso()  # poda + corte, en este orden

    meta = json.loads(next((tmp_path / "pendientes").glob("clip-*.json")).read_text("utf-8"))
    assert meta["cobertura"] == 1.0, "la poda se llevó parte de la ventana del clip"


def test_fuera_de_la_ventana_protegida_la_poda_SIGUE_podando(tmp_path: Path) -> None:
    """La protección es de la ventana, no de la sesión: lo viejo se sigue tirando o el
    anillo crecería sin techo durante las horas que dura un goteo."""
    _anillo(tmp_path, T0 - timedelta(seconds=900), 150)  # T0−900 .. T0+600
    reloj = [T0]
    c = _cliente(
        tmp_path, reloj, _status(), _Ffmpeg(), ring_s=180.0, clip_pre_s=60.0, clip_post_s=600.0
    )
    c.paso()
    quedan = sorted(p.name for p in tmp_path.glob("seg-*.mp4"))
    # Lo anterior a T0−180 no está protegido ni por edad: se fue.
    assert nombre_de(T0 - timedelta(seconds=900)) not in quedan
    # Y el pre-roll del clip sigue ahí.
    assert nombre_de(T0 - timedelta(seconds=60)) in quedan
