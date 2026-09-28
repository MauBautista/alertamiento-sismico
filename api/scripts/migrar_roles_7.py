"""Migra el pool de Cognito de los 10 roles a los 7 de D-42 (T-9.21).

Tres modos, uno por invocación. Se corren desde la raíz del repo, en este orden:

    AWS_PROFILE=takab-dev uv run --directory api python scripts/migrar_roles_7.py --dry-run

    AWS_PROFILE=takab-dev uv run --directory api python scripts/migrar_roles_7.py --apply --map mauriciobaujim+building_admin@gmail.com=tenant_admin

    AWS_PROFILE=takab-dev uv run --directory api python scripts/migrar_roles_7.py --verify

El pool sale de ``--pool-id``, o de ``TAKAB_API_COGNITO_USER_POOL_ID``, o del
``terraform output user_pool_id`` de ``infra/terraform/envs/dev``.

**Qué hace, por usuario con rol o grupo viejo** (``soc_operator``, ``security_guard``,
``building_admin``; ver ``takab_api/auth/roles.py``):

- Destino: el del ``--map usuario=rol`` si lo hay (``usuario`` = username —el ``sub``—
  o email); si no, el alias de D-42 (``soc_operator → tenant_admin``,
  ``security_guard → brigadista``). **``building_admin`` NO tiene destino por
  defecto**: ``--apply`` se NIEGA a escribir nada mientras algún ``building_admin``
  no tenga su ``--map`` explícito (D-42: quien necesite consola pasa a
  ``tenant_admin``; quien no, a ``brigadista`` con su inmueble).
- Orden (DISENO-F2 §6), el mismo que ``CognitoUserDirectory.update_user`` defiende:
  1. entrar al grupo NUEVO (nunca hay un instante sin grupo válido);
  2. ``custom:role`` al canónico; ``tenant_admin`` ⇒ ``custom:site_scope='*'``;
     ``brigadista`` ⇒ conserva su inmueble y ``custom:surface`` nunca ``web``
     (``web`` → ``mobile``; un ``building_admin`` que usaba la consola → ``both``);
  3. salir del grupo VIEJO.
- Se NIEGA también a convertir en ``brigadista`` a un ``building_admin`` con
  ``site_scope`` ``*`` o vacío: sería ``manual_activate`` en TODOS los inmuebles del
  cliente, una escalada que no decide un script.

Idempotente: lo ya canónico no se toca, y una pasada cortada a medias (rol nuevo pero
todavía en el grupo viejo) se remata en la siguiente. ``--verify`` sale 0 SOLO si ya
nadie tiene rol ni grupo viejo: es la condición para T-9.81 (borrar los grupos).

Los grupos viejos NO se borran aquí (terraform, T-9.81).
"""  # noqa: E501 — los comandos se copian enteros

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from takab_api.auth.matrix import INTERNAL_ROLES
from takab_api.auth.roles import ALIAS_HEREDADOS, CANONICAL_ROLES
from takab_api.users.directory import (
    ATTR_ROLE,
    ATTR_SITE_SCOPE,
    ATTR_SURFACE,
    CognitoUserDirectory,
    UserRecord,
)

#: Destinos que un ``--map`` puede pedir: los canónicos que un cliente puede tener.
#: Los internos de TAKAB (superadmin, soporte) NO se reparten desde un script.
DESTINOS_MAPEABLES = tuple(r for r in CANONICAL_ROLES if r not in INTERNAL_ROLES)

#: Roles viejos sin destino por defecto: exigen ``--map`` explícito.
SIN_DESTINO_POR_DEFECTO = frozenset({"building_admin"})

_TF_DIR = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "envs" / "dev"


@dataclass
class Plan:
    user: UserRecord
    grupos: list[str]
    destino: str | None
    atributos: dict[str, str] = field(default_factory=dict)
    quitar: list[str] = field(default_factory=list)
    bloqueo: str = ""

    @property
    def pendiente(self) -> bool:
        return bool(self.bloqueo or self.atributos or self.quitar) or (
            self.destino is not None and self.destino not in self.grupos
        )


def _todos(directory: CognitoUserDirectory) -> list[UserRecord]:
    users: list[UserRecord] = []
    cursor: str | None = None
    while True:
        page, cursor = directory.list_users(limit=60, cursor=cursor)
        users.extend(page)
        if not cursor:
            return users


def _clave(user: UserRecord, mapa: dict[str, str]) -> str | None:
    for k in (user.username, user.username.lower(), user.email.lower()):
        if k and k in mapa:
            return k
    return None


def _planear(user: UserRecord, grupos: list[str], mapa: dict[str, str]) -> Plan | None:
    viejo_rol = user.role in ALIAS_HEREDADOS
    viejos_grupos = [g for g in grupos if g in ALIAS_HEREDADOS]
    if not viejo_rol and not viejos_grupos:
        return None
    clave = _clave(user, mapa)
    if clave is not None:
        destino: str | None = mapa[clave]
    elif user.role in SIN_DESTINO_POR_DEFECTO:
        return Plan(
            user,
            grupos,
            None,
            bloqueo=f"building_admin sin destino: pasa --map {user.email or user.username}"
            "=tenant_admin (consola) o =brigadista (móvil, con su inmueble)",
        )
    elif viejo_rol:
        destino = ALIAS_HEREDADOS[user.role]
    else:
        destino = user.role  # rol ya canónico: solo queda salir del grupo viejo

    plan = Plan(user, grupos, destino)
    if destino == "tenant_admin":
        if user.site_scope != "*":
            plan.atributos[ATTR_SITE_SCOPE] = "*"
    elif destino == "brigadista":
        # Se bloquea quien GANARÍA permisos de campo en todo el cliente: `soc_operator`
        # no tenía manual_activate ni siren_silence (revisión de F2). `building_admin`
        # también, por prudencia: su destino se decide a mano (tenant_admin o brigadista
        # acotado). `security_guard` ya tenía esos permisos con el mismo alcance.
        if user.role in ("soc_operator", "building_admin") and user.site_scope.strip() in ("", "*"):
            plan.bloqueo = (
                f"{user.role} con site_scope '{user.site_scope}' → brigadista tendría "
                "manual_activate en TODOS los inmuebles: acota su site_scope antes o "
                "mapéalo a tenant_admin"
            )
            return plan
        surface = user.surface
        if user.role == "building_admin" and surface == "web":
            surface = "both"
        elif surface not in ("mobile", "both"):
            surface = "mobile"
        if surface != user.surface:
            plan.atributos[ATTR_SURFACE] = surface
    if user.role != destino:
        plan.atributos[ATTR_ROLE] = destino
    plan.quitar = [g for g in grupos if g in ALIAS_HEREDADOS and g != destino]
    return plan


def _describir(plan: Plan) -> str:
    u = plan.user
    ident = f"{u.username} <{u.email}>" if u.email else u.username
    antes = f"rol={u.role} grupos={','.join(plan.grupos) or '-'} scope={u.site_scope!r}"
    if plan.bloqueo:
        return f"  BLOQUEADO  {ident}  {antes}\n             {plan.bloqueo}"
    cambios = [f"+grupo {plan.destino}"] if plan.destino not in plan.grupos else []
    cambios += [f"{k}={v}" for k, v in sorted(plan.atributos.items())]
    cambios += [f"-grupo {g}" for g in plan.quitar]
    return f"  {ident}  {antes}\n    → {plan.destino}: {'; '.join(cambios) or 'nada'}"


def _parse_map(items: list[str]) -> dict[str, str]:
    mapa: dict[str, str] = {}
    for item in items:
        usuario, sep, rol = item.partition("=")
        if not sep or not usuario or not rol:
            raise ValueError(f"--map mal formado: {item!r} (usa usuario=rol)")
        if rol not in DESTINOS_MAPEABLES:
            raise ValueError(
                f"--map {item!r}: destino no permitido; "
                f"elige uno de {', '.join(DESTINOS_MAPEABLES)}"
            )
        mapa[usuario.lower() if "@" in usuario else usuario] = rol
    return mapa


def _aplicar(directory: CognitoUserDirectory, plan: Plan) -> None:
    u = plan.user.username
    assert plan.destino is not None
    if plan.destino not in plan.grupos:
        directory._call(
            "admin_add_user_to_group",
            UserPoolId=directory._pool,
            Username=u,
            GroupName=plan.destino,
        )
    if plan.atributos:
        directory.update_user(u, attributes=plan.atributos, role=None)
    for grupo in plan.quitar:
        directory._call(
            "admin_remove_user_from_group",
            UserPoolId=directory._pool,
            Username=u,
            GroupName=grupo,
        )


def _resolver_pool(pool_id: str | None) -> str:
    if pool_id:
        return pool_id
    env = os.environ.get("TAKAB_API_COGNITO_USER_POOL_ID", "")
    if env:
        return env
    out = subprocess.run(
        ["terraform", f"-chdir={_TF_DIR}", "output", "-raw", "user_pool_id"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit("no sé qué pool migrar: pasa --pool-id o TAKAB_API_COGNITO_USER_POOL_ID")
    return out.stdout.strip()


def main(argv: list[str] | None = None, *, directory: CognitoUserDirectory | None = None) -> int:
    ap = argparse.ArgumentParser(description="Migra Cognito a los 7 roles de D-42 (T-9.21).")
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--dry-run", action="store_true", help="lista y no escribe")
    modo.add_argument("--apply", action="store_true", help="migra (idempotente)")
    modo.add_argument("--verify", action="store_true", help="0 solo si no queda nadie viejo")
    ap.add_argument("--map", action="append", default=[], metavar="USUARIO=ROL")
    ap.add_argument("--pool-id")
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-2"))
    args = ap.parse_args(argv)

    try:
        mapa = _parse_map(args.map)
    except ValueError as exc:
        print(f"NO se aplica nada: {exc}", file=sys.stderr)
        return 2
    if directory is None:
        directory = CognitoUserDirectory(
            user_pool_id=_resolver_pool(args.pool_id), region=args.region
        )

    planes: list[Plan] = []
    usados: set[str] = set()
    for user in _todos(directory):
        grupos = directory._groups_of(user.username)
        clave = _clave(user, mapa)
        if clave:
            usados.add(clave)  # un usuario ya migrado cuenta: re-ejecutar no falla
        plan = _planear(user, grupos, mapa)
        if plan is not None and plan.pendiente:
            planes.append(plan)

    if args.verify:
        for plan in planes:
            print(_describir(plan))
        if planes:
            print(f"✗ {len(planes)} usuario(s) con rol o grupo viejo", file=sys.stderr)
            return 1
        print("✓ ningún usuario con rol ni grupo viejo")
        return 0

    print(f"{len(planes)} usuario(s) por migrar")
    for plan in planes:
        print(_describir(plan))
    huerfanos = sorted(set(mapa) - usados)
    if args.dry_run:
        for h in huerfanos:
            print(f"  AVISO: --map {h} no corresponde a ningún usuario del pool")
        return 0

    errores = [f"{p.user.username}: {p.bloqueo}" for p in planes if p.bloqueo]
    errores += [f"--map {h}: no corresponde a ningún usuario del pool" for h in huerfanos]
    if errores:
        print("NO se aplica nada:", file=sys.stderr)
        for e in errores:
            print(f"  {e}", file=sys.stderr)
        return 2
    for plan in planes:
        _aplicar(directory, plan)
        print(f"  ✓ {plan.user.username} → {plan.destino}")
    print("hecho; confirma con --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
