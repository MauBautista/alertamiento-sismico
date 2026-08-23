"""[T-2.143] El reloj de la PII también arranca con una baja hecha en Cognito.

`T-2.81.b` puso el reloj de retención de nombre y teléfono en `user_deactivations`
y lo escriben las dos vías de la consola: `PATCH {"enabled": false}` y
`DELETE /users/{u}`. Una cuenta retirada **directamente en el pool** —consola de
AWS, CLI— no pasa por ninguna de las dos, así que esa persona conservaba su nombre
y su teléfono indefinidamente. El hueco se cerró **declarándolo**, con una query de
reconciliación en `RUNBOOK-retencion-pii.md §6`; esto la convierte en un paso del
job que ya corre solo, porque *una reconciliación que hay que acordarse de correr
no es retención cumplida*.

LO DIFÍCIL NO ES DAR DE BAJA: ES NEGARSE A HACERLO CON UNA LECTURA A MEDIAS
───────────────────────────────────────────────────────────────────────────
El acto en sí es media línea de SQL. El riesgo está en la premisa, porque **una
lectura incompleta del pool es indistinguible de un montón de bajas**: si el
directorio no responde, si la paginación se corta, si la respuesta viene vacía, la
lista de "usuarios que existen" encoge — y actuar sobre ella arrancaría el reloj
del borrado del nombre de gente que está en el edificio ahora mismo.

De los dos errores posibles, **conservar de más solo incumple un plazo; podar de
menos borra el nombre de alguien a quien una brigada podría estar buscando** (es
el mismo criterio que difiere la poda con un incidente abierto, `retention.py`).
Por eso los tres casos abortan enteros y ninguno actúa "con lo que se pudo leer".

LO QUE ESTE MÓDULO **NO** SABE
──────────────────────────────
**Cuándo** se borró la cuenta. CloudTrail lo sabría; el pool, no — un usuario que
ya no está no tiene fecha de nada. Así que el reloj arranca el día en que la
reconciliación se entera, no el día del hecho. Eso alarga el plazo real, que es el
lado seguro del error, y es la razón de que esto sea una red de seguridad y no la
vía principal: **las bajas se hacen desde la consola de TAKAB**.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from takab_api.users.directory import DirectoryError, UserDirectory

#: Tamaño de página al recorrer el pool. Cognito admite hasta 60 en `ListUsers`.
TAMANO_PAGINA = 60

#: Tope de páginas. No es una optimización: es lo que convierte "el cursor no se
#: agota nunca" en un fallo VISIBLE en vez de un bucle infinito en el cron. Con
#: 60 por página son 60 000 cuentas, dos órdenes de magnitud por encima de
#: cualquier despliegue previsto; llegar aquí significa que algo va mal, no que el
#: cliente creció.
MAX_PAGINAS = 1000

#: `via` con el que se registra la baja detectada. No hay un valor "reconciliado"
#: y no debería haberlo: el esquema solo admite dos porque *un reloj que alguien
#: pueda arrancar sin dar de baja la cuenta deja de ser el reloj de la baja*. Que
#: la cuenta no esté en el directorio ES `account_deleted`, se haya hecho desde
#: donde se haya hecho.
#:
#: Y no es una aproximación cómoda: **toda fila de `user_profiles` nace de un token
#: verificado** (`PUT /me/profile`, `routers/me.py`), o sea de alguien que TUVO
#: cuenta. No existe el perfil de quien nunca la tuvo, así que "ausente del pool"
#: no puede significar otra cosa que "se la borraron".
VIA = "account_deleted"


@dataclass(frozen=True)
class Reconciliacion:
    """El parte de una corrida. Va al log del cron, así que dice lo que leyó.

    Sin `en_el_pool` y `revisados`, un «0 relojes arrancados» se lee igual cuando
    todo está bien que cuando no se pudo leer nada — y son exactamente los dos
    casos que hay que distinguir.
    """

    #: Perfiles del padrón sin baja registrada, en todos los clientes.
    revisados: int
    #: Cuentas leídas del directorio. Cero nunca autoriza a actuar.
    en_el_pool: int
    #: Los `user_sub` a los que se les arrancó el reloj (o se les arrancaría, en
    #: simulacro), ordenados.
    relojes_arrancados: tuple[str, ...]
    #: Por qué NO se actuó, o ``None`` si la corrida fue completa. Que sea texto y
    #: no un booleano es a propósito: el motivo es lo que se lee a las 3 a.m.
    abortada: str | None = None


_SIN_RELOJ = """
SELECT p.tenant_id::text, p.user_sub::text
  FROM user_profiles p
  LEFT JOIN user_deactivations d
    ON d.tenant_id = p.tenant_id AND d.user_sub = p.user_sub
 WHERE d.user_sub IS NULL
 ORDER BY p.user_sub
"""

# `ON CONFLICT DO NOTHING` y no `DO UPDATE`: si ya hay reloj, la persona se fue el
# día que se fue. Reescribir la fecha en cada corrida haría que el plazo no
# venciera nunca y la retención sería decorativa. El `LEFT JOIN` de arriba ya los
# excluye; esto es el cinturón por si dos corridas se solapan.
_ARRANCAR = """
INSERT INTO user_deactivations (tenant_id, user_sub, deactivated_at, via)
VALUES (%s::uuid, %s::uuid, now(), %s)
ON CONFLICT (tenant_id, user_sub) DO NOTHING
"""


def _leer_el_pool(directory: UserDirectory) -> tuple[set[str], str | None]:
    """Todos los `username` del directorio, o el motivo por el que no se pudo.

    Devolver la lista PARCIAL nunca es una opción: quien no aparezca en ella queda
    marcado como borrado, así que media lectura no es media respuesta — es una
    respuesta equivocada sobre todos los que faltan.
    """
    vistos: set[str] = set()
    cursor: str | None = None
    for _ in range(MAX_PAGINAS):
        try:
            pagina, cursor = directory.list_users(limit=TAMANO_PAGINA, cursor=cursor)
        except DirectoryError as exc:
            return set(), f"el directorio no respondió ({exc}): no se dio de baja a nadie"
        vistos.update(u.username for u in pagina)
        if cursor is None:
            return vistos, None
    return set(), (
        f"la paginación del directorio no terminó en {MAX_PAGINAS} páginas: una lista "
        "incompleta marcaría como borrados a todos los que faltan"
    )


def reconciliar(
    conn: psycopg.Connection,
    directory: UserDirectory,
    *,
    apply: bool,
) -> Reconciliacion:
    """Arranca el reloj de quien ya no está en el pool y nunca se dio de baja.

    La sesión la prepara el llamador: esto corre dentro del job de retención, que
    ya se degradó al rol interno (`ops.prune_pii.harden_session`) y por tanto ve el
    padrón de todos los clientes. Aquí no se cambia de rol ni se abre transacción
    — con `apply=False` no se escribe nada y el parte dice igual lo que haría.

    El `tenant_id` de cada baja sale de la fila de `user_profiles`, nunca de un
    parámetro: el mismo `user_sub` presente en dos padrones son dos personas para
    la base, y cada cliente conserva o poda lo suyo (regla de oro 5).
    """
    del_pool, motivo = _leer_el_pool(directory)
    candidatos = conn.execute(_SIN_RELOJ).fetchall()

    if motivo is not None:
        return Reconciliacion(
            revisados=len(candidatos), en_el_pool=0, relojes_arrancados=(), abortada=motivo
        )

    if not del_pool:
        # Un pool sin una sola cuenta es indistinguible de una lectura que falló
        # sin lanzar. Como estado real es absurdo —alguien tuvo que listarlo con
        # una credencial válida— así que se trata como lo que casi seguro es.
        return Reconciliacion(
            revisados=len(candidatos),
            en_el_pool=0,
            relojes_arrancados=(),
            abortada=(
                "el directorio devolvió CERO cuentas: es indistinguible de una lectura "
                "fallida, y actuar daría de baja a todo el padrón"
            ),
        )

    ausentes = [(tenant, sub) for tenant, sub in candidatos if sub not in del_pool]
    if apply:
        for tenant, sub in ausentes:
            conn.execute(_ARRANCAR, (tenant, sub, VIA))

    return Reconciliacion(
        revisados=len(candidatos),
        en_el_pool=len(del_pool),
        relojes_arrancados=tuple(sorted(sub for _tenant, sub in ausentes)),
    )
