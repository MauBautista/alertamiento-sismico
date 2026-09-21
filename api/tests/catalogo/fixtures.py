"""La respuesta GRABADA de USGS, vestida con el sobre GeoJSON que da el FDSN.

`api/tests/incident/fixtures/usgs-consulta-2026-09-14.json` es lo que el servicio
contestó el 2026-09-14 **destilado**: id, magnitud, estado, epicentro, profundidad
y hora en milisegundos, que es lo que `T-7.12` necesitaba comparar contra el seed.
Las CIFRAS de estos tests salen de ahí y de ningún otro sitio.

Lo que ese archivo no guarda es el SOBRE —`{"type":"FeatureCollection","features":
[{"properties":{…},"geometry":{"coordinates":[lon,lat,prof]}}]}`—, y el sobre es
justo lo que el cliente tiene que saber abrir. Aquí se vuelve a montar a partir de
los campos grabados, en un solo sitio y con el mapeo escrito: si mañana alguien
graba la respuesta cruda entera, esta función desaparece y los tests no cambian.

**No sale ni un byte a la red**: el JSON se sirve por `httpx.MockTransport`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

#: La consulta archivada la comparte `api/tests/incident/test_catalogo_con_procedencia.py`,
#: que ata el seed a ella. Se lee de allí a propósito: dos copias del mismo archivo
#: acabarían divergiendo y una de las dos dejaría de ser «lo que contestó la fuente».
GRABADA = (
    Path(__file__).resolve().parents[1] / "incident" / "fixtures" / "usgs-consulta-2026-09-14.json"
)


def archivada() -> dict:
    return json.loads(GRABADA.read_text(encoding="utf-8"))


def consulta_de(catalog_key: str) -> dict:
    """Una de las consultas archivadas, por la clave de catálogo que la motivó."""
    for c in archivada()["consultas"]:
        if c["catalog_key"] == catalog_key:
            return c
    raise KeyError(f"la consulta archivada no trae {catalog_key!r}")


def geojson(features: list[dict]) -> dict:
    """El sobre FDSN GeoJSON alrededor de los eventos grabados."""
    return {
        "type": "FeatureCollection",
        "metadata": {"count": len(features), "api": "1.14.1"},
        "features": [
            {
                "type": "Feature",
                "id": f["id"],
                "properties": {
                    "mag": f["mag"],
                    "place": f["place"],
                    "time": f["time_ms"],
                    "updated": f["time_ms"],
                    "status": f["status"],
                    "magType": f.get("magType"),
                    "ids": f",{f['id']},",
                },
                # ⚠️ El orden de GeoJSON es [lon, lat, profundidad]. Invertirlo pone
                # el epicentro en el otro hemisferio y el criterio de identidad lo
                # rechazaría por radio — un fallo que se leería como «sin correlación».
                "geometry": {
                    "type": "Point",
                    "coordinates": [f["lon"], f["lat"], f["depth_km"]],
                },
            }
            for f in features
        ],
    }


def geojson_de(catalog_key: str) -> dict:
    return geojson(consulta_de(catalog_key)["features"])


# --------------------------------------------------------------------------
# Las respuestas CRUDAS, byte a byte como las dio el servicio
# --------------------------------------------------------------------------
#: Lo que el archivo de arriba no puede dar. Son la respuesta del FDSN tal cual,
#: **con la forma exacta de la consulta de este worker** (círculo de 1 200 km,
#: ventana de ±363 s, `orderby=time`, `limit=200`) y con la URL que las produjo
#: dentro, en `metadata.url`: la propia respuesta trae su procedencia, así que
#: cualquiera puede repetir la pregunta y comparar.
#:
#: Sirven para tres cosas que el destilado no puede:
#:
#: 1. **Un estado NO revisado de verdad.** El destilado sólo trae `reviewed`, de
#:    modo que `preliminar` —el estado que dice «PUEDE CAMBIAR»— no se producía
#:    por el camino real en ningún punto de la suite. El evento de Valdez es
#:    `automatic` en la fuente, y lo sigue siendo días después: USGS revisa
#:    primero lo que le importa a alguien, y un M3.5 en Alaska no está en esa
#:    lista. Por eso el sismo de esta prueba no es mexicano: lo que hacía falta
#:    era un evento que la fuente NO haya revisado, y los sismos mexicanos de
#:    magnitud publicable los revisa en horas.
#: 2. **El sobre de verdad.** `geojson()` reconstruye el sobre a partir de los
#:    campos grabados; esto es el sobre que manda el servicio, con sus 26
#:    propiedades por evento y sus campos que no miramos.
#: 3. **El peso.** `catalog_usgs_max_bytes` se justifica con bytes por evento, y
#:    con estos ficheros esa cifra se re-deriva del árbol con `wc -c` en vez de
#:    ser una cifra de un comentario.
_CRUDAS = Path(__file__).resolve().parent / "fixtures"

#: 1 evento, `automatic`, M3.5 a 22.2 km del punto que se consultó.
CRUDA_AUTOMATICA = _CRUDAS / "usgs-automatico-2026-09-20.json"
#: 14 eventos: la hora siguiente al M8.2 de Tehuantepec (2017-09-08), pedida
#: desde la Ciudad de México con la forma de esta consulta.
CRUDA_TEHUANTEPEC = _CRUDAS / "usgs-tehuantepec-2026-09-20.json"


def cruda(ruta: Path) -> dict:
    """Una respuesta archivada, tal cual. Sin re-envolver nada."""
    return json.loads(ruta.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# La base
# --------------------------------------------------------------------------
#: El DSN de la base MIGRADA contra la que corre esta suite. Vive aquí y no en
#: cada módulo porque hay dos que la necesitan —la pasada y el censo de
#: desenlaces— y dos cadenas de conexión acaban apuntando a bases distintas,
#: que es la forma más silenciosa de que una guarda deje de medir lo que cree.
_DEFECTO = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"


def dsn() -> str:
    """`DATABASE_URL` en la forma que entiende psycopg (sin el dialecto de SQLAlchemy)."""
    return os.environ.get("DATABASE_URL", _DEFECTO).replace(
        "postgresql+psycopg://", "postgresql://"
    )
