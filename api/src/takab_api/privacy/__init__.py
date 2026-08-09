"""T-2.79 · Motor de aviso de privacidad versionado + consentimiento.

Dos piezas:

* ``artifacts`` — el aviso como objeto versionado y sellado por su CONTENIDO
  (digest SHA-256), con los textos de plataforma en ``texts/*.json``.
* ``store``     — la resolución del aviso vigente (tenant > plataforma), el
  registro append-only del consentimiento y el estado que se le devuelve a la UI.

**Dónde este motor NO puede bloquear.** El consentimiento es cumplimiento; la
alerta sísmica es seguridad de la vida. Reglas de oro 1 y 2: el camino crítico
—SASMEX→actuador en el gabinete— no depende de la nube, así que ni siquiera
puede enterarse de que esto existe. Y en la nube tampoco gatea nada de campo:
un brigadista con un aviso nuevo sin aceptar **sigue pudiendo** hacer check-in
de vida, pedir ayuda, reportar daños y ver la alerta. Lo único que cambia es que
la app le pide el consentimiento en un momento tranquilo. Está probado en
``tests/api/test_privacy.py::test_el_consentimiento_pendiente_no_bloquea_el_checkin``.
"""

from __future__ import annotations

from takab_api.privacy.artifacts import (
    APPROVED,
    CANON_PREFIX,
    PURPOSES,
    NoticeCatalog,
    NoticeSpec,
    notice_digest,
)

__all__ = [
    "APPROVED",
    "CANON_PREFIX",
    "PURPOSES",
    "NoticeCatalog",
    "NoticeSpec",
    "notice_digest",
]
