"""[T-7.64] Registrar en la nube el firmware que el despliegue acaba de activar.

**EL HECHO, MEDIDO EL 2026-09-20 en la nube dev:** ``SELECT count(*) FROM
fw_releases`` daba **0**. El registro estaba vacío y siempre lo había estado, así
que ``derive_version_drift`` caía —correctamente— en su rama 3, ``SIN
REFERENCIA``: *se sabe qué corre cada gabinete, no si eso es lo actual*. Los
siete estados de versión que construyó ``T-2.69`` estaban vivos y **no podían
distinguir nada**, porque les faltaba la mitad de la comparación: un gabinete con
código de hace un mes y otro recién desplegado se veían IDÉNTICOS en ``/fleet``.

La causa no era un olvido de operación. ``POST /fleet/releases`` existe y está
bien hecho, pero **nadie lo llamaba**: no había una sola línea del despliegue que
escribiera en ``fw_releases``. Un estado inalcanzable no da error — da una
consola que parece funcionar.

POR QUÉ ESTO ES UN CLI Y NO UN ``curl`` AL ENDPOINT
---------------------------------------------------
Porque el endpoint no es alcanzable sin una persona. ``POST /fleet/releases``
exige ``takab_superadmin``, y ese pool es **SRP + MFA TOTP obligatorio**: no hay
cliente ``client_credentials`` en el terraform de identidad, así que no existe
ninguna identidad de máquina que pueda presentarse. Un despliegue que dependiera
de que alguien teclee seis dígitos publicaría tan poco como se publica hoy.

Lo que sí existe es este camino, y es el mismo que usan ``prune_pii``,
``prune_cctv`` y ``restore_check``: un CLI que corre DENTRO de la imagen, contra
la base, declarando su ``app.role``. Con eso se reusa exactamente:

* la misma consulta (``queries.fw_releases.insert_release``) — no una copia;
* el mismo verbo de auditoría (``fw_release_publish``) que escribe el router;
* la misma **GRANT y la misma RLS**: ``fw_rel_publish`` exige
  ``app_role() = 'takab_superadmin'``, y la base sigue siendo quien lo impone.

Declarar el rol no es falsificarlo: quien puede ejecutar esto es quien puede
``ssm send-command`` contra la instancia de la plataforma, o sea el dueño de la
plataforma. Es la misma figura que ``prune_pii`` con su ``JOB_APP_ROLE``. Lo que
cambia respecto del router es el ACTOR que queda en la auditoría: ``deploy:…``
en vez de ``user:…``, que es la verdad — no lo publicó una persona en una
consola, lo publicó un despliegue.

LOS ``-dirty`` NO SE PUBLICAN, Y ES LO IMPORTANTE DE ESTE ARCHIVO
-----------------------------------------------------------------
``deploy/edge/deploy.sh`` construye la versión con ``git describe --always
--dirty``, así que un árbol con cambios sin commitear produce ``62f3f1e-dirty``.
La rama 4 de ``derive_version_drift`` manda esos valores a ``DESCONOCIDA``
**a propósito**: la comparación es por IGUALDAD EXACTA y ``62f3f1e-dirty`` no es
``62f3f1e``, así que la consola dice «esto no es ningún release publicado», que
es exactamente la verdad.

Publicar un ``-dirty`` no añadiría información: **borraría esa señal**. El
registro pasaría a contener una versión que nadie puede reconstruir desde el
repo, y el gabinete que la corre saldría ``AL DÍA`` — el rótulo más tranquilizador
del panel— sobre código que no existe en ningún commit. Por eso se rechaza aquí,
en el que escribe, y no sólo en el que llama.

PUBLICAR DOS VECES LA MISMA VERSIÓN NO ES UN ERROR *AQUÍ*
----------------------------------------------------------
El router devuelve 409, y hace bien: una persona que publica a mano dos veces el
mismo SHA está preguntando «¿el de ayer o el de hoy?». Pero un despliegue repite
el mismo SHA de forma rutinaria —se redespliega tras un canary fallido, o el
mismo commit va a dos gabinetes— y ahí la respuesta correcta no es un fallo: es
«ya estaba, y su fecha original es la buena».

Que la fecha original se conserve no es cortesía: ``released_at`` es lo que
``release_age_s`` convierte en «cuánto lleva la flota corriendo código viejo».
Reescribirlo reescribiría a posteriori la deriva de TODA la flota, y por eso
``fw_releases`` no admite UPDATE (append-only por privilegio) y ``_INSERT`` no
lleva ``ON CONFLICT``. Aquí se traduce el ``IntegrityError`` a un desenlace
benigno **sin tocar la fila que ya existe**.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import sys

from sqlalchemy.exc import IntegrityError

from takab_api.audit import audit_async
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.queries import fw_releases as qr

log = logging.getLogger("takab_api.ops.publish_release")

#: El rol que la RLS de ``fw_releases`` exige para INSERT (``fw_rel_publish``).
#: Se nombra aquí, junto al único sitio que lo usa, por la misma razón que
#: ``prune_pii.JOB_APP_ROLE``: un rol declarado a mano en varios sitios deriva.
APP_ROLE = "takab_superadmin"

#: Sufijo que ``git describe --always --dirty`` añade con el árbol sucio.
SUFIJO_SUCIO = "-dirty"

#: Desenlaces. No son "éxito y error": son TRES, y el del medio es el que evita
#: que un redespliegue rutinario se lea como un fallo del despliegue.
PUBLICADA = "publicada"
YA_ESTABA = "ya_estaba"
RECHAZADA_SUCIA = "rechazada_sucia"

#: Códigos de salida. El 3 es distinto del 1 a propósito: quien llama necesita
#: poder distinguir «no se pudo hablar con la base» (reintentable, y el
#: despliegue lo declara) de «esta versión no debe publicarse nunca» (final, y no
#: hay nada que reintentar).
SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_SUCIA = 3


def es_publicable(version: str) -> bool:
    """¿Esta versión puede entrar en el registro?

    Regla ÚNICA y derivable de la de ``deploy/edge/deploy.sh``: se publica lo que
    identifica un commit reproducible. Un ``-dirty`` no lo es, y una versión
    vacía tampoco identifica nada — publicarla haría ``AL DÍA`` a cualquier
    gabinete que reportara la cadena vacía.
    """
    return bool(version) and not version.endswith(SUFIJO_SUCIO)


def actor_por_defecto() -> str:
    """Quién publica, dicho como lo entiende quien lee la auditoría.

    ``deploy:<usuario>@<host>`` y no ``user:<uuid>``: la fila de ``audit_log``
    tiene que distinguir un release que publicó un despliegue de uno que publicó
    una persona en la consola. Son dos hechos distintos y hoy sólo existe el
    segundo como forma de decirlo.
    """
    usuario = os.environ.get("TAKAB_DEPLOY_ACTOR") or os.environ.get("USER") or "desconocido"
    return f"deploy:{usuario}@{socket.gethostname()}"


async def publicar(
    version: str,
    *,
    notes: str | None = None,
    actor: str | None = None,
) -> str:
    """Registra ``version``. Devuelve uno de los tres desenlaces de arriba.

    No recibe ``released_at``: la fecha es la del INSERT. Dejar que quien llama
    la elija abriría la puerta a fechar un release en el pasado, y ``released_at``
    es lo que ordena el registro — o sea, lo que decide el ``releases_behind`` de
    toda la flota.
    """
    if not es_publicable(version):
        return RECHAZADA_SUCIA

    quien = actor or actor_por_defecto()
    ctx = SessionCtx(tenant_id="", role=APP_ROLE, user_id="")
    try:
        async with get_tenant_conn(ctx) as conn:
            await qr.insert_release(
                conn,
                version=version,
                released_at=None,
                notes=notes,
                published_by=quien,
            )
            # Dentro de la MISMA transacción que el INSERT: un release publicado
            # sin su fila de auditoría sería un cambio de plataforma sin autor, y
            # es justo el dato que hace falta el día que alguien pregunte por qué
            # la flota entera cambió de estado.
            await audit_async(
                conn,
                tenant_id=None,
                actor=quien,
                verb="fw_release_publish",
                obj=f"fw_release:{version}",
                meta={"version": version, "via": "deploy"},
            )
    except IntegrityError:
        # El UNIQUE de `version`. La fila que ya existe NO se toca: su
        # `released_at` es el bueno (ver la cabecera del módulo).
        return YA_ESTABA
    return PUBLICADA


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="takab-publish-release",
        description="Registra en `fw_releases` el firmware que un despliegue activó.",
    )
    p.add_argument(
        "version",
        help=(
            "EXACTAMENTE el valor que el gabinete escribirá en su FW_VERSION. "
            "La comparación de la deriva es por IGUALDAD: un espacio de más aquí "
            "volvería DESCONOCIDA a toda la flota que corra ese código."
        ),
    )
    p.add_argument("--notes", default=None, help="Procedencia legible (host, release_id…).")
    p.add_argument(
        "--actor",
        default=None,
        help="Quién publica; por defecto `deploy:<usuario>@<host>`.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    version = args.version.strip()

    desenlace = asyncio.run(publicar(version, notes=args.notes, actor=args.actor))

    if desenlace == RECHAZADA_SUCIA:
        # A stderr y con la razón, no sólo el veredicto: quien lo lea está
        # mirando la salida de un despliegue que acaba de terminar BIEN.
        print(
            f"NO se publica '{version}': no identifica un commit reproducible.\n"
            "  Un `-dirty` en el registro haría AL DÍA a un gabinete que corre "
            "código que no existe en ningún commit, y borraría la señal "
            "DESCONOCIDA que hoy lo delata. Despliega desde un árbol limpio.",
            file=sys.stderr,
        )
        return SALIDA_SUCIA

    if desenlace == YA_ESTABA:
        print(f"'{version}' ya estaba publicada; se conserva su fecha original.")
        return SALIDA_OK

    print(f"release publicada: {version}")
    return SALIDA_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
