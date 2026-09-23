"""Lo que el formulario de daños de la app OFRECE es lo que la API ACEPTA (T-8.12).

`mobile/src/features/damage/categories.ts` dice de sí mismo que «los keys/severidades
espejan el schema del backend», y no lo hacían: la app ofrecía cuatro severidades
(`low`, `medium`, `high`, `critical`) y `schemas.mobile.DAMAGE_SEVERITIES` aceptaba tres.
Un brigadista que marcaba un daño como «Alta» recibía un 422 y el reporte no entraba
— justo el reporte que alimenta el dictamen. Lo encontró el carril del PDF al
derivar los rótulos del papel de sus fuentes (2026-09-23).

Un comentario que dice «espejo» no es un espejo: este test lee las dos listas y las
compara, en los dos sentidos.
"""

from __future__ import annotations

import re
from pathlib import Path

from takab_api.schemas.mobile import DAMAGE_CATEGORY_KEYS, DAMAGE_SEVERITIES

_CATEGORIAS_TS = (
    Path(__file__).resolve().parents[3] / "mobile" / "src" / "features" / "damage" / "categories.ts"
)


def _fuente() -> str:
    return _CATEGORIAS_TS.read_text(encoding="utf-8")


def _severidades_de_la_app() -> set[str]:
    m = re.search(r"export const SEVERITIES = \[([^\]]*)\]", _fuente())
    assert m, "categories.ts ya no declara `SEVERITIES = [...]`: el test se quedó ciego"
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))


def _categorias_de_la_app() -> set[str]:
    m = re.search(r"export const DAMAGE_CATEGORIES = \[(.*?)\] as const", _fuente(), re.S)
    assert m, "categories.ts ya no declara `DAMAGE_CATEGORIES`: el test se quedó ciego"
    return set(re.findall(r'key: "([a-z_]+)"', m.group(1)))


def test_las_listas_no_estan_vacias() -> None:
    """Guarda anti-vacuidad: `set() == set()` pasaría en verde."""
    assert len(_severidades_de_la_app()) >= 3
    assert len(_categorias_de_la_app()) >= 5


def test_toda_severidad_que_ofrece_la_app_la_acepta_la_api() -> None:
    assert _severidades_de_la_app() == set(DAMAGE_SEVERITIES), (
        "La app ofrece severidades que la API no acepta (o al revés): un reporte de daños "
        f"con la que falta recibe 422. App: {sorted(_severidades_de_la_app())} · "
        f"API: {sorted(DAMAGE_SEVERITIES)}"
    )


def test_toda_categoria_que_ofrece_la_app_la_acepta_la_api() -> None:
    assert _categorias_de_la_app() == set(DAMAGE_CATEGORY_KEYS), (
        f"App: {sorted(_categorias_de_la_app())} · API: {sorted(DAMAGE_CATEGORY_KEYS)}"
    )
