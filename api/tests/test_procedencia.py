"""T-5.10 · La regla de procedencia: **con procedencia, o no se pinta**.

TAKAB mide lo que pasó en un edificio; la magnitud y el epicentro los publica una
fuente oficial. Las dos cosas se leen en la misma pantalla, y **una cifra sin
procedencia se lee como propia** — que es la confusión que este vocabulario existe
para impedir.

Lo que estos tests fijan:

1. **Los cinco estados existen y se llaman igual en las tres superficies.** El
   glosario es JSON porque el panel del gabinete no puede importar nada; que las
   tres lo lean del mismo sitio es lo único que evita tres vocabularios.
2. **«Consultando», jamás «estimando».** No es estilo: «estimando» sugiere que el
   sistema está CALCULANDO una magnitud, que es exactamente lo que el blueprint
   §14 prohíbe. Nosotros preguntamos.
3. **La cifra solo se pinta con fuente y hora de consulta**, y la degradación es
   hacia el silencio: sin procedencia completa, `sin_dato_externo`.
4. **`sin_correlacion` tiene texto propio.** Es el estado que más falta hacía: sin
   él, un «no sé» se convierte en una pantalla vacía que el operador lee como «no
   pasó nada».
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from takab_api import procedencia as P

_RAIZ = Path(__file__).resolve().parents[2]
_GLOSARIO = _RAIZ / "shared/glossary/procedencia.json"

#: Las tres superficies que pintan cifras: el panel del gabinete (servido por el
#: propio Pi), la consola SOC y la app móvil.
SUPERFICIES = ("panel", "consola", "movil")

#: Los cinco, por su nombre canónico. Escritos a mano A PROPÓSITO: es la lista que
#: la ficha exige, y que aparezca un sexto estado sin decidir su texto en las tres
#: superficies tiene que poner esto rojo.
LOS_CINCO = (
    P.SIN_DATO_EXTERNO,
    P.CONSULTANDO,
    P.PRELIMINAR,
    P.CONFIRMADO,
    P.SIN_CORRELACION,
)


def test_los_cinco_estados_existen_y_no_hay_mas() -> None:
    assert P.estados() == LOS_CINCO, (
        "cambió la máquina de estados de procedencia. Si añades uno, dale texto en "
        f"las TRES superficies y añádelo aquí: {set(P.estados()) ^ set(LOS_CINCO)}"
    )


@pytest.mark.parametrize("estado", LOS_CINCO)
@pytest.mark.parametrize("superficie", SUPERFICIES)
def test_cada_estado_tiene_texto_en_CADA_superficie(estado: str, superficie: str) -> None:
    """Un estado sin texto en una superficie es un hueco en esa pantalla, y un
    hueco se lee como «no pasó nada»."""
    texto = P.rotulo(estado, superficie)
    assert texto and texto.strip(), f"`{estado}` no tiene texto en `{superficie}`"


def test_NUNCA_se_dice_estimando() -> None:
    """La palabra prohibida, en todo el glosario y en las tres superficies.

    «Estimando» sugiere que el sistema calcula la magnitud. No la calcula: se la
    pregunta a quien la publica. La diferencia es la línea que separa a TAKAB de
    prometer una cuenta atrás (blueprint §14).
    """
    crudo = _GLOSARIO.read_text(encoding="utf-8").lower()
    prohibidas = [p for p in ("estimando", "estimada", "estimación", "estimacion") if p in crudo]
    # El bloque `prohibido` las NOMBRA para prohibirlas: se descuenta.
    permitido = json.dumps(P.glosario()["prohibido"], ensure_ascii=False).lower()
    coladas = [p for p in prohibidas if p not in permitido]
    assert not coladas, (
        f"el glosario de procedencia usa {coladas}: nosotros no estimamos una "
        "magnitud, se la preguntamos a la fuente. El texto correcto es «consultando»."
    )
    assert "consultando" in P.rotulo(P.CONSULTANDO, "consola").lower()


def test_solo_DOS_estados_autorizan_a_pintar_la_cifra() -> None:
    """Y los otros tres se pintan igual — con su texto, nunca con un hueco."""
    pintan = {e for e in LOS_CINCO if P.pinta_cifra(e)}
    assert pintan == {P.PRELIMINAR, P.CONFIRMADO}, (
        f"cambió qué estados pintan la cifra externa: {pintan}. Solo lo que la "
        "fuente ha publicado —preliminar o confirmado— puede aparecer como número."
    )


def test_sin_hora_de_consulta_la_cifra_NO_se_pinta() -> None:
    """La regla entera, en su caso más peligroso: hay magnitud y no hay procedencia.

    Es la situación de las TRECE filas del seed de referencia: traen magnitud y
    fuente, y ninguna trae `consulted_at`. Pintarlas afirmaría una procedencia que
    no consta.
    """
    fila = {"source": "SSN", "magnitude": 7.1, "review_status": "confirmado"}
    assert P.de_fila(fila).estado == P.SIN_DATO_EXTERNO
    assert P.de_fila(fila).pinta_cifra is False

    completa = dict(fila, consulted_at=datetime(2026, 9, 4, tzinfo=UTC))
    assert P.de_fila(completa).estado == P.CONFIRMADO
    assert P.de_fila(completa).pinta_cifra is True


def test_un_estado_de_revision_desconocido_degrada_hacia_el_SILENCIO() -> None:
    """Degrada, nunca inventa. Un valor que no entendemos no puede ascender a
    «confirmado» — y tampoco puede tumbar la pantalla."""
    fila = {
        "source": "SSN",
        "consulted_at": datetime(2026, 9, 4, tzinfo=UTC),
        "review_status": "lo-que-sea",
    }
    assert P.de_fila(fila).estado == P.SIN_DATO_EXTERNO


def test_sin_correlacion_TIENE_texto_y_no_es_un_hueco() -> None:
    """El estado que más falta hacía. Su ausencia convertía un «no sé» en una
    pantalla vacía que el operador lee como «no pasó nada»."""
    for superficie in SUPERFICIES:
        texto = P.rotulo(P.SIN_CORRELACION, superficie)
        assert "correlaci" in texto.lower(), (
            f"el texto de `sin_correlacion` en `{superficie}` no dice que no hubo "
            f"correlación: {texto!r}"
        )
    assert P.pinta_cifra(P.SIN_CORRELACION) is False


def test_el_estado_de_HOY_esta_declarado_por_escrito() -> None:
    """Criterio 6 de la ficha: qué pasa con la magnitud que nunca se escribe.

    La respuesta no puede ser un silencio del código: `seismic_events.magnitude` se
    inserta SIEMPRE en NULL y la ficha exige decidir entre escribirla con
    procedencia o retirar el campo. Se conserva, y el glosario dice por qué.
    """
    hoy = P.glosario()["estados"][P.SIN_DATO_EXTERNO]
    assert hoy.get("es_hoy_el_normal") is True, (
        "el glosario dejó de declarar cuál es el estado real de la flota hoy"
    )
    razon = " ".join(hoy["por_que"]).lower()
    assert "null" in razon and "engine.py" in razon, (
        "la razón no cita el hecho que la sostiene: el INSERT que pone la magnitud "
        f"en NULL. Dice: {razon!r}"
    )


def test_el_glosario_declara_SU_TAMAÑO() -> None:
    """Guarda de no-vacuidad: todo lo de arriba lee un JSON. Si el archivo cambiara
    de forma y `estados` saliera vacío, los `parametrize` no generarían ni un caso
    y la suite pasaría en verde sin comprobar nada."""
    g = P.glosario()
    assert len(g["estados"]) == 5, f"el glosario trae {len(g['estados'])} estados, no 5"
    assert len(SUPERFICIES) == 3
    for estado, fila in g["estados"].items():
        faltan = [s for s in SUPERFICIES if s not in fila]
        assert not faltan, f"`{estado}` no tiene texto para {faltan}"
        assert isinstance(fila["pinta_cifra"], bool), f"`{estado}.pinta_cifra` no es booleano"


def test_la_migracion_del_catalogo_es_IDEMPOTENTE_y_sin_SET_ROLE() -> None:
    """Las dos invariantes de migración del repo, sobre la 0060.

    `reference_earthquakes` es una tabla PREEXISTENTE: el DDL va como usuario de
    conexión. Y re-aplicarla no puede fallar.
    """
    import ast

    ruta = _RAIZ / "api/migrations/versions/0060_procedencia_del_catalogo.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))

    # El SQL, no la prosa: el docstring del módulo DICE «sin SET ROLE», así que un
    # barrido del texto crudo se pone rojo por la explicación correcta (pasó al
    # escribir esto). Se leen las constantes `_UP`/`_DOWN` del árbol de sintaxis.
    sql = {
        objetivo.id: nodo.value.value
        for nodo in arbol.body
        if isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant)
        for objetivo in nodo.targets
        if isinstance(objetivo, ast.Name) and isinstance(nodo.value.value, str)
    }
    assert "_UP" in sql and "_DOWN" in sql, f"no se encontraron _UP/_DOWN: {sorted(sql)}"

    assert "SET ROLE" not in sql["_UP"].upper(), (
        "la 0060 usa `SET ROLE` sobre una tabla preexistente: rompe la invariante de "
        "dueños (la columna quedaría con otro dueño que la tabla)"
    )
    assert sql["_UP"].count("ADD COLUMN IF NOT EXISTS") >= 1, (
        "las columnas no se añaden con `IF NOT EXISTS`: re-aplicar la migración fallaría"
    )
    assert "pg_constraint" in sql["_UP"], (
        "el CHECK se añade sin comprobar `pg_constraint`: re-aplicar la migración "
        "fallaría con «constraint ya existe»"
    )
    for columna in ("consulted_at", "review_status", "provider_event_id"):
        assert columna in sql["_UP"], f"la migración no añade `{columna}`"
