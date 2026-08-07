"""T-2.71 · POST/GET /maintenance-windows: silenciar alarmas de OPERACIÓN.

La superficie más sensible que este proyecto ha abierto después de la de
actuadores. Abrir una ventana no mueve un relé, pero **apaga la vigilancia de un
edificio**: si esta pantalla se equivoca, el fallo no se ve — que es la firma de
los quince mecanismos que esta fase encontró callando en verde.

Lo que se mide aquí, y por qué:

- **La frontera multi-tenant es el ORIGEN de los nombres de alarma.** Las alarmas
  de CloudWatch se identifican por nombre y NO llevan dimensión de tenant. Si el
  cuerpo de la petición pudiera traerlos, un tenant silenciaría los del vecino —
  o los de plataforma. Se mide que un ``alarm_names`` hostil en el body **no
  llega a AWS**.
- **El vencimiento no depende de nadie.** ``active`` se deriva por predicado SQL;
  una fila con ``starts_at`` en el pasado sale ``false`` sin que nadie la cierre.
- **PUBLICADO ≠ ENTREGADO.** El acuse cuenta lo que quedó silenciado de verdad.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers import maintenance
from takab_api.routers.maintenance import get_mute_client
from takab_api.routers.maintenance import router as maintenance_router

THING = "gw-mw-test-a"
GW_A = "7d100000-0000-0000-0000-0000000001aa"
GW_MUDO = "7d100000-0000-0000-0000-0000000001bb"  # sin iot_thing
GW_B = "7d100000-0000-0000-0000-0000000001cc"  # tenant B
THING_B = "gw-mw-test-b"

_OFFLINE = f"takab-dev-gateway-offline-{THING}"
_MUDO = f"takab-dev-sensor-mudo-{THING}"


class _AwsRechazo(Exception):
    """Forma de un ``botocore.exceptions.ClientError``: AWS CONTESTÓ rechazando."""

    def __init__(self, status: int = 403, code: str = "AccessDeniedException") -> None:
        super().__init__(code)
        self.response = {
            "Error": {"Code": code, "Message": "not authorized"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }


class _FakeCW:
    """CloudWatch de mentira que RECUERDA todo lo que se le pidió.

    Que guarde las llamadas no es comodidad: es la única forma de medir que un
    nombre hostil del body no viaja. Un test que solo mirase el 201 no lo vería.

    ``falla_en`` rompe UN paso concreto de la secuencia (``put``/``get``/
    ``describe``) para poder medir el ÉXITO PARCIAL: la llamada que silencia
    llegó y la que lo comprueba no.
    """

    def __init__(
        self,
        *,
        existing: set[str] | None = None,
        falla_en: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.existing = {_OFFLINE, _MUDO} if existing is None else existing
        self.falla_en = falla_en
        self.error = error or ConnectionError("la red se cortó a mitad de la llamada")
        self.puts: list[dict] = []
        self.deleted: list[str] = []

    def put_alarm_mute_rule(self, **kw: object) -> dict:
        self.puts.append(dict(kw))
        if self.falla_en == "put":
            raise self.error
        return {}

    def get_alarm_mute_rule(self, **_kw: object) -> dict:
        if self.falla_en == "get":
            raise self.error
        put = self.puts[-1]
        return {"Name": put["Name"], "MuteTargets": dict(put["MuteTargets"])}  # type: ignore[arg-type]

    def delete_alarm_mute_rule(self, **kw: object) -> dict:
        if self.falla_en == "delete":
            # Antes de apuntar nada: si el borrado falla, NO se borró.
            raise self.error
        self.deleted.append(str(kw["AlarmMuteRuleName"]))
        return {}

    def describe_alarms(self, **kw: object) -> dict:
        if self.falla_en == "describe":
            raise self.error
        pedidas = list(kw.get("AlarmNames", []))  # type: ignore[arg-type]
        return {"MetricAlarms": [{"AlarmName": n} for n in pedidas if n in self.existing]}

    @property
    def targets(self) -> list[str]:
        """Todo nombre que alguna vez viajó hacia AWS."""
        return [n for p in self.puts for n in p["MuteTargets"]["AlarmNames"]]


@pytest.fixture
def cw() -> _FakeCW:
    return _FakeCW()


@pytest.fixture
def app(cw: _FakeCW) -> FastAPI:
    application = create_app()
    application.include_router(maintenance_router)
    application.dependency_overrides[get_mute_client] = lambda: cw
    return application


@pytest.fixture
async def gateways(base_data) -> None:
    """Tres gabinetes: uno comandable (A), uno sin ``iot_thing`` (A) y uno de B."""
    engine = get_engine()
    async with engine.begin() as conn:
        for gid, tid, sid, serial, thing in (
            (GW_A, au.DB_TENANT_PRIV, au.DB_SITE_PRIV, "SER-MW-A", THING),
            (GW_MUDO, au.DB_TENANT_PRIV, au.DB_SITE_PRIV, "SER-MW-M", None),
            (GW_B, au.DB_TENANT_PRIV2, au.DB_SITE_PRIV2, "SER-MW-B", THING_B),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                    "VALUES (:g, :t, :s, :ser, :thing) ON CONFLICT DO NOTHING"
                ),
                {"g": gid, "t": tid, "s": sid, "ser": serial, "thing": thing},
            )
    yield
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE maintenance_windows CASCADE"))
        await conn.execute(text("DELETE FROM gateways WHERE serial LIKE 'SER-MW-%'"))


def _token(role: str = "tenant_admin", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


def _body(**over: object) -> dict:
    base = {
        "scope": "gateway",
        "gateway_id": GW_A,
        "duration_s": 900,
        "reason": "cambio del cable de red del Shake",
    }
    return {**base, **over}


# --- 1. El camino feliz, y el acuse -------------------------------------------


async def test_abrir_una_ventana_silencia_las_dos_alarmas_del_gabinete(client, gateways, cw):
    r = await client.post("/maintenance-windows", json=_body(), headers=_token())
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["active"] is True
    assert b["scope"] == "gateway"
    assert sorted(b["alarm_names"]) == sorted([_MUDO, _OFFLINE])
    assert (b["requested"], b["silenced"], b["missing"]) == (2, 2, 0)
    assert b["mute_rule"] == f"takab-dev-mw-{b['window_id']}"
    # Y la regla que viajó lleva duración + una expresión de UNA sola vez.
    (put,) = cw.puts
    assert put["Rule"]["Schedule"]["Duration"] == "PT15M"
    assert put["Rule"]["Schedule"]["Expression"].startswith("at(")


async def test_el_fin_de_la_ventana_lo_dice_el_servidor_no_el_navegador(client, gateways):
    """``ends_at`` = ``starts_at`` + duración, calculado donde está el reloj bueno.
    El banner no resta relojes (misma disciplina que ``version_age_s``, T-2.69)."""
    r = await client.post("/maintenance-windows", json=_body(duration_s=1800), headers=_token())
    b = r.json()
    starts = datetime.fromisoformat(b["starts_at"])
    ends = datetime.fromisoformat(b["ends_at"])
    assert ends - starts == timedelta(seconds=1800)
    # `at()` tiene granularidad de minuto: el arranque cae en un minuto exacto.
    assert (starts.second, starts.microsecond) == (0, 0)


async def test_un_gabinete_sin_iot_thing_no_silencia_nada_y_lo_dice(client, gateways, cw):
    """ "No había alarma que silenciar" NO es "no se silenció". Colapsarlos es la
    mentira que T-2.48 cerró en el simulacro; aquí sería peor, porque la pantalla
    diría que una vigilancia está apagada cuando nunca existió."""
    r = await client.post("/maintenance-windows", json=_body(gateway_id=GW_MUDO), headers=_token())
    assert r.status_code == 201, r.text
    b = r.json()
    assert (b["requested"], b["silenced"], b["missing"]) == (0, 0, 0)
    assert b["alarm_names"] == []
    assert b["mute_rule"] is None
    assert cw.puts == [], "se creó una mute rule sin un solo objetivo"


async def test_el_acuse_no_infla_lo_que_de_verdad_quedo_mudo(client, gateways, cw):
    """El gabinete existe pero no está en ``paged_gateways``: sus alarmas no se
    crearon nunca. El ``PutAlarmMuteRule`` devuelve 200 igual."""
    cw.existing = {_OFFLINE}  # solo una de las dos existe
    r = await client.post("/maintenance-windows", json=_body(), headers=_token())
    b = r.json()
    assert (b["requested"], b["silenced"], b["missing"]) == (2, 1, 1)
    assert b["missing_names"] == [_MUDO]


# --- 2. La frontera: los nombres se DERIVAN, jamás se aceptan -------------------


async def test_un_alarm_names_hostil_en_el_body_jamas_llega_a_aws(client, gateways, cw):
    """El ataque exacto que el diseño cierra por construcción: las alarmas de
    CloudWatch no llevan tenant, así que un nombre aceptado del body silenciaría
    la vigilancia del vecino — o la de plataforma, que es peor.

    Se rechaza RUIDOSAMENTE (422), no se ignora en silencio: un cliente que crea
    que está eligiendo qué callar tiene que enterarse de que no puede."""
    hostiles = [
        "takab-dev-gateway-retirado-sigue-reportando",
        "takab-dev-dlq-telemetry",
        "takab-dev-iot-rule-errors",
        f"takab-dev-gateway-offline-{THING_B}",
    ]
    r = await client.post(
        "/maintenance-windows",
        json=_body(alarm_names=hostiles, mute_rule="pwn", silenced=99),
        headers=_token(),
    )
    assert r.status_code == 422, r.text
    assert cw.puts == []


@pytest.mark.parametrize(
    "campo", ["alarm_names", "mute_rule", "silenced", "requested", "starts_at", "tenant_id"]
)
async def test_ningun_campo_del_acuse_se_acepta_del_cliente(client, gateways, cw, campo):
    """Derivar en vez de enumerar (patrón #2): en vez de listar los campos
    peligrosos uno a uno en el código, el modelo los prohíbe TODOS y este test
    barre los que hoy existen. Un campo nuevo del acuse nace cerrado."""
    r = await client.post("/maintenance-windows", json=_body(**{campo: "x"}), headers=_token())
    assert r.status_code == 422, r.text
    assert cw.puts == []


async def test_un_tenant_no_puede_abrir_ventana_sobre_el_gabinete_de_otro(client, gateways, cw):
    """RLS: el gabinete de B sencillamente no existe para A. 404, no 403 — no se
    confirma la existencia de inventario ajeno."""
    r = await client.post("/maintenance-windows", json=_body(gateway_id=GW_B), headers=_token())
    assert r.status_code == 404, r.text
    assert cw.puts == []


async def test_un_tenant_no_ve_las_ventanas_de_otro(client, gateways):
    await client.post("/maintenance-windows", json=_body(), headers=_token())
    r = await client.get("/maintenance-windows", headers=_token(tenant=au.DB_TENANT_PRIV2))
    assert r.status_code == 200
    assert r.json()["items"] == []


# --- 2b. Quién OPERA no es a quién PERTENECE lo intervenido ---------------------
#
# La regla de oro 5 pide `tenant_id` en toda tabla de negocio y RLS default-deny,
# y remata: "un test que intente cruzar tenants DEBE fallar". La ventana se
# archivaba bajo el tenant del OPERADOR, y eso rompe las dos direcciones a la vez:
# el dueño del edificio cuyas alarmas quedan mudas no la ve, y un tenant ajeno sí
# la ve y puede cerrarla — o sea, reabrir de golpe la vigilancia de un edificio
# que no es suyo, o creer que las alarmas mudas son las suyas.
#
# El matiz que hace que esto NO se arregle prohibiendo el cruce: un
# `takab_superadmin` interviene gabinetes de tenants ajenos LEGÍTIMAMENTE. Lo que
# hay que separar no es el permiso, es el DUEÑO del registro.


@pytest.fixture
async def grant_meta_de_A_sobre_B(base_data):
    """Grant de METADATOS de A sobre B (T-1.73): A VE el inventario de B.

    Es el caso que demuestra que la RLS sola no bastaba: `gateways_read` incluye
    `app_can_view_meta`, así que el `SELECT` del que se derivan los nombres de
    alarma DEVUELVE el gabinete ajeno.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO visibility_grants (grantee_tenant_id, target_tenant_id, "
                "can_view_metadata, created_by) VALUES (:a, :b, true, :u) "
                "ON CONFLICT DO NOTHING"
            ),
            {"a": au.DB_TENANT_PRIV, "b": au.DB_TENANT_PRIV2, "u": str(uuid.uuid4())},
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM visibility_grants WHERE grantee_tenant_id = :a"),
            {"a": au.DB_TENANT_PRIV},
        )


async def test_la_ventana_se_archiva_bajo_el_DUENO_del_gabinete_no_bajo_quien_opera(
    client, gateways, cw
):
    """Un ``takab_superadmin`` (tenant de plataforma) interviene el gabinete de B.
    La intervención es legítima; el registro es de B, porque son SUS alarmas las
    que quedan mudas."""
    r = await client.post(
        "/maintenance-windows",
        json=_body(gateway_id=GW_B),
        headers=_token("takab_superadmin", tenant=au.DB_TENANT_PRIV),
    )
    assert r.status_code == 201, r.text
    b = r.json()
    assert sorted(cw.targets) == sorted(
        [f"takab-dev-gateway-offline-{THING_B}", f"takab-dev-sensor-mudo-{THING_B}"]
    )
    assert b["tenant_id"] == au.DB_TENANT_PRIV2, (
        "la ventana quedó archivada bajo el tenant del OPERADOR: el dueño del edificio "
        "cuyas alarmas están mudas no la ve, y un tenant ajeno sí"
    )

    # 1. El dueño del edificio la VE: es el criterio 2 de la ficha ("la consola lo
    #    dice mientras dure") aplicado a quien de verdad se queda sin vigilancia.
    suyas = await client.get("/maintenance-windows", headers=_token(tenant=au.DB_TENANT_PRIV2))
    assert [i["window_id"] for i in suyas.json()["items"]] == [b["window_id"]]

    # 2. El tenant del operador NO la ve...
    ajenas = await client.get("/maintenance-windows", headers=_token(tenant=au.DB_TENANT_PRIV))
    assert [i["window_id"] for i in ajenas.json()["items"]] == []

    # 3. ...ni puede cerrarla: cerrar es DESILENCIAR alarmas de otro edificio.
    cierre = await client.post(
        f"/maintenance-windows/{b['window_id']}/close",
        json={},
        headers=_token(tenant=au.DB_TENANT_PRIV),
    )
    assert cierre.status_code == 409, cierre.text
    assert cw.deleted == [], "un tenant ajeno borró la mute rule de un edificio que no es suyo"


async def test_el_rastro_de_la_ventana_es_del_dueno_y_dice_quien_la_abrio(client, gateways):
    """La bitácora tiene que quedar donde el afectado pueda leerla, y aun así
    conservar quién intervino: son dos hechos distintos y ninguno sustituye al
    otro (`tenant_id` = a quién pertenece; `meta.operator_*` = quién operó)."""
    r = await client.post(
        "/maintenance-windows",
        json=_body(gateway_id=GW_B),
        headers=_token("takab_superadmin", tenant=au.DB_TENANT_PRIV),
    )
    wid = r.json()["window_id"]
    engine = get_engine()
    async with engine.begin() as conn:
        fila = (
            (
                await conn.execute(
                    text(
                        "SELECT tenant_id, actor, meta FROM audit_log "
                        "WHERE object = :o ORDER BY ts DESC LIMIT 1"
                    ),
                    {"o": f"maintenance_window:{wid}"},
                )
            )
            .mappings()
            .one()
        )
    assert str(fila["tenant_id"]) == au.DB_TENANT_PRIV2, (
        "el rastro de las alarmas mudas de B quedó bajo el tenant de quien operó: "
        "el afectado no puede auditarlo"
    )
    assert fila["meta"]["operator_tenant_id"] == au.DB_TENANT_PRIV
    assert fila["meta"]["operator_role"] == "takab_superadmin"


async def test_VER_el_inventario_ajeno_no_da_derecho_a_callar_sus_alarmas(
    client, gateways, cw, grant_meta_de_A_sobre_B
):
    """El cruce que DEBE fallar (regla de oro 5).

    Con un grant de metadatos, el `tenant_admin` de A **ve** el gabinete de B: la
    RLS lo deja pasar, y por tanto la RLS sola nunca fue la frontera de esta
    superficie. Ver inventario ajeno es un permiso de LECTURA; apagar su
    vigilancia es un acto sobre el edificio de otro.
    """
    r = await client.post(
        "/maintenance-windows", json=_body(gateway_id=GW_B), headers=_token("tenant_admin")
    )
    assert r.status_code == 404, r.text
    assert cw.puts == [], "un tenant silenció las alarmas del gabinete de otro"


async def test_el_grant_de_metadatos_de_verdad_deja_VER_el_gabinete_ajeno(
    client, gateways, grant_meta_de_A_sobre_B
):
    """No-vacuidad del anterior: sin esto, un 404 podría venir de que el grant no
    existe (y el test no mediría el cruce, sino la ausencia de datos)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("SET ROLE takab_app"))
        await conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": au.DB_TENANT_PRIV}
        )
        await conn.execute(text("SELECT set_config('app.role', 'tenant_admin', true)"))
        visto = (
            await conn.execute(
                text("SELECT gateway_id FROM gateways WHERE gateway_id = CAST(:g AS uuid)"),
                {"g": GW_B},
            )
        ).one_or_none()
        await conn.execute(text("RESET ROLE"))
    assert visto is not None, "el grant no llegó a aplicarse: el test del cruce estaría vacío"


# --- 3. Rol: quién puede apagar qué vigilancia ---------------------------------


@pytest.mark.parametrize("role", ["soc_operator", "gov_operator", "inspector", "building_admin"])
async def test_roles_sin_la_accion_reciben_403(client, gateways, role, cw):
    r = await client.post("/maintenance-windows", json=_body(), headers=_token(role))
    assert r.status_code == 403
    assert cw.puts == []


async def test_una_ventana_de_plataforma_es_solo_del_dueno_de_la_plataforma(client, gateways, cw):
    """``ec2_*`` no tiene dueño de cliente: apagarlas es un acto de plataforma,
    mismo criterio que ``manage_tenants``/``manage_visibility``."""
    cuerpo = {"scope": "platform", "duration_s": 900, "reason": "ensayo de restore G-09"}
    r = await client.post("/maintenance-windows", json=cuerpo, headers=_token("tenant_admin"))
    assert r.status_code == 403
    assert cw.puts == []

    cw.existing = {"takab-dev-ec2-status-check", "takab-dev-ec2-cpu-sostenida"}
    r = await client.post("/maintenance-windows", json=cuerpo, headers=_token("takab_superadmin"))
    assert r.status_code == 201, r.text
    b = r.json()
    assert sorted(b["alarm_names"]) == [
        "takab-dev-ec2-cpu-sostenida",
        "takab-dev-ec2-status-check",
    ]
    assert b["tenant_id"] is None and b["gateway_id"] is None


# --- 4. Los topes: nada de ventanas eternas ni sin dueño ------------------------


@pytest.mark.parametrize("duration", [60, 299, 4 * 3600 + 60, 15 * 24 * 3600])
async def test_una_duracion_fuera_de_rango_se_rechaza(client, gateways, duration, cw):
    r = await client.post("/maintenance-windows", json=_body(duration_s=duration), headers=_token())
    assert r.status_code == 422, r.text
    assert cw.puts == []


@pytest.mark.parametrize("reason", ["", "   ", "corto"])
async def test_una_ventana_sin_motivo_escrito_se_rechaza(client, gateways, reason, cw):
    """El modo de fallo de esta función no es técnico: alguien silencia "para que
    no moleste" y el edificio deja de contar que se queda ciego en cada
    despliegue. Una ventana sin motivo es una alarma apagada sin dueño."""
    r = await client.post("/maintenance-windows", json=_body(reason=reason), headers=_token())
    assert r.status_code == 422, r.text
    assert cw.puts == []


# --- 5. Vencimiento: no depende de que nada siga vivo ---------------------------


async def test_una_ventana_vencida_deja_de_estar_activa_sin_que_nadie_la_cierre(client, gateways):
    """El criterio 3 de la ficha, medido: se inserta una fila cuya ventana YA
    pasó, sin tocar ``closed_at``, y ``active`` sale false. No hay worker de
    cierre que pueda morir, porque no hay worker."""
    engine = get_engine()
    wid = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO maintenance_windows (window_id, tenant_id, gateway_id, scope, "
                "opened_by, reason, duration_s, starts_at) VALUES (:w, :t, :g, 'gateway', :u, "
                "'ventana vencida de prueba', 900, :s)"
            ),
            {
                "w": wid,
                "t": au.DB_TENANT_PRIV,
                "g": GW_A,
                "u": str(uuid.uuid4()),
                "s": datetime.now(UTC) - timedelta(hours=3),
            },
        )
    # La lista de ACTIVAS ya no la incluye: eso solo puede pasar si `active` se
    # derivó del reloj de la transacción, porque nadie la tocó.
    activas = await client.get("/maintenance-windows?active=true", headers=_token())
    assert [i["window_id"] for i in activas.json()["items"]] == []

    todas = await client.get("/maintenance-windows?active=false", headers=_token())
    assert todas.status_code == 200
    filas = [i for i in todas.json()["items"] if i["window_id"] == wid]
    assert len(filas) == 1, "la fila existe: lo que cambió es su `active` derivado"
    assert filas[0]["active"] is False
    assert filas[0]["closed_at"] is None, (
        "nadie la cerró: `active` tiene que ser un PREDICADO derivado, no una columna"
    )


async def test_cerrar_antes_de_tiempo_borra_la_regla_y_reabre_las_alarmas(client, gateways, cw):
    """``DeleteAlarmMuteRule`` desilencia EN EL ACTO y, si alguna alarma quedó en
    ALARM, sus acciones disparan. Cerrar antes hace que el correo pendiente SALGA."""
    b = (await client.post("/maintenance-windows", json=_body(), headers=_token())).json()
    r = await client.post(f"/maintenance-windows/{b['window_id']}/close", json={}, headers=_token())
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    assert r.json()["closed_at"] is not None
    assert cw.deleted == [b["mute_rule"]]


async def test_cerrar_dos_veces_no_reescribe_el_registro(client, gateways, cw):
    b = (await client.post("/maintenance-windows", json=_body(), headers=_token())).json()
    primera = await client.post(
        f"/maintenance-windows/{b['window_id']}/close", json={}, headers=_token()
    )
    segunda = await client.post(
        f"/maintenance-windows/{b['window_id']}/close", json={}, headers=_token()
    )
    assert segunda.status_code == 409, segunda.text
    assert segunda.json()["detail"]
    assert primera.json()["closed_at"] is not None


# --- 6. Rastro: quién apagó qué, cuánto y por qué --------------------------------


async def test_abrir_una_ventana_deja_rastro_en_la_bitacora(client, gateways):
    r = await client.post("/maintenance-windows", json=_body(), headers=_token())
    wid = r.json()["window_id"]
    engine = get_engine()
    async with engine.begin() as conn:
        fila = (
            (
                await conn.execute(
                    text(
                        "SELECT verb, object, meta FROM audit_log "
                        "WHERE object = :o ORDER BY ts DESC LIMIT 1"
                    ),
                    {"o": f"maintenance_window:{wid}"},
                )
            )
            .mappings()
            .one()
        )
    assert fila["verb"] == "maintenance_window_open"
    meta = fila["meta"]
    assert meta["reason"] == "cambio del cable de red del Shake"
    assert meta["duration_s"] == 900
    assert meta["silenced"] == 2 and meta["requested"] == 2
    assert sorted(meta["alarm_names"]) == sorted([_MUDO, _OFFLINE])


async def test_cerrar_tambien_deja_rastro(client, gateways):
    b = (await client.post("/maintenance-windows", json=_body(), headers=_token())).json()
    await client.post(f"/maintenance-windows/{b['window_id']}/close", json={}, headers=_token())
    engine = get_engine()
    async with engine.begin() as conn:
        verbos = [
            r[0]
            for r in (
                await conn.execute(
                    text("SELECT verb FROM audit_log WHERE object = :o ORDER BY ts"),
                    {"o": f"maintenance_window:{b['window_id']}"},
                )
            ).all()
        ]
    assert verbos == ["maintenance_window_open", "maintenance_window_close"]


# --- 7. Sin AWS configurado: la ventana NO miente --------------------------------


async def test_sin_cliente_de_cloudwatch_la_ventana_declara_cero_silenciadas(app, client, gateways):
    """En local no hay CloudWatch. La fila se crea igual —el registro vale— pero
    el acuse dice ``0/2``, que es la verdad. Declarar "silenciado" sin haber
    llamado a nadie sería el fallo exacto que esta tarea existe para no cometer."""
    app.dependency_overrides[get_mute_client] = lambda: None
    r = await client.post("/maintenance-windows", json=_body(), headers=_token())
    assert r.status_code == 201, r.text
    b = r.json()
    assert (b["requested"], b["silenced"], b["missing"]) == (2, 0, 2)
    assert b["mute_rule"] is None


async def test_si_el_acuse_no_se_pudo_LEER_la_fila_no_declara_la_vigilancia_viva(
    app, client, gateways
):
    """El éxito PARCIAL: el ``PutAlarmMuteRule`` llegó y la relectura no.

    Las alarmas están MUDAS. Reportarlo como ``0/2`` con ``mute_rule = NULL`` era
    la peor de las dos mentiras posibles: la consola afirma que la vigilancia
    sigue viva **cuando está apagada**, y el botón REABRIR VIGILANCIA se queda sin
    nada que borrar durante hasta 4 h.
    """
    cw = _FakeCW(falla_en="get")
    app.dependency_overrides[get_mute_client] = lambda: cw
    r = await client.post("/maintenance-windows", json=_body(), headers=_token())
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["mute_rule"] == f"takab-dev-mw-{b['window_id']}", (
        "se perdió el nombre de la regla ya aplicada: REABRIR VIGILANCIA es un no-op"
    )
    assert b["mute_verified"] is False, "un acuse que no se pudo leer no puede pasar por medido"
    assert (b["requested"], b["silenced"], b["missing"]) == (2, 2, 0)

    # Y el botón REABRIR de verdad desilencia, que es lo que estaba roto.
    cierre = await client.post(
        f"/maintenance-windows/{b['window_id']}/close", json={}, headers=_token()
    )
    assert cierre.status_code == 200, cierre.text
    assert cw.deleted == [b["mute_rule"]]


async def test_si_describe_alarms_falla_tampoco_se_pierde_la_regla(app, client, gateways):
    cw = _FakeCW(falla_en="describe")
    app.dependency_overrides[get_mute_client] = lambda: cw
    b = (await client.post("/maintenance-windows", json=_body(), headers=_token())).json()
    assert b["mute_rule"] == f"takab-dev-mw-{b['window_id']}"
    assert b["mute_verified"] is False


async def test_un_rechazo_definitivo_de_aws_declara_cero_y_no_inventa_una_regla(
    app, client, gateways
):
    """El error simétrico: AWS contestó 403, la regla NO se creó y las alarmas
    SUENAN. Aquí ``0/2`` sí es la verdad medida, y ``mute_verified`` lo dice."""
    cw = _FakeCW(falla_en="put", error=_AwsRechazo(403))
    app.dependency_overrides[get_mute_client] = lambda: cw
    r = await client.post("/maintenance-windows", json=_body(), headers=_token())
    assert r.status_code == 201, r.text
    b = r.json()
    assert (b["requested"], b["silenced"], b["missing"]) == (2, 0, 2)
    assert b["mute_rule"] is None
    assert b["mute_verified"] is True


async def test_el_camino_feliz_sigue_declarandose_MEDIDO(client, gateways, cw):
    """No-vacuidad de ``mute_verified``: si fuera siempre ``False``, los tres de
    arriba pasarían sin medir nada."""
    b = (await client.post("/maintenance-windows", json=_body(), headers=_token())).json()
    assert b["mute_verified"] is True


async def test_si_no_se_puede_dejar_CONSTANCIA_del_silencio_se_deshace(
    app, client, gateways, cw, monkeypatch
):
    """La fila y el silencio son una sola operación, y la fila puede fallar.

    Si el ``UPDATE`` del acuse revienta, la transacción se revierte y la fila
    desaparece — pero la mute rule ya está en AWS. Eso es exactamente lo que esta
    tarea existe para no dejar: alarmas mudas sin un registro que lo cuente y sin
    nadie que sepa el nombre de la regla. La única salida honesta es DESHACER.
    """
    monkeypatch.setattr(
        maintenance, "_UPDATE_ACK", text("UPDATE maintenance_windows SET columna_que_no_existe = 1")
    )
    with pytest.raises(Exception):  # noqa: B017 - cualquier fallo del UPDATE sirve
        await client.post("/maintenance-windows", json=_body(), headers=_token())
    assert cw.puts, "el silencio llegó a aplicarse"
    assert cw.deleted == [cw.puts[0]["Name"]], (
        "quedaron alarmas mudas en AWS sin ninguna fila que lo cuente"
    )
    quedan = await client.get("/maintenance-windows?active=false", headers=_token())
    assert quedan.json()["items"] == []


async def test_un_fallo_que_NUNCA_salio_de_la_maquina_declara_cero_y_no_inventa_regla(
    app, client, gateways
):
    """La tercera familia del acuse, con el signo contrario al bloqueante anterior.

    Un ``NoCredentialsError`` no es "AWS no contestó": es que la petición **ni se
    envió**. Se SABE que no hay nada mudo, así que ``0/2`` es la verdad MEDIDA y
    no hay ninguna regla que conservar. Darlo por silenciado pintaría "vigilancia
    apagada" con las alarmas sonando, y nadie iría a mirar por qué no llegan unos
    correos que sí van a llegar.
    """
    sin_credenciales = type("NoCredentialsError", (Exception,), {})("Unable to locate credentials")
    cw = _FakeCW(falla_en="put", error=sin_credenciales)
    app.dependency_overrides[get_mute_client] = lambda: cw
    r = await client.post("/maintenance-windows", json=_body(), headers=_token())
    assert r.status_code == 201, r.text
    b = r.json()
    assert (b["requested"], b["silenced"], b["missing"]) == (2, 0, 2)
    assert b["mute_rule"] is None, "se guardó el nombre de una regla que no llegó a pedirse"
    assert b["mute_verified"] is True, "esto no es una suposición: está medido"


# --- 8. El CIERRE es una AFIRMACIÓN: "la vigilancia volvió" ----------------------
#
# El simétrico exacto de lo anterior, en el otro extremo del ciclo. La apertura
# aprendió a distinguir medido de supuesto; el cierre no aprendió nada: cerraba la
# fila y luego intentaba borrar la mute rule dentro de un `try/except` que solo
# escribía un `logger.warning`. Resultado: la ventana DESAPARECE de pantalla
# —`active` pasa a false— mientras las alarmas siguen mudas hasta que expire la
# `Duration`. La consola dice que la vigilancia volvió; no volvió.
#
# Mismo principio que en la apertura: ante la duda, el estado más PELIGROSO. Aquí
# el peligroso es "sigue muda", así que cerrar solo se afirma cuando el silencio se
# deshizo de verdad — o cuando ya había vencido solo.


async def test_un_cierre_que_no_pudo_DESILENCIAR_no_declara_reabierta_la_vigilancia(
    app, client, gateways
):
    cw = _FakeCW(falla_en="delete")
    app.dependency_overrides[get_mute_client] = lambda: cw
    b = (await client.post("/maintenance-windows", json=_body(), headers=_token())).json()

    r = await client.post(f"/maintenance-windows/{b['window_id']}/close", json={}, headers=_token())
    assert r.status_code == 502, r.text

    activas = await client.get("/maintenance-windows?active=true", headers=_token())
    (fila,) = activas.json()["items"]
    assert fila["window_id"] == b["window_id"]
    assert fila["closed_at"] is None, (
        "la ventana se declaró cerrada sin haber desilenciado: la consola dice que la "
        "vigilancia volvió y el edificio sigue mudo"
    )
    assert fila["mute_rule"] == b["mute_rule"], "se perdió el nombre de la regla que sigue viva"

    # Y el reintento funciona: `DeleteAlarmMuteRule` es idempotente, así que un
    # cierre que falló no deja el registro atascado.
    cw.falla_en = None
    segunda = await client.post(
        f"/maintenance-windows/{b['window_id']}/close", json={}, headers=_token()
    )
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["closed_at"] is not None
    assert cw.deleted == [b["mute_rule"]]


async def test_sin_cliente_de_cloudwatch_no_se_puede_AFIRMAR_que_la_vigilancia_volvio(
    app, client, gateways, cw
):
    """El primo hermano callado: el ``if client is not None`` saltaba el borrado
    entero. Una ventana abierta con AWS configurado y cerrada después de apagar
    ``ops_muting`` reabría la vigilancia **solo en pantalla**."""
    b = (await client.post("/maintenance-windows", json=_body(), headers=_token())).json()
    assert b["mute_rule"], "la regla llegó a crearse: si no, este test no mediría nada"

    app.dependency_overrides[get_mute_client] = lambda: None
    r = await client.post(f"/maintenance-windows/{b['window_id']}/close", json={}, headers=_token())
    assert r.status_code == 503, r.text

    activas = await client.get("/maintenance-windows?active=true", headers=_token())
    assert [i["closed_at"] for i in activas.json()["items"]] == [None]


async def test_una_ventana_YA_VENCIDA_se_cierra_aunque_AWS_no_conteste(app, client, gateways):
    """El contrapeso, para no crear un registro imposible de cerrar.

    Vencida la fila, vencida la regla: la ``Duration`` de AWS y el ``ends_at`` de
    la fila cuentan desde el MISMO borde (``mute_start``), así que ahí no queda
    nada que desilenciar y cerrar es contabilidad honesta, no una afirmación sobre
    el presente.
    """
    engine = get_engine()
    wid = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO maintenance_windows (window_id, tenant_id, gateway_id, scope, "
                "opened_by, reason, duration_s, starts_at, mute_rule) VALUES (:w, :t, :g, "
                "'gateway', :u, 'ventana vencida con regla', 900, :s, 'takab-dev-mw-vieja')"
            ),
            {
                "w": wid,
                "t": au.DB_TENANT_PRIV,
                "g": GW_A,
                "u": str(uuid.uuid4()),
                "s": datetime.now(UTC) - timedelta(hours=3),
            },
        )
    cw = _FakeCW(falla_en="delete")
    app.dependency_overrides[get_mute_client] = lambda: cw
    r = await client.post(f"/maintenance-windows/{wid}/close", json={}, headers=_token())
    assert r.status_code == 200, r.text
    assert r.json()["closed_at"] is not None


async def test_el_cierre_que_SI_desilencia_sigue_cerrando(app, client, gateways, cw):
    """No-vacuidad de los tres de arriba: si el cierre fallara siempre, todos
    pasarían sin medir la diferencia entre desilenciar y no poder."""
    b = (await client.post("/maintenance-windows", json=_body(), headers=_token())).json()
    r = await client.post(f"/maintenance-windows/{b['window_id']}/close", json={}, headers=_token())
    assert r.status_code == 200, r.text
    assert cw.deleted == [b["mute_rule"]]


async def test_un_cierre_fallido_no_deja_rastro_de_reapertura_en_la_bitacora(app, client, gateways):
    """El rastro es parte de la misma afirmación: un `maintenance_window_close`
    escrito con las alarmas todavía mudas convierte la mentira en historia."""
    cw = _FakeCW(falla_en="delete")
    app.dependency_overrides[get_mute_client] = lambda: cw
    b = (await client.post("/maintenance-windows", json=_body(), headers=_token())).json()
    await client.post(f"/maintenance-windows/{b['window_id']}/close", json={}, headers=_token())
    engine = get_engine()
    async with engine.begin() as conn:
        verbos = [
            r[0]
            for r in (
                await conn.execute(
                    text("SELECT verb FROM audit_log WHERE object = :o ORDER BY ts"),
                    {"o": f"maintenance_window:{b['window_id']}"},
                )
            ).all()
        ]
    assert verbos == ["maintenance_window_open"]


async def test_al_releer_la_ventana_los_nombres_que_faltaron_son_los_REALES(client, gateways, cw):
    """La cifra del acuse solo se conoce al APLICAR; al releer una fila no se
    vuelve a llamar a AWS. Reconstruir QUÉ nombre faltó a partir del número —
    cogiendo N nombres de la lista— produce un dato INVENTADO que se lee como
    medido. Es la misma familia de mentira que esta tarea existe para no
    cometer, así que los nombres se guardan, no se adivinan.

    El caso se elige a propósito para que la adivinanza falle: la que NO existe
    es la PRIMERA del catálogo (`gateway_offline`), y cualquier reconstrucción
    por cola devolvería la otra.
    """
    cw.existing = {_MUDO}  # existe la de sensor mudo; NO la de gabinete offline
    creada = await client.post("/maintenance-windows", json=_body(), headers=_token())
    assert creada.json()["missing_names"] == [_OFFLINE]

    listado = await client.get("/maintenance-windows?active=true", headers=_token())
    (fila,) = listado.json()["items"]
    assert fila["missing"] == 1
    assert fila["missing_names"] == [_OFFLINE], (
        "al releer se devolvió un nombre distinto del que de verdad no se silenció"
    )
