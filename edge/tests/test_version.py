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

from takab_edge.version import fw_version


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
