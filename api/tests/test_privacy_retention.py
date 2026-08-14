"""T-2.81 · Retención de PII con la excepción de compliance CODIFICADA en el job.

QUÉ SE MIDE AQUÍ Y POR QUÉ ASÍ
──────────────────────────────
La ficha pide tres cosas:

1. la excepción de compliance está **codificada en el job**, no escrita en un
   comentario;
2. si el job intenta podar una tabla protegida, **falla ruidosamente**;
3. el **simulacro con conteos** es obligatorio antes de podar nada.

El criterio 2 solo significa algo si el intento es EXPRESABLE. Un job que no
tuviera manera de pedir "borra filas de `audit_log`" haría pasar el test sin
probar nada — el mismo defecto que la T-2.70.a: un test que verifica que algo no
está anclado, sin anclarlo, no verifica nada. Por eso ``RetentionRule`` admite el
modo ``DELETE_ROWS`` aunque el plan que se despacha **no use ninguno**: la
sección C construye la regla asesina a mano y comprueba que el job se niega
ANTES de tocar la base, y la sección B comprueba que además no podría aunque
quisiera.

EL PUNTO QUE MÁS IMPORTA: CON QUÉ ROL CORRE EL JOB
──────────────────────────────────────────────────
La T-2.80 dejó ``REVOKE DELETE`` sobre doce tablas para ``takab_app``. Esa capa
protege a la API… y no protegería a este job si el job se conectara con otro
rol. El DSN de estos tests es exactamente ese peligro hecho carne: ``takab`` es
**SUPERUSER y BYPASSRLS**, o sea que se salta el privilegio, se salta la RLS y
—vía ``session_replication_role``— podría hasta saltarse los triggers.

Por eso el job **se degrada a sí mismo**: abre la transacción con ``SET LOCAL
ROLE`` y luego COMPRUEBA contra el catálogo vivo que el rol resultante no es
superusuario, no tiene BYPASSRLS y no conserva ``DELETE`` sobre ninguna tabla
protegida. La sección D corre esa degradación desde el DSN superusuario: si
alguien la rompe, estos tests son los que lo dicen.
"""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest

from conftest import (
    GOV_AGENCY,
    INC_A,
    SITE_A,
    SITE_B,
    TENANT_A,
    TENANT_B,
    reset,
    use,
)
from takab_api.db import session
from takab_api.ops import prune_pii
from takab_api.privacy import erasure, retention

USER_A = "aaaa0000-0000-0000-0000-0000000a2c01"
USER_A2 = "aaaa0000-0000-0000-0000-0000000a2c02"
USER_B = "bbbb0000-0000-0000-0000-0000000b2c01"

PUNTO = "ST_SetSRID(ST_MakePoint(-99.1332,19.4326),4326)::geography"

#: Las cinco que la regla de oro 11 nombra explícitamente. No es la lista que el
#: job usa —esa la DERIVA del catálogo— sino el control de que la derivación las
#: encuentra. Si la derivación se rompiera y devolviera un conjunto vacío o
#: parcial, este parámetro es el que lo caza.
COMPLIANCE = (
    "audit_log",
    "incident_actions",
    "dictamens",
    "evidence_objects",
    "damage_reports",
)


# ---------------------------------------------------------------------------
# Siembra
# ---------------------------------------------------------------------------


def _token(
    conn: psycopg.Connection,
    *,
    tenant: str = TENANT_A,
    user: str = USER_A,
    site: str | None = SITE_A,
    valor: str,
    dias: int,
) -> None:
    """Un push token visto por última vez hace ``dias`` días."""
    conn.execute(
        "INSERT INTO push_tokens (tenant_id, user_sub, platform, token, site_id, "
        "endpoint_arn, created_at, last_seen_at) "
        "VALUES (%s,%s,'android',%s,%s,'arn:aws:sns:us-east-2:1:endpoint/x',"
        "        now() - make_interval(days => %s), now() - make_interval(days => %s))",
        (tenant, user, valor, site, dias, dias),
    )


def _checkin(
    conn: psycopg.Connection,
    *,
    tenant: str = TENANT_A,
    user: str = USER_A,
    site: str = SITE_A,
    incidente: str | None = INC_A,
    dias: int,
    con_geom: bool = True,
) -> None:
    """Un check-in de vida creado hace ``dias`` días.

    ``created_at`` se fija en el INSERT y no por UPDATE a propósito: el trigger
    ``life_checkin_arco_guard()`` solo admite ``geom → NULL``, así que envejecer
    una fila a posteriori es imposible incluso para el superusuario. Que el
    andamio del test choque con el guard es, en sí, una señal de que el guard
    está puesto.
    """
    geom = PUNTO if con_geom else "NULL"
    conn.execute(
        "INSERT INTO life_checkins (tenant_id, incident_id, user_id, site_id, status, "
        f"geom, created_at) VALUES (%s,%s,%s,%s,'safe',{geom}, "
        "now() - make_interval(days => %s))",
        (tenant, incidente, user, site, dias),
    )


def _cierra_incidentes(conn: psycopg.Connection) -> None:
    conn.execute("UPDATE incidents SET state = 'closed', closed_at = now()")


def _plazos(dias: int | None = 30) -> dict[str, int | None]:
    """Plazo uniforme para todas las reglas del plan que se despacha."""
    return {r.key: dias for r in retention.RETENTION_PLAN}


def _perfil(
    conn: psycopg.Connection,
    *,
    tenant: str = TENANT_A,
    user: str = USER_A,
    nombre: str = "Ana Ruiz",
    telefono: str | None = "+525550001111",
) -> None:
    conn.execute(
        "INSERT INTO user_profiles (user_sub, tenant_id, display_name, phone) VALUES (%s,%s,%s,%s)",
        (user, tenant, nombre, telefono),
    )


def _baja(
    conn: psycopg.Connection,
    *,
    tenant: str = TENANT_A,
    user: str = USER_A,
    dias: int,
    via: str = "account_disabled",
    vuelta_dias: int | None = None,
) -> None:
    """La persona se fue hace ``dias``; ``vuelta_dias`` la readmite después."""
    conn.execute(
        "INSERT INTO user_deactivations (tenant_id, user_sub, deactivated_at, via, reactivated_at) "
        "VALUES (%s,%s, now() - make_interval(days => %s), %s, "
        "        CASE WHEN %s::int IS NULL THEN NULL "
        "             ELSE now() - make_interval(days => %s::int) END)",
        (tenant, user, dias, via, vuelta_dias, vuelta_dias),
    )


# ---------------------------------------------------------------------------
# A · El plan se DERIVA del inventario de la T-2.80; no se teclea aparte
# ---------------------------------------------------------------------------


def test_toda_columna_erase_del_inventario_esta_clasificada_por_el_plan() -> None:
    """El recíproco: ninguna columna que ARCO destruye se queda sin decisión.

    Sin este test, el día que alguien añada un `_ERASE` al inventario de la
    T-2.80 la retención lo ignoraría en silencio — que es exactamente cómo
    envejece un inventario escrito a mano.
    """
    erase = {k for k, v in erasure.PII_INVENTORY.items() if v.action == "erase"}
    cubiertas = {(r.table, c) for r in retention.RETENTION_PLAN for c in r.columns}
    declaradas = set(retention.SIN_RELOJ)

    assert cubiertas <= erase, (
        "el plan de retención toca columnas que el inventario de PII no marca "
        f"como destruibles: {sorted(cubiertas - erase)}"
    )
    assert erase == cubiertas | declaradas, (
        "hay columnas `erase` sin decisión de retención (ni regla ni exclusión "
        f"declarada): {sorted(erase - cubiertas - declaradas)}"
    )
    assert not (cubiertas & declaradas), "una columna no puede tener regla Y estar excluida"


def test_toda_exclusion_declara_por_que_no_tiene_reloj() -> None:
    for columna, razon in retention.SIN_RELOJ.items():
        assert len(razon) > 40, f"{columna} se excluye sin razón escrita"


# ---------------------------------------------------------------------------
# A' · [T-2.81.b] EL RELOJ DEL NOMBRE Y EL TELÉFONO
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("columna", ["display_name", "phone"])
def test_el_nombre_y_el_telefono_ya_NO_estan_en_sin_reloj(columna: str) -> None:
    """El recíproco que la ficha exige, dicho por su nombre.

    Que `SIN_RELOJ` esté vacío no basta: hay que exigir que estas DOS columnas en
    concreto hayan salido de ahí. Un `SIN_RELOJ` vaciado por accidente (o una
    columna reclasificada a `keep_link` en el inventario) dejaría el conjunto
    vacío igual, y este test seguiría en verde si solo mirase el tamaño.
    """
    assert ("user_profiles", columna) not in retention.SIN_RELOJ
    cubiertas = {(r.table, c) for r in retention.RETENTION_PLAN for c in r.columns}
    assert ("user_profiles", columna) in cubiertas, (
        "la columna salió de SIN_RELOJ sin que ninguna regla la cubra: eso no es "
        "un reloj nuevo, es una decisión perdida"
    )


def test_la_regla_del_roster_cuelga_de_la_baja_y_NO_de_updated_at() -> None:
    """El error que la T-2.81 se negó a cometer, fijado por test.

    `updated_at` describe a un empleado ESTABLE, no a uno que se fue: usarla como
    reloj borraría antes los nombres de quien más tiempo lleva en el edificio.
    """
    regla = next(r for r in retention.RETENTION_PLAN if r.table == "user_profiles")
    assert "user_deactivations" in regla.clock
    assert "deactivated_at" in regla.clock
    assert "updated_at" not in regla.clock, "el reloj volvió a ser `updated_at`"


def test_el_reloj_del_roster_no_toca_a_quien_sigue_dentro(seeded: psycopg.Connection) -> None:
    """Sin baja no hay reloj: un perfil viejísimo y sin tocar sobrevive entero."""
    _perfil(seeded)
    seeded.execute(
        "UPDATE user_profiles SET updated_at = now() - make_interval(days => 3000) "
        "WHERE user_sub = %s",
        (USER_A,),
    )
    _cierra_incidentes(seeded)

    informe = prune_pii.run(seeded, apply=True, days=_plazos(30))

    reset(seeded)
    fila = seeded.execute(
        "SELECT display_name, phone FROM user_profiles WHERE user_sub = %s", (USER_A,)
    ).fetchone()
    assert fila == ("Ana Ruiz", "+525550001111"), (
        "se podó el roster de alguien que sigue dentro: el reloj volvió a ser `updated_at`"
    )
    assert informe.total_applied == 0


def test_poda_el_nombre_y_el_telefono_de_quien_se_fue_hace_tiempo(
    seeded: psycopg.Connection,
) -> None:
    _perfil(seeded)
    _baja(seeded, dias=400)
    _cierra_incidentes(seeded)

    prune_pii.run(seeded, apply=True, days=_plazos(30))

    reset(seeded)
    fila = seeded.execute(
        "SELECT display_name, phone FROM user_profiles WHERE user_sub = %s", (USER_A,)
    ).fetchone()
    assert fila is not None, "la fila desapareció: la retención BORRÓ en vez de anonimizar"
    assert fila == (erasure.ERASED_DISPLAY_NAME, None), (
        "el dato muerto por reloj tiene que verse igual que el muerto por ARCO"
    )


def test_respeta_a_quien_se_fue_ANTEAYER(seeded: psycopg.Connection) -> None:
    _perfil(seeded)
    _baja(seeded, dias=2)
    _cierra_incidentes(seeded)

    informe = prune_pii.run(seeded, apply=True, days=_plazos(30))

    reset(seeded)
    fila = seeded.execute(
        "SELECT display_name FROM user_profiles WHERE user_sub = %s", (USER_A,)
    ).fetchone()
    assert fila[0] == "Ana Ruiz"
    assert informe.total_applied == 0


def test_a_quien_VOLVIO_no_se_le_borra_el_nombre(seeded: psycopg.Connection) -> None:
    """El modo de fallo que hace falta que exista `reactivated_at`.

    `PATCH {"enabled": false}` es la baja REVERSIBLE que la consola ofrece
    primero. Sin parar el reloj, una readmisión seguiría contando plazo y esta
    persona perdería su nombre **estando en el edificio** — con una brigada
    leyendo `(titular anonimizado)` en la lista del piso 8.
    """
    _perfil(seeded)
    _baja(seeded, dias=400, vuelta_dias=390)
    _cierra_incidentes(seeded)

    informe = prune_pii.run(seeded, apply=True, days=_plazos(30))

    reset(seeded)
    fila = seeded.execute(
        "SELECT display_name, phone FROM user_profiles WHERE user_sub = %s", (USER_A,)
    ).fetchone()
    assert fila == ("Ana Ruiz", "+525550001111"), "se podó el roster de alguien que volvió"
    assert informe.total_applied == 0


def test_el_roster_no_se_poda_con_un_incidente_ABIERTO(seeded: psycopg.Connection) -> None:
    """Mismo diferimiento que la geometría, y por la misma razón: con un incidente
    abierto el roster es la lista con la que una brigada pregunta «¿quién falta?»."""
    _perfil(seeded)
    _baja(seeded, dias=400)  # `seeded` deja INC_A abierto en el tenant A

    informe = prune_pii.run(seeded, apply=True, days=_plazos(30))

    reset(seeded)
    fila = seeded.execute(
        "SELECT display_name FROM user_profiles WHERE user_sub = %s", (USER_A,)
    ).fetchone()
    assert fila[0] == "Ana Ruiz"
    perfiles = [c for c in informe.counts if c.rule == "user_profiles.identity"]
    assert perfiles and all(c.due == 0 for c in perfiles)


def test_el_roster_podado_dos_veces_no_cambia_nada_la_segunda(
    seeded: psycopg.Connection,
) -> None:
    _perfil(seeded)
    _baja(seeded, dias=400)
    _cierra_incidentes(seeded)

    primera = prune_pii.run(seeded, apply=True, days=_plazos(30))
    segunda = prune_pii.run(seeded, apply=True, days=_plazos(30))

    assert primera.total_applied == 1
    assert segunda.total_applied == 0 and segunda.total_due == 0


def test_la_poda_del_roster_no_cruza_tenants(seeded: psycopg.Connection) -> None:
    """Regla de oro 5. `user_profiles_admin` es tenant-ciega, así que aquí el
    confinamiento lo pone el job — y por eso hay que ejercerlo, no suponerlo."""
    _perfil(seeded, tenant=TENANT_A, user=USER_A, nombre="Ana A")
    _perfil(seeded, tenant=TENANT_B, user=USER_B, nombre="Beto B")
    _baja(seeded, tenant=TENANT_A, user=USER_A, dias=400)
    _baja(seeded, tenant=TENANT_B, user=USER_B, dias=400)
    _cierra_incidentes(seeded)

    prune_pii.run(seeded, apply=True, days=_plazos(30), tenants=(TENANT_A,))

    reset(seeded)
    nombres = dict(
        seeded.execute(
            "SELECT user_sub::text, display_name FROM user_profiles WHERE user_sub IN (%s,%s)",
            (USER_A, USER_B),
        ).fetchall()
    )
    assert nombres[USER_B] == "Beto B", "la poda del tenant A se llevó el roster del tenant B"
    assert nombres[USER_A] == erasure.ERASED_DISPLAY_NAME


def test_la_baja_de_un_titular_ajeno_es_INEXPRESABLE(seeded: psycopg.Connection) -> None:
    """El mismo candado que `privacy_erasure_requests`: no lo para una
    comprobación, lo para la integridad referencial."""
    _perfil(seeded, tenant=TENANT_A, user=USER_A)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _baja(seeded, tenant=TENANT_B, user=USER_A, dias=1)


@pytest.mark.parametrize("rol", ["occupant", "soc_operator", "building_admin", "inspector"])
def test_solo_quien_administra_usuarios_puede_dar_de_baja(
    seeded: psycopg.Connection, rol: str
) -> None:
    """El reloj de la retención no lo arranca cualquiera: quien no reparte
    identidades tampoco decide cuándo caduca el nombre de un compañero."""
    _perfil(seeded)
    reset(seeded)
    use(seeded, "takab_app", tenant=TENANT_A, app_role=rol, user_id=USER_A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(
            "INSERT INTO user_deactivations (tenant_id, user_sub, via) "
            "VALUES (%s,%s,'account_disabled')",
            (TENANT_A, USER_A),
        )


def test_un_tenant_admin_no_da_de_baja_en_OTRO_cliente(seeded: psycopg.Connection) -> None:
    """Regla de oro 5, y con DOS candados independientes: la RLS del `WITH CHECK`
    y el FK compuesto. Aquí se ejerce el primero — el titular EXISTE, así que si
    la fila entrara sería por la política, no por integridad referencial."""
    _perfil(seeded, tenant=TENANT_B, user=USER_B)
    reset(seeded)
    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin", user_id=USER_A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(
            "INSERT INTO user_deactivations (tenant_id, user_sub, via) "
            "VALUES (%s,%s,'account_disabled')",
            (TENANT_B, USER_B),
        )


def test_la_baja_no_se_puede_BORRAR_desde_la_api(seeded: psycopg.Connection) -> None:
    """Una baja que se puede hacer desaparecer es un reloj que se puede parar sin
    dejar rastro. Se para escribiendo `reactivated_at`, y eso sí se ve."""
    _perfil(seeded)
    _baja(seeded, dias=10)
    reset(seeded)

    with seeded.transaction():
        prune_pii.harden_session(seeded, role=retention.JOB_ROLE)
        with pytest.raises(psycopg.Error) as exc, seeded.transaction():
            seeded.execute("DELETE FROM user_deactivations")
    assert exc.value.sqlstate == "42501"


def test_el_plan_que_se_despacha_no_borra_ni_una_fila() -> None:
    """Hoy no hay ninguna PII prunable que no esté dentro de una fila que debe
    sobrevivir. El día que la haya, este test obliga a razonarlo."""
    borradoras = [r.key for r in retention.RETENTION_PLAN if r.mode == retention.DELETE_ROWS]
    assert borradoras == [], f"el plan despacha reglas que BORRAN filas: {borradoras}"


def test_toda_regla_es_consciente_del_tenant(conn: psycopg.Connection) -> None:
    """Regla de oro 5: un job que pode a través de tenants es una fuga."""
    for regla in retention.RETENTION_PLAN:
        fila = conn.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s AND column_name='tenant_id'",
            (regla.table,),
        ).fetchone()
        assert fila[0] == 1, f"{regla.table} no tiene tenant_id: la regla no puede confinarse"


def test_ninguna_regla_arranca_con_plazo_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    """El default bajo incertidumbre es NO BORRAR NADA."""
    for regla in retention.RETENTION_PLAN:
        monkeypatch.delenv(regla.env_var, raising=False)
        assert retention.dias_configurados(regla, env={}) is None


# ---------------------------------------------------------------------------
# B · La lista de tablas protegidas se DERIVA del catálogo vivo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tabla", COMPLIANCE)
def test_la_derivacion_encuentra_las_tablas_de_la_regla_de_oro_11(
    conn: psycopg.Connection, tabla: str
) -> None:
    protegidas = retention.protected_tables(conn, role=retention.JOB_ROLE)
    assert tabla in protegidas


def test_la_derivacion_cubre_las_doce_de_la_t_2_80(conn: psycopg.Connection) -> None:
    protegidas = retention.protected_tables(conn, role=retention.JOB_ROLE)
    doce = {
        "audit_log",
        "incident_actions",
        "dictamens",
        "evidence_objects",
        "damage_reports",
        "life_checkins",
        "privacy_notices",
        "privacy_consents",
        "user_profiles",
        "push_tokens",
        "device_keys",
        "privacy_erasures",
    }
    assert doce <= protegidas, f"la derivación perdió: {sorted(doce - protegidas)}"


def test_la_derivacion_falla_cerrada_si_el_catalogo_viene_vacio() -> None:
    """Un catálogo vacío significa que la derivación se rompió, no que no haya
    nada que proteger. Fallar abierto ahí sería catastrófico."""

    class _Muda:
        def execute(self, *_a, **_k):
            return self

        def fetchall(self):
            return []

    with pytest.raises(retention.RetentionUnsafe, match="derivación"):
        retention.protected_tables(_Muda(), role=retention.JOB_ROLE)


def test_el_suelo_de_compliance_nombra_las_cinco_de_la_regla_de_oro_11() -> None:
    assert set(COMPLIANCE) <= set(retention.COMPLIANCE_ANCHOR)


@pytest.mark.parametrize("perdida", COMPLIANCE)
def test_si_una_tabla_del_suelo_se_cae_de_la_derivacion_el_job_no_arranca(
    perdida: str,
) -> None:
    """EL test que impide que la derivación se apruebe a sí misma.

    Conceder ``DELETE`` sobre `audit_log` y quitarle el trigger la sacaría del
    conjunto derivado **en silencio** — y un job que solo comprueba "todo lo que
    derivé está protegido" seguiría en verde, porque lo que ya no deriva no lo
    comprueba. El suelo convierte esa desaparición en un abort.
    """
    informe = {t: ("privilegio_ausente",) for t in retention.COMPLIANCE_ANCHOR}
    del informe[perdida]
    informe["otra_tabla_cualquiera"] = ("guard_activo",)

    with pytest.raises(retention.RetentionUnsafe, match=perdida):
        retention.validar_proteccion(informe)


# [T-2.81.c] Aquí vivía `test_un_guard_deshabilitado_no_cuenta_como_proteccion`, y se
# retiró porque **su premisa dejó de existir**, no porque estorbara. Aquel test elegía
# `rule_evaluations` por ser «la única tabla donde el privilegio DELETE quedó concedido y
# es el trigger quien la salva» — y T-2.81.c le quitó ese privilegio.
#
# La propiedad que medía sigue haciendo falta y está mejor medida en
# `test_append_only_dos_capas.py::test_un_guard_deshabilitado_deja_de_contar_como_capa`,
# que **elige la tabla del catálogo en vez de nombrarla** y comprueba algo más fuerte: en
# una tabla con las DOS capas, deshabilitar el guard tira una y deja la otra, que es
# exactamente la razón de tener dos.


# ---------------------------------------------------------------------------
# C · CRITERIO 2 · pedir la poda de una tabla protegida truena, y truena ANTES
# ---------------------------------------------------------------------------


def _regla_asesina(tabla: str) -> retention.RetentionRule:
    """La regla que la ficha teme: un `DELETE` mal escrito sobre evidencia."""
    return retention.RetentionRule(
        key=f"{tabla}.purga",
        table=tabla,
        columns=(),
        mode=retention.DELETE_ROWS,
        set_clause="",
        clock="true",
        why="regla de prueba: NO debe llegar a ejecutarse jamás",
    )


@pytest.mark.parametrize("tabla", COMPLIANCE)
def test_una_regla_que_borra_filas_de_una_tabla_protegida_es_rechazada(
    seeded: psycopg.Connection, tabla: str
) -> None:
    antes = seeded.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]

    with pytest.raises(retention.RetentionUnsafe) as exc:
        prune_pii.run(seeded, plan=(_regla_asesina(tabla),), apply=True, days=_plazos())

    assert tabla in str(exc.value)
    reset(seeded)
    despues = seeded.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]
    assert despues == antes, f"{tabla} perdió filas: la excepción llegó TARDE"


def test_el_rechazo_ocurre_en_el_preflight_antes_de_cualquier_conteo(
    seeded: psycopg.Connection,
) -> None:
    """Una regla asesina envenena el plan ENTERO: ni siquiera se simulan las
    reglas buenas. Rechazar solo la mala dejaría correr un plan que ya se sabe
    corrupto."""
    plan = (*retention.RETENTION_PLAN, _regla_asesina("audit_log"))
    with pytest.raises(retention.RetentionUnsafe, match="audit_log"):
        prune_pii.run(seeded, plan=plan, apply=False, days=_plazos())


def test_ni_saltandose_el_guard_puede_el_job_borrar_evidencia(
    seeded: psycopg.Connection,
) -> None:
    """El control que hace real a todos los anteriores.

    Si la única defensa fuese el `if` del preflight, bastaría con borrarlo. Aquí
    se emite el `DELETE` A MANO dentro de la sesión que el job se prepara —misma
    degradación de rol— y PostgreSQL lo rechaza por privilegio o por trigger.
    """
    with seeded.transaction():
        prune_pii.harden_session(seeded, role=retention.JOB_ROLE)
        for tabla in COMPLIANCE:
            with pytest.raises(psycopg.Error) as exc, seeded.transaction():
                seeded.execute(f"DELETE FROM {tabla}")
            assert exc.value.sqlstate in ("42501", "P0001"), (
                f"{tabla}: el DELETE no lo paró ni el privilegio ni el trigger "
                f"(sqlstate={exc.value.sqlstate})"
            )


# ---------------------------------------------------------------------------
# D · CON QUÉ ROL CORRE EL JOB (la capa que de verdad sostiene todo lo demás)
# ---------------------------------------------------------------------------


def test_el_job_se_degrada_aunque_el_dsn_sea_superusuario(seeded: psycopg.Connection) -> None:
    """El DSN de estos tests es superusuario + BYPASSRLS. Dentro del job no."""
    antes = seeded.execute("SELECT current_user").fetchone()[0]
    informe = prune_pii.run(seeded, apply=False, days=_plazos())

    assert informe.role == retention.JOB_ROLE
    assert informe.role != antes, "el job corrió con el rol del DSN: la degradación no ocurrió"
    assert not informe.superuser and not informe.bypassrls


def test_el_job_aborta_si_el_rol_no_existe(seeded: psycopg.Connection) -> None:
    with pytest.raises(retention.RetentionUnsafe, match="no_existe_este_rol"):
        prune_pii.run(seeded, apply=False, role="no_existe_este_rol", days=_plazos())


@pytest.mark.parametrize("rol", ["takab", "takab_ingest"])
def test_el_job_aborta_con_un_rol_que_esquiva_las_capas(
    seeded: psycopg.Connection, rol: str
) -> None:
    """``takab`` es superusuario; ``takab_ingest`` tiene BYPASSRLS. Ninguno de
    los dos puede correr este job aunque no tenga DELETE: BYPASSRLS convierte un
    job por tenant en un job global sin que nada lo grite."""
    with pytest.raises(retention.RetentionUnsafe):
        prune_pii.run(seeded, apply=False, role=rol, days=_plazos())


def test_el_nombre_de_rol_no_es_una_via_de_inyeccion(seeded: psycopg.Connection) -> None:
    with pytest.raises(retention.RetentionUnsafe):
        prune_pii.run(seeded, apply=False, role='takab_app"; DROP TABLE audit_log; --')


# ---------------------------------------------------------------------------
# E · CRITERIO 3 · el simulacro con conteos es obligatorio
# ---------------------------------------------------------------------------


def test_el_simulacro_es_el_modo_por_defecto(seeded: psycopg.Connection) -> None:
    _token(seeded, valor="tok-viejo", dias=400)
    informe = prune_pii.run(seeded, days=_plazos())  # sin `apply`

    assert informe.mode == "simulacro"
    assert informe.total_due >= 1
    assert informe.total_applied == 0
    reset(seeded)
    vivo = seeded.execute("SELECT token FROM push_tokens WHERE token = 'tok-viejo'").fetchone()
    assert vivo is not None, "el simulacro mutó datos"


def test_el_simulacro_reporta_conteos_por_regla_y_por_tenant(
    seeded: psycopg.Connection,
) -> None:
    _token(seeded, valor="tok-a", dias=400)
    _token(seeded, tenant=TENANT_B, user=USER_B, site=SITE_B, valor="tok-b", dias=400)
    informe = prune_pii.run(seeded, days=_plazos())

    porton = {(c.rule, c.tenant_id): c.due for c in informe.counts}
    assert porton.get(("push_tokens.token", TENANT_A)) == 1
    assert porton.get(("push_tokens.token", TENANT_B)) == 1


def test_sin_plazo_configurado_no_se_poda_nada(seeded: psycopg.Connection) -> None:
    _token(seeded, valor="tok-viejisimo", dias=9999)
    informe = prune_pii.run(seeded, apply=True, days={})

    assert informe.total_due == 0
    assert informe.total_applied == 0
    assert all(v is None for v in informe.windows.values())
    reset(seeded)
    assert (
        seeded.execute("SELECT count(*) FROM push_tokens WHERE token='tok-viejisimo'").fetchone()[0]
        == 1
    )


def test_si_la_poda_no_cuadra_con_el_conteo_se_revierte_todo(
    seeded: psycopg.Connection,
) -> None:
    """Que el guard del conteo NO es decorativo.

    Se reproduce el fallo real que lo estrenó: sin la política de la 0035, el job
    SELECCIONA la fila caducada (``lc_read`` deja leer a un rol interno) y la
    actualiza cero veces. El conteo dice 1, ``ROW_COUNT`` dice 0 y la corrida
    entera se revierte — incluida la poda de `push_tokens`, que sí había
    funcionado. Media poda con informe en verde es peor que ninguna.
    """
    _token(seeded, valor="tok-viejo", dias=400)
    _checkin(seeded, dias=400)
    _cierra_incidentes(seeded)
    reset(seeded)
    seeded.execute("DROP POLICY lc_retention_geom ON life_checkins")

    with pytest.raises(retention.RetentionUnsafe, match="conteo previo"):
        prune_pii.run(seeded, apply=True, days=_plazos(30))

    reset(seeded)
    assert (
        seeded.execute("SELECT count(*) FROM push_tokens WHERE token='tok-viejo'").fetchone()[0]
        == 1
    ), "la poda de push_tokens sobrevivió a una corrida que se declaró fallida"


def test_el_conteo_previo_es_la_autorizacion_de_la_poda(seeded: psycopg.Connection) -> None:
    """Podar sin haber contado no es un estado alcanzable: el job cuenta, poda y
    exige que ``ROW_COUNT`` cuadre con el conteo. Si no cuadra, revierte."""
    _token(seeded, valor="tok-viejo", dias=400)
    informe = prune_pii.run(seeded, apply=True, days=_plazos())

    aplicadas = [c for c in informe.counts if c.rule == "push_tokens.token"]
    assert aplicadas and all(c.applied == c.due for c in aplicadas)
    assert informe.total_applied == informe.total_due


# ---------------------------------------------------------------------------
# F · Qué poda, qué respeta, y que no se pueda notar dos veces
# ---------------------------------------------------------------------------


def test_poda_el_token_viejo_y_respeta_el_reciente(seeded: psycopg.Connection) -> None:
    _token(seeded, valor="tok-viejo", dias=400)
    _token(seeded, user=USER_A2, valor="tok-de-ayer", dias=1)

    prune_pii.run(seeded, apply=True, days=_plazos(30))

    reset(seeded)
    filas = dict(
        seeded.execute(
            "SELECT user_sub::text, token FROM push_tokens WHERE user_sub IN (%s,%s)",
            (USER_A, USER_A2),
        ).fetchall()
    )
    assert filas[USER_A2] == "tok-de-ayer"
    assert filas[USER_A].startswith(erasure.ERASED_TOKEN_PREFIX)


def test_la_fila_del_token_podado_sobrevive_y_queda_revocada(
    seeded: psycopg.Connection,
) -> None:
    """No se borra el hecho de que hubo un dispositivo: muere el identificador."""
    _token(seeded, valor="tok-viejo", dias=400)
    prune_pii.run(seeded, apply=True, days=_plazos(30))

    reset(seeded)
    fila = seeded.execute(
        "SELECT endpoint_arn, revoked_at FROM push_tokens WHERE user_sub = %s", (USER_A,)
    ).fetchone()
    assert fila is not None, "la fila desapareció: la retención BORRÓ en vez de anonimizar"
    assert fila[0] is None and fila[1] is not None


def test_anula_la_geometria_de_checkins_viejos_de_incidentes_cerrados(
    seeded: psycopg.Connection,
) -> None:
    _checkin(seeded, dias=400)
    _cierra_incidentes(seeded)

    prune_pii.run(seeded, apply=True, days=_plazos(90))

    reset(seeded)
    fila = seeded.execute(
        "SELECT count(*) FROM life_checkins WHERE user_id = %s AND geom IS NOT NULL",
        (USER_A,),
    ).fetchone()
    assert fila[0] == 0


def test_no_toca_la_geometria_si_el_incidente_sigue_abierto(
    seeded: psycopg.Connection,
) -> None:
    """Mientras el incidente está abierto, la ubicación de un check-in es dato de
    rescate EN VIVO. Mismo diferimiento que ARCO (`TK409`)."""
    _checkin(seeded, dias=400)  # `seeded` deja INC_A abierto

    informe = prune_pii.run(seeded, apply=True, days=_plazos(90))

    reset(seeded)
    fila = seeded.execute(
        "SELECT count(*) FROM life_checkins WHERE user_id = %s AND geom IS NOT NULL",
        (USER_A,),
    ).fetchone()
    assert fila[0] == 1
    geo = [c for c in informe.counts if c.rule == "life_checkins.geom"]
    assert all(c.due == 0 for c in geo)


def test_el_checkin_podado_sigue_contando(seeded: psycopg.Connection) -> None:
    """Criterio que gobierna toda la Fase 2.8: la retención anonimiza a la
    PERSONA y conserva el HECHO. ``COUNT(DISTINCT user_id)`` es "cuántas personas
    confirmaron estar bien", y en un sismo decide si sube o no una brigada."""
    _checkin(seeded, user=USER_A, dias=400)
    _checkin(seeded, user=USER_A2, dias=400)
    _cierra_incidentes(seeded)
    reset(seeded)
    antes = seeded.execute(
        "SELECT count(*), count(DISTINCT user_id) FROM life_checkins WHERE tenant_id = %s",
        (TENANT_A,),
    ).fetchone()

    prune_pii.run(seeded, apply=True, days=_plazos(90))

    reset(seeded)
    despues = seeded.execute(
        "SELECT count(*), count(DISTINCT user_id) FROM life_checkins WHERE tenant_id = %s",
        (TENANT_A,),
    ).fetchone()
    assert despues == antes


def test_correr_dos_veces_no_cambia_nada_la_segunda(seeded: psycopg.Connection) -> None:
    """Regla de oro 3. Y no es teoría: el guard de `life_checkins` RECHAZA un
    UPDATE que no cambie nada, así que un job no idempotente reventaría."""
    _token(seeded, valor="tok-viejo", dias=400)
    _checkin(seeded, dias=400)
    _cierra_incidentes(seeded)

    primera = prune_pii.run(seeded, apply=True, days=_plazos(30))
    segunda = prune_pii.run(seeded, apply=True, days=_plazos(30))

    assert primera.total_applied > 0
    assert segunda.total_applied == 0
    assert segunda.total_due == 0


def test_no_cruza_tenants(seeded: psycopg.Connection) -> None:
    """El tenant B tiene un token igual de viejo pero el job corre acotado a A."""
    _token(seeded, valor="tok-a", dias=400)
    _token(seeded, tenant=TENANT_B, user=USER_B, site=SITE_B, valor="tok-b", dias=400)

    prune_pii.run(seeded, apply=True, days=_plazos(30), tenants=(TENANT_A,))

    reset(seeded)
    assert (
        seeded.execute("SELECT count(*) FROM push_tokens WHERE token='tok-b'").fetchone()[0] == 1
    ), "la poda del tenant A se llevó por delante datos del tenant B"
    assert seeded.execute("SELECT count(*) FROM push_tokens WHERE token='tok-a'").fetchone()[0] == 0


def test_en_life_checkins_el_confinamiento_por_tenant_lo_impone_la_RLS(
    seeded: psycopg.Connection,
) -> None:
    """No basta con que el job filtre bien: hay que probar que si NO filtrara,
    la base lo pararía igual.

    Se emite el UPDATE a mano, sin ``WHERE tenant_id``, con la sesión del job
    apuntando al tenant A. La política ``lc_retention_geom`` exige ``tenant_id =
    app_tenant_id()``, así que la fila del tenant B tiene que quedar intacta.
    """
    _checkin(seeded, tenant=TENANT_A, user=USER_A, site=SITE_A, incidente=None, dias=400)
    _checkin(seeded, tenant=TENANT_B, user=USER_B, site=SITE_B, incidente=None, dias=400)

    with seeded.transaction():
        prune_pii.harden_session(seeded, role=retention.JOB_ROLE)
        seeded.execute("SELECT set_config('app.tenant_id', %s, true)", (TENANT_A,))
        cur = seeded.execute("UPDATE life_checkins SET geom = NULL WHERE geom IS NOT NULL")
        tocadas = cur.rowcount

    reset(seeded)
    quedan_b = seeded.execute(
        "SELECT count(*) FROM life_checkins WHERE tenant_id = %s AND geom IS NOT NULL",
        (TENANT_B,),
    ).fetchone()[0]
    assert tocadas == 1, f"el UPDATE sin filtro tocó {tocadas} filas: la RLS no acotó"
    assert quedan_b == 1, "la RLS dejó que la sesión del tenant A anonimizara al tenant B"


def test_el_checkin_ajeno_del_seed_no_se_toca_si_es_reciente(
    seeded: psycopg.Connection,
) -> None:
    """El seed mete un check-in de `GOV_AGENCY` reciente y sin geom. Que el job
    no lo cuente prueba que el reloj no es decorativo."""
    _cierra_incidentes(seeded)
    informe = prune_pii.run(seeded, apply=True, days=_plazos(90))

    reset(seeded)
    assert (
        seeded.execute(
            "SELECT count(*) FROM life_checkins WHERE user_id = %s", (GOV_AGENCY,)
        ).fetchone()[0]
        == 1
    )
    assert informe.total_applied == 0


# ---------------------------------------------------------------------------
# G · La línea de comandos (el job es invocable; la programación queda fuera)
# ---------------------------------------------------------------------------


def test_la_cli_simula_por_defecto_y_podar_exige_flag_explicito() -> None:
    assert prune_pii.build_parser().parse_args([]).apply is False
    assert prune_pii.build_parser().parse_args(["--apply"]).apply is True


# ---------------------------------------------------------------------------
# H · [T-2.81.a] QUE LA CORRIDA OCURRIÓ TIENE QUE PODERSE COMPROBAR
# ---------------------------------------------------------------------------


def _constancias(conn: psycopg.Connection) -> list[tuple]:
    reset(conn)
    return conn.execute(
        "SELECT mode, ok, total_due, total_applied, error FROM pii_retention_runs "
        "ORDER BY finished_at"
    ).fetchall()


def test_el_simulacro_que_no_borro_nada_TAMBIEN_deja_constancia(
    seeded: psycopg.Connection,
) -> None:
    """Es justamente la corrida que hay que poder enseñar: prueba que el reloj se
    revisó el día que tocaba, aunque no hubiera nada caducado."""
    inicio = datetime.now(UTC)
    informe = prune_pii.run(seeded, days=_plazos())
    prune_pii.registrar_corrida(seeded, started_at=inicio, informe=informe)

    filas = _constancias(seeded)
    assert len(filas) == 1
    assert filas[0][0] == "simulacro" and filas[0][1] is True and filas[0][4] is None


def test_la_corrida_que_FALLA_deja_constancia_Y_SOBREVIVE_al_rollback(
    seeded: psycopg.Connection,
) -> None:
    """EL test de esta ficha.

    La corrida se revierte ENTERA cuando algo no cuadra. Si la constancia se
    escribiera dentro de esa transacción, el rollback se llevaría por delante
    justo el registro de la corrida que falló — la única que alguien necesita
    leer. Aquí se ejerce el fallo real (una regla que quiere borrar evidencia) y
    se comprueba las dos mitades: la poda NO ocurrió y la constancia SÍ está.
    """
    _token(seeded, valor="tok-viejo", dias=400)
    inicio = datetime.now(UTC)
    plan = (*retention.RETENTION_PLAN, _regla_asesina("audit_log"))

    with pytest.raises(retention.RetentionUnsafe) as exc:
        prune_pii.run(seeded, plan=plan, apply=True, days=_plazos())
    prune_pii.registrar_corrida(seeded, started_at=inicio, error=str(exc.value), mode="aplicado")

    filas = _constancias(seeded)
    assert len(filas) == 1
    assert filas[0][:2] == ("aplicado", False)
    assert "audit_log" in filas[0][4], "la constancia no dice POR QUÉ falló"
    assert (
        seeded.execute("SELECT count(*) FROM push_tokens WHERE token='tok-viejo'").fetchone()[0]
        == 1
    ), "la corrida abortada podó algo: la constancia sobrevivió pero la atomicidad no"


def test_no_se_puede_declarar_un_fallo_SIN_RAZON_ni_un_exito_CON_ella(
    seeded: psycopg.Connection,
) -> None:
    """«Un fallo del job se ve» es una condición de la base, no del código."""
    reset(seeded)
    for ok, error in ((False, None), (True, "algo salió mal")):
        with pytest.raises(psycopg.errors.CheckViolation), seeded.transaction():
            seeded.execute(
                "INSERT INTO pii_retention_runs (started_at, mode, ok, error) "
                "VALUES (now(), 'aplicado', %s, %s)",
                (ok, error),
            )


def test_la_constancia_no_se_edita_ni_se_borra(seeded: psycopg.Connection) -> None:
    """Editarla sería poder afirmar que se podó lo que no se podó."""
    prune_pii.registrar_corrida(
        seeded, started_at=datetime.now(UTC), informe=prune_pii.run(seeded, days=_plazos())
    )
    with seeded.transaction():
        prune_pii.harden_session(seeded, role=retention.JOB_ROLE)
        for verbo in ("UPDATE pii_retention_runs SET ok = false", "DELETE FROM pii_retention_runs"):
            with pytest.raises(psycopg.Error) as exc, seeded.transaction():
                seeded.execute(verbo)
            assert exc.value.sqlstate == "42501", verbo


def test_la_CLI_deja_la_constancia_de_verdad_y_no_solo_sabe_hacerlo(
    conn: psycopg.Connection,
) -> None:
    """El cableado, no la función suelta.

    `registrar_corrida` probada aparte no dice nada sobre si `main()` la llama:
    un job que sabe dejar constancia y no la deja es exactamente el estado del
    que sale esta ficha. Aquí se ejerce la CLI entera, con su propia conexión y
    su propio commit, y se lee la fila desde fuera.
    """
    conn.rollback()
    antes = conn.execute("SELECT count(*) FROM pii_retention_runs").fetchone()[0]
    try:
        assert prune_pii.main([]) == 0  # simulacro, sin plazos: no poda nada
        conn.rollback()  # ver lo que la CLI confirmó desde OTRA conexión
        filas = conn.execute(
            "SELECT mode, ok, total_applied, error FROM pii_retention_runs "
            "ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()
        assert conn.execute("SELECT count(*) FROM pii_retention_runs").fetchone()[0] == antes + 1
        assert filas == ("simulacro", True, 0, None)

        # Y la salida de escape, que existe para depurar a mano y tiene que ser
        # explícita: sin ella el operador se llevaría la constancia por delante
        # sin querer, y la métrica que vigila la retención dejaría de moverse.
        assert prune_pii.main(["--sin-constancia"]) == 0
        conn.rollback()
        assert conn.execute("SELECT count(*) FROM pii_retention_runs").fetchone()[0] == antes + 1
    finally:
        conn.rollback()
        conn.execute("DELETE FROM pii_retention_runs")
        conn.commit()


def test_el_job_cede_el_LOCK_pero_no_le_ponen_tope_a_la_SENTENCIA(
    seeded: psycopg.Connection,
) -> None:
    """Los dos relojes, y por qué no es el mismo veredicto.

    `lock_timeout` acota lo que el job pasa ESPERANDO dentro de una transacción
    que ya sostiene el horizonte de `xmin`; `statement_timeout` acotaría el
    trabajo útil, que está MEDIDO en 38.9 s sobre un millón de filas y por tanto
    moriría con cualquiera de los topes de request (20 s) o worker (15 s).
    """
    with seeded.transaction():
        prune_pii.harden_session(seeded, role=retention.JOB_ROLE)
        lock = seeded.execute("SHOW lock_timeout").fetchone()[0]
        sentencia = seeded.execute("SHOW statement_timeout").fetchone()[0]

    assert lock == f"{session.JOB_LOCK_TIMEOUT_MS // 1000}s"
    assert sentencia in ("0", "0ms"), (
        "le pusieron tope de sentencia al job: una corrida legítima de 38.9 s sobre "
        "un millón de filas moriría a mitad y la retención no se ejecutaría"
    )
    assert session.JOB_LOCK_TIMEOUT_MS < 38_900, (
        "el tope de espera por lock supera el trabajo útil medido: el job estaría "
        "más rato con la transacción abierta esperando que trabajando"
    )


def test_el_tope_de_lock_no_se_queda_pegado_a_la_conexion(conn: psycopg.Connection) -> None:
    """`SET LOCAL` y no `SET`: el tope es del job, no de quien le prestó el DSN.

    Mismo alcance que la degradación de rol, y mismo filo declarado allí: `LOCAL`
    es por TRANSACCIÓN, no por savepoint, así que dentro de la transacción de un
    llamador (los tests, una consola SSM) el tope sigue puesto hasta que esa
    transacción termina. Lo que no puede es sobrevivirla.
    """
    conn.rollback()
    with conn.transaction():
        prune_pii.harden_session(conn, role=retention.JOB_ROLE)
        dentro = conn.execute("SHOW lock_timeout").fetchone()[0]
    fuera = conn.execute("SHOW lock_timeout").fetchone()[0]
    conn.rollback()

    assert dentro == f"{session.JOB_LOCK_TIMEOUT_MS // 1000}s"
    assert fuera == "0", "el tope del job se quedó pegado a la conexión del llamador"
