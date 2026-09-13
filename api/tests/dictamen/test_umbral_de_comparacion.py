"""[T-7.35] La banda de sacudida dice contra QUÉ números se comparó, y de quién son.

EL DEFECTO, medido el 2026-09-13 sobre el sistema real. El papel imprimía

    SACUDIDA FUERTE (supera el umbral de actuación del inmueble)

mientras `build_forensics` llamaba a `felt_band(pga, pgv)` **sin el tercer
argumento**, o sea clasificando con `DEFAULT_THRESHOLDS` (0.040/0.060 g, la banda
de fábrica). El umbral del inmueble no entraba en la cuenta.

Y no es teórico: el `rule_set` vigente del cliente de la demostración declara
`pga_trip_g = 0.1` y `pga_watch_g = 0.07`, y **el mapa del SOC sí los lee**
(`queries/telemetry.py:247-250`, con el comentario de que «el color del mapa y la
decisión de disparo tienen que contar la misma historia»). Un pico de 0.08 g salía
`watch` en la consola y `trip` —«SACUDIDA FUERTE»— en el dictamen FIRMADO del
mismo incidente. Dos documentos del mismo sismo diciendo lo contrario.

QUÉ SE ARREGLA, y qué no:

* La banda se clasifica con los umbrales del inmueble **vigentes en la apertura
  del incidente**, no con los de hoy: un dictamen es un documento histórico y
  describirlo con la configuración de hoy es el mismo defecto que esta auditoría
  encontró en la calibración. `rule_sets` guarda versión y `created_at`, así que
  no hace falta migración.
* El rótulo deja de atribuir el umbral a nadie, y **una línea nueva declara los
  números y su origen**. Si no consta un `rule_set` con umbrales anterior al
  incidente, se dice: «banda de referencia», no se finge.
"""

from __future__ import annotations

from takab_api.dictamen.model import FELT_LABELS, umbral_line
from takab_api.felt import (
    DEFAULT_THRESHOLDS,
    ORIGEN_INMUEBLE,
    ORIGEN_REFERENCIA,
    Thresholds,
    UmbralComparacion,
    felt_band,
)

#: Los del cliente de la demostración, leídos de su `rule_set` vigente (v19).
DEL_INMUEBLE = Thresholds(pga_watch_g=0.07, pga_trip_g=0.10, pgv_watch_cms=4.0, pgv_trip_cms=7.0)


def test_el_umbral_del_inmueble_CAMBIA_la_banda() -> None:
    """Sin esto, el arreglo no arregla nada: si las dos bandas coincidieran
    siempre, el defecto sería cosmético. Con 0.08 g no coinciden."""
    assert felt_band(0.08, None) == "trip"
    assert felt_band(0.08, None, DEL_INMUEBLE) == "watch"


def test_el_rotulo_ya_no_atribuye_el_umbral_a_nadie() -> None:
    """La mentira estaba en el paréntesis, no en la banda.

    «supera el umbral de actuación del inmueble» afirmaba DOS cosas que el
    documento no comprobaba: de quién era el umbral y que superarlo acciona algo
    (desde T-2.32 una detección instrumental sola NO acciona relés).
    """
    for clave, texto in FELT_LABELS.items():
        assert "del inmueble" not in texto, f"{clave} sigue atribuyendo el umbral: {texto!r}"
        assert "actuación" not in texto, f"{clave} sigue prometiendo actuación: {texto!r}"
    # Y la banda se sigue diciendo: quitar la mentira no es quedarse mudo.
    assert "FUERTE" in FELT_LABELS["trip"]
    assert "LEVE" in FELT_LABELS["normal"]


def test_la_linea_del_umbral_DICE_los_numeros_y_de_donde_salen() -> None:
    u = UmbralComparacion(thresholds=DEL_INMUEBLE, origen=ORIGEN_INMUEBLE, rule_set_version=19)
    linea = umbral_line(u)
    assert "0.100" in linea and "0.070" in linea, linea
    assert "7.0" in linea and "4.0" in linea, linea
    assert "v19" in linea, linea
    assert "inmueble" in linea.lower(), linea


def test_sin_umbral_del_inmueble_lo_DECLARA_en_vez_de_fingir() -> None:
    """El caso honesto: no consta configuración anterior al incidente."""
    linea = umbral_line(UmbralComparacion(thresholds=DEFAULT_THRESHOLDS, origen=ORIGEN_REFERENCIA))
    assert "referencia" in linea.lower(), linea
    assert "0.060" in linea and "0.040" in linea, linea
    assert "v" not in linea.split("·")[-1].lower() or "versión" not in linea.lower()


def test_los_dos_origenes_se_distinguen_a_simple_vista() -> None:
    """Si las dos líneas se leyeran igual, la distinción no serviría de nada."""
    a = umbral_line(UmbralComparacion(DEL_INMUEBLE, ORIGEN_INMUEBLE, 19))
    b = umbral_line(UmbralComparacion(DEFAULT_THRESHOLDS, ORIGEN_REFERENCIA))
    assert a != b
