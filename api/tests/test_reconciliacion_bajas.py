"""[T-2.143] Una baja hecha en Cognito arranca el reloj de la PII sin que nadie corra nada.

`T-2.81.b` puso el reloj de retención de nombre y teléfono en `user_deactivations`,
y lo escriben `PATCH {"enabled": false}` y `DELETE /users/{u}`. **Una cuenta
retirada directamente en el pool no pasa por ahí**, así que esa persona conservaba
su nombre y su teléfono indefinidamente. El hueco se cerró declarándolo, con una
query de reconciliación en el runbook — pero *una reconciliación que hay que
acordarse de correr no es retención cumplida*, que es el argumento entero de
`T-2.81.a`.

LO QUE SE MIDE AQUÍ NO ES QUE FUNCIONE: ES QUE SE NIEGUE A ACTUAR A CIEGAS
──────────────────────────────────────────────────────────────────────────
Arrancar el reloj de quien falta del pool es la parte fácil, y es media línea de
SQL. La parte que puede hacer daño es la otra: **una lectura incompleta del pool
es indistinguible de un montón de bajas**. Si el directorio está caído, si la
paginación se queda a medias, si la respuesta viene vacía — en los tres casos la
lista de "usuarios que existen" encoge, y actuar sobre ella pondría en marcha el
borrado del nombre de gente que sigue trabajando en el edificio.

De los dos errores posibles, **conservar de más solo incumple un plazo; podar de
menos borra el nombre de alguien a quien una brigada podría estar buscando**. Por
eso los tres casos abortan enteros y ninguno actúa "con lo que se pudo leer".
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import psycopg
import pytest

from conftest import TENANT_A, TENANT_G, reset
from takab_api.privacy import reconcile
from takab_api.users.directory import (
    DirectoryUnavailable,
    SimulatedUserDirectory,
    UserRecord,
)

#: Se usan los del conftest y no unos propios: inventarse un tenant obliga a
#: sembrarlo, y sembrarlo mal —columnas que no existen— falla por una razón que no
#: tiene nada que ver con lo que se prueba. Pasó al escribir esto.
TENANT = TENANT_A
SE_QUEDA = "22222222-2222-2222-2222-222222222201"
SE_FUE = "22222222-2222-2222-2222-222222222202"


def _registro(username: str) -> UserRecord:
    return UserRecord(
        username=username,
        email=f"{username[:8]}@ejemplo.mx",
        tenant_id=TENANT,
        role="operator",
        site_scope="*",
        zone_id="",
        surface="web",
        enabled=True,
        status="CONFIRMED",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class _DirectorioCaido(SimulatedUserDirectory):
    """Un pool que no responde. No es lo mismo que un pool vacío, y el punto de
    esta clase es que el código no pueda confundirlos."""

    def list_users(self, *, limit: int, cursor: str | None):
        raise DirectoryUnavailable("cognito-idp ListUsers: se acabó el tiempo")


class _DirectorioQueSeCortaAMedias(SimulatedUserDirectory):
    """Devuelve la primera página **y sigue diciendo que hay más**, para siempre.

    Es el fallo silencioso de verdad: cada respuesta es válida, ninguna lanza, y
    quien pare de paginar se queda con una lista corta que parece completa.
    """

    def list_users(self, *, limit: int, cursor: str | None):
        pagina, _ = super().list_users(limit=1, cursor=cursor)
        return pagina, "siempre-hay-mas"


@pytest.fixture
def poblado(seeded: psycopg.Connection) -> psycopg.Connection:
    """Dos perfiles del mismo cliente, ninguno con baja registrada.

    **Sin `commit()` en ningún sitio**, aquí ni en los tests: el fixture `conn`
    revierte al terminar y ésa es toda la limpieza que hay. Comitear deja las
    filas puestas y el siguiente test muere sembrando los mismos tenants — que es
    lo que pasó al escribir esto, con un error (`tenants_pkey` duplicada) que no
    señala al culpable.
    """
    reset(seeded)
    seeded.execute("DELETE FROM user_deactivations WHERE tenant_id = %s", (TENANT,))
    for sub, nombre in ((SE_QUEDA, "Quien Sigue"), (SE_FUE, "Quien Se Fue")):
        seeded.execute(
            "INSERT INTO user_profiles (tenant_id, user_sub, display_name, phone) "
            "VALUES (%s, %s, %s, '+525500000000') "
            "ON CONFLICT (tenant_id, user_sub) DO UPDATE SET display_name = excluded.display_name",
            (TENANT, sub, nombre),
        )
    return seeded


def _relojes(conn: psycopg.Connection) -> dict[str, str]:
    filas = conn.execute(
        "SELECT user_sub::text, via FROM user_deactivations WHERE tenant_id = %s", (TENANT,)
    ).fetchall()
    return {f[0]: f[1] for f in filas}


# ---------------------------------------------------------------------------
# 1 · El criterio: la baja hecha en el pool arranca el reloj sola
# ---------------------------------------------------------------------------


def test_quien_desaparecio_del_pool_obtiene_su_reloj(poblado: psycopg.Connection) -> None:
    """El criterio 1 y el 2 de la ficha a la vez: una cuenta que se fue del pool
    **sin pasar por la API** deja de ser invisible para la retención."""
    directorio = SimulatedUserDirectory(seed=[_registro(SE_QUEDA)])

    parte = reconcile.reconciliar(poblado, directorio, apply=True)

    assert parte.abortada is None, f"abortó sin motivo: {parte.abortada}"
    assert parte.relojes_arrancados == (SE_FUE,), (
        f"se esperaba arrancar el reloj de {SE_FUE} y se arrancó {parte.relojes_arrancados}"
    )
    assert _relojes(poblado) == {SE_FUE: "account_deleted"}


def test_quien_sigue_en_el_pool_no_recibe_reloj(poblado: psycopg.Connection) -> None:
    """No-vacuidad del anterior: si arrancara el reloj de todo el mundo, el test
    de arriba pasaría igual y estaríamos borrando nombres de gente presente."""
    directorio = SimulatedUserDirectory(seed=[_registro(SE_QUEDA), _registro(SE_FUE)])

    parte = reconcile.reconciliar(poblado, directorio, apply=True)

    assert parte.abortada is None
    assert parte.relojes_arrancados == ()
    assert _relojes(poblado) == {}


def test_en_simulacro_no_escribe_pero_dice_lo_que_haria(poblado: psycopg.Connection) -> None:
    """Mismo reparto que el resto del job de retención: se puede ver el veredicto
    antes de que toque nada."""
    directorio = SimulatedUserDirectory(seed=[_registro(SE_QUEDA)])

    parte = reconcile.reconciliar(poblado, directorio, apply=False)

    assert parte.relojes_arrancados == (SE_FUE,)
    assert _relojes(poblado) == {}, "el simulacro escribió en la base"


def test_no_reinicia_el_reloj_de_quien_ya_estaba_de_baja(poblado: psycopg.Connection) -> None:
    """La persona se fue el día que se fue. Si cada corrida reescribiera la fecha,
    el plazo no vencería nunca y la retención sería decorativa."""
    poblado.execute(
        "INSERT INTO user_deactivations (tenant_id, user_sub, deactivated_at, via) "
        "VALUES (%s, %s, now() - interval '100 days', 'account_disabled')",
        (TENANT, SE_FUE),
    )
    antes = poblado.execute(
        "SELECT deactivated_at FROM user_deactivations WHERE user_sub = %s", (SE_FUE,)
    ).fetchone()[0]

    parte = reconcile.reconciliar(
        poblado, SimulatedUserDirectory(seed=[_registro(SE_QUEDA)]), apply=True
    )

    assert parte.relojes_arrancados == ()
    despues = poblado.execute(
        "SELECT deactivated_at FROM user_deactivations WHERE user_sub = %s", (SE_FUE,)
    ).fetchone()[0]
    assert despues == antes, "la reconciliación reinició un reloj que ya corría"


def test_el_insert_no_pisa_un_reloj_existente_ni_en_una_carrera(
    poblado: psycopg.Connection,
) -> None:
    """El `ON CONFLICT DO NOTHING`, probado DONDE se puede.

    El test de arriba no lo alcanza y hay que decirlo: la consulta de candidatos ya
    excluye a quien tiene reloj, así que el conflicto no llega a ocurrir por el
    camino normal — se midió rompiendo el código, y cambiarlo a `DO UPDATE SET
    deactivated_at = now()` dejaba la suite entera en verde.

    Es el cinturón para dos corridas solapadas, y un cinturón que nunca se abrocha
    no se sabe si aguanta. Se ejecuta la sentencia a mano contra alguien que YA
    tiene reloj, que es exactamente lo que pasaría en esa carrera.
    """
    poblado.execute(
        "INSERT INTO user_deactivations (tenant_id, user_sub, deactivated_at, via) "
        "VALUES (%s, %s, now() - interval '200 days', 'account_disabled')",
        (TENANT, SE_FUE),
    )
    antes = poblado.execute(
        "SELECT deactivated_at, via FROM user_deactivations WHERE user_sub = %s", (SE_FUE,)
    ).fetchone()

    poblado.execute(reconcile._ARRANCAR, (TENANT, SE_FUE, reconcile.VIA))

    despues = poblado.execute(
        "SELECT deactivated_at, via FROM user_deactivations WHERE user_sub = %s", (SE_FUE,)
    ).fetchone()
    assert despues == antes, (
        f"la sentencia pisó un reloj que ya corría: {antes} -> {despues}. Reescribir la fecha "
        "en cada corrida haría que el plazo no venciera nunca."
    )


def test_a_quien_volvio_no_se_le_arranca_el_reloj_otra_vez(poblado: psycopg.Connection) -> None:
    """Una cuenta readmitida tiene `reactivated_at`, o sea reloj PARADO — y sigue
    en el pool, así que la reconciliación no debe tocarla. Es el caso que
    convertiría a un empleado readmitido en alguien a quien se le borra el nombre.
    """
    poblado.execute(
        "INSERT INTO user_deactivations (tenant_id, user_sub, deactivated_at, via, reactivated_at) "
        "VALUES (%s, %s, now() - interval '10 days', 'account_disabled', now())",
        (TENANT, SE_QUEDA),
    )

    parte = reconcile.reconciliar(
        poblado, SimulatedUserDirectory(seed=[_registro(SE_QUEDA), _registro(SE_FUE)]), apply=True
    )

    assert parte.relojes_arrancados == ()
    fila = poblado.execute(
        "SELECT reactivated_at FROM user_deactivations WHERE user_sub = %s", (SE_QUEDA,)
    ).fetchone()[0]
    assert fila is not None, "se le volvió a arrancar el reloj a alguien que había vuelto"


# ---------------------------------------------------------------------------
# 2 · Las tres formas de leer el pool a medias, y por qué ninguna actúa
# ---------------------------------------------------------------------------


def test_con_el_directorio_caido_no_se_arranca_ni_un_reloj(poblado: psycopg.Connection) -> None:
    """**El caso que hace peligrosa esta tarea.** Si el pool no responde, la lista
    de usuarios existentes es vacía — y una lista vacía dice exactamente lo mismo
    que "los han borrado a todos". Actuar sobre ella pondría en marcha el borrado
    del nombre de cada persona de cada edificio.
    """
    parte = reconcile.reconciliar(poblado, _DirectorioCaido(), apply=True)

    assert parte.relojes_arrancados == ()
    assert parte.abortada, "no dejó constancia de por qué no hizo nada"
    assert _relojes(poblado) == {}

    # La causa, no solo el hecho. La palabra "directorio" sale en los DOS motivos
    # —el caído y el vacío—, así que buscarla no distinguía nada: se comprobó
    # rompiendo el código, y tragarse la excepción para caer en la otra rama dejaba
    # este test en verde. Es el mismo defecto que "5 min" ⊂ "15 min" de T-2.162.
    assert "no respondió" in parte.abortada, (
        f"el motivo no dice que el directorio falló, dice: {parte.abortada!r}. Confundir "
        "«no pude preguntar» con «no hay nadie» es lo que se lee a las 3 a.m."
    )
    vacio = reconcile.reconciliar(poblado, SimulatedUserDirectory(seed=[]), apply=True)
    assert vacio.abortada != parte.abortada, (
        "el pool caído y el pool vacío dan el MISMO motivo: son dos fallos distintos "
        "y piden dos arreglos distintos"
    )


def test_un_pool_vacio_aborta_en_vez_de_dar_de_baja_a_todos(poblado: psycopg.Connection) -> None:
    """Un pool sin un solo usuario es indistinguible de una lectura fallida que no
    lanzó. Como estado real es absurdo —alguien tuvo que listarlo con una
    credencial— así que se trata como lo que casi seguro es: un fallo."""
    parte = reconcile.reconciliar(poblado, SimulatedUserDirectory(seed=[]), apply=True)

    assert parte.relojes_arrancados == ()
    assert parte.abortada and "cero cuentas" in parte.abortada.lower()
    assert _relojes(poblado) == {}


def test_una_paginacion_que_no_termina_aborta(poblado: psycopg.Connection) -> None:
    """El fallo silencioso: cada página es válida y ninguna lanza, pero el cursor
    no se agota nunca. Quien deje de paginar por un tope se queda con una lista
    corta **que parece completa**, y todos los de las páginas no leídas parecen
    borrados. Se aborta: media lectura no autoriza ninguna baja.
    """
    directorio = _DirectorioQueSeCortaAMedias(seed=[_registro(SE_QUEDA), _registro(SE_FUE)])

    parte = reconcile.reconciliar(poblado, directorio, apply=True)

    assert parte.relojes_arrancados == ()
    assert parte.abortada and "pagina" in parte.abortada.lower().replace("á", "a")
    assert _relojes(poblado) == {}


def test_la_baja_se_escribe_en_el_tenant_QUE_DICE_EL_PADRON(poblado: psycopg.Connection) -> None:
    """Regla de oro 5. La reconciliación corre como job interno y ve el padrón
    ENTERO —sin sesión de tenant—, así que es justo donde un cruce pasaría
    inadvertido: el `tenant_id` de cada baja sale de la fila de `user_profiles`,
    nunca de un parámetro ni del primer tenant que se encuentre.

    **El mismo `user_sub` en dos clientes no se puede probar y no es un descuido:**
    `user_profiles.user_sub` es PRIMARY KEY *global* (`db/schema.sql`), o sea que
    un sub pertenece a un cliente y a uno solo. El primer intento de este test
    sembraba el mismo sub en dos tenants con `ON CONFLICT DO NOTHING` y no
    insertaba nada — pasaba por vacuidad disfrazada de aserción.
    """
    de_otro = "44444444-4444-4444-4444-444444444401"
    reset(poblado)
    poblado.execute(
        "INSERT INTO user_profiles (tenant_id, user_sub, display_name) VALUES (%s,%s,'De Otro')",
        (TENANT_G, de_otro),
    )

    parte = reconcile.reconciliar(
        poblado, SimulatedUserDirectory(seed=[_registro(SE_QUEDA)]), apply=True
    )

    assert set(parte.relojes_arrancados) == {SE_FUE, de_otro}
    filas = dict(
        poblado.execute(
            "SELECT user_sub::text, tenant_id::text FROM user_deactivations "
            "WHERE user_sub IN (%s::uuid, %s::uuid)",
            (SE_FUE, de_otro),
        ).fetchall()
    )
    assert filas == {SE_FUE: TENANT, de_otro: TENANT_G}, (
        f"una baja acabó en el cliente equivocado: {filas}"
    )


def test_el_parte_no_miente_sobre_lo_que_leyo(poblado: psycopg.Connection) -> None:
    """Lo que va al log del cron. Sin estos números, "0 relojes arrancados" se lee
    igual cuando todo está bien que cuando no se leyó nada — y son la diferencia
    entre una corrida sana y una que abortó."""
    directorio = SimulatedUserDirectory(seed=[_registro(SE_QUEDA)])
    parte = reconcile.reconciliar(poblado, directorio, apply=True)

    assert parte.en_el_pool == 1
    assert parte.revisados >= 2, f"solo revisó {parte.revisados} perfiles sin baja"
    # El parte es el registro de lo que se leyó. Que sea inmutable evita que un
    # llamador lo "corrija" antes de imprimirlo y el log cuente otra cosa.
    with pytest.raises(FrozenInstanceError):
        parte.relojes_arrancados = ()  # type: ignore[misc]
