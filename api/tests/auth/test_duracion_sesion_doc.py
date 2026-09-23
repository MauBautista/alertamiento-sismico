"""La tabla de duración de sesión de `RBAC-TAKAB.md §5.4` es la de la matriz (T-8.05 · D-38).

La verdad ejecutable es ``matrix.SESSION_MAX_AGE_S``; el documento es donde la lee un humano
—un cliente que pregunta cuánto dura la sesión de su brigadista, o quien revoque `D-38`—. Dos
declaraciones del mismo hecho divergen si nadie las cruza (es la historia de la matriz RBAC
de la web, `T-5.28`), así que este test las cruza fila a fila, en las dos direcciones.
"""

from __future__ import annotations

import re
from pathlib import Path

from takab_api.auth.matrix import SESSION_MAX_AGE_S

_RBAC = Path(__file__).resolve().parents[3] / "takab-docs" / "RBAC-TAKAB.md"

#: Una fila de la tabla: `| `rol` | 24 h | … |` o `| `rol` | 30 d | … |`.
_FILA = re.compile(r"^\| `(?P<rol>[a-z_]+)` \| (?P<n>\d+) (?P<u>h|d) \|", re.M)

_SEGUNDOS = {"h": 3600, "d": 86400}


def _tabla_del_documento() -> dict[str, int]:
    texto = _RBAC.read_text(encoding="utf-8")
    inicio = texto.index("### 5.4 Duración de sesión por rol")
    fin = texto.index("\n## ", inicio)
    return {
        m.group("rol"): int(m.group("n")) * _SEGUNDOS[m.group("u")]
        for m in _FILA.finditer(texto[inicio:fin])
    }


def test_la_tabla_del_documento_no_esta_vacia() -> None:
    """Guarda de no-vacuidad: si el formato cambia, `{} == {}` pasaría en verde."""
    assert len(_tabla_del_documento()) == 10, (
        "RBAC-TAKAB.md §5.4 dejó de leerse: el test esperaba las 10 filas de roles "
        "(`| `rol` | N h|d | …`). Si cambió el formato, cambia la expresión, no la cuenta."
    )


def test_la_duracion_de_cada_rol_en_el_documento_es_la_de_la_matriz() -> None:
    documento = _tabla_del_documento()
    assert documento == dict(SESSION_MAX_AGE_S), (
        "La duración de sesión que declara RBAC-TAKAB.md §5.4 no es la que impone la API "
        "(matrix.SESSION_MAX_AGE_S).\n"
        f"  documento: {sorted(documento.items())}\n"
        f"  matriz:    {sorted(SESSION_MAX_AGE_S.items())}\n"
        "  Cambia los dos en el mismo commit y, si un tope sube por encima del refresh de su "
        "cliente, también `infra/terraform/modules/identity` (D-38)."
    )
