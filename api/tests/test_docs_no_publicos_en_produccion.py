"""[D-22] Con la consola abierta al público, `/docs` deja de estar tapado.

`web_allowed_cidrs` protegía por red todo lo que no exigía autenticación. Al
quitarla —decisión D-22, para que AWS pueda confirmar la suscripción de SNS y para
que el enlace de los correos sirva— eso deja de ser cierto.

Medido antes de abrir: `/api/health`, `/docs` y `/openapi.json` respondían **200
sin credenciales**; el resto daba 401. Los datos estaban bien defendidos; el
CATÁLOGO de la API, no.

No es una vulnerabilidad —la seguridad por oscuridad no es seguridad, y los 401
siguen ahí— pero publicar el esquema completo de una plataforma de alertamiento
regala el trabajo de enumeración a quien quiera buscarle un borde. Se apaga donde
no hace falta.
"""

from __future__ import annotations

import pytest

from takab_api.main import create_app
from takab_api.settings import Settings

#: Lo mínimo que `_exigir_secretos_en_produccion` reclama para dejar construir
#: unos ajustes de producción. Se pone por entorno porque `create_app()` no
#: recibe ajustes: hace su propio `Settings()`, como el resto del proceso.
_ENTORNO_DE_NUBE = {
    "TAKAB_API_ENV": "production",
    "TAKAB_API_DATABASE_URL": "postgresql+psycopg://u:p@db.example/takab",
    "TAKAB_API_AUTH_ISSUER": "https://cognito.example/pool",
    "TAKAB_API_AUTH_AUDIENCE": "cliente",
    "TAKAB_API_AUTH_JWKS_URL": "https://cognito.example/pool/.well-known/jwks.json",
    "TAKAB_API_COMMAND_HMAC_SECRET_PREFIX": "takab/dev/gateway-hmac",
    # El SEGUNDO pool (ocupantes, decisión #7 de T-2.02). La guarda lo exige
    # aparte porque sin él todo id_token de ocupante muere en 401 sin decir por qué.
    "TAKAB_API_AUTH_OCCUPANTS_ISSUER": "https://cognito.example/ocupantes",
    "TAKAB_API_AUTH_OCCUPANTS_AUDIENCE": "cliente-movil",
    "TAKAB_API_AUTH_OCCUPANTS_JWKS_URL": "https://cognito.example/ocupantes/.well-known/jwks.json",
}


def test_en_desarrollo_la_documentacion_sigue_servida() -> None:
    """Apagarla en local sería quitar una herramienta sin ganar nada."""
    assert Settings().es_produccion is False

    app = create_app()

    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"


def test_en_produccion_NO_se_publica_el_catalogo_de_la_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for clave, valor in _ENTORNO_DE_NUBE.items():
        monkeypatch.setenv(clave, valor)
    assert Settings().es_produccion, "el escenario no representa una nube"

    app = create_app()

    assert app.docs_url is None
    assert app.openapi_url is None, (
        "`/openapi.json` publica el esquema completo: cada ruta, cada parámetro y "
        "cada modelo. Con la consola abierta (D-22) eso es público de verdad."
    )
    assert app.redoc_url is None, "redoc sirve el MISMO esquema por otra puerta"
