"""[T-9.42 · D-48] La pasada del worker `informes`, CONTRA LA BASE y con el generador inyectado.

El generador de verdad (`routers/reports.generar_informe`) lo ejerce
`test_generador_real.py`; aquí se sustituye por uno que deja una fila de evidencia
de mentira, para medir lo que es de la PASADA:

1. **Elegibilidad.** Sólo cautela no; una PRUEBA no (no se le manda correo al
   cliente por un ensayo); fuera de la ventana no (el primer despliegue no puede
   estrenarse con un correo por cada incidente del histórico).
2. **Disparo.** Firma, cierre o plazo, lo que llegue primero, y queda escrito.
3. **Idempotencia** (regla de oro 3): dos pasadas, una fila y una acción.
4. **Fallo honesto.** Si el generador lanza, `fallido` con su causa y SIN acción:
   un aviso de «informe listo» sin informe sería peor que ninguno.
5. **Reintento acotado.** 300 s entre intentos, 3 como mucho; un `pendiente`
   huérfano (el worker murió a medias) vuelve a los 900 s.
6. **El tope se DECLARA.** Un no-op silencioso es el modo de fallo más caro.

`BASE` en 2035: la pasada barre TODOS los incidentes de la ventana, y ningún otro
fichero siembra ahí.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row
from sqlalchemy import text

from takab_api.db import pool
from takab_api.informes import pasada as P
from takab_api.routers.reports import InformeGenerado
from takab_api.settings import Settings

BASE = datetime(2035, 3, 3, 12, 0, 0, tzinfo=UTC)
DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"


def _url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def _settings(**over: Any) -> Settings:
    """`database_url` a mano: el puente async abre SU conexión con este ajuste, y en
    los tests `Settings()` podría caer a la base de desarrollo (la trampa que midió
    la suite del ShakeMap)."""
    return Settings(**{"database_url": _url(), **over})


# ------------------------------------------------------------------ generadores


async def generar_falso(
    conn, incident: Mapping[str, Any], *, settings: Settings
) -> InformeGenerado:
    """Deja una evidencia de verdad (la FK y el CHECK de la tabla la exigen)."""
    sha = hashlib.sha256(str(incident["incident_id"]).encode()).hexdigest()
    evidencia = (
        await conn.execute(
            text(
                "INSERT INTO evidence_objects (tenant_id, incident_id, kind, s3_key, sha256)"
                " VALUES (:t, :i, 'report_pdf', :k, :s) RETURNING evidence_id"
            ),
            {
                "t": incident["tenant_id"],
                "i": incident["incident_id"],
                "k": f"falso/{sha}",
                "s": sha,
            },
        )
    ).scalar_one()
    return InformeGenerado(
        evidence_id=evidencia,
        sha256=sha,
        key=f"falso/{sha}",
        dictamen_vigente=None,
        preliminar=True,
    )


async def generar_que_revienta(conn, incident: Mapping[str, Any], *, settings: Settings):
    raise RuntimeError("S3 no contesta " + "x" * 400)


# ------------------------------------------------------------------ el escenario


@dataclass
class Escena:
    conn: psycopg.Connection
    tenant: str
    site: str

    def incidente(
        self,
        *,
        severity: str = "critical",
        trigger: str = "sasmex",
        state: str = "open",
        abierto: datetime = BASE,
    ) -> str:
        inc = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at,"
            " severity, state, trigger, closed_at) VALUES (%s, gen_random_uuid(), %s, %s, %s,"
            " %s, %s, %s, %s)",
            (
                inc,
                self.tenant,
                self.site,
                abierto,
                severity,
                state,
                trigger,
                abierto + timedelta(minutes=3) if state == "closed" else None,
            ),
        )
        self.conn.commit()
        return inc

    def clasifica(self, inc: str, clasificacion: str) -> None:
        self.conn.execute(
            "INSERT INTO incident_classifications (tenant_id, incident_id, classification,"
            " classified_by, classified_at) VALUES (%s,%s,%s,gen_random_uuid(),%s)",
            (self.tenant, inc, clasificacion, BASE + timedelta(minutes=1)),
        )
        self.conn.commit()

    def firma(self, inc: str, *, cuando: datetime) -> None:
        self.conn.execute(
            "INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by,"
            " signature_kind, created_at) VALUES (%s,%s,'normal_operation','{}'::jsonb,"
            " gen_random_uuid(),'inspector',%s)",
            (self.tenant, inc, cuando),
        )
        self.conn.commit()

    def pasada(self, minutos: float, generar=generar_falso, **kw: Any) -> P.PasadaInformes:
        return P.run_informes_pass(
            partial(pool.connect, _url()),
            kw.pop("settings", None) or _settings(),
            now=BASE + timedelta(minutes=minutos),
            generar=generar,
            **kw,
        )

    def informe(self, inc: str) -> dict | None:
        return self.conn.execute(
            "SELECT * FROM post_event_reports WHERE incident_id = %s", (inc,)
        ).fetchone()

    def acciones(self, inc: str) -> list[dict]:
        return self.conn.execute(
            "SELECT actor, payload, ts FROM incident_actions"
            " WHERE incident_id = %s AND kind = 'post_event_report'",
            (inc,),
        ).fetchall()


@pytest.fixture
def escena() -> Iterator[Escena]:
    conn = psycopg.connect(
        _url().replace("postgresql+psycopg://", "postgresql://"),
        autocommit=False,
        row_factory=dict_row,
    )
    tenant, site = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute(
        "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'Informes')",
        (tenant, tenant[:8]),
    )
    conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES (%s,%s,%s,'Sitio I',"
        " ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography)",
        (site, tenant, f"I-{site[:8]}"),
    )
    conn.commit()
    try:
        yield Escena(conn, tenant, site)
    finally:
        conn.rollback()
        conn.execute("SET session_replication_role = 'replica'")
        for tabla in (
            "post_event_reports",
            "incident_actions",
            "evidence_objects",
            "dictamens",
            "incident_classifications",
            "audit_log",
            "incidents",
            "sites",
            "tenants",
        ):
            conn.execute(f"DELETE FROM {tabla} WHERE tenant_id = %s", (tenant,))  # noqa: S608
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()
        conn.close()


# ------------------------------------------------------------------ elegibilidad


def test_solo_CAUTELA_no_toca_informe(escena: Escena) -> None:
    inc = escena.incidente(severity="watch", trigger="local_threshold")
    escena.pasada(30)
    assert escena.informe(inc) is None


def test_CAUTELA_que_autoriza_evacuar_SI_toca_informe(escena: Escena) -> None:
    """SASMEX autoriza aunque la severidad local sea baja: la regla es la de autoridad."""
    inc = escena.incidente(severity="watch", trigger="sasmex")
    escena.pasada(30)
    assert escena.informe(inc)["trigger"] == "plazo"


def test_una_PRUEBA_no_manda_informe_al_cliente(escena: Escena) -> None:
    inc = escena.incidente()
    escena.clasifica(inc, "prueba")
    escena.pasada(30)
    assert escena.informe(inc) is None


def test_una_clasificacion_NO_terminal_no_lo_impide(escena: Escena) -> None:
    inc = escena.incidente()
    escena.clasifica(inc, "real")
    escena.pasada(30)
    assert escena.informe(inc) is not None


def test_fuera_de_la_ventana_no_se_estrena_el_historico(escena: Escena) -> None:
    inc = escena.incidente()
    escena.pasada(7 * 60)
    assert escena.informe(inc) is None


# ------------------------------------------------------------------ disparo


def test_antes_del_plazo_y_sin_firma_ni_cierre_no_dispara(escena: Escena) -> None:
    inc = escena.incidente()
    escena.pasada(24)
    assert escena.informe(inc) is None


def test_dispara_por_PLAZO(escena: Escena) -> None:
    inc = escena.incidente()
    r = escena.pasada(25)
    fila = escena.informe(inc)
    assert fila["trigger"] == "plazo"
    assert fila["state"] == "ok"
    assert fila["variant"] == "executive"
    assert fila["evidence_id"] is not None
    assert fila["preliminar"] is True
    assert fila["attempts"] == 1
    assert fila["error"] is None
    assert inc in r.generados


def test_dispara_por_FIRMA(escena: Escena) -> None:
    inc = escena.incidente()
    escena.firma(inc, cuando=BASE + timedelta(minutes=2))
    escena.pasada(5)
    assert escena.informe(inc)["trigger"] == "firma"


def test_dispara_por_CIERRE(escena: Escena) -> None:
    inc = escena.incidente(state="closed")
    escena.pasada(5)
    assert escena.informe(inc)["trigger"] == "cierre"


def test_gana_lo_que_llego_PRIMERO(escena: Escena) -> None:
    """Cerrado a los 3 min y firmado a los 4: si la pasada llega a los 10, fue el cierre."""
    inc = escena.incidente(state="closed")
    escena.firma(inc, cuando=BASE + timedelta(minutes=4))
    escena.pasada(10)
    assert escena.informe(inc)["trigger"] == "cierre"


def test_una_cabeza_SIN_firmar_no_es_firma(escena: Escena) -> None:
    inc = escena.incidente()
    escena.conn.execute(
        "INSERT INTO dictamens (tenant_id, incident_id, status, basis, created_at)"
        " VALUES (%s,%s,'inhabit_monitor','{}'::jsonb,%s)",
        (escena.tenant, inc, BASE + timedelta(minutes=2)),
    )
    escena.conn.commit()
    escena.pasada(5)
    assert escena.informe(inc) is None


# ------------------------------------------------------------------ la acción y la idempotencia


def test_deja_UNA_accion_con_lo_que_el_aviso_necesita(escena: Escena) -> None:
    inc = escena.incidente()
    escena.pasada(25)
    escena.pasada(26)
    fila = escena.informe(inc)
    [accion] = escena.acciones(inc)
    assert accion["actor"] == "system:informes"
    assert accion["payload"] == {
        "report_id": str(fila["report_id"]),
        "evidence_id": str(fila["evidence_id"]),
        "variant": "executive",
        "trigger": "plazo",
        "preliminar": True,
    }
    assert (
        escena.conn.execute(
            "SELECT count(*) AS n FROM post_event_reports WHERE incident_id = %s", (inc,)
        ).fetchone()["n"]
        == 1
    )


def test_la_accion_lleva_la_hora_de_SU_commit_no_la_del_arranque(
    escena: Escena, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin `now` inyectado (producción), la acción se fecha cuando EXISTE.

    Fechada al arrancar la pasada, una tanda larga de PDF dejaría la acción más
    vieja que la ventana del orquestador (`notify_lookback_s`) antes de ser visible:
    el correo del informe no saldría nunca. Aquí la pasada «arranca» en BASE+26 min
    y el reloj marca BASE+80 min cuando el PDF ya está hecho.
    """
    inc = escena.incidente()
    reclamo = escena.pasada(26, generar=generar_que_revienta)  # deja la fila reclamable
    assert reclamo.fallidos == (inc,)
    fila = escena.informe(inc)
    monkeypatch.setattr(P, "_reclama", lambda *a, **k: ([fila], None))
    monkeypatch.setattr(P, "_ahora_utc", lambda: BASE + timedelta(minutes=80))

    P.run_informes_pass(partial(pool.connect, _url()), _settings(), generar=generar_falso)

    [accion] = escena.acciones(inc)
    assert accion["ts"] == BASE + timedelta(minutes=80)
    assert escena.informe(inc)["updated_at"] == BASE + timedelta(minutes=80)


# ------------------------------------------------------------------ fallo y reintento


def test_si_el_generador_lanza_queda_FALLIDO_con_causa_y_sin_accion(escena: Escena) -> None:
    inc = escena.incidente()
    r = escena.pasada(25, generar=generar_que_revienta)
    fila = escena.informe(inc)
    assert fila["state"] == "fallido"
    assert fila["evidence_id"] is None
    assert fila["attempts"] == 1
    assert fila["error"].startswith("RuntimeError: S3 no contesta")
    assert len(fila["error"]) <= 300
    assert escena.acciones(inc) == []
    assert inc in r.fallidos


def test_se_reintenta_a_los_300_s_y_no_pasa_de_3(escena: Escena) -> None:
    inc = escena.incidente()
    escena.pasada(25, generar=generar_que_revienta)
    escena.pasada(29, generar=generar_que_revienta)  # 240 s: todavía no
    assert escena.informe(inc)["attempts"] == 1
    escena.pasada(30.1, generar=generar_que_revienta)
    assert escena.informe(inc)["attempts"] == 2
    escena.pasada(35.2, generar=generar_que_revienta)
    assert escena.informe(inc)["attempts"] == 3
    escena.pasada(60)  # ya con un generador sano: el tope manda
    fila = escena.informe(inc)
    assert (fila["state"], fila["attempts"]) == ("fallido", 3)


def test_un_reintento_que_sale_bien_queda_ok(escena: Escena) -> None:
    inc = escena.incidente()
    escena.pasada(25, generar=generar_que_revienta)
    escena.pasada(31)
    fila = escena.informe(inc)
    assert (fila["state"], fila["attempts"], fila["error"]) == ("ok", 2, None)
    assert len(escena.acciones(inc)) == 1


def test_el_PENDIENTE_huerfano_se_reintenta_a_los_900_s(escena: Escena) -> None:
    """El worker murió entre reclamar y generar: la fila queda `pendiente`."""
    viejo, reciente = escena.incidente(), escena.incidente()
    for inc, hace in ((viejo, 901), (reciente, 800)):
        escena.conn.execute(
            "INSERT INTO post_event_reports (tenant_id, incident_id, trigger, variant,"
            " updated_at) VALUES (%s,%s,'plazo','executive',%s)",
            (escena.tenant, inc, BASE + timedelta(minutes=40) - timedelta(seconds=hace)),
        )
    escena.conn.commit()
    escena.pasada(40)
    assert escena.informe(viejo)["state"] == "ok"
    assert escena.informe(reciente)["state"] == "pendiente"


def test_sin_bucket_queda_fallido_sin_bucket_y_no_revienta(escena: Escena) -> None:
    """El generador de verdad, sin `evidence_bucket`: la causa se nombra, no se adivina."""
    inc = escena.incidente()
    escena.pasada(25, generar=P.generar_por_defecto, settings=_settings(evidence_bucket=""))
    fila = escena.informe(inc)
    assert (fila["state"], fila["error"]) == ("fallido", "sin_bucket")


# ------------------------------------------------------------------ lo que no se calla


def test_el_tope_se_DECLARA_y_lo_que_sobra_sale_en_la_siguiente(escena: Escena) -> None:
    incs = [escena.incidente() for _ in range(3)]
    r = escena.pasada(25, max_por_pasada=2)
    assert r.corte == P.CORTE_POR_TOPE
    assert r.truncada
    assert len(r.generados) == 2
    r2 = escena.pasada(26, max_por_pasada=2)
    assert r2.corte is None
    assert all(escena.informe(i)["state"] == "ok" for i in incs)


def test_con_el_cerrojo_tomado_lo_dice(escena: Escena) -> None:
    otra = psycopg.connect(_url().replace("postgresql+psycopg://", "postgresql://"))
    try:
        otra.execute("SELECT pg_advisory_xact_lock(%s)", (P.LOCK_KEY,))
        r = escena.pasada(25)
    finally:
        otra.rollback()
        otra.close()
    assert r.corte == P.CORTE_POR_CERROJO
    assert r.generados == ()
