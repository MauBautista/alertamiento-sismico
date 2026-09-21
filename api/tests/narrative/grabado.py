"""T-7.27 · Las respuestas grabadas de OpenRouter, y qué son exactamente.

**Son RÉPLICAS, no capturas.** Están escritas a mano con la forma documentada de la
API —`GET /api/v1/models` con `architecture.input_modalities`, y una respuesta de
`POST /chat/completions` a una petición que llevaba una imagen—, porque capturar las de
verdad exige la clave real y salida a la red, que es lo que `GATE-AWS` tiene abierto.
Se dice aquí y no en un comentario perdido: **ninguna cifra de estos ficheros es una
medición** y nadie puede citarlas como tal. Lo que sí fijan es la FORMA, que es lo que
el código parsea y lo que se rompe en silencio cuando cambia.

`enrutar` existe porque desde esta ficha el camino real hace **dos** peticiones: el
catálogo una vez por proceso y la redacción en cada dictamen. Un `MockTransport` con un
solo `handler` respondía lo mismo a las dos, y el resultado era un catálogo interpretado
como redacción — que es un fallo de prueba, no de producto.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx

_GRABADAS = Path(__file__).resolve().parent / "grabadas"

CATALOGO_CON_VISION = json.loads((_GRABADAS / "modelos-con-vision.json").read_text("utf-8"))
CATALOGO_SIN_VISION = json.loads((_GRABADAS / "modelos-sin-vision.json").read_text("utf-8"))
CHAT_CON_IMAGEN = json.loads((_GRABADAS / "chat-con-imagen.json").read_text("utf-8"))

#: El slug que traen las tres grabadas. Es el que `deploy.sh` exporta en `dev`.
MODELO = "anthropic/claude-sonnet-5"


def enrutar(
    chat: Callable[[httpx.Request], httpx.Response],
    *,
    catalogo: dict | None = None,
    fallo_de_catalogo: Callable[[httpx.Request], httpx.Response] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Un handler que distingue el catálogo de la redacción por la RUTA."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            if fallo_de_catalogo is not None:
                return fallo_de_catalogo(request)
            cuerpo = catalogo if catalogo is not None else CATALOGO_CON_VISION
            return httpx.Response(200, json=cuerpo)
        return chat(request)

    return handler
