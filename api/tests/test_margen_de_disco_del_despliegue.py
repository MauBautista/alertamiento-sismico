"""[T-7.46] El guardia de disco del despliegue se EJECUTA aquí, no se lee.

`deploy/cloud/margen-y-poda.sh` corre dentro de la instancia, por SSM, donde
nadie lo mira hasta que falla. Y en este repositorio **no hay gate de
shellcheck** (`grep -rn shellcheck Makefile .github/workflows/` no devuelve
nada), así que esta suite es la única cosa que va a leer ese bash antes de que
decida si un despliegue sigue o se para.

Se corre el script DE VERDAD, con `df` y `docker` falsos al principio del `PATH`.
Es el patrón que `edge/tests/test_canary_sh.py` ya usa con el canary del Pi: un
`strcontains` sobre el texto acredita que la cadena está escrita, no que el bash
funcione — y el defecto que trajo esta ficha vivía justamente en lo que nadie
ejecutaba.

Lo que fija, por orden de lo que costaría equivocarse:

1. **La poda jamás se lleva lo que la instancia está sirviendo**, ni siquiera con
   el stack abajo. Es el modo de fallo por el que `docker image prune -a` a secas
   está prohibido aquí: ese comando sólo perdona lo que tiene un contenedor
   encima.
2. **La ventana no es de TIEMPO.** La recencia como criterio ya se midió mal en
   campo (`deploy/edge/deploy.sh`: la poda por fecha se llevó la release heredada
   la misma noche del estreno). El apaño que se tecleó a mano el 2026-09-16
   —`--filter until=336h`— no puede volver al script por un arreglo apresurado.
3. **No se puede decir `ok` sin haber medido.** Un `df` que no contesta aborta;
   nunca sale la línea de éxito.
4. **El margen se comprueba antes de que nada baje una imagen y antes de pisar
   `deploy.env`**, que es lo que hace que abortar deje la instancia intacta.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "deploy" / "cloud" / "margen-y-poda.sh"
DEPLOY = RAIZ / "deploy" / "cloud" / "deploy.sh"
REGISTRY = "634882473845.dkr.ecr.us-east-2.amazonaws.com"

GIB = 1024**3

#: Lo que el `docker images` falso devuelve por defecto: la que corre, una
#: anterior y cinco viejas. Ordenadas de más nueva a más vieja por `CreatedAt`,
#: que es como las ordena el script.
IMAGENES = [
    ("2026-09-16 00:00:00 +0000 UTC", f"{REGISTRY}/takab/cloud:a986a62"),
    ("2026-09-15 00:00:00 +0000 UTC", f"{REGISTRY}/takab/cloud:9a01278"),
    ("2026-09-14 00:00:00 +0000 UTC", f"{REGISTRY}/takab/cloud:f99b7e0"),
    ("2026-09-13 00:00:00 +0000 UTC", f"{REGISTRY}/takab/cloud:41ccc36"),
    ("2026-09-12 00:00:00 +0000 UTC", f"{REGISTRY}/takab/cloud:88805d0"),
    ("2026-09-11 00:00:00 +0000 UTC", f"{REGISTRY}/takab/cloud:af5c1d6"),
    ("2026-09-16 00:00:00 +0000 UTC", f"{REGISTRY}/takab/console:a986a62"),
    ("2026-09-11 00:00:00 +0000 UTC", f"{REGISTRY}/takab/console:af5c1d6"),
]


def _falsos(
    tmp: Path,
    *,
    libres_antes: int,
    libres_despues: int,
    corriendo: list[str],
    imagenes: list[tuple[str, str]] | None = None,
    df_roto: bool = False,
    rmi_falla: str | None = None,
    sin_data_root: bool = False,
) -> Path:
    """Un `PATH` con `df` y `docker` de mentira, y el registro de lo borrado.

    El `df` cambia de respuesta en cuanto aparece el testigo de que la poda ya
    corrió: así el script ve el mundo que vería de verdad —una medida antes y
    otra después— sin que la prueba tenga que adivinar en qué orden llama.
    """
    binarios = tmp / "bin"
    binarios.mkdir()
    testigo = tmp / "podado"
    borradas = tmp / "borradas.txt"
    borradas.write_text("")
    filas = imagenes if imagenes is not None else IMAGENES

    if df_roto:
        cuerpo_df = 'echo "Filesystem 1B-blocks"\nexit 0\n'
    else:
        cuerpo_df = f"""
if [ -f "{testigo}" ]; then LIBRES={libres_despues}; else LIBRES={libres_antes}; fi
echo "Filesystem 1B-blocks Used Available Capacity Mounted on"
echo "/dev/nvme0n1p1 {21 * GIB} 0 $LIBRES 0% /"
"""
    (binarios / "df").write_text("#!/usr/bin/env bash\n" + cuerpo_df)

    _escribe_docker(
        binarios / "docker", filas, corriendo, borradas, testigo, rmi_falla, sin_data_root
    )

    for nombre in ("df", "docker"):
        (binarios / nombre).chmod(0o755)
    # `awk`, `sort`, `grep`… siguen siendo los del sistema: sólo se falsean las
    # dos herramientas que hablan con la máquina.
    return binarios


def _escribe_docker(
    ruta: Path,
    filas: list[tuple[str, str]],
    corriendo: list[str],
    borradas: Path,
    testigo: Path,
    rmi_falla: str | None,
    sin_data_root: bool,
) -> None:
    ps = "\n".join(f'    echo "{ref}"' for ref in corriendo) or "    :"
    # El fake respeta `--format`: el script lo llama con DOS formatos distintos
    # —uno con la fecha para ordenar y otro solo con la referencia para podar— y
    # un fake que devolviera siempre lo mismo haría que la lista de conservación
    # nunca casara con la de candidatas. Ese fue el primer defecto de esta suite.
    img = "\n".join(
        f'    case "$REPO" in *"{ref.rsplit(":", 1)[0]}"*)'
        f' if [ -n "$CONFECHA" ]; then printf "%s\\t%s\\n" "{creado}" "{ref}";'
        f' else echo "{ref}"; fi;; esac'
        for creado, ref in filas
    )
    info = "    exit 1" if sin_data_root else '    echo "/var/lib/docker"'
    fallo = f'    if [ "$2" = "{rmi_falla}" ]; then exit 1; fi\n' if rmi_falla else ""
    ruta.write_text(
        f"""#!/usr/bin/env bash
case "$1" in
  info)
{info}
    ;;
  ps)
{ps}
    ;;
  images)
    REPO=""; CONFECHA=""
    for a in "$@"; do
      case "$a" in
        reference=*) REPO="${{a#reference=}}";;
        *CreatedAt*) CONFECHA=1;;
      esac
    done
{img or "    :"}
    ;;
  rmi)
{fallo}    echo "$2" >> "{borradas}"
    touch "{testigo}"
    ;;
esac
exit 0
"""
    )


def _corre(binarios: Path, etiqueta: str = "3f1c9ab") -> subprocess.CompletedProcess[str]:
    entorno = dict(os.environ, PATH=f"{binarios}:{os.environ['PATH']}")
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), REGISTRY, etiqueta],
        capture_output=True,
        text=True,
        env=entorno,
        check=False,
    )


def _borradas(tmp: Path) -> list[str]:
    fichero = tmp / "borradas.txt"
    return [x for x in fichero.read_text().splitlines() if x]


# ─────────────────────────────────────────── el script existe y viaja entero


def test_el_script_esta_donde_el_despliegue_lo_busca() -> None:
    """Guarda de no-vacuidad: sin esto todo lo de abajo fallaría por otra razón."""
    assert SCRIPT.is_file(), f"{SCRIPT} no existe"
    assert shutil.which("bash"), "sin bash no se puede ejercer nada de esto"


def test_el_despliegue_lo_INVOCA_antes_de_pisar_nada() -> None:
    """El orden es lo que hace que abortar deje la instancia intacta.

    Se mide por ÍNDICE en el texto y no por número de línea: un número escrito a
    mano en una prueba se desactualiza al primer commit ajeno.
    """
    texto = DEPLOY.read_text(encoding="utf-8")
    invocacion = texto.index("/opt/takab/cloud/margen-y-poda.sh ${REGISTRY}")
    for hito, aguja in (
        ("el compose", "> /opt/takab/cloud/docker-compose.yml"),
        ("las unidades de systemd", "> /etc/systemd/system/takab-cloud.service"),
        ("el fichero de entorno", "cat > /etc/takab/deploy.env"),
        ("la primera bajada de imagen", "-m alembic upgrade head"),
    ):
        assert invocacion < texto.index(aguja), (
            f"el guardia de disco se invoca DESPUÉS de {hito}: abortar ya habría "
            "dejado la instancia a medio pisar"
        )


# ──────────────────────────────────────────── lo que la poda NO puede llevarse


def test_la_poda_JAMAS_se_lleva_la_imagen_QUE_CORRE(tmp_path: Path) -> None:
    """El modo de fallo por el que `prune -a` a secas está prohibido aquí."""
    corriendo = [f"{REGISTRY}/takab/cloud:a986a62", f"{REGISTRY}/takab/console:a986a62"]
    binarios = _falsos(
        tmp_path, libres_antes=268 * 1024**2, libres_despues=9 * GIB, corriendo=corriendo
    )
    r = _corre(binarios)
    assert r.returncode == 0, r.stderr
    for viva in corriendo:
        assert viva not in _borradas(tmp_path), f"la poda se llevó {viva}, que está corriendo"


def test_con_el_stack_ABAJO_la_poda_sigue_conservando_las_recientes(tmp_path: Path) -> None:
    """El caso que `docker image prune -a` se lleva entero.

    Si `takab-secrets.service` no materializa los secretos, `takab-cloud.service`
    no levanta y la instancia se queda sin un solo contenedor de la nube. Con la
    conservación por identidad, las etiquetas recientes siguen ahí.
    """
    binarios = _falsos(tmp_path, libres_antes=268 * 1024**2, libres_despues=9 * GIB, corriendo=[])
    r = _corre(binarios)
    assert r.returncode == 0, r.stderr
    borradas = _borradas(tmp_path)
    for reciente in (
        f"{REGISTRY}/takab/cloud:a986a62",
        f"{REGISTRY}/takab/cloud:9a01278",
        f"{REGISTRY}/takab/cloud:f99b7e0",
    ):
        assert reciente not in borradas, f"con el stack abajo se llevó {reciente}"
    # Y sí se llevó las viejas: si no borrara nada, lo de arriba pasaría solo.
    assert f"{REGISTRY}/takab/cloud:af5c1d6" in borradas


def test_la_poda_NO_toca_lo_que_no_es_de_TAKAB(tmp_path: Path) -> None:
    """Empezando por la imagen que sostiene la base de datos.

    `takab-db` no está en el compose —lo arranca `user_data` con `docker run`— y
    una poda que barriera el catálogo entero se lo llevaría.
    """
    filas = [*IMAGENES, ("2026-08-01 00:00:00 +0000 UTC", "timescale/timescaledb-ha:pg16")]
    binarios = _falsos(
        tmp_path,
        libres_antes=268 * 1024**2,
        libres_despues=9 * GIB,
        corriendo=[],
        imagenes=filas,
    )
    _corre(binarios)
    assert "timescale/timescaledb-ha:pg16" not in _borradas(tmp_path)


def test_la_poda_NO_usa_una_ventana_de_TIEMPO() -> None:
    """Ancla negativa contra el apaño que se tecleó a mano el 2026-09-16.

    La recencia como criterio de conservación ya se midió mal en campo: la poda
    por fecha del edge se llevó la release heredada la misma noche del estreno,
    porque toda release nueva es más reciente que ella. Sin esta prueba, el
    comando de emergencia vuelve al script en el primer arreglo apresurado y se
    convierte en la política permanente.
    """
    texto = SCRIPT.read_text(encoding="utf-8")
    # Se miran las INVOCACIONES, no la prosa: el encabezado explica por qué
    # están prohibidas y el mensaje de ayuda se lo sugiere a un humano con su
    # advertencia al lado. Una línea que EMPIEZA por el comando sí es código.
    invocaciones = [
        ln
        for ln in texto.splitlines()
        if re.match(r"\s*(docker|[A-Z_]+=.*docker)\s", ln) and not ln.lstrip().startswith("#")
    ]
    culpables = [
        ln.strip() for ln in invocaciones if "until=" in ln or re.search(r"prune\s+-a", ln)
    ]
    assert not culpables, (
        "el script EJECUTA una poda por fecha o un `prune -a` desnudo: la primera "
        "se lleva siempre el artefacto al que se querría volver, y el segundo sólo "
        f"perdona lo que tiene un contenedor encima. {culpables}"
    )


# ────────────────────────────────────────────────── medir, y no fingir que se midió


def test_un_df_QUE_NO_CONTESTA_aborta_y_no_dice_ok(tmp_path: Path) -> None:
    """Un fallback no puede ser `ok`. Medido mal no es lo mismo que no medido."""
    binarios = _falsos(tmp_path, libres_antes=0, libres_despues=0, corriendo=[], df_roto=True)
    r = _corre(binarios)
    assert r.returncode != 0
    assert "✓" not in r.stdout, "dijo que todo iba bien sin haber medido nada"
    assert "no se pudo medir" in r.stderr


def test_sin_DATA_ROOT_de_docker_tampoco_se_sigue(tmp_path: Path) -> None:
    """El punto de montaje se deriva de Docker; si Docker no contesta, no hay
    volumen que vigilar y seguir sería vigilar el equivocado."""
    binarios = _falsos(
        tmp_path, libres_antes=9 * GIB, libres_despues=9 * GIB, corriendo=[], sin_data_root=True
    )
    r = _corre(binarios)
    assert r.returncode != 0
    assert "✓" not in r.stdout


def test_el_margen_INSUFICIENTE_para_y_el_mensaje_dice_QUE_HACER(tmp_path: Path) -> None:
    """Es la hora que costó el 2026-09-16, con nombre y apellidos.

    Aquel día el único texto legible decía «alembic upgrade head FALLÓ (rc=125)»
    y mandaba a mirar migraciones. Éste tiene que nombrar el volumen, la cifra,
    por qué la alarma que ya existe no lo vio, y que la nube sigue en pie.
    """
    binarios = _falsos(
        tmp_path,
        libres_antes=268 * 1024**2,
        libres_despues=300 * 1024**2,  # la poda apenas liberó
        corriendo=[f"{REGISTRY}/takab/cloud:a986a62"],
    )
    r = _corre(binarios)
    assert r.returncode != 0
    salida = r.stdout + r.stderr
    assert "margen insuficiente" in salida
    assert "docker system df" in salida, "no dice el primer comando que hay que correr"
    assert "/data" in salida, "no dice que la alarma que existe mira el OTRO volumen"
    assert "La API no se ha tocado" in salida, "no dice que la nube sigue en pie"


def test_cuando_CABE_se_imprimen_las_DOS_medidas(tmp_path: Path) -> None:
    """Una poda silenciosa es lo que hace que nadie sepa cuánto margen quedaba."""
    binarios = _falsos(
        tmp_path,
        libres_antes=268 * 1024**2,
        libres_despues=9 * GIB,
        corriendo=[f"{REGISTRY}/takab/cloud:a986a62"],
    )
    r = _corre(binarios)
    assert r.returncode == 0, r.stderr
    assert "antes de podar" in r.stdout, "no dice cuánto había antes"
    assert "✓" in r.stdout and "libres de" in r.stdout, "no dice cuánto queda después"
    assert "conservando" in r.stdout, "no dice qué se queda"


def test_sin_nada_que_podar_TAMBIEN_se_dice(tmp_path: Path) -> None:
    """El silencio no es una respuesta: el log del despliegue es donde se ve si
    el margen se está estrechando."""
    corriendo = [f"{REGISTRY}/takab/cloud:a986a62"]
    binarios = _falsos(
        tmp_path,
        libres_antes=9 * GIB,
        libres_despues=9 * GIB,
        corriendo=corriendo,
        imagenes=[IMAGENES[0], IMAGENES[6]],
    )
    r = _corre(binarios)
    assert r.returncode == 0, r.stderr
    assert "nada que podar" in r.stdout
    assert "libres de" in r.stdout


def test_una_imagen_que_no_se_deja_borrar_se_DICE(tmp_path: Path) -> None:
    """Y no tumba la poda: el margen sigue siendo quien juzga."""
    binarios = _falsos(
        tmp_path,
        libres_antes=268 * 1024**2,
        libres_despues=9 * GIB,
        corriendo=[],
        rmi_falla=f"{REGISTRY}/takab/cloud:af5c1d6",
    )
    r = _corre(binarios)
    assert r.returncode == 0, r.stderr
    assert "no se pudo borrar" in r.stdout
    assert "sin borrar" in r.stdout, "el recuento del ✓ no declara las fallidas"


# ───────────────────────────────── la retención no promete más de lo que hay


def test_la_retencion_local_no_promete_mas_de_lo_que_ECR_conserva() -> None:
    """La cota real de cuántas vueltas atrás EXISTEN no es el disco: es ECR.

    Más allá de las imágenes que la política de ciclo de vida conserva, la
    etiqueta ya no está en el registro y guardarla en la instancia no compra
    ninguna reversión que alguien pueda ejecutar. Se DERIVA del terraform en vez
    de escribir el número dos veces.
    """
    registry = (RAIZ / "infra/terraform/modules/registry/main.tf").read_text(encoding="utf-8")
    m = re.search(r"countNumber\s*=\s*(\d+)", registry)
    assert m, "no se encontró `countNumber` en la política de ciclo de vida de ECR"
    tope = int(m.group(1))

    script = SCRIPT.read_text(encoding="utf-8")
    d = re.search(r'RETENCION="\$\{TAKAB_RETENCION_IMAGENES:-(\d+)\}"', script)
    assert d, "no se encontró la retención por defecto en margen-y-poda.sh"
    retencion = int(d.group(1))

    assert retencion <= tope, (
        f"el despliegue conserva {retencion} etiquetas por repositorio y ECR sólo "
        f"guarda {tope}: la retención local promete vueltas atrás que el registro "
        "no puede servir"
    )


@pytest.mark.parametrize("herramienta", ["df", "docker"])
def test_los_falsos_de_esta_suite_SE_USAN_de_verdad(tmp_path: Path, herramienta: str) -> None:
    """Guarda de no-vacuidad de la propia prueba.

    Si el `PATH` dejara de tener efecto —o el script llamara a `/usr/bin/df` por
    ruta absoluta— todo lo de arriba estaría midiendo la máquina de quien corre
    los tests, no el script.
    """
    binarios = _falsos(tmp_path, libres_antes=268 * 1024**2, libres_despues=9 * GIB, corriendo=[])
    (binarios / herramienta).write_text("#!/usr/bin/env bash\nexit 77\n")
    (binarios / herramienta).chmod(0o755)
    r = _corre(binarios)
    assert r.returncode != 0, (
        f"con `{herramienta}` devolviendo 77 el script siguió adelante: no está "
        "usando el PATH de la prueba"
    )
