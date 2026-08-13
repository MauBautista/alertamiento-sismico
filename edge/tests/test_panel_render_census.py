"""[T-2.85.a] EL CENSO: un campo que `status()` sirve y el panel nunca pinta.

`run_actuator_test()` promete por escrito —`local_api/__init__.py`— que *«el
resultado por relé aflora en `status()` para que el panel lo pinte»*. Viajaba en
el JSON y el panel solo leía `actuation_test.active`: los `held`/`pulsed`/
`readback_ok` aparecían ÚNICAMENTE en los datos de demo del propio HTML, que es
la peor forma de no existir —parece que está pintado y no lo está—. Igual
`calibration.source`: el panel dice `SIN CALIBRAR` cuando falta, y cuando SÍ hay
calibración nunca dice de dónde vino.

Duele porque `PROBAR ACTUADORES` hace **lectura de retorno sobre el gas y los
ascensores** —ejerce físicamente el equipamiento del edificio— y no enseñaba el
resultado. Es la única prueba que el operador puede hacer solo.

**Esto vigila la CLASE de defecto, no los dos casos.** El censo no lee una lista
de campos escrita a mano: MUTA cada hoja del `status()` real, vuelve a
renderizar y compara el DOM. Si el panel pinta exactamente lo mismo con el campo
cambiado, ese campo NO TIENE CAMINO DE RENDER. Las excepciones se comparan por
IGUALDAD: quien arregle una tiene que borrar su línea, y quien añada un campo
mudo tiene que escribir su razón.

Tres guardas para que el censo no pueda dar un verde falso (lección de T-2.131:
que el arnés confirme por sí mismo que montó el escenario):

  · **Determinismo** — el mismo status renderizado dos veces da el MISMO DOM.
    Sin reloj congelado el segundero de la cabecera se leería como "cambió".
  · **Control positivo** — mutar `site_name`, que sí se pinta, TIENE que verse.
    Si no, el comparador está roto y el censo entero sería un verde falso.
  · **La mutación se aplicó de verdad** — se comprueba en Python antes de
    interpretar "no cambió el DOM" como "no hay camino de render".
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests.test_local_api_panel import _NOW, _base, _cold

_NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(
    _NODE is None,
    reason="node no está en el PATH: el render del panel no se puede ejecutar",
)

_INDEX = Path(__file__).resolve().parents[1] / "takab_edge" / "local_api" / "index.html"
_HARNESS = Path(__file__).with_name("panel_harness.js")

#: Sentinela de la mutación. Improbable en cualquier dato real del gabinete.
_ZZQ = "ZZQ"


# --------------------------------------------------------------------- rutas


def _hojas(obj: Any, prefijo: str = "") -> list[str]:
    """Rutas de HOJA de un `status()`: `a.b`, `a[].b` dentro de una lista.

    Una lista es hoja ADEMÁS de recorrerse: "esta lista se vació" y "el campo X
    de su primer elemento cambió" son dos caminos de render distintos, y el
    panel puede tener uno y no el otro (le pasaba a `relays_status.missing`).
    """
    if isinstance(obj, dict):
        rutas: list[str] = []
        for clave, valor in obj.items():
            hijo = f"{prefijo}.{clave}" if prefijo else clave
            rutas.append(hijo) if not isinstance(valor, (dict, list)) else None
            rutas += _hojas(valor, hijo)
        return rutas
    if isinstance(obj, list):
        rutas = [prefijo]  # la lista misma (vaciarla es un cambio observable)
        if obj and isinstance(obj[0], (dict, list)):
            rutas += _hojas(obj[0], f"{prefijo}[]")
        return rutas
    return [prefijo] if prefijo else []


def _traer(obj: Any, ruta: str) -> Any:
    cur = obj
    for paso in ruta.split("."):
        if paso.endswith("[]"):
            cur = cur[paso[:-2]][0]
        else:
            cur = cur[paso]
    return cur


def _poner(obj: Any, ruta: str, valor: Any) -> None:
    pasos = ruta.split(".")
    cur = obj
    for paso in pasos[:-1]:
        cur = cur[paso[:-2]][0] if paso.endswith("[]") else cur[paso]
    ultimo = pasos[-1]
    if ultimo.endswith("[]"):
        cur[ultimo[:-2]][0] = valor
    else:
        cur[ultimo] = valor


def _mutaciones(valor: Any) -> list[Any]:
    """DOS valores distintos del mismo campo, no uno. Una sola no basta.

    Medido: con una sola mutación el censo daba 13 falsos mudos.

    · Las cadenas se envuelven por AMBOS lados (`ZZQ…ZZQ`): el panel recorta
      marcas de tiempo con `slice(11,19)`, y una mutación pegada al final caía
      justo fuera del trozo que se pinta.
    · Los números se prueban por arriba Y a cero: casi todo umbral del panel es
      una comparación, y sumar siempre en la misma dirección deja la mitad de
      las ramas sin tocar (`edad > stale_after_s`).
    · La cadena vacía y el `null` cubren las ramas por FALSEDAD (`x || 'S/D'`),
      que son las que deciden entre pintar el dato y pintar la ausencia.
    """
    if isinstance(valor, bool):
        return [not valor]
    if isinstance(valor, (int, float)):
        return [float(valor) + 4321.5, 0.0 if valor else 1.0]
    if isinstance(valor, str):
        return [f"{_ZZQ}{valor}{_ZZQ}", ""]
    if isinstance(valor, list):
        return [[] if valor else [_ZZQ], [_ZZQ, _ZZQ]]
    if valor is None:
        return [_ZZQ, 0]
    return [_ZZQ, None]


# ----------------------------------------------------------------- el arnés


def _lote(tmp_path: Path, casos: list[dict]) -> dict[str, dict]:
    """Renderiza N casos en UN proceso node y devuelve `{id: instantánea}`."""
    cfg = {
        "base": {
            "catalog": {"available": False, "events": [], "references": []},
            "clicks": ["frame"],
            "now": _NOW,
        },
        "cases": casos,
    }
    ruta = tmp_path / "casos.json"
    ruta.write_text(json.dumps(cfg), "utf-8")
    proc = subprocess.run(  # noqa: S603 — binario de shutil.which, entrada propia
        [_NODE, str(_HARNESS), str(_INDEX), str(ruta)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, f"arnés cayó: {proc.stderr[:2000]}"
    salida = json.loads(proc.stdout)
    devueltos = {c["id"] for c in salida["cases"]}
    pedidos = {c["id"] for c in casos}
    # El arnés confirma POR SÍ MISMO que renderizó lo que se le pidió, en vez de
    # que el test lo infiera del orden de la lista (lección de T-2.131).
    assert devueltos == pedidos, f"el arnés no devolvió los casos pedidos: {pedidos ^ devueltos}"
    return {c["id"]: c for c in salida["cases"]}


def _firma(caso: dict) -> str:
    """Lo que el panel MUESTRA: árbol, texto de los canvas y errores de render.

    Los errores cuentan como parte de la firma a propósito: si mutar un campo
    hace REVENTAR el render, ese campo se está leyendo — tiene camino, y además
    uno frágil.
    """
    assert not caso.get("fatal"), caso.get("fatal")
    return json.dumps(
        {"tree": caso["tree"], "canvas": caso["canvasText"], "errors": caso["errors"]},
        sort_keys=True,
        ensure_ascii=False,
    )


# --------------------------------------------------- contrato con status()


def _status_real(supervisor) -> dict:
    """El `status()` del gabinete real CON una prueba de actuación ya corrida.

    Sin ejecutarla, `actuation_test.results` es `None` y sus campos —los que
    destapó T-2.85.a— no existirían en el censo. Se corre la de VERDAD (pin
    factory mock), no una enlatada: la forma del resultado sale del productor.
    """
    supervisor.local_api.run_actuator_test()
    return json.loads(json.dumps(supervisor.local_api.status()))


def _claves(obj: Any, prefijo: str = "") -> set[str]:
    if not isinstance(obj, dict):
        return set()
    out: set[str] = set()
    for clave, valor in obj.items():
        ruta = f"{prefijo}.{clave}" if prefijo else clave
        out.add(ruta)
        out |= _claves(valor, ruta)
    return out


def test_el_fixture_del_censo_es_el_status_real_hasta_el_ultimo_anidado(supervisor):
    """`_base()` es el sujeto del censo: si se separa de `status()`, el censo miente.

    El contrato de `test_local_api_panel.py` compara el primer nivel y `cloud`.
    Aquí se compara RECURSIVAMENTE, descendiendo solo donde ambos lados traen un
    diccionario — un gabinete recién arrancado sirve `health: null` y `signal:
    null` legítimamente, y exigir su interior sería exigir datos que no existen.

    Un diccionario VACÍO en el gabinete real corta el descenso por la misma
    razón: `signal.channels` y `shake_history.by_channel` van indexados POR
    CANAL, y sus claves son datos (`ENZ`, `EHZ`…), no esquema. Un mapa vacío
    dice "todavía no llegó nada", no "el contrato encogió".
    """
    real = _status_real(supervisor)
    fixture = _base()

    def cruzar(a: dict, b: dict, prefijo: str = "") -> list[str]:
        if not a or not b:
            return []
        problemas = []
        for clave in sorted(set(a) | set(b)):
            ruta = f"{prefijo}.{clave}" if prefijo else clave
            if clave not in b:
                problemas.append(f"{ruta}: status() la sirve y el fixture del censo no la conoce")
            elif clave not in a:
                problemas.append(f"{ruta}: el fixture la trae y status() ya no la sirve")
            elif isinstance(a[clave], dict) and isinstance(b[clave], dict):
                problemas += cruzar(a[clave], b[clave], ruta)
        return problemas

    desalineadas = cruzar(real, fixture)
    assert not desalineadas, "el fixture del censo se separó de status():\n" + "\n".join(
        desalineadas
    )
    # No-vacuidad: si `results` viniera vacío el censo no cubriría T-2.85.a.
    assert real["actuation_test"]["results"], "la prueba de actuación real no dejó resultado"
    assert _claves(real["actuation_test"]), "sección actuation_test vacía"


# ----------------------------------------------------- guardas del censo


def test_el_censo_es_determinista_y_sabe_ver_un_cambio(tmp_path):
    """Sin estas dos, un "no cambió nada" no significa nada.

    Determinismo: el reloj congelado del arnés es lo único que impide que el
    `hh:mm:ss` de la cabecera se lea como un cambio en CADA campo.
    Control positivo: `site_name` se pinta en la cabecera; si mutarlo no se ve,
    el comparador está roto y todo el censo sería un verde falso.
    """
    con_sitio = _base()
    con_sitio["site_name"] = f"{con_sitio['site_name']} {_ZZQ}"
    casos = _lote(
        tmp_path,
        [
            {"id": "base-1", "status": _base()},
            {"id": "base-2", "status": _base()},
            {"id": "control", "status": con_sitio},
        ],
    )
    assert _firma(casos["base-1"]) == _firma(casos["base-2"]), (
        "el render del panel NO es determinista con el mismo status: el censo no "
        "puede distinguir un campo mudo de un segundero"
    )
    assert _firma(casos["control"]) != _firma(casos["base-1"]), (
        "mutar `site_name` —que la cabecera pinta— no cambió el DOM: el "
        "comparador del censo está roto"
    )


# ------------------------------------------------------------- el censo


# ------------------------------------------------------------- escenas
#
# UNA SOLA ESCENA NO BASTA, y creérselo es cómo se cuela un falso rojo: casi
# todo lo que el panel pinta es CONDICIONAL. `cloud.queued` sólo se rotula sin
# enlace; `drill.*` sólo con simulacro vivo; `actuation_test.results` sólo
# después de una prueba. Censado únicamente en nominal, medio panel parecería
# mudo y la lista de excepciones se llenaría de mentiras.
#
# Cada escena enciende una rama y dice cuál. Se derivan de `_base()`/`_cold()`
# —el fixture atado a `status()` real— y no de literales sueltos.


def _escena_alerta() -> dict:
    st = _base()
    st.update(
        {
            "sasmex_active": True,
            "siren_sounding": True,
            "siren_reason": "sasmex",
            "alert_latched": True,
            "last_tier": "evacuate_or_hold",
        }
    )
    st["audio"]["sounding"] = True
    # [T-2.29] Punto 0 fijado: sin él la brújula cae en la media rodante y
    # `rose_zero` entero parecería no tener camino de render.
    st["rose_zero"] = {"at": _NOW, "channels": {"ENZ": 3.77e6, "ENN": 1.2e6, "ENE": -8.4e5}}
    return st


def _escena_reles_parciales() -> dict:
    """`partial`: faltan estados de relés que la config declara instalados.

    Es la ÚNICA causa en la que el panel nombra la lista `missing`.
    """
    st = _base()
    st["relays_status"] = {
        "reason": "partial",
        "installed": ["gas_valve", "siren", "strobe"],
        "missing": ["strobe"],
    }
    return st


def _escena_prueba() -> dict:
    """La prueba local de actuación YA TERMINADA, con su resultado por relé.

    `active: False` a propósito: mientras sostiene, la tarjeta dice «ejercitando»
    y el resultado todavía no existe. La rama `active` la cubre el banner cian,
    que se enciende mutando el `false` de la escena nominal.
    """
    st = _base()
    st["actuation_test"] = {
        "active": False,
        "finished_at": _NOW,
        "age_s": 3.0,
        "results": {
            "ok": False,
            "reason": "readback falló en: elevator, door_retainer",
            "relays": {
                # Los CUATRO desenlaces que la tarjeta distingue, uno por canal:
                # sostenido OK · pulso OK · no confirmó · sin relé detrás. Y
                # `strobe` queda declarado en la config sin resultado ⇒ NO SE PROBÓ.
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
    st["relays_status"] = {
        "reason": "ok",
        "installed": ["door_retainer", "elevator", "gas_valve", "siren", "strobe"],
        "missing": [],
    }
    return st


def _escena_sin_nube() -> dict:
    """Sin enlace y con respaldo EN MARCHA (`phase`), que es su rama propia."""
    st = _base()
    st["cloud"] = {"online": False, "mqtt_rtt_ms": None, "queued": 47, "admin_state": "active"}
    st["evidence"] = {
        **st["evidence"],
        "pending": 3,
        "items": [{"event_id": "8f2c41ab", "age_s": 900.0}],
        "oldest_pending_age_s": 900.0,
        "phase": "uploading",
        "durable": False,
        "last_result": None,
        "last_result_age_s": None,
    }
    return st


def _escena_retirado() -> dict:
    """Baja administrativa + evidencia ATASCADA e ILEGIBLE (con enlace vivo).

    Va con enlace: sin él, `evidenceView` corta en la rama «en espera» y ni
    `stale_after_s` ni `phase` llegan a leerse nunca.
    """
    st = _base()
    st["cloud"] = {**st["cloud"], "admin_state": "retired"}
    st["evidence"] = {
        **st["evidence"],
        "pending": 2,
        "items": [{"event_id": "8f2c41ab", "age_s": 9000.0}],
        # El productor sirve NOMBRES DE FICHERO (`local_api/__init__.py`), no
        # objetos: el panel los recorta con `slice(0,8)` y les añade `.json`.
        "unreadable": 1,
        "unreadable_items": ["b1d09e77-3c11-4f2a"],
        "oldest_pending_age_s": 9000.0,
        "stale_after_s": 3600.0,
        "discarded_no_data_total": 2,
        "failed_total": 3,
        "extract_failed_total": 1,
    }
    return st


def _escena_simulacro() -> dict:
    st = _base()
    st["drill"] = {
        "active": True,
        "drill_id": "DRILL-2026-0804-01",
        "elapsed_s": 252.0,
        "total_s": 480.0,
    }
    st["test_mode"] = {"active": True, "remaining_s": 87.0}
    return st


def _escena_gpio_caido() -> dict:
    st = _base()
    st["relays"] = []
    st["relays_status"] = {
        "reason": "gpio_unreachable",
        "installed": ["gas_valve", "siren"],
        "missing": ["gas_valve", "siren"],
    }
    return st


def _escena_lora_caido() -> dict:
    st = _base()
    st["lora"] = {
        **st["lora"],
        "secondaries": [
            {
                **st["lora"]["secondaries"][0],
                "link": "offline",
                "acked": False,
                "alarm_active": True,
            }
        ],
    }
    st["audio"]["profile"] = {
        "applied": {"siren": "clasico"},
        "rejected": {"test": "sasmex_oficial"},
        "test_tone": False,
    }
    return st


def _escena_sin_calibrar() -> dict:
    st = _base()
    st["calibration"] = {
        "calibrated": False,
        "source": None,
        "vel_sensitivity_ms_per_count": None,
        "accel_sensitivity_ms2_per_count": None,
    }
    st["rose_zero"] = None
    return st


#: Las escenas del censo. La primera que contiene una ruta es su "casa"; el
#: resto se usan para re-probar las que salieron mudas.
ESCENAS: dict[str, Any] = {
    "nominal": _base,
    "prueba_actuadores": _escena_prueba,
    "alerta": _escena_alerta,
    "sin_nube": _escena_sin_nube,
    "retirado": _escena_retirado,
    "simulacro": _escena_simulacro,
    "gpio_caido": _escena_gpio_caido,
    "reles_parciales": _escena_reles_parciales,
    "lora_caido": _escena_lora_caido,
    "sin_calibrar": _escena_sin_calibrar,
    "frio": _cold,
}


def _existe(obj: Any, ruta: str) -> bool:
    try:
        _traer(obj, ruta)
    except (KeyError, IndexError, TypeError):
        return False
    return True


# ------------------------------------------------------------- el censo


#: CAMPOS QUE `status()` SIRVE Y EL PANEL NO PINTA EN NINGUNA ESCENA — con su
#: razón, uno por uno.
#:
#: Se compara por IGUALDAD, nunca por contención. Arreglar uno obliga a borrar
#: su línea; añadir un campo mudo obliga a escribir por qué. Una excepción que
#: puede crecer sola no es una excepción, es un agujero.
SIN_CAMINO_DE_RENDER: dict[str, str] = {
    "audio.profile.applied.siren": (
        "El panel rotula lo que pide acción —tonos RECHAZADOS y la ausencia de "
        "tono de prueba—, no el mapa completo slot→id de catálogo, que es "
        "diagnóstico de instalación y no cambia nada de lo que hace el operador."
    ),
    "audio.sounding": (
        "Redundante con `siren_sounding`, que es el hecho ELÉCTRICO y es el que "
        "se pinta (con su `siren_reason`). Dos rótulos del mismo altavoz serían "
        "dos verdades que pueden discrepar."
    ),
    "captured_at": (
        "Campo de compatibilidad con el panel anterior: es la hora del último "
        "diagnóstico de salud, y esa sección se rotula por EDAD (`health.age_s`). "
        "Sigue en `status()` porque quitarlo es un cambio de contrato."
    ),
    "health.captured_at": (
        "Mismo motivo: la tarjeta de salud dice `DIAGNÓSTICO DE HACE …`, no una "
        "hora. Restar el reloj del navegador contra el del Pi ya costó una "
        "corrección en esta pantalla."
    ),
    "health.mqtt_rtt_ms": (
        "Se pinta el RTT de `cloud.mqtt_rtt_ms`, que es el vivo de la sesión "
        "MQTT. El del último latido de salud es el MISMO número con retraso: "
        "pintar los dos invita a comparar un dato consigo mismo."
    ),
    "lora.enabled": (
        "`_lora_section` devuelve `None` con el módulo deshabilitado, y entonces "
        "el panel ya dice `SIN RADIO LORA · MÓDULO DESHABILITADO`. Con la "
        "sección presente el flag no puede ser falso: pintarlo sería pintar una "
        "tautología."
    ),
    "lora.secondaries[].age_s": (
        "El panel pinta el VEREDICTO derivado (`link`: online / ENLACE PERDIDO / "
        "SIN CONTACTO AÚN), que es lo que ese age_s significa una vez comparado "
        "con el latido configurado. El número crudo no añade ninguna acción."
    ),
    "lora.secondaries[].id": (
        "Dirección del nodo en la radio. El operador identifica un gabinete "
        "secundario por su nombre y su zona («AZOTEA-NORTE · Torre B»), que es "
        "lo que está rotulado en el equipo."
    ),
    "now": (
        "Reloj del gabinete. La cabecera estampa el del NAVEGADOR a propósito "
        "(es el que el operador puede contrastar con su reloj) y toda edad de "
        "dato viaja ya derivada por el gabinete."
    ),
    "rose_zero.at": (
        "Cuándo se fijó el PUNTO 0. La brújula declara SI está fijado "
        "(`PUNTO 0 FIJADO` / `MEDIA RODANTE · SIN CALIBRAR`), que es la "
        "distinción que cambia cómo se lee el punto; la fecha del acto de "
        "calibrar es de instalación."
    ),
    "shake_history.by_channel.ENZ.hourly[].hour_start": (
        "Las barras horarias se pintan en orden y sin eje de tiempo: son una "
        "silueta de las últimas 24 h, no una serie que alguien vaya a leer hora "
        "a hora frente al gabinete."
    ),
    "shake_history.by_channel.ENZ.hourly[].pgv_cms_max": (
        "La silueta horaria se pinta en PGA, que es la unidad de los umbrales "
        "de disparo de este mismo gabinete."
    ),
    "shake_history.by_channel.ENZ.pgv_cms_max_24h": (
        "Igual: el máximo de 24 h se rotula en PGA. Dos unidades para el mismo "
        "pico es una que se lee mal."
    ),
    "shake_history.events_by_tier.normal": (
        "`normal` es la AUSENCIA de evento. Contarlo en la fila de eventos "
        "sería contar los segundos en los que no pasó nada."
    ),
    "shake_history.since": (
        "El agregado se rotula `DESDE EL ARRANQUE` y su antigüedad sale de "
        "`uptime_s`, que es el mismo hecho dicho en la unidad que el operador "
        "usa («lleva 4 h encendido»)."
    ),
    "signal.channels.EHZ.pga_g": (
        "EHZ es el canal de VELOCIDAD (geófono): su carril rotula `pgv_cms`. "
        "Los tres ENx son los acelerómetros y rotulan `pga_g`. Pintar la "
        "magnitud que no corresponde al sensor sería inventarla."
    ),
    "signal.channels.ENE.pgv_cms": (
        "Carril de aceleración: rotula `pga_g`. Ver `signal.channels.EHZ.pga_g`."
    ),
    "signal.channels.ENN.pgv_cms": (
        "Carril de aceleración: rotula `pga_g`. Ver `signal.channels.EHZ.pga_g`."
    ),
    "signal.channels.EHZ.received_at": (
        "La frescura del canal ya está resuelta en `age_s`, que es lo que decide "
        "entre pintar el valor y borrarlo con `SIN SEÑAL DEL SENSOR`."
    ),
    "signal.channels.EHZ.window_start": (
        "Inicio de la ventana de features. Mismo motivo que `received_at`."
    ),
    "signal.channels.ENE.received_at": ("Ver `signal.channels.EHZ.received_at`."),
    "signal.channels.ENE.window_start": ("Ver `signal.channels.EHZ.window_start`."),
    "signal.channels.ENN.received_at": ("Ver `signal.channels.EHZ.received_at`."),
    "signal.channels.ENN.window_start": ("Ver `signal.channels.EHZ.window_start`."),
    "signal.channels.ENZ.received_at": ("Ver `signal.channels.EHZ.received_at`."),
    "signal.channels.ENZ.window_start": ("Ver `signal.channels.EHZ.window_start`."),
    "signal.last_received_at": (
        "La sección de señal se rotula por edad de cada canal, no por un reloj "
        "común: un canal mudo con los otros tres vivos tiene que verse mudo."
    ),
}

#: LÍMITE DECLARADO DEL CENSO, que NO es lo mismo que "no se pinta".
#:
#: Estos campos SÍ tienen camino de render, pero sólo sobre el búfer de forma de
#: onda que el arnés no alimenta (sirve `api/waveform` vacío): sin muestras no
#: hay nada que escalar ni que re-centrar, así que mutarlos no mueve un pixel.
#: Se declaran aparte a propósito — meterlos en `SIN_CAMINO_DE_RENDER` diría una
#: falsedad sobre el panel.
SOLO_SOBRE_MUESTRAS: dict[str, str] = {
    "calibration.vel_sensitivity_ms_per_count": (
        "Escala el trazo de EHZ (velocidad) en `sens().v`/`toPhys`, sobre las "
        "muestras crudas del búfer."
    ),
    "rose_zero.channels.ENE": ("Punto 0 del eje E-O: se resta a las muestras crudas."),
    "rose_zero.channels.ENN": ("Punto 0 del eje N-S: se resta a las muestras crudas."),
    "rose_zero.channels.ENZ": ("Punto 0 del eje Z: se resta a las muestras crudas."),
}


def test_todo_campo_de_status_tiene_camino_de_render(tmp_path):
    """Mutar cualquier hoja de `status()` tiene que verse en ALGUNA escena.

    Este es el test que T-2.85.a pedía: caza la CLASE de defecto (un campo que
    viaja en el JSON y nunca llega a la pantalla), no los dos casos que la
    destaparon.
    """
    escenas = {nombre: hacer() for nombre, hacer in ESCENAS.items()}
    rutas: dict[str, str] = {}  # ruta → escena "casa" (la primera que la trae)
    for nombre, st in escenas.items():
        for ruta in _hojas(st):
            rutas.setdefault(ruta, nombre)
    assert len(rutas) > 140, f"el censo solo halló {len(rutas)} rutas: el recorrido está roto"
    # No-vacuidad dirigida: sin estas cuatro, el censo pasaría sin cubrir T-2.85.a.
    for obligada in (
        "actuation_test.results.relays.siren.readback_ok",
        "actuation_test.results.relays.gas_valve.readback_ok",
        "actuation_test.results.ok",
        "calibration.source",
    ):
        assert obligada in rutas, f"el censo no llegó a {obligada}"

    def probar(pares: list[tuple[str, str]]) -> dict[tuple[str, str], bool]:
        """`(escena, ruta) → ¿cambió el DOM al mutar?`, en un solo proceso node."""
        casos = [{"id": f"@{n}", "status": escenas[n]} for n in sorted({p[0] for p in pares})]
        ids: dict[tuple[str, str], list[str]] = {}
        for escena, ruta in pares:
            for i, despues in enumerate(_mutaciones(_traer(escenas[escena], ruta))):
                antes = _traer(escenas[escena], ruta)
                if despues == antes:
                    continue
                mutado = json.loads(json.dumps(escenas[escena]))
                _poner(mutado, ruta, despues)
                # La mutación se comprueba, no se supone: un `_poner` que no
                # escribiera nada se leería como "no hay camino de render".
                assert _traer(mutado, ruta) == despues, (
                    f"la mutación {i} de {ruta} en {escena} no se aplicó"
                )
                caso_id = f"{escena}|{ruta}|{i}"
                ids.setdefault((escena, ruta), []).append(caso_id)
                casos.append({"id": caso_id, "status": mutado})
        for par in pares:
            assert ids.get(par), f"no se pudo mutar {par[1]} en {par[0]}"
        salida = _lote(tmp_path, casos)
        return {
            par: any(_firma(salida[i]) != _firma(salida[f"@{par[0]}"]) for i in ids[par])
            for par in pares
        }

    visto = probar([(casa, ruta) for ruta, casa in rutas.items()])
    sospechosas = [r for (_, r), cambio in visto.items() if not cambio]

    # Segunda vuelta: una ruta muda en SU escena puede tener camino en otra.
    repesca = [
        (nombre, ruta)
        for ruta in sospechosas
        for nombre, st in escenas.items()
        if nombre != rutas[ruta] and _existe(st, ruta)
    ]
    if repesca:
        for (_, ruta), cambio in probar(repesca).items():
            if cambio and ruta in sospechosas:
                sospechosas.remove(ruta)

    declarados = {**SIN_CAMINO_DE_RENDER, **SOLO_SOBRE_MUESTRAS}
    assert len(declarados) == len(SIN_CAMINO_DE_RENDER) + len(SOLO_SOBRE_MUESTRAS), (
        "una ruta declarada en las DOS listas: decide cuál es"
    )
    mudos = sorted(set(sospechosas))
    detalle = "\n".join(f"  · {r}" for r in mudos if r not in declarados)
    assert mudos == sorted(declarados), (
        "CAMPOS QUE `status()` SIRVE Y EL PANEL NO PINTA EN NINGUNA ESCENA. "
        "Mutarlos no cambia ni un pixel del DOM: viajan en el JSON y nunca "
        "llegan a la pantalla. O les das camino de render, o los declaras en "
        f"`SIN_CAMINO_DE_RENDER` con su razón escrita.\n{detalle}"
    )
