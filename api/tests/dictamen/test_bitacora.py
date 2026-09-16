"""[T-7.22] Los rótulos del papel NO pueden divergir de los de la pantalla.

`dictamen/bitacora.py` es un ESPEJO de `shared/sdk-ts/src/bms.ts`, no una segunda
fuente. Vive en Python porque `api/Dockerfile` no copia `shared/sdk-ts` y el
render necesita los rótulos EN LA NUBE; el registro vivo sigue siendo el de la
consola. Esta suite es lo único que impide que las dos copias se separen.

Aquí se DERIVA el mapa esperado del propio `bms.ts` y se exige igualdad. Escribir
otra vez la tabla en el test habría sido una tercera copia, que es el problema que
se está evitando.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from takab_api.dictamen.bitacora import ROTULOS, SIN_ROTULO, rotulo

_BMS = Path(__file__).resolve().parents[3] / "shared" / "sdk-ts" / "src" / "bms.ts"


def _bloque(fuente: str, marca: str) -> str:
    try:
        return fuente.split(marca)[1].split("\n};")[0]
    except IndexError:  # pragma: no cover - el contrato se movió
        pytest.fail(f"{marca!r} no está en bms.ts: esto no está verde, está ciego")


def _rotulos_de_la_consola() -> dict[str, str]:
    """El mapa `kind → rótulo` tal como lo construye la consola.

    Dos familias, como en `bms.ts`: los verbos del ciclo de vida traen su
    `logLabel` hecho, y los de actuador se componen —etiqueta del canal más el
    estado que ese verbo AFIRMA—, que es justo la distinción por la que
    `gas_closed` y `gas_open` no pueden rotularse igual.
    """
    fuente = _BMS.read_text(encoding="utf-8")
    salida: dict[str, str] = {}

    ciclo = _bloque(fuente, "export const INCIDENT_ACTION_KINDS")
    for kind, cuerpo in re.findall(r"^  (\w+): \{(.*?)^  \},", ciclo, re.M | re.S):
        m = re.search(r"logLabel: '((?:[^'\\]|\\.)*)'", cuerpo)
        assert m is not None, f"`{kind}` no declara `logLabel` en bms.ts"
        salida[kind] = m.group(1).replace("\\'", "'")

    actuadores = _bloque(fuente, "export const ACTUATOR_CHANNELS")
    for canal, cuerpo in re.findall(r"^  (\w+): \{(.*?)^  \},", actuadores, re.M | re.S):
        etiqueta = re.search(r"label: '([^']*)'", cuerpo)
        protege = re.search(r"protecting: \{ state: '([^']*)'", cuerpo)
        reposo = re.search(r"atRest: \{ state: '([^']*)'", cuerpo)
        assert etiqueta and protege and reposo, f"el canal `{canal}` cambió de forma en bms.ts"
        for grupo in ("kinds", "legacyKinds"):
            bloque_kinds = re.search(grupo + r": \{([^}]*)\}", cuerpo)
            if bloque_kinds is None:
                continue
            for kind, activado in re.findall(r"(\w+): (true|false)", bloque_kinds.group(1)):
                estado = protege.group(1) if activado == "true" else reposo.group(1)
                salida[kind] = f"{etiqueta.group(1)} {estado}"
    return salida


def test_el_lector_de_bms_NO_esta_ciego() -> None:
    """Si el parseo dejara de casar, la igualdad de abajo pasaría contra `{}`."""
    consola = _rotulos_de_la_consola()
    assert len(consola) >= 30, f"el parseo de bms.ts solo sacó {len(consola)} rótulos"
    # Dos anclas de cada familia: si una deja de salir, el parseo se movió.
    assert consola["gas_closed"] == "VÁLVULAS DE GAS CERRADAS"
    assert consola["gas_open"] == "VÁLVULAS DE GAS ABIERTAS"
    assert consola["ack"] == "ACUSE DE OPERADOR"


def test_el_papel_y_la_pantalla_rotulan_IGUAL() -> None:
    """Igualdad, no inclusión: sobrar un rótulo es tan malo como faltar.

    Un rótulo de más en Python es un verbo que la consola ya no reconoce y que el
    papel seguiría pintando como si existiera; uno de menos es un `kind` que el
    documento entregado imprime en crudo.
    """
    consola = _rotulos_de_la_consola()
    assert ROTULOS == consola, (
        "el registro del papel divergió del de la consola. Diferencia de claves: "
        f"{sorted(set(ROTULOS) ^ set(consola))} · textos distintos: "
        f"{sorted(k for k in set(ROTULOS) & set(consola) if ROTULOS[k] != consola[k])}"
    )


def test_los_kinds_LEGADOS_siguen_teniendo_rotulo() -> None:
    """`incident_actions` es append-only y exenta de poda (regla de oro 11).

    Una fila escrita hace dos años tiene que seguir leyéndose. Si alguien
    «limpia» los legados de `bms.ts`, un dictamen histórico regenerado volvería
    al identificador crudo — y un dictamen es un documento histórico.
    """
    for viejo in ("gas_valve_close", "elevator_recall", "door_release"):
        assert viejo in ROTULOS, f"`{viejo}` perdió su rótulo: las filas antiguas se vuelven crudas"


def test_un_kind_DESCONOCIDO_se_declara_en_vez_de_salir_en_crudo() -> None:
    """Y sale con su identificador: el dato de la tabla no se oculta.

    El precedente rechaza con razón un registro Python que pretenda ser COMPLETO
    —su completitud descansaría en una convención—. Aquí no se pretende: lo que
    no se sabe rotular se dice que no se sabe.
    """
    texto, conocido = rotulo("verbo_que_nadie_ha_escrito_aun")
    assert conocido is False
    assert "verbo_que_nadie_ha_escrito_aun" in texto
    assert SIN_ROTULO in texto


def test_un_kind_CONOCIDO_sale_sin_el_aviso() -> None:
    """El lado negativo: el aviso en un verbo que sí se sabe rotular sería ruido
    que enseña a ignorar el aviso de verdad."""
    texto, conocido = rotulo("gas_closed")
    assert conocido is True
    assert texto == "VÁLVULAS DE GAS CERRADAS"
    assert SIN_ROTULO not in texto
