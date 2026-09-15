"""[T-7.13] La pasada de fases del worker: quién saca al incidente de la alerta.

Hasta esta ficha **nada cerraba un incidente en producción**: `transition_incident`
y `close_resolved` existían sin llamador, no había TTL, el acuse dejaba el banner
puesto y la clasificación era inerte. Un incidente abierto en julio seguía siendo
«la alerta» en septiembre (`D-33`).

Lo que fija esta suite, por orden de lo que costaría equivocarse:

1. **No basta con que haya HABIDO una vuelta a `normal`.** La calma anterior al
   sismo sigue en la tabla: quien pregunte «¿existe una fila normal de este
   sitio?» la encuentra y apaga la alerta mientras la sacudida está empezando.
   Lo que decide es el **último** tier del sitio.
2. **Con el sitio todavía sacudiéndose no se sale de la alerta**, por mucho que
   hayan pasado el settle y el retén.
3. **El reloj no cierra nada por sí solo.** El retén (`alert_hold_min_s`) es un
   MÍNIMO que se suma a la condición de estado, nunca una condición suficiente,
   y el TTL es de la REVISIÓN: un `open` no se cierra por vencimiento jamás.
4. **Cada transición deja su CAUSA** en `incident_actions`: quien lea el timeline
   a las 3 de la mañana tiene que poder distinguir «lo cerró el inspector» de «lo
   cerró el TTL porque nadie lo miró».
5. **Idempotente y sin tocar cerrados.** La pasada corre cada 5 s.

Las aserciones son de PERTENENCIA, no de igualdad de lista: la pasada es global
—como la del dictamen— y la base de tests lleva incidentes de otras suites.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.incident.lifecycle import PasadaDeFases, run_lifecycle_pass
from takab_api.settings import Settings

NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)
FIRMANTE = "00000000-0000-0000-0000-0000000000aa"

SETTLE_S = 60.0
HOLD_S = 180.0
TTL_S = 21600.0


def _dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
    )
    return url.replace("postgresql+psycopg://", "postgresql://")


def _settings(**over: float) -> Settings:
    return Settings(
        dictamen_settle_s=over.get("settle", SETTLE_S),
        alert_hold_min_s=over.get("hold", HOLD_S),
        incident_review_ttl_s=over.get("ttl", TTL_S),
    )


@dataclass
class Escenario:
    conn: psycopg.Connection
    tenant: str
    site: str
    otro_sitio: str
    gateway: str

    # ------------------------------------------------------------- siembra
    def incidente(
        self, *, state: str = "open", abierto_hace_s: float = 600.0, site: str | None = None
    ) -> str:
        inc = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at, "
            "severity, state, trigger) VALUES (%s, gen_random_uuid(), %s, %s, %s, "
            "'critical', %s, 'sasmex')",
            (inc, self.tenant, site or self.site, NOW - timedelta(seconds=abierto_hace_s), state),
        )
        self.conn.commit()
        return inc

    def tier(self, tier: str, *, hace_s: float, site: str | None = None) -> None:
        """Una transición de tier del sitio, como la escribe `handle_tier_transition`."""
        self.conn.execute(
            "INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, prev_tier,"
            " new_tier) VALUES (%s,%s,%s,%s,'watch',%s)",
            (
                NOW - timedelta(seconds=hace_s),
                self.tenant,
                site or self.site,
                self.gateway,
                tier,
            ),
        )
        self.conn.commit()

    def clasificar(self, inc: str, valor: str, *, sustituye: str | None = None) -> str:
        fila = self.conn.execute(
            "INSERT INTO incident_classifications "
            "(tenant_id, incident_id, classification, classified_by, supersedes_id) "
            "VALUES (%s,%s,%s,gen_random_uuid(),%s) RETURNING classification_id",
            (self.tenant, inc, valor, sustituye),
        ).fetchone()
        self.conn.commit()
        return str(fila["classification_id"])

    def dictamen(self, inc: str, *, firmado: bool) -> None:
        self.conn.execute(
            "INSERT INTO dictamens (incident_id, tenant_id, status, basis, signed_by) "
            "VALUES (%s,%s,'normal_operation','{}'::jsonb,%s)",
            (inc, self.tenant, FIRMANTE if firmado else None),
        )
        self.conn.commit()

    def entro_a_revision(self, inc: str, *, hace_s: float) -> None:
        """La huella que deja `transition_incident` al pasar a revisión."""
        self.conn.execute(
            "INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor) "
            "VALUES (%s,%s,%s,'in_review','system:incident')",
            (inc, self.tenant, NOW - timedelta(seconds=hace_s)),
        )
        self.conn.commit()

    # -------------------------------------------------------------- lectura
    def estado(self, inc: str) -> dict:
        return self.conn.execute(
            "SELECT state, closed_at FROM incidents WHERE incident_id = %s", (inc,)
        ).fetchone()

    def acciones(self, inc: str) -> list[dict]:
        return self.conn.execute(
            "SELECT kind, actor, payload FROM incident_actions WHERE incident_id = %s"
            " ORDER BY ts, kind",
            (inc,),
        ).fetchall()

    def cierre(self, inc: str) -> list[dict]:
        return [a for a in self.acciones(inc) if a["kind"] == "close"]

    # --------------------------------------------------------------- pasada
    def pasada(self, *, now: datetime = NOW, maximo: int = 200, **over: float) -> PasadaDeFases:
        """Corre la pasada **con el rol del worker**, no como superusuario."""
        self.conn.execute('SET ROLE "takab_ingest"')
        try:
            return run_lifecycle_pass(self.conn, _settings(**over), now=now, max_por_pasada=maximo)
        finally:
            self.conn.execute("RESET ROLE")
            self.conn.commit()


@pytest.fixture
def esc() -> Iterator[Escenario]:
    """Tenant propio por test; la pasada COMMITEA, así que la limpieza es explícita."""
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    tenant, site, otro, gateway = (str(uuid.uuid4()) for _ in range(4))
    try:
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name, visibility) "
            "VALUES (%s,%s,'Fases T-7.13','private')",
            (tenant, tenant[:8]),
        )
        for sid, sufijo in ((site, "A"), (otro, "B")):
            conn.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(%s,%s,%s,'Sitio',ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography)",
                (sid, tenant, f"{tenant[:8]}-{sufijo}"),
            )
        conn.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, status) "
            "VALUES (%s,%s,%s,%s,'online')",
            (gateway, tenant, site, f"SER-{tenant[:8]}"),
        )
        conn.commit()
        yield Escenario(conn, tenant, site, otro, gateway)
    finally:
        _limpiar(conn, tenant)
        conn.close()


def _limpiar(conn: psycopg.Connection, tenant: str) -> None:
    """`incident_actions`, `dictamens` y las clasificaciones son append-only: el
    superusuario apaga los triggers de fila con `session_replication_role` (solo
    en tests; en producción esas filas son inmutables, regla de oro 11)."""
    conn.rollback()
    conn.execute("RESET ROLE")
    try:
        conn.execute("SET session_replication_role = 'replica'")
        for tabla in (
            "incident_actions",
            "incident_classifications",
            "dictamens",
            "incidents",
            "rule_evaluations",
            "audit_log",
            "gateways",
            "sites",
            "tenants",
        ):
            conn.execute(f"DELETE FROM {tabla} WHERE tenant_id = %s", (tenant,))
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()
    except psycopg.Error:
        conn.rollback()


# ───────────────────────────────────────────── open/acked → in_review


def test_con_tier_normal_y_el_reten_cumplido_pasa_a_REVISION(esc: Escenario) -> None:
    inc = esc.incidente(state="open", abierto_hace_s=600.0)
    esc.tier("restricted", hace_s=590.0)
    esc.tier("normal", hace_s=400.0)

    esc.pasada()

    assert esc.estado(inc)["state"] == "in_review"
    accion = esc.acciones(inc)
    assert [a["kind"] for a in accion] == ["in_review"]
    assert accion[0]["payload"]["reason"] == "shaking_concluded"
    assert accion[0]["actor"] == "system:incident"


def test_haber_estado_normal_ANTES_del_sismo_no_apaga_la_alerta(esc: Escenario) -> None:
    """El error que apagaría la alerta en el peor instante posible.

    El sitio estaba en calma justo antes del sismo y esa fila sigue en la tabla.
    Una consulta que pregunte «¿hubo alguna vuelta a normal?» la encuentra y
    concluye que la sacudida terminó **mientras está empezando**. Lo que decide
    es el ÚLTIMO tier, que aquí dice que el edificio se está moviendo.
    """
    inc = esc.incidente(state="open", abierto_hace_s=600.0)
    esc.tier("normal", hace_s=900.0)  # la calma PREVIA
    esc.tier("restricted", hace_s=590.0)  # y ahora está sacudiéndose

    esc.pasada()

    assert esc.estado(inc)["state"] == "open", (
        "la calma PREVIA al sismo se leyó como el final de la sacudida"
    )


def test_con_el_sitio_TODAVIA_sacudiendose_no_pasa_a_revision(esc: Escenario) -> None:
    inc = esc.incidente(state="acked", abierto_hace_s=3600.0)
    esc.tier("normal", hace_s=3000.0)
    esc.tier("evacuate_or_hold", hace_s=30.0)  # la réplica

    esc.pasada()

    assert esc.estado(inc)["state"] == "acked"


def test_antes_del_RETEN_minimo_no_pasa_aunque_el_tier_sea_normal(esc: Escenario) -> None:
    """El retén es un MÍNIMO que se suma al estado, no una alternativa a él."""
    inc = esc.incidente(state="open", abierto_hace_s=90.0)  # settle sí, retén no
    esc.tier("normal", hace_s=80.0)

    esc.pasada(settle=60.0, hold=180.0)
    assert esc.estado(inc)["state"] == "open"

    esc.pasada(now=NOW + timedelta(seconds=120), settle=60.0, hold=180.0)
    assert esc.estado(inc)["state"] == "in_review"


def test_el_tier_de_OTRO_sitio_no_saca_a_este_de_la_alerta(esc: Escenario) -> None:
    inc = esc.incidente(state="open", abierto_hace_s=600.0)
    esc.tier("restricted", hace_s=590.0)
    esc.tier("normal", hace_s=400.0, site=esc.otro_sitio)

    esc.pasada()

    assert esc.estado(inc)["state"] == "open"


def test_un_sitio_SIN_transiciones_pasa_a_revision_cumplido_el_reten(esc: Escenario) -> None:
    """SASMEX lejano: la alerta suena y el edificio no siente nada.

    Ninguna estación reporta sacudida, así que nada indica que siga temblando.
    Llevar la alerta puesta para siempre sería pintar como vigente lo que el
    servidor no sabe (regla de oro 7); es el mismo tier que el teléfono del
    ocupante ya lee como `shaking_concluded`.
    """
    inc = esc.incidente(state="open", abierto_hace_s=600.0)

    esc.pasada()

    assert esc.estado(inc)["state"] == "in_review"


# ───────────────────────────────────────────────────────── → closed


def test_la_clasificacion_TERMINAL_cierra_y_deja_su_causa(esc: Escenario) -> None:
    inc = esc.incidente(state="in_review")
    esc.clasificar(inc, "falso_positivo")

    esc.pasada()

    fila = esc.estado(inc)
    assert fila["state"] == "closed" and fila["closed_at"] is not None
    cierre = esc.cierre(inc)
    assert len(cierre) == 1
    assert cierre[0]["payload"]["reason"] == "classification"
    assert cierre[0]["payload"]["classification"] == "falso_positivo"
    assert cierre[0]["actor"] == "system:incident"


def test_la_clasificacion_REAL_deja_el_incidente_en_revision(esc: Escenario) -> None:
    """`real` no es un cierre: el evento ocurrió y el inmueble sigue por dictaminar."""
    inc = esc.incidente(state="in_review")
    esc.clasificar(inc, "real")

    esc.pasada()

    assert esc.estado(inc)["state"] == "in_review"


def test_la_clasificacion_CORREGIDA_manda_sobre_la_sustituida(esc: Escenario) -> None:
    """Corregir INSERTA (T-5.12): decide la VIGENTE, no la primera que se escribió.

    Cerrar por una clasificación ya corregida es cerrar por un dato retirado.
    """
    inc = esc.incidente(state="in_review")
    primera = esc.clasificar(inc, "falso_positivo")
    esc.clasificar(inc, "real", sustituye=primera)

    esc.pasada()

    assert esc.estado(inc)["state"] == "in_review"


def test_el_dictamen_FIRMADO_cierra_y_el_preliminar_no(esc: Escenario) -> None:
    firmado = esc.incidente(state="in_review")
    preliminar = esc.incidente(state="in_review")
    esc.dictamen(firmado, firmado=True)
    esc.dictamen(preliminar, firmado=False)

    esc.pasada()

    assert esc.estado(firmado)["state"] == "closed"
    assert esc.estado(preliminar)["state"] == "in_review"
    assert esc.cierre(firmado)[0]["payload"]["reason"] == "dictamen_signed"


def test_el_TTL_cierra_contando_desde_que_ENTRO_a_revision(esc: Escenario) -> None:
    """La red de seguridad, no la vía normal: horas, y desde el ingreso a revisión.

    Contarlo desde `opened_at` cerraría por vencimiento un incidente que acaba de
    entrar en revisión tras una noche de réplicas — justo cuando alguien va a
    mirarlo.
    """
    inc = esc.incidente(state="in_review", abierto_hace_s=TTL_S + 3600.0)
    esc.entro_a_revision(inc, hace_s=60.0)

    esc.pasada()
    assert esc.estado(inc)["state"] == "in_review", (
        "el TTL se contó desde la apertura y no desde el ingreso a revisión"
    )

    esc.pasada(now=NOW + timedelta(seconds=TTL_S))
    assert esc.estado(inc)["state"] == "closed"
    assert esc.cierre(inc)[0]["payload"]["reason"] == "review_ttl"


def test_el_TTL_en_CERO_desactiva_esa_via_y_deja_las_otras(esc: Escenario) -> None:
    """Cómo se revoca `D-33` si un cliente exige cierre humano siempre."""
    viejo = esc.incidente(state="in_review", abierto_hace_s=TTL_S * 10)
    clasificado = esc.incidente(state="in_review", abierto_hace_s=TTL_S * 10)
    esc.clasificar(clasificado, "prueba")

    esc.pasada(ttl=0.0)

    assert esc.estado(viejo)["state"] == "in_review"
    assert esc.estado(clasificado)["state"] == "closed"


def test_el_TTL_no_cierra_lo_que_sigue_en_ALERTA(esc: Escenario) -> None:
    """El TTL es de la revisión. Un `open` no se cierra por reloj jamás."""
    inc = esc.incidente(state="open", abierto_hace_s=TTL_S * 10)
    esc.tier("evacuate_or_hold", hace_s=10.0)

    esc.pasada()

    assert esc.estado(inc)["state"] == "open"


# ─────────────────────────────────────────── idempotencia y alcance


def test_la_pasada_es_IDEMPOTENTE(esc: Escenario) -> None:
    inc = esc.incidente(state="in_review")
    esc.clasificar(inc, "prueba")

    primera = esc.pasada()
    segunda = esc.pasada()

    assert inc in primera.cerrados
    assert inc not in segunda.cerrados
    assert len(esc.cierre(inc)) == 1


def test_no_toca_un_incidente_ya_CERRADO(esc: Escenario) -> None:
    inc = esc.incidente(state="closed")
    esc.clasificar(inc, "falso_positivo")
    esc.dictamen(inc, firmado=True)

    resultado = esc.pasada()

    assert inc not in resultado.cerrados
    assert esc.acciones(inc) == []


def test_un_incidente_en_ALERTA_con_clasificacion_terminal_se_cierra_DIRECTO(
    esc: Escenario,
) -> None:
    """El operador que clasifica sin esperar.

    `open → closed` es una transición válida, y pasarlo antes por `in_review`
    escribiría en el timeline una revisión que nadie hizo.
    """
    inc = esc.incidente(state="open", abierto_hace_s=30.0)
    esc.tier("restricted", hace_s=20.0)
    esc.clasificar(inc, "prueba")

    esc.pasada()

    assert esc.estado(inc)["state"] == "closed"
    assert [a["kind"] for a in esc.acciones(inc)] == ["close"]


def test_el_tope_por_pasada_se_DECLARA_en_el_resultado(esc: Escenario) -> None:
    """Un corte silencioso se lee como «ya está todo hecho»."""
    for _ in range(3):
        inc = esc.incidente(state="in_review")
        esc.clasificar(inc, "prueba")

    resultado = esc.pasada(maximo=2)

    assert len(resultado.cerrados) == 2
    assert resultado.truncada is True, "la pasada se quedó a medias y no lo dijo"
