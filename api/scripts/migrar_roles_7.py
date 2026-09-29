"""Verifica que el pool de Cognito ya no nombra los roles retirados por D-42 (T-9.21 · T-9.81).

La migración de los 10 roles a los 7 ya se hizo (T-9.21) y T-9.81 dio de baja los tres
viejos en el código y borró sus grupos por terraform. Del script queda UN modo:

    AWS_PROFILE=takab-dev uv run --directory api python scripts/migrar_roles_7.py --verify

Sale 0 SOLO si ningún usuario tiene ``custom:role`` ni grupo en
``takab_api.auth.roles.ROLES_RETIRADOS``; 1 si queda alguno (y lo lista). Un usuario así
ya no entra: con su grupo viejo es 401 ``rol_retirado``, y sin él, «role not in groups».
Se arregla a mano desde la consola (``PATCH /users/{id}``), no con este script.

``--apply`` y ``--dry-run`` se retiraron con la baja: lo DICEN y salen 2 sin tocar nada
(re-migrar hacia grupos que ya no existen no tiene sentido).

El pool sale de ``--pool-id``, o de ``TAKAB_API_COGNITO_USER_POOL_ID``, o del
``terraform output user_pool_id`` de ``infra/terraform/envs/dev``.
"""  # noqa: E501 — el comando se copia entero

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from takab_api.auth.roles import ROLES_RETIRADOS
from takab_api.users.directory import CognitoUserDirectory, UserRecord

_TF_DIR = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "envs" / "dev"

_RETIRADO = (
    "{modo} se retiró con la baja de los roles viejos (T-9.81): la migración ya se hizo. "
    "Usa --verify para comprobar que nadie nombra un rol retirado."
)


def _todos(directory: CognitoUserDirectory) -> list[UserRecord]:
    users: list[UserRecord] = []
    cursor: str | None = None
    while True:
        page, cursor = directory.list_users(limit=60, cursor=cursor)
        users.extend(page)
        if not cursor:
            return users


def _describir(user: UserRecord, grupos: list[str]) -> str:
    ident = f"{user.username} <{user.email}>" if user.email else user.username
    return f"  {ident}  rol={user.role} grupos={','.join(grupos) or '-'}"


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
        raise SystemExit("no sé qué pool: pasa --pool-id o TAKAB_API_COGNITO_USER_POOL_ID")
    return out.stdout.strip()


def main(argv: list[str] | None = None, *, directory: CognitoUserDirectory | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Verifica que nadie nombra un rol retirado por D-42 (T-9.81)."
    )
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--verify", action="store_true", help="0 solo si no queda nadie viejo")
    modo.add_argument("--dry-run", action="store_true", help="RETIRADO (T-9.81): sale 2")
    modo.add_argument("--apply", action="store_true", help="RETIRADO (T-9.81): sale 2")
    ap.add_argument("--pool-id")
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-2"))
    args = ap.parse_args(argv)

    if not args.verify:
        print(_RETIRADO.format(modo="--apply" if args.apply else "--dry-run"), file=sys.stderr)
        return 2
    if directory is None:
        directory = CognitoUserDirectory(
            user_pool_id=_resolver_pool(args.pool_id), region=args.region
        )

    pendientes: list[str] = []
    for user in _todos(directory):
        grupos = directory._groups_of(user.username)
        if user.role in ROLES_RETIRADOS or ROLES_RETIRADOS.intersection(grupos):
            pendientes.append(_describir(user, grupos))

    for linea in pendientes:
        print(linea)
    if pendientes:
        print(f"✗ {len(pendientes)} usuario(s) con rol o grupo retirado", file=sys.stderr)
        return 1
    print("✓ ningún usuario con rol ni grupo retirado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
