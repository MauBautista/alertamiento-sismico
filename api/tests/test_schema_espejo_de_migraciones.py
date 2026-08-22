"""`db/schema.sql` y las migraciones son DOS fuentes de verdad del mismo DDL.

`CLAUDE.md §5` dice que `db/schema.sql` es *«la fuente de verdad del DDL»*, y
`api/migrations/versions/` es lo que de verdad se ejecuta contra una base. Mientras
las dos existan hay que vigilar que no divergan — y **nada lo vigilaba**.

**El defecto que lo destapó, medido el 2026-08-22.** La migración `0045` añadió
`last_checked_at` a `gateway_catalog_state`; el espejo la escribió dentro de
`gateway_config_state`, la tabla de al lado. Resultado: la columna de `config_state`
era huérfana (cero lectores en todo el repo) y `gateway_catalog_state` no la tenía,
así que **una base creada desde `db/schema.sql` reventaba** en el `UPDATE` de
`routers/commands.py::_CATALOG_TOUCH_SQL`. Nadie lo vio porque la suite arranca por
`alembic upgrade head` (`conftest.py`), que nunca lee el espejo.

**Por qué se comprueba en UNA sola dirección.** Migración ⇒ espejo: toda columna que
una migración añade tiene que estar en el `CREATE TABLE` correspondiente. La
dirección contraria no se puede exigir: `db/schema.sql` es el esquema **final**
—`0001` lo aplica entero—, así que la inmensa mayoría de sus columnas no tiene ningún
`ALTER` que las nombre. Exigirla daría ruido, no señal.

**Esto no sustituye a comparar dos bases de verdad**, que es lo único que cerraría el
caso entero (tipos, defaults, constraints, índices). Cubre la familia de fallo que ya
se pagó: una columna que se añade en un sitio y se declara en otro, o en ninguno.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ESQUEMA = REPO_ROOT / "db/schema.sql"
MIGRACIONES = REPO_ROOT / "api/migrations/versions"

#: `ALTER TABLE x … ;` — el cuerpo puede traer varias cláusulas y saltos de línea.
_ALTER = re.compile(r"ALTER\s+TABLE\s+(?:ONLY\s+)?(\w+)([^;]*);", re.I)
#: `ADD COLUMN [IF NOT EXISTS] nombre …`
_ADD = re.compile(r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", re.I)
#: `CREATE TABLE [IF NOT EXISTS] nombre ( … );`
_CREATE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\n\s*\)\s*;", re.I | re.S
)

#: Palabras que abren una CLÁUSULA de tabla, no una columna.
_NO_ES_COLUMNA = {
    "primary",
    "foreign",
    "unique",
    "check",
    "constraint",
    "exclude",
    "like",
    "inherits",
    "partition",
}


def _sin_comentarios(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _columnas_declaradas() -> dict[str, set[str]]:
    """`tabla → columnas` según el espejo `db/schema.sql`."""
    texto = _sin_comentarios(ESQUEMA.read_text(encoding="utf-8"))
    tablas: dict[str, set[str]] = {}
    for tabla, cuerpo in _CREATE.findall(texto):
        columnas: set[str] = set()
        for linea in cuerpo.splitlines():
            token = linea.strip().lstrip("(").split(" ")[0].strip(",").lower()
            if token and token not in _NO_ES_COLUMNA and re.fullmatch(r"\w+", token):
                columnas.add(token)
        # Una tabla puede aparecer más de una vez (p. ej. re-declaración en otra
        # sección): se acumula en vez de sobrescribir, o el censo perdería columnas.
        tablas.setdefault(tabla.lower(), set()).update(columnas)
    return tablas


def _columnas_anadidas() -> dict[str, set[str]]:
    """`tabla → columnas` que las migraciones añaden con `ALTER TABLE … ADD COLUMN`."""
    anadidas: dict[str, set[str]] = {}
    for fichero in sorted(MIGRACIONES.glob("*.py")):
        texto = _sin_comentarios(fichero.read_text(encoding="utf-8"))
        for tabla, cuerpo in _ALTER.findall(texto):
            for columna in _ADD.findall(cuerpo):
                anadidas.setdefault(tabla.lower(), set()).add(columna.lower())
    return anadidas


def test_el_censo_no_esta_vacio() -> None:
    """Un censo que no encuentra nada pasa todos los demás tests sin mirar nada.

    Es la trampa que este repo ya pagó en otros censos: el candado sale verde
    porque su parser dejó de reconocer la forma del fichero, no porque no haya
    defectos. Las cifras son cotas inferiores holgadas, no el valor exacto: subirlas
    a igualdad obligaría a tocar este test cada vez que nace una migración.
    """
    declaradas = _columnas_declaradas()
    anadidas = _columnas_anadidas()
    # 49 `CREATE TABLE` el 2026-08-22; la cota es holgada hacia abajo a propósito.
    assert len(declaradas) >= 40, (
        f"el espejo solo dio {len(declaradas)} tablas: el parser se rompió"
    )
    assert len(anadidas) > 10, (
        f"solo se reconocieron ALTER sobre {len(anadidas)} tablas: o el parser se rompió, "
        "o las migraciones cambiaron de forma"
    )
    assert "gateway_catalog_state" in anadidas, (
        "no se reconoció el ALTER de la migración 0045, que es el caso que originó "
        "este candado: si ése no se ve, el candado no protege de nada"
    )


def test_toda_columna_que_una_migracion_anade_esta_en_el_espejo() -> None:
    """El defecto de `last_checked_at`, fijado para que no vuelva."""
    declaradas = _columnas_declaradas()
    faltan: list[str] = []
    tablas_ausentes: list[str] = []
    for tabla, columnas in sorted(_columnas_anadidas().items()):
        if tabla not in declaradas:
            tablas_ausentes.append(tabla)
            continue
        for columna in sorted(columnas - declaradas[tabla]):
            faltan.append(f"{tabla}.{columna}")

    assert not tablas_ausentes, (
        f"migraciones que alteran tablas que `db/schema.sql` no declara: {tablas_ausentes}. "
        "El espejo es la fuente de verdad del DDL (CLAUDE.md §5): una tabla que solo existe "
        "en las migraciones deja el esquema consolidado incapaz de crear la base."
    )
    assert not faltan, (
        f"columnas que una migración añade y el espejo NO declara: {faltan}.\n"
        "Una base creada desde `db/schema.sql` en vez de por migraciones no las tendría, y el "
        "código que las usa reventaría en producción. Ojo al modo de fallo que ya se pagó: la "
        "columna puede estar en el fichero pero DENTRO DE OTRA TABLA — mirar que el `CREATE "
        "TABLE` sea el correcto, no solo que el nombre aparezca."
    )
