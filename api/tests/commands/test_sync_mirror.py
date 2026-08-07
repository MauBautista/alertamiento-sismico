"""B3 · El espejo de publicación no puede desincronizarse del original.

El documento firmado que viaja a ``takab/cfg/<thing>`` lo COMPONE
``commands/sync.py::_CANDIDATES_SQL``. La consola tiene que responder "¿ya lo
tiene?" (``in_sync``) y "¿hay algo que mandarle?" (``has_edge_config``) sin
mandar nada, así que ``queries/fleet.py::_CONFIG_STATE`` repite esa composición
palabra por palabra. Son dos copias del MISMO cálculo en dos archivos, y las dos
copias ya se han pagado caras:

- Si la base diverge, ``in_sync`` compara contra un documento que nadie va a
  publicar y la consola dice PENDIENTE para siempre (o SINCRONIZADO cuando no lo
  está, que es peor).
- Si ``admin_state`` diverge, el gabinete recibe un estado administrativo que la
  consola no espera — y ``cloud_admin_state`` es justo lo que hace que el panel
  del gabinete declare su baja.

Este archivo no juzga si el cálculo es correcto: fija que sea EL MISMO. Es lo
único que hace que una corrección en el original arrastre obligatoriamente a su
espejo, en vez de dejar un bug de tres líneas repartido en dos módulos.

**Deuda conocida que este test bloquea a propósito** (B3, 2026-08-06):
``admin_state`` se deriva SOLO de ``g.status``, mientras que ``is_ghost``
(``routers/fleet.py``) y la métrica de fantasmas usan ``g.status OR s.status``.
Hay un estado alcanzable —sitio retirado, gabinete no propagado; la migración
0024 nació para sanearlo— en el que el panel del gabinete diría ACTIVO y la
consola lo pintaría fantasma. Arreglarlo exige mover las DOS copias en el mismo
commit: cambiar solo el espejo dejaría ``in_sync`` en falso permanente. Este
test es lo que obliga a que se muevan juntas.
"""

from __future__ import annotations

import re

from takab_api.commands.sync import _CANDIDATES_SQL
from takab_api.queries.fleet import _CONFIG_STATE

_MIRROR = str(_CONFIG_STATE)

# El SQL está indentado distinto en cada archivo (2 vs 4 espacios): lo que se
# compara es la EXPRESIÓN, no su sangría.
_BASE = re.compile(r"SELECT\s+(COALESCE\(rs\.config->'edge'.*?)\s+AS\s+base", re.S)
_ADMIN = re.compile(r"(CASE\s+WHEN\s+g\.status.*?END)\s+AS\s+admin_state", re.S)
_DOC = re.compile(r"SELECT\s+(b\.base\s*\|\|.*?)\s+AS\s+doc", re.S)


def _expr(patron: re.Pattern[str], sql: str, etiqueta: str) -> str:
    m = patron.search(sql)
    assert m is not None, (
        f"no se encontró la expresión de `{etiqueta}`: o se renombró, o una de "
        "las dos copias dejó de componer el documento firmado como la otra"
    )
    return re.sub(r"\s+", " ", m.group(1)).strip()


def test_la_BASE_del_documento_es_la_misma_en_el_worker_y_en_la_consola() -> None:
    """``COALESCE(rule_set activo, último doc publicado)``, idéntico en los dos.

    La segunda rama del COALESCE no es un adorno: ``apply_signed_update`` en el
    edge es REEMPLAZO TOTAL, así que publicar sin la base apagaría
    ``command_enabled`` y devolvería los umbrales a la banda por defecto. Si el
    espejo dejara de tenerla, ``in_sync`` mediría contra un documento imposible.
    """
    assert _expr(_BASE, _CANDIDATES_SQL, "base") == _expr(_BASE, _MIRROR, "base")


def test_el_ESTADO_ADMINISTRATIVO_se_deriva_igual_en_el_worker_y_en_la_consola() -> None:
    """``cloud_admin_state`` es lo que hace que el gabinete declare su baja (T-2.65).

    Ver la deuda anotada en la cabecera del archivo: la derivación de HOY mira
    solo ``g.status`` y debería mirar también el sitio padre. Este test no fija
    que sea correcta — fija que sea LA MISMA, para que el arreglo no pueda
    aterrizar en un solo lado.
    """
    assert _expr(_ADMIN, _CANDIDATES_SQL, "admin_state") == _expr(_ADMIN, _MIRROR, "admin_state")


def test_la_FUSION_final_del_documento_es_la_misma() -> None:
    """El ``||`` con ``equipment`` + ``cloud_admin_state``: una firma, un documento."""
    assert _expr(_DOC, _CANDIDATES_SQL, "doc") == _expr(_DOC, _MIRROR, "doc")
