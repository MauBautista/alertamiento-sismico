"""`deploy/edge/canary.sh` CORRIDO DE VERDAD contra un gabinete de mentira (T-2.70).

Mismo patrón que `test_deploy_sh.py`, y por la misma razón: un test que leyera el
texto del script comprobaría que las palabras están, no que el gabinete vuelve
atrás. Aquí se monta un `/opt/takab` falso en un `tmp_path` con su layout A/B
(`releases/<id>/` + symlink `edge`), se ponen `systemctl`/`curl` falsos en el
PATH y se ejecuta el script; los asertos miran DÓNDE quedó apuntando el symlink,
QUÉ unidades se tocaron y CON QUÉ código salió.

Lo que el `systemctl` falso modela, que es lo que hace útil al arnés:

* `restart takab-edge` **lanza un proceso de verdad** que toma el cerrojo del
  GPIO cuando el `edge.env` dice que el dueño es `edge`, y NO lo toma cuando dice
  `gpio` — igual que el arnés de `deploy.sh`. Sin eso, «el gabinete protege» no
  se podría distinguir de «la unidad está arriba».
* `show -p MainPID` sale de un archivo que el falso actualiza. Es lo que permite
  montar el escenario que la ficha exige y que `systemctl is-active` no ve:
  **arranca y crashea al segundo 4**, con la unidad `active` todo el rato y el
  PID relevándose por debajo.
* La avería se declara POR RELEASE (`RELEASE_MALA`, `RELEASE_PANEL_MUDO`,
  `RELEASE_QUE_CICLA`) y no por gabinete. Es lo que permite medir lo único que
  esta ficha existe para probar: que volver a la versión anterior CURA. Con una
  avería global el rollback «fallaba» siempre y los tests medirían el arnés.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import signal
import subprocess

import pytest

_CANARY = pathlib.Path(__file__).resolve().parents[2] / "deploy" / "edge" / "canary.sh"


def _ejecutable(ruta: pathlib.Path, cuerpo: str) -> None:
    ruta.write_text("#!/usr/bin/env bash\n" + cuerpo.strip() + "\n")
    ruta.chmod(0o755)


@pytest.fixture
def gabinete(tmp_path: pathlib.Path):
    """Un `/opt/takab` de mentira con layout A/B y los binarios falsos."""
    raiz = tmp_path / "opt-takab"
    releases = raiz / "releases"
    estado = tmp_path / "estado"
    binarios = tmp_path / "bin"
    for d in (releases, estado, binarios, raiz / "bin"):
        d.mkdir(parents=True, exist_ok=True)

    cerrojo = tmp_path / "gpio.lock"
    mainpid = estado / "mainpid"
    bitacora = estado / "systemctl.log"
    pid_dueno = estado / "pid_dueno"
    entorno = tmp_path / "edge.env"
    entorno.write_text("TAKAB_EDGE_GATEWAY_ID=gw-falso-0001\nTAKAB_EDGE_GPIO_OWNER=gpio\n")

    def crear_release(nombre: str, *, completa: bool = True) -> pathlib.Path:
        """El layout REAL de una release: `<id>/edge/` (con su venv y su
        FW_VERSION) junto a `<id>/shared/schemas/`. El symlink apunta al
        subdirectorio `edge`, no a la release — ver la nota de `canary.sh`."""
        d = releases / nombre / "edge"
        (d / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
        (releases / nombre / "shared" / "schemas").mkdir(parents=True, exist_ok=True)
        if completa:
            _ejecutable(d / ".venv" / "bin" / "takab-edge", "exec sleep 600")
        (d / "FW_VERSION").write_text(nombre + "\n")
        return d

    # `systemctl` falso. Cada invocación queda en la bitácora: es lo que permite
    # ANCLAR que este script no reinicia jamás al dueño de los pines.
    #
    # LA AVERÍA ES DE LA RELEASE, NO DEL GABINETE. Los dobles miran a dónde
    # apunta el symlink ANTES de decidir si fallan (`RELEASE_MALA`,
    # `RELEASE_PANEL_MUDO`, `RELEASE_QUE_CICLA`). Un doble que fallara de forma
    # global no podría modelar lo único que esta ficha existe para probar: que
    # volver a la versión anterior CURA. Con la avería global, el rollback
    # «fallaba» siempre y los tests medían el arnés en vez del script.
    _ejecutable(
        binarios / "systemctl",
        f"""
        echo "systemctl $*" >> "{bitacora}"
        # El symlink apunta a `<id>/edge`: el id es el componente ANTERIOR.
        ACTIVA="$(readlink "{raiz}/edge" 2>/dev/null || true)"
        ACTIVA="${{ACTIVA%/edge}}"
        ACTIVA="${{ACTIVA##*/}}"

        if [ "$1" = show ]; then
          # RELEASE_SIN_INTERPRETE: la unidad arranca (`Type=simple` da por buena
          # la unidad en el fork) y el exec muere en el hijo — 203/EXEC. systemd
          # la reporta `active` y con MainPID=0. Es lo que pasó en el gabinete la
          # primera noche del layout A/B.
          if [ -n "${{RELEASE_SIN_INTERPRETE:-}}" ] \
             && [ "$ACTIVA" = "${{RELEASE_SIN_INTERPRETE}}" ]; then
            echo 0; exit 0
          fi
          cat "{mainpid}" 2>/dev/null || echo 0
          exit 0
        fi

        if [ "$1" = is-active ]; then
          if [ "$2" = takab-edge ] && [ -n "${{RELEASE_MALA:-}}" ] \\
             && [ "$ACTIVA" = "${{RELEASE_MALA}}" ]; then
            echo inactive; exit 3
          fi
          case " ${{UNIDADES_VIVAS:-takab-edge takab-gpio}} " in
            *" $2 "*) echo active; exit 0 ;;
          esac
          echo inactive; exit 3
        fi

        if [ "$1" = restart ] && [ "$2" = takab-edge ]; then
          if [ -n "${{RELEASE_MALA:-}}" ] && [ "$ACTIVA" = "${{RELEASE_MALA}}" ]; then
            # La unidad no levanta: systemd la deja en `failed` y sin MainPID.
            echo 0 > "{mainpid}"
            exit 1
          fi
          # ¿Este proceso reclama los pines? Lo decide el edge.env del gabinete,
          # con la misma semántica de «gana la última» que systemd — y con un
          # lector INDEPENDIENTE del que usa canary.sh, para medir el script
          # contra el gabinete y no contra sí mismo.
          DUENO_CFG="$(sed -n 's/^ *TAKAB_EDGE_GPIO_OWNER=//p' \\
            "${{TAKAB_EDGE_ENV_FILE:-/dev/null}}" 2>/dev/null | tail -1 || true)"
          if [ "$DUENO_CFG" != gpio ]; then
            # takab-edge ES el dueño: reiniciarlo SUELTA el cerrojo y lo retoma.
            if [ -s "{pid_dueno}" ]; then
              kill -9 "$(cat "{pid_dueno}")" 2>/dev/null || true
              for _ in 1 2 3 4 5 6 7 8 9 10; do
                flock -n "{cerrojo}" true && break
                sleep 0.05
              done
            fi
            (
              exec 9<>"{cerrojo}"
              flock -n 9 || exit 1
              echo "$BASHPID" > "{pid_dueno}"
              printf 'pid=%s\\nunit=takab-edge\\n' "$BASHPID" >> "{cerrojo}"
              echo "$BASHPID" > "{mainpid}"
              exec sleep 600
            ) </dev/null >/dev/null 2>&1 &
            sleep 0.3
          else
            # Gabinete D3: el cliente arranca y NO toca un pin.
            echo $((RANDOM + 20000)) > "{mainpid}"
          fi
          if [ -n "${{RELEASE_QUE_CICLA:-}}" ] && [ "$ACTIVA" = "${{RELEASE_QUE_CICLA}}" ]; then
            # CRASH-LOOP: la unidad sigue `active`, pero systemd repone el
            # proceso. Es el escenario que `is-active` no puede ver.
            ( sleep "${{CICLA_TRAS:-3}}"; echo $((RANDOM + 40000)) > "{mainpid}" ) \\
              </dev/null >/dev/null 2>&1 &
          fi
          exit 0
        fi
        exit 0
        """,
    )

    _ejecutable(
        binarios / "curl",
        f"""
        # El symlink apunta a `<id>/edge`: el id es el componente ANTERIOR.
        ACTIVA="$(readlink "{raiz}/edge" 2>/dev/null || true)"
        ACTIVA="${{ACTIVA%/edge}}"
        ACTIVA="${{ACTIVA##*/}}"
        if [ -n "${{RELEASE_PANEL_MUDO:-}}" ] && [ "$ACTIVA" = "${{RELEASE_PANEL_MUDO}}" ]; then
          exit 22
        fi
        echo '{{"ok":true}}'
        """,
    )

    # `flock` falso: delega SIEMPRE en el real salvo para simular la rama que no
    # es ni 0 (libre) ni 9 (tomado) — «no se pudo interrogar el cerrojo». El
    # discriminante es `-E`, que sólo usa la INTERROGACIÓN de canary.sh; la toma
    # del cerrojo del systemctl falso (`flock -n 9`) sigue yendo al binario real
    # con su fd 9 heredado a través de este envoltorio.
    _ejecutable(
        binarios / "flock",
        f"""
        if [ -n "${{CERROJO_ILEGIBLE:-}}" ] && [ "$1" = -n ] && [ "$2" = -E ]; then
          exit 5
        fi
        exec {shutil.which("flock")} "$@"
        """,
    )

    for real in ("sleep", "date", "sed", "cat", "ln", "mv", "readlink", "tr", "mkdir"):
        camino = shutil.which(real)
        if camino:
            (binarios / real).symlink_to(camino)

    class Gabinete:
        def __init__(self) -> None:
            self.raiz = raiz
            self.releases = releases
            self.estado = estado
            self.cerrojo = cerrojo
            self.mainpid = mainpid
            self.bitacora = bitacora
            self.entorno = entorno
            self.vivo = raiz / "edge"
            self.crear_release = crear_release

        def dueno_gpio_vivo(self) -> None:
            """Arranca un `takab-gpio` falso que se queda con los pines."""
            proc = subprocess.Popen(
                [
                    "bash",
                    "-c",
                    f'exec 9<>"{cerrojo}"; flock -n 9 || exit 1; '
                    f'echo "$BASHPID" > "{pid_dueno}"; '
                    f'printf \'pid=%s\\nunit=takab-gpio\\n\' "$BASHPID" >> "{cerrojo}"; '
                    f"exec sleep 600",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._dueno = proc
            import time

            time.sleep(0.4)

        def apuntar(self, nombre: str) -> None:
            destino = releases / nombre / "edge"
            if self.vivo.is_symlink() or self.vivo.exists():
                self.vivo.unlink()
            self.vivo.symlink_to(destino)

        def correr(self, *args: str, **entorno_extra: str):
            env = dict(os.environ)
            env["PATH"] = f"{binarios}:{env['PATH']}"
            env["TAKAB_REMOTE_ROOT"] = str(raiz)
            env["TAKAB_EDGE_GPIO_LOCK_PATH"] = str(cerrojo)
            env["TAKAB_EDGE_ENV_FILE"] = str(entorno)
            env["TAKAB_CANARY_ESTADO"] = str(estado / "canary")
            env["TAKAB_CANARY_PLAZO_ARRANQUE"] = "4"
            env["TAKAB_CANARY_REMOJO"] = "6"
            env["TAKAB_CANARY_INTERVALO"] = "1"
            env["TAKAB_CANARY_PANEL"] = "http://127.0.0.1:8080/api/status"
            env.update(entorno_extra)
            return subprocess.run(
                ["bash", str(_CANARY), *args],
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )

        def veredicto(self) -> dict:
            return json.loads((estado / "canary" / "veredicto.json").read_text())

        def systemctl_log(self) -> str:
            return bitacora.read_text() if bitacora.exists() else ""

        def apuntando_a(self) -> str:
            return os.readlink(self.vivo) if self.vivo.is_symlink() else ""

    g = Gabinete()
    g._dueno = None  # type: ignore[attr-defined]
    yield g
    for archivo in (pid_dueno,):
        if archivo.exists():
            try:
                os.kill(int(archivo.read_text().strip()), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass
    if getattr(g, "_dueno", None) is not None:
        g._dueno.kill()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# El camino feliz, y el que la ficha exige que NO salga feliz
# ---------------------------------------------------------------------------


def test_una_release_sana_se_activa_y_sobrevive_al_remojo(gabinete) -> None:
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")
    gabinete.dueno_gpio_vivo()

    r = gabinete.correr("activar", "v2")

    assert r.returncode == 0, r.stderr
    assert gabinete.apuntando_a().endswith("/v2/edge")
    assert gabinete.veredicto()["resultado"] == "ok"


def test_el_que_arranca_y_crashea_al_rato_NO_se_declara_bueno(gabinete) -> None:
    """El defecto exacto que `systemctl is-active` no puede ver.

    Fichado en T-2.70.a, refinamiento 3: «un proceso que arranca y crashea al
    segundo 4 se reporta como despliegue exitoso, y con `Restart=always` el
    gabinete queda ciclando mientras el operador se va del sitio». Aquí la
    unidad está `active` de principio a fin y el panel contesta: lo único que
    delata el ciclo es el relevo del MainPID durante el remojo.
    """
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")
    gabinete.dueno_gpio_vivo()

    r = gabinete.correr("activar", "v2", RELEASE_QUE_CICLA="v2", CICLA_TRAS="3")

    assert r.returncode == 1, r.stdout + r.stderr
    assert "crash-loop" in r.stderr
    assert gabinete.apuntando_a().endswith("/v1/edge"), "no volvió a la release anterior"
    v = gabinete.veredicto()
    assert v["resultado"] == "revertido"
    assert "crash-loop" in v["razon"]


def test_una_release_que_no_levanta_vuelve_atras_sola(gabinete) -> None:
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")
    gabinete.dueno_gpio_vivo()

    r = gabinete.correr("activar", "v2", RELEASE_MALA="v2")

    assert r.returncode == 1
    assert gabinete.apuntando_a().endswith("/v1/edge")
    assert gabinete.veredicto()["resultado"] == "revertido"


def test_el_panel_mudo_cuenta_como_enfermo(gabinete) -> None:
    """Arrancar no es servir: un supervisor vivo con el panel mudo no es un
    gabinete operable, y el operador no puede verlo desde `is-active`."""
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")
    gabinete.dueno_gpio_vivo()

    r = gabinete.correr("activar", "v2", RELEASE_PANEL_MUDO="v2")

    assert r.returncode == 1
    assert "panel" in r.stderr
    assert gabinete.apuntando_a().endswith("/v1/edge")
    assert gabinete.veredicto()["resultado"] == "revertido"


def test_sin_dueno_de_los_pines_ni_la_vuelta_atras_salva_el_gabinete(gabinete) -> None:
    """El cerrojo LIBRE es «el gabinete no protege», y eso no se declara ✓
    aunque la unidad esté arriba y el panel conteste.

    Y el desenlace importa tanto como el diagnóstico: en un gabinete D3 los
    pines los sostiene `takab-gpio`, una unidad que este script NO reinicia, así
    que volver a la release anterior no puede curar esto. El script revierte
    igual —es lo único que sabe hacer— y entonces dice la verdad incómoda con
    todas las letras: esto ya no es la actualización, es el gabinete. Sale con
    un código propio (3) para que quien llame no lo confunda con un rollback
    normal y mande a alguien al sitio.
    """
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")
    # Nadie toma el cerrojo: `dueno_gpio_vivo()` NO se llama a propósito.
    gabinete.cerrojo.write_text("")

    r = gabinete.correr("activar", "v2")

    assert r.returncode == 3, r.stdout + r.stderr
    assert "LIBRE" in r.stderr
    assert "es el gabinete" in r.stderr
    assert gabinete.apuntando_a().endswith("/v1/edge")
    assert gabinete.veredicto()["resultado"] == "revertido_sin_salud"


# ---------------------------------------------------------------------------
# «No pude medir» no es «está roto»
# ---------------------------------------------------------------------------


def test_lo_que_no_se_pudo_medir_NO_dispara_una_vuelta_atras(gabinete) -> None:
    """Revertir es reiniciar, y reiniciar cuesta una ventana sin sirena.

    `flock` saliendo con un código que no es ni 0 (libre) ni 9 (tomado) no dice
    nada sobre la salud del gabinete: dice que no se pudo interrogar el cerrojo
    —falta util-linux, /var/lib/takab no existe, el kernel va endurecido—. El
    script deja la release puesta, sale 2 y lo GRITA, pero no cicla el edificio
    por un dato que nadie leyó. Es la misma distinción que `deploy.sh` hace en
    su rama `ilegible`, y el daño que evita es de segundo orden: un falso rojo
    empuja al operador a revertir, y revertir mueve gas y retenedores.
    """
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")
    gabinete.dueno_gpio_vivo()

    r = gabinete.correr("activar", "v2", CERROJO_ILEGIBLE="1")

    assert r.returncode == 2, r.stdout + r.stderr
    assert "NO VERIFICADA" in r.stderr
    assert gabinete.apuntando_a().endswith("/v2/edge"), "no debía revertir"
    assert gabinete.veredicto()["resultado"] == "no_medible"
    assert gabinete.systemctl_log().count("restart") == 1, "revirtió pese a no haber medido"


# ---------------------------------------------------------------------------
# Las guardas físicas
# ---------------------------------------------------------------------------


def test_jamas_se_reinicia_al_dueno_de_los_pines(gabinete) -> None:
    """Regla de oro 4. Reiniciar `takab-gpio` cicla GAS_VALVE y DOOR_RETAINER
    (2 transiciones por pin, medidas) y abre una ventana sin sirena. Ninguna
    rama de este script —ni activar, ni revertir— puede nombrarlo."""
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")
    gabinete.dueno_gpio_vivo()

    # El camino que MÁS reinicia: activa, cicla, revierte y vuelve a arrancar.
    gabinete.correr("activar", "v2", RELEASE_QUE_CICLA="v2", CICLA_TRAS="3")

    registro = gabinete.systemctl_log()
    assert "restart takab-edge" in registro
    assert "takab-gpio" not in registro, registro


def test_en_un_gabinete_sin_dueno_dedicado_activar_exige_ventana(gabinete) -> None:
    """Con `TAKAB_EDGE_GPIO_OWNER=edge` —el estado de todo gabinete desplegado
    hasta el 2026-08-16— reiniciar `takab-edge` ES reiniciar al dueño de los
    pines. Eso no se hace a espaldas del edificio."""
    gabinete.entorno.write_text("TAKAB_EDGE_GPIO_OWNER=edge\n")
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")

    r = gabinete.correr("activar", "v2")

    assert r.returncode == 1
    assert "ventana" in r.stderr
    assert gabinete.apuntando_a().endswith("/v1/edge"), "el symlink se tocó pese a la negativa"
    assert "restart" not in gabinete.systemctl_log()


def test_con_la_ventana_declarada_el_mismo_gabinete_sí_activa(gabinete) -> None:
    gabinete.entorno.write_text("TAKAB_EDGE_GPIO_OWNER=edge\n")
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")

    r = gabinete.correr("activar", "v2", "--ventana-de-mantenimiento")

    assert r.returncode == 0, r.stderr
    assert gabinete.apuntando_a().endswith("/v2/edge")


def test_un_gabinete_sin_migrar_al_layout_AB_no_se_toca(gabinete) -> None:
    """`${RAIZ}/edge` como DIRECTORIO de verdad es el layout de antes de esta
    ficha. Repuntar ahí borraría el árbol vivo; se niega y lo dice."""
    gabinete.crear_release("v2")
    (gabinete.raiz / "edge").mkdir()
    (gabinete.raiz / "edge" / "FW_VERSION").write_text("antiguo\n")

    r = gabinete.correr("activar", "v2")

    assert r.returncode == 1
    assert "symlink" in r.stderr
    assert (gabinete.raiz / "edge" / "FW_VERSION").read_text() == "antiguo\n"


def test_una_release_sin_ejecutable_no_se_activa(gabinete) -> None:
    """Activar una release incompleta no es un despliegue malo: es apagar el
    gabinete. Se comprueba ANTES de repuntar nada."""
    gabinete.crear_release("v1")
    gabinete.crear_release("rota", completa=False)
    gabinete.apuntar("v1")

    r = gabinete.correr("activar", "rota")

    assert r.returncode == 1
    assert gabinete.apuntando_a().endswith("/v1/edge")
    assert "restart" not in gabinete.systemctl_log()


def test_sin_release_anterior_el_fallo_se_declara_sin_vuelta(gabinete) -> None:
    """La misma honestidad que `deploy.sh` aplica a `edge.prev`: no se ofrece
    una vuelta atrás que no existe, y el operador se entera ANTES de irse."""
    gabinete.crear_release("v1")
    gabinete.dueno_gpio_vivo()  # hay dueño, pero no hay release previa

    r = gabinete.correr("activar", "v1", RELEASE_PANEL_MUDO="v1")

    assert r.returncode == 1
    assert "NO HAY VUELTA ATRÁS" in r.stderr
    assert gabinete.veredicto()["resultado"] == "sin_vuelta"


def test_repuntar_no_anida_ni_deja_restos_dentro_de_las_releases(gabinete) -> None:
    """La trampa del `mv` SIN `-T`: el destino es un symlink A DIRECTORIO, así
    que `mv` lo sigue y deja el temporal DENTRO de la release activa. El
    symlink se queda apuntando a lo de antes y el despliegue se declara hecho
    sobre código que nadie activó.

    El aserto mira el temporal por su nombre real (`edge.nuevo`) porque la
    primera versión de este test buscaba un nombre que ese camino no crea nunca
    y por eso pasaba en verde con la `-T` quitada.
    """
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")
    gabinete.dueno_gpio_vivo()

    gabinete.correr("activar", "v2")

    assert gabinete.vivo.is_symlink()
    assert gabinete.apuntando_a().endswith("/v2/edge")
    restos = [p for p in gabinete.raiz.rglob("edge.nuevo")]
    assert restos == [], f"quedaron temporales del repunte: {restos}"


# ---------------------------------------------------------------------------
# Reversión ordenada (la que un comando firmado de la nube acabará pidiendo)
# ---------------------------------------------------------------------------


def test_revertir_a_mano_usa_el_veredicto_que_dejo_la_activacion(gabinete) -> None:
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")
    gabinete.dueno_gpio_vivo()
    assert gabinete.correr("activar", "v2").returncode == 0

    r = gabinete.correr("revertir", "--motivo", "el SOC vio latencias raras")

    assert r.returncode == 1, r.stdout + r.stderr
    assert gabinete.apuntando_a().endswith("/v1/edge")
    v = gabinete.veredicto()
    assert v["resultado"] == "revertido"
    assert v["razon"] == "el SOC vio latencias raras"


def test_estado_habla_aunque_nunca_se_haya_activado_nada(gabinete) -> None:
    gabinete.crear_release("v1")
    gabinete.apuntar("v1")

    r = gabinete.correr("estado")

    assert r.returncode == 0
    assert json.loads(r.stdout)["resultado"] == "sin_datos"


def test_activar_lo_ya_activo_es_un_no_op_que_no_reinicia_nada(gabinete) -> None:
    """Idempotencia: re-ordenar la versión que ya corre no puede costar un
    reinicio. Con el dueño en `takab-edge` ese reinicio sería, además, un ciclo
    eléctrico de gas y retenedores por nada."""
    gabinete.crear_release("v1")
    gabinete.apuntar("v1")

    r = gabinete.correr("activar", "v1")

    assert r.returncode == 0
    assert "restart" not in gabinete.systemctl_log()
    assert gabinete.veredicto()["resultado"] == "ya_activa"


# ---------------------------------------------------------------------------
# [T-2.70 · CAMPO 2026-08-23] Lo que pasó en el gabinete de verdad
# ---------------------------------------------------------------------------


def test_una_unidad_ACTIVA_sin_proceso_principal_es_una_medicion_MALA(gabinete) -> None:
    """EL DEFECTO QUE COSTÓ UN EDIFICIO SIN SIRENA, reproducido.

    La primera noche del layout A/B, el `ExecStart` de las dos unidades apuntaba
    a un venv cuyo intérprete `ProtectHome=true` esconde: el exec moría con
    **203/EXEC**. Con `Type=simple` systemd da la unidad por arrancada en el fork
    —`is-active` dice `active`— y el fallo llega en el hijo, dejando `MainPID=0`.

    El canary leía ese `0` como «no pude preguntar», dejaba la release puesta y
    salía con «ACTIVACIÓN NO VERIFICADA». Resultado medido: el gabinete se quedó
    sin dueño de pines —sin sirena, sin cierre de gas, sin retenedores— con las
    dos unidades ciclando, hasta que alguien lo miró.

    «Activa y sin proceso principal» no es la ausencia de un dato: es el retrato
    de un `ExecStart` que no llegó a ejecutarse. Se mide, y se revierte.
    """
    gabinete.crear_release("v1")
    gabinete.crear_release("v2")
    gabinete.apuntar("v1")
    gabinete.dueno_gpio_vivo()

    r = gabinete.correr("activar", "v2", RELEASE_SIN_INTERPRETE="v2")

    assert r.returncode == 1, r.stdout + r.stderr
    assert "MainPID=0" in r.stderr
    assert "ExecStart" in r.stderr
    assert gabinete.apuntando_a().endswith("/v1/edge"), "no volvió a la release anterior"
    v = gabinete.veredicto()
    assert v["resultado"] == "revertido"
    assert "NO VERIFICADA" not in r.stderr, (
        "lo trató como «no pude medir»: eso es lo que dejó el gabinete roto"
    )
