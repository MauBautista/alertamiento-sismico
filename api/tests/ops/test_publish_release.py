"""[T-7.64] El registro de releases se llena SOLO, y la deriva vuelve a significar algo.

El eje de este archivo es el criterio 5 de la ficha: **una prueba que cruce el
camino entero**. Hasta hoy ``derive_version_drift`` estaba bien probada con
releases INYECTADAS a mano en la lista, y por eso todos sus estados salían verdes
mientras en producción ninguno era alcanzable: nadie escribía en ``fw_releases``.
Probar la función pura con datos de laboratorio no dice nada sobre si esos datos
llegan a existir — es la misma familia de verde que ``T-7.62`` encontró en el
sembrador de fases, donde la prueba pasaba porque el motor de incidentes no corre
en ella.

Así que aquí se publica **por el camino que usará el despliegue** (el CLI, no un
INSERT a mano) y después se le pregunta a la derivación, con el registro leído de
la base, si el gabinete que corre esa versión está ``AL DÍA``.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from takab_api.db.engine import get_engine
from takab_api.ops import publish_release as pr
from takab_api.schemas.fleet import (
    VERSION_AL_DIA,
    VERSION_DESCONOCIDA,
    VERSION_SIN_REFERENCIA,
    ReleaseRef,
    derive_version_drift,
)


def _publicar(version: str, **kw: object) -> str:
    return asyncio.run(pr.publicar(version, **kw))  # type: ignore[arg-type]


def _registro() -> list[ReleaseRef]:
    """El registro TAL Y COMO lo lee la API, no una lista escrita a mano."""

    async def leer() -> list[ReleaseRef]:
        async with get_engine().connect() as conn:
            filas = await __import__(
                "takab_api.queries.fw_releases", fromlist=["list_releases"]
            ).list_releases(conn)
            return [ReleaseRef(version=f.version, age_s=f.age_s) for f in filas]

    return asyncio.run(leer())


def _limpiar() -> None:
    async def borrar() -> None:
        async with get_engine().begin() as conn:
            # `fw_releases` es append-only POR PRIVILEGIO (el rol de la app no
            # puede borrar), no por trigger: el dueño de la tabla sí puede, y la
            # conexión de los tests es la del dueño. Limpiar entre pruebas no
            # relaja ninguna garantía de producción — allí sigue sin haber DELETE
            # concedido a `takab_app`.
            await conn.execute(text("DELETE FROM fw_releases"))

    asyncio.run(borrar())


@pytest.fixture(autouse=True)
def _registro_vacio() -> None:
    _limpiar()
    yield
    _limpiar()


# --- La regla de los `-dirty`, que es pura y no toca la base -----------------


def test_un_arbol_sucio_no_es_publicable() -> None:
    """La rama 4 de la derivación manda los `-dirty` a DESCONOCIDA A PROPÓSITO.

    Publicarlos no añadiría información: borraría esa señal, y el gabinete que
    corre código sin commitear saldría con el rótulo más tranquilizador del panel.
    """
    assert pr.es_publicable("62f3f1e")
    assert not pr.es_publicable("62f3f1e-dirty")
    assert not pr.es_publicable("")


def test_publicar_un_dirty_no_escribe_nada() -> None:
    """Y la regla vive en EL QUE ESCRIBE, no sólo en el que llama.

    Que `deploy.sh` no lo invoque para un árbol sucio es un atajo local; si
    alguien llama a este CLI a mano con un `-dirty`, el registro tampoco se
    ensucia.
    """
    assert _publicar("62f3f1e-dirty") == pr.RECHAZADA_SUCIA
    assert _registro() == []


def test_el_codigo_de_salida_distingue_lo_final_de_lo_reintentable() -> None:
    """3 no es 1: quien llama tiene que poder decidir si reintentar tiene sentido."""
    assert pr.main(["62f3f1e-dirty"]) == pr.SALIDA_SUCIA
    assert pr.SALIDA_SUCIA != pr.SALIDA_ERROR


# --- El camino entero -------------------------------------------------------


def _auditadas(version: str) -> int:
    """Cuántas publicaciones de `version` hay ANOTADAS ahora mismo.

    Se mide como DELTA y no como total porque ``audit_log`` es append-only y el
    conftest no lo trunca: contar en absoluto sumaba las corridas anteriores de
    la propia suite y el número dependía de cuántas veces se hubiera ejecutado.
    """

    async def contar() -> int:
        async with get_engine().connect() as conn:
            return (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM audit_log WHERE verb = 'fw_release_publish' "
                        "AND object = :obj"
                    ),
                    {"obj": f"fw_release:{version}"},
                )
            ).scalar_one()

    return int(asyncio.run(contar()))


def test_publicar_deja_la_version_en_el_registro_con_su_autor() -> None:
    antes = _auditadas("62f3f1e")
    assert _publicar("62f3f1e", notes="gw-dev-0001", actor="deploy:prueba@aqui") == pr.PUBLICADA
    assert [r.version for r in _registro()] == ["62f3f1e"]

    async def fila() -> tuple[str, str]:
        async with get_engine().connect() as conn:
            r = (
                await conn.execute(
                    text("SELECT published_by, notes FROM fw_releases WHERE version = '62f3f1e'")
                )
            ).one()
            return r.published_by, r.notes

    autor, notas = asyncio.run(fila())
    assert autor == "deploy:prueba@aqui"
    assert notas == "gw-dev-0001"
    # Un cambio de plataforma sin autor sería el dato que falta el día que alguien
    # pregunte por qué la flota entera cambió de estado.
    assert _auditadas("62f3f1e") == antes + 1


def test_el_camino_entero_desplegar_publicar_al_dia() -> None:
    """EL CRITERIO 5, y la razón de ser de esta ficha.

    Antes de publicar, un gabinete que corre `62f3f1e` sale ``SIN REFERENCIA`` —no
    porque el gabinete falle, sino porque la plataforma no ha publicado nada—, que
    es lo que TODA la flota decía el 2026-09-20. Después de que el despliegue
    publique, el mismo gabinete, con el mismo latido, sale ``AL DÍA``.
    """
    fw = "62f3f1e"
    antes = derive_version_drift(
        fw_version=fw, age_s=30.0, sin_enlace_s=300.0, releases=_registro()
    )
    assert antes.state == VERSION_SIN_REFERENCIA
    assert antes.releases_behind is None

    assert _publicar(fw, notes="desplegado a takab-pi5") == pr.PUBLICADA

    despues = derive_version_drift(
        fw_version=fw, age_s=30.0, sin_enlace_s=300.0, releases=_registro()
    )
    assert despues.state == VERSION_AL_DIA
    assert despues.releases_behind == 0


def test_un_gabinete_que_no_se_actualizo_sigue_delatandose() -> None:
    """Publicar no vuelve verde a nadie por sí solo: sólo hace comparable la flota.

    Si publicar «arreglara» el panel, sería un maquillaje. Lo que hace es que el
    gabinete atrasado pase de indistinguible a ATRASADO.
    """
    _publicar("62f3f1e")
    viejo = derive_version_drift(
        fw_version="0ae06a0", age_s=30.0, sin_enlace_s=300.0, releases=_registro()
    )
    assert viejo.state == VERSION_DESCONOCIDA  # corre algo que nadie publicó


def test_republicar_la_misma_version_es_benigno_y_no_reescribe_su_fecha() -> None:
    """Un redespliegue del mismo SHA es rutina; el router da 409 y aquí no.

    Y lo que de verdad se protege no es el código de salida: es `released_at`. Es
    lo que `release_age_s` convierte en «cuánto lleva la flota corriendo código
    viejo», así que reescribirlo reescribiría a posteriori la deriva de todos.
    """

    async def fecha() -> object:
        async with get_engine().connect() as conn:
            return (
                await conn.execute(
                    text("SELECT released_at FROM fw_releases WHERE version = '62f3f1e'")
                )
            ).scalar_one()

    assert _publicar("62f3f1e") == pr.PUBLICADA
    original = asyncio.run(fecha())

    assert _publicar("62f3f1e") == pr.YA_ESTABA
    assert asyncio.run(fecha()) == original
    assert len(_registro()) == 1
    assert pr.main(["62f3f1e"]) == pr.SALIDA_OK


def test_el_orden_del_registro_es_el_que_la_deriva_cuenta() -> None:
    """`releases_behind` es el índice en la lista, así que el orden ES el dato."""
    for v in ("aaaaaaa", "bbbbbbb", "ccccccc"):
        assert _publicar(v) == pr.PUBLICADA
    reg = _registro()
    assert [r.version for r in reg] == ["ccccccc", "bbbbbbb", "aaaaaaa"]
    d = derive_version_drift(fw_version="aaaaaaa", age_s=30.0, sin_enlace_s=300.0, releases=reg)
    assert d.releases_behind == 2
