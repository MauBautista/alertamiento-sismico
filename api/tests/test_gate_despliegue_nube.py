"""[T-2.153] El gate del despliegue de nube, comprobado sin desplegar nada.

`deploy/cloud/deploy.sh` levantaba contenedores y declaraba ✓ **sin preguntarle
nada a la API**. Es la misma familia de defecto que `systemctl is-active`
haciéndose pasar por canary: «arrancó» no es «sirve», y «migró» no es «la API ve
el esquema que su imagen espera».

Aquí se aísla el veredicto —el bloque de Python que el script embebe— y se le dan
las tres respuestas que puede recibir de `/api/health`. No se despliega nada: lo
que se mide es **qué decide**, que es lo único que este gate aporta.

El extractor imita la expansión del heredoc (`\\$` → `$`, `\\\\` → `\\`,
`\\<salto>` → continuación) porque el bloque vive dentro de un `cat <<EOF` sin
comillas. Sin eso se estaría probando un texto que el EC2 nunca ve — y esa
diferencia ya costó un despliegue: el `commands=` del CLI no decodificaba los
`\\n` y el script llegaba en una sola línea.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "cloud" / "deploy.sh"


def _bloque_remoto() -> str:
    """El script que de verdad corre en el EC2, tras expandir el heredoc."""
    lineas = _DEPLOY.read_text().splitlines()
    ini = next(i for i, l in enumerate(lineas) if l.startswith("REMOTE_SCRIPT="))
    ini = next(i for i in range(ini, len(lineas)) if "<<" in lineas[i]) + 1
    fin = next(i for i in range(ini, len(lineas)) if lineas[i] == "EOF")
    crudo = "\n".join(lineas[ini:fin])
    out: list[str] = []
    i = 0
    while i < len(crudo):
        c = crudo[i]
        if c == "\\" and i + 1 < len(crudo):
            sig = crudo[i + 1]
            if sig in "$`\\":
                out.append(sig)
                i += 2
                continue
            if sig == "\n":
                i += 2
                continue
        out.append(c)
        i += 1
    return "".join(out)


def _veredicto() -> str:
    m = re.search(r"python3 -c '(.*?)' \"", _bloque_remoto(), re.S)
    assert m is not None, "el gate del despliegue desapareció de deploy/cloud/deploy.sh"
    return m.group(1)


def _juzgar(salud: dict, *, desplegado: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _veredicto(), desplegado],
        input=json.dumps(salud),
        capture_output=True,
        text=True,
    )


def _salud(*, build: str, estado: str, aplicada: str = "0051", pendientes: int = 0) -> dict:
    return {
        "status": "ok",
        "build": build,
        "esquema": {
            "estado": estado,
            "aplicada": aplicada,
            "esperada": "0051",
            "pendientes": pendientes,
        },
    }


def test_el_despliegue_bueno_se_declara_bueno() -> None:
    r = _juzgar(_salud(build="abc1234", estado="al_dia"), desplegado="abc1234")
    assert r.returncode == 0, r.stderr
    assert "al día" in r.stdout


def test_un_esquema_ATRASADO_tumba_el_despliegue() -> None:
    """EL CASO DEL 2026-08-21, que nadie detectó.

    La nube corría `0038` con el repo en `0046` —OCHO migraciones— y no lo dijo
    ni una alarma, ni un health-check ni un test: se descubrió por un síntoma
    lateral (una alarma de retención atascada) tras media hora persiguiendo el
    script equivocado.
    """
    r = _juzgar(
        _salud(build="abc1234", estado="atrasada", aplicada="0038", pendientes=8),
        desplegado="abc1234",
    )
    assert r.returncode == 1
    assert "esquema NO está al día" in r.stderr
    assert "'0038'" in r.stderr and "8" in r.stderr, "no dice cuánto va por detrás"


def test_los_contenedores_con_la_imagen_ANTERIOR_tumban_el_despliegue() -> None:
    """`docker compose ps` en verde con la imagen de ayer tiene EXACTAMENTE el
    mismo aspecto que un despliegue bueno. Lo único que los separa es preguntarle
    a la API qué commit corre."""
    r = _juzgar(_salud(build="viejo99", estado="al_dia"), desplegado="abc1234")
    assert r.returncode == 1
    assert "imagen ANTERIOR" in r.stderr
    assert "'viejo99'" in r.stderr and "'abc1234'" in r.stderr


def test_no_poder_saber_la_revision_NO_es_estar_al_dia() -> None:
    """`desconocida` es «no se pudo preguntar», y eso no autoriza a declarar ✓.
    Es la misma doctrina que el canary del gabinete: lo que no se midió no se
    aprueba — aunque tampoco se castigue inventando una avería."""
    r = _juzgar(
        _salud(build="abc1234", estado="desconocida", aplicada="", pendientes=0),
        desplegado="abc1234",
    )
    assert r.returncode == 1
    assert "esquema NO está al día" in r.stderr


def test_los_DOS_fallos_a_la_vez_se_dicen_LOS_DOS() -> None:
    """Un gate que se para en el primer problema manda al operador a arreglar
    una cosa, desplegar otra vez y descubrir la segunda. Se dicen juntos."""
    r = _juzgar(
        _salud(build="viejo99", estado="atrasada", aplicada="0038", pendientes=8),
        desplegado="abc1234",
    )
    assert r.returncode == 1
    assert "imagen ANTERIOR" in r.stderr
    assert "esquema NO está al día" in r.stderr


@pytest.mark.parametrize("clave", ["build", "esquema"])
def test_una_salud_MUTILADA_no_pasa_por_buena(clave: str) -> None:
    """Si `/api/health` deja de declarar una de las dos mitades, el gate no puede
    seguir diciendo ✓: sería aprobar por ausencia de dato."""
    salud = _salud(build="abc1234", estado="al_dia")
    del salud[clave]
    r = _juzgar(salud, desplegado="abc1234")
    assert r.returncode == 1


def test_el_gate_ESPERA_a_que_la_api_conteste_antes_de_rendirse() -> None:
    """No es un `curl` suelto: la API tarda en levantar tras el `restart`, y un
    gate que preguntara una sola vez sería un falso rojo en cada despliegue —
    entrenando al operador a ignorar el único aviso que dice si sirve."""
    remoto = _bloque_remoto()
    assert "for _ in $(seq 1 30)" in remoto, "el gate no reintenta: sería un falso rojo"
    assert "/api/health" in remoto
    assert "logs --tail" in remoto, "si no contesta, hay que dejar el journal a mano"
