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

import os
import pathlib
import shutil
import subprocess
import textwrap

import pytest

_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_DEPLOY = _RAIZ / "deploy" / "edge" / "deploy.sh"

#: Marca que se siembra en el árbol vivo antes de desplegar. Si sigue ahí, el
#: árbol vivo NO se tocó; si desapareció, el `rsync --delete` ya pasó por encima.
_CENTINELA = "CODIGO_ANTERIOR.txt"


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
    _escribir_ejecutable(
        binarios / "uv",
        f"""
        echo "uv $*" >> "{bitacora}"
        mkdir -p .venv/bin
        [ -x .venv/bin/python ] || cp "{plantilla_py}" .venv/bin/python
        : > .venv/bin/takab-edge && chmod +x .venv/bin/takab-edge
        : > .venv/bin/takab-gpio && chmod +x .venv/bin/takab-gpio
        """,
    )

    _escribir_ejecutable(binarios / "sudo", f'echo "sudo $*" >> "{bitacora}"')  # NO ejecuta
    _escribir_ejecutable(
        binarios / "systemctl",
        f'echo "systemctl $*" >> "{bitacora}"; [ "$1" = is-active ] && echo active; exit 0',
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

    return Gabinete()


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
