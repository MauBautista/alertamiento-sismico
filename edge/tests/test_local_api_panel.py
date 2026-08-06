"""Panel del gabinete — RENDER de todas sus pantallas (index.html ejecutado).

`test_local_api.py` cubre el SERVIDOR (`/api/status`, PIN, secciones defensivas) y
comprueba el HTML por coincidencia de cadenas. Eso caza que alguien borre un
rótulo; no caza lo que decide si el panel sirve o miente a quien está DE PIE
frente al gabinete, sin nube y sin internet:

- que cada zona se pinte con datos reales,
- que los botones hagan lo que dicen (y que el rechazo se vea),
- y sobre todo que un dato DEGRADADO se vea degradado (regla de oro 7): un valor
  congelado pintado en verde es peor que un "S/D" honesto.

Ese comportamiento vive en `render()`, que es JavaScript. Aquí se EJECUTA, contra
un mini-DOM propio (`panel_harness.js`, cero dependencias — el job `edge` del CI
solo hace `uv sync`). Node está en el runner de CI y en el equipo de desarrollo;
si faltara, estos tests se saltan con su razón — nunca pasan en falso.

El status nominal de referencia (`_base()`) NO es inventado: `test_contrato_*`
compara sus claves contra las que sirve el gabinete real, así que un campo nuevo
o renombrado en `LocalDashboard.status()` rompe aquí hasta que el panel lo mire.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(
    _NODE is None,
    reason="node no está en el PATH: el render del panel no se puede ejecutar",
)

_INDEX = Path(__file__).resolve().parents[1] / "takab_edge" / "local_api" / "index.html"
_HARNESS = Path(__file__).with_name("panel_harness.js")
#: El paquete de tokens del monorepo — la ÚNICA fuente de verdad de la paleta.
_TOKENS_JSON = Path(__file__).resolve().parents[2] / "shared" / "design-tokens" / "tokens.json"

#: Paleta del panel — el COLOR es la señal de estado, no un adorno.
OK = "#00E676"
WARN = "#FFC107"
CRIT = "#FF5252"
CYAN = "#00BFFF"

_NOW = "2026-08-04T10:00:00+00:00"


def _channel(pga: float, age_s: float = 0.4, clipping: bool = False) -> dict:
    return {
        "pga_g": pga,
        "pgv_cms": pga * 39,
        "rms": 380.0,
        "sta_lta": 1.2,
        "clipping": clipping,
        "health_score": 1.0,
        "window_start": _NOW,
        "received_at": _NOW,
        "age_s": age_s,
    }


def _base() -> dict:
    """Gabinete NOMINAL: todo provisionado, todo vivo. Punto de partida de todo."""
    return {
        "gateway_id": "gw-test-0001",
        "site_name": "Hospital de Prueba",
        "now": _NOW,
        "uptime_s": 14520.0,
        "refresh_ms": 1000,
        "sasmex_active": False,
        "siren_sounding": False,
        "siren_reason": None,
        "audible_silenced": False,
        "alert_latched": False,
        "network_alert": None,
        "lora": {
            "enabled": True,
            "heartbeat_s": 90,
            "secondaries": [
                {
                    "id": 258,
                    "name": "AZOTEA-NORTE",
                    "zone": "Torre B",
                    "age_s": 34,
                    "battery_mv": 3870,
                    "rssi_dbm": -92,
                    "snr_db": 7.5,
                    "alarm_active": False,
                    "link": "online",
                    "acked": None,
                }
            ],
        },
        "last_tier": "normal",
        "relays": [
            {
                "channel": "siren",
                "energized": False,
                "activated": False,
                "fail_safe": "normally_open",
            },
            {
                "channel": "gas_valve",
                "energized": True,
                "activated": False,
                "fail_safe": "fail_close",
            },
        ],
        "captured_at": _NOW,
        "site_lat": 19.0414,
        "site_lon": -98.2063,
        "neighbors": [{"code": "AM.R7B21", "lat": 19.12, "lon": -98.42, "distance_km": 17.2}],
        "config_version": 4,
        "thresholds": {
            "pga_watch_g": 0.040,
            "pga_trip_g": 0.060,
            "pgv_watch_cms": 2.0,
            "pgv_trip_cms": 4.0,
        },
        "latencies": {
            "reflex_s": 0.00665,
            "reflex_budget_s": 0.100,
            "rules_s": 0.118,
            "rules_budget_s": 0.200,
        },
        "seedlink": {"packets_seen": 1284902, "reconnects": 2, "duplicates": 0, "gaps": 0},
        "calibration": {
            "calibrated": True,
            "source": "StationXML FDSN AM.R4F74",
            "vel_sensitivity_ms_per_count": 2.5021894e-9,
            "accel_sensitivity_ms2_per_count": 2.6007802e-6,
        },
        "rose_zero": None,
        "shake_history": {
            "since": _NOW,
            "by_channel": {
                "ENZ": {
                    "pga_g_max_24h": 0.011,
                    "pgv_cms_max_24h": 0.9,
                    "hourly": [{"hour_start": _NOW, "pga_g_max": 0.011, "pgv_cms_max": 0.9}],
                }
            },
            "events_by_tier": {
                "normal": 1,
                "watch": 1,
                "restricted": 0,
                "evacuate_or_hold": 0,
                "manual_only": 0,
            },
            "noise_floor": {
                "current_mg": 0.8,
                "baseline_low_mg": 0.6,
                "baseline_high_mg": 1.1,
                "trend": "stable",
            },
        },
        "signal": {
            "channels": {c: _channel(0.001) for c in ("EHZ", "ENZ", "ENN", "ENE")},
            "last_received_at": _NOW,
            "stale_after_s": 5.0,
        },
        "health": {
            "ntp_offset_s": 0.0031,
            "seedlink_lag_s": 0.42,
            "packet_loss_pct": 0.2,
            "mqtt_rtt_ms": 84.0,
            "ups_status": "line",
            "battery_pct": 100.0,
            "ups_runtime_s": 2460.0,
            "temperature_c": 58.4,
            "cert_days_remaining": 213,
            "disk_used_pct": 62.0,
            "captured_at": _NOW,
            "age_s": 38.0,
        },
        "cloud": {"online": True, "mqtt_rtt_ms": 84.0, "queued": 0, "admin_state": "active"},
        "drill": None,
        "actuation_test": {"active": False, "results": None},
        "test_mode": {"active": False, "remaining_s": 0.0},
        "audio": {
            "enabled": True,
            "sounding": False,
            "profile": {"applied": {}, "rejected": {}, "test_tone": True},
        },
        "events": [{"at": _NOW, "action": "boot", "via": "boot"}],
    }


def _cold() -> dict:
    """Arranque en frío: el gabinete acaba de encender y no sabe casi nada."""
    st = _base()
    st.update(
        {
            "uptime_s": 4.0,
            "last_tier": None,
            "relays": [],
            "lora": None,
            "site_lat": None,
            "site_lon": None,
            "neighbors": [],
            "config_version": 0,
            "thresholds": None,
            "latencies": {
                "reflex_s": None,
                "reflex_budget_s": 0.100,
                "rules_s": None,
                "rules_budget_s": 0.200,
            },
            "seedlink": None,
            "calibration": {
                "calibrated": False,
                "source": None,
                "vel_sensitivity_ms_per_count": None,
                "accel_sensitivity_ms2_per_count": None,
            },
            "shake_history": None,
            "signal": None,
            "health": None,
            "cloud": {
                "online": False,
                "mqtt_rtt_ms": None,
                "queued": None,
                "admin_state": "active",
            },
            "audio": None,
            "events": [],
        }
    )
    return st


_CATALOG = {
    "available": True,
    "source": "SSN · UNAM",
    "captured_at": "2026-08-04T09:00:00",
    "note": "réplicas agregadas",
    "events": [
        {
            "m": 5.4,
            "at": "2026-08-04 03:12:00",
            "lat": 16.8,
            "lon": -99.1,
            "depth_km": 18.0,
            "place": "GUERRERO",
        },
        {
            "m": 3.9,
            "at": "2026-08-04 01:02:00",
            "lat": 18.2,
            "lon": -97.4,
            "depth_km": 60.0,
            "place": "PUEBLA",
        },
    ],
    "references": [{"n": "PUEBLA", "lat": 19.04, "lon": -98.20}],
}


# ------------------------------------------------------------------ arnés


def _render(tmp_path: Path, **cfg) -> dict:
    """Ejecuta el panel con esta configuración y devuelve la instantánea del DOM."""
    cfg.setdefault("status", _base())
    cfg.setdefault("catalog", {"available": False, "events": [], "references": []})
    path = tmp_path / "panel_cfg.json"
    path.write_text(json.dumps(cfg), "utf-8")
    proc = subprocess.run(  # noqa: S603 — binario resuelto por shutil.which, entrada propia
        [_NODE, str(_HARNESS), str(_INDEX), str(path)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, f"arnés cayó: {proc.stderr[:2000]}"
    out = json.loads(proc.stdout)
    assert not out.get("fatal"), out.get("fatal")
    # Una excepción dentro de render() dejaría media pantalla sin repintar
    # mostrando el estado ANTERIOR: eso es exactamente la mentira que se persigue.
    assert out["errors"] == [], out["errors"]
    return out


def _node(tree: dict, node_id: str) -> dict:
    if tree.get("id") == node_id:
        return tree
    for kid in tree.get("kids", ()):
        found = _node(kid, node_id) if _has(kid, node_id) else None
        if found is not None:
            return found
    raise AssertionError(f"el panel no tiene ningún elemento con id={node_id!r}")


def _has(tree: dict, node_id: str) -> bool:
    if tree.get("id") == node_id:
        return True
    return any(_has(k, node_id) for k in tree.get("kids", ()))


def _text(node: dict) -> str:
    return (node.get("txt") or "") + "".join(_text(k) for k in node.get("kids", ()))


def _txt(out: dict, node_id: str) -> str:
    return _text(_node(out["tree"], node_id))


def _colors(node: dict) -> set[str]:
    mine = {node.get("color", ""), node.get("bg", "")} - {""}
    for kid in node.get("kids", ()):
        mine |= _colors(kid)
    return mine


def _hidden(out: dict, node_id: str) -> bool:
    return "hide" in _node(out["tree"], node_id).get("cls", "").split()


def _leaves(node: dict) -> list[dict]:
    """Nodos con texto propio — para afirmar sobre el color de UN valor."""
    found = [node] if (node.get("txt") or "").strip() else []
    for kid in node.get("kids", ()):
        found += _leaves(kid)
    return found


def _posts(out: dict, url: str) -> list[dict]:
    return [f for f in out["fetches"] if f["method"] == "POST" and f["url"] == url]


def _value_color(out: dict, node_id: str, needle: str) -> str:
    for leaf in _leaves(_node(out["tree"], node_id)):
        if needle in leaf["txt"]:
            return leaf["color"]
    raise AssertionError(f"{needle!r} no aparece dentro de #{node_id}")


# ------------------------------------------------------------------- paleta
#
# [T-2.64.b] El panel del gabinete NO puede importar `@takab/design-tokens`: se
# sirve como un único archivo estático desde un Pi sin red ni build. Su paleta es
# una COPIA literal — de hecho DOS copias, el `:root` de CSS y el objeto `C` que
# pinta los canvas. Tres verdades para un mismo color es una que se desvía.
#
# Estas comprobaciones son texto puro, sin DOM; heredan el `skipif` de node del
# módulo, que en CI está garantizado (el job `edge` verifica `node --version`).


def _root_vars() -> dict[str, str]:
    """Custom properties declaradas en el `:root` del propio `index.html`."""
    html = _INDEX.read_text("utf-8")
    inicio = html.index(":root{")
    bloque = html[inicio + len(":root{") : html.index("}", inicio)]
    return {m[1]: m[2].strip() for m in re.finditer(r"(--tk-[a-z0-9-]+)\s*:\s*([^;]+)", bloque)}


def _js_palette() -> dict[str, str]:
    """El objeto `const C = {...}` que colorea los canvas."""
    html = _INDEX.read_text("utf-8")
    inicio = html.index("const C = {")
    bloque = html[inicio : html.index("}", inicio)]
    return {m[1]: m[2].upper() for m in re.finditer(r"(\w+)\s*:\s*'(#[0-9a-fA-F]{6})'", bloque)}


def _luminancia(color: str) -> float:
    """Luminancia relativa WCAG 2.x de un `#RRGGBB`."""
    crudo = color.lstrip("#")
    canales = [int(crudo[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contraste(fg: str, bg: str) -> float:
    a, b = _luminancia(fg), _luminancia(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


#: AA de WCAG 1.4.3 para texto normal. El panel NO tiene texto grande donde use
#: gris: sus rótulos son de 9–11 px, leídos DE PIE frente al gabinete.
_AA = 4.5


@pytest.mark.parametrize("fondo", ["--tk-surface-0", "--tk-surface-1", "--tk-surface-2"])
def test_los_grises_del_panel_se_leen_de_pie_frente_al_gabinete(fondo):
    """Un rótulo por debajo de AA no es un detalle estético en un gabinete.

    `--tk-fg-3` vestía «SIRENA», «PGA MÁX · 24 h», las unidades de los carriles y
    los rótulos de la brújula a 9–10 px. Medido: 3.48:1 sobre `surface-1` y
    3.15:1 sobre `surface-2` — por debajo del 4.5 que exige AA para texto normal.
    """
    root = _root_vars()
    flojos = [
        f"{nombre} ({valor}) sobre {fondo} = {_contraste(valor, root[fondo]):.2f}:1"
        for nombre, valor in root.items()
        # `-disabled` está exento por WCAG 1.4.3 (texto de control apagado).
        if nombre.startswith("--tk-fg-")
        and nombre != "--tk-fg-disabled"
        and _contraste(valor, root[fondo]) < _AA
    ]
    assert not flojos, "grises por debajo de AA en el panel del gabinete:\n" + "\n".join(flojos)


def test_la_paleta_del_panel_no_inventa_su_propia_verdad():
    """Todo gris/fondo del panel existe en el paquete y con el MISMO valor.

    Sin esto el design system tiene dos verdades: se corrige `tokens.json`, la
    consola SOC mejora y el panel del gabinete —la pantalla que se mira sin nube
    y sin internet— se queda con el color viejo. Es justo lo que pasó con
    `--tk-fg-4`, un token que solo existía aquí.
    """
    paquete = json.loads(_TOKENS_JSON.read_text("utf-8"))
    divergen = []
    for nombre, valor in _root_vars().items():
        if not nombre.startswith(("--tk-fg-", "--tk-surface-")):
            continue
        if nombre not in paquete:
            divergen.append(f"{nombre}: solo existe en el panel, no en el paquete de tokens")
        elif valor.replace(" ", "") != paquete[nombre].replace(" ", ""):
            divergen.append(f"{nombre}: panel {valor} ≠ paquete {paquete[nombre]}")
    assert not divergen, "la paleta del panel se separó del paquete:\n" + "\n".join(divergen)


def test_la_paleta_js_de_los_canvas_no_se_separa_de_la_css():
    """`C.fg3` y `var(--tk-fg-3)` son el MISMO color o el panel se pinta a dos tonos.

    Los canvas (brújula, mapa, comparativa) no leen custom properties: llevan los
    hex a mano en `C`. Corregir solo el `:root` dejaría los ejes de la brújula y
    las etiquetas del mapa en el gris ilegible.
    """
    root = _root_vars()
    equivalencias = {
        "fg1": "--tk-fg-1",
        "fg2": "--tk-fg-2",
        "fg3": "--tk-fg-3",
        "cyan": "--tk-cyan",
        "geo": "--tk-geo",
        "ok": "--tk-ok",
        "warn": "--tk-warn",
        "crit": "--tk-crit",
    }
    js = _js_palette()
    assert js, "no se pudo leer el objeto C del panel"
    divergen = []
    for clave, valor in js.items():
        css = equivalencias.get(clave)
        assert css is not None, f"C.{clave} no está mapeado a ninguna custom property"
        if css not in root:
            divergen.append(f"C.{clave} apunta a {css}, que el :root ya no declara")
        elif valor.upper() != root[css].upper():
            divergen.append(f"C.{clave} = {valor} ≠ {css} = {root[css]}")
    assert not divergen, "las dos paletas del panel se separaron:\n" + "\n".join(divergen)


# --------------------------------------------------- contrato con el servidor


def test_contrato_el_status_del_gabinete_real_alimenta_el_panel(supervisor, tmp_path):
    """El status REAL del gabinete se pinta sin reventar y con sus claves.

    Sin esta prueba el arnés sería un teatro: un cambio en `status()` no rompería
    nada aquí y el panel se quedaría atrás en silencio.
    """
    real = json.loads(json.dumps(supervisor.local_api.status()))
    faltan = set(real) - set(_base())
    sobran = set(_base()) - set(real)
    assert not faltan, f"claves nuevas de status() que el panel no conoce: {sorted(faltan)}"
    assert not sobran, f"claves del fixture que status() ya no sirve: {sorted(sobran)}"
    # [T-2.65] …y también DENTRO de `cloud`: el contrato solo se comparaba en el
    # primer nivel, así que un campo anidado nuevo (o desaparecido) no rompía
    # nada y el panel lo habría pintado como `undefined` en silencio.
    assert set(real["cloud"]) == set(_base()["cloud"]), (
        f"contrato de status()['cloud'] desalineado: "
        f"real={sorted(real['cloud'])} fixture={sorted(_base()['cloud'])}"
    )
    out = _render(tmp_path, status=real)
    # Un gabinete recién arrancado no tiene señal ni salud: debe DECIRLO.
    assert "S/D" in _txt(out, "salud-grid") or "SIN DIAGNÓSTICO" in _txt(out, "salud-age")


# ------------------------------------------------------------------ zonas


#: Toda zona con contenido dinámico. Ninguna puede quedarse muda ni en nominal
#: ni en arranque en frío: un hueco silencioso se lee como "aquí no pasa nada".
_ZONAS = [
    "hdr-id",
    "hdr-site",
    "hdr-meta",
    "pill-live-txt",
    "pill-cloud-txt",
    "tier-label",
    "tier-sub",
    "relays",
    "decim-note",
    "lanes",
    "waves-sr",
    "prox-profile",
    "prox-bars",
    "hist-since",
    "pga-hour",
    "pga-24h",
    "hist-rows",
    "lat-rows",
    "rose-variant-note",
    "rose-station",
    "rose-site",
    "rose-coords",
    "rose-axes",
    "quorum-note",
    "salud-age",
    "salud-grid",
    "lora-rows",
    "event-rows",
    "ssn-meta",
    "action-btns",
    "pin-msg",
]


@pytest.mark.parametrize("escena", ["nominal", "frio"])
def test_todas_las_zonas_del_panel_se_pintan(tmp_path, escena):
    out = _render(tmp_path, status=_base() if escena == "nominal" else _cold())
    vacias = [z for z in _ZONAS if not _txt(out, z).strip()]
    assert not vacias, f"zonas mudas en escena {escena}: {vacias}"


def test_las_zonas_del_mapa_se_pintan_al_abrirlo(tmp_path):
    out = _render(
        tmp_path, catalog=_CATALOG, clicks=["#open-map", "frame", "row:ssn-rows-big", "frame"]
    )
    assert not _hidden(out, "overlay")
    for zona in ("station-rows", "ssn-rows-big", "ssn-count", "ssn-meta-big", "cmp-facts"):
        assert _txt(out, zona).strip(), f"zona vacía con el mapa abierto: {zona}"
    # El mapa y la gráfica son canvas: se comprueba lo que ESTAMPAN.
    assert any("ALCANCE" in t for t in out["canvasText"])
    assert any("BANDA ILUSTRATIVA" in t for t in out["canvasText"])


def test_modo_muro_llena_su_franja_propia(tmp_path):
    out = _render(tmp_path, catalog=_CATALOG, clicks=["data:mode:muro"])
    assert _txt(out, "muro-nearest").strip()
    assert _txt(out, "muro-top3").strip()
    assert "mode-muro" in _node(out["tree"], "__body__")["cls"]


def test_modo_campo_se_elige_solo_en_pantalla_angosta(tmp_path):
    out = _render(tmp_path, innerWidth=800)
    assert "mode-campo" in _node(out["tree"], "__body__")["cls"]


# ----------------------------------------------------------------- banners


def test_banner_rojo_solo_con_actuacion_real_sasmex(tmp_path):
    st = _base()
    st["sasmex_active"] = True
    st["siren_sounding"] = True
    st["alert_latched"] = True
    out = _render(tmp_path, status=st)
    assert not _hidden(out, "banner-alert")
    assert "SASMEX WR-1" in _txt(out, "alert-meta")
    assert _hidden(out, "banner-aviso")


def test_banner_rojo_declara_quorum_cuando_lo_comanda_la_red(tmp_path):
    st = _base()
    st["network_alert"] = {"command_id": "c-1", "at": _NOW}
    out = _render(tmp_path, status=st)
    assert not _hidden(out, "banner-alert")
    assert "QUÓRUM RED" in _txt(out, "alert-meta")


def test_tier_instrumental_es_aviso_ambar_no_rojo(tmp_path):
    """[T-2.32] Una estación sola NO actúa: el rojo queda para la actuación real."""
    st = _base()
    st["last_tier"] = "evacuate_or_hold"
    out = _render(tmp_path, status=st)
    assert _hidden(out, "banner-alert")
    assert not _hidden(out, "banner-aviso")
    assert "EVACUATE_OR_HOLD" in _txt(out, "aviso-meta")


def test_enclave_sin_alerta_viva_se_declara(tmp_path):
    st = _base()
    st["alert_latched"] = True
    out = _render(tmp_path, status=st)
    assert not _hidden(out, "banner-latched")
    assert _hidden(out, "banner-alert")


def test_simulacro_se_anuncia_y_lo_real_lo_aborta(tmp_path):
    st = _base()
    st["drill"] = {"active": True, "drill_id": "DRILL-1", "elapsed_s": 60, "total_s": 480}
    out = _render(tmp_path, status=st)
    assert "NO ES UNA ALERTA REAL" in _txt(out, "amber-txt")

    st["sasmex_active"] = True
    out = _render(tmp_path, status=st)
    assert "SIMULACRO ABORTADO" in _txt(out, "amber-txt")
    assert not _hidden(out, "banner-alert")


def test_banner_wr1_sigue_visible_incluso_bajo_alerta(tmp_path):
    """Modo prueba armado = la nube NO recibe. Ocultarlo bajo alerta sería mentir."""
    st = _base()
    st["test_mode"] = {"active": True, "remaining_s": 87.0}
    st["sasmex_active"] = True
    out = _render(tmp_path, status=st)
    assert not _hidden(out, "banner-wr1")
    assert "87 s RESTANTES" in _txt(out, "wr1-left")


def test_prueba_de_actuadores_tiene_su_propio_banner(tmp_path):
    st = _base()
    st["actuation_test"] = {"active": True, "results": None}
    st["siren_sounding"] = True
    out = _render(tmp_path, status=st)
    assert not _hidden(out, "banner-cyan")
    assert _hidden(out, "banner-alert")


def test_el_modo_demo_se_declara_siempre(tmp_path):
    out = _render(tmp_path, search="?demo=alerta", clicks=["frame"])
    assert not _hidden(out, "demo-ribbon")
    assert "alerta" in _txt(out, "demo-which")
    assert not _hidden(out, "banner-alert")


# ------------------------------------------------- estados degradados (oro 7)


def test_feature_vieja_no_se_pinta_como_medicion_viva(tmp_path):
    """El fallo del 2026-07-14, esta vez en el panel LOCAL.

    `live_by_channel()` NUNCA desaloja: con SeedLink muerto el último `Feature1s`
    sigue en `/api/status` con su `age_s` creciendo. Los carriles ya lo
    declaraban, pero la barra de proximidad, los ejes de la brújula y el resumen
    accesible leían el mismo dict SIN mirar la edad. Resultado: PGA de hace dos
    horas en VERDE y "2 % del disparo" — el gabinete lleva ciego media mañana y
    la pantalla dice que todo está tranquilo.
    """
    st = _base()
    for canal in st["signal"]["channels"].values():
        canal["age_s"] = 7200.0
    st["health"]["seedlink_lag_s"] = 7200.0
    out = _render(tmp_path, status=st, clicks=["frame"])

    assert "SIN SEÑAL DEL SENSOR" in _txt(out, "lanes")  # esto ya funcionaba
    assert "S/D" in _txt(out, "prox-bars")
    assert OK not in _colors(_node(out["tree"], "prox-bars")), (
        "PGA congelado pintado como si midiera"
    )
    assert _value_color(out, "rose-axes", "S/D") == WARN
    assert CYAN not in _colors(_node(out["tree"], "rose-axes"))
    assert "S/D" in _txt(out, "waves-sr")
    # La brújula deja de apuntar: un vector quieto se lee como "quieto de verdad".
    assert any("SIN SEÑAL DEL SENSOR" in t for t in out["canvasText"])


def test_una_prueba_de_sirena_no_se_lee_como_una_alerta(tmp_path):
    """[T-2.49] El altavoz ya distinguía prueba de sismo; la PANTALLA no.

    `siren_sounding` es un booleano eléctrico: sin la razón, quien llega a mitad
    de un self-test lee «SIRENA: SONANDO» exactamente igual que en un sismo.
    """
    st = _base()
    st["siren_sounding"] = True
    st["siren_reason"] = "test"
    out = _render(tmp_path, status=st)
    assert "SIRENA: SONANDO · PRUEBA" in _txt(out, "tier-sub")
    assert _hidden(out, "banner-alert")

    st["siren_reason"] = "alert"
    st["sasmex_active"] = True
    out = _render(tmp_path, status=st)
    assert "SIRENA: SONANDO · ALERTA" in _txt(out, "tier-sub")


def test_un_tono_rechazado_por_el_catalogo_se_declara(tmp_path):
    """El tono oficial de SASMEX está RESERVADO (GATE-LEGAL): pedirlo no cambia
    nada y el gabinete sigue con el anterior. Silenciarlo aquí sería dejar al
    operador creyendo que suena lo que su config dice."""
    st = _base()
    st["audio"]["profile"] = {
        "applied": {},
        "rejected": {"siren": "sasmex-oficial-v1"},
        "test_tone": True,
    }
    out = _render(tmp_path, status=st)
    assert "RECHAZADO(S)" in _txt(out, "salud-grid")
    assert "sasmex-oficial-v1" in _txt(out, "salud-grid")
    assert _value_color(out, "salud-grid", "RECHAZADO(S)") == CRIT


def test_sin_tono_de_prueba_el_boton_lo_advierte_antes_del_clic(tmp_path):
    """Sin tono de prueba una prueba CALLA a propósito (caer al de alerta era el
    bug). Sin decirlo, el silencio se lee como un altavoz averiado."""
    st = _base()
    st["audio"]["profile"] = {"applied": {}, "rejected": {}, "test_tone": False}
    out = _render(tmp_path, status=st)
    assert "SIN TONO DE PRUEBA" in _txt(out, "action-btns")
    assert "SIN TONO DE PRUEBA" in _txt(out, "salud-grid")
    assert _value_color(out, "salud-grid", "SIN TONO DE PRUEBA") == WARN


def test_sin_canales_la_brujula_y_los_carriles_lo_dicen(tmp_path):
    st = _base()
    st["signal"] = {"channels": {}, "last_received_at": None, "stale_after_s": 5.0}
    out = _render(tmp_path, status=st, clicks=["frame"])
    assert "SIN SEÑAL DEL SENSOR" in _txt(out, "lanes")
    assert any("SIN SEÑAL DEL SENSOR" in t for t in out["canvasText"])


def test_saturacion_del_adc_no_se_confunde_con_una_medicion_alta(tmp_path):
    st = _base()
    st["signal"]["channels"]["ENZ"] = _channel(0.9, clipping=True)
    out = _render(tmp_path, status=st)
    assert "SATURACIÓN DEL ADC" in _txt(out, "lanes")
    assert "NO MIDIENDO" in _txt(out, "lanes")


def test_diagnostico_de_salud_viejo_se_rotula_como_viejo(tmp_path):
    st = _base()
    st["health"]["age_s"] = 4000.0
    out = _render(tmp_path, status=st)
    assert "DIAGNÓSTICO DE HACE" in _txt(out, "salud-age")
    assert _node(out["tree"], "salud-age")["color"] == WARN


def test_sin_diagnostico_de_salud_se_declara(tmp_path):
    st = _base()
    st["health"] = None
    out = _render(tmp_path, status=st)
    assert "SIN DIAGNÓSTICO AÚN" in _txt(out, "salud-age")
    assert "S/D" in _txt(out, "salud-grid")


def test_sin_contadores_seedlink_se_declara_sin_cliente(tmp_path):
    st = _base()
    st["seedlink"] = None
    out = _render(tmp_path, status=st)
    assert "sin cliente" in _txt(out, "salud-grid")


def test_sin_umbrales_la_proximidad_no_inventa_una_escala(tmp_path):
    st = _base()
    st["thresholds"] = None
    out = _render(tmp_path, status=st)
    assert "motor caído" in _txt(out, "prox-profile")
    assert "S/D" in _txt(out, "prox-bars")


def test_latencias_sin_medicion_son_sd_jamas_cero(tmp_path):
    st = _base()
    st["latencies"] = {
        "reflex_s": None,
        "reflex_budget_s": 0.100,
        "rules_s": None,
        "rules_budget_s": 0.200,
    }
    out = _render(tmp_path, status=st)
    texto = _txt(out, "lat-rows")
    assert "S/D" in texto
    assert "0.00 ms" not in texto, "un cero fabricado se lee como 'instantáneo'"
    assert _value_color(out, "lat-rows", "S/D") == WARN


def test_latencia_fuera_de_presupuesto_se_pinta_critica(tmp_path):
    st = _base()
    st["latencies"]["reflex_s"] = 0.4  # 4× el presupuesto de 100 ms
    out = _render(tmp_path, status=st)
    assert _value_color(out, "lat-rows", "400.00 ms") == CRIT


def test_sin_reles_se_declara_sd(tmp_path):
    st = _base()
    st["relays"] = []
    out = _render(tmp_path, status=st)
    assert "RELÉS" in _txt(out, "relays")
    assert "S/D" in _txt(out, "relays")


def test_solo_se_pintan_los_reles_instalados(tmp_path):
    """[T-2.31] El equipamiento llega fusionado en la config firmada: un relé de
    gas en un sitio sin gas sería un dato falso. El filtro es del servidor; aquí
    se comprueba que el panel pinta EXACTAMENTE lo que le sirven."""
    st = _base()
    st["relays"] = [
        {"channel": "siren", "energized": False, "activated": False, "fail_safe": "normally_open"}
    ]
    out = _render(tmp_path, status=st)
    assert "SIRENA" in _txt(out, "relays")
    assert "GAS" not in _txt(out, "relays")


def test_sin_ubicacion_provisionada_no_hay_centro_inventado(tmp_path):
    st = _base()
    st["site_lat"] = None
    st["site_lon"] = None
    st["neighbors"] = []
    out = _render(tmp_path, status=st, catalog=_CATALOG, clicks=["#open-map", "frame"])
    assert "SIN UBICACIÓN PROVISIONADA" in _txt(out, "rose-coords")
    assert _node(out["tree"], "rose-coords")["color"] == WARN
    assert "SIN UBICACIÓN PROVISIONADA" in _txt(out, "station-rows")
    assert any("SIN UBICACIÓN PROVISIONADA" in t for t in out["canvasText"])


def test_sin_calibrar_las_unidades_se_declaran_relativas(tmp_path):
    st = _base()
    st["calibration"] = {
        "calibrated": False,
        "source": None,
        "vel_sensitivity_ms_per_count": None,
        "accel_sensitivity_ms2_per_count": None,
    }
    out = _render(tmp_path, status=st)
    assert not _hidden(out, "nocal-pill")
    assert "g rel." in _txt(out, "lanes")


def test_sin_historico_de_sacudida_se_declara(tmp_path):
    st = _base()
    st["shake_history"] = None
    out = _render(tmp_path, status=st)
    assert "S/D" in _txt(out, "hist-since")
    assert "módulo de señal caído" in _txt(out, "hist-rows")
    assert _txt(out, "pga-hour") == "S/D"


def test_sin_enlace_a_nube_dice_que_la_proteccion_local_sigue(tmp_path):
    st = _base()
    st["cloud"] = {"online": False, "mqtt_rtt_ms": None, "queued": 47}
    out = _render(tmp_path, status=st)
    assert "SIN ENLACE — PROTECCIÓN LOCAL ACTIVA" in _txt(out, "pill-cloud-txt")
    assert "47 EN COLA" in _txt(out, "pill-cloud-txt")
    assert "sin enlace" in _txt(out, "salud-grid")


def test_catalogo_ssn_no_disponible_se_declara_en_los_dos_sitios(tmp_path):
    out = _render(tmp_path, catalog={"available": False, "events": [], "references": []})
    for zona in ("ssn-meta", "ssn-meta-big"):
        assert "CATÁLOGO NO DISPONIBLE" in _txt(out, zona)
        assert _node(out["tree"], zona)["color"] == WARN
    assert _txt(out, "ssn-count") == "—"


def test_catalogo_ssn_disponible_declara_su_instantanea(tmp_path):
    out = _render(tmp_path, catalog=_CATALOG)
    assert "INSTANTÁNEA DEL CATÁLOGO" in _txt(out, "ssn-meta")
    assert "MÁS CERCANO" in _txt(out, "ssn-nearest")
    assert "M 5.4" in _txt(out, "ssn-rows")


def test_lora_distingue_sin_radio_de_sin_secundarios(tmp_path):
    """No es lo mismo «este gabinete no tiene radio» que «la tiene y no hay nadie»."""
    st = _base()
    st["lora"] = None
    out = _render(tmp_path, status=st)
    assert "SIN RADIO LORA" in _txt(out, "lora-rows")

    st["lora"] = {"enabled": True, "heartbeat_s": 90, "secondaries": []}
    out = _render(tmp_path, status=st)
    assert "SIN GABINETES SECUNDARIOS PROVISIONADOS" in _txt(out, "lora-rows")


def test_lora_marca_el_enlace_perdido_y_el_ack_faltante(tmp_path):
    st = _base()
    st["lora"]["secondaries"] = [
        {
            "id": 1,
            "name": "PATIO-SUR",
            "zone": "",
            "age_s": 900,
            "battery_mv": 3600,
            "rssi_dbm": -104,
            "snr_db": 2.1,
            "alarm_active": True,
            "link": "offline",
            "acked": False,
        },
        {
            "id": 2,
            "name": "NUEVO",
            "zone": "",
            "age_s": None,
            "battery_mv": None,
            "rssi_dbm": None,
            "snr_db": None,
            "alarm_active": False,
            "link": "never",
            "acked": None,
        },
    ]
    out = _render(tmp_path, status=st)
    texto = _txt(out, "lora-rows")
    assert "ENLACE PERDIDO" in texto
    assert "SIN ACK" in texto
    assert "SIN CONTACTO AÚN" in texto
    assert CRIT in _colors(_node(out["tree"], "lora-rows"))


def test_bitacora_vacia_se_distingue_de_bitacora_rota(tmp_path):
    st = _base()
    st["events"] = []
    out = _render(tmp_path, status=st)
    assert "Sin eventos · DESDE EL ARRANQUE" in _txt(out, "event-rows")


def test_bitacora_pinta_transiciones_y_acciones_del_panel(tmp_path):
    st = _base()
    st["events"] = [
        {"at": _NOW, "from_tier": "normal", "to_tier": "watch", "source": "local_threshold"},
        {"at": _NOW, "action": "silence", "via": "lan"},
    ]
    out = _render(tmp_path, status=st)
    texto = _txt(out, "event-rows")
    assert "normal → watch" in texto
    assert "silence · desde el panel" in texto


# ------------------------------------------------- estados de CONEXIÓN del panel


def test_panel_en_vivo_cuando_el_gabinete_responde(tmp_path):
    out = _render(tmp_path)
    assert _txt(out, "pill-live-txt") == "PANEL EN VIVO"
    assert _node(out["tree"], "pill-live-txt")["color"] == OK


def test_un_fallo_degrada_a_dato_retenido(tmp_path):
    out = _render(tmp_path, statusNetworkFail=True)
    assert "DATO RETENIDO" in _txt(out, "pill-live-txt")
    assert _node(out["tree"], "pill-live-txt")["color"] == WARN


def test_tres_fallos_declaran_sin_conexion_con_el_gabinete(tmp_path):
    """El peor estado del panel: dejar de rotularlo sería mostrar una foto vieja."""
    out = _render(tmp_path, statusNetworkFail=True, clicks=["tick", "tick"])
    assert "SIN CONEXIÓN CON EL GABINETE" in _txt(out, "pill-live-txt")
    assert _node(out["tree"], "pill-live-txt")["color"] == CRIT


def test_un_500_del_servidor_tambien_degrada(tmp_path):
    out = _render(tmp_path, statusStatus=500)
    assert "DATO RETENIDO" in _txt(out, "pill-live-txt")


# --------------------------------------------------------- barra de acciones


def test_la_barra_ofrece_solo_las_ordenes_aplicables(tmp_path):
    out = _render(tmp_path)
    texto = _txt(out, "action-btns")
    assert "PROBAR SIRENA" in texto
    assert "CALIBRAR BRÚJULA" in texto
    assert "PROBAR ACTUADORES" in texto
    assert "MODO PRUEBA WR-1" in texto
    assert "SIMULACRO DE VOCEO" in texto  # audio.enabled = true
    # Sin sirena sonando ni enclave, estas dos NO se ofrecen: un botón muerto
    # invita a pulsarlo justo cuando no hay tiempo para descubrir que no hace nada.
    assert "SILENCIAR AUDIBLES" not in texto
    assert "CERRAR ALERTA" not in texto


def test_silenciar_solo_aparece_con_la_sirena_sonando(tmp_path):
    st = _base()
    st["siren_sounding"] = True
    out = _render(tmp_path, status=st, clicks=["action:SILENCIAR AUDIBLES"])
    assert _posts(out, "api/silence")


def test_cerrar_alerta_aparece_con_el_enclave_y_exige_dos_clics(tmp_path):
    st = _base()
    st["alert_latched"] = True
    uno = _render(tmp_path, status=st, clicks=["action:CERRAR ALERTA"])
    assert not [f for f in uno["fetches"] if f["method"] == "POST"], "un solo clic NO puede cerrar"
    assert "CLIC NUEVAMENTE" in _txt(uno, "action-btns")
    assert "CLIC NUEVAMENTE PARA CONFIRMAR" in _txt(uno, "pin-msg")

    dos = _render(tmp_path, status=st, clicks=["action:CERRAR ALERTA", "confirm"])
    assert _posts(dos, "api/reset")


def test_sin_audio_no_se_ofrece_el_voceo_de_simulacro(tmp_path):
    st = _base()
    st["audio"] = None
    out = _render(tmp_path, status=st)
    assert "SIMULACRO DE VOCEO" not in _txt(out, "action-btns")


def test_modo_prueba_wr1_conmuta_su_rotulo(tmp_path):
    st = _base()
    st["test_mode"] = {"active": True, "remaining_s": 87.0}
    out = _render(tmp_path, status=st, clicks=["action:SALIR DE PRUEBA WR-1"])
    assert _posts(out, "api/test-mode")


def test_una_orden_aceptada_refresca_el_estado_al_instante(tmp_path):
    """[T-2.26] Sin el refetch, la alerta seguía en pantalla hasta el siguiente poll."""
    st = _base()
    st["siren_sounding"] = True
    out = _render(tmp_path, status=st, clicks=["action:SILENCIAR AUDIBLES"])
    gets = [f for f in out["fetches"] if f["url"] == "api/status"]
    assert len(gets) >= 2, "la orden aceptada no volvió a leer el estado"
    assert "ORDEN ACEPTADA" in _txt(out, "pin-msg")


@pytest.mark.parametrize(
    ("status_http", "pin", "grito"),
    [
        (401, "", "CAPTURE EL PIN DE 6 DÍGITOS"),
        (401, "123456", "PIN INCORRECTO"),
        (403, "123456", "SIN PIN CONFIGURADO"),
        (429, "123456", "BLOQUEADO POR INTENTOS"),
        (409, "123456", "ERROR 409"),
        ("network", "123456", "SIN CONEXIÓN CON EL GABINETE"),
    ],
)
def test_una_orden_rechazada_se_grita(tmp_path, status_http, pin, grito):
    """Incidente 2026-07-31: un armado falló EN SILENCIO junto al PIN.

    A distancia de kiosco el mensajito no existe; el rechazo tiene que ocupar
    pantalla y nombrar la orden que no pasó. El 401 tiene DOS causas distintas
    (no se tecleó PIN / el PIN está mal) y decirlas al revés manda al operador
    a teclear algo que ya tecleó.
    """
    out = _render(
        tmp_path,
        pin=pin,
        actionStatus={"api/siren-test": status_http},
        clicks=["action:PROBAR SIRENA"],
    )
    assert not _hidden(out, "action-toast")
    toast = _txt(out, "action-toast-txt")
    assert "PROBAR SIRENA" in toast
    assert grito in toast
    assert grito in _txt(out, "pin-msg")


def test_sin_pin_capturado_no_se_manda_el_header(tmp_path):
    """Sondear con un header vacío QUEMA intentos y acerca el lockout de 60 s.

    El servidor trata la ausencia de header como "la página pregunta" (401 que
    no cuenta); mandar `X-Takab-Pin: ''` lo convertiría en un intento fallido.
    """
    out = _render(tmp_path, pin="", clicks=["action:PROBAR SIRENA"])
    (post,) = _posts(out, "api/siren-test")
    assert post["headers"] == {}

    out = _render(tmp_path, pin="123456", clicks=["action:PROBAR SIRENA"])
    (post,) = _posts(out, "api/siren-test")
    assert post["headers"] == {"X-Takab-Pin": "123456"}


def test_el_grito_no_aparece_cuando_la_orden_pasa(tmp_path):
    out = _render(tmp_path, clicks=["action:PROBAR SIRENA"])
    assert _hidden(out, "action-toast")


def test_calibrar_la_brujula_sin_senal_es_un_409_visible(tmp_path):
    """El servidor responde 409 (`ActionUnavailable`): jamás un OK que no hizo nada."""
    out = _render(
        tmp_path,
        actionStatus={"api/rose-zero": 409},
        clicks=["action:CALIBRAR BRÚJULA", "confirm"],
    )
    assert "ERROR 409" in _txt(out, "action-toast-txt")


# ------------------------------------------------------------- interacción


def test_las_pestanas_de_la_bitacora_conmutan(tmp_path):
    out = _render(tmp_path, catalog=_CATALOG, clicks=["#tab-ssn"])
    assert _hidden(out, "pane-local")
    assert not _hidden(out, "pane-ssn")
    out = _render(tmp_path, catalog=_CATALOG, clicks=["#tab-ssn", "#tab-local"])
    assert not _hidden(out, "pane-local")
    assert _hidden(out, "pane-ssn")


def test_el_mapa_se_abre_y_se_cierra(tmp_path):
    out = _render(tmp_path, catalog=_CATALOG, clicks=["#open-map"])
    assert not _hidden(out, "overlay")
    out = _render(tmp_path, catalog=_CATALOG, clicks=["#open-map", "#close-map"])
    assert _hidden(out, "overlay")


def test_el_alcance_del_mapa_conmuta_local_y_regional(tmp_path):
    out = _render(tmp_path, catalog=_CATALOG, clicks=["#open-map", "data:scope:local", "frame"])
    assert any("ALCANCE RED LOCAL" in t for t in out["canvasText"])
    out = _render(tmp_path, catalog=_CATALOG, clicks=["#open-map", "data:scope:regional", "frame"])
    assert any("ALCANCE REGIONAL" in t for t in out["canvasText"])


def test_las_variantes_de_la_brujula_se_declaran(tmp_path):
    out = _render(tmp_path, clicks=["data:variant:B", "frame"])
    assert "variante B" in _txt(out, "rose-variant-note")
    assert "Vector horizontal resultante" in _txt(out, "quorum-note")


# --------------------------------------------------------- cajón comparativo


def test_el_cajon_comparativo_pide_una_seleccion(tmp_path):
    out = _render(tmp_path, catalog=_CATALOG, clicks=["#open-map"])
    assert "SELECCIONE UN SISMO" in _txt(out, "cmp-facts")


def test_la_comparativa_declara_que_es_estimacion_no_medicion(tmp_path):
    out = _render(tmp_path, catalog=_CATALOG, clicks=["#open-map", "row:ssn-rows-big", "frame"])
    texto = _txt(out, "cmp-facts")
    assert "ESTIMACIÓN TEÓRICA" in texto
    assert "NO ES DATO MEDIDO" in texto
    assert "DISTANCIA EPICENTRAL" in texto
    assert "ARRIBO P TEÓRICO" in texto


def test_la_comparativa_sin_dato_medido_lo_dice(tmp_path):
    st = _base()
    st["shake_history"] = None  # sin agregado no hay bucket que comparar
    out = _render(tmp_path, status=st, catalog=_CATALOG, clicks=["#open-map", "row:ssn-rows-big"])
    assert "SIN DATO MEDIDO" in _txt(out, "cmp-facts")


def test_una_estacion_vecina_no_finge_medir(tmp_path):
    out = _render(
        tmp_path,
        catalog=_CATALOG,
        clicks=["#open-map", "row:ssn-rows-big", "row:station-rows"],
    )
    # La primera fila es la estación PROPIA; se comprueba que la lista es clicable
    # y que el modelo distingue quién mide (solo la propia).
    assert "ESTA ESTACIÓN" in _txt(out, "station-rows")
    assert "VECINA" in _txt(out, "station-rows")


def test_sin_catalogo_el_cajon_y_el_mapa_lo_declaran(tmp_path):
    out = _render(tmp_path, clicks=["#open-map", "frame"])
    assert "CATÁLOGO NO DISPONIBLE" in _txt(out, "cmp-facts")


# ------------------------------------------------------------ invariantes


def test_el_panel_no_lanza_un_segundo_bucle_de_poll(tmp_path):
    """Un `setTimeout` de más = dos ticks concurrentes contra un servidor de hilos."""
    out = _render(tmp_path, clicks=["tick", "tick"])
    assert out["pendingTimeouts"] == 1


# ------------------------------------------- T-2.65 · baja administrativa
#
# Un gabinete retirado en la nube SIGUE PROTEGIENDO y lo DECLARA. Antes el panel
# decía `ENLACE NUBE · CONECTADO` y era verdad —el MQTT vive—, pero era media
# verdad: la consola ya no lo veía. La única huella local era que `config_version`
# dejaba de subir, sin edad: invisible. El 2026-08-04 `gw-dev-0001` siguió
# latiendo así y lo detectó un operador preguntando por su estación.


def test_baja_en_la_nube_se_declara_sin_dejar_de_prometer_proteccion(tmp_path):
    st = _base()
    st["cloud"] = {**st["cloud"], "admin_state": "retired"}
    out = _render(tmp_path, status=st)
    assert not _hidden(out, "banner-baja")
    texto = _txt(out, "banner-baja")
    assert "DADO DE BAJA EN LA NUBE" in texto
    assert "SIGUE PROTEGIENDO" in texto
    # La mitad que de verdad importa al que está parado frente al gabinete.
    assert "SASMEX" in texto


def test_gabinete_activo_no_pinta_la_baja(tmp_path):
    """El default no puede inventar un cartel de baja en un gabinete sano."""
    assert _hidden(_render(tmp_path, status=_base()), "banner-baja")


def test_status_sin_admin_state_no_pinta_la_baja(tmp_path):
    """Nube vieja (o sección caída): la AUSENCIA del dato jamás enciende el aviso."""
    st = _base()
    st["cloud"] = {"online": True, "mqtt_rtt_ms": 84.0, "queued": 0}
    out = _render(tmp_path, status=st)
    assert _hidden(out, "banner-baja")


def test_una_alerta_sismica_real_tapa_el_aviso_de_baja(tmp_path):
    """CRITERIO 3: nunca por encima de una alerta sísmica real."""
    st = _base()
    st["cloud"] = {**st["cloud"], "admin_state": "retired"}
    st["sasmex_active"] = True
    out = _render(tmp_path, status=st)
    assert not _hidden(out, "banner-alert")
    assert _hidden(out, "banner-baja")


def test_el_aviso_de_baja_va_por_debajo_de_todos_los_banners(tmp_path):
    """La precedencia REAL del panel no es una tabla ni un z-index: es el ORDEN
    FÍSICO en el marcado (los banners son hermanos directos de <body>) más un
    guard por banner. Este es el primer test del repo que afirma esa posición —
    los ocho de arriba solo afirman visible/oculto, así que un banner insertado
    encima de la alerta roja no habría roto nada.
    """
    st = _base()
    st["cloud"] = {**st["cloud"], "admin_state": "retired"}
    out = _render(tmp_path, status=st)
    kids = [k["id"] for k in _node(out["tree"], "__body__")["kids"] if k.get("id")]
    assert "banner-baja" in kids
    for encima in ("banner-wr1", "banner-alert", "banner-aviso", "banner-latched"):
        assert kids.index("banner-baja") > kids.index(encima), (
            f"#banner-baja se pinta por ENCIMA de #{encima}"
        )


def test_sin_enlace_el_aviso_de_baja_no_se_afirma_en_presente(tmp_path):
    """Regla de oro 7 traducida a este dato. `cloud_admin_state` NO caduca —es un
    hecho administrativo enclavado, firmado y persistido, no una medición— así que
    NO se oculta por viejo: ocultarlo volvería el silencio indistinguible de una
    avería, que es el bug original. Pero sin enlace un `restore` de la nube no
    puede alcanzar al gabinete, así que el aviso se CALIFICA con la versión de
    config que lo respalda en vez de afirmarse en presente.
    """
    st = _base()
    st["cloud"] = {"online": False, "mqtt_rtt_ms": None, "queued": 3, "admin_state": "retired"}
    st["config_version"] = 41
    out = _render(tmp_path, status=st)
    assert not _hidden(out, "banner-baja")
    meta = _txt(out, "baja-meta")
    assert "v41" in meta
    assert "SIN ENLACE" in meta
