"""[T-2.147.a · D-05 · D-11] El push del pánico: solo a los tácticos.

`D-05` decidió que una activación manual **despierta a quien tiene que actuar, y
a nadie más**. La sirena ya suena y la app ya explica la alarma; lo único que
añade el push es que vibre el teléfono de alguien dormido, y eso solo aporta
valor para la brigada. Dos personas no deben poder despertar a 400: un pánico
falso a las 3 a.m. quema la credibilidad que hace que la gente obedezca la
SIGUIENTE alerta, que puede ser la de verdad.

DÓNDE VIVE ESTO, Y POR QUÉ NO EN EL ROUTER
-------------------------------------------
`notification_jobs` tiene RLS que solo admite escrituras de los roles internos
de TAKAB: los jobs los crea el worker. Una petición de occupant no lo es, y
debilitar esa política para que el teléfono de un ocupante pudiera encolar
notificaciones sería mover la frontera equivocada. El router deja el HECHO —un
incidente `trigger='manual'`— y el worker lo recoge; de paso hereda gratis la
idempotencia, el reintento con backoff y la cuarentena de canal caído.

LA PROPIEDAD QUE JUSTIFICA EL ARCHIVO
--------------------------------------
`test_el_occupant_del_mismo_sitio_queda_FUERA` es la diferencia entre la opción
(B) que se eligió y la (A) que se descartó. Si el filtro fallara, el sistema
despertaría al edificio entero y no se notaría hasta el primer pánico falso de
madrugada, delante de todo el mundo.
"""

from __future__ import annotations

import uuid

import pytest

from takab_api.auth.matrix import roles_with_action
from takab_api.notify.orchestrator import _PUSH_DEVICES_BY_ROLE_SQL, run_notify_pass
from takab_api.notify.push import PUSH_CLASS_CRISIS, PUSH_CLASS_PANIC
from takab_api.settings import Settings
from tests.notify.test_orchestrator import (  # noqa: F401
    BASE,
    _providers,
    _Scenario,
    scenario,
)

TACTICO = "brigadista"


def _sitio_del_incidente(sc: _Scenario, incident_id: str) -> str:
    return sc.conn.execute(
        "SELECT site_id FROM incidents WHERE incident_id = %s", (incident_id,)
    ).fetchone()["site_id"]


def _asignar(sc: _Scenario, site: str, user: str, role: str) -> None:
    sc.conn.execute(
        "INSERT INTO user_zone_assignments (user_id, tenant_id, site_id, role) "
        "VALUES (%s,%s,%s,%s)",
        (user, sc.tenant, site, role),
    )
    sc.conn.commit()


def _token(sc: _Scenario, site: str, user: str) -> str:
    token_id = str(uuid.uuid4())
    sc.conn.execute(
        "INSERT INTO push_tokens (push_token_id, tenant_id, user_sub, platform, token, site_id) "
        "VALUES (%s,%s,%s,'android',%s,%s)",
        (token_id, sc.tenant, user, f"tok-{token_id}", site),
    )
    sc.conn.commit()
    return token_id


def _push_jobs(sc: _Scenario, incident_id: str) -> list[dict]:
    return [j for j in sc.jobs(incident_id) if j["channel"] == "push"]


# --- El encolado -------------------------------------------------------------


def test_un_panico_encola_su_push_con_el_circulo_acotado(scenario: _Scenario) -> None:  # noqa: F811
    """El worker recoge el incidente `manual` y le pone su job."""
    incident = scenario.seed_incident(trigger="manual", severity="critical")
    scenario.seed_config()

    run_notify_pass(scenario.conn, Settings(), _providers(), now=BASE)

    jobs = _push_jobs(scenario, incident)
    assert len(jobs) == 1, f"se esperaba un push del pánico, hay {len(jobs)}"
    job = jobs[0]
    assert job["mode"] == "parallel", "el push del pánico no escala: es una sola voz"

    target = job["target"]
    assert target["push_class"] == PUSH_CLASS_PANIC, (
        f"salió como {target['push_class']!r}; con {PUSH_CLASS_CRISIS} sonaría el "
        "tono del SASMEX sobre una activación manual (la mentira de T-2.104)"
    )
    assert set(target["roles"]) == set(roles_with_action("manual_activate")), (
        "el círculo no coincide con la matriz: se escribió a mano y ya divergió"
    )
    assert "occupant" not in target["roles"], (
        "el círculo incluye al occupant: eso es la opción (A) —despertar a todo "
        "el edificio— implementada por accidente"
    )


def test_una_segunda_pasada_no_duplica_el_push(scenario: _Scenario) -> None:  # noqa: F811
    """Idempotencia. Sin ella, el worker manda un push por pasada mientras el
    incidente siga dentro de la ventana — o sea martillear a la brigada."""
    incident = scenario.seed_incident(trigger="manual", severity="critical")
    scenario.seed_config()

    run_notify_pass(scenario.conn, Settings(), _providers(), now=BASE)
    run_notify_pass(scenario.conn, Settings(), _providers(), now=BASE)

    assert len(_push_jobs(scenario, incident)) == 1, "la segunda pasada duplicó el push del pánico"


def test_un_incidente_SISMICO_no_recibe_el_push_del_panico(scenario: _Scenario) -> None:  # noqa: F811
    """No-vacuidad por el otro lado: el trigger es lo que selecciona, no la hora.

    Si el escaneo cogiera cualquier incidente reciente, un sismo real saldría
    con la clase PANIC —sin el tono sísmico— y sería el defecto de T-2.104 al
    revés: quitarle el tono de evacuación a algo que sí lo merece.
    """
    incident = scenario.seed_incident(trigger="sasmex", severity="critical")
    scenario.seed_config()

    run_notify_pass(scenario.conn, Settings(), _providers(), now=BASE)

    clases = {j["target"].get("push_class") for j in _push_jobs(scenario, incident)}
    assert PUSH_CLASS_PANIC not in clases, (
        f"un incidente sísmico recibió la clase del pánico: {clases}"
    )


# --- EL FILTRO POR ROL, que es el punto entero -------------------------------


def test_el_occupant_del_mismo_sitio_queda_FUERA(scenario: _Scenario) -> None:  # noqa: F811
    """LA PROPIEDAD DE `D-05`, medida sobre el SQL que el worker usa de verdad.

    Mismo sitio, mismo tenant, token vivo: lo único que separa al táctico del
    occupant es su fila en `user_zone_assignments`. Si el JOIN no filtrara, los
    dos entrarían — y el sistema despertaría al edificio entero.
    """
    incident = scenario.seed_incident(trigger="manual", severity="critical")
    site = _sitio_del_incidente(scenario, incident)

    ocupante, brigada = str(uuid.uuid4()), str(uuid.uuid4())
    _asignar(scenario, site, ocupante, "occupant")
    _asignar(scenario, site, brigada, TACTICO)
    tok_ocupante = _token(scenario, site, ocupante)
    tok_brigada = _token(scenario, site, brigada)

    filas = scenario.conn.execute(
        _PUSH_DEVICES_BY_ROLE_SQL,
        {
            "site": site,
            "tenant": scenario.tenant,
            "roles": list(roles_with_action("manual_activate")),
        },
    ).fetchall()
    alcanzados = {str(f["push_token_id"]) for f in filas}

    assert tok_brigada in alcanzados, (
        "el táctico NO recibiría el push: el filtro por rol se pasó de estricto y "
        "el pánico no despierta a nadie"
    )
    assert tok_ocupante not in alcanzados, (
        "el occupant del mismo sitio recibiría el push del pánico: eso es "
        "despertar a todo el edificio, que es exactamente lo que D-05 descartó"
    )


def test_sin_filtro_de_rol_los_dos_entran(scenario: _Scenario) -> None:  # noqa: F811
    """NO-VACUIDAD del test anterior, y es la mitad que lo hace creíble.

    Si el sitio tuviera un solo dispositivo, «el occupant no está» pasaría por
    no haber occupant. Aquí se comprueba que **con el círculo abierto los dos
    aparecen**: entonces la exclusión de arriba la produce el filtro y no el
    escenario.
    """
    incident = scenario.seed_incident(trigger="manual", severity="critical")
    site = _sitio_del_incidente(scenario, incident)

    ocupante, brigada = str(uuid.uuid4()), str(uuid.uuid4())
    _asignar(scenario, site, ocupante, "occupant")
    _asignar(scenario, site, brigada, TACTICO)
    _token(scenario, site, ocupante)
    _token(scenario, site, brigada)

    filas = scenario.conn.execute(
        _PUSH_DEVICES_BY_ROLE_SQL,
        {"site": site, "tenant": scenario.tenant, "roles": ["occupant", TACTICO]},
    ).fetchall()
    assert len(filas) == 2, (
        f"con los dos roles en el círculo se esperaban 2 dispositivos, hay {len(filas)}: "
        "el escenario no monta lo que el test de exclusión cree medir"
    )


def test_un_tactico_de_OTRO_sitio_no_entra(scenario: _Scenario) -> None:  # noqa: F811
    """El rol no basta: el push es del INMUEBLE donde pulsaron el pánico.

    Un brigadista de otra torre del mismo cliente no tiene nada que hacer a las
    3 a.m. con una alarma que no es suya.
    """
    incident = scenario.seed_incident(trigger="manual", severity="critical")
    otro_incident = scenario.seed_incident(trigger="manual", severity="critical")
    site = _sitio_del_incidente(scenario, incident)
    otro_site = _sitio_del_incidente(scenario, otro_incident)

    forastero = str(uuid.uuid4())
    _asignar(scenario, otro_site, forastero, TACTICO)
    tok_forastero = _token(scenario, otro_site, forastero)

    filas = scenario.conn.execute(
        _PUSH_DEVICES_BY_ROLE_SQL,
        {
            "site": site,
            "tenant": scenario.tenant,
            "roles": list(roles_with_action("manual_activate")),
        },
    ).fetchall()
    assert tok_forastero not in {str(f["push_token_id"]) for f in filas}, (
        "un táctico de otro inmueble recibiría el push de esta alarma"
    )


@pytest.mark.parametrize("rol", ["occupant"])
def test_los_roles_no_tacticos_nunca_estan_en_el_circulo(rol: str) -> None:
    """Guarda sobre la MATRIZ, no sobre el escenario.

    Si algún día `manual_activate` se le concediera al occupant, este test cae
    antes de que nadie lo descubra por un teléfono sonando de madrugada. La
    decisión de D-05 se apoya en que ese rol NO puede disparar a mano.
    """
    assert rol not in roles_with_action("manual_activate"), (
        f"{rol!r} ganó `manual_activate` en la matriz: el push del pánico pasaría "
        "a alcanzarlo y D-05 quedaría derogada por un cambio de permisos"
    )
