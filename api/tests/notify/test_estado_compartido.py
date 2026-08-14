"""Lo que el worker recordaba EN RAM y ahora vive en la base (T-2.77.b/.c).

Tres memorias de proceso, un solo tema: nada de lo que hace falta después puede
vivir en un proceso que se reinicia y que no está solo.

Dos defectos MEDIDOS, no supuestos:

1. Al reiniciar el worker se olvidaba la cuarentena y se volvía a martillear una
   plantilla que Meta había pausado — exactamente lo que degrada su calificación
   de calidad y termina costando el canal entero.
2. Con más de una instancia del worker la guarda de duplicados no existía entre
   instancias. Y el supuesto de "un solo worker" ya estaba contradicho por el
   código de al lado: el orquestador usa ``pg_advisory_xact_lock`` porque asume
   varias.

Y la tercera, de T-2.77.b: el **identificador que el proveedor le dio al
mensaje** moría en el recibo en memoria del worker. Sin persistirlo no hay con
qué casar el desenlace tardío contra el job, así que el webhook de estado no
tendría nada que buscar.

Cada test monta el escenario y **lo confirma por sí mismo** antes de medir nada:
que el canal estaba VIVO antes de la pausa, que el primer intento salió de
verdad, que la fila existe en la tabla. Un arnés que infiere que se montó a
partir de la misma vista que después interroga puede salir verde midiendo la
nada.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.notify.orchestrator import run_notify_pass
from takab_api.notify.providers import DuplicateGuard, NotifyError, bind_state
from takab_api.notify.state import PgNotifyState
from takab_api.notify.twilio import build_sms_provider
from takab_api.notify.whatsapp import (
    TEMPLATES_DIR,
    build_whatsapp_provider,
    template_digest,
)
from takab_api.settings import Settings

BASE = datetime(2034, 5, 11, 9, 0, 0, tzinfo=UTC)
SRC_LON, SRC_LAT = -101.5, 11.0  # aislado, lejos de otras fixtures

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"

WA_MSISDN = "+525577777777"
SMS_MSISDN = "+525588888888"


def _dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL).replace(
        "postgresql+psycopg://", "postgresql://"
    )


# --- providers de mentira, sin una sola llamada de red ------------------------


class _Contador:
    """Transporte httpx que cuenta lo que se le pide y contesta lo que se le diga."""

    def __init__(self, respuesta) -> None:
        self._respuesta = respuesta
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if callable(self._respuesta):
            return self._respuesta(request)
        return self._respuesta

    @property
    def calls(self) -> int:
        return len(self.requests)


def _timeout(_request: httpx.Request) -> httpx.Response:
    """El fallo AMBIGUO: la petición pudo llegar y crear el mensaje."""
    raise httpx.ConnectTimeout("sin respuesta")


def _sms(transport_handler) -> tuple[object, _Contador]:
    contador = _Contador(transport_handler)
    settings = Settings(
        notify_sms_account_sid="AC" + "0" * 30,
        notify_sms_auth_token="t0k3n-de-mentira",
        notify_sms_from="+15005550006",
    )
    provider = build_sms_provider(settings)
    # El transporte se inyecta a posteriori porque `build_sms_provider` no lo
    # acepta; es el mismo atributo que usa `httpx.Client(transport=...)` dentro.
    provider._transport = httpx.MockTransport(contador)  # type: ignore[attr-defined]
    return provider, contador


def _wa_templates(tmp_path: Path, nombre: str) -> Path:
    """Los artefactos REALES del repo con el sello de aprobación puesto."""
    destino = tmp_path / nombre
    destino.mkdir()
    for src in sorted(TEMPLATES_DIR.glob("*.json")):
        doc = json.loads(src.read_text(encoding="utf-8"))
        doc["approval"] = {
            "status": "APPROVED",
            "approved_digest": template_digest(doc["template"]),
        }
        (destino / src.name).write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    return destino


def _whatsapp(directorio: Path, handler) -> tuple[object, _Contador]:
    contador = _Contador(handler)
    settings = Settings(
        notify_whatsapp_phone_number_id="123456789012345",
        notify_whatsapp_access_token="EA" + "f" * 30,
        notify_whatsapp_graph_version="v23.0",
        notify_whatsapp_templates_dir=str(directorio),
    )
    provider = build_whatsapp_provider(settings, transport=httpx.MockTransport(contador))
    return provider, contador


def _pausada(_request: httpx.Request) -> httpx.Response:
    """Meta pausa la plantilla por calidad: 132015, familia 132xxx."""
    return httpx.Response(400, json={"error": {"code": 132015, "message": "Template is paused"}})


def _aceptado(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.OK" + uuid.uuid4().hex[:6], "message_status": "accepted"}],
        },
    )


# --- escenario -----------------------------------------------------------------


class _Escenario:
    def __init__(self, conn: psycopg.Connection, tenant: str) -> None:
        self.conn = conn
        self.tenant = tenant

    def seed_config(self, config: dict) -> None:
        self.conn.execute(
            "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, is_active, config) "
            "VALUES (%s,'tenant',%s,1,true,%s::jsonb)",
            (self.tenant, self.tenant, json.dumps(config)),
        )
        self.conn.commit()

    def seed_consent(self, msisdn: str) -> None:
        self.conn.execute("RESET ROLE")
        self.conn.execute(
            "INSERT INTO privacy_consents (tenant_id, purpose, subject_kind, subject_ref, "
            "decision, notice_source, notice_digest, notice_version, notice_locale, via, "
            "actor_sub, decided_at) VALUES (%s,'whatsapp_alerts','msisdn',%s,'accept','repo',%s,"
            "'1.0.0','es-MX','out_of_band',%s,%s)",
            (self.tenant, msisdn, "0" * 64, str(uuid.uuid4()), BASE - timedelta(days=1)),
        )
        self.conn.commit()
        self.conn.execute("SET ROLE takab_ingest")
        self.conn.commit()

    def seed_incident(self, *, opened_at: datetime | None = None) -> str:
        site, incident = str(uuid.uuid4()), str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s,%s,%s,'Sitio C', ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)",
            (site, self.tenant, f"C-{site[:8]}", SRC_LON, SRC_LAT),
        )
        self.conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at, "
            "severity, trigger) VALUES (%s,%s,%s,%s,%s,'warning','local_threshold')",
            (incident, str(uuid.uuid4()), self.tenant, site, opened_at or BASE),
        )
        self.conn.commit()
        return incident

    def job(self, incident_id: str, channel: str) -> dict:
        row = self.conn.execute(
            "SELECT status, attempts, error, inflight_until, provider_message_id "
            "FROM notification_jobs WHERE incident_id = %s AND channel = %s",
            (incident_id, channel),
        ).fetchone()
        assert row is not None, f"no hay job {channel} para {incident_id}"
        return row

    def cuarentena(self) -> list[dict]:
        self.conn.rollback()
        return self.conn.execute(
            "SELECT channel, template_name, reason FROM notify_template_quarantine "
            "ORDER BY template_name"
        ).fetchall()


@pytest.fixture
def escenario() -> Iterator[_Escenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    tenant = str(uuid.uuid4())
    sc = _Escenario(conn, tenant)
    try:
        conn.execute("SET ROLE takab_ingest")
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Estado Compartido')",
            (tenant, tenant[:8]),
        )
        conn.commit()
        yield sc
    finally:
        conn.rollback()
        conn.execute("RESET ROLE")
        try:
            conn.execute("SET session_replication_role = 'replica'")
            conn.execute("DELETE FROM notification_jobs WHERE tenant_id = %s", (tenant,))
            conn.execute("DELETE FROM incident_actions WHERE tenant_id = %s", (tenant,))
            conn.execute("DELETE FROM incidents WHERE tenant_id = %s", (tenant,))
            conn.execute("DELETE FROM rule_sets WHERE tenant_id = %s", (tenant,))
            conn.execute("DELETE FROM sites WHERE tenant_id = %s", (tenant,))
            conn.execute("DELETE FROM privacy_consents WHERE tenant_id = %s", (tenant,))
            conn.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant,))
            # La cuarentena NO lleva tenant (es del despliegue): se limpia entera.
            conn.execute("DELETE FROM notify_template_quarantine")
            conn.execute("SET session_replication_role = 'origin'")
            conn.commit()
        except psycopg.Error:
            conn.rollback()
        conn.close()


def _pasada(escenario: _Escenario, providers: dict, *, now: datetime) -> dict:
    """Una pasada de UNA instancia del orquestador."""
    return run_notify_pass(escenario.conn, Settings(notify_max_attempts=9), providers, now=now)


# =============================================================================
# CRITERIO · la guarda de duplicados es COMPARTIDA entre instancias
# =============================================================================


def test_dos_orquestadores_contra_la_misma_base_y_el_mensaje_sale_UNA_vez(
    escenario: _Escenario,
) -> None:
    """El caso real, y el único que produce el duplicado.

    No es "dos pasadas simultáneas" —eso ya lo serializa el advisory lock—: es
    que la instancia A intente y se quede sin respuesta (ambiguo: el mensaje
    PUDO crearse), y que el reintento lo coja la instancia B, cuya memoria está
    vacía porque es otro proceso. Antes de esta ficha, B enviaba: segundo SMS al
    mismo teléfono en mitad de un sismo.

    El segundo incidente es la NO-VACUIDAD: la misma instancia B, en la misma
    pasada y contra el mismo número, sí envía lo que nadie había intentado. Sin
    él, un provider roto que no enviara nunca pasaría este test.
    """
    escenario.seed_config({"notifications": {"sms": {"to": SMS_MSISDN}}})
    intentado = escenario.seed_incident()
    virgen = escenario.seed_incident()

    # --- instancia A: intenta y se queda sin respuesta -----------------------
    a_provider, a_transporte = _sms(_timeout)
    _pasada(escenario, {"sms": a_provider}, now=BASE)

    # El arnés se confirma a sí mismo: A SALIÓ a la red de verdad (dos veces, una
    # por incidente) y el job quedó marcado como "pudo haber mensaje vivo".
    assert a_transporte.calls == 2, "el montaje no llegó a intentar el envío"
    marcado = escenario.job(intentado, "sms")
    assert marcado["inflight_until"] is not None, "la guarda no se escribió en la base"
    assert marcado["status"] == "pending"  # último salto: reintenta, no es lápida

    # Se rebobina SOLO el job virgen: se le borra la guarda para que represente
    # al que nadie tocó (A también lo intentó, y aquí interesa el contraste).
    escenario.conn.execute(
        "UPDATE notification_jobs SET inflight_until = NULL, due_at = %s "
        "WHERE incident_id = %s AND channel = 'sms'",
        (BASE, virgen),
    )
    escenario.conn.execute(
        "UPDATE notification_jobs SET due_at = %s WHERE incident_id = %s AND channel = 'sms'",
        (BASE, intentado),
    )
    escenario.conn.commit()

    # --- instancia B: proceso NUEVO, memoria vacía ---------------------------
    b_provider, b_transporte = _sms(
        httpx.Response(201, json={"sid": "SM" + "b" * 32, "status": "queued"})
    )
    assert b_provider is not a_provider
    _pasada(escenario, {"sms": b_provider}, now=BASE + timedelta(seconds=60))

    # B salió a la red UNA sola vez, y fue por el incidente que nadie había
    # intentado. El otro ni se rozó: se escaló en vez de arriesgar el duplicado.
    assert b_transporte.calls == 1
    assert escenario.job(virgen, "sms")["status"] == "sent"
    bloqueado = escenario.job(intentado, "sms")
    assert bloqueado["status"] != "sent"
    assert "duplicado" in (bloqueado["error"] or "")


def test_la_guarda_en_memoria_NO_se_ve_entre_instancias_y_la_de_la_base_SI(
    escenario: _Escenario,
) -> None:
    """El defecto desnudo, al nivel de la guarda.

    Dos ``DuplicateGuard`` sin almacén compartido son dos memorias ajenas: lo que
    recuerda una no existe para la otra. Atadas al estado de la base —el mismo
    job— el recuerdo es de las dos. Es la diferencia entre 'un solo worker' y lo
    que el despliegue hace de verdad.
    """
    escenario.seed_config({"notifications": {"sms": {"to": SMS_MSISDN}}})
    incidente = escenario.seed_incident()
    _pasada(escenario, {"sms": _sms(_timeout)[0]}, now=BASE)
    job_id = escenario.conn.execute(
        "SELECT job_id FROM notification_jobs WHERE incident_id = %s AND channel='sms'",
        (incidente,),
    ).fetchone()["job_id"]

    clave = (SMS_MSISDN, incidente)
    en_ram_a, en_ram_b = DuplicateGuard(), DuplicateGuard()
    en_ram_a.remember(clave, 300.0)
    assert en_ram_a.seen(clave) is True
    assert en_ram_b.seen(clave) is False, "no-vacuidad: así se veía el defecto"

    estado_a = PgNotifyState(escenario.conn, now=BASE)
    estado_b = PgNotifyState(escenario.conn, now=BASE)
    estado_a.enter_job(job_id)
    estado_b.enter_job(job_id)
    compartida_a, compartida_b = DuplicateGuard(store=estado_a), DuplicateGuard(store=estado_b)
    compartida_a.remember(clave, 300.0)
    assert compartida_b.seen(clave) is True


def test_la_guarda_compartida_CADUCA_como_la_de_memoria(escenario: _Escenario) -> None:
    """El TTL sigue siendo la ventana de vida del mensaje en el proveedor: pasado
    ese instante ya no queda nada vivo que duplicar, y el canal vuelve."""
    escenario.seed_config({"notifications": {"sms": {"to": SMS_MSISDN}}})
    incidente = escenario.seed_incident()
    _pasada(escenario, {"sms": _sms(_timeout)[0]}, now=BASE)
    job_id = escenario.conn.execute(
        "SELECT job_id FROM notification_jobs WHERE incident_id = %s AND channel='sms'",
        (incidente,),
    ).fetchone()["job_id"]

    dentro = PgNotifyState(escenario.conn, now=BASE + timedelta(seconds=299))
    dentro.enter_job(job_id)
    assert dentro.seen(("x", "y")) is True

    fuera = PgNotifyState(escenario.conn, now=BASE + timedelta(seconds=301))
    fuera.enter_job(job_id)
    assert fuera.seen(("x", "y")) is False


# =============================================================================
# CRITERIO · la cuarentena SOBREVIVE al reinicio del worker
# =============================================================================


def test_la_plantilla_en_cuarentena_SIGUE_en_cuarentena_tras_reiniciar_el_provider(
    escenario: _Escenario, tmp_path: Path
) -> None:
    """El defecto que costaba el canal entero.

    Meta pausa una plantilla (132015); el canal cae y escala, que es lo correcto.
    Hasta hoy, el siguiente arranque del worker cargaba el catálogo limpio y
    volvía a martillearla — y martillear una plantilla pausada no la despausa:
    solo empeora su calificación de calidad, que es lo que acaba costando el
    canal para toda la flota.

    "Reiniciar el provider" es literal: se construye uno NUEVO, con catálogo
    nuevo y memoria vacía, y se le da un estado compartido nuevo sobre la misma
    base — que es exactamente lo que hace un ``systemctl restart``.
    """
    directorio = _wa_templates(tmp_path, "plantillas")
    escenario.seed_config({"notifications": {"whatsapp": {"to": WA_MSISDN}}})
    escenario.seed_consent(WA_MSISDN)
    escenario.seed_incident()

    # --- antes: el canal está VIVO (no-vacuidad del montaje) -----------------
    provider1, transporte1 = _whatsapp(directorio, _pausada)
    assert provider1.simulated is False, "el montaje no llegó a tener un canal vivo"

    _pasada(escenario, {"whatsapp": provider1}, now=BASE)
    assert transporte1.calls == 1, "el montaje no llegó a hablar con Meta"

    # La cuarentena está ESCRITA en la base, y se comprueba en la tabla — no
    # preguntándole al mismo objeto que la puso.
    filas = escenario.cuarentena()
    assert len(filas) == 1, filas
    assert filas[0]["channel"] == "whatsapp"
    assert "132015" in filas[0]["reason"]
    nombre = filas[0]["template_name"]

    # --- el reinicio: provider nuevo, memoria vacía, misma base --------------
    provider2, transporte2 = _whatsapp(_wa_templates(tmp_path, "plantillas-2"), _aceptado)
    assert provider2 is not provider1
    assert provider2.simulated is False, "el provider nace vivo: la cuarentena no está en él"

    bind_state(
        {"whatsapp": provider2}, PgNotifyState(escenario.conn, now=BASE + timedelta(minutes=30))
    )
    assert nombre in provider2.quarantined
    assert provider2.simulated is True, "el reinicio levantó la cuarentena"

    # Y no se le vuelve a hablar a Meta: el canal se declara simulado y escala.
    otro = escenario.seed_incident(opened_at=BASE + timedelta(minutes=30))
    _pasada(escenario, {"whatsapp": provider2}, now=BASE + timedelta(minutes=31))
    assert transporte2.calls == 0, "se volvió a martillear una plantilla pausada"
    assert escenario.job(otro, "whatsapp")["status"] == "simulated"


def test_la_cuarentena_persistida_no_se_pisa_a_si_misma(escenario: _Escenario, tmp_path) -> None:
    """La PRIMERA razón manda: es la que cuenta por qué cayó el canal. Un
    reintento posterior confirma que sigue muerta, no reescribe la historia."""
    estado = PgNotifyState(escenario.conn, now=BASE)
    estado.quarantine("whatsapp", "alerta_sismica", "Meta devolvió 132015: pausada")
    estado.quarantine("whatsapp", "alerta_sismica", "otra cosa distinta")
    escenario.conn.commit()

    (fila,) = escenario.cuarentena()
    assert "132015" in fila["reason"]


def test_sin_estado_atado_el_provider_se_comporta_como_siempre(tmp_path: Path) -> None:
    """La API construye el registro de providers solo para saber qué canal es
    real, y lo hace SIN base. Ese camino no puede haber cambiado: sin estado
    atado, la cuarentena vuelve a ser memoria del proceso y nada consulta nada."""
    provider, _ = _whatsapp(_wa_templates(tmp_path, "p"), _pausada)
    assert provider.simulated is False
    assert provider.quarantined == {}
    with pytest.raises(NotifyError):
        provider.send(
            {"to": WA_MSISDN, "opt_in": {"at": "2026-08-01T12:00:00Z"}},
            {"incident_id": str(uuid.uuid4()), "kind": "incident", "site_name": "Torre C"},
        )
    assert provider.quarantined  # cayó en caliente, en memoria, como antes
    assert provider.simulated is True


# =============================================================================
# T-2.77.b · el identificador del proveedor se PERSISTE (o no hay qué casar)
# =============================================================================


def test_el_sid_de_twilio_queda_ESCRITO_en_el_job(escenario: _Escenario) -> None:
    """Sin esto, el webhook de estado no tiene con qué encontrar el job.

    Twilio devuelve el ``MessageSid`` en la respuesta del POST y hasta hoy se
    quedaba en el recibo en memoria del worker: al reiniciar, el mensaje que
    seguía en vuelo ya no era de nadie.
    """
    sid = "SM" + "1" * 32
    escenario.seed_config({"notifications": {"sms": {"to": SMS_MSISDN}}})
    incidente = escenario.seed_incident()
    provider, transporte = _sms(httpx.Response(201, json={"sid": sid, "status": "queued"}))

    _pasada(escenario, {"sms": provider}, now=BASE)

    assert transporte.calls == 1, "el montaje no llegó a enviar"
    fila = escenario.job(incidente, "sms")
    assert fila["status"] == "sent"
    assert fila["provider_message_id"] == sid


def test_el_identificador_del_canal_de_plantilla_queda_ESCRITO_en_el_job(
    escenario: _Escenario, tmp_path: Path
) -> None:
    """Lo mismo para el otro proveedor, y por el mismo camino: el orquestador lo
    lee del recibo por una propiedad con el MISMO nombre en los dos canales, sin
    una sola rama que sepa cómo lo llama cada uno."""
    escenario.seed_config({"notifications": {"whatsapp": {"to": WA_MSISDN}}})
    escenario.seed_consent(WA_MSISDN)
    incidente = escenario.seed_incident()
    provider, transporte = _whatsapp(_wa_templates(tmp_path, "plantillas"), _aceptado)

    _pasada(escenario, {"whatsapp": provider}, now=BASE)

    assert transporte.calls == 1, "el montaje no llegó a enviar"
    fila = escenario.job(incidente, "whatsapp")
    assert fila["status"] == "sent"
    assert fila["provider_message_id"], "el identificador no se persistió"
    assert fila["provider_message_id"] == provider.last_receipt.message_id


def test_un_canal_sin_recibo_no_BORRA_lo_que_ya_habia_escrito(escenario: _Escenario) -> None:
    """El correo y el webhook firmado no devuelven identificador: mandan cadena
    vacía. Un reenvío por ese camino no puede dejar el job sin con qué casar su
    desenlace tardío — de ahí el `coalesce(nullif(...))` del UPDATE."""

    class _SinRecibo:
        simulated = False

        def send(self, target: dict, message: dict) -> None: ...

    escenario.seed_config({"notifications": {"email": {"to": ["ops@example.mx"]}}})
    incidente = escenario.seed_incident()
    _pasada(escenario, {"email": _SinRecibo()}, now=BASE)

    escenario.conn.execute(
        "UPDATE notification_jobs SET provider_message_id = 'ya-estaba', status = 'pending', "
        "due_at = %s WHERE incident_id = %s AND channel = 'email'",
        (BASE, incidente),
    )
    escenario.conn.commit()

    _pasada(escenario, {"email": _SinRecibo()}, now=BASE + timedelta(seconds=1))
    assert escenario.job(incidente, "email")["provider_message_id"] == "ya-estaba"
