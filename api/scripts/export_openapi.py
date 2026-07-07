"""Vuelca el OpenAPI de la API a ``shared/sdk-ts/openapi.json`` (T-1.22 · G8).

Determinista: mismo árbol → mismo byte a byte (``sort_keys``, sin timestamps ni
dependencia de entorno). Se usa como fuente del cliente ``sdk-ts`` y como drift
gate en CI (``git diff --exit-code``).

Los frames del canal WebSocket (``ws/protocol.py``) no cuelgan de ninguna ruta
HTTP, así que FastAPI no los emite solos: se inyectan a mano en
``components/schemas`` para que el SDK tenga los tipos del live.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

# El contrato publicado es el de producción: ``/dev/token`` (solo dev, atado a
# JWKS inline) queda fuera para que el dump no dependa del entorno.
os.environ.pop("TAKAB_API_AUTH_JWKS_JSON", None)

from takab_api.main import create_app  # noqa: E402
from takab_api.ws import protocol as wsp  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT = _REPO_ROOT / "shared" / "sdk-ts" / "openapi.json"


def _ws_frame_models() -> list[type[BaseModel]]:
    """Modelos Pydantic definidos en ``ws/protocol.py`` (frames del canal live)."""
    return sorted(
        (
            obj
            for obj in vars(wsp).values()
            if isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
            and obj.__module__ == wsp.__name__
        ),
        key=lambda m: m.__name__,
    )


def build_openapi() -> dict[str, Any]:
    """Construye el OpenAPI + los esquemas de los frames WebSocket."""
    schema = create_app().openapi()

    _, ws_defs = models_json_schema(
        [(m, "serialization") for m in _ws_frame_models()],
        ref_template="#/components/schemas/{model}",
    )
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, definition in ws_defs.get("$defs", {}).items():
        components.setdefault(name, definition)
    return schema


def main() -> None:
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(build_openapi(), sort_keys=True, indent=2, ensure_ascii=False)
    _OUT.write_text(text + "\n", encoding="utf-8")
    print(f"OpenAPI escrito en {_OUT.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
