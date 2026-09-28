"""[F3·r2 · D-43] El contrato publica QUIÉN firmó: la app no lo puede adivinar.

La app sellaba «FIRMA DIGITAL · INSPECTOR» todo certificado porque
``MobileDictamenOut`` no traía ``signature_kind`` y el tipo del SDK lo declaraba
opcional a mano: los tests de jest lo inyectaban en el fixture y pasaban con un campo
que la API real no enviaba. Esta guarda lee el OpenAPI que genera la app y el que
está comiteado para el SDK."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from takab_api.main import create_app

_SDK = Path(__file__).resolve().parents[3] / "shared/sdk-ts/openapi.json"

_ESPERADO = {
    "MobileDictamenOut": {"signature_kind", "band", "confirmed_by_role"},
    "DictamenOut": {"signature_kind", "band", "confirmed_by_role"},
}


@pytest.mark.parametrize("fuente", ["app", "sdk"])
def test_el_contrato_del_dictamen_trae_tipo_de_firma_banda_y_rol(fuente: str) -> None:
    doc = create_app().openapi() if fuente == "app" else json.loads(_SDK.read_text())
    esquemas = doc["components"]["schemas"]
    for modelo, campos in _ESPERADO.items():
        faltan = campos - set(esquemas[modelo]["properties"])
        assert not faltan, (fuente, modelo, faltan)
