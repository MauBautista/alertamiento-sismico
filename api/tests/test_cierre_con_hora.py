"""[T-7.51] Un incidente cerrado no puede decir en papel que sigue abierto.

## El defecto, medido en la nube dev el 2026-09-17

Tres de los cuatro incidentes vivos tenían `state = 'closed'` y `closed_at`
**nulo**. El dictamen imprime el campo CIERRE como «EN CURSO» cuando ese campo
falta, así que **el dictamen pericial de un incidente cerrado afirmaba que seguía
abierto**. Misma clase de defecto que `T-7.38`, `T-7.42` y `T-7.43` cerraron en
otras frases del mismo papel.

## La puerta

Ningún camino de la aplicación cierra sin la hora: `lifecycle.transition_incident`
pone `closed_at` **y** escribe `incident_actions` **y** audita. Los tres no tenían
ninguna de las tres cosas — y `audit_log` lo conserva la purga de `T-7.10` **por
nombre**, así que su ausencia es evidencia, no falta de datos.

Quien cerraba era el **arnés de los E2E móviles**
(`infra/scripts/sql/staging-incident/{reset,crisis}.sql`), cuyo `SITE_ID` por
defecto es el del gabinete REAL de Puebla. Cerraba incidentes de operación.

## Lo que NO se hizo, y es la mitad de la ficha

No se rellenó `closed_at`. La hora real de aquellos cierres **no existe en
ninguna parte**, y fabricarla contaminaría la tabla de la que cuelga un dictamen
pericial. Se DECLARA la ausencia, como hace `documentos/identidad.py` con los
cuatro datos que no tiene.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from conftest import reset
from takab_api.dictamen.model import cierre_text

_RAIZ = Path(__file__).resolve().parents[2]
TS = "%Y-%m-%d %H:%M UTC"


# ───────────────────────────────── el papel: tres casos, no dos


def test_un_incidente_CERRADO_no_puede_decir_EN_CURSO() -> None:
    """El defecto, en su forma más pequeña y comprobable."""
    assert cierre_text(None, "closed", True, TS) != "EN CURSO"
    assert "CERRADO" in cierre_text(None, "closed", True, TS)
    assert "NO REGISTRADA" in cierre_text(None, "closed", True, TS), (
        "el papel tiene que DECLARAR que la hora no se registró, no disimularla: "
        "un hueco se lee como un descuido y una hora inventada es peor"
    )


def test_un_incidente_ABIERTO_sigue_diciendo_EN_CURSO() -> None:
    """La contraprueba: no vale arreglarlo rotulando todo como cerrado."""
    assert cierre_text(None, "open", False, TS) == "EN CURSO"
    assert cierre_text(None, "in_review", False, TS) == "EN CURSO"


def test_un_cierre_CON_hora_imprime_la_hora() -> None:
    assert cierre_text(datetime(2026, 9, 15, 7, 5, tzinfo=UTC), "closed", False, TS) == (
        "2026-09-15 07:05 UTC"
    )


def test_el_dictamen_de_un_incidente_cerrado_SIN_hora_lo_declara() -> None:
    """Y en el papel de verdad, no sólo en la función pura."""
    from takab_api.dictamen.pdf import render
    from tests.dictamen.test_pdf import model
    from tests.documentos.espia import espia_del_render

    with espia_del_render() as cap:
        render(model(closed_at=None, state="closed", cierre_sin_hora=True))
    assert "NO REGISTRADA" in cap.texto, (
        "el dictamen de un incidente cerrado sin hora no declara la ausencia"
    )
    assert "EN CURSO" not in cap.texto, "sigue afirmando que el incidente sigue abierto"


# ───────────────────────────────── la base, que es donde se cierra la puerta


def test_la_BASE_impide_cerrar_sin_hora_ni_declaracion(seeded: psycopg.Connection) -> None:
    """La guarda va en la base, no en el código.

    Un `CHECK` lo hace imposible de escribir mal desde **cualquier** puerta,
    incluida la que no encontramos: los `.sql` de `infra/scripts/` no pasan por
    ningún censo de `api/src`, que es justo por donde entró este defecto.
    """
    reset(seeded)
    fila = seeded.execute(
        "SELECT incident_id FROM incidents WHERE state <> 'closed' LIMIT 1"
    ).fetchone()
    assert fila, "la semilla no dejó ningún incidente abierto: este test no mide nada"
    with pytest.raises(psycopg.errors.CheckViolation, match="cierre_con_hora"):
        seeded.execute(
            "UPDATE incidents SET state = 'closed' WHERE incident_id = %s",
            (fila[0],),
        )


def test_cerrar_CON_hora_sigue_siendo_posible(seeded: psycopg.Connection) -> None:
    """Porque una guarda que bloquea lo legítimo se acaba quitando entera."""
    reset(seeded)
    fila = seeded.execute(
        "SELECT incident_id FROM incidents WHERE state <> 'closed' LIMIT 1"
    ).fetchone()
    assert fila
    cur = seeded.execute(
        "UPDATE incidents SET state = 'closed', closed_at = now() WHERE incident_id = %s",
        (fila[0],),
    )
    assert cur.rowcount == 1


def test_una_fila_DECLARADA_sigue_siendo_escribible(seeded: psycopg.Connection) -> None:
    """⚠️ La razón por la que hay columna y no sólo un `CHECK … NOT VALID`.

    Medido: un `NOT VALID` bloquea también los UPDATE de las filas que YA lo
    violan. Las tres de producción se habrían convertido en **minas**: el
    backfill de picos del dictamen, el UPSERT de la ingesta o `replay/service.py`
    fallarían al tocarlas. Con la declaración, quedan dichas y siguen vivas.
    """
    reset(seeded)
    fila = seeded.execute(
        "SELECT incident_id FROM incidents WHERE state <> 'closed' LIMIT 1"
    ).fetchone()
    assert fila
    seeded.execute(
        "UPDATE incidents SET state='closed', cierre_sin_hora=true WHERE incident_id = %s",
        (fila[0],),
    )
    cur = seeded.execute(
        "UPDATE incidents SET severity = 'critical' WHERE incident_id = %s", (fila[0],)
    )
    assert cur.rowcount == 1, (
        "una fila declarada dejó de poder actualizarse: el backfill de picos del "
        "dictamen y el UPSERT de la ingesta fallarían sobre ella"
    )


# ───────────────────── el censo: ninguna puerta del repo cierra sin la hora


def test_NINGUN_sitio_del_repo_cierra_un_incidente_SIN_la_hora() -> None:
    """Derivado del árbol, y a propósito FUERA de `api/src`.

    Por ahí entró: `test_audit_single_writer.py` sólo recorre
    `api/src/takab_api/**/*.py`, así que un `UPDATE` desde `infra/scripts/` pasa
    ese censo **porque no mira**, no porque no infrinja. Éste mira el repo.
    """
    cierra = re.compile(r"state\s*=\s*'closed'", re.I)
    culpables: list[str] = []
    for ruta in sorted(_RAIZ.rglob("*.sql")):
        if "node_modules" in ruta.parts or ".venv" in ruta.parts:
            continue
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        for n, linea in enumerate(texto.splitlines(), 1):
            if linea.lstrip().startswith("--") or not cierra.search(linea):
                continue
            # El SET puede repartirse en dos líneas: se mira la sentencia entera.
            ventana = "\n".join(texto.splitlines()[max(0, n - 1) : n + 2])
            if "UPDATE" not in ventana.upper() and "SET" not in ventana.upper():
                continue  # un CHECK o un WHERE, no una escritura
            if "closed_at" not in ventana:
                culpables.append(f"{ruta.relative_to(_RAIZ)}:{n}  {linea.strip()[:80]}")
    assert not culpables, (
        "hay sitios que cierran un incidente sin registrar la hora. El dictamen "
        "imprime «EN CURSO» cuando ese campo falta, así que el papel pericial "
        f"afirmaría que el incidente sigue abierto: {culpables}"
    )


def test_el_censo_CAZA_un_cierre_sin_hora(tmp_path: Path) -> None:
    """Porque un censo que no puede fallar no censa nada."""
    cierra = re.compile(r"state\s*=\s*'closed'", re.I)
    malo = "UPDATE incidents SET state = 'closed' WHERE site_id = :'site'::uuid;"
    bueno = "UPDATE incidents SET state = 'closed', closed_at = now() WHERE x;"
    assert cierra.search(malo) and "closed_at" not in malo
    assert cierra.search(bueno) and "closed_at" in bueno
