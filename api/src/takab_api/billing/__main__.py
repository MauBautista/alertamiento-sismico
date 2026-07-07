"""Entrypoint del metering: ``python -m takab_api.billing [--day YYYY-MM-DD]``.

Pasada ONE-SHOT (no worker residente): computa los medidores del día indicado
(default: AYER en UTC — el día cerrado más reciente) y termina. Scheduling en
dev = cron o ``make billing``; en AWS = EventBridge→ECS run-task (TODO prod).
Conecta como ``takab_ingest`` (BYPASSRLS): agregación cross-tenant.
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, date, datetime, timedelta

from takab_api.billing.meters import run_billing_pass
from takab_api.db import pool
from takab_api.settings import Settings

log = logging.getLogger("takab_api.billing")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="takab_api.billing", description=__doc__)
    parser.add_argument(
        "--day",
        type=date.fromisoformat,
        default=(datetime.now(tz=UTC) - timedelta(days=1)).date(),
        help="día UTC a medir (default: ayer)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    with pool.connect(settings.database_url) as conn:
        meters = run_billing_pass(conn, settings, args.day)
    log.info("billing %s: %d tenants", args.day.isoformat(), len(meters))


if __name__ == "__main__":
    main()
