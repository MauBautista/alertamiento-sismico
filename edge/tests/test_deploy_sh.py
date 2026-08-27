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
    flock_real = shutil.which("flock")

    # El intérprete falso del venv. Lo usan TRES caminos del script: el pre-vuelo
    # (`compileall`, que aquí delega en el python real y compila el árbol de
    # verdad), el gate (`-c '<imports>'`) y la HUELLA DEL DUEÑO DE LOS PINES
    # (`-c '<script con HUELLA-DEL-DUENO>'`). Las variables de entorno separan
    # los modos de fallo que el script debe distinguir.
    #
    # [T-2.70.a·D3·B2] La huella va PRIMERO en el `case`: su script menciona
    # `takab_edge` (importa el entry point del dueño) y sin este orden caería en
    # la rama de `FALLA_CODIGO`, que sale 0 sin imprimir nada — o sea que el
    # veredicto se leería como «no se pudo medir».
    #
    # EL DEFAULT ES `DUENO-IGUAL`, y esto no es comodidad: en este arnés nada
    # cambia los bytes de los módulos del dueño, así que «su código es el que
    # acabamos de desplegar» es LO CIERTO. Lo contrario —callar por omisión— hacía
    # que el veredicto de CADA test de despliegue sano dependiera de si el gate
    # llegaba a preguntar, y eso lo decide una CARRERA DE UN SEGUNDO:
    # `INICIO_DUENO = btime + ticks/HZ` trunca a segundos enteros y `MARCA_SWAP`
    # es `date +%s`. En un portátil el test dura ~1 s, los dos caen en el mismo
    # segundo, el gate se salta la huella y todo sale verde; en un runner más
    # lento caen en segundos distintos, el gate SÍ pregunta, el falso no
    # contestaba nada y ocho tests se ponían rojos. Verde por velocidad no es
    # verde, y el rojo estaba en el único sitio donde nadie miraba.
    #
    # Los dos escenarios que sí quieren medir la frescura lo DECLARAN:
    #   DUENO_CODIGO_CAMBIO=1 → el dueño se quedó con el código anterior.
    #   DUENO_HUELLA_MUDA=1   → el intérprete revienta y NO se puede medir; el
    #                           gate tiene que salir rojo igual (fail-closed).
    py_venv = f"""
        case "$1 $2" in
          "-m compileall")
            [ -n "${{FALLA_COMPILEALL:-}}" ] && {{ echo "SyntaxError simulado" >&2; exit 1; }}
            exec "{python_real}" "$@" ;;
        esac
        case "$2" in
          *HUELLA-DEL-DUENO*)
            [ -n "${{DUENO_HUELLA_MUDA:-}}" ] && exit 0
            if [ -n "${{DUENO_CODIGO_CAMBIO:-}}" ]; then
              echo "DUENO-CAMBIO takab_edge/gpio/__main__.py"
            else
              echo "DUENO-IGUAL"
            fi
            exit 0 ;;
          *lgpio*)
            [ -n "${{FALLA_DEPS:-}}" ] && {{ echo "No module named lgpio" >&2; exit 1; }} ;;
          *takab_edge*)
            [ -n "${{FALLA_CODIGO:-}}" ] && {{ echo "ImportError: takab_edge" >&2; exit 1; }} ;;
        esac
        exit 0
    """

    # [T-2.70] GABINETE YA MIGRADO AL LAYOUT A/B, que es el caso normal a partir
    # de esta ficha: una release completa en `releases/<id>/edge` y `edge` como
    # SYMLINK a ella. `vivo` sigue siendo la ruta que los `ExecStart` nombran, y
    # todo lo que se lee «del árbol vivo» se lee a través del enlace — que es
    # exactamente lo que hace el gabinete.
    #
    # Que el venv exista importa: el pre-vuelo compila con SU intérprete (3.12 en
    # el Pi) y no con el del sistema (3.13). Y que el ejecutable `takab-edge`
    # exista también: es lo que `canary.sh` exige para aceptar una release como
    # vuelta atrás válida.
    release_previa = raiz / "releases" / "20260101T000000Z-anterior" / "edge"
    (release_previa / ".venv" / "bin").mkdir(parents=True)
    (release_previa.parent / "shared" / "schemas").mkdir(parents=True)
    (release_previa / _CENTINELA).write_text("soy el despliegue anterior\n")
    _escribir_ejecutable(release_previa / ".venv" / "bin" / "python", py_venv)
    _escribir_ejecutable(release_previa / ".venv" / "bin" / "takab-edge", "exec sleep 600")
    vivo = raiz / "edge"
    vivo.symlink_to(release_previa)

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

    # [T-2.70·CAMPO] `VENV_PYTHON_EN=<ruta>` hace que el `bin/python` del venv sea
    # un SYMLINK a esa ruta, que es exactamente lo que `uv` hace con su intérprete
    # gestionado. Sin poder modelarlo, el gate del intérprete no se podría probar.
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
        if [ -n "${{VENV_PYTHON_EN:-}}" ]; then
          cp "{plantilla_py}" "${{VENV_PYTHON_EN}}"
          ln -sf "${{VENV_PYTHON_EN}}" .venv/bin/python
        else
          [ -x .venv/bin/python ] || cp "{plantilla_py}" .venv/bin/python
        fi
        {materializar}
        """,
    )

    # sudo falso: registra SIEMPRE y delega TODO salvo lo que escribiría fuera del
    # sandbox (`install` en /etc/systemd/system, `chown`). La lista está invertida
    # a propósito: antes era una allowlist de un solo comando (`systemctl`) y
    # cualquier `sudo` nuevo se convertía en un `exit 0` mudo. Eso escondió el
    # defecto que `gw-dev-0001` destapó el 2026-08-09 — la identidad del gabinete
    # se leía SIN sudo, y en un Pi real (`edge.env` es 0600 root:root) abortaba
    # todo despliegue. Con la allowlist, un `sudo sed` de arreglo habría devuelto
    # cadena vacía y el dueño habría caído al default `edge` con los tests en
    # verde: exactamente el fallo que D3 existe para impedir.
    _escribir_ejecutable(
        binarios / "sudo",
        f"""
        REAL="$@"
        case "$1" in -n) shift ;; esac
        echo "sudo $REAL" >> "{bitacora}"
        case "$1" in
          install|chown) exit 0 ;;
          *) exec "$@" ;;
        esac
        """,
    )

    # El cerrojo de propiedad de pines del gabinete de mentira (T-2.70.a·D1.1).
    cerrojo = tmp_path / "gpio.lock"
    # Contabilidad DEL ARNÉS, no del script: el PID del proceso que sostiene el
    # cerrojo, para que el teardown pueda matarlo SIEMPRE. Antes se leía del
    # registro del propio cerrojo, y eso deja de funcionar en cuanto un test
    # simula un registro vacío (ENOSPC) o un registro que MIENTE sobre el pid:
    # el `sleep 120` quedaba vivo dos minutos sosteniendo un cerrojo.
    pid_dueno = tmp_path / "dueno-real.pid"

    # systemctl falso. Su `restart` RECLAMA LOS PINES, que es lo que hace de
    # verdad el proceso que arranca: `GpioController._on_start` toma un flock
    # EXCLUSIVO sobre el cerrojo y escribe su PID y su unidad. Sin modelar eso,
    # la verificación de propiedad no se podría probar en absoluto.
    #
    #   NO_RECLAMA_PINES=1 → el servicio arranca pero NADIE toma el GPIO. Es el
    #     escenario que `systemctl is-active` no puede ver: unidad viva, sirena
    #     sin dueño.
    #   UNIDAD_DUENA=... → los pines los reclama OTRA unidad (mañana: takab-gpio).
    #   UNIDADES_VIVAS=... → qué unidades conoce systemd Y están activas.
    #   RETRASO_CERROJO=N → el arranque tarda N segundos en tomar el cerrojo.
    #   REGISTRO_VACIO=1 → toma el cerrojo pero NO escribe el registro (ENOSPC).
    #   REGISTRO_RANCIO=1 → escribe primero una línea de un dueño ANTERIOR.
    #   PID_FALSO=N → el registro nombra a N en vez de al dueño de verdad.
    #   UNIDADES_HABILITADAS=... → qué unidades tiene systemd habilitadas al
    #     arrancar (`is-enabled`). Por defecto SOLO `takab-edge`, que es el
    #     estado de todo gabinete desplegado hasta hoy.
    #
    # [T-2.70.a·D3·B2] `start` reclama los pines igual que `restart`: el
    # despliegue de un gabinete provisionado con el dueño dedicado usa `start`
    # (no-op si ya corre) y NUNCA `restart`, porque reiniciar a un dueño VIVO
    # cicla GAS_VALVE y DOOR_RETAINER. Si el falso no modelara `start`, ese
    # camino no reclamaría nada y el test no podría distinguirlo de un `enable`
    # a secas.
    #
    # [T-2.70.a·D1·BLOQUEANTE] `is-active` es una ALLOWLIST, no un `echo active`
    # incondicional. Esa era la vacuidad que dejaba pasar dos mutaciones del paso
    # 7 con los 14 tests en verde: un doble que dice `active` y sale 0 para
    # CUALQUIER cadena no puede distinguir «se interrogó a la unidad dueña» de
    # «se interrogó a `takab-edge`» ni de «no se interrogó a nadie». Y una
    # DENYLIST (`UNIDADES_MUERTAS=…`) no arreglaría el fondo: seguiría diciendo
    # `active` por defecto para un nombre que no es una unidad —justo el caso
    # del `python -m takab_edge.gpio` suelto de una sesión SSH—, que es el
    # escenario que esta verificación existe para delatar.
    _escribir_ejecutable(
        binarios / "systemctl",
        f"""
        echo "systemctl $*" >> "{bitacora}"
        # FALLA_START_GPIO=1 → la unidad del dueño no arranca (ExecStart que
        # revienta, unidad mal escrita, dependencia sin montar). El despliegue NO
        # puede abortar por el código de salida de systemctl: el veredicto lo da
        # el paso 7, que MIDE quién tiene los pines.
        if [ -n "${{FALLA_START_GPIO:-}}" ] && [ "$2" = takab-gpio ]; then
          case "$1" in
            start|restart|enable) echo "Job for takab-gpio.service failed" >&2; exit 1 ;;
          esac
        fi
        # QUÉ UNIDAD RECLAMA LOS PINES lo decide el `edge.env` del gabinete, no
        # una constante del arnés: con `TAKAB_EDGE_GPIO_OWNER=gpio`, `takab-edge`
        # NO instancia su GpioController y arrancarlo no toca el cerrojo. Sin
        # modelar eso, cualquier `restart takab-edge` «reclamaba» los pines y un
        # `takab-gpio` que no arranca salía en verde — el escenario (a) de la
        # auditoría, invisible. Se lee del archivo, con la misma semántica de
        # «gana la última» que systemd, pero con un lector INDEPENDIENTE del que
        # usa deploy.sh: así el script se mide contra el gabinete y no contra sí
        # mismo.
        DUENO_CFG="$(sed -n 's/^ *TAKAB_EDGE_GPIO_OWNER=//p' \\
          "${{TAKAB_EDGE_ENV_FILE:-/dev/null}}" 2>/dev/null | tail -1 || true)"
        case "$DUENO_CFG" in gpio) RECLAMANTE=takab-gpio ;; *) RECLAMANTE=takab-edge ;; esac

        case "$1" in restart|start) ARRANCA=1 ;; *) ARRANCA=0 ;; esac
        [ "$2" = "$RECLAMANTE" ] || ARRANCA=0
        # `restart` DETIENE antes de arrancar, y detener al dueño de los pines
        # suelta el cerrojo: sin modelarlo, un `restart takab-gpio` sobre un
        # dueño vivo no cambiaba nada y la ventana de mantenimiento no se podía
        # distinguir de no hacer nada. Sólo se mata al proceso si el registro
        # dice que los pines los tiene ESTA unidad — `restart takab-edge` no
        # detiene a `takab-gpio`.
        if [ "$1" = restart ] && [ -s "{pid_dueno}" ]; then
          DUENO_ACTUAL="$(sed -n 's/^unit=//p' "{cerrojo}" 2>/dev/null | tail -1 || true)"
          if [ "$DUENO_ACTUAL" = "$2" ]; then
            kill -9 "$(cat "{pid_dueno}")" 2>/dev/null || true
            for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
              flock -n "{cerrojo}" true && break
              sleep 0.05
            done
          fi
        fi
        if [ "$ARRANCA" = 1 ] && [ -z "${{NO_RECLAMA_PINES:-}}" ]; then
          # `exec` y no `flock -n <archivo> sleep 120`: util-linux hace fork, así
          # que ahí `$!` era el PID de FLOCK y el que se queda con el descriptor
          # (y con el cerrojo) es el `sleep` hijo. El teardown mataba al padre y
          # dejaba vivo al `sleep` dos minutos más, sosteniendo el cerrojo. Con
          # el subshell + `exec`, `$BASHPID` ES el proceso que tiene el fd 9
          # abierto: el registro nombra al dueño de verdad y matarlo lo suelta.
          #
          # El cerrojo se ABRE dentro del subshell (`exec 9<>`) y no en la
          # redirección del `&`, porque con `RETRASO_CERROJO` el archivo no debe
          # existir hasta que el arranque llegue de verdad a `gpio._on_start`:
          # así el sondeo del paso 7 ve la secuencia REAL de un arranque lento
          # —no hay archivo, luego hay archivo y cerrojo libre, luego dueño— y no
          # una toma instantánea que ningún test podría distinguir de un `sleep`.
          #
          # `9<>` y NO `9>` [T-2.70.a·D3·B2]: `>` TRUNCA el archivo antes de
          # intentar el `flock`, así que un arranque que llega tarde y NO
          # consigue el cerrojo borraba igualmente el registro del dueño que sí
          # lo tiene. `GpioController._acquire_pin_ownership` abre con
          # `O_RDWR|O_CREAT` —sin truncar— y trunca DESPUÉS del flock; el arnés
          # tiene que hacer lo mismo o modela una avería que el código no tiene.
          (
            sleep "${{RETRASO_CERROJO:-0}}"
            exec 9<>"{cerrojo}"
            flock -n 9 || exit 1
            echo "$BASHPID" > "{pid_dueno}"
            if [ -z "${{REGISTRO_VACIO:-}}" ]; then
              if [ -n "${{REGISTRO_RANCIO:-}}" ]; then
                printf 'pid=1\\nunit=impostor.service\\n' > "{cerrojo}"
              fi
              printf 'pid=%s\\nunit=%s\\n' \\
                "${{PID_FALSO:-$BASHPID}}" "${{UNIDAD_DUENA:-$2}}" >> "{cerrojo}"
            fi
            exec sleep 120
          ) </dev/null >/dev/null 2>&1 &
          sleep 0.3
        fi
        if [ "$1" = show ]; then
          # [T-2.70] El MainPID que el canary vigila durante el remojo. Sale del
          # dueño de los pines cuando `takab-edge` lo es, y de un valor estable
          # cuando no: lo que el canary mide es que NO CAMBIE.
          if [ -s "{pid_dueno}" ]; then cat "{pid_dueno}"; else echo 4242; fi
          exit 0
        fi
        if [ "$1" = is-active ]; then
          case " ${{UNIDADES_VIVAS:-takab-edge takab-gpio}} " in
            *" $2 "*) echo active; exit 0 ;;
          esac
          echo inactive
          exit 3
        fi
        if [ "$1" = is-enabled ]; then
          case " ${{UNIDADES_HABILITADAS:-takab-edge}} " in
            *" $2 "*) echo enabled; exit 0 ;;
          esac
          echo disabled
          exit 1
        fi
        exit 0
        """,
    )
    # [T-2.70] `curl` falso: el panel local del gabinete, que es una de las
    # cuatro señales de salud que el canary sostiene durante el remojo.
    # `PANEL_MUERTO=1` lo calla — un supervisor que arranca y no llega a servir.
    _escribir_ejecutable(
        binarios / "curl",
        """
        if [ -n "${PANEL_MUERTO:-}" ]; then exit 22; fi
        echo '{"ok":true}'
        """,
    )

    # flock falso: delega SIEMPRE en el real salvo para simular la tercera rama
    # del veredicto — «no se pudo interrogar el cerrojo», que no es ni 0 (libre)
    # ni 9 (tomado). El discriminante es `-E`, que sólo usa la INTERROGACIÓN de
    # `deploy.sh`; la toma del cerrojo del `systemctl` falso (`flock -n 9`) sigue
    # yendo al binario de verdad, con su fd 9 heredado a través de este wrapper.
    #
    # No se reproduce con un cerrojo que sea un DIRECTORIO —lo primero que se
    # probó—: `flock` bloquea un directorio sin pestañear y sale 0, o sea que ese
    # escenario cae en «está LIBRE», que es la avería CONTRARIA. Tampoco con un
    # `chmod 000`: en un CI que corra como root eso no falla y el test se
    # volvería vacío sin avisar.
    _escribir_ejecutable(
        binarios / "flock",
        f"""
        if [ -n "${{FLOCK_ILEGIBLE:-}}" ] && [ "$2" = -E ]; then
          echo "flock: no se pudo abrir el cerrojo (simulado)" >&2
          exit "${{FLOCK_ILEGIBLE}}"
        fi
        exec "{flock_real}" "$@"
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

    # [T-2.70.a·D3·B2] El `/etc/takab/edge.env` del gabinete de mentira. Es la
    # IDENTIDAD (mapa de pines, tenant/site, dev_mode) y desde D3 también dice
    # QUIÉN es el dueño de los pines (`TAKAB_EDGE_GPIO_OWNER`), que es lo que el
    # despliegue tiene que leer para decidir a quién habilitar. Existe por
    # defecto porque un gabinete SIN él no arranca: las dos unidades lo declaran
    # `EnvironmentFile=` sin `-`.
    entorno = tmp_path / "edge.env"
    entorno.write_text("TAKAB_EDGE_GATEWAY_ID=gw-falso-0001\nTAKAB_EDGE_DEV_MODE=false\n")

    class Gabinete:
        def __init__(self) -> None:
            self.raiz = raiz
            self.vivo = vivo
            self.releases = raiz / "releases"
            self.release_previa = release_previa
            self.bitacora = bitacora
            self.cerrojo = cerrojo
            self.pid_dueno = pid_dueno
            self.entorno = entorno

        def provisionar(self, **claves: str) -> None:
            """Reescribe el `edge.env` del gabinete con estas claves añadidas."""
            lineas = ["TAKAB_EDGE_GATEWAY_ID=gw-falso-0001", "TAKAB_EDGE_DEV_MODE=false"]
            lineas += [f"{k}={v}" for k, v in claves.items()]
            entorno.write_text("\n".join(lineas) + "\n")

        def dueno_preexistente(self, unidad: str = "takab-gpio") -> int:
            """Un dueño de pines que YA estaba corriendo ANTES de este despliegue.

            Es el estado normal de un gabinete con `TAKAB_EDGE_GPIO_OWNER=gpio`:
            `takab-gpio` lleva días de pie y el despliegue NO lo reinicia (eso
            costaría un ciclo eléctrico de gas y retenedores). Modelarlo es lo
            único que permite medir si el script se da cuenta de que el dueño se
            quedó con el CÓDIGO ANTERIOR.

            Mismo `exec` que el systemctl falso: `$BASHPID` ES el proceso que
            sostiene el descriptor, así que el registro nombra al dueño de verdad
            y el teardown puede matarlo.
            """
            guion = f"""
            (
              exec 9<>"{cerrojo}"
              flock -n 9 || exit 1
              echo "$BASHPID" > "{pid_dueno}"
              printf 'pid=%s\\nunit=%s\\n' "$BASHPID" "{unidad}" > "{cerrojo}"
              exec sleep 120
            ) </dev/null >/dev/null 2>&1 &
            """
            subprocess.run(["bash", "-c", textwrap.dedent(guion)], check=True, timeout=30)
            # El arranque del dueño tiene que quedar en un SEGUNDO distinto al del
            # swap: el veredicto compara epochs enteros y sin esta separación un
            # dueño rancio podría leerse como recién arrancado. En el Pi la
            # distancia real son días; aquí, 1.2 s.
            for _ in range(100):
                if pid_dueno.exists() and pid_dueno.read_text().strip().isdigit():
                    break
                time.sleep(0.05)
            time.sleep(1.2)
            return int(pid_dueno.read_text().strip())

        def desplegar(self, *args: str, **entorno_extra: str) -> subprocess.CompletedProcess[str]:
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
            # Mismo seam: en producción nadie lo exporta y vale
            # /etc/takab/edge.env, que es el `EnvironmentFile=` de LAS DOS
            # unidades. El sandbox no puede escribir ahí.
            env["TAKAB_EDGE_ENV_FILE"] = str(entorno)
            # [T-2.70] El despliegue ACTIVA por `bin/canary.sh`, que aquí corre
            # DE VERDAD: sus plazos se acortan (en el Pi son 90 s + 120 s) y su
            # estado se escribe dentro del tmp, no en /var/lib/takab.
            env["TAKAB_CANARY_ESTADO"] = str(tmp_path / "canary")
            env["TAKAB_CANARY_PLAZO_ARRANQUE"] = "12"
            env["TAKAB_CANARY_REMOJO"] = "2"
            env["TAKAB_CANARY_INTERVALO"] = "1"
            env["TAKAB_CANARY_PANEL"] = "http://127.0.0.1:8080/api/status"
            # [T-2.171] La regla A-1 se declara SALTADA aquí, y a propósito: esta
            # suite no despliega nada — corre `deploy.sh` contra un gabinete de
            # mentira, desde una rama de trabajo o desde la rama de una PR, que
            # nunca son `main`. Sin esto los 38 tests morirían en la guardia sin
            # llegar a probar lo que vienen a probar.
            #
            # Que la guardia FUNCIONE no se comprueba aquí sino en
            # `api/tests/test_guarda_de_rama.py`, que la corre contra repos de
            # mentira con su `origin` y juzga su código de salida. Saltarla en un
            # sitio donde no aplica no es debilitarla; confundir los dos sitios,
            # sí lo sería.
            env["TAKAB_DEPLOY_RAMA_LIBRE"] = "1"
            env.update(entorno_extra)
            return subprocess.run(
                ["bash", str(_DEPLOY), "gabinete-falso", *args],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(_RAIZ),
                timeout=300,
            )

        def soltar_los_pines(self) -> None:
            """Mata al dueño de los pines y limpia su registro, si lo hay."""
            if pid_dueno.exists():
                pid = pid_dueno.read_text().strip()
                if pid.isdigit():
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        os.kill(int(pid), signal.SIGKILL)
                pid_dueno.unlink()
            if self.cerrojo.exists():
                self.cerrojo.write_text("")

        def gabinete_virgen(self) -> None:
            """PRIMER despliegue de este gabinete: ni código en disco ni dueño.

            No es un caso de laboratorio — es el estado de todo gabinete nuevo.

            **También suelta los pines, y eso no es limpieza: es la premisa.** Un
            gabinete sin `/opt/takab/edge` no puede tener un proceso ejecutando
            ese código. Modelar lo contrario producía un escenario imposible —
            árbol borrado + dueño vivo— en el que el script hace lo correcto
            (sin instantánea con la que comparar, el veredicto es rojo
            conservador) y el test esperaba verde. Que el test pasara o no lo
            decidía una carrera de un segundo: `INICIO_DUENO >= MARCA_SWAP` son
            dos relojes de segundo ENTERO, y aquí el despliegue entero cabe en
            uno. En CI, más lento, no cabía, y el test parpadeaba.

            El escenario que SÍ existe —árbol borrado a mano con el servicio
            todavía en pie— tiene ahora su propio test, y ahí el rojo es lo
            correcto.
            """
            # Con el layout A/B «borrar el árbol vivo» es dejar el gabinete sin
            # symlink Y sin la release a la que apuntaba: es el estado de un
            # gabinete recién aprovisionado, o de uno al que alguien le borró
            # /opt/takab/edge a mano.
            self.vivo.unlink()
            shutil.rmtree(self.release_previa.parent)
            self.soltar_los_pines()

        def sin_migrar(self) -> None:
            """Devuelve el gabinete al layout de antes de T-2.70: `edge` como
            DIRECTORIO de verdad. Es el estado de todo gabinete desplegado hasta
            esta ficha, y el que la migración A/B tiene que reconocer."""
            self.vivo.unlink()
            shutil.copytree(self.release_previa, self.vivo, symlinks=True)
            shutil.rmtree(self.release_previa.parent)

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
        # cerrojo. Que el PID sea EXACTAMENTE ese proceso lo garantiza el `exec`
        # del systemctl falso (ver arriba): con `flock -n <archivo> sleep 120`
        # este `kill` mataba al padre `flock` y el `sleep` heredero seguía con el
        # descriptor.
        #
        # Se lee del archivo de contabilidad DEL ARNÉS y no del registro del
        # cerrojo: hay tests que simulan un registro vacío o un registro que
        # miente sobre el pid, y ahí el registro no sirve para limpiar.
        pid = ""
        if pid_dueno.exists():
            pid = pid_dueno.read_text().strip()
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


def test_tras_activar_la_release_anterior_sigue_ENTERA(gabinete) -> None:
    """[T-2.70] La reversibilidad que el layout A/B trae, y que `edge.prev` no
    podía dar: la release anterior sigue en disco CON SU VENV, así que volver a
    ella devuelve código Y dependencias.

    Antes esto era una instantánea del fuente con `--exclude .venv`: revertía la
    mitad, y la otra mitad exigía volver a correr el despliegue entero desde el
    commit anterior — con enlace a internet y una persona en el sitio.
    """
    assert gabinete.desplegar().returncode == 0
    anterior = gabinete.release_previa
    assert (anterior / _CENTINELA).exists(), (
        "la release anterior debe seguir siendo la ANTERIOR, no la nueva"
    )
    assert (anterior / ".venv" / "bin" / "takab-edge").exists(), (
        "sin su venv la release anterior no es una vuelta atrás: es media"
    )
    assert gabinete.vivo.is_symlink(), "el árbol vivo debe ser el symlink que decide la versión"
    assert not gabinete.vivo.resolve().samefile(anterior), "el symlink no se repuntó"


# ------------------------------------------- B3: abortar sin haber destruido


def test_el_prevuelo_aborta_sin_tocar_el_arbol_vivo(gabinete) -> None:
    """B3, LA PRUEBA DE COMPORTAMIENTO.

    El código nuevo no compila. Antes, el gate corría DESPUÉS del `rsync
    --delete` y el disco ya tenía el código nuevo sin verificar: el mensaje
    «sigue con el código anterior» era falso y el próximo arranque —un corte de
    luz, un `Restart=always`— habría ejecutado ese código solo.

    Con el layout A/B el pre-vuelo corre sobre una RELEASE que nadie apunta. Al
    abortar, el árbol vivo tiene que seguir EXACTAMENTE como estaba: el
    centinela del despliegue anterior sigue ahí y el código nuevo NO llegó a la
    ruta desde la que arrancan las unidades.
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
    assert "Estado seguro" in r.stderr


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


def test_un_gate_que_falla_YA_NO_deja_codigo_sin_verificar_en_la_ruta_de_arranque(
    gabinete,
) -> None:
    """[T-2.70] EL PELIGRO QUE ESTE TEST VIGILABA DEJÓ DE EXISTIR, y por eso el
    test cambia de forma en vez de borrarse.

    Con el despliegue in-place, un gate que fallaba dejaba el disco con código
    nuevo SIN VERIFICAR en `/opt/takab/edge`, y el próximo arranque —un corte de
    luz, un `Restart=always`— lo ejecutaba solo. El script tuvo que aprender a
    DECIRLO, porque el texto anterior («sigue con el código anterior») era falso
    justo en el escenario más peligroso.

    Con A/B la release que falla el gate es INERTE: nadie la apunta. Así que
    ahora lo que se exige es lo contrario — que el árbol vivo siga siendo el
    anterior, y que el mensaje no invente ni un peligro ni una vuelta atrás.
    """
    r = gabinete.desplegar(FALLA_CODIGO="1")

    assert r.returncode != 0
    assert gabinete.centinela_intacto(), "el gabinete debe seguir apuntando a la release anterior"
    assert not gabinete.codigo_nuevo_en_el_arbol_vivo(), (
        "la release que falló el gate NO puede estar en la ruta desde la que arranca"
    )
    assert "systemctl restart takab-edge" not in gabinete.registro(), (
        "un gate que falla no puede haber reiniciado nada"
    )
    assert "intacto" in r.stderr
    assert "EL DISCO YA TIENE EL CÓDIGO NUEVO" not in r.stderr, (
        "ese aviso describía el layout in-place; repetirlo ahora sería mentir al revés"
    )


# ------------------- A3: el primer despliegue no tiene vuelta atrás que ofrecer


def test_el_primer_despliegue_de_un_gabinete_virgen_completa(gabinete) -> None:
    """Premisa del test de abajo, y camino real de todo gabinete nuevo: sin
    `/opt/takab/edge` previo el despliegue tiene que terminar igual de bien.

    Aquí no hay release anterior, y eso es correcto; lo que no era correcto es lo
    que el mensaje de aborto decía en ese caso.
    """
    gabinete.gabinete_virgen()
    r = gabinete.desplegar()

    assert gabinete.codigo_nuevo_en_el_arbol_vivo()
    assert "no hay release anterior completa" in r.stdout, (
        "un gabinete virgen tiene que ENTERARSE de que no tiene vuelta atrás"
    )

    # El VEREDICTO no se puede exigir verde aquí, y exigirlo era codificar un
    # accidente de esta máquina. Sin release anterior no hay con qué comparar el
    # código del dueño, así que el script sólo puede certificar el despliegue si
    # LEE que el dueño arrancó después de la activación — y esa lectura es de
    # `/proc/<pid>/stat`, que en un contenedor endurecido (el runner de CI) puede
    # no estar disponible. Cuando no lo está, el rojo es CORRECTO: fail-closed.
    #
    # Lo que sí se exige, y es más fuerte que el `rc == 0` de antes: si se niega
    # a certificar, tiene que decir la razón que MIDIÓ. El script llegó a afirmar
    # "arrancó ANTES del swap" con INICIO_DUENO=0 por no haber podido leer nada.
    if r.returncode != 0:
        assert "no se pudo LEER el arranque" in r.stderr or "no hay release anterior" in r.stderr, (
            "se negó a certificar el despliegue sin decir cuál de las dos cosas "
            f"le faltó.\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )


def test_sin_release_anterior_el_aborto_no_ofrece_una_vuelta_atras_inexistente(gabinete) -> None:
    """A3. El mensaje de aborto ofrecía SIEMPRE el comando de restauración desde
    `edge.prev` — pero `edge.prev` sólo se creaba `if [ -d "$VIVO" ]`.

    En el primer despliegue de un gabinete esa instantánea NO EXISTÍA, así que el
    script mandaba a un operador con el gabinete abortado a correr un `rsync`
    desde un directorio que no está. Es la misma familia que la frase «sigue con
    el código anterior»: el mensaje afirma un estado seguro que no se ha
    comprobado, y un operador que se fía se va del sitio creyendo que puede
    volver atrás.

    Con A/B el comando desapareció —la vuelta atrás es del canary y no del
    operador—, pero la obligación es la misma: si este gabinete no tiene NINGUNA
    release buena, el mensaje tiene que decirlo.
    """
    gabinete.gabinete_virgen()
    r = gabinete.desplegar(FALLA_CODIGO="1")

    assert r.returncode != 0
    assert "rsync -a --delete --exclude .venv" not in r.stderr, (
        "ofrece restaurar desde una instantánea que NO se tomó: el comando fallaría "
        "y el operador ya se habría ido creyendo que tiene vuelta atrás"
    )
    assert "sigue SIN código bueno" in r.stderr, (
        "en el primer despliegue el mensaje debe DECIR que no hay release a la que volver"
    )


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

    [T-2.70] Desde el canary este caso ya no sólo se DELATA: se REVIERTE. La
    propiedad de los pines es una de las cuatro señales del remojo, así que la
    activación no llega ni a declararse buena — vuelve sola a la release
    anterior y el despliegue sale rojo.
    """
    r = gabinete.desplegar(NO_RECLAMA_PINES="1", TAKAB_DEPLOY_PLAZO_PROPIEDAD="2")

    assert "systemctl restart takab-edge" in gabinete.registro(), (
        "premisa: el despliegue llegó hasta el reinicio; sólo falta el dueño de los pines"
    )
    assert r.returncode != 0, (
        "un gabinete cuyos pines no tiene NADIE es un gabinete que no protege; "
        "el despliegue no puede reportarlo como bueno.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "REVERTIDO" in r.stderr or "NADIE reclamó los pines" in r.stderr
    assert "cerrojo" in r.stderr or "pines" in r.stderr, (
        "el diagnóstico tiene que nombrar la PROPIEDAD DE LOS PINES: es lo que "
        "distingue «el gabinete no protege» de «la unidad no arrancó»"
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
    r = gabinete.desplegar(NO_RECLAMA_PINES="1", TAKAB_DEPLOY_PLAZO_PROPIEDAD="2")

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


# ---- D1·BLOQUEANTE: la unidad DUEÑA tiene que estar viva PARA SYSTEMD -------
#
# Estos dos tests son los que matan las mutaciones M-E4 (`systemctl is-active
# "$DUENO_UNIDAD"` → `systemctl is-active takab-edge`) y M-E5 (esa línea → `:`),
# que con los 14 tests anteriores salían en `14 passed`. La vacuidad no estaba
# en el script sino AQUÍ: el `systemctl` falso decía `active` y salía 0 para
# cualquier cadena, así que lo único comprobable era que «takab-gpio» apareciera
# en el stdout — y esa cadena la imprime el `echo` que lee el REGISTRO, aunque
# el `is-active` interrogue a otra unidad o no interrogue a nadie.


def test_una_unidad_duena_que_systemd_da_por_MUERTA_tumba_el_despliegue(gabinete) -> None:
    """El día del criterio 1 de T-2.70.a, con `takab-gpio` caído.

    Los pines los reclamó `takab-gpio` (el registro lo dice) pero systemd NO la
    tiene activa. Es el escenario que separa «hay dueño» de «hay dueño que
    sobrevive al próximo reinicio», y el que delata a una verificación anclada
    al nombre viejo: preguntar por `takab-edge` —que aquí SÍ está activa,
    haciendo todo lo demás— saldría verde midiendo a un proceso que ya no toca
    el GPIO.
    """
    r = gabinete.desplegar(
        UNIDAD_DUENA="takab-gpio",
        UNIDADES_VIVAS="takab-edge",  # takab-gpio NO está activa para systemd
        TAKAB_DEPLOY_PLAZO_PROPIEDAD="2",
    )

    assert gabinete.dueno_de_los_pines()["unit"] == "takab-gpio", (
        "premisa: los pines los tiene takab-gpio, y es lo que dice el registro"
    )
    assert r.returncode != 0, (
        "la verificación NO interrogó a la unidad que de verdad tiene los pines: "
        "o pregunta por un nombre escrito a mano, o no pregunta.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "takab-gpio" in r.stderr, (
        "el diagnóstico debe NOMBRAR a la unidad que systemd da por muerta"
    )
    assert "no sobrevive" in r.stderr, (
        "el mensaje tiene que decir POR QUÉ importa: sin unidad, el gabinete no "
        "vuelve a proteger tras el próximo reinicio"
    )
    assert "✓ pines del gabinete en poder" not in r.stdout, (
        "declaró el despliegue bueno pese a que nadie garantiza el próximo arranque"
    )


def test_los_pines_en_manos_de_un_proceso_SUELTO_tumban_el_despliegue(gabinete) -> None:
    """Un `python -m takab_edge.gpio` lanzado a mano desde una sesión SSH.

    Ese proceso sostiene el cerrojo de verdad —el edificio está protegido AHORA
    MISMO—, pero no lo gobierna systemd: el registro nombra lo que
    `_unidad_de_este_proceso()` sepa decir (`TAKAB_GPIO_UNIT` o `sys.argv[0]`),
    que no es ninguna unidad. Al primer reinicio, o al cerrar la sesión SSH, el
    gabinete se queda sin sirena, sin gas y sin retenedores, y el despliegue lo
    habría declarado bueno.

    Aquí NO se toca `UNIDADES_VIVAS`: el arnés da por muerto todo lo que no sea
    una unidad conocida, que es justo lo que hace `systemctl is-active` con una
    cadena que no es una unidad. Por eso este caso mata las mismas dos
    mutaciones sin ningún seam extra.
    """
    r = gabinete.desplegar(
        UNIDAD_DUENA="/opt/takab/edge/.venv/bin/python",
        TAKAB_DEPLOY_PLAZO_PROPIEDAD="2",
    )

    assert r.returncode != 0, (
        "los pines los sostiene un proceso que systemd no conoce y el despliegue "
        "salió en verde.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "no sobrevive" in r.stderr


# ---- D1·MENOR-1: SONDEAR, no dormir 3 s y disparar una vez ------------------


def test_un_arranque_LENTO_pero_sano_no_se_reporta_como_gabinete_sin_dueno(gabinete) -> None:
    """El falso rojo más caro que tiene este script.

    La verificación pasó de medir «systemd forkeó» (t≈0) a medir «`gpio._on_start`
    corrió su primera sentencia» —intérprete, numpy/scipy, `supervisor.build()`—
    conservando el mismo `sleep 3` de un solo disparo. Un gabinete SANO que tarde
    4 s en tomar el cerrojo se reportaba como «NADIE es dueño de los pines… el
    gabinete NO está protegiendo», y ese mensaje empuja al operador a revertir:
    revertir es reiniciar, y reiniciar mueve `GAS_VALVE` y `DOOR_RETAINER`.

    NO se pasa `TAKAB_DEPLOY_PLAZO_PROPIEDAD` A PROPÓSITO: lo que se está
    anclando es que el plazo POR DEFECTO tolere un arranque lento. Con el plazo
    en 3 s este test vuelve a rojo, que es lo que debe pasar si alguien recorta
    la constante a ciegas en vez de sondear.
    """
    r = gabinete.desplegar(RETRASO_CERROJO="4")

    assert r.returncode == 0, (
        "un gabinete que tarda 4 s en tomar los pines está SANO y se reportó "
        "como sin dueño.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "✓ pines del gabinete en poder de takab-edge" in r.stdout
    assert "NO está protegiendo" not in r.stderr


def test_el_sondeo_no_declara_bueno_un_gabinete_que_nunca_toma_los_pines(gabinete) -> None:
    """La no-vacuidad del sondeo: esperar no puede convertirse en perdonar.

    Con `NO_RECLAMA_PINES` el cerrojo no se toma nunca; ni el canary ni el paso 7
    pueden rendirse en verde por cansancio. El veredicto tiene que nombrar el
    cerrojo, que es lo que distingue este fallo de «la unidad no arrancó».
    """
    r = gabinete.desplegar(NO_RECLAMA_PINES="1", TAKAB_DEPLOY_PLAZO_PROPIEDAD="2")

    assert r.returncode != 0
    veredicto = (gabinete.raiz.parent / "canary" / "veredicto.json").read_text()
    assert "cerrojo" in veredicto, f"el veredicto del canary no nombra el cerrojo: {veredicto}"
    assert '"resultado":"revertido' in veredicto, (
        f"un gabinete que nunca toma los pines tiene que provocar la vuelta atrás: {veredicto}"
    )


# ---- D1·MENOR-2: el registro es INFORMATIVO; un disco lleno no es un intruso


def test_un_registro_ILEGIBLE_apunta_al_disco_y_no_tumba_un_gabinete_que_protege(
    gabinete,
) -> None:
    """Las dos mitades de D1 se contradecían sobre el registro.

    `gpio._registrar_dueno` escribe el registro en un `try/except` y CONSERVA la
    propiedad si su E/S falla —`ENOSPC` con `/var/lib/takab` lleno de spool y
    evidencia, o un `EIO` de una microSD muriéndose—, y eso está anclado por
    `test_un_registro_que_no_se_puede_escribir_no_tumba_la_propiedad`.
    `deploy.sh` leía ese mismo registro vacío y abortaba acusando a «un `flock`
    suelto de una sesión SSH».

    O sea: un gabinete que protege perfectamente, con su cerrojo tomado, se
    declaraba secuestrado, y el operador salía a buscar un intruso que no existe
    en vez de mirar el disco. El `flock` YA demostró que hay dueño; el texto es
    un extra.
    """
    r = gabinete.desplegar(REGISTRO_VACIO="1")

    assert gabinete.cerrojo.exists() and not gabinete.dueno_de_los_pines(), (
        "premisa: el cerrojo está tomado y su registro está VACÍO"
    )
    assert r.returncode == 0, (
        "un registro que no se pudo escribir tumbó un gabinete que SÍ tiene "
        "dueño de los pines.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "df -h" in r.stderr, "el aviso tiene que mandar al operador AL DISCO"
    assert "suelto de una sesión SSH" not in r.stderr, (
        "seguía acusando a un intruso que no existe: el operador sale a buscar "
        "un `flock` de una sesión SSH en vez de mirar el disco"
    )
    assert "⚠" in r.stderr, "y tiene que ser un AVISO visible, no un silencio"


def test_un_registro_que_nombra_un_PID_MUERTO_sigue_tumbando_el_despliegue(gabinete) -> None:
    """El límite del perdón de MENOR-2, y la rama `/proc` anclada.

    Un registro vacío es un disco enfermo; un registro que nombra a un pid que
    NO EXISTE es un registro DESMENTIDO — el cerrojo lo sostiene alguien que no
    es quien dice el texto. Ahí sí hay que abortar, y por eso el perdón del
    registro ilegible no se puede generalizar a «el registro no importa».
    """
    muerto = subprocess.Popen(["true"])
    muerto.wait()
    assert not pathlib.Path(f"/proc/{muerto.pid}").is_dir(), (
        "premisa: el pid sembrado en el registro no corresponde a ningún proceso"
    )

    r = gabinete.desplegar(PID_FALSO=str(muerto.pid), TAKAB_DEPLOY_PLAZO_PROPIEDAD="2")

    assert r.returncode != 0, (
        "el registro nombra a un pid muerto y el despliegue salió en verde.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert str(muerto.pid) in r.stderr
    assert "que no existe" in r.stderr


# ---- D1·MENOR-7: las ramas del paso 7 que nadie anclaba ---------------------


def test_un_cerrojo_que_no_se_puede_INTERROGAR_tumba_el_despliegue(gabinete) -> None:
    """La tercera rama del `flock`: ni 0 (libre) ni 9 (tomado).

    Sin poder medir la propiedad de los pines, este despliegue no se declara
    bueno — y el mensaje NO puede colapsar con el de «está LIBRE», que es la
    avería contraria: ahí se sabe que no hay dueño, aquí no se sabe nada.

    Y no se sondea: que `flock` no pueda interrogar el cerrojo no es una
    cuestión de tiempo (falta `util-linux`, no existe `/var/lib/takab`), así que
    esperar 45 s no cambiaría la respuesta. Este test corre con el plazo LARGO
    por defecto a propósito: si tardara, es que se está sondeando algo que no
    va a cambiar.
    """
    arranque = time.monotonic()
    r = gabinete.desplegar(FLOCK_ILEGIBLE="42")
    tardanza = time.monotonic() - arranque

    assert r.returncode != 0, (
        "un cerrojo que no se puede interrogar se dio por bueno.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "no se pudo interrogar el cerrojo" in r.stderr
    assert "flock salió 42" in r.stderr, "el código de salida real es el diagnóstico"
    assert "está LIBRE" not in r.stderr, (
        "«no se pudo medir» y «no hay dueño» son averías distintas y el operador "
        "actúa distinto; no pueden compartir mensaje"
    )
    assert tardanza < 30, (
        f"tardó {tardanza:.1f} s: se está sondeando una avería que no depende del "
        "tiempo, y eso alarga cada despliegue roto sin cambiar el veredicto"
    )


def test_del_registro_del_cerrojo_gana_la_ULTIMA_linea(gabinete) -> None:
    """`tail -1`, y por qué no da igual.

    El registro se reescribe con `ftruncate`+`pwrite`, pero un relevo que
    escribiera un registro más corto sobre uno más largo dejaría cola del dueño
    ANTERIOR. Quien manda es el último en escribir —igual que en systemd y en
    bash—, así que la lectura tiene que quedarse con la última línea. Con `head
    -1` este despliegue reportaría al impostor: un pid 1 que existe siempre y una
    unidad que systemd no conoce.
    """
    r = gabinete.desplegar(REGISTRO_RANCIO="1")

    assert "impostor.service" in gabinete.cerrojo.read_text(), (
        "premisa: el registro trae la línea del dueño anterior por delante"
    )
    assert r.returncode == 0, (
        "leyó el registro por la línea RANCIA en vez de por la última.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "✓ pines del gabinete en poder de takab-edge" in r.stdout
    assert "impostor" not in r.stdout, "reportó al dueño ANTERIOR como si mandara"


# ---- D3·B2: el despliegue no reiniciaba NI HABILITABA al dueño de los pines --
#
# Medido por la auditoría de D3: el script instala LAS DOS unidades, hace
# `daemon-reload` y reinicia `takab-edge`. No hay un solo `systemctl enable
# takab-gpio` en el repo y nada provisiona `TAKAB_EDGE_GPIO_OWNER`, así que:
#
#   (a) la topología de D3 no es ALCANZABLE por el camino documentado — su
#       criterio 1 sólo se cumple dentro de los tests;
#   (b) si alguien la alcanza a mano, cada despliegue actualiza el código,
#       reinicia al CLIENTE y deja al DUEÑO DE LOS PINES con el código anterior
#       indefinidamente… imprimiendo ✓;
#   (c) sin `enable`, el siguiente reinicio del Pi arranca SIN dueño de pines:
#       un edificio sin ninguna de las cuatro protecciones.
#
# LA DECISIÓN, y por qué ésta. Reiniciar al dueño es una ACTUACIÓN FÍSICA (2
# transiciones por pin en `GAS_VALVE` y `DOOR_RETAINER`, medidas en
# test_deploy_artifacts.py) y una ventana sin sirena. Si `deploy.sh` lo
# reiniciara en cada despliegue, D3 no habría comprado NADA: seguiría costando
# un ciclo eléctrico por despliegue, sólo que en otro proceso. Así que el
# reinicio del dueño va en VENTANA DE MANTENIMIENTO declarada
# (`--ventana-de-mantenimiento`), y el despliegue de todos los días:
#
#   · HABILITA la unidad del dueño (symlink; no toca un pin) — cierra (c);
#   · la ARRANCA con `start`, que es no-op si ya corre y NUNCA cicla a un dueño
#     vivo — cierra (a), porque hace la topología alcanzable sin coste físico;
#   · y si el dueño se queda con CÓDIGO ANTERIOR, NO imprime ✓ y sale != 0 —
#     cierra (b).


def test_un_gabinete_provisionado_con_el_dueno_dedicado_lo_HABILITA_y_lo_LEVANTA(
    gabinete,
) -> None:
    """(a) y (c). El camino documentado tiene que poder LLEGAR a la topología D3.

    Con `TAKAB_EDGE_GPIO_OWNER=gpio` en el `edge.env`, `takab-edge` ya no
    instancia su `GpioController`: si nadie habilita ni arranca `takab-gpio`, el
    gabinete queda sin sirena, sin cierre de gas, sin retorno de ascensores y sin
    retenedores — y el script de hoy lo dejaba así reportando el despliegue como
    bueno.

    `enable` cierra el agujero del PRÓXIMO REINICIO (sin él, el Pi arranca sin
    dueño de pines); `start` cierra el de AHORA. Y `start` y no `restart`: sobre
    un dueño ya vivo `start` es un no-op y no mueve un solo pin.
    """
    gabinete.provisionar(TAKAB_EDGE_GPIO_OWNER="gpio")
    r = gabinete.desplegar(UNIDAD_DUENA="takab-gpio")

    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    registro = gabinete.registro()
    assert "systemctl enable takab-gpio" in registro, (
        "el gabinete está provisionado con el dueño dedicado y NADIE habilita su "
        "unidad: al próximo reinicio del Pi el edificio arranca sin sirena, sin "
        "gas, sin ascensores y sin retenedores"
    )
    assert "systemctl start takab-gpio" in registro, (
        "se habilitó la unidad del dueño pero no se levantó: hasta el próximo "
        "reinicio el gabinete sigue sin nadie sosteniendo los pines"
    )
    assert "systemctl restart takab-gpio" not in registro, (
        "el despliegue de todos los días REINICIÓ al dueño de los pines: eso es "
        "una actuación física sobre gas y retenedores en cada deploy, que es "
        "justo lo que D3 existe para eliminar"
    )
    assert gabinete.dueno_de_los_pines()["unit"] == "takab-gpio"


def test_un_gabinete_de_hoy_no_habilita_al_dueno_dedicado(gabinete) -> None:
    """LA NO-VACUIDAD del test de arriba, y el daño de habilitar a ciegas.

    Todo gabinete desplegado hasta hoy tiene `gpio_owner=edge` (el defecto): el
    dueño de los pines es `takab-edge`. Habilitar `takab-gpio` ahí deja DOS
    unidades reclamando el mismo cerrojo en el próximo arranque en frío, y como
    `takab-edge` declara `After=takab-gpio.service`, el que gana es el dedicado
    y `takab-edge` queda en crash-loop PARA SIEMPRE contra el cerrojo: sin nube,
    sin SeedLink y sin panel. Eléctricamente mudo (D1.1), operativamente ciego.
    """
    r = gabinete.desplegar()

    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    registro = gabinete.registro()
    assert "enable takab-gpio" not in registro, (
        "habilitó al dueño dedicado en un gabinete cuyo `edge.env` dice que el "
        "dueño es `takab-edge`: dos reclamantes del mismo cerrojo y un "
        "`takab-edge` en crash-loop tras el próximo reinicio"
    )
    assert "start takab-gpio" not in registro
    assert "systemctl restart takab-edge" in registro


def test_un_takab_gpio_habilitado_por_ERROR_se_deshabilita(gabinete) -> None:
    """La otra mitad de (c): el gabinete que volvió atrás y nadie lo deshabilitó.

    Un sitio que probó D3 y revirtió `TAKAB_EDGE_GPIO_OWNER` a `edge` se queda
    con la unidad del dueño dedicado HABILITADA. No pasa nada hasta el siguiente
    corte de luz; entonces arrancan las dos, gana `takab-gpio` (por el `After=`)
    y `takab-edge` cicla contra el cerrojo sin nube, sin SeedLink y sin panel.

    Deshabilitar es borrar un symlink: no toca un pin, no detiene nada y es
    idempotente. Detener al dueño NO se hace desde aquí — eso sí sería actuación
    física, y encima sobre el proceso que en ese momento puede tener los pines.
    """
    r = gabinete.desplegar(UNIDADES_HABILITADAS="takab-edge takab-gpio")

    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert "systemctl disable takab-gpio" in gabinete.registro(), (
        "`takab-gpio` quedó habilitada en un gabinete con el dueño en "
        "`takab-edge`: el próximo arranque en frío deja al supervisor en "
        "crash-loop y nadie lo dice"
    )
    assert "systemctl stop takab-gpio" not in gabinete.registro(), (
        "detener al dueño desde un despliegue es actuación física sobre gas y "
        "retenedores; deshabilitar basta y no mueve nada"
    )
    assert "⚠" in r.stderr, "y tiene que DECIRLO: un symlink corregido en silencio no enseña nada"


def test_el_dueno_de_los_pines_en_CODIGO_VIEJO_no_se_declara_bueno(gabinete) -> None:
    """(b), EL BLOQUEANTE. El ✓ que mentía.

    `takab-gpio` lleva días de pie; el despliegue le cambia el código BAJO LOS
    PIES (el venv es editable e in-place), reinicia al CLIENTE y el paso 7
    imprime `✓ pines del gabinete en poder de takab-gpio (pid N)`. Verde. El
    proceso que sostiene la sirena, el gas y los retenedores sigue ejecutando el
    código anterior indefinidamente — incluido el `Type=notify` que el
    `daemon-reload` escribió y no aplicó.

    Es el mismo defecto que D1.5 cerró para la VERIFICACIÓN, reabierto en el
    REINICIO: la comprobación mide un hecho verdadero («hay dueño») y lo reporta
    como el hecho que importa («el despliegue llegó al dueño»).
    """
    gabinete.provisionar(TAKAB_EDGE_GPIO_OWNER="gpio")
    pid = gabinete.dueno_preexistente("takab-gpio")
    # DECLARADO y no heredado del silencio del falso: este test mide el veredicto
    # ante un dueño cuyo código SÍ cambió, y eso tiene que decirlo el escenario.
    r = gabinete.desplegar(DUENO_CODIGO_CAMBIO="1")

    assert gabinete.dueno_de_los_pines()["pid"] == str(pid), (
        "premisa: los pines los sigue teniendo el proceso que ya estaba de pie "
        "ANTES del despliegue (el `start` de un dueño vivo es un no-op)"
    )
    assert r.returncode != 0, (
        "el dueño de los pines se quedó con el código anterior y el despliegue "
        f"salió en VERDE.\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "✓ pines del gabinete en poder" not in r.stdout, (
        "imprimió el ✓ del paso 7 midiendo a un proceso que no ejecuta lo que acabamos de desplegar"
    )
    assert "CÓDIGO ANTERIOR" in r.stderr
    # Y dice qué hacer, sin empujar a lo que hace daño: revertir también es
    # reiniciar, y reiniciar mueve GAS_VALVE y DOOR_RETAINER.
    assert "--ventana-de-mantenimiento" in r.stderr, (
        "el mensaje tiene que dar el camino sancionado (que reinicia al dueño "
        "bajo la MISMA verificación de propiedad), no mandar a teclear un "
        "`systemctl restart` a pelo"
    )
    assert "NO REVIERTAS" in r.stderr


def test_si_la_huella_del_dueno_NO_SE_PUEDE_MEDIR_el_gate_sale_rojo(gabinete) -> None:
    """Fail-closed: «no lo sé» no puede resolverse imprimiendo un ✓.

    El script lo dice en su comentario —«ante cualquier duda se asume CAMBIÓ»— y
    hasta ahora **ningún test lo ejercitaba a propósito**: se cumplía de rebote,
    porque el intérprete falso callaba por omisión y una carrera de un segundo
    decidía si el gate llegaba a preguntarle. Al hacer determinista el arnés esa
    cobertura accidental habría desaparecido en silencio, que es exactamente el
    modo en que una guarda se queda sin quien la vigile.

    Aquí el intérprete revienta (no imprime nada) con el dueño de pie desde antes
    del despliegue: el veredicto tiene que ser ROJO y tiene que decir que no pudo
    comparar, no inventarse un ✓ sobre el proceso que sostiene la sirena.
    """
    gabinete.provisionar(TAKAB_EDGE_GPIO_OWNER="gpio")
    gabinete.dueno_preexistente("takab-gpio")
    r = gabinete.desplegar(DUENO_HUELLA_MUDA="1")

    assert r.returncode != 0, (
        "no se pudo medir si el dueño de los pines corre el código nuevo y el "
        f"despliegue salió en VERDE.\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "no se pudo comparar" in r.stderr, (
        "salió rojo, sí, pero sin decir que la causa es que NO PUDO MEDIR: un "
        "operador no puede distinguirlo de un dueño realmente rancio"
    )
    assert "✓ pines del gabinete en poder" not in r.stdout


def test_un_dueno_de_pines_VIEJO_con_el_MISMO_codigo_no_obliga_a_ciclar_gas(gabinete) -> None:
    """El límite del gate de arriba, y lo que lo hace usable.

    Un gate que dijera «el dueño no se reinició ⇒ rojo» saldría rojo en TODOS los
    despliegues de un gabinete D3, porque el dueño no se reinicia nunca por
    diseño. Eso entrena al operador a ignorar el único rojo que importa — el
    daño de segundo orden que este mismo script ya documenta dos veces.

    Lo que se mide no es «¿se reinició?» sino «¿corre código distinto del que
    acabamos de poner?». La mayoría de los despliegues tocan el supervisor, la
    nube o el panel: el código del dueño de los pines no cambia y no hay nada
    que ciclar.
    """
    gabinete.provisionar(TAKAB_EDGE_GPIO_OWNER="gpio")
    gabinete.dueno_preexistente("takab-gpio")
    # Sin variables: «el código del dueño no cambió» es el default del arnés, y
    # aquí el dueño es además PREEXISTENTE, así que el gate llega a preguntar.
    r = gabinete.desplegar()

    assert r.returncode == 0, (
        "el código del dueño de los pines NO cambió en este despliegue y aun así "
        f"se declaró no verificado.\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "✓ pines del gabinete en poder de takab-gpio" in r.stdout
    assert "CÓDIGO ANTERIOR" not in r.stderr
    assert "systemctl restart takab-gpio" not in gabinete.registro(), (
        "no había nada que actualizar en el dueño y se le reinició igual: un "
        "ciclo de gas y retenedores gratis"
    )


def test_la_ventana_de_mantenimiento_reinicia_al_dueno_DESPUES_de_activar(gabinete) -> None:
    """El camino sancionado, con el edificio avisado — y el orden INVERTIDO por
    el layout A/B, que es un cambio de fondo y no de estilo.

    Antes el dueño iba PRIMERO, por el `After=takab-gpio.service` de
    `takab-edge`. Con A/B eso deja de ser correcto: el `ExecStart` del dueño
    resuelve por el MISMO symlink que el del cliente, así que reiniciarlo antes
    del repunte lo dejaría estrenando la versión VIEJA — un ciclo eléctrico de
    `GAS_VALVE` y `DOOR_RETAINER` a cambio de nada.

    Y va después del CANARY, no sólo del repunte: si la release nueva no
    sobrevive al remojo, la vuelta atrás ya ocurrió y no hay ninguna razón para
    tocar los pines. El coste físico sólo se paga cuando hay algo que estrenar.

    El reinicio va por AQUÍ y no a mano por SSH a propósito: así queda bajo la
    MISMA verificación de propiedad del paso 7, que es lo que dice si el dueño
    volvió a tomar los pines.
    """
    gabinete.provisionar(TAKAB_EDGE_GPIO_OWNER="gpio")
    gabinete.dueno_preexistente("takab-gpio")
    r = gabinete.desplegar("--ventana-de-mantenimiento", UNIDAD_DUENA="takab-gpio")

    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    registro = gabinete.registro()
    assert "systemctl restart takab-gpio" in registro, (
        "se declaró la ventana de mantenimiento y el dueño de los pines siguió "
        "con el código anterior"
    )
    assert registro.index("restart takab-gpio") > registro.index("restart takab-edge"), (
        "reinició al DUEÑO antes del repunte del symlink: habría estrenado la "
        "versión VIEJA y ciclado gas y retenedores a cambio de nada"
    )


def test_del_edge_env_gana_la_ULTIMA_asignacion_del_dueno(gabinete) -> None:
    """`EnvironmentFile=` tiene la semántica de siempre en esta casa: gana la
    última. Un `edge.env` con la clave repetida —el resultado natural de una
    fusión de `merge_env.py` sobre un archivo editado a mano— se leería al revés
    con un `grep | head -1`, y el despliegue habilitaría exactamente la unidad
    equivocada: la que deja al gabinete con dos reclamantes o sin ninguno.
    """
    gabinete.entorno.write_text(
        "TAKAB_EDGE_GATEWAY_ID=gw-falso-0001\n"
        "TAKAB_EDGE_GPIO_OWNER=edge\n"
        "TAKAB_EDGE_GPIO_OWNER=gpio\n"
    )
    r = gabinete.desplegar(UNIDAD_DUENA="takab-gpio")

    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert "systemctl enable takab-gpio" in gabinete.registro(), (
        "leyó la PRIMERA asignación de TAKAB_EDGE_GPIO_OWNER; systemd lee la "
        "última y el gabinete arranca con el dueño dedicado"
    )


def test_si_el_dueno_no_arranca_el_veredicto_lo_da_la_MEDICION_y_no_systemctl(
    gabinete,
) -> None:
    """Quién decide que un despliegue es malo.

    `systemctl start takab-gpio` puede salir != 0 por mil razones y el script
    corre bajo `set -euo pipefail`: dejar que abortara ahí cambiaría una
    comprobación MEDIDA —«¿quién sostiene el cerrojo?»— por el código de salida
    de un comando que sólo sabe decir «no arrancó», y encima dejaría al cliente
    sin activar.

    Así que se avisa y se sigue: quien dicta es la MEDICIÓN. [T-2.70] Ahora esa
    medición llega antes —es una de las cuatro señales del remojo del canary— y
    su desenlace es más fuerte: además de delatar, revierte.
    """
    gabinete.provisionar(TAKAB_EDGE_GPIO_OWNER="gpio")
    r = gabinete.desplegar(FALLA_START_GPIO="1", TAKAB_DEPLOY_PLAZO_PROPIEDAD="2")

    assert "systemctl restart takab-edge" in gabinete.registro(), (
        "abortó en el paso 6 por el código de salida de systemctl: el cliente se "
        "quedó sin activar la release nueva"
    )
    assert r.returncode != 0, "nadie tiene los pines y el despliegue salió en verde"
    veredicto = (gabinete.raiz.parent / "canary" / "veredicto.json").read_text()
    assert "cerrojo" in veredicto, (
        "el veredicto tiene que venir de MEDIR la propiedad, no del error de "
        f"systemctl.\nveredicto: {veredicto}\nstderr:\n{r.stderr}"
    )


# ---- D3·m5: sin identidad no se despliega ----------------------------------


def test_un_gabinete_SIN_identidad_no_llega_a_tocar_el_arbol_vivo(gabinete) -> None:
    """[T-2.70.a·D3·m5] `EnvironmentFile=` va SIN `-`, y esto lo hace visible.

    Las dos unidades exigen `/etc/takab/edge.env`: sin él no arrancan. Es la
    dirección correcta —un dueño de pines que arranca SIN identidad lo hace con
    el mapa de pines de `GpioPins` por defecto, o sea energizando los pines
    equivocados de un gabinete cableado, y encima con la unidad en verde— pero
    el despliegue no lo comprobaba: instalaba las unidades, reiniciaba, y el
    operador descubría el problema 45 s después con «NADIE reclamó los pines»,
    un diagnóstico que apunta al cerrojo en vez de al archivo que falta.

    Se comprueba en el PRE-VUELO, que es donde todavía no se ha destruido nada.
    """
    gabinete.entorno.unlink()
    r = gabinete.desplegar()

    assert r.returncode != 0, (
        "desplegó sobre un gabinete sin identidad: las dos unidades declaran "
        f"`EnvironmentFile=` sin `-` y ninguna arrancaría.\nstdout:\n{r.stdout}"
        f"\nstderr:\n{r.stderr}"
    )
    assert gabinete.centinela_intacto(), (
        "abortó DESPUÉS de destruir el árbol vivo: la comprobación de identidad "
        "tiene que correr en el pre-vuelo"
    )
    assert "systemctl restart" not in gabinete.registro()
    assert str(gabinete.entorno) in r.stderr, "el mensaje debe nombrar el archivo que falta"
    assert "provision_gateway.sh" in r.stderr, "y el script que lo instala"


# ---------------------------------------------------------------------------
# [T-2.70] La migración al layout A/B y la poda de releases
# ---------------------------------------------------------------------------


def test_migrar_un_gabinete_de_hoy_al_layout_AB_exige_ventana(gabinete) -> None:
    """Todo gabinete desplegado hasta esta ficha tiene `edge` como DIRECTORIO.
    Convertirlo en symlink cambia la ruta desde la que arrancan LAS DOS unidades
    —el camino de vida—, y entre el `mv` del directorio y el del symlink hay un
    hueco en que esa ruta no existe. Eso no se hace sin avisar al edificio.
    """
    gabinete.sin_migrar()
    r = gabinete.desplegar()

    assert r.returncode != 0
    assert "DIRECTORIO" in r.stderr and "ventana" in r.stderr
    assert not gabinete.vivo.is_symlink(), "migró pese a negarse"
    assert gabinete.centinela_intacto(), "el árbol vivo se tocó pese a abortar"
    assert "systemctl restart" not in gabinete.registro()


def test_la_migracion_conserva_el_arbol_heredado_como_release(gabinete) -> None:
    """La primera activación A/B de un gabinete necesita una vuelta atrás, y la
    única que puede tener es lo que ya estaba corriendo. Se conserva ENTERO —con
    su venv—, porque una release sin venv no es una vuelta atrás: es media.

    Es la misma lección que este script aprendió con `edge.prev`: no ofrecer una
    reversión que no existe.
    """
    gabinete.sin_migrar()
    r = gabinete.desplegar("--ventana-de-mantenimiento")

    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert gabinete.vivo.is_symlink(), "tras migrar, la ruta de arranque debe ser el symlink"
    heredadas = sorted(gabinete.releases.glob("heredada-*"))
    assert len(heredadas) == 1, f"se esperaba UNA release heredada: {heredadas}"
    heredada = heredadas[0] / "edge"
    assert (heredada / _CENTINELA).exists(), "la heredada debe ser el árbol ANTERIOR"
    assert (heredada / ".venv" / "bin" / "python").exists(), (
        "sin su venv la release heredada no sirve como vuelta atrás"
    )
    assert not (gabinete.raiz / "edge.premigracion").exists(), (
        "el original duplicado tiene que desaparecer: una microSD no aguanta dos copias"
    )


def test_la_poda_jamas_borra_la_release_activa_ni_la_anterior(gabinete) -> None:
    """Un gabinete con microSD no puede acumular releases con su venv, pero una
    poda que se llevara la activa o la anterior convertiría la limpieza en el
    defecto que el canary existe para evitar: una actualización sin vuelta atrás.
    """
    # Con mtimes ANTIGUOS de verdad: la poda ordena por fecha de modificación,
    # así que cuatro directorios creados en el mismo instante que la release
    # anterior dejaban el orden al azar y el test parpadeaba.
    for i in range(4):
        vieja = gabinete.releases / f"20250101T00000{i}Z-vieja" / "edge"
        vieja.mkdir(parents=True)
        os.utime(vieja.parent, (1_700_000_000 + i, 1_700_000_000 + i))

    r = gabinete.desplegar(TAKAB_DEPLOY_RELEASES_VIVAS="2")

    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert gabinete.vivo.resolve().exists(), "la poda se llevó la release ACTIVA"
    assert (gabinete.release_previa / _CENTINELA).exists(), (
        "la poda se llevó la release ANTERIOR: el gabinete se quedó sin vuelta atrás"
    )
    assert sorted(gabinete.releases.glob("*vieja")) == [], "la poda no llegó a las antiguas"


def test_un_venv_cuyo_interprete_ProtectHome_esconde_NO_se_activa(gabinete, tmp_path) -> None:
    """[T-2.70 · CAMPO 2026-08-23] EL GATE QUE FALTABA, y que costó un edificio
    sin sirena.

    Las dos unidades declaran `ProtectHome=true`: para ellas `/home`, `/root` y
    `/run/user` NO EXISTEN. Un venv cuyo `bin/python` resuelve ahí arranca
    perfectamente desde una sesión ssh —que es donde corren los otros tres
    gates— y muere con **203/EXEC** cuando lo lanza systemd: el ejecutable
    existe, el que no existe en ese namespace es su intérprete.

    Pasó de verdad la primera noche del layout A/B: hasta entonces el venv del Pi
    era UNO y se reusaba desde julio, con su intérprete fuera de `/home` porque
    alguien exportó `UV_PYTHON_INSTALL_DIR` a mano aquella vez — un hecho que
    vivía en un directorio y en ningún archivo. Con A/B cada release estrena
    venv, `uv` eligió intérprete por primera vez en meses y se lo puso en `$HOME`.

    El sandbox no puede montar un `/home` de mentira, así que se le apunta el
    gate a un prefijo suyo. Que el DEFAULT siga siendo los tres reales lo ancla
    `test_deploy_artifacts.py`.
    """
    escondido = tmp_path / "escondido"
    escondido.mkdir(exist_ok=True)

    r = gabinete.desplegar(
        TAKAB_DEPLOY_RUTAS_OCULTAS=str(escondido),
        VENV_PYTHON_EN=str(escondido / "python3.12"),
    )

    assert r.returncode != 0, "activó un venv que systemd no puede ejecutar"
    assert "NO pueden verlo" in r.stderr
    assert "ProtectHome" in r.stderr
    assert gabinete.centinela_intacto(), "el gabinete debe seguir en la release anterior"
    assert "systemctl restart" not in gabinete.registro(), "reinició pese a fallar el gate"


def test_la_poda_JAMAS_se_lleva_la_release_heredada(gabinete) -> None:
    """[T-2.70 · CAMPO 2026-08-23] La recencia es el criterio equivocado para
    la heredada, y costó la red de seguridad la misma noche del estreno.

    Es el árbol que el gabinete llevaba corriendo ANTES del layout A/B: meses de
    operación real detrás y la única versión de la que se sabe que ese edificio
    sobrevive a un corte de luz. Todas las releases nuevas son, por definición,
    más recientes, así que una poda por fecha se la lleva la primera — y así el
    gabinete se quedó con tres releases del mismo día y ninguna con historia.
    """
    import os

    heredada = gabinete.releases / "heredada-20250101T000000Z" / "edge"
    heredada.mkdir(parents=True)
    os.utime(heredada.parent, (1_600_000_000, 1_600_000_000))  # la MÁS antigua
    for i in range(3):
        otra = gabinete.releases / f"20250601T00000{i}Z-vieja" / "edge"
        otra.mkdir(parents=True)
        os.utime(otra.parent, (1_700_000_000 + i, 1_700_000_000 + i))

    r = gabinete.desplegar(TAKAB_DEPLOY_RELEASES_VIVAS="1")

    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    assert heredada.exists(), "la poda se llevó la única release con historia real"
    assert sorted(gabinete.releases.glob("*vieja")) == [], (
        "premisa: la poda SÍ tenía que llevarse las otras antiguas"
    )
