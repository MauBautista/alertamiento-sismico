"""Constancia de MFA en el camino de comando de actuadores (T-2.84.b · `RO-8.c`).

La regla de oro 8 exige «comando firmado + **MFA** + rate-limit + nonce + ack, sin
excepción» sobre la superficie que cierra válvulas de gas y mueve ascensores. Este
módulo es la mitad que faltaba: hasta T-2.84.b, el MFA era el único de los cinco
controles **sin una sola línea de código ni de prueba en ninguna capa**.

§1 · Qué dice el token, de verdad
---------------------------------
Antes de escribir una comprobación hubo que averiguar qué puede comprobarse. La
respuesta, verificada contra la documentación de AWS y no de memoria, es que **el
token no dice si hubo segundo factor**:

- el *payload* por defecto del **ID token** —el que esta API verifica; ver
  ``tokens.py::_decode``, que exige ``token_use == "id"``— lleva
  ``sub``, ``cognito:groups``, ``email_verified``, ``cognito:preferred_role``,
  ``iss``, ``cognito:username``, ``nonce``, ``origin_jti``, ``cognito:roles``,
  ``aud``, ``identities``, ``event_id``, ``token_use``, ``auth_time``, ``exp``,
  ``iat``, ``jti`` y ``email``. **Ni ``amr`` ni ``acr``**
  (*Understanding the identity (ID) token*, Amazon Cognito Developer Guide);
- el **access token** tampoco los lleva (*Understanding the access token*);
- y en la tabla *Claims and scopes reference* del disparador *pre token
  generation*, ``acr`` y ``amr`` figuran como ``Can add? No · Can modify? No ·
  Can suppress? No``: son claims reservados de Cognito, así que **ni siquiera un
  Lambda propio puede fabricarlos**.

De ahí la decisión de diseño: **comprobar ``amr``/``acr`` habría sido teatro.**
Escrito como exigencia dura rechazaría el 100 % de los tokens reales; escrito como
«si viene, que valga» no se dispararía jamás. Y ``auth_time`` —que sí viaja— dice
*cuándo* se autenticó el usuario, no *cómo*: es frescura de sesión, no MFA. Ver
§4, donde queda declarado como lo que este módulo NO cubre.

§2 · Qué sí certifica el token: de qué pool viene
-------------------------------------------------
El ``iss`` va firmado y se verifica duro, y **el pool es quien porta la política de
MFA**. Este proyecto tiene DOS pools a la vez desde T-2.02 (decisión #7 ratificada):

===================  ====================  ==========================================
pool                 ``mfa_configuration``  por qué
===================  ====================  ==========================================
principal            ``ON``                todo el personal operativo
ocupantes            ``OPTIONAL``          el ocupante puede declinar su TOTP; obligar
                                           a un civil rompería el camino de vida
===================  ====================  ==========================================

O sea que el escenario de «¿y si algún día conviven dos pools con políticas
distintas?» **no es hipotético: es hoy**. ``tokens.decode_verify_any`` ya devuelve
de cuál viene cada token; lo que faltaba era que esa procedencia llegara al camino
de comando y se exigiera ahí, en vez de quedar implícita.

§3 · Por qué no basta con «está delegado al pool»
--------------------------------------------------
Era la respuesta escrita en el docstring de ``routers/commands.py`` y es *casi*
cierta. Se apoya en tres premisas, y ninguna estaba comprobada:

1. **que el pool principal siga en ``ON``.** Lo ancla ahora
   ``infra/terraform/modules/identity/tests/mfa.tftest.hcl``, que hasta T-2.84.b no
   existía: ``identity`` era el único de los módulos de Terraform sin pruebas, así
   que una deriva a ``OPTIONAL`` no la habría visto nadie;
2. **que el ancla pool→rol de ``deps.get_claims`` aguante** (el pool de ocupantes
   sólo emite ``occupant``). Eso sí tenía pruebas: ``tests/auth/test_dual_issuer.py``;
3. **que ningún rol emitido por un pool sin MFA cargue una acción de actuador.**
   Hoy se cumple —``occupant`` no tiene ninguna—, pero *por casualidad del catálogo
   de roles*, no por control. El día que ``occupant`` ganase ``manual_activate``, un
   usuario que declinó su TOTP movería un actuador y nada se pondría rojo. Esa
   premisa la vigila ahora
   ``tests/api/test_command_mfa.py::test_ningun_rol_del_pool_sin_MFA_carga_una_accion_de_actuador``.

Y hay una cuarta grieta que la delegación no cubre y conviene tener escrita, porque
sale de la propia documentación de AWS: **«The first time that a new user signs in
to your app, Amazon Cognito issues OAuth 2.0 tokens, even if your user pool requires
MFA»** (*Adding MFA to a user pool*). El primer inicio de sesión de un usuario nuevo
emite tokens **sin** TOTP; el pool le pide registrar el factor a partir del segundo.
Con ``mfa_configuration = "ON"`` la ventana es de un solo inicio de sesión y sólo
para cuentas recién creadas, pero *existe* — y el docstring que decía «todo ID token
de rol web implica TOTP superado» era, tal cual, falso.

§4 · Qué NO cubre este módulo
------------------------------
- **Constancia por token de que ESA sesión presentó el factor.** Cognito no la
  emite (§1). Sólo la daría un disparador *pre token generation* que escribiera un
  claim propio —``amr`` no, que es reservado— alimentado por el flujo de
  autenticación, o migrar la verificación al *access token* con un *authorizer*
  propio. Ninguna de las dos cosas existe hoy.
- **Frescura de re-autenticación** (``auth_time``). Un token de refresco vigente
  sigue emitiendo ID tokens mucho después del último factor presentado. Exigir
  ``auth_time`` reciente en el camino de comando es una decisión de producto: haría
  que el operador tuviera que volver a autenticarse en plena emergencia.
- **Dispositivos recordados.** Cognito documenta que *«After you configure a user's
  device to be remembered, Amazon Cognito no longer requires them to submit an MFA
  code when they sign in with the same device key»* (*Working with user devices in
  your user pool*). Es un bypass legítimo del segundo factor, invisible desde el
  token. Hoy el módulo de Terraform no declara ``device_configuration`` (el
  comportamiento por omisión es *no recordar*), y el ``.tftest.hcl`` lo ancla para
  que encenderlo no pueda pasar inadvertido — pero si algún día se enciende a
  propósito, esta guarda no lo notará.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException

from takab_api.auth.claims import Claims
from takab_api.auth.tokens import POOL_OCUPANTES, POOL_PRINCIPAL

#: Pools cuya política de Cognito impone el segundo factor a TODO token que emiten.
#:
#: El espejo de esta constante vive en Terraform y **está anclado por su propia
#: prueba**: ``infra/terraform/modules/identity/tests/mfa.tftest.hcl`` exige que
#: todo pool del módulo esté en ``mfa_configuration = "ON"`` salvo el de ocupantes,
#: que se declara ``OPTIONAL`` con su razón. Un pool nuevo entra rojo en los dos
#: lados: aquí no está en la lista, y allí no está en la excepción declarada.
MFA_ENFORCED_POOLS: frozenset[str] = frozenset({POOL_PRINCIPAL})

#: Marca que identifica a una dependencia como guarda de MFA. El censo de
#: ``tests/api/test_command_mfa.py`` la busca recorriendo el árbol de dependencias
#: de cada ruta: es lo que permite exigir POSTURA a todo handler que firme un
#: comando, en vez de ir tapando endpoints de uno en uno.
MFA_GUARD_ATTR = "takab_mfa_guard"

#: 403 y no 401: el token es válido y la identidad está probada; lo que falta es un
#: control de autorización sobre esta superficie concreta. Un 401 invitaría al
#: cliente a reintentar con el mismo token, que es exactamente lo que no sirve.
_SIN_CONSTANCIA = (
    "este comando mueve actuadores del edificio y exige un token con constancia de "
    "segundo factor (regla de oro 8): el pool de Cognito que lo emitió no impone MFA"
)


def require_mfa(inner: Callable[..., Claims]) -> Callable[..., Claims]:
    """Envuelve una dependencia de claims exigiendo procedencia con MFA (o 403).

    Va **DEBAJO** de la guarda de rol —``require_roles(*R, inner=require_mfa(...))``,
    o sea que se evalúa ANTES— y ese orden es la mitad del control. Compuesta al
    revés, un rol sin acciones de comando se caería por el rol y esta guarda no
    llegaría a ejecutarse nunca: el rechazo volvería a ser un accidente del
    catálogo de roles, que es exactamente el defecto que `RO-8.c` describe. La
    fuerza de la autenticación es una propiedad de la credencial y se decide antes
    de mirar qué puede hacer quien la presenta.
    """

    def _dep(claims: Claims = Depends(inner)) -> Claims:
        if claims.pool not in MFA_ENFORCED_POOLS:
            raise HTTPException(status_code=403, detail=_SIN_CONSTANCIA)
        return claims

    setattr(_dep, MFA_GUARD_ATTR, True)
    return _dep


__all__ = [
    "MFA_ENFORCED_POOLS",
    "MFA_GUARD_ATTR",
    "POOL_OCUPANTES",
    "POOL_PRINCIPAL",
    "require_mfa",
]
