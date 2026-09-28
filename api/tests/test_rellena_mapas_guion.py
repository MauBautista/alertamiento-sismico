"""[T-9.50] El guion que rellena los mapas en la nube llama a lo que existe.

`infra/scripts/rellena_mapas.sh` es texto que corre en la instancia por SSM: si el
módulo o el servicio se renombran, el guion falla allí y no aquí. Esto lo ata:

* el módulo que invoca existe en el árbol y tiene su `--desde`;
* el servicio es `incident-engine` (el único con el DSN de `takab_ingest`) y existe
  en el compose que despliega la nube;
* sin fecha no corre.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GUION = REPO / "infra" / "scripts" / "rellena_mapas.sh"


def test_invoca_un_modulo_que_existe_con_sus_argumentos() -> None:
    texto = GUION.read_text()
    m = re.search(r"python -m (takab_api\.[\w.]+)", texto)
    assert m, "el guion no invoca ningún módulo de takab_api"
    modulo = REPO / "api" / "src" / Path(*m.group(1).split("."))
    fuente = modulo.with_suffix(".py").read_text()
    assert '"--desde"' in fuente and '"--hasta"' in fuente and '"--max"' in fuente


def test_corre_en_incident_engine_que_existe_en_el_compose() -> None:
    assert "exec -T incident-engine " in GUION.read_text()
    compose = (REPO / "deploy" / "cloud" / "docker-compose.yml").read_text()
    assert re.search(r"^  incident-engine:\s*$", compose, re.M)


def test_sin_fecha_no_corre() -> None:
    r = subprocess.run(["bash", str(GUION)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 2
    assert "uso:" in r.stderr


def test_admite_TF_DEV_como_el_Makefile() -> None:
    """Desde un worktree sin terraform inicializado, `terraform output` muere: el guion
    tiene que poder apuntar al directorio inicializado (medido el 2026-09-28)."""
    assert 'TF_DIR="${TF_DEV:-' in GUION.read_text()
