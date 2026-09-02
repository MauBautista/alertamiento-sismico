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
FG3 = "#8A9CB1"

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
        # [T-2.68] POR QUÉ la lista es esa. Nominal: los declarados = los vivos.
        "relays_status": {
            "reason": "ok",
            "installed": ["gas_valve", "siren"],
            "missing": [],
        },
        # [T-2.146 · SPOF-02] Nominal HOY = sin ruta de hardware: el `K_wd` no está
        # montado (`D-16` aplazó la BOM), así que el latido nace deshabilitado. No es
        # una avería, y por eso tiene rótulo propio y no el de «no late».
        "keepalive": {"estado": "sin_ruta", "enabled": False, "beating": False},
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
        # [T-2.67] Respaldo de evidencia AL CORRIENTE: nada pendiente, nada perdido.
        "evidence": {
            "pending": 0,
            "items": [],
            "unreadable": 0,
            "unreadable_items": [],
            "oldest_pending_age_s": None,
            "checked_age_s": 42.0,
            "phase": "idle",
            "durable": True,
            "uploaded_total": 6,
            "discarded_no_data_total": 0,
            "failed_total": 0,
            "extract_failed_total": 0,
            "last_result": "uploaded",
            "last_result_age_s": 1830.0,
            "stale_after_s": 3600.0,
        },
        "drill": None,
        # [T-2.85.a] `finished_at`/`age_s`: sin fecha, un `RETORNO CONFIRMADO`
        # de hace nueve días se pinta igual que uno de hace tres segundos.
        "actuation_test": {
            "active": False,
            "results": None,
            "finished_at": None,
            "age_s": None,
        },
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
            # [T-2.68] "Arranque en frío" NO es una causa: gpio puebla sus cinco
            # canales antes de que el panel escuche. Una lista vacía aquí no
            # tiene explicación conocida, y eso es la PEOR causa, no la benigna.
            "relays_status": {"reason": "unknown", "installed": None, "missing": []},
            # En frío no se pudo leer el gpio: no se afirma ninguno de los tres.
            "keepalive": {"estado": "sd", "enabled": False, "beating": None},
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
            # Módulo de respaldo aún sin arrancar: la sección degrada a null.
            "evidence": None,
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
    # [T-2.66] La edad llega CALCULADA del gabinete: el arnés expone el `Date`
    # REAL (panel_harness.js), así que una edad de navegador caducaría con el
    # calendario. Por defecto: instantánea fresca del feed firmado.
    "provenance": {
        "version": 3,
        "origin": "signed_feed",
        "installed_at": "2026-08-04T09:05:00+00:00",
        "captured_at": "2026-08-04T09:00:00",
        "captured_age_s": 3600.0,
        "installed_age_s": 3300.0,
        "stale_after_s": 172800.0,
    },
}


def _catalog(**provenance) -> dict:
    """El catálogo de referencia con la procedencia sobrescrita campo a campo."""
    cat = json.loads(json.dumps(_CATALOG))
    if provenance.pop("sin_procedencia", False):
        cat.pop("provenance")
        return cat
    cat["provenance"].update(provenance)
    return cat


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
    """Custom properties DECLARADAS en el `:root` del propio `index.html`.

    Los comentarios CSS se quitan antes de leer: el `:root` de este panel
    documenta por qué vale cada color, y varias de esas explicaciones citan el
    valor viejo que reemplazaron. Contarlas convertiría cada explicación en una
    declaración fantasma —`--tk-violet` seguía «existiendo» sólo porque el
    comentario de T-2.137 cuenta que dejó de existir—. Misma disciplina que
    `estadoGlosario.test.ts` con la prosa de la consola.
    """
    html = re.sub(r"/\*[\s\S]*?\*/", "", _INDEX.read_text("utf-8"))
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


# ------------------------------------------------- [T-2.137] el violeta único
#
# `soc.css` AFIRMABA POR ESCRITO que su violeta «es el mismo color que el
# `banner-wr1` del panel LAN». No lo era, y de tres formas a la vez:
#
#   · el panel declaraba `--tk-violet:#7C4DFF`, un nombre que el paquete de
#     tokens no conoce (por eso el espejo de arriba no lo veía: solo cruzaba
#     `--tk-fg-*` y `--tk-surface-*`);
#   · la consola pinta `--tk-status-maintenance` = `#A78BFA`;
#   · y el TEXTO del banner del panel no era ninguno de los dos, sino un
#     tercer violeta a fuego, `#B79CFF`, inline en el marcado — invisible para
#     cualquier espejo que solo mire custom properties.
#
# Las dos superficies dicen lo mismo —«este equipo NO va a alertar»— y quien
# opera mira las dos. Medido (WCAG 2.x, sobre el tinte de cada banner):
#
#   rol                                     #7C4DFF   #A78BFA   umbral
#   texto del banner sobre su tinte (panel)   2.86      4.53      4.5 (AA)
#   texto de `.soc-maint` (consola)           2.65      4.69      4.5 (AA)
#   borde del banner contra su propio tinte   2.86      4.53      3.0 (no-texto)
#
# `#7C4DFF` REPRUEBA en los tres roles; solo sobrevivía porque el panel jamás
# lo usó como texto. Gana `#A78BFA`, que es además el que ya vive en el
# paquete. El panel no puede importarlo (se sirve como un único fichero
# estático desde un Pi sin build ni red), así que su copia queda vigilada aquí.


def _hex_a_rgb(color: str) -> tuple[int, int, int]:
    crudo = color.lstrip("#")
    return (int(crudo[0:2], 16), int(crudo[2:4], 16), int(crudo[4:6], 16))


def _es_violeta(r: int, g: int, b: int) -> bool:
    """Azul-violeta saturado: el rango del que hablan las dos pantallas.

    Se mide por TONO y no por lista de hexes conocidos: una lista solo caza el
    violeta que ya sabíamos que existía, y el defecto de esta ficha fue
    justamente un cuarto tono que nadie había enumerado.
    """
    return b > 120 and b - max(r, g) > 40 and r > g


def _violetas_del_panel() -> dict[str, str]:
    """Todo violeta del panel —`#RRGGBB` y `rgba()`— con dónde aparece.

    Sin comentarios (HTML, CSS y JS): citar el color que se retiró no es
    pintarlo, y contarlo dejaría el censo imposible de documentar.
    """
    html = _INDEX.read_text("utf-8")
    sin_comentarios = re.sub(r"<!--[\s\S]*?-->", "", html)
    sin_comentarios = re.sub(r"/\*[\s\S]*?\*/", "", sin_comentarios)
    hallados: dict[str, str] = {}
    for m in re.finditer(r"#[0-9a-fA-F]{6}", sin_comentarios):
        r, g, b = _hex_a_rgb(m.group(0))
        if _es_violeta(r, g, b):
            hallados[m.group(0).upper()] = "hex"
    for m in re.finditer(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", sin_comentarios):
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        if _es_violeta(r, g, b):
            hallados[f"#{r:02X}{g:02X}{b:02X}"] = m.group(0)
    return hallados


def test_el_panel_no_tiene_mas_que_un_violeta_y_es_el_del_paquete():
    """UN solo violeta en el panel, y el que manda el design system.

    Eran tres: `--tk-violet:#7C4DFF`, el tinte `rgba(124,77,255,…)` y un
    `#B79CFF` a fuego en el `<span>` del banner. El tercero es el que enseña la
    lección: un espejo que solo compara custom properties no ve un color
    escrito inline, y ahí es donde vivía el texto que la persona lee.
    """
    paquete = json.loads(_TOKENS_JSON.read_text("utf-8"))
    canonico = paquete["--tk-status-maintenance"].upper()
    hallados = _violetas_del_panel()
    assert hallados, "el barrido no encontró NINGÚN violeta: si esto pasa, el resto miente"
    intrusos = {c: donde for c, donde in hallados.items() if c != canonico}
    assert not intrusos, (
        "el panel pinta un violeta que no es `--tk-status-maintenance` "
        f"({canonico}) del paquete:\n"
        + "\n".join(f"  · {c} (como {donde})" for c, donde in sorted(intrusos.items()))
        + "\nEl panel no puede importar el paquete: su copia se corrige aquí, "
        "nunca al revés."
    )


def test_el_violeta_de_mantenimiento_del_panel_se_declara_con_el_nombre_del_paquete():
    """La copia lleva el NOMBRE del token, no un alias local.

    Con `--tk-violet` el espejo `test_la_paleta_del_panel_no_inventa_su_propia_
    verdad` no tenía contra qué compararlo y la divergencia sobrevivió un ciclo
    entero. Con el nombre del paquete, cualquier futuro cambio de valor en
    `tokens.json` se ve desde aquí.
    """
    paquete = json.loads(_TOKENS_JSON.read_text("utf-8"))
    root = _root_vars()
    assert "--tk-violet" not in root, (
        "`--tk-violet` no existe en `@takab/design-tokens`: el panel volvería a "
        "tener un color propio que el design system no gobierna."
    )
    assert "--tk-status-maintenance" in root, (
        "el panel dejó de declarar `--tk-status-maintenance`; el banner del modo "
        "prueba WR-1 se pintaría desde un fallback."
    )
    assert root["--tk-status-maintenance"].upper() == paquete["--tk-status-maintenance"].upper(), (
        f"panel {root['--tk-status-maintenance']} ≠ paquete {paquete['--tk-status-maintenance']}"
    )


def test_el_banner_wr1_se_lee_de_pie_frente_al_gabinete():
    """El rótulo que dice «LA NUBE NO RECIBE ALERTAS» tiene que LEERSE.

    Es de 13 px en negrita —no es «texto grande» de WCAG, que empieza en 18.66
    px en negrita—, así que le toca el 4.5:1 de AA. Se mide sobre el tinte REAL
    del banner (el violeta al 16 % compuesto sobre `--tk-surface-0`), no sobre
    el fondo de la página: componer el alfa a mano es de donde salía la
    impresión de que `#7C4DFF` valía como color de texto (2.86:1).
    """
    html = _INDEX.read_text("utf-8")
    root = _root_vars()
    violeta = root["--tk-status-maintenance"]

    regla = re.search(r"#banner-wr1\{([^}]*)\}", html)
    assert regla, "el banner del modo prueba WR-1 perdió su regla CSS"
    alfa_txt = re.search(r"background:\s*rgba\([^)]*,\s*([0-9.]+)\s*\)", regla.group(1))
    assert alfa_txt, f"el tinte del banner ya no es un rgba(): {regla.group(1)}"

    alfa = float(alfa_txt.group(1))
    vr, vg, vb = _hex_a_rgb(violeta)
    sr, sg, sb = _hex_a_rgb(root["--tk-surface-0"])
    tinte = "#{:02X}{:02X}{:02X}".format(
        *(round(alfa * v + (1 - alfa) * s) for v, s in ((vr, sr), (vg, sg), (vb, sb)))
    )

    medido = _contraste(violeta, tinte)
    assert medido >= _AA, (
        f"el rótulo del banner WR-1 ({violeta}) sobre su propio tinte ({tinte}) "
        f"mide {medido:.2f}:1, por debajo de AA ({_AA}). Es el letrero que avisa "
        "de que la nube está ciega: si no se lee, no avisa."
    )


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
    "evi-state",
    "evi-rows",
    # [T-2.85.a] Resultado de PROBAR ACTUADORES. Ni con prueba ni sin ella puede
    # quedarse muda: "aquí no pone nada" se lee como "no pasa nada".
    "test-state",
    "test-rows",
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


# ------------------------------- T-2.85.a · el resultado de PROBAR ACTUADORES
#
# El botón hace lectura de retorno sobre el gas y los ascensores —ejerce
# físicamente el equipamiento del edificio— y hasta aquí no enseñaba si había
# pasado: `held`/`pulsed`/`readback_ok` viajaban en `status()` y sólo aparecían
# en los datos de demo del propio HTML. Es la única prueba que el operador puede
# hacer él solo, y el manual de operación no podía decirle cómo leer su
# resultado. La CLASE de defecto la vigila `test_panel_render_census.py`.


def _con_prueba(**cambios) -> dict:
    """Status con una prueba TERMINADA: cuatro desenlaces + uno sin probar."""
    st = _base()
    st["relays_status"] = {
        "reason": "ok",
        "installed": ["door_retainer", "elevator", "gas_valve", "siren", "strobe"],
        "missing": [],
    }
    st["actuation_test"] = {
        "active": False,
        "finished_at": _NOW,
        "age_s": 6.0,
        "results": {
            "ok": False,
            "reason": "readback falló en: elevator, door_retainer",
            "relays": {
                "siren": {
                    "held": True,
                    "readback_ok": True,
                    "fail_safe": "normally_open",
                    "energized": True,
                },
                "gas_valve": {
                    "pulsed": True,
                    "readback_ok": True,
                    "fail_safe": "fail_close",
                    "energized": True,
                },
                "elevator": {
                    "pulsed": True,
                    "readback_ok": False,
                    "fail_safe": "normally_open",
                    "energized": False,
                },
                "door_retainer": {
                    "pulsed": False,
                    "readback_ok": False,
                    "fail_safe": "normally_closed",
                    "energized": None,
                },
            },
        },
    }
    st["actuation_test"].update(cambios)
    return st


def test_el_resultado_de_la_prueba_se_pinta_rele_a_rele(tmp_path):
    """Criterio 1: el resultado por relé, CON su lectura de retorno."""
    texto = _txt(_render(tmp_path, status=_con_prueba()), "test-rows")
    assert "SIRENA" in texto and "SOSTENIDO · RETORNO OK" in texto
    assert "GAS" in texto and "PULSO · RETORNO OK" in texto
    # El fail-safe y el estado eléctrico en que quedó: el gas cierra sin
    # corriente y las puertas liberan, y eso no se deduce del veredicto.
    assert "fail-safe fail_close" in texto
    assert "ENERGIZADO" in texto


def test_un_rele_que_no_confirma_se_distingue_de_uno_que_no_se_probo(tmp_path):
    """Criterio 2 (regla de oro 7). Son tres cosas, no una.

    `NO CONFIRMÓ` manda a llamar a soporte; `NO SE PROBÓ` no es un fallo y
    pintarlo como tal manda a buscar una avería que no existe.
    """
    texto = _txt(_render(tmp_path, status=_con_prueba()), "test-rows")
    assert "ASCENSORES" in texto and "NO CONFIRMÓ EL RETORNO" in texto
    assert "PUERTAS" in texto and "SIN RELÉ DETRÁS" in texto
    # `strobe` está DECLARADO instalado y la prueba no lo tocó.
    assert "NO SE PROBÓ" in texto
    assert texto.count("NO SE PROBÓ") == 1, "solo el estrobo quedó sin probar"
    # …y la píldora resume sin colapsar: dos relés sin confirmar, en rojo.
    assert "2 RELÉS SIN CONFIRMAR" in _txt(_render(tmp_path, status=_con_prueba()), "test-state")


def test_una_prueba_en_verde_lo_dice_y_cuenta_los_reles(tmp_path):
    st = _con_prueba()
    for canal in st["actuation_test"]["results"]["relays"].values():
        canal["readback_ok"] = True
        canal.pop("pulsed", None)
        canal["held"] = True
    st["actuation_test"]["results"]["ok"] = True
    st["actuation_test"]["results"]["reason"] = None
    assert "RETORNO CONFIRMADO" in _txt(_render(tmp_path, status=st), "test-state")


def test_un_resultado_sin_hora_no_se_pinta_como_reciente(tmp_path):
    """Regla de oro 7: un `RETORNO CONFIRMADO` sin fecha es un dato congelado."""
    fresco = _txt(_render(tmp_path, status=_con_prueba()), "test-rows")
    assert "10:00:00 UTC" in fresco and "hace 6 s" in fresco
    viejo = _txt(_render(tmp_path, status=_con_prueba(finished_at=None, age_s=None)), "test-rows")
    assert "HORA S/D" in viejo and "hace S/D" in viejo


def test_sin_prueba_la_tarjeta_lo_declara_en_vez_de_callar(tmp_path):
    """Una tarjeta muda se lee como «aquí no pasa nada»."""
    out = _render(tmp_path, status=_base())
    assert "SIN PRUEBA DESDE EL ARRANQUE" in _txt(out, "test-state")
    assert "PROBAR ACTUADORES" in _txt(out, "test-rows")


def test_una_prueba_rechazada_no_se_lee_como_un_fallo_del_equipamiento(tmp_path):
    """El gpio se niega a probar con una alerta viva: eso no es un relé roto."""
    st = _con_prueba()
    st["actuation_test"]["results"] = {
        "ok": False,
        "reason": "alerta o protección viva; prueba local rechazada",
        "relays": {},
    }
    out = _render(tmp_path, status=st)
    assert "PRUEBA RECHAZADA" in _txt(out, "test-state")
    assert "alerta o protección viva" in _txt(out, "test-rows")
    assert "NO CONFIRMÓ" not in _txt(out, "test-rows")


def test_mientras_sostiene_la_tarjeta_no_promete_un_resultado(tmp_path):
    st = _con_prueba(active=True)
    out = _render(tmp_path, status=st)
    assert "EN CURSO" in _txt(out, "test-state")
    assert "RETORNO OK" not in _txt(out, "test-rows")


def test_la_calibracion_dice_de_donde_viene(tmp_path):
    """Criterio 3: `calibration.source` se pinta cuando existe.

    De la procedencia depende que el PGA esté en `g` o sea un número relativo:
    el panel gritaba `SIN CALIBRAR` y, cuando SÍ había calibración, callaba.
    """
    out = _render(tmp_path, status=_base())
    assert _hidden(out, "nocal-pill")
    assert not _hidden(out, "cal-pill")
    assert "CALIBRADO · StationXML" in _txt(out, "cal-pill")

    frio = _render(tmp_path, status=_cold())
    assert not _hidden(frio, "nocal-pill")
    assert _hidden(frio, "cal-pill")


def test_una_calibracion_sin_procedencia_se_declara_en_vez_de_afirmarse(tmp_path):
    """`calibrated` se DERIVA de la procedencia: las dos cosas a la vez es una
    contradicción del servidor, y el panel la delata en vez de callarla."""
    st = _base()
    st["calibration"] = {**st["calibration"], "source": None}
    out = _render(tmp_path, status=st)
    assert "PROCEDENCIA S/D" in _txt(out, "cal-pill")
    assert _value_color(out, "cal-pill", "PROCEDENCIA S/D") == WARN


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
    st["relays_status"] = {"reason": "unknown", "installed": None, "missing": []}
    out = _render(tmp_path, status=st)
    assert "RELÉS" in _txt(out, "relays")
    assert "S/D" in _txt(out, "relays")


# ------------------------------------------- T-2.68 · las causas del `RELÉS · S/D`
#
# El rótulo único "arranque en frío" era, además de ambiguo, el único estado que
# NUNCA ocurre: gpio puebla sus cinco canales —síncrono, bajo lock, índice 0 del
# toposort— antes de que el panel (índice 15) abra su socket. El panel acertaba
# cero veces de cada cuatro y la lectura que inducía ("todo bien, espera") era la
# más peligrosa posible mientras el proceso que toca la sirena podía estar roto.


def _con_reles(reason: str, *, relays=None, installed=None, missing=()) -> dict:
    """`_base()` con la lista de relés y su diagnóstico puestos a mano."""
    st = _base()
    st["relays"] = [] if relays is None else relays
    st["relays_status"] = {
        "reason": reason,
        "installed": installed,
        "missing": list(missing),
    }
    return st


def test_el_panel_ya_no_dice_arranque_en_frio(tmp_path):
    """El rótulo que mentía desaparece: no hay estado del gabinete que lo cumpla."""
    st = _con_reles("gpio_error", installed=["siren"], missing=["siren"])
    out = _render(tmp_path, status=st)
    assert "arranque en frío" not in _txt(out, "relays")


def test_gpio_averiado_no_se_lee_como_una_espera(tmp_path):
    """Causa (a): `relay_states()` LANZÓ con el módulo en marcha. Avería en rojo."""
    st = _con_reles("gpio_error", installed=["siren", "gas_valve"], missing=["gas_valve", "siren"])
    out = _render(tmp_path, status=st)
    texto = _txt(out, "relays")
    assert "AVERÍA" in texto
    assert "journal" in texto, "una avería sin acción no le sirve a quien está de pie ahí"
    assert _value_color(out, "relays", "AVERÍA") == CRIT


def test_gpio_detenido_se_distingue_de_gpio_averiado(tmp_path):
    """Causa (b): módulo detenido. NO lanza (regresión 2026-07-30), así que
    ningún `except` lo veía: solo `gpio.running` lo delata. Pide otra acción que
    una avería en caliente, y por eso no puede pintarse igual."""
    detenido = _txt(_render(tmp_path, status=_con_reles("gpio_stopped")), "relays")
    averiado = _txt(_render(tmp_path, status=_con_reles("gpio_error")), "relays")
    assert "DETENIDO" in detenido
    assert "NO puede accionar" in detenido
    assert detenido != averiado, "dos causas con reacciones distintas, un solo rótulo"


def test_el_dueno_de_los_pines_mudo_no_se_lee_como_averia_ni_como_detenido(tmp_path):
    """[T-2.70.a·D2/P1] Causa NUEVA: el dueño de los pines NO CONTESTA.

    No es «el módulo está parado» (eso lo sabríamos) ni «su lectura reventó en
    marcha» (eso es una avería del proceso que sí tenemos delante). Pintarla con
    cualquiera de los dos rótulos manda al operador a revisar el journal
    equivocado, que es exactamente el defecto que T-2.68 arregló para las otras.
    """
    mudo = _txt(_render(tmp_path, status=_con_reles("gpio_unreachable")), "relays")
    averiado = _txt(_render(tmp_path, status=_con_reles("gpio_error")), "relays")
    detenido = _txt(_render(tmp_path, status=_con_reles("gpio_stopped")), "relays")
    assert "NO CONTESTA" in mudo
    assert mudo != averiado and mudo != detenido, (
        "tres causas con reacciones distintas compartiendo rótulo"
    )
    assert (
        _value_color(
            _render(tmp_path, status=_con_reles("gpio_unreachable")), "relays", "NO CONTESTA"
        )
        == CRIT
    )


def test_sin_poder_medir_el_gabinete_la_pantalla_dice_S_D_y_no_NO(tmp_path):
    """[T-2.70.a·D2/P1] `null` NO es `false`.

    Los cuatro booleanos del gabinete pasan a valer `null` cuando el panel no
    pudo medirlos, y el JS los leía por verdad simple: `sasmex_active` nulo se
    pintaba «SASMEX: NO» y `siren_sounding` nulo, «SIRENA: EN REPOSO». Un «no hay
    alerta» afirmado sobre un dato que nadie pudo medir es exactamente la mentira
    tranquilizadora de la regla de oro 7.
    """
    st = _base()
    for campo in ("sasmex_active", "siren_sounding", "audible_silenced", "alert_latched"):
        st[campo] = None
    st["relays"] = []
    st["relays_status"] = {"reason": "gpio_unreachable", "installed": None, "missing": []}
    texto = _txt(_render(tmp_path, status=st), "tier-sub")
    assert "SIRENA: S/D" in texto, texto
    assert "SASMEX: S/D" in texto, texto
    assert "EN REPOSO" not in texto
    assert "SASMEX: NO" not in texto


def test_config_ilegible_avisa_que_la_lista_no_se_filtro(tmp_path):
    """Causa (c): el `try` único cubría gpio Y config, así que un store corrupto
    se pintaba como gpio roto. El estado eléctrico sí se midió: se pinta, con la
    advertencia de que el filtro de equipamiento no se pudo aplicar."""
    st = _con_reles("config_error", relays=_base()["relays"], installed=None)
    out = _render(tmp_path, status=st)
    texto = _txt(out, "relays")
    assert "SIRENA" in texto, "el estado medido no se tira por un rótulo que falta"
    assert "PERFIL" in texto
    assert "no instalados" in texto
    assert _value_color(out, "relays", "PERFIL") == CRIT


def test_un_sitio_sin_actuadores_no_se_pinta_como_averia(tmp_path):
    """Causa (d): los cinco declarados `false`. Lista vacía LEGÍTIMA — ni la
    consola ni el env exigen "al menos uno". Es ámbar (revisa el perfil), no
    rojo (el gabinete está roto)."""
    out = _render(tmp_path, status=_con_reles("no_actuators_installed", installed=[]))
    texto = _txt(out, "relays")
    assert "SIN ACTUADORES" in texto
    assert "0 instalados" in texto
    assert _value_color(out, "relays", "SIN ACTUADORES") == WARN


def test_la_lista_parcial_delata_los_reles_que_faltan(tmp_path):
    """La lista CORTA miente igual que la vacía y nada la disparaba: con los
    cinco declarados y dos vivos, el panel pintaba dos filas y callaba las
    otras tres."""
    st = _con_reles(
        "partial",
        relays=_base()["relays"],
        installed=["door_retainer", "elevator", "gas_valve", "siren", "strobe"],
        missing=["door_retainer", "elevator", "strobe"],
    )
    out = _render(tmp_path, status=st)
    texto = _txt(out, "relays")
    assert "SIRENA" in texto  # las filas vivas siguen ahí
    assert "INCOMPLETO" in texto
    for etiqueta in ("PUERTAS", "ASCENSORES", "ESTROBO"):
        assert etiqueta in texto, f"el relé ausente {etiqueta} no se nombra"
    assert "revisar journal" in texto
    assert _value_color(out, "relays", "INCOMPLETO") == CRIT


def test_sin_causa_conocida_el_panel_asume_lo_peor(tmp_path):
    """El default es la PEOR causa. Sin explicación, la lista vacía se trata como
    avería del proceso que toca la sirena — jamás como una espera benigna."""
    out = _render(tmp_path, status=_con_reles("unknown"))
    texto = _txt(out, "relays")
    assert "S/D" in texto
    assert "sin causa conocida" in texto
    assert _value_color(out, "relays", "S/D") == CRIT, "un ámbar aquí invita a esperar"


def test_una_causa_desconocida_por_el_panel_tambien_es_lo_peor(tmp_path):
    """Razón que este panel no conoce (servidor más nuevo) ⇒ peor caso, no hueco."""
    out = _render(tmp_path, status=_con_reles("causa_del_futuro"))
    assert _value_color(out, "relays", "S/D") == CRIT


def test_un_status_sin_relays_status_no_deja_muda_la_zona(tmp_path):
    """El contrato es ADITIVO: un servidor viejo (sin el hermano) no puede dejar
    la zona en blanco ni pintar la lista vacía como si no pasara nada."""
    st = _base()
    st["relays"] = []
    del st["relays_status"]
    out = _render(tmp_path, status=st)
    assert "RELÉS" in _txt(out, "relays")
    assert _value_color(out, "relays", "S/D") == CRIT


def test_la_escena_demo_de_gpio_caido_pinta_la_averia(tmp_path):
    """Las escenas demo son la TERCERA copia del contrato y el test de `status()`
    no las cubre: un olvido ahí pasa el CI pintando `undefined`. Esta se ejecuta
    de verdad."""
    out = _render(tmp_path, search="?demo=gpio_caido", clicks=["frame"])
    assert "AVERÍA" in _txt(out, "relays")
    assert _value_color(out, "relays", "AVERÍA") == CRIT


def test_la_escena_demo_de_arranque_frio_ya_no_miente(tmp_path):
    """La escena conserva su nombre histórico; el rótulo que inducía a esperar,
    no. Ese estado no existe en el gabinete real."""
    out = _render(tmp_path, search="?demo=arranque_frio", clicks=["frame"])
    assert "arranque en frío" not in _txt(out, "relays")
    assert _value_color(out, "relays", "S/D") == CRIT


def test_con_reles_vivos_el_panel_no_inventa_un_diagnostico(tmp_path):
    """Nominal: ni una línea de más. El diagnóstico solo aparece cuando hay algo
    que diagnosticar — un aviso permanente se vuelve invisible."""
    out = _render(tmp_path, status=_base())
    texto = _txt(out, "relays")
    assert "SIRENA" in texto and "GAS" in texto
    for rotulo in ("S/D", "AVERÍA", "INCOMPLETO", "DETENIDO", "SIN ACTUADORES"):
        assert rotulo not in texto, f"{rotulo} pintado con el gabinete sano"


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


# ------------------------------------------------ evidencia / backfill (T-2.67)
#
# La consola de nube ve la evidencia desde T-2.43; el panel del gabinete —lo
# único que queda CUANDO NO HAY NUBE— no veía nada. Y "no veía nada" era peor que
# un hueco: el mejor caso (subida confirmada) y el peor (descarte por ring vacío,
# que PIERDE la evidencia) borran el mismo fichero, así que desde fuera se veían
# idénticos. Estos tests fijan que cada causa tenga su rótulo y su color.


def _con_evidencia(**cambios) -> dict:
    st = _base()
    st["evidence"] = {**st["evidence"], **cambios}
    return st


def test_la_evidencia_al_corriente_no_alarma(tmp_path):
    out = _render(tmp_path, status=_base())
    assert "SIN EVIDENCIA PENDIENTE" in _txt(out, "evi-state")
    assert _node(out["tree"], "evi-state")["color"] == OK
    assert "ATASCADA" not in _txt(out, "evi-state")
    assert "6" in _txt(out, "evi-rows")  # las archivadas se declaran


def test_la_evidencia_atascada_se_delata_con_su_edad(tmp_path):
    """El gabinete real lleva semanas con evidencia pendiente y el panel callaba.

    Un pendiente más viejo que su umbral NO está "en camino": está atascado, y
    el operador tiene que enterarse aquí porque es el único sitio donde se ve
    sin nube.
    """
    st = _con_evidencia(
        pending=18,
        items=[{"event_id": "37af89a4", "age_s": 15.3 * 86400}],
        oldest_pending_age_s=15.3 * 86400,
        last_result="extract_failed",
        last_result_age_s=120.0,
        extract_failed_total=42,
        uploaded_total=0,
    )
    out = _render(tmp_path, status=st)

    assert "ATASCADA" in _txt(out, "evi-state")
    assert "15.3 d" in _txt(out, "evi-state")
    assert _node(out["tree"], "evi-state")["color"] == CRIT
    assert OK not in _colors(_node(out["tree"], "evi-state"))
    # …y con la causa medida, no un "falló" genérico: se reintenta sin progresar.
    assert "EXTRACCIÓN" in _txt(out, "evi-rows")
    assert "37af89a4" in _txt(out, "evi-rows")  # la evidencia LISTADA por evento


def test_la_evidencia_descartada_por_ring_vacio_se_llama_perdida(tmp_path):
    """Sin datos en el ring el fichero se borra igual que tras una subida OK.

    Si el panel solo contara "pendientes", una evidencia perdida se vería
    exactamente igual que una archivada: cola a cero y ni una palabra.
    """
    st = _con_evidencia(pending=0, discarded_no_data_total=2, uploaded_total=1)
    out = _render(tmp_path, status=st)

    assert "2 · EVIDENCIA PERDIDA" in _txt(out, "evi-rows")
    assert _value_color(out, "evi-rows", "EVIDENCIA PERDIDA") == CRIT


def test_la_evidencia_pendiente_sin_enlace_espera_y_no_es_un_fallo(tmp_path):
    """Sin nube, tener evidencia en cola es lo CORRECTO — no una avería."""
    st = _con_evidencia(pending=3, oldest_pending_age_s=300.0, last_result=None)
    st["cloud"] = {"online": False, "mqtt_rtt_ms": None, "queued": 47, "admin_state": "active"}
    out = _render(tmp_path, status=st)

    assert "EN ESPERA DE ENLACE" in _txt(out, "evi-state")
    assert _node(out["tree"], "evi-state")["color"] == WARN
    assert CRIT not in _colors(_node(out["tree"], "evi-state"))
    assert "ATASCADA" not in _txt(out, "evi-state")
    # …y el número de la cola MQTT (47) no se cuela en la sección de evidencia:
    # dos "EN COLA" con significados distintos serían un rótulo que desinforma.
    assert "47" not in _txt(out, "evi-state")


def test_el_respaldo_en_curso_se_distingue_del_atasco(tmp_path):
    st = _con_evidencia(pending=2, oldest_pending_age_s=90.0, phase="uploading")
    out = _render(tmp_path, status=st)
    assert "BACKFILL EN CURSO" in _txt(out, "evi-state")
    assert _node(out["tree"], "evi-state")["color"] == CYAN


def test_la_cola_de_evidencia_no_durable_se_declara(tmp_path):
    """Sin `cloud_spool_dir` la evidencia se evapora al reiniciar y el conteo
    diría 0 para siempre. El panel no puede callar eso: es el hueco de
    `provision_gateway.sh`, y afecta a todo gabinete recién aprovisionado."""
    out = _render(tmp_path, status=_con_evidencia(durable=False))
    assert "COLA NO DURABLE" in _txt(out, "evi-rows")
    assert _value_color(out, "evi-rows", "COLA NO DURABLE") == WARN


def test_sin_seccion_de_evidencia_el_panel_lo_dice(tmp_path):
    """Módulo caído ⇒ S/D honesto; jamás un verde por defecto ni un hueco mudo."""
    out = _render(tmp_path, status=_con_evidencia() | {"evidence": None})
    assert "S/D" in _txt(out, "evi-state")
    assert _node(out["tree"], "evi-state")["color"] == WARN
    assert _txt(out, "evi-rows").strip()


def test_un_pendiente_ilegible_se_nombra_en_el_panel(tmp_path):
    """El fichero apartado no puede desaparecer en silencio (regla de oro 7).

    Un `.json` que no es un objeto reventaba el arranque del gabinete ENTERO.
    Ya no revienta — pero "no revienta" no basta: si el panel callara, el
    directorio se llenaría de basura invisible. El operador está de pie frente
    al kiosco y sin shell: necesita el NOMBRE del fichero y la acción.
    """
    st = _con_evidencia(
        pending=2, oldest_pending_age_s=300.0, unreadable=1, unreadable_items=["evt-envenenado"]
    )
    out = _render(tmp_path, status=st)

    assert "PENDIENTE ILEGIBLE" in _txt(out, "evi-state")
    assert _node(out["tree"], "evi-state")["color"] == CRIT
    assert OK not in _colors(_node(out["tree"], "evi-state"))
    assert "evt-enve" in _txt(out, "evi-rows")  # NOMBRADO, no un número anónimo
    assert "BÓRRALO" in _txt(out, "evi-rows")  # …y con la acción concreta


def test_un_ilegible_no_lo_tapa_un_backfill_en_curso(tmp_path):
    """Una avería PERMANENTE que pide una persona gana a un estado transitorio."""
    st = _con_evidencia(
        pending=2,
        oldest_pending_age_s=90.0,
        phase="uploading",
        unreadable=1,
        unreadable_items=["evt-envenenado"],
    )
    out = _render(tmp_path, status=st)
    assert "ILEGIBLE" in _txt(out, "evi-state")
    assert "BACKFILL EN CURSO" not in _txt(out, "evi-state")


def test_un_ilegible_con_la_cola_vacia_sigue_gritando(tmp_path):
    """Cola a cero + fichero apartado NO es "al corriente": sería un verde falso."""
    st = _con_evidencia(pending=0, unreadable=2, unreadable_items=["evt-a", "evt-b"])
    out = _render(tmp_path, status=st)
    assert "SIN EVIDENCIA PENDIENTE" not in _txt(out, "evi-state")
    assert "2 PENDIENTES ILEGIBLES" in _txt(out, "evi-state")
    assert _node(out["tree"], "evi-state")["color"] == CRIT


def test_una_edad_de_evidencia_ilegible_no_se_pinta_como_recien_llegada(tmp_path):
    """`age_s = None` es "no se sabe", no "hace un momento": S/D, y sin verde."""
    st = _con_evidencia(pending=4, oldest_pending_age_s=None, items=[])
    out = _render(tmp_path, status=st)
    assert "S/D" in _txt(out, "evi-state")
    assert OK not in _colors(_node(out["tree"], "evi-state"))


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


# --- T-2.66 · el catálogo declara su edad y su procedencia -------------------


def test_catalogo_fresco_declara_edad_y_origen_en_tono_neutro(tmp_path):
    """Fresco NO es silencio: la edad exacta se ve siempre, para que nadie
    dependa del umbral para razonar. Pero el tono es neutro (no alarma)."""
    out = _render(tmp_path, catalog=_catalog(captured_age_s=3600.0))
    for zona in ("ssn-meta", "ssn-meta-big"):
        assert "HACE 60 m" in _txt(out, zona), _txt(out, zona)
        assert "FEED FIRMADO v3" in _txt(out, zona)
        assert "CATÁLOGO VIEJO" not in _txt(out, zona)
        assert _node(out["tree"], zona)["color"] == FG3
    # Las dos afirmaciones que implican ACTUALIDAD siguen siendo absolutas.
    assert _txt(out, "ssn-count") == "2"
    assert _txt(out, "ssn-nearest").startswith("MÁS CERCANO:")


def test_catalogo_viejo_se_rotula_ambar_sin_apagar_el_mapa(tmp_path):
    """Umbral cruzado ⇒ ÁMBAR y las dos afirmaciones de actualidad se
    relativizan a la captura. Pero NO se borra: a diferencia de un canal de
    señal (T-2.58), el catálogo es una instantánea FECHADA cuyos datos no se
    pudren — el mapa se ancla en `references` y la comparativa es teórica.
    Borrarlo apagaría las dos para castigar una afirmación que se arregla con
    un rótulo."""
    viejo = _catalog(captured_age_s=6 * 86400.0, stale_after_s=172800.0)
    out = _render(
        tmp_path, catalog=viejo, clicks=["#open-map", "frame", "row:ssn-rows-big", "frame"]
    )
    for zona in ("ssn-meta", "ssn-meta-big"):
        assert "CATÁLOGO VIEJO" in _txt(out, zona), _txt(out, zona)
        assert "6.0 d" in _txt(out, zona)  # no "144.0 h": ilegible justo donde importa
        assert "UMBRAL 2.0 d" in _txt(out, zona)
        assert _node(out["tree"], zona)["color"] == WARN
    assert "EN LA CAPTURA" in _txt(out, "ssn-count")
    assert _node(out["tree"], "ssn-count")["color"] == WARN
    assert "MÁS CERCANO EN LA CAPTURA" in _txt(out, "ssn-nearest")
    assert _node(out["tree"], "ssn-nearest")["color"] == WARN
    # …y todo lo que NO envejece sigue vivo: filas, comparativa y mapa.
    assert "M 5.4" in _txt(out, "ssn-rows-big")
    assert _txt(out, "cmp-facts").strip()
    assert any("ALCANCE" in t for t in out["canvasText"])


def test_catalogo_sin_edad_conocida_no_se_pinta_como_fresco(tmp_path):
    """Dos caminos a lo mismo: un gabinete viejo que no manda procedencia, y un
    `capturado` ilegible (es un string LIBRE). Ninguno puede afirmar frescura."""
    for cat in (_catalog(sin_procedencia=True), _catalog(captured_age_s=None)):
        out = _render(tmp_path, catalog=cat)
        assert "EDAD DESCONOCIDA" in _txt(out, "ssn-meta")
        assert _node(out["tree"], "ssn-meta")["color"] == WARN
        assert "EN LA CAPTURA" in _txt(out, "ssn-nearest")


def test_el_origen_distingue_feed_firmado_de_archivo_provisionado(tmp_path):
    """«De dónde vino» cambia la reacción: un archivo provisionado a mano no se
    actualiza solo, y `_load_once` solo lo relee al REINICIAR el servicio."""
    out = _render(tmp_path, catalog=_catalog(origin="provisioned_file", version=0))
    assert "ARCHIVO PROVISIONADO" in _txt(out, "ssn-meta")
    assert "FEED FIRMADO" not in _txt(out, "ssn-meta")


def test_el_muro_hereda_el_ambar_del_catalogo_viejo(tmp_path):
    """El muro es la pantalla que se ve DE LEJOS y copiaba el texto sin el
    color: el rótulo ámbar se perdía justo donde más se mira."""
    out = _render(tmp_path, catalog=_catalog(captured_age_s=6 * 86400.0), clicks=["data:mode:muro"])
    assert "CATÁLOGO VIEJO" in _txt(out, "muro-ssnmeta")
    assert _node(out["tree"], "muro-ssnmeta")["color"] == WARN
    assert "EN LA CAPTURA" in _txt(out, "muro-nearest")
    assert _node(out["tree"], "muro-nearest")["color"] == WARN


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


# --------------------------------------------------- [T-5.01] modo demo INERTE
#
# El defecto que estos tests vienen a cerrar, medido en la auditoría V1-COMERCIAL
# (2026-09-02): con `?demo=` puesto, `doAction()` hacía el POST igual —el único
# `if (!DEMO)` del flujo solo se saltaba el refetch de estado— y `PROBAR
# ACTUADORES` («sostiene sirena+estrobo · pulso en gas, ascensores, puertas») se
# pintaba incondicionalmente. O sea: abrir el panel en modo demo en el monitor de
# una exposición y pulsar un botón **accionaba el edificio de verdad**, mientras
# la cinta de arriba afirmaba `DEMO · NO ES ESTADO REAL`.
#
# Es la familia de defecto que este repositorio ya persigue —una superficie que
# dice «bien» cuando quiere decir «no sé»— con un agravante: aquí la superficie
# dice «nada de lo que ves es real» al lado de un botón que sí lo es.
#
# LOS TESTS CUENTAN PETICIONES, NO LEEN PROSA. Un test que comprobara el rótulo
# `INERTE` habría pasado en verde con el POST intacto, que es exactamente cómo
# `test_el_modo_demo_se_declara_siempre` —que sigue siendo correcto— convivió con
# el defecto durante meses: verifica que la cinta se VEA, no que los botones
# estén inertes.


def _escenas_demo() -> list[str]:
    """Los nombres de escena, DERIVADOS del propio `index.html`.

    Escritos a mano, una escena nueva entraría sin prueba — y las escenas son
    justo lo que puebla la pantalla de falsedades creíbles. El delimitador es el
    literal del objeto, y que se haya delimitado de verdad lo comprueba el
    `assert` de no-vacuidad de aquí abajo.
    """
    html = _INDEX.read_text("utf-8")
    i = html.index("const SCENES = {")
    bloque = html[i : html.index("\n};", i)]
    escenas = re.findall(r"^  ([a-z_]+):", bloque, re.M)
    assert len(escenas) >= 10, f"el barrido de escenas se quedó corto: {escenas}"
    return escenas


def _etiquetas_de_accion(out: dict) -> list[str]:
    """Las etiquetas de los botones, DERIVADAS del DOM que pintó `renderActions`.

    Enumerarlas a mano dejaría fuera al botón siguiente, que es el que va a tener
    el defecto. Cada botón es `<button><span>ETIQUETA</span><span class=sub>…`,
    así que la etiqueta es el texto del PRIMER hijo.
    """
    caja = _node(out["tree"], "action-btns")
    return [
        (b["kids"][0].get("txt") or "").strip()
        for b in caja.get("kids", ())
        if b.get("tag") == "BUTTON" and b.get("kids")
    ]


@pytest.mark.parametrize("escena", _escenas_demo())
def test_en_modo_demo_ningun_boton_manda_una_orden_al_gabinete(tmp_path, escena):
    """CERO peticiones al gabinete desde cualquier escena de demostración.

    Se pulsan TODOS los botones que la escena ofrezca, derivados del DOM. El
    conteo esperado es cero y se dice en voz alta: un test de conjunto vacío que
    no declara su tamaño pasa por vacuidad, y aquí la vacuidad sería el propio
    defecto (una escena que no pinta botones también da cero POST).
    """
    primera = _render(tmp_path, search=f"?demo={escena}", clicks=["frame"])
    etiquetas = _etiquetas_de_accion(primera)

    out = _render(
        tmp_path,
        search=f"?demo={escena}",
        clicks=["frame"] + [f"action:{e}" for e in etiquetas] + ["frame"],
    )
    ordenes = [f for f in out["fetches"] if f["method"] == "POST"]
    assert ordenes == [], (
        f"la escena {escena!r} mandó {len(ordenes)} orden(es) al gabinete: "
        f"{[o['url'] for o in ordenes]}\n"
        "  La pantalla dice DEMO · NO ES ESTADO REAL mientras el botón acciona el edificio."
    )


def test_la_demo_pulsa_botones_de_verdad_y_no_una_lista_vacia(tmp_path):
    """Guarda de no-vacuidad del test de arriba, con su cifra a la vista.

    Sin esto, borrar `renderActions` entero dejaría el test anterior en verde:
    cero botones también producen cero peticiones.
    """
    out = _render(tmp_path, search="?demo=alerta", clicks=["frame"])
    etiquetas = _etiquetas_de_accion(out)
    assert len(etiquetas) >= 5, f"la escena de alerta pinta {len(etiquetas)} botones: {etiquetas}"
    assert "PROBAR ACTUADORES" in etiquetas, etiquetas
    assert "CERRAR ALERTA" in etiquetas, etiquetas


def test_en_modo_demo_los_botones_se_declaran_inertes(tmp_path):
    """Se PINTAN, y se pintan inertes.

    Esconderlos sería mentir en la otra dirección: `?demo=` existe para enseñar
    cómo se ve el panel en estados que no se pueden reproducir a voluntad, y un
    panel sin sus botones no se parece al real. La honestidad es que sigan ahí y
    que digan que no hacen nada.
    """
    out = _render(tmp_path, search="?demo=alerta", clicks=["frame"])
    caja = _node(out["tree"], "action-btns")
    botones = [b for b in caja.get("kids", ()) if b.get("tag") == "BUTTON"]
    assert botones, "sin botones no hay nada que declarar inerte"
    for b in botones:
        assert "inert" in b.get("cls", "").split(), f"botón sin marca de inerte: {_text(b)!r}"
    assert "INERTE EN DEMO" in _txt(out, "action-btns")


def test_en_modo_demo_el_clic_lo_dice_en_vez_de_callarse(tmp_path):
    """Un botón que no hace nada y no explica por qué es una avería aparente.

    El panel ya grita sus rechazos con el NOMBRE de la orden (UX post-incidente
    del 2026-07-31); este camino usa el mismo canal.
    """
    out = _render(tmp_path, search="?demo=alerta", clicks=["frame", "action:PROBAR SIRENA"])
    assert "MODO DEMO" in _txt(out, "pin-msg")
    assert "PROBAR SIRENA" in _txt(out, "action-toast")


def test_el_panel_manda_sus_ordenes_por_UN_SOLO_embudo_y_la_guarda_esta_en_el():
    """Lo que hace estructural a la guarda de demo, en vez de disciplinaria.

    Los tests de arriba pulsan los botones que `renderActions` pinta. Si mañana
    alguien añade un `fetch(..., POST)` en otro sitio —un atajo de teclado, un
    gesto, una acción desde una tarjeta— quedaría fuera de ese barrido y el
    defecto volvería por la puerta de al lado.

    Medido hoy: en las ~2 400 líneas del panel hay **un** POST, y su función
    tiene la guarda la primera. Este test lo exige por conteo, no por revisión.
    """
    html = _INDEX.read_text("utf-8")
    posts = [
        n for n, ln in enumerate(html.splitlines(), 1) if re.search(r"method:\s*['\"]POST['\"]", ln)
    ]
    assert len(posts) == 1, (
        f"el panel tiene {len(posts)} caminos que mandan órdenes (líneas {posts}).\n"
        "  La guarda de `?demo=` vive en `doAction`; un POST fuera de ahí la esquiva.\n"
        "  O se enruta por `doAction`, o este test crece con su razón escrita."
    )
    cuerpo = html[html.index("async function doAction(") : html.index("function renderActions(")]
    assert cuerpo.index("if (DEMO){") < cuerpo.index("if (twoStep"), (
        "la guarda de demo tiene que ir ANTES del armado de dos clics: si no, el "
        "botón se queda armado y el operador cree que la orden salió."
    )


def test_sin_modo_demo_los_mismos_botones_siguen_mandando_su_orden(tmp_path):
    """Guarda anti-prohibir-de-más: la mitad que hace inútil una prohibición.

    Sin esto, `doAction(){ return; }` dejaría verdes todos los tests de arriba y
    el panel del gabinete real se quedaría sin botones que funcionen.
    """
    st = _base()
    st["siren_sounding"] = True
    st["alert_latched"] = True
    con_demo = _etiquetas_de_accion(
        _render(tmp_path, status=st, search="?demo=alerta", clicks=["frame"])
    )
    sin_demo = _etiquetas_de_accion(_render(tmp_path, status=st, clicks=["frame"]))
    assert sin_demo == con_demo, (
        "la demo cambió QUÉ botones se ofrecen; solo puede cambiar si accionan.\n"
        f"  con demo: {con_demo}\n  sin demo: {sin_demo}"
    )

    out = _render(tmp_path, status=st, clicks=["action:PROBAR SIRENA"])
    assert _posts(out, "api/siren-test"), "sin demo, el botón tiene que seguir mandando su orden"
    assert "INERTE EN DEMO" not in _txt(out, "action-btns")


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
    assert "S/D · NO MEDIDO" in _txt(out, "cmp-facts")


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
    assert "RETIRADO EN LA NUBE" in texto
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
