"""version — el gabinete declara QUÉ código corre, o admite que no lo sabe.

Por qué existe: `gateways.fw_version` en la nube se llenaba A MANO. Se llenó una vez
(2026-07-30, `737dd73`) y a partir del siguiente despliegue habría empezado a mentir,
porque nadie lo actualizaba. Es el mismo agujero que `/api/health` ya cerró para la
nube con `TAKAB_API_BUILD_SHA`: un dato con pinta de correcto es peor que uno vacío
(regla de oro 7).

`deploy/edge/deploy.sh` escribe el SHA desplegado en `FW_VERSION` junto al código, y
el edge lo LEE y lo publica en su heartbeat. Así la versión es algo que el gabinete
DECLARA, no algo que alguien recordó anotar.
"""

from __future__ import annotations

import pytest
from takab_edge import version as version_mod
from takab_edge.version import fw_version, running_version


@pytest.fixture(autouse=True)
def _restaura_la_captura():
    """La captura del arranque es estado de PROCESO: se restaura entre tests."""
    previo = version_mod._RUNNING
    yield
    version_mod._RUNNING = previo


def test_sin_archivo_no_inventa_version(tmp_path):
    """Sin FW_VERSION la respuesta es None = «no sé», jamás un valor plausible."""
    assert fw_version(tmp_path) is None


def test_lee_el_sha_desplegado(tmp_path):
    (tmp_path / "FW_VERSION").write_text("737dd73\n")
    assert fw_version(tmp_path) == "737dd73"


def test_ignora_espacios_y_saltos(tmp_path):
    # `git rev-parse` deja un salto final; un editor humano puede dejar espacios.
    (tmp_path / "FW_VERSION").write_text("  86ea606  \n\n")
    assert fw_version(tmp_path) == "86ea606"


def test_archivo_vacio_es_sin_dato(tmp_path):
    """Un archivo en blanco (deploy a medias) NO es una versión válida."""
    (tmp_path / "FW_VERSION").write_text("   \n")
    assert fw_version(tmp_path) is None


def test_valor_absurdo_se_descarta(tmp_path):
    """Guard barato contra un archivo corrupto: una versión no es un párrafo."""
    (tmp_path / "FW_VERSION").write_text("x" * 200)
    assert fw_version(tmp_path) is None


def test_no_revienta_si_el_archivo_es_ilegible(tmp_path):
    """Leer la versión JAMÁS puede tumbar el arranque del gabinete."""
    ruta = tmp_path / "FW_VERSION"
    ruta.mkdir()  # un directorio donde se espera un archivo: OSError al leer
    assert fw_version(tmp_path) is None


# --------------------------------------------------------------------------
# [T-2.70] ESCRITO != CORRIENDO. `fw_version()` lee el ARCHIVO en cada latido —
# a propósito, porque T-1.74 pregunta "¿alguien tocó el disco?". Una
# actualización remota pregunta lo contrario: "¿corre el código nuevo?", y esa
# el archivo NO la responde. `deploy.sh` escribe FW_VERSION ANTES de reiniciar,
# así que durante hasta un latido entero (y para siempre si el restart falla)
# el proceso VIEJO publica la versión NUEVA. Un canary cuyo criterio de éxito
# fuera `fw_version` daría VERDE a una actualización que nunca se aplicó.
# --------------------------------------------------------------------------


def test_la_version_que_corre_se_congela_al_arrancar(tmp_path):
    """El proceso declara el código que CARGÓ, no el que hay ahora en el disco."""
    (tmp_path / "FW_VERSION").write_text("aaaaaaa\n")
    version_mod._capture(tmp_path)  # el proceso arranca con aaaaaaa

    # Llega un deploy: reescribe el archivo bajo los pies del proceso vivo.
    (tmp_path / "FW_VERSION").write_text("bbbbbbb\n")

    assert fw_version(tmp_path) == "bbbbbbb", "el ARCHIVO ya es el nuevo"
    assert running_version() == "aaaaaaa", "el PROCESO sigue siendo el viejo"


def test_sin_archivo_al_arrancar_la_version_que_corre_es_sin_dato(tmp_path):
    """«No sé qué corro» se conserva aunque después aparezca un FW_VERSION."""
    version_mod._capture(tmp_path)  # arranca sin archivo (dev local)
    (tmp_path / "FW_VERSION").write_text("ccccccc\n")

    assert fw_version(tmp_path) == "ccccccc"
    assert running_version() is None


def test_la_captura_ocurre_al_importar_el_modulo():
    """Nadie tiene que acordarse de llamarla: si dependiera de la primera
    llamada, un proceso que preguntara por primera vez DESPUÉS de un deploy
    capturaría la versión nueva sin haberla cargado nunca."""
    assert version_mod._RUNNING is not version_mod._SIN_CAPTURAR
