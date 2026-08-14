"""[T-2.81.a] Siembra de VOLUMEN para medir la transacción larga de `prune_pii`.

La ficha dice, literalmente, que la corrida entera es una sola transacción y que
"sobre millones de filas mantiene una transacción larga, y eso **no se ha medido
con volumen real**". Esto es lo que produce el volumen con el que se mide. No
siembra nunca sobre una base que no se le nombre explícitamente en el DSN.

    createdb takab_perf_pii
    DATABASE_URL=postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_perf_pii \\
        uv run alembic upgrade head
    DATABASE_URL=... uv run python scripts/seed_prune_pii_volume.py --tokens 1000000

Se siembra `push_tokens` porque es la regla del plan con menos condiciones
alrededor: mide el coste del `UPDATE` masivo y no el de un predicado raro. Todas
las filas nacen caducadas (`last_seen_at` muy atrás) para que la corrida tenga
que tocarlas TODAS — el peor caso, que es el único que dice algo.
"""

from __future__ import annotations

import argparse
import os
import time
import uuid

import psycopg

TENANTS = 4
LOTE = 50_000


def _dsn(valor: str | None) -> str:
    crudo = valor or os.environ.get("DATABASE_URL", "")
    if not crudo:
        raise SystemExit("falta el DSN: pasa --dsn o exporta DATABASE_URL")
    return crudo.replace("postgresql+psycopg://", "postgresql://")


def sembrar(conn: psycopg.Connection, *, tokens: int, dias: int) -> None:
    tenants: list[str] = []
    for i in range(TENANTS):
        tid = str(uuid.UUID(int=0xA0000000 + i))
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name, visibility) "
            "VALUES (%s,%s,%s,'private') ON CONFLICT DO NOTHING",
            (tid, f"PERF{i}", f"Perf {i}"),
        )
        tenants.append(tid)
    conn.commit()

    por_tenant = tokens // TENANTS
    for tid in tenants:
        hechos = 0
        while hechos < por_tenant:
            n = min(LOTE, por_tenant - hechos)
            t0 = time.perf_counter()
            conn.execute(
                "INSERT INTO push_tokens (tenant_id, user_sub, platform, token, endpoint_arn, "
                "                         created_at, last_seen_at) "
                "SELECT %s, gen_random_uuid(), 'android', "
                "       'tok-' || %s || '-' || g::text, "
                "       'arn:aws:sns:us-east-2:1:endpoint/' || g::text, "
                "       now() - make_interval(days => %s), now() - make_interval(days => %s) "
                "  FROM generate_series(%s, %s) g",
                (tid, tid, dias, dias, hechos + 1, hechos + n),
            )
            conn.commit()
            hechos += n
            print(f"  {tid[:8]} {hechos}/{por_tenant} ({time.perf_counter() - t0:.1f}s)")
    total = conn.execute("SELECT count(*) FROM push_tokens").fetchone()[0]
    print(f"push_tokens sembrados: {total}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tokens", type=int, default=1_000_000)
    p.add_argument("--dias", type=int, default=800)
    p.add_argument("--dsn", default=None)
    args = p.parse_args()
    with psycopg.connect(_dsn(args.dsn), autocommit=False) as conn:
        sembrar(conn, tokens=args.tokens, dias=args.dias)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
