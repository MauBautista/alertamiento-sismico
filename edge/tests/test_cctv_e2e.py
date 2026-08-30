"""El camino completo del CCTV, sin cámara, sin ffmpeg y sin AWS (T-3.11).

Es lo que el simulador existe para desbloquear: hasta ahora cada pieza tenía su test y
nadie había recorrido la cadena entera. Aquí se recorre —anillo, disparo, clip, metadato,
goteo, grant, subida— y se comprueba lo que solo se ve al final, que es si las piezas
encajan.

**Lo que NO acredita**, y conviene tenerlo delante: los segmentos del anillo no son vídeo
decodificable, así que nada de lo que solo un ffmpeg real puede fallar se prueba aquí. Eso
es `GATE-HW`, con la cámara delante.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from simulators.cctv import CamaraSimulada
from takab_edge.cctv.cliente import ClienteCctv, Fase
from takab_edge.config.settings import CctvConfig

T0 = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)
#: La historia que el simulador escribe y que el analizador tendrá que ver: sube, hace
#: pico y se vacía. Vive aquí y no en los píxeles, porque en los píxeles no está.
GUION = [0, 3, 12, 28, 40, 40, 33, 18, 6, 2, 1, 0]


class _Nube:
    """El gabinete + S3, en memoria: otorga grants y acepta los PUT."""

    def __init__(self) -> None:
        self.grants: list[dict] = []
        self.subidos: dict[str, bytes] = {}

    def pedir(self, **kw) -> dict:
        self.grants.append(kw)
        clave = f"evidence/t/{kw['event_id']}/{kw['mode']}-{kw['sha256'][:8]}"
        return {"url": f"https://s3.sim/{clave}", "key": clave}

    def subir(self, url: str, datos: bytes, tipo: str) -> bool:  # noqa: ARG002
        self.subidos[url] = datos
        return True


def _status(*, prueba: bool = False, tier: str = "evacuate_or_hold") -> dict:
    return {
        "test_mode": {"active": prueba},
        "drill": {"active": False},
        "events": [
            {"at": T0.isoformat(), "to_tier": tier, "source": "sasmex", "event_id": "ev-e2e"}
        ],
    }


def _armar(tmp: Path, nube: _Nube | None, estado: dict, reloj: list[datetime]):
    camara = CamaraSimulada(directorio=tmp, guion=GUION)
    cliente = ClienteCctv(
        config=CctvConfig(clip_pre_s=60.0, clip_post_s=600.0, still_interval_s=30.0, max_stills=6),
        fuentes=camara.fuentes(),
        directorio=tmp,
        leer_status=lambda: estado,
        correr=camara.correr,
        reloj=lambda: reloj[0],
        pedir_grant=nube.pedir if nube else None,
        subir=nube.subir if nube else None,
    )
    return camara, cliente


def test_de_la_señal_al_clip_subido_pasando_por_todo(tmp_path: Path) -> None:
    """El camino entero. Si esto pasa, las piezas encajan; los detalles los prueba cada una."""
    nube = _Nube()
    reloj = [T0]
    camara, cliente = _armar(tmp_path, nube, _status(), reloj)

    # El gabinete lleva tres minutos grabando cuando llega la alerta: es el estado normal,
    # y es lo que hace que el clip pueda cubrir su T−60 s.
    camara.preparar_preroll(T0)

    assert cliente.paso() is Fase.CLIP
    assert not list((tmp_path / "pendientes").glob("clip-*.mp4")), "todavía no toca cortar"

    # …pasan los diez minutos de la ventana y el anillo sigue grabando.
    camara.avanzar(T0, T0 + timedelta(seconds=600))
    reloj[0] = T0 + timedelta(seconds=600)
    assert cliente.paso() is Fase.GOTEO

    clips = list((tmp_path / "pendientes").glob("clip-*.mp4"))
    stills = list((tmp_path / "pendientes").glob("still-*.jpg"))
    # Cortado, subido y borrado en el mismo tick: pendientes/ queda vacío de ese clip.
    assert clips == [] and stills == []
    assert len(nube.grants) >= 2, "un grant para el clip y otro para la primera captura"

    modos = [g["mode"] for g in nube.grants]
    assert "cctv_clip" in modos and "cctv_still" in modos
    grant_clip = next(g for g in nube.grants if g["mode"] == "cctv_clip")
    assert grant_clip["event_id"] == "ev-e2e"
    assert grant_clip["ts_from"] == T0 - timedelta(seconds=60)
    assert grant_clip["ts_to"] == T0 + timedelta(seconds=600)
    # El clip que llegó a «S3» pesa lo que pesan sus segmentos, no cero.
    assert any(len(b) > 100_000 for b in nube.subidos.values())


def test_el_metadato_del_clip_declara_su_cobertura_real(tmp_path: Path) -> None:
    """Sin subidor el clip se queda en disco con su JSON al lado — el modo con el que un
    gabinete sin nube acumula evidencia sin perderla."""
    reloj = [T0]
    camara, cliente = _armar(tmp_path, None, _status(), reloj)
    camara.preparar_preroll(T0)
    cliente.paso()
    camara.avanzar(T0, T0 + timedelta(seconds=600))
    reloj[0] = T0 + timedelta(seconds=600)
    cliente.paso()

    meta = json.loads(next((tmp_path / "pendientes").glob("clip-*.json")).read_text("utf-8"))
    assert meta["event_id"] == "ev-e2e"
    assert meta["cobertura"] == 1.0, "el anillo cubría la ventana entera"
    assert "simulada" not in json.dumps(meta), "la credencial NO puede acabar en el metadato"


def test_un_gabinete_recien_arrancado_declara_lo_que_le_falta(tmp_path: Path) -> None:
    """Sin pre-roll el clip sale igual —es evidencia útil— pero DICE que empieza tarde. Un
    clip que afirmara cubrir T−60 s sin cubrirlo sería una mentira en un reporte."""
    reloj = [T0]
    camara, cliente = _armar(tmp_path, None, _status(), reloj)
    camara.avanzar(T0 - timedelta(seconds=20), T0)  # solo 20 s de los 60
    cliente.paso()
    camara.avanzar(T0, T0 + timedelta(seconds=600))
    reloj[0] = T0 + timedelta(seconds=600)
    cliente.paso()

    meta = json.loads(next((tmp_path / "pendientes").glob("clip-*.json")).read_text("utf-8"))
    assert meta["cobertura"] < 1.0


def test_en_modo_prueba_del_WR1_no_sale_un_solo_byte(tmp_path: Path) -> None:
    """La puerta más cara del módulo, comprobada sobre la cadena entera: una prueba de
    banco del radio no puede subir vídeo real de un edificio con gente."""
    nube = _Nube()
    reloj = [T0]
    camara, cliente = _armar(tmp_path, nube, _status(prueba=True), reloj)
    camara.preparar_preroll(T0)
    camara.avanzar(T0, T0 + timedelta(seconds=600))
    reloj[0] = T0 + timedelta(seconds=600)

    assert cliente.paso() is Fase.OCIOSO
    assert nube.grants == [] and nube.subidos == {}
    assert not list((tmp_path / "pendientes").glob("*"))


def test_las_capturas_del_goteo_son_JPEG_de_verdad(tmp_path: Path) -> None:
    """No son fotos de personas —y por eso el guion va aparte— pero son ficheros válidos:
    nada revienta al intentar decodificarlas."""
    reloj = [T0]
    camara, cliente = _armar(tmp_path, None, _status(), reloj)
    camara.preparar_preroll(T0)
    cliente.paso()
    camara.avanzar(T0, T0 + timedelta(seconds=600))
    reloj[0] = T0 + timedelta(seconds=600)
    cliente.paso()

    assert camara.capturas, "el goteo tomó al menos una"
    crudo = camara.capturas[0].read_bytes()
    assert crudo[:2] == b"\xff\xd8" and crudo[-2:] == b"\xff\xd9"


def test_el_simulador_reconoce_los_TRES_comandos_por_su_forma(tmp_path: Path) -> None:
    """Un doble que acepte cualquier cosa no vigila nada: si alguien cambia el comando del
    anillo por uno que decodifica, el simulador deja de reconocerlo y esto se entera."""
    reloj = [T0]
    camara, cliente = _armar(tmp_path, None, _status(), reloj)
    camara.preparar_preroll(T0)
    cliente.paso()
    camara.avanzar(T0, T0 + timedelta(seconds=600))
    reloj[0] = T0 + timedelta(seconds=600)
    cliente.paso()

    recorte = next(c for c in camara.comandos if "concat" in c)
    captura = next(c for c in camara.comandos if "-frames:v" in c)
    assert recorte[recorte.index("-c") + 1] == "copy", "el recorte NO recomprime"
    assert captura[captura.index("-frames:v") + 1] == "1"


def test_la_camara_sin_instantanea_hace_que_el_goteo_salga_del_RTSP(tmp_path: Path) -> None:
    """Es el caso de la cámara barata, y cuesta muy distinto: decodifica."""
    camara = CamaraSimulada(directorio=tmp_path, guion=GUION)
    assert camara.fuentes().snapshot is not None
    assert camara.fuentes(con_instantanea=False).snapshot is None


def test_el_guion_es_la_historia_que_el_analizador_tiene_que_ver(tmp_path: Path) -> None:
    """Vive explícito y no en los píxeles: fingir que un detector podría leerla del JPEG
    sería el tipo de verde mentiroso que este árbol persigue."""
    camara = CamaraSimulada(directorio=tmp_path, guion=GUION)
    assert camara.personas_en(4) == 40
    assert camara.personas_en(999) == 0, "fuera del guion la evacuación ya terminó"
