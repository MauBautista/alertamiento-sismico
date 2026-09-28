"""[T-9.50 · D-44] Relleno del mapa de la sacudida para incidentes VIEJOS, una vez y a mano.

La pasada del worker mira sólo `incident_review_ttl_s` hacia atrás, y a propósito:
un arranque en frío no puede recalcular meses bloqueando el bucle que sostiene la
actuación comandada por el quórum. Consecuencia: los incidentes anteriores a
`T-9.50` que nunca entraron en revisión se quedaron sin mapa, y los que lo tienen
no tienen superficie (`D-44`). Esto los rellena por rango de fechas.

**No es otra pasada**: es `servicio.run_shakemap_pass` con el rango y sin
presupuesto de reloj, así que el criterio de candidato, el cálculo, el cerrojo
(no pisa al worker) y el UPSERT idempotente son los mismos. Se puede cortar y
volver a correr: lo ya calculado ya no es candidato y la vuelta siguiente sigue
donde se quedó.

Se corre en el contenedor del worker de incidentes, cuyo DSN es `takab_ingest`
(el único escritor de `incident_shakemap`)::

    docker compose exec incident-engine \\
        python -m takab_api.shakemap.rellena --desde 2026-09-01 [--hasta 2026-09-27] [--max 200]

`--hasta` es INCLUSIVO (el día entero). La madurez (`shakemap_espera_s`) se
respeta también aquí: un incidente de hace 30 s no tiene mapa ni a mano.
"""

from __future__ import annotations

import argparse
import math
from datetime import UTC, date, datetime, time, timedelta

from takab_api.db import pool
from takab_api.settings import Settings
from takab_api.shakemap import servicio as S

#: Tope de incidentes por corrida. Lo que no quepa se DICE y entra en la siguiente.
MAX_POR_DEFECTO = 200


def _fecha(valor: str) -> date:
    try:
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"fecha inválida {valor!r}: se espera AAAA-MM-DD") from exc


def _args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m takab_api.shakemap.rellena",
        description="Calcula y persiste el mapa de la sacudida de incidentes viejos (T-9.50).",
    )
    p.add_argument("--desde", type=_fecha, required=True, help="AAAA-MM-DD, inclusivo")
    p.add_argument("--hasta", type=_fecha, default=None, help="AAAA-MM-DD, inclusivo (hoy)")
    p.add_argument("--max", type=int, default=MAX_POR_DEFECTO, help="tope de incidentes")
    return p.parse_args(argv)


def main(argv: list[str] | None = None, *, settings: Settings | None = None) -> S.PasadaDeShakemap:
    """Corre el relleno e imprime lo que hizo, con el corte si lo hubo."""
    args = _args(argv)
    s = settings or Settings()
    desde = datetime.combine(args.desde, time.min, tzinfo=UTC)
    # Inclusivo: hasta el último instante del día pedido.
    hasta = (
        None
        if args.hasta is None
        else datetime.combine(args.hasta + timedelta(days=1), time.min, tzinfo=UTC)
        - timedelta(microseconds=1)
    )
    with pool.connect(s.database_url) as conn:
        # Como el worker, y no como quien sea el DSN: en el contenedor del worker es
        # un no-op; desde el de la API (`takab_app`) muere aquí con «permission
        # denied to set role», que es mejor que morir a mitad en el primer UPSERT; y
        # en local, con el superusuario, ejerce los privilegios que la nube tiene.
        conn.execute('SET ROLE "takab_ingest"')
        conn.commit()
        pasada = S.run_shakemap_pass(
            conn,
            s,
            max_por_pasada=args.max,
            desde=desde,
            hasta=hasta,
            # Sin presupuesto de reloj: aquí no hay bucle que retrasar, y cortar por
            # tiempo una operación manual sólo obligaría a repetirla a ciegas.
            presupuesto_s=math.inf,
        )
    rango = f"{args.desde.isoformat()} … {args.hasta.isoformat() if args.hasta else 'hoy'}"
    print(f"relleno del mapa de la sacudida [{rango}]: {len(pasada.calculados)} mapas calculados")
    for inc in pasada.calculados:
        print(f"  · {inc}")
    if pasada.corte is None:
        print("sin corte: no quedan incidentes pendientes en el rango")
    else:
        # Un no-op silencioso es el modo de fallo más caro de este repositorio.
        print(f"CORTADO POR {pasada.corte.upper()}: vuelve a correrlo para seguir")
    return pasada


if __name__ == "__main__":
    main()
