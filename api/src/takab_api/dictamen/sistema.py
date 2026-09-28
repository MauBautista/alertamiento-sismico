"""Identidad fija con la que FIRMA el sistema (T-9.31 · D-43).

Patrón de ``commands.quorum_actuation.QUORUM_ACTOR_UUID``: un UUID constante que
no pertenece a ninguna persona. ``signed_by = SYSTEM_DICTAMEN_SIGNER_UUID`` sólo
aparece junto a ``signature_kind = 'system'`` (lo exige un CHECK de la migración
0073, que cita esta misma cifra; ``test_migracion_0073`` ata las dos copias).

QUIÉN firmó se lee SIEMPRE de ``signature_kind``, nunca de ``signed_by``: este
UUID jamás se imprime (A-145) ni se resuelve contra ``user_profiles``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from takab_api.dictamen.rules import DANOS_ROJO

SYSTEM_DICTAMEN_SIGNER_UUID = "00000000-0000-4000-8000-00000000d043"

#: [F3·r3 · D-43] Firmas de una PERSONA: la del inspector y la confirmación. Sobre
#: una cabeza así el worker sólo sube por los daños que esa persona no vio.
FIRMAS_HUMANAS: frozenset[str] = frozenset({"inspector", "confirmation"})

#: [F3·r3 · D-43] ¿Esta fila ``d`` de ``dictamens`` es una firma de INSPECTOR? Es lo
#: único que da por ATENDIDA una solicitud de dictamen técnico (``dictamen_request``):
#: ni el VERDE del sistema ni una confirmación de la brigada son la inspección que se
#: pidió. Las filas firmadas ANTERIORES a la 0073 (``signature_kind`` NULL) cuentan:
#: antes de D-43 sólo el inspector firmaba, y sin eso cada solicitud atendida de la
#: historia volvería a estar pendiente. UNA copia, citada por el 409 de
#: ``incidents_ops``, el correo del orquestador y el worker (alias ``d`` obligatorio).
FIRMA_DE_INSPECTOR_SQL = (
    "(d.signature_kind = 'inspector' OR (d.signature_kind IS NULL AND d.signed_by IS NOT NULL))"
)


#: [D-49 · R4] Clave de ``basis`` donde una firma HUMANA (inspector o confirmación)
#: guarda los ``report_id`` de los reportes de daño que existían al firmar, leídos
#: DENTRO del lock del incidente. Es la evidencia que esa persona vio.
CLAVE_DANOS_VISTOS = "danos_vistos"

#: [D-49 · R4] ¿Esta fila ``d`` es una firma HUMANA? (``FIRMAS_HUMANAS`` en SQL; alias
#: ``d`` obligatorio). Las filas anteriores a la 0073 (``signature_kind`` NULL) NO
#: entran: el worker las sigue tratando como antes de D-43.
FIRMA_HUMANA_SQL = (
    "(d.signed_by IS NOT NULL AND d.signature_kind IN ("
    + ", ".join(f"'{k}'" for k in sorted(FIRMAS_HUMANAS))
    + "))"
)

#: [D-49 · R5] ¿Esta fila ``d`` ATIENDE una escalada al inspector para el REINGRESO?
#: Cualquier firma HUMANA (``FIRMA_HUMANA_SQL``: inspector o confirmación, R3) o una
#: firma anterior a la 0073 sin tipo (que cuenta como inspector, igual que en
#: ``FIRMA_DE_INSPECTOR_SQL``). El VERDE del sistema NO la atiende. Alias ``d``.
ATIENDE_ESCALADA_SQL = f"({FIRMA_HUMANA_SQL} OR {FIRMA_DE_INSPECTOR_SQL})"

#: [D-49 · R5] ¿El incidente ``i`` tiene una ``dictamen_request`` que ninguna firma
#: HUMANA posterior atendió? ÚNICA copia: la regla 1d de ``reingreso``.
ESCALADA_PENDIENTE_SQL = (
    "EXISTS (SELECT 1 FROM incident_actions a "
    "WHERE a.incident_id = i.incident_id AND a.kind = 'dictamen_request' "
    "AND NOT EXISTS (SELECT 1 FROM dictamens d WHERE d.incident_id = a.incident_id "
    f"AND {ATIENDE_ESCALADA_SQL} AND d.created_at > a.ts))"
)


def danos_no_vistos(reportes: Sequence[Any], firma: Any | None) -> list[Any]:
    """[D-49 · R4] Los reportes de daño que la última firma HUMANA NO vio.

    ÚNICA copia de la regla: la usan el worker (qué sube la banda tras la firma) y
    el 409 «requiere inspector» de la confirmación. ``reportes`` = filas con
    ``report_id``, ``created_at`` y ``claves``; ``firma`` = la última firma humana de
    la cadena (con ``basis``, ``created_at`` y ``signature_kind``), o ``None`` si no
    hay ninguna (entonces nadie vio nada).

    * Con ``basis.danos_vistos`` se compara por ID: la lista se leyó dentro del lock
      al firmar, así que un reporte anterior a la firma que no estaba en ella entró
      en vuelo y NO se vio.
    * Firma vieja sin la lista: como antes de D-49, los creados DESPUÉS de la firma
      y, sobre una confirmación, además cualquiera con un daño ROJO (la API no
      dejaba confirmar con uno, así que si existe es que entró en vuelo).
    """
    if firma is None:
        return list(reportes)
    basis = firma["basis"]
    vistos = basis.get(CLAVE_DANOS_VISTOS) if isinstance(basis, dict) else None
    if isinstance(vistos, list):
        ids = {str(v) for v in vistos}
        return [r for r in reportes if str(r["report_id"]) not in ids]
    confirmacion = firma["signature_kind"] == "confirmation"
    return [
        r
        for r in reportes
        if r["created_at"] > firma["created_at"]
        or (confirmacion and set(r["claves"] or ()) & DANOS_ROJO)
    ]
