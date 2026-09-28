"""Catálogo de roles: los SIETE canónicos y la ventana de alias de los viejos (D-42 · T-9.20).

D-42 bajó los roles de 10 a 7. Los identificadores técnicos NO cambian (la RLS no
se toca): lo que desaparece son tres roles, que durante una ventana siguen entrando
**canonizados** a su heredero:

- ``soc_operator``   → ``tenant_admin`` (era un subconjunto estricto del administrador).
- ``security_guard`` → ``brigadista``   (tenían EXACTAMENTE los mismos permisos).
- ``building_admin`` → ``brigadista``   (quien necesite consola se mapea a
  ``tenant_admin`` con el script de migración de Cognito, T-9.21; NUNCA con una
  excepción por usuario en tiempo de ejecución, que sería una vía de escalada).

Reglas que este módulo sostiene y que no se reinterpretan:

1. **Antifalsificación sobre lo CRUDO.** ``Claims.from_verified`` comprueba
   ``custom:role`` ∈ ``cognito:groups`` tal como vienen en el token, y SOLO DESPUÉS
   llama a :func:`canonizar`. Canonizar antes dejaría pasar un ``custom:role`` viejo
   con el grupo de su heredero (o al revés).
2. **La baja.** ``Settings.roles_heredados_hasta`` (``None`` = ventana abierta). Pasada
   esa fecha, un token con rol viejo es 401 ``rol_retirado`` —en REST y en el cierre
   del WS— y se comprueba ANTES que la edad de sesión: ``sesion_expirada`` mandaría a
   la persona a re-entrar, y re-entrar con el mismo rol no lo arregla. T-9.81 quitará
   los alias del código; la fecha es la palanca intermedia.
3. **La historia no se reescribe.** Bitácora, acciones, dictámenes y PDF guardan el rol
   que se tenía; sus rótulos viven en :data:`ROL_HISTORICO` (fuente única del lado api).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from takab_api.auth.tokens import AuthError

if TYPE_CHECKING:
    from takab_api.auth.claims import Claims

#: Los siete roles de D-42, en orden estable (internos primero, luego el cliente).
CANONICAL_ROLES: tuple[str, ...] = (
    "takab_superadmin",
    "takab_support",
    "tenant_admin",
    "gov_operator",
    "inspector",
    "brigadista",
    "occupant",
)

#: Etiqueta en castellano de cada canónico. La web y la app la leen del servidor
#: (``GET /users/assignable-roles``) en vez de escribirla a mano.
ETIQUETA: dict[str, str] = {
    "takab_superadmin": "SUPERADMIN TAKAB",
    "takab_support": "SOPORTE TAKAB",
    "tenant_admin": "ADMINISTRADOR",
    "gov_operator": "GOBIERNO",
    "inspector": "INSPECTOR",
    "brigadista": "BRIGADISTA",
    "occupant": "OCUPANTE",
}

#: Rol viejo → canónico. Solo durante la ventana de D-42 (T-9.81 los quita).
ALIAS_HEREDADOS: dict[str, str] = {
    "soc_operator": "tenant_admin",
    "security_guard": "brigadista",
    "building_admin": "brigadista",
}

#: Rótulos de los roles viejos para lo HISTÓRICO (filas que no se reescriben: el PDF
#: de un reporte viejo sigue diciendo con qué rol se firmó). Espejo en la web:
#: ``rolesHistoricos.ts`` (uno solo).
ROL_HISTORICO: dict[str, str] = {
    "soc_operator": "OPERACIÓN SOC",
    "building_admin": "ADMINISTRACIÓN DEL INMUEBLE",
    "security_guard": "SEGURIDAD",
}

#: Motivo del 401 / del cierre WS tras la baja. Contrato con web y móvil.
_MEXICO = ZoneInfo("America/Mexico_City")

ROL_RETIRADO = "rol_retirado"


class RolRetirado(AuthError):
    """El token trae un rol viejo y la ventana de alias ya cerró. 401, NO renovable."""

    def __init__(self) -> None:
        super().__init__(ROL_RETIRADO)


def canonizar(role: str) -> str:
    """El canónico de ``role``; un rol que no es alias se devuelve tal cual (un rol
    desconocido sigue siendo desconocido: la matriz y la sesión lo niegan)."""
    return ALIAS_HEREDADOS.get(role, role)


def es_heredado(role: str) -> bool:
    return role in ALIAS_HEREDADOS


def literales_de(canonico: str) -> tuple[str, ...]:
    """El canónico y sus alias viejos, para las consultas que filtran por un rol
    guardado en la base (filas escritas antes de la 0072, o por un cliente viejo)."""
    return (canonico, *sorted(v for v, n in ALIAS_HEREDADOS.items() if n == canonico))


def enforce_rol_vigente(claims: Claims, hasta: date | None, *, hoy: date | None = None) -> None:
    """``RolRetirado`` si el token trae un rol viejo y ``hoy`` > ``hasta``.

    ``hasta=None`` ⇒ ventana abierta. El día de la baja todavía entra (``>`` estricto):
    la fecha dice «hasta», no «desde»."""
    if hasta is None or not es_heredado(claims.role_raw):
        return
    if hoy is None:
        # La fecha la escribe una persona en México: se compara con el día de la Ciudad
        # de México, no con el de UTC (que cambia a las 18:00 hora local).
        hoy = datetime.now(_MEXICO).date()
    if hoy > hasta:
        raise RolRetirado()
