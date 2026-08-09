"""[T-2.86.c · hueco RO-6.c] En producción, un secreto ausente IMPIDE ARRANCAR.

El defecto que cierra esto: los defaults de ``Settings`` **son credenciales de
desarrollo** (``postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab``), así
que un secreto que no llegue en producción no produce un error — produce un
arranque limpio contra el valor equivocado. Eso es exactamente lo contrario de
la regla de oro 6, y es peor que no tener default: un fallo silencioso no se
investiga.

QUÉ SE COMPRUEBA AQUÍ, en las dos direcciones:
  · REQUERIDOS  — un secreto de producción ausente (o igual al default de dev)
    revienta la construcción de ``Settings``.
  · PROHIBIDOS  — una credencial que SOLO existe para desarrollo (la llave que
    firma ``/dev/token``, el JWKS inline, el mapa HMAC inline) presente en
    producción revienta igual. Es la mitad que se olvida: no basta con que
    esté lo que tiene que estar, hace falta que NO esté lo que abre la puerta.
  · Y que nada de esto se activa en desarrollo ni en la propia suite, que es la
    condición para que el arreglo sobreviva a la segunda semana.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from takab_api.settings import (
    DEFAULT_DEV_DATABASE_URL,
    MARCADORES_DE_NUBE,
    PROHIBIDOS_EN_PRODUCCION,
    REQUERIDOS_EN_PRODUCCION,
    ConfiguracionInvalida,
    Settings,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Un despliegue MÍNIMO y sano: lo que ``deploy/cloud/deploy.sh`` +
#: ``deploy/cloud/takab-secrets.sh`` inyectan hoy, reducido a lo que el guardia
#: exige. Cada test parte de aquí y RETIRA una pieza.
PROD_OK = {
    "TAKAB_API_BUILD_SHA": "8f385fb",
    # Marcador de nube: sin al menos uno, `build_sha` suelto es un test, no un
    # despliegue (ver `test_build_sha_suelto_no_es_produccion`).
    "TAKAB_API_QUEUE_URL_EVENTS": "https://sqs.us-east-2.amazonaws.com/1/takab-events",
    "TAKAB_API_DATABASE_URL": "postgresql+psycopg://takab_app:REDACTADO@127.0.0.1:5432/takab",
    "TAKAB_API_AUTH_ISSUER": "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_abc",
    "TAKAB_API_AUTH_AUDIENCE": "cliente-web,cliente-movil",
    "TAKAB_API_AUTH_JWKS_URL": (
        "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_abc/.well-known/jwks.json"
    ),
    # [T-2.99] Segundo pool. Está aquí porque un despliegue SIN él no es "mínimo":
    # es uno donde ningún ocupante puede entrar.
    "TAKAB_API_AUTH_OCCUPANTS_ISSUER": (
        "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_occ"
    ),
    "TAKAB_API_AUTH_OCCUPANTS_AUDIENCE": "cliente-ocupantes",
    "TAKAB_API_AUTH_OCCUPANTS_JWKS_URL": (
        "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_occ/.well-known/jwks.json"
    ),
    "TAKAB_API_COMMAND_HMAC_SECRET_PREFIX": "takab/dev/gateway-hmac",
}


def _entorno(monkeypatch, valores: dict[str, str]) -> None:
    """Deja el entorno EXACTAMENTE en `valores` para todo lo que mira Settings."""
    tocadas = (
        list(PROD_OK)
        + [f"TAKAB_API_{n.upper()}" for n in PROHIBIDOS_EN_PRODUCCION]
        + [f"TAKAB_API_{n.upper()}" for n in MARCADORES_DE_NUBE]
    )
    for clave in tocadas:
        monkeypatch.delenv(clave, raising=False)
    monkeypatch.delenv("TAKAB_API_ENV", raising=False)
    for clave, valor in valores.items():
        monkeypatch.setenv(clave, valor)


# ---------------------------------------------------------------------------
# El desarrollo NO se rompe (la condición sin la cual el arreglo se desactiva)
# ---------------------------------------------------------------------------


def test_sin_senal_de_produccion_los_defaults_siguen_valiendo(monkeypatch) -> None:
    """Sin `build_sha` inyectado no hay producción: los defaults de dev valen.

    Es la mitad que hace el arreglo sostenible. Un guardia que exija secretos en
    la máquina de un desarrollador se desactiva el primer martes.
    """
    _entorno(monkeypatch, {})
    s = Settings()
    assert s.es_produccion is False
    assert s.database_url == DEFAULT_DEV_DATABASE_URL


def test_la_senal_de_produccion_se_deriva_sola_del_commit_desplegado(monkeypatch) -> None:
    """`TAKAB_API_BUILD_SHA` es la señal, y nadie tiene que acordarse de ponerla.

    `deploy/cloud/deploy.sh` la inyecta en CADA despliegue desde T-1.37 (es lo
    que `/health` publica). En local y en CI vale "unknown". Ver el test de
    anclaje de más abajo: si el deploy dejara de inyectarla, esto sale en rojo.
    """
    _entorno(monkeypatch, PROD_OK)
    assert Settings().es_produccion is True


def test_build_sha_suelto_no_es_produccion(monkeypatch) -> None:
    """Una variable suelta es un TEST; un despliegue trae el `cloud.env` entero.

    Este caso no es hipotético: `api/tests/test_health.py` pone
    `TAKAB_API_BUILD_SHA` y nada más para comprobar que `/health` dice qué commit
    está vivo. Con la regla ingenua (`build_sha != "unknown"` a secas) ese test se
    volvía "producción" y el guardia lo reventaba — 500 en la sonda de liveness
    por un defecto de esta clase. De ahí el segundo requisito.
    """
    _entorno(monkeypatch, {"TAKAB_API_BUILD_SHA": "8f385fb"})
    assert Settings().es_produccion is False


@pytest.mark.parametrize("marcador", MARCADORES_DE_NUBE)
def test_cualquier_marcador_de_nube_basta_para_ser_produccion(monkeypatch, marcador) -> None:
    """Cada marcador declarado tiene que activar el perfil por sí solo.

    Si uno dejara de hacerlo (un typo en el nombre del campo), el guardia se
    apagaría en silencio para los despliegues que sólo tuvieran ése.
    """
    valor = "true" if marcador == "ops_metrics_enabled" else "algo"
    _entorno(
        monkeypatch,
        {"TAKAB_API_BUILD_SHA": "8f385fb", f"TAKAB_API_{marcador.upper()}": valor},
    )
    with pytest.raises(ConfiguracionInvalida):  # es producción y le faltan secretos
        Settings()


def test_ningun_marcador_es_a_la_vez_requerido(monkeypatch) -> None:
    """Un marcador que fuera requerido apagaría el guardia que debe denunciarlo."""
    assert not (set(MARCADORES_DE_NUBE) & set(REQUERIDOS_EN_PRODUCCION))


def test_el_perfil_se_puede_forzar_en_los_dos_sentidos(monkeypatch) -> None:
    _entorno(monkeypatch, {**PROD_OK, "TAKAB_API_ENV": "dev"})
    assert Settings().es_produccion is False  # imagen de prod corriendo en local

    _entorno(monkeypatch, {"TAKAB_API_ENV": "production"})
    with pytest.raises(ConfiguracionInvalida):  # sin secretos y declarándose producción
        Settings()


def test_env_solo_acepta_los_dos_perfiles(monkeypatch) -> None:
    """Un typo (`TAKAB_API_ENV=prod`) no puede degradar a "no es producción"."""
    _entorno(monkeypatch, {**PROD_OK, "TAKAB_API_ENV": "prod"})
    with pytest.raises(ConfiguracionInvalida, match="TAKAB_API_ENV"):
        Settings()


# ---------------------------------------------------------------------------
# Criterio 2/3: un secreto RETIRADO impide arrancar
# ---------------------------------------------------------------------------


def test_produccion_con_todo_puesto_arranca(monkeypatch) -> None:
    _entorno(monkeypatch, PROD_OK)
    Settings()  # no levanta


@pytest.mark.parametrize("retirado", sorted(REQUERIDOS_EN_PRODUCCION))
def test_un_secreto_retirado_impide_arrancar(monkeypatch, retirado: str) -> None:
    """EL test del criterio 3, uno por cada requerido: se quita y tiene que reventar."""
    entorno = dict(PROD_OK)
    del entorno[f"TAKAB_API_{retirado.upper()}"]
    _entorno(monkeypatch, entorno)
    with pytest.raises(ConfiguracionInvalida) as exc:
        Settings()
    # El mensaje tiene que decir QUÉ variable falta, con el nombre que se pone
    # en el entorno del contenedor — no "validation error".
    assert f"TAKAB_API_{retirado.upper()}" in str(exc.value)


def test_el_dsn_por_defecto_no_cuenta_como_configurado(monkeypatch) -> None:
    """El caso REAL del hueco: el secreto no llega y cae al default de dev.

    Sin esto, `takab-secrets.service` podría fallar entero y la API arrancaría
    tan feliz apuntando a `takab:takab_dev@127.0.0.1:5433` — un default que en
    la propia instancia co-locada tiene un Postgres escuchando cerca.
    """
    entorno = {**PROD_OK, "TAKAB_API_DATABASE_URL": DEFAULT_DEV_DATABASE_URL}
    _entorno(monkeypatch, entorno)
    with pytest.raises(ConfiguracionInvalida, match="default de desarrollo"):
        Settings()


@pytest.mark.parametrize("prohibido", sorted(PROHIBIDOS_EN_PRODUCCION))
def test_una_credencial_de_dev_presente_en_produccion_impide_arrancar(
    monkeypatch, prohibido: str
) -> None:
    """La mitad simétrica: lo que SOLO sirve en dev no puede viajar a producción.

    `auth_dev_private_key` firma los tokens de `/dev/token`: presente en la nube
    es una fábrica de identidades de cualquier rol y cualquier tenant.
    `command_hmac_keys_json` GANA sobre Secrets Manager (settings.py), o sea que
    un mapa inline olvidado suplanta la clave real de cada gabinete.
    """
    _entorno(monkeypatch, {**PROD_OK, f"TAKAB_API_{prohibido.upper()}": "valor-de-dev"})
    with pytest.raises(ConfiguracionInvalida) as exc:
        Settings()
    assert f"TAKAB_API_{prohibido.upper()}" in str(exc.value)


def test_el_mensaje_no_filtra_el_valor_del_secreto(monkeypatch) -> None:
    """El error acaba en el journal del EC2: no puede llevar el secreto dentro.

    No es teórico: con un `ValueError` normal, pydantic lo envuelve en un
    `ValidationError` cuyo texto incluye `input_value={...}` — el diccionario de
    entrada RECORTADO, o sea un trozo del DSN CON su contraseña. Por eso el
    guardia levanta un `RuntimeError` propio, que pydantic deja pasar entero.
    """
    contrasena = "PASSWORD-QUE-NO-DEBE-SALIR"
    secreto = "clave-privada-que-no-debe-salir-en-el-log"
    _entorno(
        monkeypatch,
        {
            **PROD_OK,
            "TAKAB_API_DATABASE_URL": f"postgresql+psycopg://u:{contrasena}@h:5432/takab",
            "TAKAB_API_AUTH_DEV_PRIVATE_KEY": secreto,
        },
    )
    with pytest.raises(ConfiguracionInvalida) as exc:
        Settings()
    texto = str(exc.value)
    assert secreto not in texto
    assert contrasena not in texto
    assert "input_value" not in texto  # el envoltorio de pydantic, que sí lo imprimiría


def test_los_campos_declarados_existen_de_verdad(monkeypatch) -> None:
    """Anti-podredumbre: un campo renombrado no puede dejar la regla en un no-op.

    El guardia lee los campos con `getattr(self, campo, "")`. Si mañana alguien
    renombra `auth_dev_private_key`, esa entrada pasaría a leer "" para siempre y
    la prohibición se apagaría sin que nada se pusiera rojo.
    """
    campos = set(Settings.model_fields)
    declarados = set(REQUERIDOS_EN_PRODUCCION) | set(PROHIBIDOS_EN_PRODUCCION)
    assert declarados <= campos, f"campos declarados que ya no existen: {declarados - campos}"


# ---------------------------------------------------------------------------
# Anclaje: la señal de producción existe en el camino de despliegue REAL
# ---------------------------------------------------------------------------


def _vars_del_despliegue() -> set[str]:
    """Nombres `TAKAB_API_*` que el despliegue REAL escribe hoy.

    Dos ficheros porque son dos mitades: `deploy.sh` escribe `cloud.env` (nada
    secreto) y `takab-secrets.sh` materializa los secretos desde Secrets Manager
    a tmpfs en el arranque. El fallo que este guardia caza es justo que la
    segunda mitad no llegue.
    """
    nombres: set[str] = set()
    for fichero in ("deploy.sh", "takab-secrets.sh"):
        texto = (REPO_ROOT / "deploy" / "cloud" / fichero).read_text(encoding="utf-8")
        nombres |= set(re.findall(r"TAKAB_API_([A-Z0-9_]+)=", texto))
    return nombres


def test_el_despliegue_de_hoy_sobrevive_al_guardia() -> None:
    """Nadie puede introducir un guardia que deje la nube sin arrancar.

    Exigir un secreto que el camino de despliegue NO inyecta convierte el
    siguiente `make cloud-deploy` en un crash-loop. Este test compara las dos
    listas contra los ficheros reales, así que el error se ve aquí y no en el
    EC2.
    """
    del_despliegue = _vars_del_despliegue()
    faltan = {c.upper() for c in REQUERIDOS_EN_PRODUCCION} - del_despliegue
    assert not faltan, (
        f"REQUERIDOS_EN_PRODUCCION exige {sorted(faltan)}, y ni deploy.sh ni "
        "takab-secrets.sh lo inyectan: el próximo despliegue no arrancaría"
    )


def test_el_despliegue_de_hoy_no_lleva_credenciales_de_dev() -> None:
    """El espejo: si deploy.sh empezara a inyectar un PROHIBIDO, saldría en rojo aquí."""
    colados = {c.upper() for c in PROHIBIDOS_EN_PRODUCCION} & _vars_del_despliegue()
    assert not colados, (
        f"el camino de despliegue inyecta {sorted(colados)}, que son credenciales "
        "de DESARROLLO: o se quita de deploy.sh, o el guardia impedirá arrancar"
    )


def test_el_despliegue_de_hoy_activa_el_perfil_de_produccion() -> None:
    """Y el guardia tiene que ENCENDERSE con lo que el despliegue pone.

    Sin esto, afinar los marcadores para arreglar un test podría apagar el
    guardia entero en la nube sin que nada se quejara.
    """
    del_despliegue = _vars_del_despliegue()
    assert "BUILD_SHA" in del_despliegue
    assert {m.upper() for m in MARCADORES_DE_NUBE} & del_despliegue, (
        "el despliegue no escribe ni un MARCADOR_DE_NUBE: `es_produccion` daría "
        "False en la nube y todo este fichero sería decorativo"
    )


def test_el_deploy_real_habilita_el_pool_de_ocupantes() -> None:
    """[T-2.99] El pool de OCUPANTES tiene que llegar al despliegue, o nadie entra.

    El defecto que cierra este test: `deploy.sh` cableaba el pool principal
    (issuer/audience/jwks) y NUNCA el de ocupantes. Con `auth_occupants_issuer`
    vacío, `decode_verify_any` ni siquiera mira el segundo pool —cae al
    `decode_verify` del principal— y el id_token de CUALQUIER ocupante muere con
    `invalid token`: 401 en `/me`, la app se queda en la pantalla de login y el
    mensaje no dice por qué. El pool existía en Terraform desde T-2.02 y la app
    lo apuntaba desde `mobile/.env`; lo único que faltaba eran tres líneas.

    Por qué no lo vio ningún test: `api/tests/api/conftest.py` acuña los tokens
    de los DOS pools contra el mismo JWKS inline, así que el dual-issuer siempre
    tuvo issuer configurado en la suite. El hueco vivía en el camino de
    despliegue, que es justo lo que estos anclajes miran.
    """
    faltan = {
        "AUTH_OCCUPANTS_ISSUER",
        "AUTH_OCCUPANTS_AUDIENCE",
        "AUTH_OCCUPANTS_JWKS_URL",
    } - _vars_del_despliegue()
    assert not faltan, (
        f"el camino de despliegue no inyecta {sorted(faltan)}: el pool de ocupantes "
        "queda DESHABILITADO en la nube y ningún ocupante puede iniciar sesión"
    )


def test_el_deploy_real_inyecta_la_senal_de_produccion() -> None:
    """Sin este anclaje el guardia es fail-open: si `deploy.sh` dejara de poner
    `TAKAB_API_BUILD_SHA`, `es_produccion` daría False en la nube y todo lo de
    arriba se volvería decorativo, en silencio y sin que nada se pusiera rojo.
    """
    deploy = (REPO_ROOT / "deploy" / "cloud" / "deploy.sh").read_text(encoding="utf-8")
    assert re.search(r"^TAKAB_API_BUILD_SHA=\S", deploy, re.M), (
        "deploy/cloud/deploy.sh ya no inyecta TAKAB_API_BUILD_SHA: la señal de "
        "producción de Settings.es_produccion se quedó sin fuente y el guardia "
        "de secretos no se activaría en la nube."
    )
