"""[T-6.18] Las dos mitades de la BAJADA del SOC local no pueden separarse.

`make soc-local` levantaba la API de producción tal cual, y su publicador es el
de **AWS IoT Core**: en una laptop sin credenciales cada comando firmado moría
al publicar, un simulacro salía con «5 SIN COMANDO EMITIDO» y el aborto por
sismo real no se podía ensayar (auditoría UI/UX, U-37). Ahora la API del arnés
publica en el buzón del thing y el gabinete lo escucha.

Son dos procesos distintos que tienen que coincidir en **tres cosas**, y ninguna
la garantizaba nadie:

1. el BUZÓN — si `demo/api_local.py` publicara en un directorio y el gabinete
   escuchara en otro, el comando se escribiría donde nadie lee y el simulacro
   volvería a quedarse sin acuse, sin un solo error en ningún log;
2. que el gabinete EJECUTE comandos remotos — de fábrica va apagado, y así debe
   seguir; el arnés lo enciende a propósito;
3. que el orquestador arranque la app CON la bajada, no la de producción.

Esto se comprueba estáticamente porque el arnés entero no cabe en CI: son cinco
procesos, una base y un gabinete. Lo que sí cabe es que las piezas sigan
apuntando al mismo sitio.
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
SOC_LOCAL_PY = (_ROOT / "demo" / "soc_local.py").read_text("utf-8")
SOC_LOCAL_SH = (_ROOT / "demo" / "soc_local.sh").read_text("utf-8")
API_LOCAL_PY = (_ROOT / "demo" / "api_local.py").read_text("utf-8")

#: La variable por la que viaja el buzón. Es el contrato entre los dos procesos.
BUZON = "TAKAB_DEMO_DOWNLINK"


def test_las_dos_mitades_leen_el_buzon_de_la_misma_variable() -> None:
    """Si una de las dos dejara de leerla, el comando iría a un buzón mudo."""
    assert BUZON in API_LOCAL_PY, "la API del arnés ya no lee el buzón del entorno"
    assert BUZON in SOC_LOCAL_PY, "el gabinete del arnés ya no lee el buzón del entorno"
    assert BUZON in SOC_LOCAL_SH, "el orquestador ya no exporta el buzón"


def test_el_orquestador_levanta_la_api_CON_la_bajada() -> None:
    """`takab_api.main:app` publica a AWS IoT: en local eso es la avería."""
    assert "uvicorn demo.api_local:app" in SOC_LOCAL_SH
    assert "uvicorn takab_api.main:app" not in SOC_LOCAL_SH
    # El venv de la API no conoce la raíz del repo; sin esto uvicorn no importa.
    assert 'PYTHONPATH="$ROOT"' in SOC_LOCAL_SH


def test_el_gabinete_escucha_y_ejecuta() -> None:
    """Escuchar no basta: sin `--command-enabled` verifica la firma y RECHAZA.

    Medido el 2026-09-09 con la bajada ya puesta: el comando llegó, la firma se
    verificó y el acuse fue `rejected` con `detail=command_enabled=false`. El
    default de fábrica NO se toca —un gabinete recién provisionado no acciona
    nada que le mande la nube—; lo enciende el arnés, y lo declara al arrancar.
    """
    assert '"--downlink",' in SOC_LOCAL_PY
    assert '"--command-enabled"' in SOC_LOCAL_PY
    assert "--sin-comandos" in SOC_LOCAL_PY, "se perdió la forma de volver al gabinete de fábrica"


def test_la_api_del_arnes_sustituye_SOLO_el_publicador() -> None:
    """La app es la de producción; lo único inyectado es a dónde publica.

    Si esto empezara a sustituir la firma o el verificador, el arnés probaría su
    propio código en vez del `CommandDispatcher` real del edge, que es justo lo
    que hay que probar.
    """
    os.environ.setdefault(BUZON, str(_ROOT / ".local-soc" / "bajada"))
    from demo.api_local import app
    from demo.spool import SpoolCommandPublisher

    from takab_api.routers.commands import get_publisher

    override = app.dependency_overrides.get(get_publisher)
    assert override is not None, "la API del arnés dejó de enchufar la bajada"
    assert isinstance(override(), SpoolCommandPublisher)
    assert list(app.dependency_overrides) == [get_publisher], (
        "el arnés sustituye algo más que el publicador: "
        f"{[getattr(f, '__name__', f) for f in app.dependency_overrides]}"
    )
