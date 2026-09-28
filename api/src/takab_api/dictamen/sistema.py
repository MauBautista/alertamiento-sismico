"""Identidad fija con la que FIRMA el sistema (T-9.31 · D-43).

Patrón de ``commands.quorum_actuation.QUORUM_ACTOR_UUID``: un UUID constante que
no pertenece a ninguna persona. ``signed_by = SYSTEM_DICTAMEN_SIGNER_UUID`` sólo
aparece junto a ``signature_kind = 'system'`` (lo exige un CHECK de la migración
0073, que cita esta misma cifra; ``test_migracion_0073`` ata las dos copias).

QUIÉN firmó se lee SIEMPRE de ``signature_kind``, nunca de ``signed_by``: este
UUID jamás se imprime (A-145) ni se resuelve contra ``user_profiles``.
"""

from __future__ import annotations

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
