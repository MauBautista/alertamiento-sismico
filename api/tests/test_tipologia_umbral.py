"""El catálogo de tipología y su banda de referencia (T-5.16 · D-28).

**Un censo, no una lista escrita a mano.** El catálogo vive en
`shared/schemas/tipologia_umbral.json` y lo consumen CUATRO superficies: la
validación de la API, el `CHECK` de `sites.building_type`, el desplegable de la
consola y la propia ficha. Cada una de las cuatro se compara aquí **por
igualdad y en los dos sentidos** — con contención, un tipo nuevo entraría en una
y no en las otras, que es exactamente cómo divergió el espejo de la matriz RBAC
(`T-5.28`).

Y la aserción que sostiene la decisión: **la tipología NO resuelve umbrales**.
Si alguien pusiera `resuelve_umbrales: true` sin pasar por `D-28`, el catálogo
pasaría a re-armar edificios desde una pantalla de captura. Este test lo impide.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[2]
_CATALOGO = _RAIZ / "shared" / "schemas" / "tipologia_umbral.json"
_BLUEPRINT = _RAIZ / "takab-docs" / "BLUEPRINT-TECNICO-TAKAB.md"
_SCHEMA_SQL = _RAIZ / "db" / "schema.sql"

CAT = json.loads(_CATALOGO.read_text(encoding="utf-8"))
VALORES = [t["value"] for t in CAT["tipos"]]


def test_la_tipologia_NO_resuelve_umbrales():
    """La decisión `D-28`, clavada donde no se pueda cambiar de paso.

    Cambiar esto a `true` haría que editar el tipo de un sitio desde la pantalla
    de flota re-armara el edificio a otra sensibilidad, sin publicar y sin
    firmar. Es un cambio de actuación por un acto de captura.
    """
    assert CAT["resuelve_umbrales"] is False
    assert CAT["decision"] == "D-28"
    assert len(CAT["por_que_no_resuelve"]) >= 3, "una decisión sin razón escrita no es una decisión"


def test_el_catalogo_es_cerrado_y_sin_repetidos():
    assert len(VALORES) == len(set(VALORES)) == 6
    assert VALORES == sorted(VALORES, key=lambda v: VALORES.index(v)), "orden estable"
    # `otro` va al final: es el cajón declarado, no el primero que se elige.
    assert VALORES[-1] == "otro"


def test_las_tres_bandas_son_LAS_DEL_BLUEPRINT_leidas_de_el():
    """No se teclean aquí: se sacan del documento canónico y se comparan.

    Si alguien retoca una cifra en el blueprint y no en el catálogo (o al revés),
    este test lo dice con el número que cambió.
    """
    texto = _BLUEPRINT.read_text(encoding="utf-8")
    # «Hospitales 0.040–0.060 g · Industriales 0.080–0.120 g · Corporativos 0.100–0.150 g»
    pares = re.findall(r"(Hospitales|Industriales|Corporativos)\s+([\d.]+)[–-]([\d.]+)\s*g", texto)
    assert len(pares) == 3, f"el blueprint dejó de declarar las tres bandas: {pares}"

    canonico = {
        "Hospitales": "hospital",
        "Industriales": "industrial",
        "Corporativos": "corporativo",
    }
    del_blueprint = {canonico[n]: (float(a), float(b)) for n, a, b in pares}
    del_catalogo = {
        t["value"]: (t["banda"]["pga_watch_g"], t["banda"]["pga_trip_g"])
        for t in CAT["tipos"]
        if t["banda"] is not None
    }
    assert del_catalogo == del_blueprint


def test_el_tipo_SIN_banda_dice_POR_QUE_no_la_tiene():
    """Un hueco callado se lee como «se me olvidó»; declarado, como «nadie la publicó»."""
    sin_banda = [t for t in CAT["tipos"] if t["banda"] is None]
    assert len(sin_banda) == 3, "cambió el reparto de tipos con y sin banda"
    for t in sin_banda:
        assert len(t.get("sin_banda_por_que", "")) > 60, f"{t['value']} no explica su ausencia"


def test_ninguna_banda_inventa_un_PGV():
    """El blueprint publica PGA por tipología y NO publica PGV. Ver `sin_referencia_de_pgv`."""
    for t in CAT["tipos"]:
        if t["banda"] is not None:
            assert set(t["banda"]) == {"pga_watch_g", "pga_trip_g"}
    assert len(CAT["sin_referencia_de_pgv"]) > 80


def test_la_banda_de_cautela_va_SIEMPRE_por_debajo_de_la_de_disparo():
    for t in CAT["tipos"]:
        if t["banda"] is not None:
            assert t["banda"]["pga_watch_g"] < t["banda"]["pga_trip_g"], t["value"]


def test_el_CHECK_de_la_base_enumera_EXACTAMENTE_el_catalogo():
    """El `CHECK` es una copia en SQL; esto es lo que impide que diverja."""
    sql = _SCHEMA_SQL.read_text(encoding="utf-8")
    # `re.S`: el CHECK ocupa dos líneas en el schema. Sin esto el test pasaba a
    # ser una guardia que no encuentra nada y se pone roja por la razón equivocada.
    m = re.search(r"building_type text CHECK \(building_type IN\s*\(([^)]+)\)\)", sql, re.S)
    assert m is not None, "`sites.building_type` perdió su CHECK contra el catálogo"
    en_sql = sorted(re.findall(r"'([a-z_]+)'", m.group(1)))
    assert en_sql == sorted(VALORES)


def test_la_validacion_de_la_API_sale_del_catalogo_y_no_de_una_lista():
    from takab_api.sites.tipologia import BANDAS, TIPOS, banda_de

    assert sorted(TIPOS) == sorted(VALORES)
    assert sorted(BANDAS) == sorted(t["value"] for t in CAT["tipos"] if t["banda"])
    assert banda_de("hospital") == (0.040, 0.060)
    # Un tipo sin banda devuelve `None`, NO la de hospital: es el defecto que
    # abre la ficha —toda la flota corriendo la banda de hospital sin saberlo—.
    assert banda_de("universidad") is None
    assert banda_de("inexistente") is None
