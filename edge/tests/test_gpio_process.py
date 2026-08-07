"""gpio como proceso mínimo y auditable (regla de oro 4): sin deps pesadas, <1 s.

El camino de vida corre en su propio proceso (`python -m takab_edge.gpio`) que NO
arrastra ObsPy/NumPy/SciPy (que podrían tardar/colgar) ni el resto del edge.

[T-2.70.a · D1.3] EL PRESUPUESTO DE DEPENDENCIAS, DERIVADO
----------------------------------------------------------
Hasta hoy «mínimo» se vigilaba con una BLACKLIST de cinco nombres
(`numpy, obspy, scipy, pandas, matplotlib`). Esa guarda es *fail-open*: pasa
cualquier librería que nadie haya escrito en la lista — y la lista no contiene
ni una librería de IPC, que es exactamente lo que los pasos siguientes de
T-2.70.a van a introducir (`pyzmq`, `msgpack`, `grpcio`, `protobuf`, `paho`…).

**El invariante elegido: una ALLOWLIST de paquetes de terceros.** Todo lo que el
proceso importe tiene que ser stdlib, código de este repo, o uno de los paquetes
explícitamente permitidos abajo. Es *fail-closed*: una dependencia nueva —la que
sea, la haya previsto alguien o no— pone el build en rojo hasta que alguien la
autorice A PROPÓSITO, con su razón escrita al lado.

Por qué NO los otros dos candidatos, medido y no supuesto:

* **Tope de módulos.** Medido en esta máquina: el proceso carga ~340 módulos, y
  añadirle `asyncio + http.server + socketserver + ssl + multiprocessing + json`
  sólo suma **+17** (pydantic y gpiozero ya arrastran casi todo el grafo común).
  Un tope con holgura suficiente para sobrevivir a un cambio de parche del
  intérprete no vería entrar un stack de IPC entero: sería una guarda verde que
  no atrapa nada, que es justo el patrón que esta sesión lleva cinco veces.
* **Tiempo de import.** Depende de la máquina (un runner de CI frío contra un
  portátil caliente varía varias veces), así que como gate es ruido. El
  presupuesto temporal ya lo cubre `test_gpio_process_starts_under_one_second`,
  que mide arranque COMPLETO y tiene una cota con significado físico.

Y la allowlist tiene la propiedad que ninguno de los otros dos tiene: al fallar
puede decir **QUÉ** entró y **POR DÓNDE** — la cadena de imports que lo trajo,
leída de `python -X importtime`, que es información de la propia máquina y no de
una lista escrita a mano.

Nota deliberada: un IPC hecho con **socket UNIX + json de la stdlib** pasa esta
guarda, y debe pasarla — es precisamente la forma que la regla de oro 4 pide.
Lo que la guarda prohíbe es pagar una dependencia de terceros por ello.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

_HEAVY = ("numpy", "obspy", "scipy", "pandas", "matplotlib")

#: Paquetes de TERCEROS que el proceso mínimo tiene permitido cargar, cada uno
#: con la razón por la que está. Añadir un nombre aquí es una decisión de
#: arquitectura sobre el camino de vida, no un trámite: este proceso es el que
#: toca la sirena, la válvula de gas y los retenedores de puerta.
_EXTERNOS_PERMITIDOS: dict[str, str] = {
    "gpiozero": "el driver de pines; ES el trabajo de este proceso",
    "colorzero": "dependencia directa de gpiozero (no se elige por separado)",
    "lgpio": "backend GPIO de producción del Pi (en la suite manda GPIOZERO_PIN_FACTORY=mock)",
    "pydantic": "modelo de EdgeSettings (mapa de pines y perfil fail-safe)",
    "pydantic_core": "núcleo compilado de pydantic",
    "pydantic_settings": "carga la config desde /etc/takab/edge.env",
    "dotenv": "lo arrastra pydantic_settings para leer el .env",
    "annotated_types": "dependencia de pydantic",
    "typing_extensions": "dependencia de pydantic",
    "typing_inspection": "dependencia de pydantic",
}

#: Paquetes de ESTE repo (no son «terceros»: viajan en el rsync del deploy).
_PAQUETES_LOCALES = frozenset({"takab_edge", "simulators"})

#: Lo que no es «un paquete de terceros» aunque no esté en
#: `sys.stdlib_module_names`. Aquí había un `not raiz.startswith("_")`, y eso NO
#: era una propiedad de la stdlib: era un COMODÍN. Un módulo de primer nivel con
#: guion bajo es una forma perfectamente normal de distribuir una extensión C de
#: terceros —`_cffi_backend` (cffi), `_cmsgpack`, `_ssl` de un wheel— y el
#: comodín los dejaba pasar TODOS al proceso que toca la sirena y el gas.
#: Cada entrada, medida en este árbol, con su razón:
_NO_SON_DEPENDENCIAS: dict[str, str] = {
    "__main__": "el propio `python -c` de esta medición; no es un paquete",
    "_virtualenv": "lo inyecta el .pth del venv ANTES de cualquier import nuestro",
    "_distutils_hack": "lo inyecta `distutils-precedence.pth` de setuptools, igual",
}

#: `_sysconfigdata__linux_x86_64-linux-gnu` (y su gemelo `…aarch64…` en el Pi):
#: ES stdlib, pero su nombre lleva la plataforma dentro, así que no puede estar
#: en `sys.stdlib_module_names` ni en una lista escrita a mano. Se reconoce por
#: FORMA, y el prefijo es el del propio CPython (`sysconfig._get_sysconfigdata_name`).
_RE_SYSCONFIGDATA = re.compile(r"^_sysconfigdata_")


def _dependencias_no_autorizadas(raices: set[str]) -> list[str]:
    """Paquetes de terceros que nadie autorizó, dado el conjunto de raíces cargadas.

    Función y no expresión suelta dentro del test para poder medirla contra
    raíces de mentira (ver `test_la_allowlist_no_tiene_comodines`).
    """
    return sorted(
        raiz
        for raiz in raices
        if raiz not in sys.stdlib_module_names
        and raiz not in _EXTERNOS_PERMITIDOS
        and raiz not in _PAQUETES_LOCALES
        and raiz not in _NO_SON_DEPENDENCIAS
        and not _RE_SYSCONFIGDATA.match(raiz)
    )


#: `import time: %9d | %10d | <2·profundidad espacios><nombre>`
_RE_IMPORTTIME = re.compile(r"^import time:\s*(\d+) \|\s*(\d+) \|( *)(\S+)\s*$")


def _run(code: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "GPIOZERO_PIN_FACTORY": "mock"}
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _run_importtime(code: str, cerrojo: str) -> subprocess.CompletedProcess:
    # `cerrojo` explícito y no heredado: este censo lo pide un fixture de ámbito
    # MÓDULO, que se construye ANTES que el autouse por-test que aísla el cerrojo
    # de pines. Sin esto el subproceso cae al cerrojo DERIVADO de dev
    # (`EdgeSettings.gpio_lock_file`), que es el mismo archivo para todo gabinete
    # `gw-dev-0001` de esta máquina: arrancaría igual, pero el censo dependería
    # de que ningún otro test del mismo id lo esté sosteniendo en ese instante.
    env = {
        **os.environ,
        "GPIOZERO_PIN_FACTORY": "mock",
        "TAKAB_EDGE_GPIO_LOCK_PATH": cerrojo,
    }
    return subprocess.run(
        [sys.executable, "-X", "importtime", "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


class _Censo:
    """Lo que el proceso mínimo CARGÓ, y por qué cadena de imports llegó.

    Dos fuentes, y cada una responde lo que la otra no puede:

    * **`sys.modules` del propio subproceso (stdout)** = el veredicto. Es lo que
      de verdad quedó cargado.
    * **`-X importtime` (stderr)** = la cadena. Imprime en POST-orden (cada
      módulo tras sus hijos) y codifica la profundidad en la sangría del nombre,
      así que se reconstruye quién trajo a quién.

    Por qué no basta `importtime` solo: TAMBIÉN registra los imports que
    FRACASAN. `gpiozero` intenta `pigpio`, `spidev`, `importlib_metadata` e
    `importlib_resources` dentro de `try/except` y ninguno está instalado; un
    veredicto leído de ahí acusaría de dependencias a paquetes que el proceso no
    tiene. Medido al escribir esto: 4 falsos positivos de golpe.
    """

    def __init__(self, stdout: str, stderr: str) -> None:
        self.cargados: list[str] = sorted(stdout.split("MODULOS:")[1].split())
        self.entradas: list[tuple[int, str, int]] = []  # (profundidad, nombre, acumulado_us)
        for linea in stderr.splitlines():
            m = _RE_IMPORTTIME.match(linea)
            if m is None:
                continue  # cabecera, o cualquier otra cosa que el proceso imprima
            sangria, nombre = m.group(3), m.group(4)
            self.entradas.append(((len(sangria) - 1) // 2, nombre, int(m.group(2))))

    @property
    def modulos(self) -> list[str]:
        return self.cargados

    def raices(self) -> set[str]:
        """Nombres de primer nivel REALMENTE cargados (`pydantic.main` → `pydantic`)."""
        return {nombre.split(".")[0] for nombre in self.cargados}

    def cadena(self, objetivo: str) -> str:
        """`a → b → objetivo`: quién importó a quién hasta llegar a `objetivo`.

        En post-orden, el padre de una entrada es la PRIMERA entrada posterior
        con menos profundidad.

        `objetivo` es un nombre de PRIMER NIVEL; si no aparece tal cual (el
        paquete pudo entrar por un submódulo), se usa la primera entrada cuya
        raíz coincida, que es igual de buena para señalar por dónde llegó.
        """
        indices = [i for i, (_, n, _) in enumerate(self.entradas) if n == objetivo] or [
            i for i, (_, n, _) in enumerate(self.entradas) if n.split(".")[0] == objetivo
        ]
        if not indices:
            return objetivo
        i = indices[0]
        profundidad, _, _ = self.entradas[i]
        cadena = [objetivo]
        for j in range(i + 1, len(self.entradas)):
            prof_j, nombre_j, _ = self.entradas[j]
            if prof_j < profundidad:
                cadena.append(nombre_j)
                profundidad = prof_j
                if profundidad == 0:
                    break
        return " → ".join(reversed(cadena))

    def acumulado_ms(self) -> float:
        """Coste del import más caro de primer nivel, en ms (informativo)."""
        de_raiz = [acum for prof, _, acum in self.entradas if prof == 0]
        return max(de_raiz, default=0) / 1000.0


#: El proceso REAL: importa el entry point, arranca el controlador (que es donde
#: se instancia la pin factory y con ella gpiozero) y para. Medir sólo el import
#: dejaría fuera precisamente al driver de pines.
_ARRANQUE_COMPLETO = (
    "import sys;"
    "from takab_edge.config import load_settings;"
    "from takab_edge.gpio.__main__ import run_gpio_process;"
    "c = run_gpio_process(load_settings(), block=False);"
    "c.stop();"
    "sys.stdout.write('MODULOS:' + ' '.join(sorted(sys.modules)))"
)


@pytest.fixture(scope="module")
def censo_del_proceso_gpio(tmp_path_factory: pytest.TempPathFactory) -> _Censo:
    cerrojo = tmp_path_factory.mktemp("censo-gpio") / "gpio.lock"
    resultado = _run_importtime(_ARRANQUE_COMPLETO, str(cerrojo))
    assert resultado.returncode == 0, resultado.stderr
    censo = _Censo(resultado.stdout, resultado.stderr)
    assert len(censo.modulos) > 100 and len(censo.entradas) > 100, (
        "el censo salió vacío o ridículo: no se está leyendo bien el proceso "
        f"({len(censo.modulos)} módulos cargados, {len(censo.entradas)} líneas de "
        "`-X importtime`)"
    )
    return censo


def test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada(
    censo_del_proceso_gpio: _Censo,
) -> None:
    """[D1.3] EL INVARIANTE: stdlib + este repo + lo explícitamente permitido.

    Fail-closed. La blacklist anterior (cinco nombres) dejaba pasar todo lo que
    nadie hubiera imaginado — y lo que viene a continuación en T-2.70.a es
    exactamente eso: una librería de IPC que nadie enumeró.
    """
    censo = censo_del_proceso_gpio
    intrusos = _dependencias_no_autorizadas(censo.raices())
    detalle = "\n".join(f"  · {raiz}: {censo.cadena(raiz)}" for raiz in intrusos)
    assert not intrusos, (
        "el proceso del camino de vida cargó dependencias de terceros que nadie "
        f"autorizó ({len(intrusos)}), y por esta cadena de imports:\n{detalle}\n"
        "Este es el proceso que toca la sirena, el gas y los retenedores de puerta "
        "(regla de oro 4). Si la dependencia es deliberada, decláralas en "
        "_EXTERNOS_PERMITIDOS con la razón; si no, sácala del grafo de "
        "`takab_edge.gpio` (los módulos pesados se importan DENTRO de la función "
        "que los usa, no en la cabecera).\n"
        f"Censo de esta corrida: {len(censo.modulos)} módulos, "
        f"{censo.acumulado_ms():.0f} ms de import."
    )


def test_la_allowlist_no_esta_podrida(censo_del_proceso_gpio: _Censo) -> None:
    """NO-VACUIDAD de la guarda de arriba: si la allowlist creciera con nombres
    que ya nadie carga, quedaría autorizando de más sin que nada lo dijera —
    y un día alguien reintroduce ese paquete y la guarda no lo ve.

    Excepción DECLARADA: `lgpio` sólo se carga con `dev_mode=False` (el Pi real),
    y la suite corre con la MockFactory. Es la única entrada que puede no estar.
    """
    raices = censo_del_proceso_gpio.raices()
    sin_usar = sorted(set(_EXTERNOS_PERMITIDOS) - raices - {"lgpio"})
    assert not sin_usar, (
        f"la allowlist autoriza paquetes que el proceso ya no carga: {sin_usar}. "
        "Quítalos: una autorización sin uso es un agujero abierto en silencio."
    )


def test_la_allowlist_no_tiene_comodines(censo_del_proceso_gpio: _Censo) -> None:
    """NO-VACUIDAD de la forma del filtro: una extensión C de terceros NO pasa.

    La guarda llevaba `and not raiz.startswith("_")`, que no es una propiedad de
    la stdlib sino una puerta abierta: `_cffi_backend` (la extensión de cffi,
    que arrastran `cryptography` y buena parte del stack de MQTT/TLS) es un
    módulo de PRIMER NIVEL con guion bajo, y entraba sin que nadie lo
    autorizara. Aquí se mide con raíces de mentira, porque el veredicto tiene
    que ser el mismo el día que ese paquete aparezca de verdad.

    Y la otra mitad: lo que el filtro sí debe dejar pasar —el `__main__` de la
    propia medición, los dos `.pth` del venv y el `_sysconfigdata_` de la
    plataforma— no puede convertirse en rojo, o la guarda sería un freno de mano
    y alguien la desactivaría entera.
    """
    intrusos = _dependencias_no_autorizadas({"_cffi_backend", "os", "takab_edge", "gpiozero"})
    assert intrusos == ["_cffi_backend"], (
        "el filtro deja pasar módulos de primer nivel con guion bajo: así es "
        "como se distribuye una extensión C de terceros"
    )

    benignos = {"__main__", "_virtualenv", "_distutils_hack", "_sysconfigdata__linux_aarch64-gnu"}
    assert _dependencias_no_autorizadas(benignos) == []
    # …y lo declarado se declara de verdad: nada de la lista es un comodín.
    assert _dependencias_no_autorizadas(censo_del_proceso_gpio.raices()) == []


def test_gpio_process_does_not_import_heavy_deps():
    # La blacklist histórica se conserva porque NOMBRA a los villanos concretos
    # (ObsPy/NumPy/SciPy son lo que puede tardar o colgar en el arranque del
    # camino de vida) y porque mide por otra vía: `sys.modules` del proceso real,
    # sin parsear nada. La guarda que de verdad cierra el hueco es la allowlist.
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
