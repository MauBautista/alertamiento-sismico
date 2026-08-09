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

[auditoría adversarial D1, 2026-08-08 · punto 7] EL CENSO SÓLO MIRABA A DEV
---------------------------------------------------------------------------
La allowlist es fail-closed, sí, pero **censaba un único montaje: el de DEV**
(`dev_mode=True` ⇒ `ensure_dev_pin_factory`). Una dependencia de terceros
importada en la rama de **producción** (`dev_mode=False` ⇒
`ensure_prod_pin_factory`) era literalmente invisible para la guarda — y
producción es el proceso que corre en el Pi, el que sostiene el reflejo
SASMEX→sirena cuyo presupuesto de arranque es la razón de ser de todo esto.

Ahora el censo son **TRES montajes**, y el veredicto se saca de la UNIÓN:

1. ``dev`` — `dev_mode=True`. Es lo que ven `make edge`, `demo/gabinete.py` y
   la suite entera.
2. ``producción`` — `dev_mode=False`, o sea la rama que ejecutan las unidades
   systemd del gabinete. Arranque COMPLETO: cerrojo de pines, rama de
   producción de `_arrancar_hardware`, cinco relés, tres botones y la puerta de
   servicio. La pin factory sigue siendo la MockFactory por
   `GPIOZERO_PIN_FACTORY`, así que `ensure_prod_pin_factory` sale por su primera
   guarda (la del override) — de ahí el tercer montaje.
3. ``backend-producción`` — `ensure_prod_pin_factory()` **sin** override, que es
   como arranca de verdad en el Pi: factory `None` ⇒ intento REAL de
   `from gpiozero.pins.lgpio import LGPIOFactory` ⇒ `LGPIOFactory()`. Es el
   único montaje que puede alcanzar el backend de producción.

**LO QUE ESTA MÁQUINA NO PUEDE MEDIR, dicho con todas las letras:** `lgpio` es
un extra de hardware (`uv sync --extra hardware`) y en un x86 de desarrollo o en
un runner de CI **no está instalado**, así que el montaje 3 muere en el import y
el censo NO cubre ni el grafo de `gpiozero.pins.lgpio` ni el de `lgpio` ni lo
que el constructor de `LGPIOFactory` importe por su cuenta. Eso no se disimula:
`test_el_censo_cubre_el_montaje_de_produccion` **ancla el veredicto** del
montaje 3, de modo que el día que la máquina sí tenga `lgpio` la cobertura sube
sola, y una caída silenciosa a otra rama (p.ej. `OK:MockFactory`, que
significaría que el override se coló) pone el build en rojo en vez de fingir.

El montaje 3 **no construye ningún `DigitalOutputDevice`**: como mucho abre un
handle del gpiochip y no reclama ninguna línea, así que ni siquiera corriendo en
un Pi movería la válvula de gas o los retenedores.
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
    # Los inyecta `site` en el arranque del intérprete, antes de la primera línea
    # de código nuestro: son el gancho de personalización de CPython, no algo que
    # `takab_edge.gpio` importe. Misma clase que los dos de arriba, y por eso van
    # aquí y no en `_EXTERNOS_PERMITIDOS` (autorizar es para lo que SÍ elegimos).
    # No están en este árbol y por eso no aparecían: los inyecta el runner de
    # GitHub, así que estos tres tests pasaban en local y sólo se ponían rojos en
    # CI — que es donde nadie los estaba mirando, porque esta rama nunca tuvo PR.
    "sitecustomize": "gancho de `site` del intérprete que hospeda la corrida",
    "usercustomize": "el gemelo por-usuario de `sitecustomize`, mismo gancho",
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


def _run_importtime(
    code: str,
    cerrojo: str,
    socket: str,
    *,
    dev_mode: bool = True,
    con_mock: bool = True,
) -> subprocess.CompletedProcess:
    # `cerrojo` y `socket` explícitos y no heredados: este censo lo pide un
    # fixture de ámbito MÓDULO, que se construye ANTES que el autouse por-test
    # que aísla ambos. Sin esto el subproceso cae a las rutas DERIVADAS de dev
    # (`EdgeSettings.gpio_lock_file`/`gpio_socket_file`), que son los mismos
    # archivos para todo gabinete `gw-dev-0001` de esta máquina: arrancaría
    # igual, pero el censo dependería de que ningún otro test del mismo id los
    # esté sosteniendo en ese instante. Y con `dev_mode=False` las derivadas son
    # las de PRODUCCIÓN (`/var/lib/takab`, `/run/takab`), que no existen aquí.
    env = {
        **os.environ,
        "TAKAB_EDGE_GPIO_LOCK_PATH": cerrojo,
        "TAKAB_EDGE_GPIO_SOCKET_PATH": socket,
        "TAKAB_EDGE_DEV_MODE": "true" if dev_mode else "false",
    }
    if con_mock:
        env["GPIOZERO_PIN_FACTORY"] = "mock"
    else:
        # El montaje que ejercita el backend REAL: `ensure_prod_pin_factory` sale
        # por su primera guarda si esta variable existe, así que aquí no puede
        # existir — ni siquiera heredada del `GPIOZERO_PIN_FACTORY=mock` con el
        # que se invoca la suite.
        env.pop("GPIOZERO_PIN_FACTORY", None)
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


class _CensoConjunto:
    """La UNIÓN de los montajes censados, y de cuál salió cada cosa.

    El veredicto de la allowlist se saca de aquí y no de un montaje suelto: una
    dependencia que sólo aparece en producción tiene que contar igual que una
    que aparece en dev — es más grave, de hecho, porque producción es la que
    corre en el gabinete.
    """

    def __init__(self, por_montaje: dict[str, _Censo], veredicto_backend: str) -> None:
        self.por_montaje = por_montaje
        #: Hasta dónde llegó el montaje 3 (`ensure_prod_pin_factory` sin
        #: override) EN ESTA MÁQUINA. Es la declaración de cobertura, y va
        #: anclada por test para que no pueda degradarse en silencio.
        self.veredicto_backend = veredicto_backend

    @property
    def modulos(self) -> list[str]:
        return sorted({m for censo in self.por_montaje.values() for m in censo.modulos})

    @property
    def entradas(self) -> list[tuple[int, str, int]]:
        return [e for censo in self.por_montaje.values() for e in censo.entradas]

    def raices(self) -> set[str]:
        return {raiz for censo in self.por_montaje.values() for raiz in censo.raices()}

    def cadena(self, objetivo: str) -> str:
        """`[montaje] a → b → objetivo`, por cada montaje donde entró.

        Decir POR DÓNDE entró incluye decir EN QUÉ MONTAJE: una dependencia que
        sólo aparece con `dev_mode=False` es un hallazgo distinto —y peor— que
        una que aparece en los tres.
        """
        partes = [
            f"[{etiqueta}] {censo.cadena(objetivo)}"
            for etiqueta, censo in self.por_montaje.items()
            if objetivo in censo.raices()
        ]
        return " · ".join(partes) or objetivo

    def acumulado_ms(self) -> float:
        return max(censo.acumulado_ms() for censo in self.por_montaje.values())


#: Montajes 1 y 2 — el proceso REAL: importa el entry point, arranca el
#: controlador (que es donde se instancia la pin factory y con ella gpiozero) y
#: para. Medir sólo el import dejaría fuera precisamente al driver de pines. El
#: `DEVMODE:` no es adorno: es la prueba de que el subproceso tomó la rama que
#: se le pidió y no la de siempre (ver `test_el_censo_cubre_el_montaje_...`).
_ARRANQUE_COMPLETO = (
    "import sys;"
    "from takab_edge.config import load_settings;"
    "from takab_edge.gpio.__main__ import run_gpio_process;"
    "cfg = load_settings();"
    "c = run_gpio_process(cfg, block=False);"
    "c.stop();"
    "sys.stdout.write('DEVMODE:' + repr(cfg.dev_mode) + '\\n');"
    "sys.stdout.write('MODULOS:' + ' '.join(sorted(sys.modules)))"
)

#: Montaje 3 — la selección de backend de PRODUCCIÓN, sin override de env, que
#: es como arranca en el Pi (factory `None` ⇒ lgpio EXPLÍCITO o tronar).
#:
#: Llama a la función y a nada más: **no construye ningún `DigitalOutputDevice`**,
#: así que ni en un Pi reclamaría una línea de GPIO. Lo que interesa aquí son los
#: imports, y el `except` es obligatorio porque en una máquina sin el extra de
#: hardware esto TIENE que fallar — y el censo de `sys.modules` sigue valiendo
#: igual, porque lo que se importó antes de tronar ya está cargado.
_ARRANQUE_BACKEND_PRODUCCION = """
import sys
from gpiozero import Device
from takab_edge.gpio import ensure_prod_pin_factory

try:
    ensure_prod_pin_factory()
    veredicto = "OK:" + type(Device.pin_factory).__name__
except BaseException as exc:
    causa = type(exc.__cause__).__name__ if exc.__cause__ is not None else "-"
    veredicto = "EXC:" + type(exc).__name__ + ":" + causa
sys.stdout.write("BACKEND:" + veredicto + "\\n")
sys.stdout.write("MODULOS:" + " ".join(sorted(sys.modules)))
"""

#: Los dos únicos desenlaces DECLARADOS del montaje 3, con lo que cada uno deja
#: dentro y fuera del censo. Cualquier otro (`OK:MockFactory`, p.ej.) significa
#: que el censo se cayó a otra rama y estaría fingiendo cobertura de producción.
_DESENLACES_DEL_BACKEND = {
    "OK:LGPIOFactory": (
        "la máquina TIENE el extra de hardware y un gpiochip usable: el censo "
        "cubre `gpiozero.pins.lgpio`, `lgpio` y el constructor de la factory"
    ),
    "EXC:RuntimeError:ModuleNotFoundError": (
        "`lgpio` NO está instalado aquí (x86 de dev / runner de CI sin `uv sync "
        "--extra hardware`): el censo cubre la rama de producción HASTA el "
        "import, y NO cubre el grafo de `gpiozero.pins.lgpio` ni el de `lgpio`"
    ),
    "EXC:RuntimeError:-": (
        "`lgpio` importó pero la factory no pudo instanciarse (sin /dev/gpiochip "
        "utilizable): el censo SÍ cubre el grafo de imports del backend"
    ),
}

_RE_MARCADOR = re.compile(r"^(DEVMODE|BACKEND):(.+)$", re.MULTILINE)


def _marcador(salida: str, clave: str) -> str:
    for m in _RE_MARCADOR.finditer(salida):
        if m.group(1) == clave:
            return m.group(2).strip()
    raise AssertionError(f"el subproceso no imprimió el marcador {clave}: {salida[:400]!r}")


@pytest.fixture(scope="module")
def censo_del_proceso_gpio(tmp_path_factory: pytest.TempPathFactory) -> _CensoConjunto:
    raiz = tmp_path_factory.mktemp("censo-gpio")  # corto: AF_UNIX corta en ~108 bytes
    por_montaje: dict[str, _Censo] = {}

    for etiqueta, dev_mode in (("dev", True), ("producción", False)):
        breve = "d" if dev_mode else "p"
        resultado = _run_importtime(
            _ARRANQUE_COMPLETO,
            cerrojo=str(raiz / f"{breve}.lock"),
            socket=str(raiz / f"{breve}.sock"),
            dev_mode=dev_mode,
        )
        assert resultado.returncode == 0, f"[{etiqueta}] {resultado.stderr}"
        assert _marcador(resultado.stdout, "DEVMODE") == repr(dev_mode), (
            f"[{etiqueta}] el subproceso NO arrancó en el montaje pedido: "
            f"dev_mode={_marcador(resultado.stdout, 'DEVMODE')}. Un censo que "
            "cree medir producción y mide dev es peor que no medirla."
        )
        por_montaje[etiqueta] = _Censo(resultado.stdout, resultado.stderr)

    backend = _run_importtime(
        _ARRANQUE_BACKEND_PRODUCCION,
        cerrojo=str(raiz / "b.lock"),
        socket=str(raiz / "b.sock"),
        dev_mode=False,
        con_mock=False,
    )
    assert backend.returncode == 0, f"[backend-producción] {backend.stderr}"
    por_montaje["backend-producción"] = _Censo(backend.stdout, backend.stderr)

    for etiqueta, censo in por_montaje.items():
        assert len(censo.modulos) > 100 and len(censo.entradas) > 100, (
            f"el censo de [{etiqueta}] salió vacío o ridículo: no se está "
            f"leyendo bien el proceso ({len(censo.modulos)} módulos cargados, "
            f"{len(censo.entradas)} líneas de `-X importtime`)"
        )
    return _CensoConjunto(por_montaje, _marcador(backend.stdout, "BACKEND"))


def test_el_censo_cubre_el_montaje_de_produccion(censo_del_proceso_gpio: _CensoConjunto) -> None:
    """[auditoría D1 · punto 7] La guarda tiene que mirar a la rama del GABINETE.

    La allowlist de D1.3 es fail-closed pero censaba UN montaje: el de dev. Una
    dependencia de terceros importada bajo `dev_mode=False` no la veía nadie — y
    ésa es la rama que corre en el Pi sosteniendo el reflejo SASMEX→sirena.

    Este test es el que impide que la cobertura se caiga en silencio: no basta
    con que existan tres censos, hay que probar que cada uno FUE DONDE DIJO.
    """
    montajes = censo_del_proceso_gpio.por_montaje
    assert set(montajes) == {"dev", "producción", "backend-producción"}, (
        f"faltan montajes en el censo: {sorted(montajes)}. Con menos de tres, "
        "la allowlist vuelve a ser una guarda que sólo mira a dev."
    )
    # Que el montaje de producción NO sea el de dev con otro nombre: si los dos
    # cargaran exactamente lo mismo por accidente el censo seguiría siendo
    # correcto, pero si `dev_mode` no hubiera llegado, sería una mentira. Eso lo
    # ancla el marcador DEVMODE del fixture; aquí se ancla lo que se deriva de
    # él y es específico de producción.
    assert censo_del_proceso_gpio.veredicto_backend in _DESENLACES_DEL_BACKEND, (
        "el montaje que ejercita `ensure_prod_pin_factory` SIN override terminó "
        f"en un desenlace no declarado: {censo_del_proceso_gpio.veredicto_backend!r}. "
        f"Los declarados son {sorted(_DESENLACES_DEL_BACKEND)}. En particular "
        "`OK:NoneType` es lo que deja la PRIMERA guarda de la función (la del "
        "override): significaría que GPIOZERO_PIN_FACTORY se coló en el entorno "
        "del subproceso y que el censo NO está tocando el backend de producción "
        "— estaría fingiendo cobertura del proceso que gobierna la sirena y el "
        "gas. Medido: quitar el `env.pop` del arnés produce exactamente eso."
    )
    # …y la mitad honesta: lo que ESTA máquina no alcanza, escrito y comprobable.
    if censo_del_proceso_gpio.veredicto_backend != "OK:LGPIOFactory":
        assert "lgpio" not in censo_del_proceso_gpio.raices(), (
            "el veredicto del backend dice que no se llegó a instanciar "
            f"LGPIOFactory ({censo_del_proceso_gpio.veredicto_backend}) pero "
            "`lgpio` SÍ está cargado: uno de los dos está mintiendo"
        )


def test_el_proceso_minimo_no_carga_ninguna_dependencia_no_autorizada(
    censo_del_proceso_gpio: _CensoConjunto,
) -> None:
    """[D1.3] EL INVARIANTE: stdlib + este repo + lo explícitamente permitido.

    Fail-closed. La blacklist anterior (cinco nombres) dejaba pasar todo lo que
    nadie hubiera imaginado — y lo que viene a continuación en T-2.70.a es
    exactamente eso: una librería de IPC que nadie enumeró.

    [auditoría D1] Y se mide sobre los TRES montajes, no sólo el de dev: la
    cadena que acompaña a cada intruso dice también en cuál entró, porque «sólo
    en producción» es el hallazgo grave.
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
        f"Censo de esta corrida: {len(censo.modulos)} módulos en "
        f"{sorted(censo.por_montaje)}, {censo.acumulado_ms():.0f} ms de import."
    )


def test_la_allowlist_no_esta_podrida(censo_del_proceso_gpio: _CensoConjunto) -> None:
    """NO-VACUIDAD de la guarda de arriba: si la allowlist creciera con nombres
    que ya nadie carga, quedaría autorizando de más sin que nada lo dijera —
    y un día alguien reintroduce ese paquete y la guarda no lo ve.

    Excepción DECLARADA y **DERIVADA, no escrita a mano**: `lgpio` sólo entra por
    `ensure_prod_pin_factory` sin override, y en una máquina sin el extra de
    hardware ese montaje muere en el import. La excepción vale exactamente
    mientras el censo del backend diga que no llegó — el día que la máquina tenga
    `lgpio`, la entrada deja de estar exenta sola. Antes era un `{"lgpio"}` fijo,
    que es una exención que nadie vuelve a mirar.
    """
    raices = censo_del_proceso_gpio.raices()
    fuera_de_alcance = (
        set() if censo_del_proceso_gpio.veredicto_backend == "OK:LGPIOFactory" else {"lgpio"}
    )
    sin_usar = sorted(set(_EXTERNOS_PERMITIDOS) - raices - fuera_de_alcance)
    assert not sin_usar, (
        f"la allowlist autoriza paquetes que el proceso ya no carga: {sin_usar}. "
        "Quítalos: una autorización sin uso es un agujero abierto en silencio. "
        f"(Fuera de alcance en esta máquina: {sorted(fuera_de_alcance) or 'nada'} — "
        f"backend: {censo_del_proceso_gpio.veredicto_backend}.)"
    )


def test_la_allowlist_no_tiene_comodines(censo_del_proceso_gpio: _CensoConjunto) -> None:
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

    benignos = {
        "__main__",
        "_virtualenv",
        "_distutils_hack",
        "_sysconfigdata__linux_aarch64-gnu",
        # Los pone el intérprete que hospeda la corrida (el runner de CI trae uno
        # y esta máquina no): sin ellos aquí, la guarda es verde en el portátil y
        # roja en CI, que es la peor de las dos combinaciones.
        "sitecustomize",
        "usercustomize",
    }
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
