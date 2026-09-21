"""T-7.25 · `consultando` deja de ser inalcanzable, y se DERIVA del intento.

`procedencia.de_fila()` traduce UNA fila de `reference_earthquakes`. Con eso solo,
``consultando`` —«se le preguntó a la fuente y todavía no contestó»— **no se podía
alcanzar jamás**: mientras la pregunta está en vuelo esa fila no existe, así que un
timeout, un 5xx o un worker muerto a mitad se leían igual que «nadie preguntó
nunca» (`sin_dato_externo`).

`de_consulta()` mete en la derivación el otro hecho —el INTENTO, que sí está
registrado— y con los dos la máquina de estados queda completa. Lo que estos tests
fijan es la separación que da sentido al vocabulario:

* **nadie preguntó** ⇒ `sin_dato_externo` (lo de hoy, y lo que se despliega),
* **pregunté y no me contestó** ⇒ `consultando`,
* **contestó y nada suyo es éste** ⇒ `sin_correlacion`,
* **contestó y éste es** ⇒ lo que diga la fila: `preliminar` o `confirmado`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import psycopg
import pytest

from takab_api import procedencia as P
from tests.catalogo.fixtures import dsn

PREGUNTADO = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
CONTESTADO = datetime(2026, 9, 20, 12, 0, 6, tzinfo=UTC)


def _intento(**over) -> dict:
    base = {
        "provider": "USGS",
        "asked_at": PREGUNTADO,
        "answered_at": None,
        "outcome": None,
        "catalog_key": None,
        "detail": "",
    }
    return {**base, **over}


def _fila_citable(estado: str = P.CONFIRMADO) -> dict:
    return {
        "source": "USGS",
        "consulted_at": CONTESTADO,
        "review_status": estado,
        "provider_event_id": "us7000lh50",
    }


def test_sin_intento_NADIE_pregunto() -> None:
    """Sin fila de intento el estado es `sin_dato_externo`, y eso es un hecho.

    Es el caso de TODOS los incidentes mientras la consulta se despliegue
    apagada, que es como se despliega. No es `sin_correlacion`: ésa afirma algo
    sobre el catálogo de referencia —que se le preguntó y ninguno es éste— y
    aquí no se ha preguntado nada.

    ⚠️ Esta guarda acreditaba una rama que la producción no ejecutaba. El único
    llamador (`forensics/_catalog`) sólo entraba en `de_consulta` cuando HABÍA
    fila: sin ella se quedaba con el `sin_correlacion` del constructor, así que
    `de_consulta(None, None)` estaba verde aquí y muerto allí. Quien lo ejerce
    de verdad por el camino de producción es
    `tests/catalogo/test_consulta.py::test_SIN_fila_de_consulta_nadie_pregunto_…`,
    contra la base y hasta la línea del dictamen; esto es su cara unitaria.
    """
    assert P.de_consulta(None, None).estado == P.SIN_DATO_EXTERNO
    assert P.de_consulta(None, _fila_citable()).estado == P.CONFIRMADO


def test_una_pregunta_en_vuelo_es_consultando() -> None:
    """El worker escribió el intento y todavía no ha vuelto."""
    p = P.de_consulta(_intento(), None)
    assert p.estado == P.CONSULTANDO
    assert p.fuente == "USGS"
    assert p.consultado_en == PREGUNTADO
    assert not p.pinta_cifra


def test_un_intento_que_no_obtuvo_respuesta_tambien_es_consultando() -> None:
    """Un timeout es «pregunté y no me contestó», que es lo que dice el glosario.
    Lo que NO puede ser es `sin_dato_externo`: eso afirmaría que nadie preguntó."""
    p = P.de_consulta(_intento(outcome="sin_respuesta", detail="HTTP 503"), None)
    assert p.estado == P.CONSULTANDO


def test_contesto_y_nada_suyo_es_este_es_sin_correlacion() -> None:
    p = P.de_consulta(_intento(answered_at=CONTESTADO, outcome="sin_correlacion"), None)
    assert p.estado == P.SIN_CORRELACION
    assert p.consultado_en == CONTESTADO
    assert not p.pinta_cifra


def test_contesto_y_caso_da_el_estado_de_la_FILA() -> None:
    """Casar no concede procedencia: la concede la fila, con su hora de consulta
    y el estado que declaró la fuente."""
    intento = _intento(answered_at=CONTESTADO, outcome="correlacionado", catalog_key="USGS-x")
    assert P.de_consulta(intento, _fila_citable(P.CONFIRMADO)).estado == P.CONFIRMADO
    assert P.de_consulta(intento, _fila_citable(P.PRELIMINAR)).estado == P.PRELIMINAR


def test_caso_pero_la_fila_no_es_citable_degrada_al_silencio() -> None:
    """La degradación de `T-5.10` sigue mandando: sin hora de consulta la cifra
    existe y no se pinta. Que el worker diga «correlacionado» no la rescata."""
    intento = _intento(answered_at=CONTESTADO, outcome="correlacionado", catalog_key="USGS-x")
    sin_hora = {**_fila_citable(), "consulted_at": None}
    assert P.de_consulta(intento, sin_hora).estado == P.SIN_DATO_EXTERNO


@pytest.mark.parametrize("estado", [P.CONSULTANDO, P.SIN_CORRELACION])
def test_los_dos_estados_que_produce_el_intento_NO_pintan_cifra(estado: str) -> None:
    assert not P.pinta_cifra(estado)


def test_los_desenlaces_del_worker_son_los_que_admite_la_base() -> None:
    """Espejo del CHECK de `catalog_consultations.outcome`, leído de LA BASE.

    Si alguien añade un cuarto desenlace y no le da estado aquí, la derivación
    lo trataría como «contestó y casó» en silencio — un intento que la fuente
    resolvió de una cuarta manera se publicaría como una correlación buena.

    ⚠️ Esto leía `db/schema.sql` con una expresión regular, y así el censo
    nacía ciego a la mitad de su propio caso: un desenlace añadido **sólo en la
    migración** —que es por donde pasa toda base que ya existe, y son todas las
    de la nube— lo dejaba verde. Ahora se le pregunta al catálogo del sistema
    de la base contra la que corre la suite, que es la que de verdad acepta o
    rechaza el `INSERT`.
    """
    conn = psycopg.connect(dsn(), autocommit=True)
    try:
        filas = conn.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'catalog_consultations'::regclass AND contype = 'c'"
            "   AND pg_get_constraintdef(oid) LIKE '%outcome%'"
        ).fetchall()
    finally:
        conn.close()
    assert len(filas) == 1, f"se esperaba UN check de `outcome` y la base tiene {len(filas)}"
    admitidos = set(re.findall(r"'([^']+)'::text", filas[0][0]))
    assert admitidos == set(P.DESENLACES), (
        f"la base admite {sorted(admitidos)} y el módulo declara {sorted(P.DESENLACES)}"
    )
