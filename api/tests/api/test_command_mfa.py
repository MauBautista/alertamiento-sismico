"""T-2.84.b · `RO-8.c`: la constancia de MFA en el camino de comando de actuadores.

La regla de oro 8 exige «comando firmado + **MFA** + rate-limit + nonce + ack, sin
excepción» sobre la superficie que cierra válvulas de gas y mueve ascensores. De los
cinco controles, el MFA era el único sin una sola línea de prueba en ninguna capa.

**Lo primero que hubo que averiguar: qué dice de verdad el token.** La respuesta,
verificada contra la documentación de AWS y no de memoria, es *nada*:

- el *payload* por defecto del **ID token** —el que esta API verifica, ver
  `auth/tokens.py::_decode`, que exige `token_use == "id"`— es
  `sub · cognito:groups · email_verified · cognito:preferred_role · iss ·
  cognito:username · nonce · origin_jti · cognito:roles · aud · identities ·
  event_id · token_use · auth_time · exp · iat · jti · email`.
  **No lleva `amr`. No lleva `acr`.**
  (`docs.aws.amazon.com/cognito/latest/developerguide/
  amazon-cognito-user-pools-using-the-id-token.html`);
- el **access token** tampoco los lleva (misma guía, `…-using-the-access-token.html`);
- y `amr`/`acr` figuran en la tabla *Claims and scopes reference* del disparador
  *pre token generation* como `Can add? **No** · Can modify? **No** · Can suppress?
  **No**`: son de Cognito, así que **tampoco se pueden fabricar** con un Lambda
  (`…/user-pool-lambda-pre-token-generation.html`).

O sea: **un test que comprobara `amr == ["mfa"]` sería ficción** — rechazaría el 100 %
de los tokens reales, o (escrito como «si viene, que valga») no se dispararía jamás.
`auth_time` sí viaja, pero dice **cuándo** se autenticó el usuario, no **cómo**: es
frescura, no segundo factor.

**Lo que el token SÍ dice, y es lo que aquí se exige: de qué pool viene.** El `iss` va
firmado y verificado, y el pool es quien porta la política de MFA. Este proyecto tiene
**dos pools a la vez** (decisión #7, T-2.02): el principal en `mfa_configuration = "ON"`
y el de ocupantes en `"OPTIONAL"` —a propósito: el ocupante puede declinar su TOTP—.
Así que el escenario de «si algún día conviven dos pools» **no es hipotético: es hoy**.

Lo que estos tests fijan es que el rechazo del camino de comando sea **por procedencia
y no por casualidad del catálogo de roles**. Hoy un token del pool sin MFA no comanda
porque `occupant` no tiene ninguna acción de comando; el día que la tenga, la puerta se
abriría sola y en silencio. Ver `auth/mfa.py`.

**Alcance, dicho explícitamente.** El MFA protege el camino de ACTUACIÓN, no la API
entera: el check-in de vida y el voto de pánico del ocupante siguen sin exigirlo, y hay
un test que lo fija (`test_el_camino_de_vida_del_ocupante_no_queda_exigido_de_MFA`).
Exigir MFA ahí rompería el camino de vida, que es lo contrario de lo que la regla busca.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.auth.matrix import ROLE_ACTION_MATRIX
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.commands import get_publisher

pytestmark = pytest.mark.anyio

KEY = "clave-mfa-test"
THING = "gw-mfa-test"
GW_MFA = "7c600000-0000-0000-0000-0000000000f1"
SITE_MFA = "7c600000-0000-0000-0000-00000000016f"
ZONE_MFA = "7c600000-0000-0000-0000-0000000000f2"
OCC_A = "70000000-0000-0000-0000-0000000dd001"
OCC_B = "70000000-0000-0000-0000-0000000dd002"
# Mismo centro que el seed de pánico: el geofence del voto usa el geom del sitio.
SITE_LON, SITE_LAT = -98.3014, 19.0633


class _FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        self.published.append((topic, json.loads(payload)))


@pytest.fixture
def publisher() -> _FakePublisher:
    return _FakePublisher()


@pytest.fixture
def app(publisher: _FakePublisher) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_publisher] = lambda: publisher
    return application


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch):
    """Los DOS pools vivos: es la configuración real desde T-2.03."""
    monkeypatch.delenv("TAKAB_API_COMMAND_HMAC_SECRET_PREFIX", raising=False)
    monkeypatch.setenv("TAKAB_API_COMMAND_HMAC_KEYS_JSON", json.dumps({THING: KEY}))
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


@pytest.fixture
async def sitio_comandable(base_data) -> None:
    """Sitio del tenant PRIV con gabinete comandable y dos ocupantes enrolados."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(:s, :t, 'S-MFA', 'Sitio MFA', "
                "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) "
                "ON CONFLICT (site_id) DO NOTHING"
            ),
            {"s": SITE_MFA, "t": au.DB_TENANT_PRIV, "lon": SITE_LON, "lat": SITE_LAT},
        )
        await conn.execute(
            text(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (:g, :t, :s, 'SER-MFA', :thing) ON CONFLICT (gateway_id) DO NOTHING"
            ),
            {"g": GW_MFA, "t": au.DB_TENANT_PRIV, "s": SITE_MFA, "thing": THING},
        )
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name) "
                "VALUES (:z, :t, :s, 'PB') ON CONFLICT (zone_id) DO NOTHING"
            ),
            {"z": ZONE_MFA, "t": au.DB_TENANT_PRIV, "s": SITE_MFA},
        )
        for user in (OCC_A, OCC_B):
            await conn.execute(
                text(
                    "INSERT INTO user_zone_assignments "
                    "(user_id, tenant_id, site_id, zone_id, role) "
                    "VALUES (:u, :t, :s, :z, 'occupant') ON CONFLICT DO NOTHING"
                ),
                {"u": user, "t": au.DB_TENANT_PRIV, "s": SITE_MFA, "z": ZONE_MFA},
            )
        await conn.execute(
            text("DELETE FROM manual_activation_votes WHERE site_id = :s"), {"s": SITE_MFA}
        )


def _cuerpo(channel: str = "siren", action: str = "activate") -> dict:
    return {"channel": channel, "action": action, "event_id": "EVT-MFA-1"}


async def _comandar(client, token: str, **over):
    return await client.post(
        f"/sites/{SITE_MFA}/commands", json=_cuerpo(**over), headers=au.bearer(token)
    )


# ===========================================================================
# 1 · La conducta: sin constancia de MFA no se comanda un actuador
# ===========================================================================


async def test_el_camino_de_comando_rechaza_por_falta_de_constancia_de_MFA(
    client, sitio_comandable, publisher: _FakePublisher
) -> None:
    """Un token del pool `OPTIONAL` no comanda — y el motivo es la PROCEDENCIA.

    El matiz es todo el test. Hoy este token ya se cae, pero se cae porque
    `occupant` no figura en `COMMAND_ROLES`: el MFA no interviene. Exigir que el
    motivo nombre el segundo factor es exigir que el control EXISTA, en vez de
    heredarlo de una coincidencia del catálogo de roles que mañana puede cambiar.
    """
    token = au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC_A, surface="both")
    r = await _comandar(client, token)

    assert r.status_code == 403, r.text
    detalle = str(r.json().get("detail", "")).lower()
    assert "segundo factor" in detalle, (
        "el camino de comando rechazó el token, pero NO por falta de MFA: el motivo "
        f"fue {detalle!r}. Ese rechazo es un accidente del catálogo de roles "
        "(`occupant` no tiene acciones de comando hoy), no un control. La regla de "
        "oro 8 dice «sin excepción»: el rechazo tiene que salir de la procedencia "
        "del token, que es lo único que Cognito sí certifica."
    )
    assert publisher.published == [], "no puede haber salido nada al gabinete"


async def test_un_amr_forjado_no_compra_la_constancia_de_MFA(
    client, sitio_comandable, publisher: _FakePublisher
) -> None:
    """Y no se puede comprar poniéndole al token los claims que Cognito no emite.

    Es la otra mitad de la decisión de diseño: si la constancia se leyera de `amr`
    o de `acr`, bastaría con que quien acuña un token los escribiera. Cognito los
    declara **no añadibles ni modificables** justamente porque son suyos; una API
    que los creyera estaría confiando en un campo que su emisor real nunca pone.
    """
    token = au.occupant_token(
        tenant=au.DB_TENANT_PRIV,
        user_id=OCC_A,
        surface="both",
        **{"amr": ["pwd", "mfa", "otp"], "acr": "urn:mace:incommon:iap:silver"},
    )
    r = await _comandar(client, token)

    assert r.status_code == 403, r.text
    assert "segundo factor" in str(r.json().get("detail", "")).lower(), (
        "un `amr`/`acr` escrito a mano en el token abrió (o cambió el motivo de) el "
        "camino de comando. La constancia de MFA no puede leerse de un claim que el "
        "emisor real no emite y que cualquiera que acuñe el token puede inventar."
    )
    assert publisher.published == []


async def test_el_token_real_de_cognito_sin_amr_ni_acr_sigue_comandando(
    client, sitio_comandable, publisher: _FakePublisher
) -> None:
    """La guarda anti-teatro: el token REAL no lleva `amr` ni `acr`, y debe pasar.

    Sin este test, «exigir MFA» podría implementarse pidiendo un claim que Cognito
    nunca manda: la suite quedaría verde en el rechazo y la consola no podría
    comandar nada en producción. Aquí se acuña exactamente lo que el pool principal
    emite —ni un claim más— y tiene que salir un comando firmado al gabinete.
    """
    token = au.make_token("tenant_admin", tenant=au.DB_TENANT_PRIV, site_scope="*")
    r = await _comandar(client, token)

    assert r.status_code == 201, r.text
    assert len(publisher.published) == 1, "el comando del pool con MFA ON debe salir"
    assert publisher.published[0][0] == f"takab/cmd/{THING}"


# ===========================================================================
# 2 · El alcance: el camino de VIDA no queda exigido de MFA
# ===========================================================================


async def test_el_camino_de_vida_del_ocupante_no_queda_exigido_de_MFA(
    client, sitio_comandable, publisher: _FakePublisher
) -> None:
    """El ocupante —pool `OPTIONAL`, puede no tener TOTP— sigue pudiendo pedir auxilio.

    Es la excepción DECLARADA de `RO-8.c`, y está acotada por otros tres controles:
    dos votantes DISTINTOS en ventana, geofence y rate-limit por usuario. Un voto
    jamás activa. Exigirle MFA a quien está pidiendo ayuda con el edificio temblando
    invertiría el sentido de la regla de oro 8, que existe para proteger vidas.
    """
    r1 = await client.post(
        f"/sites/{SITE_MFA}/manual-activation-votes",
        json={},
        headers=au.bearer(au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC_A)),
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "counted"
    assert publisher.published == [], "un voto JAMÁS activa"

    r2 = await client.post(
        f"/sites/{SITE_MFA}/manual-activation-votes",
        json={},
        headers=au.bearer(au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC_B)),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "activated", (
        "el quórum de pánico dejó de activar la sirena. Si la guarda de MFA se "
        "extendió al voto del ocupante, el camino de vida está roto: ese token "
        "viene del pool OPTIONAL por diseño y nunca podrá traer constancia de MFA."
    )
    assert len(publisher.published) == 1, "el quórum debe firmar y publicar la sirena"


# ===========================================================================
# 3 · La clase, no el caso: quién puede comandar y quién declara su postura
# ===========================================================================

#: Roles que emite un pool SIN MFA obligatoria. Es el ancla pool→rol que impone
#: `auth/deps.py::get_claims`: el pool de ocupantes SOLO emite `occupant`, y un
#: `occupant` SOLO puede venir de ahí. Escrito literalmente y no importado del
#: código a propósito: si alguien relaja el ancla, esto tiene que enterarse.
_ROLES_SIN_MFA = frozenset({"occupant"})

#: Acciones de la matriz RBAC que mueven un actuador del edificio.
_ACCIONES_DE_ACTUADOR = ("siren_test", "self_test", "manual_activate", "siren_silence")


def test_ningun_rol_del_pool_sin_MFA_carga_una_accion_de_actuador() -> None:
    """La premisa de la que depende «el MFA está delegado al pool».

    La delegación sólo se sostiene mientras los roles que pueden comandar vivan
    todos en el pool con `mfa_configuration = "ON"`. El día que `occupant` gane
    `manual_activate` —una escalada plausible: es el rol más numeroso—, un usuario
    que declinó su TOTP podría mover un actuador y **ningún otro test del árbol se
    daría cuenta**. Esta es la valla.
    """
    con_actuador = {
        rol
        for rol in _ROLES_SIN_MFA
        if any(ROLE_ACTION_MATRIX.get(rol, {}).get(a) for a in _ACCIONES_DE_ACTUADOR)
    }
    assert con_actuador == set(), (
        f"{sorted(con_actuador)} sale de un pool de Cognito con MFA OPTIONAL y acaba "
        "de ganar una acción de actuador. La delegación del MFA al pool ya no cubre "
        "ese camino: o el rol se mueve al pool principal (MFA ON), o la acción se "
        "retira, o se declara aquí la excepción con sus controles compensatorios "
        "(como el quórum-de-2 del pánico)."
    )


# --- El censo derivado: todo handler que FIRME un comando declara su postura ---

_ROUTERS = Path(__file__).resolve().parents[2] / "src" / "takab_api" / "routers"

#: Atributo que marca a una dependencia como guarda de MFA. Se escribe literal (no
#: se importa de `auth/mfa.py`) para que el censo no pueda quedarse verde por
#: mirarse en el mismo espejo que el código que vigila.
_MARCA_GUARDA = "takab_mfa_guard"

#: Handlers que firman un comando SIN la guarda, con la razón por la que se
#: aceptan. Se compara por IGUALDAD: uno nuevo sale rojo aunque nadie lo apunte, y
#: uno que gane la guarda también (hay que borrarlo de aquí).
_EXCEPCIONES_DECLARADAS = {
    "panic_vote": (
        "Camino de VIDA (T-2.13). El votante es un `occupant` del pool con MFA "
        "OPTIONAL por diseño: exigirle segundo factor lo dejaría sin poder pedir "
        "auxilio. Acotado por quórum de 2 votantes distintos + geofence + "
        "rate-limit, y el comando es siempre `siren/activate` (cableado en el "
        "handler): no puede tocar gas ni ascensores."
    ),
    "start_drill": (
        "HUECO DECLARADO, no excepción razonada. `routers/drills.py` queda fuera "
        "del alcance de T-2.84.b (fichero de otro obrero en este árbol). Un "
        "simulacro VOCEA y suena la sirena, así que merece la misma guarda: sus "
        "roles viven hoy en el pool principal (MFA ON), de modo que la delegación "
        "se sostiene, pero NO está comprobada positivamente."
    ),
    "stop_drill": "Misma razón y mismo hueco que `start_drill`.",
}


def _es_decorador_de_ruta(dec: ast.expr) -> bool:
    f = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "router"


def _handlers_que_firman_un_comando() -> dict[str, str]:
    """{handler: módulo} derivado por AST sobre `takab_api/routers/`.

    Nadie escribe la lista: un router nuevo que llame a `issue_signed_command`
    entra solo en el censo y tiene que resolver su postura de MFA.
    """
    out: dict[str, str] = {}
    for ruta in sorted(_ROUTERS.glob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in arbol.body:
            if not isinstance(nodo, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            if not any(_es_decorador_de_ruta(d) for d in nodo.decorator_list):
                continue
            if any(
                isinstance(s, ast.Call)
                and isinstance(s.func, ast.Name)
                and s.func.id == "issue_signed_command"
                for s in ast.walk(nodo)
            ):
                out[nodo.name] = ruta.stem
    return out


def _tiene_guarda(dependant) -> bool:
    if getattr(dependant.call, _MARCA_GUARDA, False):
        return True
    return any(_tiene_guarda(d) for d in dependant.dependencies)


def test_todo_handler_que_firma_un_comando_declara_su_postura_de_MFA() -> None:
    """El censo: quien firme un comando lleva la guarda o está declarado, con razón.

    Es la diferencia entre tapar un caso y cerrar la clase. `RO-8.c` no se abrió
    porque un endpoint concreto estuviera mal: se abrió porque **nada obligaba a
    ningún endpoint a tener postura**. Un `POST` nuevo que llame a
    `issue_signed_command` cae aquí sin que nadie tenga que acordarse.
    """
    firman = _handlers_que_firman_un_comando()
    assert firman, (
        "el censo salió VACÍO. O `issue_signed_command` se renombró, o los handlers "
        "dejaron de llamarlo directamente: en cualquier caso este test se habría "
        "vuelto verde sin comprobar nada, que es justo lo que no puede pasar."
    )

    sin_guarda: set[str] = set()
    for handler, modulo in sorted(firman.items()):
        mod = importlib.import_module(f"takab_api.routers.{modulo}")
        rutas = [r for r in mod.router.routes if getattr(r.endpoint, "__name__", "") == handler]
        assert rutas, f"`{handler}` no está montado como ruta en `{modulo}.router`"
        if not all(_tiene_guarda(r.dependant) for r in rutas):
            sin_guarda.add(handler)

    assert sin_guarda == set(_EXCEPCIONES_DECLARADAS), (
        "el censo de MFA no cuadra con las excepciones declaradas.\n"
        f"  sin guarda y sin declarar: {sorted(sin_guarda - set(_EXCEPCIONES_DECLARADAS))}\n"
        f"  declarados pero YA con guarda (bórralos de la lista): "
        f"{sorted(set(_EXCEPCIONES_DECLARADAS) - sin_guarda)}\n"
        "Un handler que firma un comando de actuador o lleva `require_mfa`, o "
        "aparece arriba con la razón a la vista. Omitirlo no es una opción: la "
        "regla de oro 8 dice «sin excepción», así que las que haya se leen."
    )
