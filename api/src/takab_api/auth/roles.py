"""Catálogo de roles: los SIETE canónicos y la BAJA de los tres viejos (D-42 · T-9.81).

D-42 bajó los roles de 10 a 7. Los identificadores técnicos NO cambiaron (la RLS no
se tocó). Durante la ventana de T-9.20 los tres retirados entraban **canonizados** a su
heredero; ``migrar_roles_7.py --verify`` dio cero (nadie tiene ya rol ni grupo viejo) y
T-9.81 quitó esa traducción del código:

- ``soc_operator``, ``security_guard`` y ``building_admin`` son :data:`ROLES_RETIRADOS`.

Reglas que este módulo sostiene y que no se reinterpretan:

1. **Antifalsificación sobre lo CRUDO.** ``Claims.from_verified`` comprueba
   ``custom:role`` ∈ ``cognito:groups`` PRIMERO; solo un token íntegro llega a
   :func:`enforce_no_retirado`. Un rol viejo sin su grupo sigue siendo
   «role not in groups» (forjado), no «retirado».
2. **La baja, sin fecha.** Un token con rol viejo es SIEMPRE 401 ``rol_retirado`` —en
   REST y en el cierre del WS (4401)— y ANTES que la edad de sesión:
   ``sesion_expirada`` mandaría a la persona a re-entrar, y re-entrar con el mismo rol
   no lo arregla. La palanca de fecha (``roles_heredados_hasta``) desapareció con la
   ventana: no hay variable que la reabra.
3. **La historia no se reescribe.** Bitácora, acciones, dictámenes y PDF guardan el rol
   que se tenía; sus rótulos viven en :data:`ROL_HISTORICO` (fuente única del lado api).
"""

from __future__ import annotations

from takab_api.auth.tokens import AuthError

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

#: [T-9.81] Los tres roles dados de baja por D-42. Un token con uno de ellos es 401
#: ``rol_retirado``; ``migrar_roles_7.py --verify`` los busca en el pool.
ROLES_RETIRADOS: frozenset[str] = frozenset({"soc_operator", "security_guard", "building_admin"})

#: Rótulos de los roles retirados para lo HISTÓRICO (filas que no se reescriben: el PDF
#: de un reporte viejo sigue diciendo con qué rol se firmó). Espejo en la web:
#: ``rolesHistoricos.ts`` (uno solo).
ROL_HISTORICO: dict[str, str] = {
    "soc_operator": "OPERACIÓN SOC",
    "building_admin": "ADMINISTRACIÓN DEL INMUEBLE",
    "security_guard": "SEGURIDAD",
}

#: [T-9.81] A dónde fue cada retirado (la copia congelada de la 0072 lo ata). NO traduce
#: tokens —eso se acabó—: solo le dice a :func:`literales_de` qué literal viejo puede
#: quedar en una fila GUARDADA de su heredero.
HEREDERO_HISTORICO: dict[str, str] = {
    "soc_operator": "tenant_admin",
    "security_guard": "brigadista",
    "building_admin": "brigadista",
}

#: Motivo del 401 / del cierre WS de un rol retirado. Contrato con web y móvil.
ROL_RETIRADO = "rol_retirado"


class RolRetirado(AuthError):
    """El token trae un rol dado de baja por D-42. 401, NO renovable."""

    def __init__(self) -> None:
        super().__init__(ROL_RETIRADO)


def enforce_no_retirado(role: str) -> None:
    """``RolRetirado`` si ``role`` es uno de :data:`ROLES_RETIRADOS`; si no, nada."""
    if role in ROLES_RETIRADOS:
        raise RolRetirado()


def literales_de(canonico: str) -> tuple[str, ...]:
    """El canónico y los literales viejos que pudieron quedar en una fila GUARDADA de
    su heredero, para las consultas que filtran por un rol escrito en la base.

    La 0072 canonizó ``push_tokens`` y ``user_zone_assignments`` y, tras la baja, ningún
    token viejo puede escribir otra; incluirlos no le da nada a nadie que no lo tuviera
    y cierra el hueco de una fila que se le escapara a la migración."""
    return (canonico, *sorted(v for v, n in HEREDERO_HISTORICO.items() if n == canonico))
