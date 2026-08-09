"""`takab-gpioctl` — interroga al DUEÑO de los pines desde el shell.

[T-2.70.a·D2/P2] Es lo que `deploy.sh` y el traspaso de D3 necesitan: poder
preguntar «¿quién sostiene los pines, está en marcha, cómo están los cinco relés
y qué edad tiene ese dato?» sin importar `takab_edge.supervisor` ni instanciar un
segundo `GpioController` (que el cerrojo de D1.1 rechazaría, con razón).

**Interroga, NO acciona — y es una decisión, no un olvido.** Una CLI capaz de
silenciar la sirena o comandar relés sería una segunda puerta a los actuadores:
sin el PIN del panel, sin quedar en su registro de acciones y sin el ack firmado
que la nube exige (regla de oro 8). Lo que el despliegue necesita es SABER, y eso
es todo lo que hay aquí. Anclado por test.

Códigos de salida, que son el contrato real con el script:

* ``0`` el dueño contestó (y con ``--esperar``, además está listo).
* ``3`` nadie contesta en esa ruta: no hay dueño, o todavía no ha atado el socket.
* ``4`` contestó pero el gabinete NO está en marcha (`running=False`).
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from takab_edge.gpio_link import GpioLinkUnavailable
from takab_edge.pinlink.client import IpcGpioLink

SALIDA_OK = 0
SALIDA_SIN_DUENO = 3
SALIDA_NO_EN_MARCHA = 4


def _formato_humano(estado: dict) -> str:
    relés = "\n".join(
        f"  {r['channel']:<14} {'ENERGIZADO' if r['energized'] else 'en reposo':<11}"
        f" {'PROTEGIENDO' if r['activated'] else '-':<12} fail-safe={r['fail_safe']}"
        for r in estado["relays"]
    )
    latencia = estado.get("last_reflex_latency_s")
    return "\n".join(
        [
            f"dueño de los pines: EN MARCHA (dato de hace {estado['age_s'] * 1000:.0f} ms)"
            if estado["running"]
            else "dueño de los pines: DETENIDO",
            f"SASMEX enclavado:   {'SÍ' if estado['sasmex_active'] else 'no'}",
            f"sirena:             {'SONANDO' if estado['siren_sounding'] else 'en reposo'}"
            f" ({estado['siren_reason'] or 'sin razón'})",
            f"audibles:           {'SILENCIADOS' if estado['audible_silenced'] else 'armados'}",
            f"modo prueba WR-1:   {'ARMADO' if estado['test_mode_active'] else 'no'}",
            f"último reflejo:     {latencia * 1000:.2f} ms"
            if latencia is not None
            else "último reflejo:     sin medir desde el arranque",
            "relés:",
            relés,
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="takab-gpioctl",
        description="Interroga al dueño de los pines del gabinete (solo lectura).",
    )
    parser.add_argument(
        "--socket", default="", help="ruta del socket (por defecto, la de la config)"
    )
    parser.add_argument("--json", action="store_true", help="salida cruda para scripts")
    parser.add_argument("--timeout", type=float, default=3.0, help="segundos de espera")
    parser.add_argument(
        "--esperar",
        action="store_true",
        help="reintenta hasta el timeout en vez de rendirse al primer intento",
    )
    args = parser.parse_args(argv)

    ruta = args.socket
    if not ruta:
        from takab_edge.config import load_settings

        ruta = load_settings().gpio_socket_file

    link = IpcGpioLink(ruta=ruta, espera_inicial_s=args.timeout if args.esperar else 0.5)
    link.start()
    try:
        limite = time.monotonic() + (args.timeout if args.esperar else 0.0)
        while True:
            try:
                snap = link.snapshot()
                break
            except GpioLinkUnavailable as exc:
                if time.monotonic() >= limite:
                    print(  # noqa: T201 — es una CLI: su salida ES el producto
                        f"takab-gpioctl: el dueño de los pines no contesta en {ruta}: {exc}",
                        file=sys.stderr,
                    )
                    return SALIDA_SIN_DUENO
                time.sleep(0.1)
    finally:
        link.stop()

    from takab_edge.pinlink import codec as cd

    estado = cd.instantanea_a_json(snap)
    estado["age_s"] = round(snap.age_s, 4)
    print(json.dumps(estado, indent=2) if args.json else _formato_humano(estado))  # noqa: T201
    return SALIDA_OK if snap.running else SALIDA_NO_EN_MARCHA


if __name__ == "__main__":  # pragma: no cover — entry point
    raise SystemExit(main())
