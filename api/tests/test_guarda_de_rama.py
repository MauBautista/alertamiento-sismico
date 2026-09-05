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
    _git(clon, "add", "a.txt")
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
) -> subprocess.CompletedProcess[str]:
    entorno = dict(os.environ)
    entorno["PATH"] = str(_bin_minimo(repo.parent, con_gh=gh))
    if rama_libre:
        entorno["TAKAB_DEPLOY_RAMA_LIBRE"] = "1"
    return subprocess.run(
        ["bash", "-c", f'. "{GUARDAS}" && guarda_de_rama "prueba" {sucio}'],
        cwd=repo,
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
