"""`deploy.sh` EJECUTADO de verdad contra un gabinete de mentira.

`test_deploy_artifacts.py` lee el script como TEXTO: comprueba que las líneas
están y en qué orden aparecen. Eso ancla la intención, pero no prueba el
COMPORTAMIENTO — y las dos cosas que este script tenía rotas eran de
comportamiento:

* **el gate era estructuralmente ciego** (`import lgpio, awsiot`: dos paquetes
  de terceros que viven en el `.venv`, y el `.venv` está EXCLUIDO del rsync, así
  que el gate no podía fallar por culpa del código desplegado); y
* **el gate corría después de destruir el estado anterior**, mientras el mensaje
  de aborto prometía que «el gabinete sigue con el código anterior».

Un test de texto no distingue «el gate aborta» de «el gate aborta Y el árbol
vivo quedó intacto». Este archivo sí: monta un `/opt/takab` falso en un
`tmp_path`, pone `ssh`/`rsync`/`uv`/`sudo`/`systemctl` falsos en el PATH, corre
el script de verdad y MIRA EL DISCO.

Cómo funciona el sandbox
------------------------
* `ssh` falso: recibe `(host, "VAR=… bash -s")` y hace `eval` de ese comando en
  esta misma máquina, con el heredoc entrando por stdin. O sea que el "bloque
  remoto" se ejecuta de verdad, sólo que aquí.
* `TAKAB_REMOTE_ROOT` reapunta `/opt/takab` al `tmp_path`. Es el único seam que
  el script tiene para las pruebas; en producción nadie lo exporta.
* `python3` falso: delega en el real (así `compileall` compila DE VERDAD el
  árbol del repo) salvo que el test pida el fallo.
* `.venv/bin/python` falso: lo crea el `uv` falso y decide, por variable de
  entorno, si fallan las dependencias de terceros o el código desplegado. Esa
  distinción es justo la que el gate viejo no podía hacer.
* `sudo` NO ejecuta: registra. Así ningún test escribe en `/etc/systemd/system`.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import shutil
import signal
import subprocess
import textwrap
import time

import pytest

_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_DEPLOY = _RAIZ / "deploy" / "edge" / "deploy.sh"

#: Marca que se siembra en el árbol vivo antes de desplegar. Si sigue ahí, el
#: árbol vivo NO se tocó; si desapareció, el `rsync --delete` ya pasó por encima.
_CENTINELA = "CODIGO_ANTERIOR.txt"


def _console_scripts() -> list[str]:
    """Los console scripts DECLARADOS hoy en `edge/pyproject.toml`."""
    import tomllib

    datos = tomllib.loads((_RAIZ / "edge" / "pyproject.toml").read_text(encoding="utf-8"))
    return list(datos["project"]["scripts"])


def _escribir_ejecutable(ruta: pathlib.Path, cuerpo: str) -> None:
    ruta.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(cuerpo))
    ruta.chmod(0o755)


@pytest.fixture
def gabinete(tmp_path: pathlib.Path):
    """Un `/opt/takab` de mentira + los binarios falsos que el script invoca."""
    raiz = tmp_path / "opt-takab"
    binarios = tmp_path / "bin"
    binarios.mkdir()
    bitacora = tmp_path / "bitacora.txt"
    bitacora.write_text("")

    rsync_real = shutil.which("rsync")
    python_real = shutil.which("python3")

    # El intérprete falso del venv. Lo usan DOS caminos del script: el pre-vuelo
    # (`compileall`, que aquí delega en el python real y compila el árbol de
    # verdad) y el gate (`-c '<imports>'`). Las tres variables de entorno
    # separan los tres modos de fallo que el script debe distinguir.
    py_venv = f"""
        case "$1 $2" in
          "-m compileall")
            [ -n "${{FALLA_COMPILEALL:-}}" ] && {{ echo "SyntaxError simulado" >&2; exit 1; }}
            exec "{python_real}" "$@" ;;
        esac
        case "$2" in
          *lgpio*)
            [ -n "${{FALLA_DEPS:-}}" ] && {{ echo "No module named lgpio" >&2; exit 1; }} ;;
          *takab_edge*)
            [ -n "${{FALLA_CODIGO:-}}" ] && {{ echo "ImportError: takab_edge" >&2; exit 1; }} ;;
        esac
        exit 0
    """

    # Árbol vivo PREEXISTENTE con su centinela y su venv: simula el gabinete ya
    # desplegado, que es el caso real. Que el venv exista importa: el pre-vuelo
    # compila con SU intérprete (3.12 en el Pi) y no con el del sistema (3.13).
    vivo = raiz / "edge"
    (vivo / ".venv" / "bin").mkdir(parents=True)
    (vivo / _CENTINELA).write_text("soy el despliegue anterior\n")
    _escribir_ejecutable(vivo / ".venv" / "bin" / "python", py_venv)

    # ssh falso: ejecuta aquí el comando remoto, con el heredoc por stdin.
    _escribir_ejecutable(
        binarios / "ssh",
        f"""
        echo "ssh $*" >> "{bitacora}"
        shift            # descarta el host
        eval "$@"
        """,
    )

    # rsync falso: quita el prefijo `host:` de los argumentos y delega en el real.
    _escribir_ejecutable(
        binarios / "rsync",
        f"""
        echo "rsync $*" >> "{bitacora}"
        args=()
        for a in "$@"; do
          args+=( "${{a/#gabinete-falso:/}}" )
        done
        exec "{rsync_real}" "${{args[@]}}"
        """,
    )

    # python3 falso (respaldo, si aún no hubiera venv): el real salvo inyección.
    _escribir_ejecutable(binarios / "python3", py_venv)

    # Plantilla del intérprete falso, para el gabinete VIRGEN: ahí no hay venv
    # todavía y es `uv` quien lo crea. Sin esto, el escenario de primer
    # despliegue fallaría por un motivo que en el Pi no existe.
    plantilla_py = binarios / "python-de-venv.plantilla"
    _escribir_ejecutable(plantilla_py, py_venv)

    # uv falso: materializa los console scripts que el gate exige. NO reescribe
    # .venv/bin/python cuando ya viene del gabinete simulado.
    # [T-2.70.a·D2/P2] Los console scripts salen de `pyproject.toml`, no de una
    # lista escrita aquí: el gate del despliegue los exige TODOS, y una lista a
    # mano deja el sandbox una versión por detrás del proyecto — el primer script
    # nuevo hace fallar diez tests por un motivo que en el Pi no existe.
    materializar = "\n        ".join(
        f": > .venv/bin/{nombre} && chmod +x .venv/bin/{nombre}"
        for nombre in sorted(_console_scripts())
    )
    _escribir_ejecutable(
        binarios / "uv",
        f"""
        echo "uv $*" >> "{bitacora}"
        mkdir -p .venv/bin
        [ -x .venv/bin/python ] || cp "{plantilla_py}" .venv/bin/python
        {materializar}
        """,
    )

    # sudo falso: registra y NO ejecuta… salvo `systemctl`, porque el reinicio
    # del gabinete va por `sudo systemctl restart` y sin delegarlo el arranque
    # simulado nunca ocurriría (y con él, nadie reclamaría los pines). `install`
    # y `chown` siguen siendo puro registro: ningún test escribe en
    # /etc/systemd/system.
    _escribir_ejecutable(
        binarios / "sudo",
        f"""
        echo "sudo $*" >> "{bitacora}"
        [ "$1" = systemctl ] && exec "$@"
        exit 0
        """,
    )

    # El cerrojo de propiedad de pines del gabinete de mentira (T-2.70.a·D1.1).
    cerrojo = tmp_path / "gpio.lock"

    # systemctl falso. Su `restart` RECLAMA LOS PINES, que es lo que hace de
    # verdad el proceso que arranca: `GpioController._on_start` toma un flock
    # EXCLUSIVO sobre el cerrojo y escribe su PID y su unidad. Sin modelar eso,
    # la verificación de propiedad no se podría probar en absoluto.
    #
    #   NO_RECLAMA_PINES=1 → el servicio arranca pero NADIE toma el GPIO. Es el
    #     escenario que `systemctl is-active` no puede ver: unidad viva, sirena
    #     sin dueño.
    #   UNIDAD_DUENA=... → los pines los reclama OTRA unidad (mañana: takab-gpio).
    _escribir_ejecutable(
        binarios / "systemctl",
        f"""
        echo "systemctl $*" >> "{bitacora}"
        if [ "$1" = restart ] && [ -z "${{NO_RECLAMA_PINES:-}}" ]; then
          # `exec` y no `flock -n <archivo> sleep 120`: util-linux hace fork, así
          # que ahí `$!` era el PID de FLOCK y el que se queda con el descriptor
          # (y con el cerrojo) es el `sleep` hijo. El teardown mataba al padre y
          # dejaba vivo al `sleep` dos minutos más, sosteniendo el cerrojo. Con
          # el subshell + `exec`, `$!` ES el proceso que tiene el fd 9 abierto:
          # el registro nombra al dueño de verdad y matarlo lo suelta.
          ( flock -n 9 || exit 1; exec sleep 120 ) 9>"{cerrojo}" </dev/null >/dev/null 2>&1 &
          sleep 0.3
          printf 'pid=%s\\nunit=%s\\n' "$!" "${{UNIDAD_DUENA:-$2}}" > "{cerrojo}"
        fi
        [ "$1" = is-active ] && echo active
        exit 0
        """,
    )
    # journalctl falso: el paso INFORMATIVO del final. `FALLA_JOURNALCTL` simula
    # el journal recortado/sin permisos que en el Pi devuelve != 0.
    _escribir_ejecutable(
        binarios / "journalctl",
        f"""
        echo "journalctl $*" >> "{bitacora}"
        [ -n "${{FALLA_JOURNALCTL:-}}" ] && {{ echo "Failed to open journal" >&2; exit 1; }}
        exit 0
        """,
    )

    class Gabinete:
        def __init__(self) -> None:
            self.raiz = raiz
            self.vivo = vivo
            self.previo = raiz / "edge.prev"
            self.bitacora = bitacora
            self.cerrojo = cerrojo

        def desplegar(self, **entorno: str) -> subprocess.CompletedProcess[str]:
            env = dict(os.environ)
            # HOME apunta al sandbox A PROPÓSITO: el bloque remoto hace
            # `export PATH="$HOME/.local/bin:$PATH"` (en el Pi, uv vive ahí), y
            # con el HOME real eso colaría el `uv` DE VERDAD por delante del
            # falso — que es justo lo que pasó al escribir este test: el uv real
            # se puso a instalar numpy dentro del /opt/takab de mentira.
            hogar = tmp_path / "hogar"
            (hogar / ".local" / "bin").mkdir(parents=True, exist_ok=True)
            env["HOME"] = str(hogar)
            env["PATH"] = f"{binarios}:{env['PATH']}"
            env["TAKAB_REMOTE_ROOT"] = str(raiz)
            # Mismo seam que la raíz remota: en producción nadie lo exporta y el
            # script cae a /var/lib/takab/gpio.lock, que es el que usan las DOS
            # unidades (WorkingDirectory=/var/lib/takab, ReadWritePaths=).
            env["TAKAB_EDGE_GPIO_LOCK_PATH"] = str(cerrojo)
            env.update(entorno)
            return subprocess.run(
                ["bash", str(_DEPLOY), "gabinete-falso"],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(_RAIZ),
                timeout=300,
            )

        def gabinete_virgen(self) -> None:
            """Borra el árbol vivo: PRIMER despliegue de este gabinete.

            No es un caso de laboratorio — es el estado de todo gabinete nuevo, y
            el de cualquiera al que le hayan borrado `/opt/takab/edge`.
            """
            shutil.rmtree(self.vivo)

        def registro(self) -> str:
            return bitacora.read_text()

        def centinela_intacto(self) -> bool:
            return (self.vivo / _CENTINELA).exists()

        def codigo_nuevo_en_el_arbol_vivo(self) -> bool:
            return (self.vivo / "takab_edge" / "supervisor.py").exists()

        def dueno_de_los_pines(self) -> dict[str, str]:
            """`{'pid': ..., 'unit': ...}` del registro del cerrojo (vacío si no hay)."""
            if not self.cerrojo.exists():
                return {}
            return dict(
                linea.split("=", 1)
                for linea in self.cerrojo.read_text().splitlines()
                if "=" in linea
            )

    gabinete = Gabinete()
    try:
        yield gabinete
    finally:
        # El proceso que sostiene el flock es un `sleep 120` de verdad: matarlo o
        # la suite se queda con procesos colgados DOS MINUTOS, y sosteniendo un
        # cerrojo. Que el PID del registro sea EXACTAMENTE ese proceso lo
        # garantiza el `exec` del systemctl falso (ver arriba): con `flock -n
        # <archivo> sleep 120` este `kill` mataba al padre `flock` y el `sleep`
        # heredero seguía con el descriptor.
        pid = gabinete.dueno_de_los_pines().get("pid", "")
        if pid.isdigit():
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(int(pid), signal.SIGKILL)


# --------------------------------------------------------------- camino feliz


def test_un_despliegue_sano_llega_hasta_el_reinicio(gabinete) -> None:
    """Línea base: sin fallos inyectados el script completa, deja el código
    nuevo en el árbol vivo, escribe FW_VERSION y reinicia."""
    r = gabinete.desplegar()
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"

    assert gabinete.codigo_nuevo_en_el_arbol_vivo(), "el código nuevo debe quedar en el árbol vivo"
    assert not gabinete.centinela_intacto(), "el swap debe barrer el árbol anterior (--delete)"
    assert (gabinete.vivo / "FW_VERSION").read_text().strip(), "FW_VERSION debe quedar escrita"
    assert (gabinete.vivo / ".venv").is_dir(), "el .venv del Pi NO se borra en el swap"
    assert "systemctl restart takab-edge" in gabinete.registro()


def test_el_swap_deja_una_instantanea_para_volver_atras(gabinete) -> None:
    """La reversibilidad que hoy existe: `edge.prev` guarda el fuente anterior.

    No revierte el `.venv` (eso exigiría el despliegue A/B), pero convierte «no
    hay vuelta atrás» en «hay vuelta atrás del fuente» — y es lo que el mensaje
    de aborto ofrece como comando.
    """
    assert gabinete.desplegar().returncode == 0
    assert (gabinete.previo / _CENTINELA).exists(), (
        "la instantánea debe contener el árbol ANTERIOR, no el nuevo"
    )


# ------------------------------------------- B3: abortar sin haber destruido


def test_el_prevuelo_aborta_sin_tocar_el_arbol_vivo(gabinete) -> None:
    """B3, LA PRUEBA DE COMPORTAMIENTO.

    El código nuevo no compila. Antes, el gate corría DESPUÉS del `rsync
    --delete` y el disco ya tenía el código nuevo sin verificar: el mensaje
    «sigue con el código anterior» era falso y el próximo arranque —un corte de
    luz, un `Restart=always`— habría ejecutado ese código solo.

    Ahora el pre-vuelo corre sobre el árbol de ENSAYO. Al abortar, el árbol vivo
    tiene que seguir EXACTAMENTE como estaba: el centinela del despliegue
    anterior sigue ahí y el código nuevo NO llegó.
    """
    r = gabinete.desplegar(FALLA_COMPILEALL="1")
    assert r.returncode != 0, "un pre-vuelo que no compila debe abortar"

    assert gabinete.centinela_intacto(), (
        "EL ÁRBOL VIVO SE DESTRUYÓ pese a abortar: el pre-vuelo llegó tarde"
    )
    assert not gabinete.codigo_nuevo_en_el_arbol_vivo(), (
        "el código nuevo NO verificado no debe estar en el árbol que arranca el gabinete"
    )
    assert "systemctl restart" not in gabinete.registro(), "no se puede reiniciar tras abortar"
    assert "uv sync" not in gabinete.registro(), "ni siquiera se llega a tocar el venv"
    assert "NADA se ha destruido" in r.stderr


# ---------------------------------------- B2: el gate ve el código desplegado


def test_el_gate_falla_por_el_codigo_desplegado_y_no_solo_por_el_venv(gabinete) -> None:
    """B2, LA PRUEBA DE COMPORTAMIENTO.

    `FALLA_CODIGO` hace que `import lgpio, awsiot` SIGA FUNCIONANDO y que sólo
    falle `import takab_edge.supervisor, takab_edge.gpio.__main__`. Con el gate
    viejo este despliegue habría pasado el gate y reiniciado el gabinete con
    código que no arranca — el gate no podía fallar por culpa del código, porque
    sólo miraba dos paquetes que el rsync ni siquiera copia.

    Con el gate de ahora, aborta antes del restart.
    """
    r = gabinete.desplegar(FALLA_CODIGO="1")
    assert r.returncode != 0, (
        "el gate debe abortar cuando el CÓDIGO DESPLEGADO no importa; si esto pasa en verde, "
        "el gate volvió a ser ciego al árbol que despliega"
    )
    assert "systemctl restart" not in gabinete.registro(), "no se reinicia con código roto"
    assert "el CÓDIGO DESPLEGADO no importa" in r.stderr


def test_el_gate_sigue_viendo_el_venv_podado(gabinete) -> None:
    """El fallo histórico (un `uv sync` con un solo extra PODÓ `awsiotsdk` y
    dejó al gabinete offline spooleando) tiene que seguir cazándose."""
    r = gabinete.desplegar(FALLA_DEPS="1")
    assert r.returncode != 0
    assert "systemctl restart" not in gabinete.registro()
    assert "lgpio" in r.stderr


# ------------------------------------------------- B3: el mensaje no miente


def test_tras_el_swap_el_mensaje_de_aborto_dice_la_verdad(gabinete) -> None:
    """Cuando el gate aborta DESPUÉS del swap, el disco ya cambió y el mensaje
    lo tiene que decir. El texto viejo —«El gabinete NO se ha reiniciado y sigue
    con el código anterior»— era falso justo en el escenario más peligroso.
    """
    r = gabinete.desplegar(FALLA_CODIGO="1")

    # La premisa del mensaje, verificada EN EL DISCO y no en el texto:
    assert gabinete.codigo_nuevo_en_el_arbol_vivo(), (
        "premisa: tras el swap el árbol vivo YA tiene el código nuevo sin verificar"
    )

    assert "EL DISCO YA TIENE EL CÓDIGO NUEVO" in r.stderr
    assert "estado seguro" in r.stderr
    assert "sigue con el código anterior" not in r.stderr, (
        "esa era la frase que mentía: tras el swap el disco NO sigue con el código anterior"
    )
    # Y ofrece la vuelta atrás que sí existe, apuntando a una instantánea REAL.
    assert str(gabinete.previo) in r.stderr
    assert (gabinete.previo / _CENTINELA).exists(), (
        "el comando de restauración que imprime debe apuntar a una instantánea que existe"
    )


# ------------------- A3: el primer despliegue no tiene vuelta atrás que ofrecer


def test_el_primer_despliegue_de_un_gabinete_virgen_completa(gabinete) -> None:
    """Premisa del test de abajo, y camino real de todo gabinete nuevo: sin
    `/opt/takab/edge` previo el despliegue tiene que terminar igual de bien.

    Aquí NO se toma instantánea (no hay de qué), y eso es correcto; lo que no era
    correcto es lo que el mensaje de aborto decía en ese caso.
    """
    gabinete.gabinete_virgen()
    r = gabinete.desplegar()

    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert gabinete.codigo_nuevo_en_el_arbol_vivo()
    assert not gabinete.previo.exists(), "sin árbol vivo previo no hay instantánea que tomar"


def test_sin_instantanea_el_aborto_no_ofrece_una_vuelta_atras_inexistente(gabinete) -> None:
    """A3. El mensaje de aborto ofrecía SIEMPRE el comando de restauración desde
    `edge.prev` — pero `edge.prev` sólo se crea `if [ -d "$VIVO" ]`.

    En el primer despliegue de un gabinete (o tras borrar `/opt/takab/edge`) esa
    instantánea NO EXISTE, así que el script mandaba a un operador con el
    gabinete abortado a correr un `rsync` desde un directorio que no está. Es la
    misma familia que la frase «sigue con el código anterior»: el mensaje afirma
    un estado seguro que no se ha comprobado. Un operador que se fía se va del
    sitio creyendo que puede volver atrás.
    """
    gabinete.gabinete_virgen()
    r = gabinete.desplegar(FALLA_CODIGO="1")

    assert r.returncode != 0
    assert not gabinete.previo.exists(), "premisa: en el primer despliegue no hay instantánea"

    # La verdad sobre el disco se sigue diciendo (eso no cambia)...
    assert "EL DISCO YA TIENE EL CÓDIGO NUEVO" in r.stderr
    # ...pero la vuelta atrás que no existe NO se ofrece.
    assert "rsync -a --delete --exclude .venv" not in r.stderr, (
        "ofrece restaurar desde una instantánea que NO se tomó: el comando fallaría "
        "y el operador ya se habría ido creyendo que tiene vuelta atrás"
    )
    assert "NO HAY VUELTA ATRÁS" in r.stderr, (
        "en el primer despliegue el mensaje debe DECIR que no hay código anterior al que volver"
    )


# ---------------- A4: un paso informativo no puede tumbar un despliegue sano


def test_un_journal_ilegible_no_convierte_un_despliegue_bueno_en_fallido(gabinete) -> None:
    """A4. El último paso remoto (`journalctl … | tail -8`) es INFORMATIVO, pero
    corría bajo `set -euo pipefail` siendo el último comando del bloque: su
    código de salida ERA el del despliegue.

    Un journal recortado (`Storage=volatile` tras un reboot), un permiso que
    falta o un fallo del pipe convertían un despliegue YA TERMINADO —unidades
    instaladas, `takab-edge` reiniciado y activo— en «deploy fallido». Éxito
    reportado como fracaso: el operador revierte un gabinete sano, que es
    actuación física sobre gas y puertas por un error de contabilidad.
    """
    r = gabinete.desplegar(FALLA_JOURNALCTL="1")

    assert "systemctl restart takab-edge" in gabinete.registro(), (
        "premisa: el despliegue llegó hasta el reinicio y sólo falló el paso informativo"
    )
    assert r.returncode == 0, (
        f"un journalctl que falla NO puede tumbar el despliegue.\nstdout:\n{r.stdout}"
        f"\nstderr:\n{r.stderr}"
    )
    assert "edge desplegado" in r.stdout


# ------------- D1.5: la verificación medía el proceso EQUIVOCADO


def test_el_despliegue_verifica_quien_ES_DUENO_DE_LOS_PINES(gabinete) -> None:
    """[T-2.70.a·D1.5] LA VERIFICACIÓN, ahora sobre lo que importa.

    Lo que había era `systemctl is-active takab-edge`: mide que UNA UNIDAD
    CONCRETA esté arriba, no que alguien esté sosteniendo el GPIO. El día que
    `takab-edge` deje de tocar los pines —que es literalmente el objetivo de
    T-2.70.a— esa línea seguiría saliendo verde con la sirena sin dueño, porque
    está anclada a un nombre y no a un hecho.

    Aquí el despliegue no nombra ninguna unidad: PREGUNTA al cerrojo de
    propiedad quién manda, y lo dice.
    """
    r = gabinete.desplegar()
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"

    dueno = gabinete.dueno_de_los_pines()
    assert dueno.get("unit"), "premisa: el arranque simulado dejó su unidad en el registro"
    assert f"pid {dueno['pid']}" in r.stdout, "el despliegue debe decir QUIÉN tiene los pines"
    assert dueno["unit"] in r.stdout


def test_el_pid_del_registro_ES_el_proceso_que_sostiene_el_cerrojo(gabinete) -> None:
    """El arnés tiene que modelar UN dueño, no un padre y un hijo.

    El systemctl falso lanzaba `flock -n <archivo> sleep 120 &` y anotaba `$!`.
    util-linux hace fork: `$!` era el PID de **flock**, y quien se queda con el
    descriptor —o sea con el cerrojo— es el `sleep` HIJO. Consecuencias medidas:
    el teardown del fixture mataba al padre y dejaba el `sleep` vivo dos minutos
    sosteniendo un cerrojo, y el registro nombraba a un proceso que no era el
    dueño (que es exactamente el fallo que `deploy.sh` existe para delatar).

    Se mide matando al PID del registro: si ES el dueño, el cerrojo queda libre.
    """
    assert gabinete.desplegar().returncode == 0
    pid = int(gabinete.dueno_de_los_pines()["pid"])
    assert pathlib.Path(f"/proc/{pid}").is_dir(), "premisa: el registro nombra a un proceso vivo"

    libre = ["flock", "-n", str(gabinete.cerrojo), "true"]
    assert subprocess.run(libre, timeout=30).returncode != 0, "premisa: el cerrojo está tomado"

    os.kill(pid, signal.SIGKILL)
    for _ in range(50):  # el kernel suelta el flock al cerrar el fd, no instantáneamente
        if subprocess.run(libre, timeout=30).returncode == 0:
            break
        time.sleep(0.1)
    else:
        pytest.fail(
            "matar al PID del registro NO soltó el cerrojo: quien lo sostiene es "
            "OTRO proceso (el hijo de `flock`), así que el registro miente y el "
            "teardown de este fixture deja procesos colgados"
        )


def test_un_servicio_vivo_que_NO_tiene_los_pines_tumba_el_despliegue(gabinete) -> None:
    """LA NO-VACUIDAD, y el fallo concreto que el `is-active` no ve.

    `NO_RECLAMA_PINES=1` deja el escenario exacto: `systemctl restart` devuelve
    0, `systemctl is-active` dice `active`… y NADIE sostiene el cerrojo. Con la
    verificación anterior este despliegue salía en VERDE y el operador se iba del
    sitio con un edificio sin alertamiento.
    """
    r = gabinete.desplegar(NO_RECLAMA_PINES="1")

    assert "systemctl restart takab-edge" in gabinete.registro(), (
        "premisa: el despliegue llegó hasta el reinicio; sólo falta el dueño de los pines"
    )
    assert r.returncode != 0, (
        "un gabinete cuyos pines no tiene NADIE es un gabinete que no protege; "
        "el despliegue no puede reportarlo como bueno.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "NADIE reclamó los pines" in r.stderr
    assert "ni siquiera existe" in r.stderr, (
        "el diagnóstico tiene que distinguir «nunca se reclamó» de «se soltó»: "
        "son dos averías distintas y el operador actúa distinto"
    )


def test_la_verificacion_no_esta_anclada_al_nombre_takab_edge(gabinete) -> None:
    """El criterio 1 de T-2.70.a en cuanto se cumpla: los pines pasan a
    `takab-gpio` y el despliegue tiene que seguir verificándolos SIN cambiar.

    Si la verificación siguiera escrita contra `takab-edge`, este despliegue
    —pines en poder de otra unidad, que es el estado FINAL deseado— saldría en
    rojo o, peor, en verde midiendo a quien ya no toca el GPIO.
    """
    r = gabinete.desplegar(UNIDAD_DUENA="takab-gpio")

    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert gabinete.dueno_de_los_pines()["unit"] == "takab-gpio"
    assert "takab-gpio" in r.stdout, (
        "el despliegue debe REPORTAR la unidad que de verdad tiene los pines, "
        "no la que el script trae escrita"
    )


def test_el_cerrojo_se_interroga_con_flock_y_no_leyendo_el_archivo(gabinete) -> None:
    """El registro del cerrojo es TEXTO: sobrevive al proceso que lo escribió.

    Una verificación que se conformara con leerlo daría por bueno un gabinete
    cuyo dueño murió por SIGKILL hace media hora. Lo que prueba propiedad es el
    `flock`, que muere con el proceso pase lo que pase. Aquí se siembra un
    registro con aspecto perfecto y sin nadie detrás.
    """
    gabinete.cerrojo.write_text("pid=1\nunit=takab-edge\n")
    r = gabinete.desplegar(NO_RECLAMA_PINES="1")

    assert r.returncode != 0, (
        "el despliegue se creyó un registro de texto sin comprobar el cerrojo: "
        "un dueño muerto se está reportando como vivo.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    # Y aborta por la rama del CERROJO, no por la de «el archivo no existe»: el
    # archivo está ahí, con aspecto impecable. Sin esta aserción los dos
    # escenarios colapsarían en el mismo camino y este test no probaría el flock.
    assert "ni siquiera existe" not in r.stderr
    assert "está LIBRE" in r.stderr
