"""T-2.78.a · Acuñar, listar y revocar credenciales de guardia.

    python -m takab_api.ops.oncall issue  --label "Mauricio (primaria)" --days 90
    python -m takab_api.ops.oncall list
    python -m takab_api.ops.oncall revoke --contact-id <uuid>

**El secreto se enseña UNA vez y aquí**, al acuñarlo: la base guarda solo su
hash (``hash_ack_token``), así que no hay ningún sitio del que recuperarlo. Si se
pierde, se revoca y se acuña otro — que es el comportamiento que se quiere de una
credencial, y la razón por la que esto no es un endpoint de la consola: un
secreto que viaja por una respuesta HTTP acaba en un log de acceso, en un
historial de sesión o en una captura de pantalla.

Va por CLI y no por API por una segunda razón, operativa: dar de alta a alguien
de guardia es un acto **raro y deliberado** (semanas o meses entre uno y otro), y
lo hace quien ya tiene acceso a la instancia. Un endpoint para eso sería una
superficie más que defender a cambio de cero comodidad real.

Conecta con el DSN de ``TAKAB_API_DATABASE_URL`` como el resto de utilidades de
operación (``takab_ingest``, BYPASSRLS): ``ops_oncall_contacts`` tiene RLS con
FORCE y una política de negación explícita, así que ningún rol de aplicación la
lee — ni siquiera para contar filas.
"""

from __future__ import annotations

import argparse
import sys

import psycopg

from takab_api.db import pool
from takab_api.ops.alerts import hash_ack_token, new_ack_token
from takab_api.settings import Settings

_ISSUE = """
INSERT INTO ops_oncall_contacts (label, token_hash, expires_at)
VALUES (%(label)s, %(hash)s, now() + make_interval(days => %(days)s))
RETURNING contact_id, expires_at
"""

_LIST = """
SELECT contact_id, label, issued_at, expires_at, revoked_at,
       (revoked_at IS NULL AND expires_at > now()) AS vigente
  FROM ops_oncall_contacts ORDER BY issued_at
"""

_REVOKE = """
UPDATE ops_oncall_contacts SET revoked_at = now()
 WHERE contact_id = %(id)s AND revoked_at IS NULL
RETURNING label
"""


def issue(conn: psycopg.Connection, *, label: str, days: int) -> tuple[str, str]:
    """Acuña una credencial. Devuelve ``(contact_id, secreto)``; el secreto no se
    vuelve a poder leer."""
    secreto = new_ack_token()
    with conn.cursor() as cur:
        cur.execute(_ISSUE, {"label": label, "hash": hash_ack_token(secreto), "days": days})
        fila = cur.fetchone()
    conn.commit()
    contact_id = fila["contact_id"] if isinstance(fila, dict) else fila[0]
    return str(contact_id), secreto


def revoke(conn: psycopg.Connection, *, contact_id: str) -> str | None:
    """Revoca en el acto. Devuelve la etiqueta, o ``None`` si no había nada que
    revocar (id inexistente o ya revocada) — las dos son el mismo no-op."""
    with conn.cursor() as cur:
        cur.execute(_REVOKE, {"id": contact_id})
        fila = cur.fetchone()
    conn.commit()
    if fila is None:
        return None
    return fila["label"] if isinstance(fila, dict) else fila[0]


def listar(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(_LIST)
        return [dict(f) for f in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="takab-oncall", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_issue = sub.add_parser("issue", help="acuña una credencial de guardia")
    p_issue.add_argument("--label", required=True, help="a nombre de quién queda el acuse")
    p_issue.add_argument("--days", type=int, default=90, help="vigencia en días (default 90)")

    sub.add_parser("list", help="quién tiene credencial y hasta cuándo")

    p_rev = sub.add_parser("revoke", help="revoca una credencial en el acto")
    p_rev.add_argument("--contact-id", required=True)

    args = parser.parse_args(argv)
    with pool.connect(Settings().database_url) as conn:
        if args.cmd == "issue":
            if args.days < 1:
                print("la vigencia tiene que ser de al menos un día", file=sys.stderr)
                return 2
            contact_id, secreto = issue(conn, label=args.label, days=args.days)
            print(f"contact_id : {contact_id}")
            print(f"etiqueta   : {args.label}")
            print(f"credencial : {secreto}")
            print(
                "\nGuárdala AHORA en el gestor de contraseñas de la persona: solo vive el "
                "hash y no hay de dónde recuperarla.\nSe usa en la página de acuse "
                "(`/api/ops/alerts/ack`), que el gestor rellena sola."
            )
            return 0
        if args.cmd == "revoke":
            label = revoke(conn, contact_id=args.contact_id)
            print(f"revocada: {label}" if label else "nada que revocar (o ya estaba revocada)")
            return 0
        for fila in listar(conn):
            estado = "vigente" if fila["vigente"] else "NO vigente"
            print(
                f"{fila['contact_id']}  {estado:<10}  hasta {fila['expires_at']}  {fila['label']}"
            )
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
