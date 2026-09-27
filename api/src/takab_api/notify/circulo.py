"""[T-9.11 · D-39] A QUIÉN despierta el push de un incidente: una tabla pura.

Hasta esta ficha el orquestador **nunca miraba el disparador**: todo incidente con
teléfonos registrados salía como CRISIS («ALERTA SÍSMICA», el canal que salta el No
Molestar) a TODO el inmueble. Un golpe cerca del sensor despertaba a 400 personas con
la alerta sísmica, y después `mobile-state` les ocultaba el incidente (T-2.105): el
pánico sin instrucción que el cliente pidió no difundir.

La decisión vive aquí, en una función sin base ni reloj, para que revocarla (D-39,
«Cómo se revocaría») sea cambiar una línea con su test:

==============================================  =====================================
incidente                                       push
==============================================  =====================================
autoriza evacuar (SASMEX, cuórum de red)         CRISIS a TODO el inmueble
local sin corroborar en DISPARO                  MOVEMENT a los roles de `movement_alert`
local sin corroborar en CAUTELA                  ninguno (consola y panel del gabinete)
pánico manual (`trigger='manual'`)               ninguno por aquí: `_enqueue_panic_push`
cualquier otro que no autorice                   CRISIS a todos (conducta anterior)
==============================================  =====================================

**Por qué el pánico sale de esta tabla.** `_enqueue` corre antes que
`_enqueue_panic_push` y éste se salta todo incidente que ya tenga push: con teléfonos
registrados, una activación manual salía como «ALERTA SÍSMICA» a todo el edificio en
vez de como PANIC a la brigada — lo contrario de D-05.

**DISPARO** es el escalón que exige dos canales sobre el umbral (`restricted` o
`evacuate_or_hold` ⇒ severity `warning`/`critical`, `settings.TIER_SEVERITY`). La
CAUTELA (`watch`, un canal) no despierta a nadie: el golpe del ensayo del 24-sep se
quedó ahí, y despertar a la brigada con cada camión enseña a ignorar el aviso.
"""

from __future__ import annotations

from dataclasses import dataclass

from takab_api.auth.matrix import roles_with_action
from takab_api.notify.push import PUSH_CLASS_CRISIS, PUSH_CLASS_MOVEMENT
from takab_api.settings import TIER_SEVERITY

#: Severidades del escalón de DISPARO. Se DERIVAN de la tabla de tiers del edge, no se
#: teclean: si el mapeo cambia, esto lo sigue.
SEVERIDADES_DE_DISPARO: frozenset[str] = frozenset(
    {TIER_SEVERITY["restricted"], TIER_SEVERITY["evacuate_or_hold"]}
)


#: [T-9.11 · D-42] Roles cuyo teléfono NO pertenece a un inmueble sino al CLIENTE
#: entero: el administrador ve todo su cliente, sin alcance por edificio, así que su
#: app registra el token con `site_id` NULL. Un token así recibe los avisos de
#: CUALQUIER inmueble de su tenant, y sólo los que su rol recibiría en ese inmueble.
#: Fuera de estos roles, un token sin inmueble sigue sin ser destinatario de nada
#: (el defecto declarado de T-2.109).
ROLES_DE_TODO_EL_CLIENTE: tuple[str, ...] = ("tenant_admin",)


@dataclass(frozen=True)
class DestinoPush:
    """Qué clase de push y a qué círculo. ``roles=None`` = TODO el inmueble."""

    push_class: str
    roles: tuple[str, ...] | None


def push_target_for(*, trigger: str, severity: str, autoriza: bool) -> DestinoPush | None:
    """El push de incidente que toca, o ``None`` si ningún teléfono debe sonar."""
    if autoriza:
        return DestinoPush(PUSH_CLASS_CRISIS, None)
    if trigger == "manual":
        return None
    if trigger == "local_threshold":
        if severity in SEVERIDADES_DE_DISPARO:
            return DestinoPush(PUSH_CLASS_MOVEMENT, roles_with_action("movement_alert"))
        return None
    return DestinoPush(PUSH_CLASS_CRISIS, None)
