"""[T-2.171] La regla A-1, comprobada por conducta y no por lectura.

`deploy/cloud/README.md:55` la escribe desde la auditoría de cierre —*«Deploy SOLO
desde main pusheado con CI verde»*— y durante meses vivió ahí y en un solo script.
El 2026-08-27 esa checklist falló **dos veces el mismo día**: un `terraform apply`
que no aplicó el topic ni la regla que venía a aplicar, y un `make cloud-deploy`
que puso en la nube un build sin la migración que lo acompañaba.

Lo que hace difícil de ver a este defecto es que **todo salió en verde**. El gate
del despliegue comprobó que la API corre el commit desplegado y que su esquema
está al día —ciertas las dos, del commit equivocado—; la alarma de deriva comparó
imagen contra base y coincidían; el plan de Terraform comparó código contra estado
y «sin cambios» *era* la respuesta correcta. Un gate verifica que desplegaste **lo
que pediste**; ninguno puede saber que querías otra cosa.

Aquí no se lee el script: se **corre la guardia** contra repos de mentira, porque
lo único que importa de ella es su código de salida.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GUARDAS = REPO / "deploy" / "lib" / "guardas.sh"

#: Todo script de despliegue del repo. El censo lo pone el árbol, no una lista:
#: un `deploy/<algo>/deploy.sh` nuevo sin guardia no puede pasar en verde.
SCRIPTS = sorted((REPO / "deploy").glob("*/deploy.sh"))


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo_de_mentira(tmp_path: Path) -> Path:
    """Un repo con `origin`, `main` publicada y una rama de trabajo."""
    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remoto)], check=True)
    clon = tmp_path / "clon"
    subprocess.run(["git", "clone", "-q", str(remoto), str(clon)], check=True)
    _git(clon, "config", "user.email", "t@takab.mx")
    _git(clon, "config", "user.name", "test")
    _git(clon, "checkout", "-q", "-b", "main")
    (clon / "a.txt").write_text("uno\n")
    # Cada repo lleva SU guardas.sh, comiteado: la guardia deduce de su propia
    # ubicación qué árbol se despliega (y un fichero sin comitear lo ensuciaría).
    (clon / "deploy" / "lib").mkdir(parents=True)
    (clon / "deploy" / "lib" / "guardas.sh").write_text(GUARDAS.read_text())
    _git(clon, "add", "a.txt", "deploy/lib/guardas.sh")
    _git(clon, "commit", "-qm", "uno")
    _git(clon, "push", "-q", "-u", "origin", "main")
    return clon


#: Lo que la guardia usa de fuera del shell. Se construye un PATH MÍNIMO con esto
#: en vez de filtrar el del sistema: filtrar quitaba el directorio de `gh`, que en
#: esta máquina es el mismo de `bash`, y el test se quedaba sin intérprete.
_BINARIOS = ("bash", "git", "head")


def _bin_minimo(tmp: Path, *, con_gh: str | None) -> Path:
    """Un PATH controlado. `con_gh` es el veredicto que dará el `gh` de mentira,
    o `None` para que `gh` NO exista y la guardia tenga que declararlo."""
    binario = tmp / f"bin-{con_gh or 'sin-gh'}"
    binario.mkdir(exist_ok=True)
    for nombre in _BINARIOS:
        destino = binario / nombre
        if not destino.exists():
            ruta = subprocess.run(["which", nombre], capture_output=True, text=True).stdout.strip()
            assert ruta, f"no se encontró {nombre} para el PATH mínimo"
            destino.symlink_to(ruta)
    if con_gh is not None:
        gh = binario / "gh"
        gh.write_text(f'#!/bin/sh\necho "{con_gh}"\n')
        gh.chmod(0o755)
    return binario


def _correr(
    repo: Path,
    *,
    rama_libre: bool = False,
    sucio: str = "no",
    gh: str | None = "success",
    desde: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    entorno = dict(os.environ)
    entorno["PATH"] = str(_bin_minimo(repo.parent, con_gh=gh))
    if rama_libre:
        entorno["TAKAB_DEPLOY_RAMA_LIBRE"] = "1"
    return subprocess.run(
        [
            "bash",
            "-c",
            f'. "{repo / "deploy" / "lib" / "guardas.sh"}" && guarda_de_rama "prueba" {sucio}',
        ],
        cwd=desde or repo,
        capture_output=True,
        text=True,
        env=entorno,
    )


def test_en_main_limpia_y_pusheada_la_guardia_deja_pasar(repo_de_mentira: Path) -> None:
    res = _correr(repo_de_mentira)
    assert res.returncode == 0, res.stderr


def test_desde_una_rama_de_trabajo_se_NIEGA(repo_de_mentira: Path) -> None:
    """El caso exacto del 27-ago."""
    _git(repo_de_mentira, "checkout", "-q", "-b", "feat/lo-que-sea")
    res = _correr(repo_de_mentira)
    assert res.returncode != 0, "la guardia dejó desplegar desde una rama de trabajo"
    assert "feat/lo-que-sea" in res.stderr


def test_el_rechazo_dice_QUE_FALTA_y_no_solo_donde_estas(repo_de_mentira: Path) -> None:
    """La pregunta útil aquel día no era *dónde estoy* —eso ya se sabía— sino
    *qué me estoy dejando fuera*. Sin esa lista, el mensaje no ahorra el
    diagnóstico que costó el incidente."""
    _git(repo_de_mentira, "checkout", "-q", "-b", "vieja", "HEAD")
    (repo_de_mentira / "b.txt").write_text("dos\n")
    _git(repo_de_mentira, "add", "b.txt")
    _git(repo_de_mentira, "commit", "-qm", "la migracion que se quedaria fuera")
    _git(repo_de_mentira, "push", "-q", "origin", "vieja:main")
    _git(repo_de_mentira, "reset", "-q", "--hard", "HEAD~1")

    res = _correr(repo_de_mentira)
    assert res.returncode != 0
    assert "la migracion que se quedaria fuera" in res.stderr, (
        f"el rechazo no enumera lo que el despliegue dejaría fuera:\n{res.stderr}"
    )


def test_un_arbol_sucio_se_niega_salvo_que_el_llamador_lo_tolere(repo_de_mentira: Path) -> None:
    """La tolerancia existe por el EDGE y por nada más: `deploy/edge/deploy.sh`
    declara a propósito que un árbol sucio se despliega (marca la versión
    `--dirty` y avisa) porque depurar en sitio es un caso real. Rama y limpieza
    son dos preguntas distintas."""
    (repo_de_mentira / "a.txt").write_text("cambiado\n")
    assert _correr(repo_de_mentira).returncode != 0
    assert _correr(repo_de_mentira, sucio="si").returncode == 0


def test_main_con_commits_sin_pushear_se_niega(repo_de_mentira: Path) -> None:
    """«Lo que se despliega debe ser EXACTAMENTE lo que el repositorio y el CI
    vieron» — y el CI no ha visto lo que no se ha subido."""
    (repo_de_mentira / "c.txt").write_text("tres\n")
    _git(repo_de_mentira, "add", "c.txt")
    _git(repo_de_mentira, "commit", "-qm", "sin pushear")
    res = _correr(repo_de_mentira)
    assert res.returncode != 0
    assert "sin pushear" in res.stderr.lower() or "SIN PUSHEAR" in res.stderr


def test_la_escotilla_deja_pasar_pero_JAMAS_en_silencio(repo_de_mentira: Path) -> None:
    """Desplegar una rama a `dev` para probarla es legítimo y frecuente; lo que no
    puede ser es el default ni pasar desapercibido."""
    _git(repo_de_mentira, "checkout", "-q", "-b", "feat/probando")
    res = _correr(repo_de_mentira, rama_libre=True)
    assert res.returncode == 0
    assert "feat/probando" in res.stderr and "NO es main" in res.stderr


def test_sin_gh_la_guardia_declara_que_aplica_A1_A_MEDIAS(repo_de_mentira: Path) -> None:
    """Un fallback no puede hacerse pasar por un OK. Sin `gh` no se puede mirar el
    CI, así que la guardia queda a media potencia — y decirlo es la diferencia
    entre una limitación declarada y una que nadie sabe que tiene."""
    res = _correr(repo_de_mentira, gh=None)
    assert res.returncode == 0
    assert "A MEDIAS" in res.stderr


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.parent.name)
def test_todo_script_de_despliegue_pasa_por_la_guardia(script: Path) -> None:
    """El censo lo pone el árbol. Enumerar los tres a mano dejaría al cuarto
    fuera, y el cuarto sería justo el que nadie recuerda que despliega."""
    texto = script.read_text(encoding="utf-8")
    assert "guardas.sh" in texto and "guarda_de_rama" in texto, (
        f"{script.relative_to(REPO)} despliega y NO pasa por la regla A-1. "
        "Sourcea `deploy/lib/guardas.sh` y llama a `guarda_de_rama <componente>`."
    )


def test_el_terraform_a_mano_tambien_tiene_target_con_guardia() -> None:
    """El `apply` es el que menos se deja guardar —se teclea sin script de por
    medio— y es uno de los dos que fallaron. `make cloud-apply` es su puerta."""
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "cloud-apply:" in makefile, "no existe `make cloud-apply`"
    bloque = makefile.split("cloud-apply:", 1)[1].split("\n\n", 1)[0]
    assert "guarda_de_rama" in bloque, "`make cloud-apply` no aplica la regla A-1"
    assert "local.auto.tfvars" in bloque, (
        "`make cloud-apply` no comprueba `local.auto.tfvars`. Está en .gitignore, y sin él "
        "todo lo que lleva `count` evalúa a cero: el 2026-08-27 un plan desde un worktree "
        "limpio proponía destruir los tres DKIM, DMARC, MAIL FROM y la consola."
    )


def test_con_el_CI_de_main_en_rojo_la_guardia_se_niega(repo_de_mentira: Path) -> None:
    """La otra mitad de A-1: «main pusheado Y CON CI VERDE». Un `main` correcto
    cuyo último CI falló no es desplegable — el commit existe, pero nadie ha
    demostrado que funcione."""
    res = _correr(repo_de_mentira, gh="failure")
    assert res.returncode != 0
    assert "CI de main no esta en verde" in res.stderr


# --- la guardia mira el árbol que se DESPLIEGA, no el directorio desde el que se lanza --


def _otro_clon_en_main(repo: Path) -> Path:
    """Otro clon del mismo remoto, en `main`, limpio y al día: desde aquí se LANZA."""
    otro = repo.parent / "otro-clon"
    subprocess.run(
        ["git", "clone", "-q", "-b", "main", str(repo.parent / "remoto.git"), str(otro)],
        check=True,
    )
    return otro


def test_lanzada_desde_main_NO_aprueba_un_arbol_en_otra_rama(repo_de_mentira: Path) -> None:
    """El hueco medido el 2026-09-29: `deploy.sh` despliega el árbol donde vive, y la
    guardia miraba el directorio desde el que se lanzaba. Lanzado desde un clon en
    `main`, el despliegue de un árbol en una rama de trabajo PASABA."""
    _git(repo_de_mentira, "checkout", "-q", "-b", "trabajo")
    desde_main = _otro_clon_en_main(repo_de_mentira)
    r = _correr(repo_de_mentira, desde=desde_main)
    assert r.returncode != 0, r.stderr
    assert "trabajo" in r.stderr


def test_lanzada_desde_otra_rama_SI_aprueba_un_arbol_en_main(repo_de_mentira: Path) -> None:
    """Y al revés: el árbol que se despliega está en `main`; que la terminal esté en
    otra carpeta u otra rama no es asunto de la guardia (el 2026-09-29 lo bloqueó)."""
    desde_otra = _otro_clon_en_main(repo_de_mentira)
    _git(desde_otra, "checkout", "-q", "-b", "cualquier-cosa")
    r = _correr(repo_de_mentira, desde=desde_otra)
    assert r.returncode == 0, r.stderr


def _cloud_apply(lanza: Path, tf_dev: Path) -> subprocess.CompletedProcess[str]:
    """`make cloud-apply` de VERDAD (el Makefile del repo), con un `terraform` de
    mentira que sólo deja constancia de que se le llamó."""
    binario = _bin_minimo(lanza.parent, con_gh="success")
    for nombre in ("make", "sh"):
        if not (binario / nombre).exists():
            ruta = subprocess.run(["which", nombre], capture_output=True, text=True).stdout.strip()
            (binario / nombre).symlink_to(ruta)
    terraform = binario / "terraform"
    terraform.write_text('#!/bin/sh\necho "TERRAFORM-APLICADO $*"\n')
    terraform.chmod(0o755)
    (tf_dev / "local.auto.tfvars").write_text("")
    entorno = dict(os.environ, PATH=str(binario))
    entorno.pop("TAKAB_DEPLOY_RAMA_LIBRE", None)
    return subprocess.run(
        ["make", "-s", "-f", str(REPO / "Makefile"), "cloud-apply", f"TF_DEV={tf_dev}"],
        cwd=lanza,
        capture_output=True,
        text=True,
        env=entorno,
    )


def _tf_dev(repo: Path) -> Path:
    tf = repo / "infra" / "terraform" / "envs" / "dev"
    tf.mkdir(parents=True)
    # `local.auto.tfvars` va en .gitignore en el repo real: aquí también, o
    # ensuciaría el árbol y la guardia se negaría por la razón equivocada.
    (repo / ".gitignore").write_text("local.auto.tfvars\n")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-qm", "ignora los tfvars")
    _git(repo, "push", "-q", "origin", "HEAD:main")
    return tf


def test_cloud_apply_desde_main_NO_aplica_un_TF_DEV_en_otra_rama(repo_de_mentira: Path) -> None:
    """El mismo hueco en el terraform: `TF_DEV` apunta a la carpeta de siempre (la
    única con `local.auto.tfvars`), y la guardia miraba el directorio del `make`.
    Con la carpeta de siempre en una rama vieja, el `apply` de ESE árbol pasaba."""
    tf = _tf_dev(repo_de_mentira)
    desde_main = _otro_clon_en_main(repo_de_mentira)
    _git(repo_de_mentira, "checkout", "-q", "-b", "rama-vieja")
    r = _cloud_apply(desde_main, tf)
    assert "TERRAFORM-APLICADO" not in r.stdout, "aplicó el terraform de un árbol fuera de main"
    assert r.returncode != 0
    assert "rama-vieja" in r.stderr


def test_cloud_apply_desde_otra_rama_SI_aplica_un_TF_DEV_en_main(repo_de_mentira: Path) -> None:
    tf = _tf_dev(repo_de_mentira)
    desde_otra = _otro_clon_en_main(repo_de_mentira)
    _git(desde_otra, "checkout", "-q", "-b", "cualquier-cosa")
    r = _cloud_apply(desde_otra, tf)
    assert r.returncode == 0, r.stderr
    assert f"TERRAFORM-APLICADO -chdir={tf} apply" in r.stdout


def test_cloud_deploy_lee_sus_artefactos_del_arbol_que_juzga(repo_de_mentira: Path) -> None:
    """El reverso del hueco: la guardia ya juzga el árbol del script, así que lo que
    el script ENVÍA (compose, unidades, seeds; rutas relativas) también tiene que salir
    de ese árbol y no del directorio desde el que se lanza. Se corre el script de
    verdad hasta su primer `terraform`, que deja constancia de dónde está."""
    guion = repo_de_mentira / "deploy" / "cloud" / "deploy.sh"
    guion.parent.mkdir(parents=True)
    guion.write_text((REPO / "deploy" / "cloud" / "deploy.sh").read_text())
    _git(repo_de_mentira, "add", "deploy/cloud/deploy.sh")
    _git(repo_de_mentira, "commit", "-qm", "el guion de la nube")
    _git(repo_de_mentira, "push", "-q", "origin", "main")
    desde = _otro_clon_en_main(repo_de_mentira)
    _git(desde, "checkout", "-q", "-b", "trabajo")

    binario = _bin_minimo(repo_de_mentira.parent, con_gh="success")
    for nombre in ("dirname",):
        if not (binario / nombre).exists():
            ruta = subprocess.run(["which", nombre], capture_output=True, text=True).stdout.strip()
            (binario / nombre).symlink_to(ruta)
    bitacora = repo_de_mentira.parent / "terraform.log"
    # `aws` contesta (la cuenta) y `terraform` muere: el guion llega a los dos.
    for nombre, cola in (("aws", "echo 123456789012"), ("terraform", "exit 1")):
        falso = binario / nombre
        falso.write_text(f'#!/bin/sh\necho "{nombre}|$PWD|$*" >> "$TF_LOG"\n{cola}\n')
        falso.chmod(0o755)
    entorno = {
        "PATH": str(binario),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TF_LOG": str(bitacora),
        "AWS_PROFILE": "x",
        "AWS_REGION": "x",
        "TF_DEV": "infra/terraform/envs/dev",
        "CLOUD_TAG": "abc1234",
    }
    r = subprocess.run(["bash", str(guion)], cwd=desde, capture_output=True, text=True, env=entorno)
    assert r.returncode != 0  # muere en el terraform de mentira, a propósito
    assert bitacora.exists(), f"no llegó a aws ni a terraform:\n{r.stderr}"
    llamadas = [linea.split("|", 2) for linea in bitacora.read_text().splitlines()]
    for nombre, pwd, _ in llamadas:
        assert Path(pwd).resolve() == repo_de_mentira.resolve(), (
            f"{nombre} corrió en {pwd}: el guion lee sus artefactos de otro árbol que el "
            "que juzgó la guardia"
        )
    tf = [args for nombre, _, args in llamadas if nombre == "terraform"]
    assert tf, f"no llegó al terraform: {llamadas}\n{r.stderr}"
    # Un TF_DEV relativo conserva lo que significaba donde se tecleó.
    assert f"-chdir={(desde / 'infra/terraform/envs/dev').resolve()}" in tf[0], tf[0]


def _guardia_a_mano(
    guardas: Path, *, cwd: Path, gh: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """La guardia con un `gh` a medida (un guion de sh, no un veredicto fijo)."""
    binario = cwd.parent / f"bin-{cwd.name}"
    binario.mkdir(exist_ok=True)
    for nombre in _BINARIOS:
        if not (binario / nombre).exists():
            ruta = subprocess.run(["which", nombre], capture_output=True, text=True).stdout.strip()
            (binario / nombre).symlink_to(ruta)
    (binario / "gh").write_text(f"#!/bin/sh\n{gh}\n")
    (binario / "gh").chmod(0o755)
    entorno = dict(os.environ, PATH=str(binario), **(extra_env or {}))
    entorno.pop("TAKAB_DEPLOY_RAMA_LIBRE", None)
    return subprocess.run(
        ["bash", "-c", f'. "{guardas}" && guarda_de_rama "prueba"'],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=entorno,
    )


def test_el_CI_se_pregunta_en_el_arbol_juzgado_no_en_el_cwd(
    repo_de_mentira: Path, tmp_path: Path
) -> None:
    """`gh` decide el repositorio por el git de su directorio. Lanzada desde fuera de
    un repo, la guardia bloqueaba un árbol bueno con «CI desconocido»; desde otro
    repo, habría leído el CI de ESE repo."""
    fuera = tmp_path / "fuera-de-git"
    fuera.mkdir()
    raiz = repo_de_mentira.resolve()
    r = _guardia_a_mano(
        repo_de_mentira / "deploy" / "lib" / "guardas.sh",
        cwd=fuera,
        gh=f'[ "$(pwd -P)" = "{raiz}" ] && echo success || echo "gh-en-$(pwd -P)"',
    )
    assert r.returncode == 0, r.stderr


def test_un_CDPATH_exportado_no_desvia_la_raiz(repo_de_mentira: Path) -> None:
    """El Makefile sourcea por ruta RELATIVA; con CDPATH, `cd` imprime el destino y la
    raíz salía con dos líneas: la guardia bloqueaba diciendo «DETACHED ()»."""
    r = subprocess.run(
        ["bash", "-c", '. deploy/lib/guardas.sh && guarda_de_rama "prueba"'],
        cwd=repo_de_mentira,
        capture_output=True,
        text=True,
        env=dict(
            os.environ,
            PATH=str(_bin_minimo(repo_de_mentira.parent, con_gh="success")),
            CDPATH=".",
        ),
    )
    assert r.returncode == 0, r.stderr


def test_una_guardia_fuera_de_un_repo_se_niega_DICIENDO_por_que(tmp_path: Path) -> None:
    suelto = tmp_path / "suelto" / "deploy" / "lib"
    suelto.mkdir(parents=True)
    (suelto / "guardas.sh").write_text(GUARDAS.read_text())
    r = _guardia_a_mano(suelto / "guardas.sh", cwd=tmp_path, gh="echo success")
    assert r.returncode != 0
    assert "no es un repositorio git" in r.stderr, r.stderr
    assert "DETACHED" not in r.stderr
