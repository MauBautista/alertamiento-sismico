"""El juicio de SeedLink de `goal-presentacion.sh` mira el PRESENTE, no el acumulado.

`seedlink.gaps` del panel es un ACUMULADO desde que arrancó el edge. El 2026-09-29 el
Shake entregó con retraso de 18:00 a 23:47 (746 huecos). Se reinició, volvió a 0,4 s y
dejó de sumar, pero el guion seguía dando ✗ «SeedLink con 746 huecos»: un tropiezo de
hace horas lo tenía en rojo hasta el siguiente reinicio del edge. Reiniciarlo para
«limpiar» el contador habría escondido la historia en vez de medir el presente.

Se corre el bloque del guion tal cual, extraído entre sus marcas, con un `curl` que
devuelve la segunda lectura del panel.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

GUION = Path(__file__).resolve().parents[2] / "deploy" / "demo" / "goal-presentacion.sh"
INICIO, FIN = "# >>> juicio de seedlink", "# <<< juicio de seedlink"


def _bloque() -> str:
    texto = GUION.read_text(encoding="utf-8")
    assert INICIO in texto and FIN in texto, "el juicio de SeedLink no está entre sus marcas"
    return texto.split(INICIO, 1)[1].split(FIN, 1)[0]


def _estado(gaps: int | None, paquetes: int | None, lag: float | None = 1.2) -> dict:
    estado: dict = {"health": {"seedlink_lag_s": lag}}
    if gaps is not None:
        estado["seedlink"] = {"gaps": gaps, "packets_seen": paquetes, "reconnects": 3}
    return estado


def _juzga(tmp_path: Path, primera: dict, segunda: dict | None) -> str:
    (tmp_path / "primera.json").write_text(json.dumps(primera))
    if segunda is not None:
        (tmp_path / "segunda.json").write_text(json.dumps(segunda))
    arnes = f"""
verde() {{ echo "VERDE $1"; }}
rojo() {{ echo "ROJO $1"; }}
no_medido_a() {{ echo "NOMEDIDO $1"; }}
sleep() {{ :; }}
curl() {{ cat "{tmp_path}/segunda.json" 2>/dev/null || return 22; }}
PANEL=http://panel
ESTADO="$(cat "{tmp_path}/primera.json")"
campo() {{ printf '%s' "$ESTADO" | jq -r "$1 | if . == null then empty else . end" 2>/dev/null; }}
{_bloque()}
"""
    r = subprocess.run(["bash", "-c", arnes], capture_output=True, text=True, check=True)
    lineas = r.stdout.strip().splitlines()
    assert len(lineas) == 1, f"el juicio debe dar UN veredicto, dio: {lineas}"
    return lineas[0]


def test_huecos_VIEJOS_con_el_sensor_sano_no_son_un_suspenso(tmp_path: Path) -> None:
    """El caso del 2026-09-29, con el Shake ya reiniciado."""
    v = _juzga(tmp_path, _estado(746, 17_000), _estado(746, 17_070))
    assert v.startswith("VERDE"), v
    assert "746" in v, "el acumulado se dice, no se esconde"


def test_huecos_NUEVOS_durante_la_medicion_son_un_suspenso(tmp_path: Path) -> None:
    v = _juzga(tmp_path, _estado(746, 17_000), _estado(748, 17_050))
    assert v.startswith("ROJO") and "2 huecos NUEVOS" in v, v


def test_un_sensor_PARADO_es_un_suspenso_aunque_no_sume_huecos(tmp_path: Path) -> None:
    """Sin paquetes tampoco hay huecos: el cero de huecos no puede pasar por sano."""
    v = _juzga(tmp_path, _estado(0, 500), _estado(0, 500))
    assert v.startswith("ROJO") and "PARADO" in v, v


def test_un_retraso_de_entrega_es_un_suspenso(tmp_path: Path) -> None:
    """Lo que delató el episodio: 19,6 s y luego 40 s de retraso, con paquetes llegando."""
    v = _juzga(tmp_path, _estado(10, 1_000, lag=40.4), _estado(10, 1_040, lag=40.4))
    assert v.startswith("ROJO") and "retraso" in v, v


def test_sin_huecos_nunca_sigue_siendo_verde(tmp_path: Path) -> None:
    v = _juzga(tmp_path, _estado(0, 1_000), _estado(0, 1_070))
    assert v.startswith("VERDE") and "0 huecos" in v, v


@pytest.mark.parametrize("cual", ["primera", "segunda"])
def test_una_lectura_que_falta_es_NO_MEDIDO_nunca_verde_ni_rojo(tmp_path: Path, cual: str) -> None:
    if cual == "primera":
        v = _juzga(tmp_path, _estado(None, None), _estado(0, 1_070))
    else:
        v = _juzga(tmp_path, _estado(0, 1_000), None)
    assert v.startswith("NOMEDIDO"), v
