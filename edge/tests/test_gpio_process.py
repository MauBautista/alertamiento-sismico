"""gpio como proceso mínimo y auditable (regla de oro 4): sin deps pesadas, <1 s.

El camino de vida corre en su propio proceso (`python -m takab_edge.gpio`) que NO
arrastra ObsPy/NumPy/SciPy (que podrían tardar/colgar) ni el resto del edge.
"""

from __future__ import annotations

import os
import subprocess
import sys

_HEAVY = ("numpy", "obspy", "scipy", "pandas", "matplotlib")


def _run(code: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "GPIOZERO_PIN_FACTORY": "mock"}
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_gpio_process_does_not_import_heavy_deps():
    code = (
        "import sys, takab_edge.gpio.__main__;"
        f"heavy=[m for m in {_HEAVY!r} if m in sys.modules];"
        "print('HEAVY:' + ','.join(heavy))"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    loaded = result.stdout.split("HEAVY:")[1].strip()
    assert loaded == "", f"el proceso gpio cargó deps pesadas: {loaded}"


def test_gpio_process_starts_under_one_second():
    # Mide desde el primer import hasta que el controlador arrancó (incluye gpiozero
    # + MockFactory + 5 relés + 3 botones). El arranque del intérprete queda fuera.
    code = (
        "import time; t0 = time.perf_counter();"
        "from takab_edge.config import load_settings;"
        "from takab_edge.gpio.__main__ import run_gpio_process;"
        "c = run_gpio_process(load_settings(), block=False);"
        "dt = time.perf_counter() - t0; c.stop();"
        "import sys; sys.stdout.write(f'ELAPSED:{dt:.4f}')"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    elapsed = float(result.stdout.split("ELAPSED:")[1])
    assert elapsed < 1.0, f"arranque del proceso gpio {elapsed:.3f}s ≥ 1 s"


def test_gpio_process_module_runs_and_stops():
    # Sanidad del entry point real: arranca y para limpio, sin excepción.
    code = (
        "from takab_edge.config import load_settings;"
        "from takab_edge.gpio.__main__ import run_gpio_process;"
        "c = run_gpio_process(load_settings(), block=False);"
        "assert c.running; c.stop(); assert not c.running; print('OK')"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
