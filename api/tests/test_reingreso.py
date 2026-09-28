"""[T-9.04] El reingreso PERSISTENTE, en su forma pura.

Tres defectos medidos en `mobile_state` que esta función cierra:

1. **Un NO HABITAR firmado caducaba solo.** Firmar cierra el incidente (`D-33`,
   tres segundos) y la rama de cerrados sólo re-declaraba dictámenes HABITABLES:
   la app volvía a `idle` —el edificio desbloqueado— sin que nadie firmara nada.
2. **«REINGRESO AUTORIZADO» en reposo por incidentes que nunca ordenaron
   evacuar**: la consulta de cerrados no miraba `autoriza_evacuacion` (T-2.105),
   y además contaba las 8 h desde el CIERRE, no desde la FIRMA.
3. (Ése vive en el router: un local nuevo tapaba a un SASMEX abierto más viejo.)

Aquí se fijan las reglas sobre datos inventados, sin base; el ancla de arriba
abajo, contra el endpoint real, es `tests/api/test_reingreso_persistente.py`.
"""

from __future__ import annotations

import typing
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from takab_api.incident.classification import CLASIFICACIONES, TERMINALES
from takab_api.reingreso import (
    HABITABLES,
    IncidenteCerrado,
    RazonBloqueo,
    deriva_reingreso,
)

AHORA = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)
MIN_NODES = 3
VENTANA_FIRMA_S = 8 * 3600.0
LOOKBACK_S = 30 * 86400.0


def _inc(
    *,
    trigger: str = "sasmex",
    node_count: int | None = None,
    abierto_hace: timedelta = timedelta(days=1),
    cerrado_hace: timedelta | None = timedelta(hours=1),
    clasificacion: str | None = None,
    dictamen: str | None = None,
    firmado: bool = False,
    firmado_hace: timedelta = timedelta(hours=1),
    incident_id: UUID | None = None,
    banda: str | None = None,
    escalada: bool = False,
) -> IncidenteCerrado:
    return IncidenteCerrado(
        incident_id=incident_id or uuid4(),
        trigger=trigger,
        node_count=node_count,
        opened_at=AHORA - abierto_hace,
        closed_at=(AHORA - cerrado_hace) if cerrado_hace is not None else None,
        clasificacion=clasificacion,
        dictamen_status=dictamen,
        dictamen_firmado=firmado,
        dictamen_at=(AHORA - firmado_hace) if dictamen is not None else None,
        dictamen_band=banda,
        escalada_pendiente=escalada,
    )


def _deriva(*cerrados: IncidenteCerrado):
    return deriva_reingreso(
        list(cerrados),
        ahora=AHORA,
        min_nodes=MIN_NODES,
        ventana_firma_s=VENTANA_FIRMA_S,
        lookback_pendiente_s=LOOKBACK_S,
    )


# --- 1 · NO HABITAR no caduca ------------------------------------------------------


@pytest.mark.parametrize("hace", [timedelta(hours=9), timedelta(days=3), timedelta(days=400)])
@pytest.mark.parametrize("veredicto", ["no_inhabit_inspect", "restricted"])
def test_un_NO_HABITAR_firmado_NO_caduca(hace: timedelta, veredicto: str) -> None:
    """El defecto 1. Un edificio declarado inhabitable no se vuelve habitable
    porque pase el reloj: sólo lo levanta una firma habitable POSTERIOR."""
    inc = _inc(dictamen=veredicto, firmado=True, firmado_hace=hace, cerrado_hace=hace)
    r = _deriva(inc)
    assert r.fase == "reentry_blocked"
    assert r.razon == "no_habitable"
    assert r.incidente == inc


def test_un_veredicto_firmado_DESCONOCIDO_bloquea() -> None:
    """Default-deny: lo que no está en `HABITABLES` no libera a nadie."""
    r = _deriva(_inc(dictamen="estado_del_futuro", firmado=True))
    assert r.fase == "reentry_blocked" and r.razon == "no_habitable"


# --- 2 · HABITABLE: 8 h desde la FIRMA, no desde el cierre ---------------------------


@pytest.mark.parametrize("veredicto", sorted(HABITABLES))
def test_habitable_firmado_hace_poco_autoriza(veredicto: str) -> None:
    r = _deriva(_inc(dictamen=veredicto, firmado=True, firmado_hace=timedelta(hours=1)))
    assert r.fase == "reentry_approved"
    assert r.razon is None


def test_la_ventana_cuenta_desde_la_FIRMA_no_desde_el_cierre() -> None:
    """Firmado hace 9 h y cerrado hace una: ya no se declara. Contar desde el
    cierre haría que cualquier cierre tardío —el TTL, una limpieza— resucitara
    una autorización que su firmante dio hace días."""
    r = _deriva(
        _inc(
            dictamen="inhabit_monitor",
            firmado=True,
            firmado_hace=timedelta(hours=9),
            cerrado_hace=timedelta(hours=1),
        )
    )
    assert r.fase == "idle"


def test_al_filo_de_la_ventana_ya_no_se_declara() -> None:
    """«hace menos de» — el filo exacto ya no cuenta."""
    r = _deriva(_inc(dictamen="normal_operation", firmado=True, firmado_hace=timedelta(hours=8)))
    assert r.fase == "idle"


def test_un_preliminar_SIN_firma_no_libera() -> None:
    """Un preliminar automático no autoriza a nadie a volver a entrar."""
    r = _deriva(_inc(dictamen="normal_operation", firmado=False))
    assert r.fase == "reentry_blocked"
    assert r.razon == "pendiente_dictamen"


# --- 3 · sin firma: pendiente de dictamen, con cota -----------------------------------


def test_cerrado_sin_dictamen_queda_PENDIENTE() -> None:
    r = _deriva(_inc(cerrado_hace=timedelta(hours=2)))
    assert r.fase == "reentry_blocked"
    assert r.razon == "pendiente_dictamen"


def test_la_espera_del_dictamen_tiene_cota() -> None:
    """Sin cota, un incidente que nadie dictaminó dejaría el edificio bloqueado
    para siempre en la pantalla de alguien que ya volvió a trabajar."""
    assert _deriva(_inc(cerrado_hace=timedelta(days=31))).fase == "idle"


def test_cerrado_sin_hora_no_queda_pendiente() -> None:
    """La base lo prohíbe desde la 0066; si llegara, no se inventa la hora."""
    assert _deriva(_inc(cerrado_hace=None)).fase == "idle"


# --- 4 · quién puede bloquear o autorizar ---------------------------------------------


def test_una_estacion_sola_NO_bloquea_ni_autoriza() -> None:
    """[T-2.105] El defecto 2: un umbral instrumental de un gabinete no ordenó
    evacuar a nadie, así que no hay reingreso que bloquear ni que autorizar."""
    for dictamen, firmado in ((None, False), ("inhabit_monitor", True), ("restricted", True)):
        r = _deriva(_inc(trigger="local_threshold", dictamen=dictamen, firmado=firmado))
        assert r.fase == "idle", (dictamen, firmado)


def test_el_cuorum_de_red_si_cuenta() -> None:
    r = _deriva(
        _inc(trigger="local_threshold", node_count=MIN_NODES, dictamen="restricted", firmado=True)
    )
    assert r.fase == "reentry_blocked" and r.razon == "no_habitable"


@pytest.mark.parametrize("clasificacion", sorted(TERMINALES))
def test_una_clasificacion_TERMINAL_es_idle(clasificacion: str) -> None:
    """Falso positivo, prueba o reproducción: el sismo no ocurrió en ese edificio,
    así que ni bloquea ni autoriza — tampoco con un NO HABITAR firmado encima."""
    r = _deriva(_inc(clasificacion=clasificacion, dictamen="no_inhabit_inspect", firmado=True))
    assert r.fase == "idle"


@pytest.mark.parametrize("clasificacion", sorted(set(CLASIFICACIONES) - TERMINALES))
def test_una_clasificacion_NO_terminal_no_cambia_nada(clasificacion: str) -> None:
    r = _deriva(_inc(clasificacion=clasificacion, dictamen="no_inhabit_inspect", firmado=True))
    assert r.fase == "reentry_blocked"


# --- 5 · varios cerrados: manda el más nuevo QUE TIENE ALGO QUE DECIR --------------------


@pytest.mark.parametrize("al_reves", [False, True], ids=["en_orden", "al_reves"])
def test_manda_el_mas_nuevo_aunque_llegue_desordenado(al_reves: bool) -> None:
    """El orden lo decide `closed_at`, dentro de la función: que un `ORDER BY`
    decidiera lo que lee alguien fuera del edificio es lo que T-7.55 no quiso."""
    viejo = _inc(abierto_hace=timedelta(days=5), cerrado_hace=timedelta(days=5))
    nuevo = _inc(
        abierto_hace=timedelta(hours=3),
        dictamen="normal_operation",
        firmado=True,
        firmado_hace=timedelta(hours=1),
    )
    r = _deriva(*((nuevo, viejo) if al_reves else (viejo, nuevo)))
    assert r.fase == "reentry_approved"
    assert r.incidente == nuevo


def test_el_mas_nuevo_es_el_ultimo_CERRADO_no_el_ultimo_abierto() -> None:
    """[T-9.04] Sin NO HABITAR, decide el candidato cerrado MÁS RECIENTEMENTE.

    A se abre hace 3 días y el TTL lo cierra hace una hora sin que nadie lo
    inspeccione; B se abre hace 2 días y se firma habitable (y se cierra) ese
    mismo día. Por apertura mandaba B —`idle`, la habitable ya caducó—, y el
    ocupante leía la calma sobre un SASMEX que nadie ha visto. Por cierre manda
    A: lo último que se sabe del edificio es que está pendiente de dictamen."""
    a = _inc(abierto_hace=timedelta(days=3), cerrado_hace=timedelta(hours=1))
    b = _inc(
        abierto_hace=timedelta(days=2),
        cerrado_hace=timedelta(days=2),
        dictamen="normal_operation",
        firmado=True,
        firmado_hace=timedelta(days=2),
    )
    r = _deriva(a, b)
    assert r.fase == "reentry_blocked"
    assert r.razon == "pendiente_dictamen"
    assert r.incidente == a


def test_una_habitable_firmada_DESPUES_del_ultimo_cierre_autoriza() -> None:
    """La otra cara: el inspector firma habitable sobre A (abierto hace 3 días)
    hace 30 minutos —firmar lo cierra, `D-33`— y B, abierto después, quedó
    cerrado hace 2 días sin dictamen. La última palabra sobre el edificio es la
    firma de A; por apertura mandaba B y la app decía «pendiente»."""
    a = _inc(
        abierto_hace=timedelta(days=3),
        cerrado_hace=timedelta(minutes=30),
        dictamen="inhabit_monitor",
        firmado=True,
        firmado_hace=timedelta(minutes=30),
    )
    b = _inc(abierto_hace=timedelta(days=2), cerrado_hace=timedelta(days=2))
    r = _deriva(a, b)
    assert r.fase == "reentry_approved"
    assert r.incidente == a


def test_el_mas_nuevo_decide_aunque_diga_idle() -> None:
    """El candidato más nuevo DECIDE, también cuando su veredicto es `idle`
    (habitable ya caducada): no se cae a un pendiente más viejo, porque la
    habitable firmada después de aquel cierre dice que alguien sí inspeccionó."""
    pendiente_viejo = _inc(abierto_hace=timedelta(days=4), cerrado_hace=timedelta(days=4))
    habitable = _inc(
        abierto_hace=timedelta(days=1),
        cerrado_hace=timedelta(days=1),
        dictamen="normal_operation",
        firmado=True,
        firmado_hace=timedelta(days=1),
    )
    assert _deriva(pendiente_viejo, habitable).fase == "idle"


def test_una_habitable_sobre_OTRO_incidente_NO_levanta_el_NO_HABITAR() -> None:
    """[T-9.04 · la ficha] Un NO HABITAR sólo lo levanta un dictamen habitable
    firmado DESPUÉS **sobre ese incidente** — y eso siempre es posible, porque
    `sign_dictamen` no mira el estado. Una habitable sobre otro incidente, aunque
    sea más nuevo, no dice que el daño de ÉSTE se reparó: la app sigue citando el
    NO HABITAR, que es donde el inspector tiene que firmar."""
    viejo = _inc(
        abierto_hace=timedelta(days=5),
        dictamen="no_inhabit_inspect",
        firmado=True,
        firmado_hace=timedelta(days=5),
        cerrado_hace=timedelta(days=5),
    )
    nuevo = _inc(
        abierto_hace=timedelta(days=2),
        dictamen="normal_operation",
        firmado=True,
        firmado_hace=timedelta(hours=1),
    )
    r = _deriva(viejo, nuevo)
    assert r.fase == "reentry_blocked"
    assert r.razon == "no_habitable"
    assert r.incidente == viejo


def test_un_NO_HABITAR_firmado_TARDE_sobre_un_incidente_mas_viejo_bloquea() -> None:
    """[T-9.04] «Más nuevo» no puede decidirse por la apertura del incidente.

    A se abre hace 3 días y B hace 2; B se firma habitable hace 2 días. HOY el
    inspector firma NO HABITAR sobre A: el daño se descubrió tarde. El último
    veredicto firmado sobre el edificio es NO HABITAR, y la app lo pintaba en
    calma porque B se abrió después que A."""
    a = _inc(
        abierto_hace=timedelta(days=3),
        cerrado_hace=timedelta(days=3),
        dictamen="no_inhabit_inspect",
        firmado=True,
        firmado_hace=timedelta(minutes=5),
    )
    b = _inc(
        abierto_hace=timedelta(days=2),
        cerrado_hace=timedelta(days=2),
        dictamen="normal_operation",
        firmado=True,
        firmado_hace=timedelta(days=2),
    )
    r = _deriva(a, b)
    assert r.fase == "reentry_blocked"
    assert r.razon == "no_habitable"
    assert r.incidente == a


def test_un_PENDIENTE_mas_nuevo_NO_tapa_un_NO_HABITAR() -> None:
    """[T-9.04] Precedencia `no_habitable` > `pendiente_*`.

    A: SASMEX con NO HABITAR firmado hace 2 días. B: la réplica SASMEX de hace
    6 h, cerrada por TTL sin dictamen —el edificio ya estaba cerrado, nadie lo
    inspeccionó—. Parar en B bajaba el cartel rojo a una franja ámbar y citaba
    el incidente equivocado. Las réplicas son lo normal justo después del sismo
    que provoca un NO HABITAR."""
    a = _inc(
        abierto_hace=timedelta(days=2),
        cerrado_hace=timedelta(days=2),
        dictamen="no_inhabit_inspect",
        firmado=True,
        firmado_hace=timedelta(days=2),
    )
    b = _inc(abierto_hace=timedelta(hours=6), cerrado_hace=timedelta(hours=1))
    r = _deriva(a, b)
    assert r.fase == "reentry_blocked"
    assert r.razon == "no_habitable"
    assert r.incidente == a


def test_con_varios_NO_HABITAR_se_cita_el_firmado_mas_recientemente() -> None:
    """Todos bloquean; la app cita el último veredicto que se firmó, no el
    incidente que se abrió después."""
    firmado_antes = _inc(
        abierto_hace=timedelta(days=2),
        dictamen="restricted",
        firmado=True,
        firmado_hace=timedelta(days=2),
    )
    firmado_despues = _inc(
        abierto_hace=timedelta(days=4),
        dictamen="no_inhabit_inspect",
        firmado=True,
        firmado_hace=timedelta(hours=1),
    )
    r = _deriva(firmado_antes, firmado_despues)
    assert r.razon == "no_habitable" and r.incidente == firmado_despues


def test_una_prueba_posterior_NO_levanta_un_NO_HABITAR() -> None:
    """⚠️ Un incidente clasificado como prueba/reproducción/falso positivo no
    ocurrió: no dice nada del edificio. Si mandara por ser el más nuevo, probar
    el WR-1 un martes desbloquearía un inmueble dictaminado inhabitable."""
    viejo = _inc(
        abierto_hace=timedelta(days=5),
        dictamen="no_inhabit_inspect",
        firmado=True,
        firmado_hace=timedelta(days=5),
        cerrado_hace=timedelta(days=5),
    )
    prueba = _inc(abierto_hace=timedelta(hours=1), clasificacion="prueba")
    r = _deriva(viejo, prueba)
    assert r.fase == "reentry_blocked"
    assert r.razon == "no_habitable"
    assert r.incidente == viejo


def test_un_cerrado_SIN_veredicto_y_fuera_de_la_espera_NO_levanta_nada() -> None:
    """Sin firma no hay veredicto: un incidente que nadie dictaminó no puede
    liberar lo que un inspector sí dictaminó antes."""
    viejo = _inc(
        abierto_hace=timedelta(days=90),
        dictamen="no_inhabit_inspect",
        firmado=True,
        firmado_hace=timedelta(days=90),
        cerrado_hace=timedelta(days=90),
    )
    sin_veredicto = _inc(abierto_hace=timedelta(days=40), cerrado_hace=timedelta(days=40))
    r = _deriva(viejo, sin_veredicto)
    assert r.fase == "reentry_blocked" and r.incidente == viejo


def test_un_local_nuevo_no_tapa_al_autorizante() -> None:
    viejo = _inc(abierto_hace=timedelta(days=1), dictamen="restricted", firmado=True)
    local = _inc(
        trigger="local_threshold",
        abierto_hace=timedelta(hours=1),
        dictamen="normal_operation",
        firmado=True,
    )
    assert _deriva(viejo, local).incidente == viejo


def test_sin_cerrados_es_idle() -> None:
    r = _deriva()
    assert r.fase == "idle" and r.razon is None and r.incidente is None


# --- 6 · el contrato -----------------------------------------------------------------


def test_las_razones_son_las_del_contrato() -> None:
    """`pendiente_confirmacion` se RESERVA en el tipo (lo usa F3) aunque hoy
    ninguna regla lo produzca: añadir un valor a un `Literal` publicado es la
    forma de que el `switch` de la app lo declare antes de recibirlo."""
    from takab_api.schemas.mobile import MobileReentryOut

    razones = set(typing.get_args(RazonBloqueo))
    assert razones == {"no_habitable", "pendiente_dictamen", "pendiente_confirmacion"}
    anotacion = MobileReentryOut.model_fields["reason"].annotation
    publicadas = {a for arg in typing.get_args(anotacion) for a in typing.get_args(arg)}
    assert publicadas == razones


# ── [T-9.32 · D-43] pendiente de CONFIRMACIÓN ─────────────────────────────────


def test_un_AMARILLO_de_la_regla_sin_firmar_es_PENDIENTE_DE_CONFIRMACION() -> None:
    r = _deriva(_inc(dictamen="inhabit_monitor", banda="amarillo"))
    assert (r.fase, r.razon) == ("reentry_blocked", "pendiente_confirmacion")


@pytest.mark.parametrize(
    ("dictamen", "banda"),
    [("no_inhabit_inspect", "rojo"), ("inhabit_monitor", None), ("normal_operation", "verde")],
)
def test_sin_firmar_y_no_amarillo_sigue_PENDIENTE_DE_DICTAMEN(dictamen: str, banda) -> None:
    """Un ROJO lo firma el inspector; una fila histórica no tiene banda; el VERDE lo
    firma el sistema tras la gracia. Ninguno espera una confirmación."""
    r = _deriva(_inc(dictamen=dictamen, banda=banda))
    assert (r.fase, r.razon) == ("reentry_blocked", "pendiente_dictamen")


def test_un_AMARILLO_CONFIRMADO_autoriza() -> None:
    r = _deriva(_inc(dictamen="inhabit_monitor", banda="amarillo", firmado=True))
    assert r.fase == "reentry_approved"


# ── 1b · [F3·r2 · D-43] ROJO de la regla SIN FIRMAR ─────────────────────────────


def test_rojo_sin_firmar_viejo_gana_a_una_replica_verde_firmada_posterior() -> None:
    principal = _inc(
        abierto_hace=timedelta(days=60),
        cerrado_hace=timedelta(days=59),
        dictamen="no_inhabit_inspect",
        banda="rojo",
        firmado_hace=timedelta(days=58),
    )
    replica = _inc(
        abierto_hace=timedelta(hours=3),
        cerrado_hace=timedelta(hours=1),
        dictamen="normal_operation",
        banda="verde",
        firmado=True,
        firmado_hace=timedelta(hours=2),
    )
    r = _deriva(replica, principal)
    assert r.fase == "reentry_blocked"
    assert r.razon == "pendiente_dictamen"
    assert r.incidente == principal


def test_un_no_habitar_firmado_sigue_antes_que_la_regla_1b() -> None:
    rojo = _inc(dictamen="no_inhabit_inspect", banda="rojo", firmado_hace=timedelta(hours=1))
    firmado = _inc(dictamen="no_inhabit_inspect", firmado=True, firmado_hace=timedelta(days=2))
    r = _deriva(rojo, firmado)
    assert r.razon == "no_habitable" and r.incidente == firmado


def test_la_regla_1b_no_toca_filas_v1_sin_banda() -> None:
    viejo = _inc(
        abierto_hace=timedelta(days=60),
        cerrado_hace=timedelta(days=59),
        dictamen="no_inhabit_inspect",
        banda=None,
    )
    assert _deriva(viejo).fase == "idle"
