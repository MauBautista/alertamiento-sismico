"""Alcance por sitio de la consola web (T-2.45).

``site_scope`` ya se aplica en WS, móvil, comandos y simulacros desde hace tiempo. En la
consola **no se aplicaba**: un ``soc_operator`` acotado a una estación veía todo el
tenant. Esto lo cierra, pero con un cutover en dos fases, porque encenderlo de golpe
sería peor que el hueco:

El claim ``custom:site_scope`` **no está aprovisionado para usuarios web** (nadie lo
escribe: ``infra/terraform/modules/identity/main.tf`` no lo emite y hasta T-2.54 no hay
pantalla que lo edite). ``claims.site_scope`` es default-deny, así que aplicar el filtro
tal cual dejaría a **todo** ``soc_operator`` con cero sitios — una consola en blanco en
una plataforma de alertamiento.

- **Fase A** (``console_scope_enforced=False``, la que se despliega): un claim vacío
  significa *sin restricción declarada* y no filtra, pero se **audita como hueco**
  (``scope_gap``) para que la ausencia sea visible y contable en vez de silenciosa. Un
  claim que SÍ trae sitios se respeta desde ya: honrarlo es estrictamente más seguro.
- **Fase B** (``True``): un claim vacío filtra a cero filas, que es lo que el claim
  significa. Se enciende cuando T-2.54 pueda escribir ``custom:site_scope``.

Fuera de alcance se responde **404, nunca 403**: un 403 confirma que el recurso existe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from takab_api.auth.claims import ALL_SITES, Claims

log = logging.getLogger("takab_api.auth")

#: Roles cuyo alcance NO lo gobierna ``site_scope``.
#:
#: Los tres primeros son de plataforma o de tenant completo. ``gov_operator`` está aquí
#: porque su alcance lo gobierna el mecanismo de VISIBILIDAD entre tenants (§1.73), no
#: el scope por sitio: acotarlo aquí además duplicaría la autoridad en dos sitios.
SCOPE_EXEMPT_ROLES: frozenset[str] = frozenset(
    {"takab_superadmin", "takab_support", "tenant_admin", "gov_operator"}
)


@dataclass(frozen=True, slots=True)
class ConsoleScope:
    """Alcance efectivo del request y por qué es ese."""

    #: ``None`` = sin filtro. Un conjunto (incluso vacío) filtra.
    sites: frozenset[str] | None
    #: El claim traía sitios (o ``*``). Si es falso, no hay alcance declarado.
    declared: bool
    #: Fase A con un rol acotado y claim vacío: el filtro NO se aplicó y debería.
    gap: bool

    @property
    def enforced(self) -> bool:
        """Si el servidor está filtrando de verdad. Es lo que la UI debe declarar."""
        return self.sites is not None

    def allows(self, site_id: str) -> bool:
        return self.sites is None or site_id in self.sites


def console_scope(claims: Claims, *, enforced: bool) -> ConsoleScope:
    """Alcance del request para las pantallas de consola."""
    if claims.role in SCOPE_EXEMPT_ROLES or claims.site_scope is ALL_SITES:
        return ConsoleScope(sites=None, declared=claims.site_scope is ALL_SITES, gap=False)

    sites = claims.site_scope
    assert not isinstance(sites, type(ALL_SITES))  # noqa: S101 - ya cubierto arriba
    if sites:
        return ConsoleScope(sites=frozenset(sites), declared=True, gap=False)

    # Claim vacío en un rol acotado.
    if enforced:
        return ConsoleScope(sites=frozenset(), declared=False, gap=False)
    log.warning(
        "console_scope: rol %r sin custom:site_scope aprovisionado (tenant %s, sub %s); "
        "fase A ⇒ sin filtro",
        claims.role,
        claims.tenant_id,
        claims.sub,
    )
    return ConsoleScope(sites=None, declared=False, gap=True)


#: Marcador que las SQL de consola llevan donde va el filtro por sitio.
SCOPE_MARKER = "/*+console_scope*/"


def scope_sql(scope: ConsoleScope, column: str) -> tuple[str, dict]:
    """Fragmento SQL del filtro y sus params. Sin filtro ⇒ cadena vacía.

    Un conjunto vacío produce ``= ANY('{}')``, que filtra a cero filas — que es
    exactamente lo que un alcance vacío significa en fase B.
    """
    if scope.sites is None:
        return "", {}
    return (
        f" AND {column} = ANY(CAST(:console_scope AS uuid[]))",
        {"console_scope": sorted(scope.sites)},
    )


def apply_scope(sql: str, scope: ConsoleScope, column: str) -> tuple[str, dict]:
    """Sustituye ``SCOPE_MARKER`` en la SQL por el filtro (o por nada)."""
    clause, params = scope_sql(scope, column)
    return sql.replace(SCOPE_MARKER, clause), params
