#!/usr/bin/env bash
# [T-9.54 · D-45] Reconstruye la cartografía que empaqueta el repo, desde sus fuentes.
#
# No corre en CI: descarga ~240 MB y tarda minutos. Lo que CI comprueba es la huella de
# lo comiteado (tools/geodatos/verifica.py). Este guion es la receta, para que cualquier
# capa se pueda rehacer y auditar: cada fuente se descarga y se compara con el sha256 del
# manifiesto ANTES de tocarla, y si una fuente cambió, se para.
#
# Herramienta: mapshaper (licencia MPL-2.0) por npx. Es de construcción y no entra al repo.
#
# Uso:  tools/geodatos/construye.sh [DIRECTORIO_DE_TRABAJO]
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
TRABAJO="${1:-$(mktemp -d)}"
MANIFIESTO="$RAIZ/shared/geodatos/MANIFEST.json"
MAPSHAPER=(npx -y mapshaper@0.6.121)
mkdir -p "$TRABAJO"
cd "$TRABAJO"

fuente() { # capa → url y sha256 de su fuente, del manifiesto
  python3 -c "import json,sys;c=json.load(open('$MANIFIESTO'))['capas']['$1']['fuente'];print(c['url']);print(c['sha256'])"
}

descarga() { # capa, fichero destino
  local url sha
  { read -r url; read -r sha; } < <(fuente "$1")
  [ -f "$2" ] || curl -sSL --fail --max-time 900 -o "$2" "$url"
  echo "$sha  $2" | sha256sum -c --quiet || {
    echo "✗ la fuente de '$1' ya no es la del manifiesto: revisa licencia y contenido antes de actualizar" >&2
    exit 1
  }
}

# --- Zonificación geotécnica de la CDMX (Atlas de Riesgos, SPCGIR 2019, CC BY 4.0) -----
# Cada AGEB lleva una descripción; se traduce a lomas / transición / lago y se disuelve.
descarga ntc_cdmx sismico.csv
python3 - <<'PY'
import csv, json
csv.field_size_limit(10**9)
def zona(desc):
    d = desc.lower()
    if "lagos" in d or "lacustres muy blandos" in d:
        return "lago"
    if "contacto" in d:
        return "transicion"
    if "altas de la cuenca" in d:
        return "lomas"
    raise SystemExit(f"descripción sin zona: {desc!r}")
feats = [
    {"type": "Feature", "properties": {"zona": zona(r["descripcio"])},
     "geometry": json.loads(r["geo_shape"])}
    for r in csv.DictReader(open("sismico.csv", encoding="utf-8", errors="replace"))
]
json.dump({"type": "FeatureCollection", "features": feats}, open("ageb_zona.geojson", "w"))
PY
"${MAPSHAPER[@]}" ageb_zona.geojson -dissolve zona -simplify 8% keep-shapes -clean \
  -o format=geojson precision=0.00001 ntc_cdmx.geojson

# --- Edafología del INEGI 1:250 000 serie II (2024) -------------------------------------
# El shapefile viene en la cónica conforme de Lambert del INEGI (ITRF2008) y SIN .prj.
descarga edafologia edafologia.zip
unzip -q -o edafologia.zip
cp 794551131916/conjunto_de_datos/*cont_nac.shp eda.shp
cp 794551131916/conjunto_de_datos/*cont_nac.shx eda.shx
cp 794551131916/conjunto_de_datos/*cont_nac.dbf eda.dbf
NODE_OPTIONS=--max-old-space-size=7000 "${MAPSHAPER[@]}" eda.shp \
  -proj from='+proj=lcc +lat_1=17.5 +lat_2=29.5 +lat_0=12 +lon_0=-102 +x_0=2500000 +y_0=0 +ellps=GRS80 +towgs84=0,0,0 +units=m +no_defs' wgs84 \
  -filter 'GRUPO1 != "PE"' -simplify 0.85% keep-shapes -dissolve GRUPO1 copy-fields=N_G1 \
  -clean -filter-slivers min-area=4km2 -o format=geojson precision=0.001 edafologia.geojson

# --- Límites estatales de Natural Earth 1:10m (dominio público) --------------------------
descarga estados ne_admin1.geojson
python3 - <<'PY'
import json
d = json.load(open("ne_admin1.geojson"))
feats = []
for f in d["features"]:
    p = f["properties"]
    if p.get("adm0_a3") != "MEX" or not p.get("name"):
        continue
    nombre = "Ciudad de México" if p["name"] == "Distrito Federal" else p["name"]
    feats.append({"type": "Feature", "properties": {"nombre": nombre, "clave": p.get("iso_3166_2")},
                  "geometry": f["geometry"]})
json.dump({"type": "FeatureCollection", "features": feats}, open("estados_mex_raw.geojson", "w"))
PY
"${MAPSHAPER[@]}" estados_mex_raw.geojson -simplify 25% keep-shapes \
  -o format=geojson precision=0.0001 estados_mex.geojson

cp ntc_cdmx.geojson "$RAIZ/web/public/geodatos/ntc_cdmx.geojson"
cp ntc_cdmx.geojson "$RAIZ/api/src/takab_api/geodatos/ntc_cdmx.geojson"
cp edafologia.geojson "$RAIZ/web/public/geodatos/edafologia.geojson"
cp estados_mex.geojson "$RAIZ/api/src/takab_api/geodatos/estados_mex.geojson"
echo "✓ capas reconstruidas en el repo. Si sus huellas cambiaron, actualiza el manifiesto y revisa el diff."
python3 "$RAIZ/tools/geodatos/verifica.py" "$RAIZ" || true
