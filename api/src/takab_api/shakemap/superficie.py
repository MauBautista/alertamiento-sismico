"""[T-9.51 · D-44] La superficie ESTIMADA de la sacudida: la ley, corregida cerca de lo medido.

Módulo puro (numpy, sin base ni red ni reloj). Determinista y sin IA (regla de oro 1):
es un mapa descriptivo que **jamás** gatea una actuación.

QUÉ AFIRMA, Y QUÉ NO
────────────────────
`D-44` enmienda a `D-08`: además de los puntos medidos se dibuja una superficie, pero
**rotulada como estimación**. Con tres o cuatro estaciones la superficie es sobre todo
modelo, y eso lo dice el rótulo —«ESTIMADO a partir de N sensores (M calibrados)»— y
la máscara de zona AJUSTADA, no el color.

EL MÉTODO (`METODO`)
────────────────────
1. **La base es la ley** de la capa 2 (`ATTEN-LAW v1`, `geo.pga_law_g`), evaluada en el
   centro de cada celda con la distancia hipocentral al epicentro citado.
2. **El residuo de cada sensor calibrado**: ``r = log10(medido / ley en su sitio)``, el
   mismo de la capa 3 de `calculo.py`.
3. **Se reparte con peso gaussiano** de escala ``L`` (15 km por defecto) y se ENCOGE
   hacia cero::

       r(x) = Σ wᵢ·rᵢ / (Σ wᵢ + λ)      wᵢ = exp(−dᵢ² / 2L²)

   Con ``λ`` > 0 la estimación nunca llega del todo a lo medido (el punto medido se
   pinta encima), y lejos de toda estación ``Σ w → 0`` y manda la ley: la superficie
   no inventa sacudida donde nadie midió.
4. ``PGA(x) = ley(x) · 10^r(x)``.

**AJUSTADA** = celda a menos de ``2L`` de un sensor calibrado con medida; el resto es
**MODELADA**, y quien pinte las distingue.

LO QUE NO ENTRA
───────────────
* **Un sensor sin calibrar no ajusta.** Cuenta en ``N`` (midió) y no en ``M``. Su pico
  puede venir en cuentas mal escaladas, y un residuo falso tiñe kilómetros.
* **Un sensor retirado ni llega aquí**: lo filtra quien llama (`status = 'active'`).
* **Sin ancla no hay superficie**, y el motivo se dice (`MOTIVOS`): sin epicentro con
  magnitud no hay ley; sin una sola medida no hay mapa de la sacudida (la regla de
  `calculo.py`); sin un sensor calibrado sería puro modelo presentado como ajuste.

LA MALLA
────────
Cubre los sensores calibrados con medida (los que la anclan) más un margen de ``3L``,
con un mínimo de 30 km a cada lado. Celdas CUADRADAS en km (la longitud se escala con
el coseno de la latitud) y como mucho ``celdas_max`` (96) por lado. **Fila 0 = norte**,
columna 0 = oeste: el orden de un PNG, para que el ráster no tenga que voltear nada.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from takab_api.geo import EARTH_RADIUS_KM
from takab_api.shakemap.calculo import LEY
from takab_api.shakemap.gmice import CITA as CITA_MMI

METODO = "residuos-gaussianos-v1"
VERSION_JSON = 1

#: Escala del peso gaussiano, en km.
ESCALA_KM = 15.0
#: Encogimiento hacia la ley (λ): el peso que «vota» por residuo cero.
ENCOGIMIENTO = 0.25
#: Margen alrededor de las estaciones, en múltiplos de L.
MARGEN_EN_L = 3.0
#: Semiancho mínimo de la malla, en km.
SEMIANCHO_MIN_KM = 30.0
CELDAS_MAX = 96
#: Techo físico de la estimación (g): nada de valores absurdos por un residuo extremo.
PGA_MAX_G = 5.0

MOTIVO_SIN_EPICENTRO = "sin_epicentro"
MOTIVO_SIN_MEDIDAS = "sin_medidas"
MOTIVO_SIN_CALIBRADOS = "sin_calibrados"

MOTIVOS: dict[str, str] = {
    MOTIVO_SIN_EPICENTRO: "no hay epicentro con magnitud: sin él no hay ley que corregir",
    MOTIVO_SIN_MEDIDAS: "ningún inmueble instrumentado midió en la ventana",
    MOTIVO_SIN_CALIBRADOS: (
        "ningún sensor con medida tiene calibración declarada: sería puro modelo"
    ),
}

_KM_POR_GRADO = math.pi * EARTH_RADIUS_KM / 180.0


@dataclass(frozen=True)
class EpicentroLey:
    """Lo que la ley necesita del epicentro. Sin magnitud no hay ley."""

    lat: float
    lon: float
    depth_km: float | None
    magnitud: float | None


@dataclass(frozen=True)
class Estacion:
    """Un inmueble ACTIVO: dónde está, qué midió y si su sensor está calibrado."""

    lat: float
    lon: float
    pga_g: float | None
    calibrado: bool


@dataclass(frozen=True)
class Superficie:
    """La malla estimada. ``pga_g[i][j]`` y ``ajustada[i][j]``: fila 0 = norte."""

    oeste: float
    sur: float
    este: float
    norte: float
    ancho: int
    alto: int
    pga_g: tuple[tuple[float, ...], ...]
    ajustada: tuple[tuple[bool, ...], ...]
    n_sensores: int
    n_calibrados: int
    escala_km: float
    ley: str = LEY
    metodo: str = METODO

    def centro(self, i: int, j: int) -> tuple[float, float]:
        """(lat, lon) del centro de la celda ``(fila, columna)``."""
        lat = self.norte - (i + 0.5) * (self.norte - self.sur) / self.alto
        lon = self.oeste + (j + 0.5) * (self.este - self.oeste) / self.ancho
        return lat, lon

    def to_json(self) -> dict:
        """Compacto: PGA en micro-g enteros y la máscara como cadena de 0/1, por filas."""
        return {
            "version": VERSION_JSON,
            "bbox": [self.oeste, self.sur, self.este, self.norte],
            "ancho": self.ancho,
            "alto": self.alto,
            "pga_ug": [round(v * 1e6) for fila in self.pga_g for v in fila],
            "ajustada": "".join("1" if a else "0" for fila in self.ajustada for a in fila),
            "n_sensores": self.n_sensores,
            "n_calibrados": self.n_calibrados,
            "escala_km": self.escala_km,
            "ley": self.ley,
            "metodo": self.metodo,
            "cita_mmi": CITA_MMI,
        }

    @classmethod
    def from_json(cls, d: dict) -> Superficie:
        ancho, alto = int(d["ancho"]), int(d["alto"])
        pga = [v / 1e6 for v in d["pga_ug"]]
        mascara = [c == "1" for c in d["ajustada"]]
        oeste, sur, este, norte = d["bbox"]
        return cls(
            oeste=oeste,
            sur=sur,
            este=este,
            norte=norte,
            ancho=ancho,
            alto=alto,
            pga_g=tuple(tuple(pga[i * ancho : (i + 1) * ancho]) for i in range(alto)),
            ajustada=tuple(tuple(mascara[i * ancho : (i + 1) * ancho]) for i in range(alto)),
            n_sensores=int(d["n_sensores"]),
            n_calibrados=int(d["n_calibrados"]),
            escala_km=float(d["escala_km"]),
            ley=d["ley"],
            metodo=d["metodo"],
        )


def _haversine(lat1, lon1, lat2, lon2):  # noqa: ANN001, ANN202 - arrays de numpy
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def _ley(epi: EpicentroLey, lat, lon):  # noqa: ANN001, ANN202 - arrays de numpy
    """`geo.pga_law_g(M, geo.hypo_km(R, prof))`, vectorizada (mismo piso de 1 km)."""
    epi_km = _haversine(epi.lat, epi.lon, lat, lon)
    hypo = epi_km if epi.depth_km is None else np.hypot(epi_km, epi.depth_km)
    return 10 ** (0.5 * epi.magnitud - 2.8) / np.maximum(hypo, 1.0)


def estima(
    estaciones: Sequence[Estacion],
    epicentro: EpicentroLey | None,
    *,
    escala_km: float = ESCALA_KM,
    encogimiento: float = ENCOGIMIENTO,
    celdas_max: int = CELDAS_MAX,
) -> tuple[Superficie | None, str | None]:
    """La superficie, o ``(None, motivo)`` si no hay con qué anclarla."""
    if epicentro is None or epicentro.magnitud is None:
        return None, MOTIVO_SIN_EPICENTRO
    medidas = [e for e in estaciones if e.pga_g is not None and e.pga_g > 0]
    if not medidas:
        return None, MOTIVO_SIN_MEDIDAS
    ajustan = [e for e in medidas if e.calibrado]
    if not ajustan:
        return None, MOTIVO_SIN_CALIBRADOS

    # La malla: los sensores que la ANCLAN más el margen, en km locales. Un sensor sin
    # calibrar se pinta como punto, pero no extiende la superficie: allí sólo habría ley.
    lat0 = sum(e.lat for e in ajustan) / len(ajustan)
    km_lon = _KM_POR_GRADO * math.cos(math.radians(lat0))
    xs = [e.lon * km_lon for e in ajustan]
    ys = [e.lat * _KM_POR_GRADO for e in ajustan]
    margen = MARGEN_EN_L * escala_km
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    semi_x = max((max(xs) - min(xs)) / 2 + margen, SEMIANCHO_MIN_KM)
    semi_y = max((max(ys) - min(ys)) / 2 + margen, SEMIANCHO_MIN_KM)
    celda = 2 * max(semi_x, semi_y) / celdas_max
    ancho = max(1, min(celdas_max, math.ceil(2 * semi_x / celda)))
    alto = max(1, min(celdas_max, math.ceil(2 * semi_y / celda)))
    oeste, este = (cx - ancho * celda / 2) / km_lon, (cx + ancho * celda / 2) / km_lon
    sur, norte = (cy - alto * celda / 2) / _KM_POR_GRADO, (cy + alto * celda / 2) / _KM_POR_GRADO

    filas = norte - (np.arange(alto) + 0.5) * (norte - sur) / alto
    columnas = oeste + (np.arange(ancho) + 0.5) * (este - oeste) / ancho
    lat, lon = np.meshgrid(filas, columnas, indexing="ij")

    ley = _ley(epicentro, lat, lon)
    num = np.zeros_like(ley)
    den = np.zeros_like(ley)
    cerca = np.full(ley.shape, np.inf)
    for e in ajustan:
        residuo = math.log10(e.pga_g / float(_ley(epicentro, e.lat, e.lon)))
        d = _haversine(e.lat, e.lon, lat, lon)
        w = np.exp(-(d**2) / (2 * escala_km**2))
        num += w * residuo
        den += w
        cerca = np.minimum(cerca, d)
    pga = np.clip(ley * 10 ** (num / (den + encogimiento)), 0.0, PGA_MAX_G)
    ajustada = cerca < 2 * escala_km

    return (
        Superficie(
            oeste=float(oeste),
            sur=float(sur),
            este=float(este),
            norte=float(norte),
            ancho=ancho,
            alto=alto,
            pga_g=tuple(tuple(float(v) for v in fila) for fila in pga),
            ajustada=tuple(tuple(bool(v) for v in fila) for fila in ajustada),
            n_sensores=len(medidas),
            n_calibrados=len(ajustan),
            escala_km=escala_km,
        ),
        None,
    )
