"""La cadena de acuse: quién recibió la alerta y cuánto tardó (T-5.15).

Lo que fija, en orden de importancia:

* **`simulated` NO es `delivered`, y ninguno de los dos es `sent`.** La tabla ya
  distinguía los seis estados; lo que faltaba era una lectura que no los
  colapsara. `delivered` sale de `delivered_at IS NOT NULL` y de nada más: es la
  única columna que afirma que alguien lo tuvo en la mano.
* **Quien no recibió no tiene latencia, y eso NO es un cero.** Un cero se lee
  «llegó al instante», que es lo contrario de «no llegó».
* **El destinatario sale enmascarado**, y la URL de un webhook sale sin ruta:
  esa ruta es la credencial.
* **Aislamiento entre clientes**: el incidente del vecino da 404, no una lista
  vacía — una lista vacía confirmaría que el incidente existe.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers.notify_chain import router as chain_router


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(chain_router)
    return application


def _token(role: str = "soc_operator", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _sql(sql: str, **p):
    engine = get_engine()
    async with engine.begin() as conn:
        r = await conn.execute(text(sql), p)
        return r.fetchall() if r.returns_rows else []


async def _incidente(*, tenant: str = au.DB_TENANT_PRIV, site: str = au.DB_SITE_PRIV) -> str:
    iid = str(uuid.uuid4())
    await _sql(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at,"
        " severity, state, trigger)"
        " VALUES (:i, :e, :t, :s, now() - interval '10 minutes', 'critical', 'open', 'sasmex')",
        i=iid,
        e=str(uuid.uuid4()),
        t=tenant,
        s=site,
    )
    return iid


async def _job(incidente: str, *, tenant: str = au.DB_TENANT_PRIV, **campos) -> str:
    """Un job REAL en `notification_jobs`, con los tiempos relativos a `opened_at`."""
    jid = str(uuid.uuid4())
    base = {
        "channel": "email",
        "mode": "cascade",
        "position": 0,
        "status": "pending",
        "target": '{"to": ["ops@cliente.com"]}',
        "sent_off_s": None,
        "delivered_off_s": None,
        "deadline_off_s": None,
        "last_status": None,
        "error": None,
        "attempts": 0,
    }
    base.update(campos)
    await _sql(
        "INSERT INTO notification_jobs (job_id, tenant_id, incident_id, channel, mode, position,"
        " status, target, due_at, deadline_at, created_at, sent_at, delivered_at,"
        " last_status, error, attempts)"
        " SELECT :j, :t, :i, :ch, :mo, :pos, :st, CAST(:tg AS jsonb), i.opened_at,"
        "        i.opened_at + make_interval(secs => CAST(:dl AS double precision)), i.opened_at,"
        "        i.opened_at + make_interval(secs => CAST(:so AS double precision)),"
        "        i.opened_at + make_interval(secs => CAST(:do AS double precision)),"
        "        :ls, :er, :at"
        "   FROM incidents i WHERE i.incident_id = :i",
        j=jid,
        t=tenant,
        i=incidente,
        ch=base["channel"],
        mo=base["mode"],
        pos=base["position"],
        st=base["status"],
        tg=base["target"],
        so=base["sent_off_s"],
        do=base["delivered_off_s"],
        dl=base["deadline_off_s"],
        ls=base["last_status"],
        er=base["error"],
        at=base["attempts"],
    )
    return jid


@pytest.fixture(autouse=True)
async def _limpio():
    yield
    await _sql("DELETE FROM notification_jobs")
    await _sql("DELETE FROM incident_actions WHERE kind = 'ack'")
    await _sql("DELETE FROM incidents WHERE trigger = 'sasmex' AND severity = 'critical'")


# ─────────────────────────────────────────────── los seis estados, sin colapsar


async def test_entregado_trae_las_DOS_latencias(client, base_data):
    iid = await _incidente()
    await _job(iid, status="sent", sent_off_s=3.5, delivered_off_s=19.0, last_status="delivered")

    r = await client.get(f"/incidents/{iid}/notifications", headers=_token())
    assert r.status_code == 200, r.text
    job = r.json()["items"][0]
    assert job["delivered"] is True
    # Despacho = desde que se abrió el incidente (el mismo t0 que usa el
    # orquestador para su SLA). Entrega = desde que el proveedor lo aceptó.
    assert job["dispatch_latency_s"] == pytest.approx(3.5, abs=0.1)
    assert job["delivery_latency_s"] == pytest.approx(15.5, abs=0.1)


async def test_simulado_NO_es_entregado_ni_tiene_latencia(client, base_data):
    """`simulated` significa «no había proveedor»: nadie recibió nada."""
    iid = await _incidente()
    await _job(iid, status="simulated", channel="sms", target='{"to": "+525512345678"}')

    job = (await client.get(f"/incidents/{iid}/notifications", headers=_token())).json()["items"][0]
    assert job["status"] == "simulated"
    assert job["delivered"] is False
    assert job["dispatch_latency_s"] is None, "un simulado con latencia diría que salió"
    assert job["delivery_latency_s"] is None


async def test_aceptado_por_el_proveedor_NO_es_entregado(client, base_data):
    """`sent_at` dice que el proveedor lo aceptó, no que un humano lo tenga."""
    iid = await _incidente()
    await _job(iid, status="sent", sent_off_s=2.0, last_status="sent")

    job = (await client.get(f"/incidents/{iid}/notifications", headers=_token())).json()["items"][0]
    assert job["delivered"] is False
    assert job["dispatch_latency_s"] == pytest.approx(2.0, abs=0.1)
    assert job["delivery_latency_s"] is None, "sin confirmación no hay latencia de entrega"


async def test_los_seis_estados_de_la_tabla_se_leen_sin_colapsarse(client, base_data):
    """Barrido por IGUALDAD contra el CHECK de la columna: un estado nuevo sale rojo."""
    esperados = {"pending", "sent", "failed", "skipped", "simulated", "blocked_demo"}
    en_la_base = {
        r[0]
        for r in await _sql(
            "SELECT unnest(enum_from_check) FROM ("
            "  SELECT regexp_matches(pg_get_constraintdef(oid),"
            "         '''([a-z_]+)''', 'g') AS enum_from_check"
            "    FROM pg_constraint"
            "   WHERE conname = 'notification_jobs_status_check') s"
        )
    }
    assert en_la_base == esperados, "el CHECK de status cambió y este test no se enteró"

    iid = await _incidente()
    # Canal distinto por estado: `uq_notification_jobs_incident` es
    # (incident_id, channel, mode) y seis jobs del mismo canal colisionarían.
    canales = ["email", "sms", "whatsapp", "webhook", "push", "email"]
    for i, (st, ch) in enumerate(zip(sorted(esperados), canales, strict=True)):
        await _job(iid, status=st, channel=ch, mode="cascade" if i < 5 else "parallel", position=i)

    items = (await client.get(f"/incidents/{iid}/notifications", headers=_token())).json()["items"]
    assert {j["status"] for j in items} == esperados
    # Solo el que tiene `delivered_at` está entregado, y ninguno de estos lo tiene.
    assert not any(j["delivered"] for j in items)


# ─────────────────────────────────────────────────────── el destinatario


async def test_el_correo_sale_enmascarado(client, base_data):
    iid = await _incidente()
    await _job(iid, target='{"to": ["ops@cliente.com"]}')

    job = (await client.get(f"/incidents/{iid}/notifications", headers=_token())).json()["items"][0]
    assert job["recipient"]["kind"] == "correo"
    assert job["recipient"]["hint"] == "o***@cliente.com"
    assert "ops@cliente.com" not in str(job)


async def test_la_URL_del_webhook_sale_SIN_RUTA(client, base_data):
    """La ruta de un webhook autoriza a publicar. No puede salir de la API."""
    iid = await _incidente()
    await _job(
        iid,
        channel="webhook",
        target='{"url": "https://hooks.example.com/services/T0/B0/xoxbSECRETO"}',
    )

    cuerpo = (await client.get(f"/incidents/{iid}/notifications", headers=_token())).text
    assert "hooks.example.com" in cuerpo
    assert "xoxbSECRETO" not in cuerpo and "services" not in cuerpo


async def test_un_destinatario_no_reconocido_se_DECLARA(client, base_data):
    iid = await _incidente()
    await _job(iid, channel="email", target='{"destinatarios": ["ops@cliente.com"]}')

    job = (await client.get(f"/incidents/{iid}/notifications", headers=_token())).json()["items"][0]
    assert job["recipient"]["unrecognised"] is True
    assert job["recipient"]["hint"] == ""


# ─────────────────────────────────────────────────────────── aislamiento


async def test_el_incidente_del_vecino_da_404_y_no_una_lista_vacia(client, base_data):
    """Una lista vacía confirmaría que el incidente existe."""
    ajeno = await _incidente(tenant=au.DB_TENANT_PRIV2, site=au.DB_SITE_PRIV2)
    await _job(ajeno, tenant=au.DB_TENANT_PRIV2)

    r = await client.get(f"/incidents/{ajeno}/notifications", headers=_token())
    assert r.status_code == 404, r.text


async def test_un_incidente_sin_envios_dice_que_no_hubo_ninguno(client, base_data):
    """Y eso NO es lo mismo que el 404 de arriba."""
    iid = await _incidente()
    r = await client.get(f"/incidents/{iid}/notifications", headers=_token())
    assert r.status_code == 200 and r.json()["items"] == []


# ────────────────────────────────────────────────── la latencia del acuse


async def test_el_acuse_deja_ESCRITA_su_latencia(client, base_data):
    """Es el defecto que abre la ficha: el acuse nunca leía el instante de apertura."""
    iid = await _incidente()
    r = await client.post(f"/incidents/{iid}/ack", headers=_token())
    assert r.status_code == 200, r.text

    filas = await _sql(
        "SELECT payload FROM incident_actions WHERE incident_id = :i AND kind = 'ack'", i=iid
    )
    assert len(filas) == 1
    payload = filas[0][0]
    # El incidente se abrió hace 10 minutos: ~600 s, y desde luego no cero.
    assert payload["latency_s"] == pytest.approx(600, abs=30)


async def test_el_incidente_sin_acusar_no_tiene_latencia_de_acuse(client, base_data):
    """Ni cero: no hay fila, y no haberla es la respuesta correcta."""
    iid = await _incidente()
    filas = await _sql(
        "SELECT payload FROM incident_actions WHERE incident_id = :i AND kind = 'ack'", i=iid
    )
    assert filas == []


# ─────────────────────────────────── el acuse de GOBIERNO, que no dejaba rastro


async def test_el_acuse_de_GOBIERNO_tambien_entra_en_la_bitacora(client, base_data):
    """Encontrado haciendo la ficha: `gov_ack_incident` solo escribía `audit_log`.

    El resultado era que un incidente acusado por Protección Civil salía `acked`
    en la consola **y con la bitácora sin un solo acuse**: la pantalla que existe
    para reconstruir lo ocurrido afirmaba que nadie había acusado. Es peor que la
    latencia que falta, porque no es un hueco — es una contradicción con el
    propio estado del incidente que hay al lado.
    """
    iid = await _incidente(tenant=au.DB_TENANT_GOV, site=au.DB_SITE_GOV)
    r = await client.post(
        f"/incidents/{iid}/ack",
        headers=au.bearer(au.make_token("gov_operator", tenant=au.DB_TENANT_AGENCY)),
    )
    assert r.status_code == 200, r.text

    filas = await _sql(
        "SELECT actor, payload FROM incident_actions WHERE incident_id = :i AND kind = 'ack'",
        i=iid,
    )
    assert len(filas) == 1, "el acuse de gobierno no dejó fila en la bitácora"
    actor, payload = filas[0]
    assert actor.startswith("gov:"), "el acuse de gobierno tiene que distinguirse del del tenant"
    assert payload["latency_s"] == pytest.approx(600, abs=30)
    assert payload["via"] == "gov_ack_incident"


# ───────────────────────────────── el plazo, que también se incumple CALLANDO


async def test_el_que_NUNCA_salio_y_venció_su_plazo_lo_incumplió(client, base_data):
    """El SLA no se cumple por no intentarlo.

    La primera versión comparaba `sent_at <= deadline_at` y devolvía `null` sin
    `sent_at`: un job encolado hace media hora, con plazo de 60 s y sin enviar,
    salía SIN aviso de plazo. Es la misma familia que un fallback pintado de
    `ok` — el incumplimiento más grave, el que ni se intentó, era el único
    silencioso.
    """
    iid = await _incidente()
    await _job(iid, status="pending", deadline_off_s=60)  # el incidente se abrió hace 10 min

    job = (await client.get(f"/incidents/{iid}/notifications", headers=_token())).json()["items"][0]
    assert job["deadline_met"] is False
    assert job["sent_at"] is None, "el arnés dejó de probar lo que dice probar"


async def test_el_que_todavia_esta_dentro_de_plazo_no_se_acusa_de_nada(client, base_data):
    iid = await _incidente()
    await _job(iid, status="pending", deadline_off_s=3600)  # una hora desde la apertura

    job = (await client.get(f"/incidents/{iid}/notifications", headers=_token())).json()["items"][0]
    assert job["deadline_met"] is True


async def test_sin_plazo_no_hay_veredicto_de_plazo(client, base_data):
    """`None` aquí SÍ es correcto: el canal no tenía deadline que cumplir."""
    iid = await _incidente()
    await _job(iid, status="sent", sent_off_s=2.0)

    job = (await client.get(f"/incidents/{iid}/notifications", headers=_token())).json()["items"][0]
    assert job["deadline_met"] is None
