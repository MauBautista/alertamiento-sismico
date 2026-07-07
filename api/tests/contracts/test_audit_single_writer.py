"""Contract-test (T-1.24): ``takab_api.audit`` es el ÚNICO escritor de audit_log.

Un INSERT suelto a ``audit_log`` fuera del helper burla la formalización (shape
de fila, meta jsonb, futura redacción/enriquecimiento). Patrón del contract de
``waveform_features_1s``: escaneo del árbol src.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "takab_api"
_INSERT = re.compile(r"INSERT\s+INTO\s+audit_log", re.IGNORECASE)
_ALLOW = {_SRC / "audit.py"}


def test_only_audit_module_inserts_audit_log() -> None:
    offenders: list[str] = []
    for py in _SRC.rglob("*.py"):
        if py in _ALLOW:
            continue
        if _INSERT.search(py.read_text(encoding="utf-8")):
            offenders.append(str(py.relative_to(_SRC)))
    assert offenders == [], (
        f"INSERT a audit_log fuera de takab_api/audit.py: {offenders} — "
        "usa audit()/audit_async() (helper único, T-1.24)"
    )
