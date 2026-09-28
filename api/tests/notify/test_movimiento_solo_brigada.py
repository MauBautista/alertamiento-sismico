"""[T-9.11 · D-39] Un movimiento de UN SOLO inmueble despierta a su brigada, no a sus ocupantes.

El pedido del cliente tras la presentación del 24-sep: «para no difundir el pánico». Al
revisarlo se midió que el orquestador NUNCA miraba el disparador: un golpe cerca del
sensor mandaba «ALERTA SÍSMICA» por el canal que ignora el No Molestar a TODOS los
teléfonos del sitio.

La regla (una tabla pura, `notify/circulo.py::push_target_for`):

  · local sin corroborar en DISPARO (`restricted`/`evacuate_or_hold` ⇒ severity
    `warning`/`critical`) ⇒ push MOVEMENT solo a los roles de `movement_alert`;
  · local en CAUTELA (`watch`) ⇒ ningún teléfono (se queda en consola y panel);
  · lo que autoriza evacuar (SASMEX, cuórum de red) ⇒ CRISIS a TODO el inmueble;
  · un pánico manual ⇒ nada por aquí: lo lleva `_enqueue_panic_push` (D-05).

Y dos caminos de SUBIDA que la primera pasada no ve: un local que pasa de CAUTELA a
DISPARO (ahora sí despierta a la brigada) y uno que escala a SASMEX/cuórum sin haber
mandado push nunca (la escalada de T-9.03 avisa a todos).
"""

from __future__ import annotations

import uuid

import pytest

from takab_api.auth.matrix import roles_with_action
from takab_api.notify.circulo import SEVERIDADES_DE_DISPARO, push_target_for
from takab_api.notify.orchestrator import _PUSH_DEVICES_BY_ROLE_SQL
from takab_api.notify.push import PUSH_CLASS_CRISIS, PUSH_CLASS_MOVEMENT, PUSH_CLASS_PANIC
from tests.notify.test_escalada_avisa_a_todos import _Escena, esc  # noqa: F401
from tests.notify.test_orchestrator import _Scenario, scenario  # noqa: F401

MOVIMIENTO = set(roles_with_action("movement_alert"))


# --- la tabla pura -------------------------------------------------------------------


def test_el_circulo_del_movimiento_es_la_brigada_y_nunca_el_ocupante() -> None:
    assert {"brigadista", "inspector", "tenant_admin"} <= MOVIMIENTO
    assert "occupant" not in MOVIMIENTO
    assert "gov_operator" not in MOVIMIENTO


@pytest.mark.parametrize("severity", sorted(SEVERIDADES_DE_DISPARO))
def test_local_en_DISPARO_va_a_la_brigada_con_voz(severity: str) -> None:
    destino = push_target_for(trigger="local_threshold", severity=severity, autoriza=False)
    assert destino is not None
    assert destino.push_class == PUSH_CLASS_MOVEMENT
    assert set(destino.roles or ()) == MOVIMIENTO


@pytest.mark.parametrize("severity", ["watch", "info"])
def test_local_en_CAUTELA_no_despierta_a_nadie(severity: str) -> None:
    assert push_target_for(trigger="local_threshold", severity=severity, autoriza=False) is None


@pytest.mark.parametrize(
    ("trigger", "severity"),
    [
        ("sasmex", "critical"),
        ("sasmex", "watch"),
        ("quorum", "warning"),
        ("local_threshold", "critical"),
    ],
)
def test_lo_que_autoriza_evacuar_va_a_TODOS(trigger: str, severity: str) -> None:
    destino = push_target_for(trigger=trigger, severity=severity, autoriza=True)
    assert destino is not None
    assert destino.push_class == PUSH_CLASS_CRISIS
    assert destino.roles is None, "una orden de evacuar con círculo dejaría fuera al ocupante"


def test_un_panico_manual_no_sale_por_aqui() -> None:
    assert push_target_for(trigger="manual", severity="critical", autoriza=False) is None


# --- contra el worker real -------------------------------------------------------------


def _sitio(e: _Escena, incidente: str) -> str:
    return str(
        e.conn.execute(
            "SELECT site_id FROM incidents WHERE incident_id = %s", (incidente,)
        ).fetchone()["site_id"]
    )


def _telefono(e: _Escena, sitio: str, rol: str | None) -> str:
    """Un teléfono con el ROL de quien lo tiene (`push_tokens.role`, T-9.05)."""
    token = str(uuid.uuid4())
    e.conn.execute(
        "INSERT INTO push_tokens (push_token_id, tenant_id, user_sub, platform, token, "
        "site_id, role) VALUES (%s,%s,%s,'android',%s,%s,%s)",
        (token, e.sc.tenant, str(uuid.uuid4()), f"tok-{token}", sitio, rol),
    )
    e.conn.commit()
    return token


def _local_con_dos_telefonos(e: _Escena, severity: str) -> tuple[str, str, str]:
    incidente = e.sc.seed_incident(trigger="local_threshold", severity=severity)
    sitio = _sitio(e, incidente)
    return incidente, _telefono(e, sitio, "occupant"), _telefono(e, sitio, "brigadista")


def _alcanzados(e: _Escena) -> set[str]:
    return {d.push_token_id for devices, _ in e.push.entregas for d in devices}


def test_local_en_DISPARO_despierta_SOLO_a_la_brigada(esc: _Escena) -> None:  # noqa: F811
    incidente, ocupante, brigada = _local_con_dos_telefonos(esc, "critical")

    esc.pasada()

    [job] = esc.push_de_incidente(incidente)
    assert job["target"]["push_class"] == PUSH_CLASS_MOVEMENT
    assert job["target"]["autoriza"] is False
    assert brigada in _alcanzados(esc)
    assert ocupante not in _alcanzados(esc), (
        "el ocupante recibió el aviso de un movimiento que solo sintió su edificio: "
        "es el pánico que el cliente pidió no difundir (D-39)"
    )
    [(_, payload)] = esc.push.entregas
    assert "building_movement" in str(payload)


def test_local_en_CAUTELA_no_encola_push(esc: _Escena) -> None:  # noqa: F811
    incidente, _, _ = _local_con_dos_telefonos(esc, "watch")

    esc.pasada()

    assert esc.push_de_incidente(incidente) == []
    assert _alcanzados(esc) == set()


def test_de_CAUTELA_a_DISPARO_despierta_entonces_a_la_brigada(esc: _Escena) -> None:  # noqa: F811
    incidente, ocupante, brigada = _local_con_dos_telefonos(esc, "watch")
    esc.pasada()
    assert esc.push_de_incidente(incidente) == []

    esc.actualizar(incidente, severity="warning")
    esc.pasada(5)

    [job] = esc.push_de_incidente(incidente)
    assert job["target"]["push_class"] == PUSH_CLASS_MOVEMENT
    assert brigada in _alcanzados(esc)
    assert ocupante not in _alcanzados(esc)

    esc.pasada(10)
    assert len(esc.push_de_incidente(incidente)) == 1, "la subida no es idempotente"


def test_de_CAUTELA_a_SASMEX_sin_push_previo_avisa_a_TODOS(esc: _Escena) -> None:  # noqa: F811
    incidente, ocupante, brigada = _local_con_dos_telefonos(esc, "watch")
    esc.pasada()

    esc.actualizar(incidente, trigger="sasmex", severity="critical")
    esc.pasada(5)

    assert len(esc.escaladas(incidente)) == 1
    [job] = esc.push_de_escalada(incidente)
    assert job["target"]["push_class"] == PUSH_CLASS_CRISIS
    assert {ocupante, brigada} <= _alcanzados(esc), (
        "el SASMEX llegó a un incidente que nunca había mandado push y nadie se enteró"
    )


def test_de_DISPARO_a_SASMEX_la_escalada_avisa_a_TODOS(esc: _Escena) -> None:  # noqa: F811
    incidente, ocupante, _ = _local_con_dos_telefonos(esc, "critical")
    esc.pasada()
    assert ocupante not in _alcanzados(esc)

    esc.actualizar(incidente, trigger="sasmex")
    esc.pasada(5)

    [job] = esc.push_de_escalada(incidente)
    assert job["target"]["push_class"] == PUSH_CLASS_CRISIS
    assert ocupante in _alcanzados(esc)


def test_SASMEX_va_a_TODOS(esc: _Escena) -> None:  # noqa: F811
    incidente = esc.sc.seed_incident(trigger="sasmex", severity="critical")
    sitio = _sitio(esc, incidente)
    ocupante, brigada = _telefono(esc, sitio, "occupant"), _telefono(esc, sitio, "brigadista")

    esc.pasada()

    [job] = esc.push_de_incidente(incidente)
    assert job["target"]["push_class"] == PUSH_CLASS_CRISIS
    assert "roles" not in job["target"]
    assert {ocupante, brigada} <= _alcanzados(esc)


def test_un_panico_con_telefonos_sale_UNA_vez_y_como_PANICO(esc: _Escena) -> None:  # noqa: F811
    """Con teléfonos registrados, `_enqueue` metía un push CRISIS a todo el edificio
    antes que `_enqueue_panic_push`, cuyo `NOT EXISTS` entonces lo saltaba: una
    activación manual sonaba como «ALERTA SÍSMICA» en los 400 teléfonos (D-05)."""
    incidente = esc.sc.seed_incident(trigger="manual", severity="critical")
    sitio = _sitio(esc, incidente)
    ocupante = _telefono(esc, sitio, "occupant")
    _telefono(esc, sitio, "brigadista")

    esc.pasada()

    [job] = esc.push_de_incidente(incidente)
    assert job["target"]["push_class"] == PUSH_CLASS_PANIC
    assert ocupante not in _alcanzados(esc)


def test_el_rol_del_telefono_basta_sin_asignacion_de_zona(esc: _Escena) -> None:  # noqa: F811
    """Los tácticos no tienen fila en `user_zone_assignments`: sin `push_tokens.role`
    (T-9.05) el círculo por rol no encontraba a nadie."""
    incidente = esc.sc.seed_incident(trigger="local_threshold", severity="critical")
    sitio = _sitio(esc, incidente)
    brigada = _telefono(esc, sitio, "brigadista")
    ocupante = _telefono(esc, sitio, "occupant")
    filas = esc.conn.execute(
        _PUSH_DEVICES_BY_ROLE_SQL,
        {
            "site": sitio,
            "tenant": esc.sc.tenant,
            "roles": sorted(MOVIMIENTO),
            "roles_cliente": ["tenant_admin"],
        },
    ).fetchall()
    alcanzados = {str(f["push_token_id"]) for f in filas}
    assert brigada in alcanzados
    assert ocupante not in alcanzados


# --- lo que la revisión de F1 encontró ------------------------------------------------


def _telefono_del_cliente(e: _Escena, rol: str, *, tenant: str | None = None) -> str:
    """Un teléfono SIN inmueble (`site_id` NULL): el del administrador, que ve todo su
    cliente (D-42) y no tiene un solo edificio que vigilar."""
    token = str(uuid.uuid4())
    e.conn.execute(
        "INSERT INTO push_tokens (push_token_id, tenant_id, user_sub, platform, token, "
        "site_id, role) VALUES (%s,%s,%s,'android',%s,NULL,%s)",
        (token, tenant or e.sc.tenant, str(uuid.uuid4()), f"tok-{token}", rol),
    )
    e.conn.commit()
    return token


def test_el_ADMINISTRADOR_sin_inmueble_recibe_el_movimiento(esc: _Escena) -> None:  # noqa: F811
    """El administrador tiene alcance `*`: su teléfono no pertenece a UN edificio, y con
    el filtro `site_id = <sitio>` no le llegaba nada —ni el movimiento que D-39 le
    manda atender ni el SASMEX—."""
    incidente = esc.sc.seed_incident(trigger="local_threshold", severity="critical")
    _telefono(esc, _sitio(esc, incidente), "occupant")
    admin = _telefono_del_cliente(esc, "tenant_admin")

    esc.pasada()

    [job] = esc.push_de_incidente(incidente)
    assert job["target"]["push_class"] == PUSH_CLASS_MOVEMENT
    assert admin in _alcanzados(esc)


def test_el_ADMINISTRADOR_sin_inmueble_recibe_el_SASMEX(esc: _Escena) -> None:  # noqa: F811
    esc.sc.seed_incident(trigger="sasmex", severity="critical")
    admin = _telefono_del_cliente(esc, "tenant_admin")

    esc.pasada()

    assert admin in _alcanzados(esc), "el administrador no se enteró de un SASMEX en su cliente"


def test_un_telefono_SIN_inmueble_que_no_es_del_cliente_entero_no_recibe(esc: _Escena) -> None:  # noqa: F811
    """El defecto de T-2.109 sigue declarado: un token de ocupante con `site_id` NULL
    no es destinatario de nada (la app lo mandaba así por error)."""
    incidente = esc.sc.seed_incident(trigger="sasmex", severity="critical")
    _telefono(esc, _sitio(esc, incidente), "occupant")
    huerfano = _telefono_del_cliente(esc, "occupant")
    sin_rol = _telefono_del_cliente(esc, None)  # type: ignore[arg-type]

    esc.pasada()

    assert huerfano not in _alcanzados(esc)
    assert sin_rol not in _alcanzados(esc)


def test_el_ADMINISTRADOR_de_OTRO_cliente_no_recibe(esc: _Escena) -> None:  # noqa: F811
    esc.sc.seed_incident(trigger="sasmex", severity="critical")
    otro = esc.sc.seed_tenant()
    ajeno = _telefono_del_cliente(esc, "tenant_admin", tenant=otro)

    esc.pasada()

    assert ajeno not in _alcanzados(esc), "un aviso cruzó de cliente (regla de oro 5)"


def test_una_subida_pasada_la_HORA_sigue_despertando_a_la_brigada(esc: _Escena) -> None:  # noqa: F811
    """La ventana era `notify_lookback_s` (una hora) desde la APERTURA: un local que
    seguía abierto en CAUTELA más de una hora y luego subía a DISPARO, o ganaba
    SASMEX, no despertaba a nadie."""
    incidente, ocupante, brigada = _local_con_dos_telefonos(esc, "watch")
    esc.pasada()

    esc.actualizar(incidente, severity="critical")
    esc.pasada(3601)
    assert brigada in _alcanzados(esc)
    assert ocupante not in _alcanzados(esc)

    esc.actualizar(incidente, trigger="sasmex")
    esc.pasada(3700)
    assert len(esc.escaladas(incidente)) == 1
    assert ocupante in _alcanzados(esc)


def test_un_telefono_con_ROL_VIEJO_guardado_sigue_en_el_circulo(esc: _Escena) -> None:  # noqa: F811
    """[T-9.20 · D-42] La 0072 canoniza `push_tokens.role`, pero un teléfono que no se ha
    vuelto a abrir puede traer aún `security_guard`: sigue siendo de la brigada."""
    incidente = esc.sc.seed_incident(trigger="local_threshold", severity="critical")
    sitio = _sitio(esc, incidente)
    guardia = _telefono(esc, sitio, "security_guard")
    ocupante = _telefono(esc, sitio, "occupant")

    esc.pasada()

    assert guardia in _alcanzados(esc)
    assert ocupante not in _alcanzados(esc)
