"""T-2.80 · ARCO por anonimización con tombstone.

EL CONFLICTO, Y POR QUÉ NO ES UN CONFLICTO
──────────────────────────────────────────
El ocupante tiene derecho a que sus datos personales desaparezcan. El sistema
tiene la obligación dura de conservar íntegras la auditoría, la evidencia de
incidentes y los dictámenes estructurales (regla de oro 11: eso **no se poda
jamás**). Parecen dos requisitos incompatibles y no lo son, porque el derecho es
sobre la PERSONA y la obligación es sobre el HECHO.

La bisagra está en qué es exactamente ``life_checkins.user_id``: un `sub` de
Cognito, es decir un UUID opaco. Solo es dato personal mientras exista un mapeo
`sub → nombre/teléfono`, y ese mapeo vive en ``user_profiles`` (y en Cognito).
ARCO **destruye el mapeo y deja el UUID en pie**. El hecho —"alguien confirmó
estar bien en el piso 8 a las 13:42"— sobrevive completo; la persona detrás deja
de ser recuperable.

POR QUÉ EL `sub` NO SE SUSTITUYE POR UN SEUDÓNIMO
─────────────────────────────────────────────────
La tentación obvia es reemplazar `user_id` por un valor constante. Sería un
error grave: ``COUNT(DISTINCT user_id)`` es "cuántas PERSONAS confirmaron estar
bien en esta zona", y colapsar todos los titulares anonimizados en un mismo
valor lo hundiría. En un sismo eso no es una métrica: es la diferencia entre
mandar o no mandar una brigada a un piso. Por eso el criterio 2 de la ficha
—"un check-in anonimizado sigue contando"— gobierna el diseño entero.

Lo que sí se destruye del check-in es ``geom``: la ubicación GPS exacta de una
persona. El conteo no la necesita (``zone_id`` da la granularidad que el rescate
usa) y es el dato más sensible de la tabla.

QUÉ IMPIDE FÍSICAMENTE BORRAR EN VEZ DE ANONIMIZAR
──────────────────────────────────────────────────
Tres capas, ninguna de ellas un comentario:

1. **Privilegios.** ``takab_app`` no tiene ``DELETE`` en ninguna tabla protegida
   —y hay ``REVOKE`` explícito, porque el 0001 concede ``ON ALL TABLES`` después
   de aplicar el schema— y sobre ``life_checkins`` solo tiene ``UPDATE (geom)``:
   privilegio **por columna**. Reescribir `status` o `user_id` es un error de
   permisos de PostgreSQL, no una decisión del código.
2. **Triggers, con los eventos separados.** El ``DELETE`` de ``life_checkins``
   lo sigue vetando ``forbid_update_delete()``, el guard canónico de auditoría,
   dictámenes y evidencia: **no hay excepción de ARCO para borrar**. El
   ``UPDATE`` pasa a ``life_checkin_arco_guard()``, que rechaza todo cambio que
   no sea exactamente "anular ``geom``" — comparando la fila entera vía
   ``to_jsonb``, así que cubre también las columnas que se añadan mañana. Los
   dos cubren al dueño de la tabla, que es a quien el privilegio no cubre.
3. **La firma de la función.** ``privacy_erase_subject(p_right, p_via)`` no
   recibe sujeto: opera sobre ``app_user_id()``. Ejercer ARCO sobre un tercero
   no está prohibido, es **inexpresable**.

LA LÁPIDA (`privacy_erasures`)
──────────────────────────────
Deja constancia del acto sin conservar el dato: qué derecho se ejerció, cuándo,
por qué vía y **cuántas** filas se anonimizaron por tabla. Ni una copia del
nombre, del teléfono ni del token — guardar eso "para trazabilidad" convertiría
la anonimización en una seudonimización reversible, que es exactamente lo que la
tarea no puede ser.

Y sella ``(audit_watermark, audit_digest)``: el último ``audit_id`` del tenant en
el instante del borrado y el SHA-256 de toda la bitácora anterior. Eso es lo que
convierte "el audit_log sigue íntegro" en algo **medible años después** por
cualquiera, y no en una afirmación del día del despliegue.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# ---------------------------------------------------------------------------
# Códigos de error de la capa SQL (la decisión se toma en la DB, no en el router)
# ---------------------------------------------------------------------------

#: La sesión no identifica a un titular (no hay `app.user_id`).
SQLSTATE_FORBIDDEN = "TK403"
#: Hay un incidente ABIERTO en un sitio del titular: la anonimización se aplaza.
SQLSTATE_DEFERRED = "TK409"
#: Se intentó borrar o reescribir una fila que solo admite ser anonimizada. Es el
#: código por defecto de ``RAISE EXCEPTION``, el MISMO que levanta
#: ``forbid_update_delete()``: el guard de `life_checkins` es una variante de ese
#: guard, no una excepción distinta, y quien ya captura uno captura el otro.
SQLSTATE_APPEND_ONLY = "P0001"

#: Lo que ve la consola donde había un nombre. NO es un nombre falso a propósito
#: (regla de oro 7: un dato inventado es peor que un hueco declarado).
ERASED_DISPLAY_NAME = "(titular anonimizado)"

#: Prefijo del token de push ya inservible. Se conserva la FILA —el hecho de que
#: hubo un dispositivo registrado— y muere el identificador que lo enruta.
ERASED_TOKEN_PREFIX = "arco:"

#: Firma de la función de borrado. Anclada en un test: el día que alguien añada
#: un parámetro de sujeto para que un tercero ejerza ARCO por otro, rompe y
#: obliga a razonar la superficie nueva (ver `tests/test_privacy_erasure.py`).
ERASE_FN_ARGS: tuple[str, ...] = ("p_right", "p_via")

#: Tablas donde ARCO DESTRUYE un valor. Debe coincidir exactamente con las
#: entradas ``erase`` del inventario — hay un test que lo comprueba.
ERASED_TABLES: tuple[str, ...] = ("user_profiles", "push_tokens", "life_checkins")

#: Tablas donde ARCO no destruye nada: REVOCA una capacidad hacia adelante.
#: La distinción no es cosmética. ``device_keys.public_key`` verifica la firma de
#: intención de ``damage_reports`` —evidencia— y destruirla sería podar la
#: integridad de esa evidencia por la puerta de atrás. Se revoca, se conserva.
REVOKED_TABLES: tuple[str, ...] = ("push_tokens", "device_keys")

#: Todo lo que el acto toca, y por tanto las claves exactas de ``affected``.
TOUCHED_TABLES: tuple[str, ...] = (
    "user_profiles",
    "push_tokens",
    "device_keys",
    "life_checkins",
)

Right = Literal["cancelacion", "oposicion"]
Action = Literal["erase", "keep_link", "retain_compliance"]


# ---------------------------------------------------------------------------
# EL DETECTOR · el inventario de PII se DERIVA del esquema, no se teclea
# ---------------------------------------------------------------------------
#
# Un inventario enumerado a mano envejece en silencio: el día que alguien añada
# `occupant_email` a una tabla, nadie se acordará de venir aquí. El detector
# recorre `information_schema` y marca lo que huele a persona; el test exige que
# todo hallazgo esté clasificado abajo. El inventario no puede quedarse corto sin
# que la suite se ponga roja.

#: Columnas que apuntan a una persona (un `sub` de Cognito, o su rastro textual).
SUBJECT_LINK_NAMES = frozenset(
    {
        "user_id",
        "user_sub",
        "actor",
        "actor_sub",
        "subject_ref",
        "verified_by",
        "signed_by",
        "requested_by",
        "published_by",
        "updated_by",
        "created_by",
        "issued_by",
        "assigned_by",
    }
)

#: Columnas que CONTIENEN dato personal directo, no una referencia a él.
NAMED_PII = frozenset(
    {
        "display_name",
        "phone",
        "msisdn",
        "email",
        "token",
        "endpoint_arn",
        "public_key",
        "notes",
    }
)

#: Una geometría solo es PII si la tabla sabe de quién es. `sites.geom` es la
#: ubicación de un edificio; `life_checkins.geom`, la de una persona.
GEO_TYPES = frozenset({"geography", "geometry"})


def detect_pii_columns(rows: Iterable[tuple[str, str, str]]) -> set[tuple[str, str]]:
    """``(table, column, udt_name)`` del esquema → columnas que exigen decisión ARCO.

    Función pura: el test le pasa el esquema VIVO. Así el inventario se contrasta
    con la realidad de la base y no con la memoria de quien lo escribió.
    """
    por_tabla: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for tabla, columna, udt in rows:
        por_tabla[tabla].append((columna, udt))

    hallazgos: set[tuple[str, str]] = set()
    for tabla, columnas in por_tabla.items():
        nombres = {c for c, _ in columnas}
        tiene_sujeto = bool(nombres & SUBJECT_LINK_NAMES)
        for columna, udt in columnas:
            if columna in SUBJECT_LINK_NAMES or columna in NAMED_PII:
                hallazgos.add((tabla, columna))
            elif udt in GEO_TYPES and tiene_sujeto:
                hallazgos.add((tabla, columna))
    return hallazgos


@dataclass(frozen=True)
class PiiColumn:
    """Qué le pasa a esta columna cuando el titular ejerce ARCO, y por qué.

    ``why`` no es documentación decorativa: es la justificación que hay que poder
    dar si alguien pregunta por qué un dato personal sigue ahí. Una entrada
    ``retain_compliance`` sin razón escrita es una fuga con permiso.
    """

    action: Action
    why: str


_ERASE = "erase"
_KEEP = "keep_link"
_RETAIN = "retain_compliance"

#: Razones que se repiten. Extraídas para que decir lo mismo no se convierta en
#: decir cosas parecidas.
_R_SUB_OPACO = (
    "`sub` de Cognito: UUID opaco. Es la CLAVE DE CONTEO del histórico y deja de "
    "ser dato personal en cuanto ARCO destruye el mapeo en `user_profiles`. "
    "Colapsarlo a un seudónimo hundiría COUNT(DISTINCT) — criterio 2 de la ficha."
)
_R_AUDITORIA = (
    "Fila de auditoría/evidencia: regla de oro 11, no se poda ni se reescribe "
    "jamás. Queda un UUID opaco, no una identidad."
)
_R_OPERADOR = (
    "Acto de OPERACIÓN auditable (quién configuró, emitió o publicó algo que "
    "afecta a la seguridad del inmueble). Equivale a una fila de auditoría: "
    "regla de oro 11. El sujeto además es personal de la plataforma o del "
    "cliente, no un ocupante."
)

#: EL PLAN. Toda columna que el detector encuentre tiene que estar aquí.
PII_INVENTORY: dict[tuple[str, str], PiiColumn] = {
    # --- lo que ARCO destruye -------------------------------------------------
    ("user_profiles", "display_name"): PiiColumn(
        _ERASE,
        "El nombre. Es el mapeo `sub → persona`: destruirlo es lo que hace "
        f"anónimo todo lo demás. Queda {ERASED_DISPLAY_NAME!r}, un hueco declarado.",
    ),
    ("user_profiles", "phone"): PiiColumn(
        _ERASE, "Teléfono del roster (llamada de un toque). Dato personal directo."
    ),
    ("push_tokens", "token"): PiiColumn(
        _ERASE,
        "Identificador de dispositivo que ENRUTA a la persona. Se sustituye "
        "por un valor inservible y la fila se marca revocada; la fila queda.",
    ),
    ("push_tokens", "endpoint_arn"): PiiColumn(
        _ERASE, "Endpoint SNS derivado del token: mismo alcance, misma suerte."
    ),
    ("life_checkins", "geom"): PiiColumn(
        _ERASE,
        "Ubicación GPS EXACTA de una persona. El conteo de rescate no la "
        "necesita (`zone_id` da la granularidad que se usa) y es el dato más "
        "sensible de la tabla. La FILA no se toca: por eso sigue contando.",
    ),
    # --- lo que se conserva porque es la clave del hecho ----------------------
    ("life_checkins", "user_id"): PiiColumn(_KEEP, _R_SUB_OPACO),
    ("life_checkins", "verified_by"): PiiColumn(
        _KEEP,
        "Brigadista que verificó el check-in delegado. Es la diferencia "
        "entre 'se reportó' y 'alguien lo comprobó en persona': parte del hecho.",
    ),
    ("user_zone_assignments", "user_id"): PiiColumn(
        _KEEP,
        "Denominador del headcount ('8 asignados al piso 8, 5 confirmaron'). "
        "Quitar la asignación es DAR DE BAJA la cuenta, que es otro acto y otra "
        "ficha; ARCO no lo incluye.",
    ),
    ("manual_activation_votes", "user_id"): PiiColumn(
        _KEEP, "Voto de activación manual: quórum de 2 ocupantes en 30 s. " + _R_SUB_OPACO
    ),
    ("push_tokens", "user_sub"): PiiColumn(_KEEP, _R_SUB_OPACO),
    ("device_keys", "user_sub"): PiiColumn(_KEEP, _R_SUB_OPACO),
    ("user_profiles", "user_sub"): PiiColumn(
        _KEEP,
        "La FILA se conserva anonimizada, no se borra: es lo que mantiene "
        "el `sub` atado a su tenant y por tanto las tablas de hechos coherentes.",
    ),
    # --- lo que se conserva por regla de oro 11 -------------------------------
    ("audit_log", "actor"): PiiColumn(_RETAIN, _R_AUDITORIA),
    ("incident_actions", "actor"): PiiColumn(_RETAIN, _R_AUDITORIA),
    ("dictamens", "signed_by"): PiiColumn(
        _RETAIN,
        "FIRMA de un dictamen estructural. Borrarla no anonimiza: "
        "invalida el dictamen, que es evidencia de habitabilidad de un edificio.",
    ),
    ("damage_reports", "user_sub"): PiiColumn(_RETAIN, _R_AUDITORIA),
    ("damage_reports", "notes"): PiiColumn(
        _RETAIN,
        "Texto libre DENTRO de evidencia append-only. Puede contener PII "
        "que el ocupante tecleó y NO se puede anonimizar sin abrir un hueco en el "
        "trigger de evidencia. Hueco declarado, no cubierto por T-2.80.",
    ),
    ("device_keys", "public_key"): PiiColumn(
        _RETAIN,
        "Verifica `damage_reports.intent_signature`. Destruirla dejaría la "
        "evidencia firmada sin poder verificarse: podar su integridad por la "
        "puerta de atrás. La llave se REVOCA (no sirve hacia adelante) y se queda.",
    ),
    ("privacy_consents", "user_sub"): PiiColumn(
        _RETAIN,
        "Prueba de la base legal del tratamiento. Es lo que el responsable "
        "enseña si alguien reclama: destruirla le quita la defensa al titular tanto "
        "como al responsable (art. 8 LFPDPPP: revocar opera hacia adelante).",
    ),
    ("privacy_consents", "actor_sub"): PiiColumn(
        _RETAIN, "Quién REGISTRÓ el consentimiento (≠ quién consintió). " + _R_AUDITORIA
    ),
    ("privacy_consents", "subject_ref"): PiiColumn(
        _RETAIN,
        "Para `subject_kind='user'` es el `sub` opaco. Para 'msisdn' es un "
        "TELÉFONO EN CLARO dentro de una tabla append-only: hueco declarado, ver la "
        "sección 'lo que NO cubre' — T-2.80 solo anonimiza sujetos de tipo `user`.",
    ),
    ("privacy_notices", "published_by"): PiiColumn(_RETAIN, _R_OPERADOR),
    ("privacy_erasures", "user_sub"): PiiColumn(
        _KEEP,
        "Sujeto de la propia lápida. `sub` opaco: es la clave de idempotencia "
        "del acto, y no hay nada a lo que remontarlo una vez destruido el mapeo.",
    ),
    ("privacy_erasures", "requested_by"): PiiColumn(
        _RETAIN, "Quién pidió el borrado. Hoy es siempre el propio titular. " + _R_AUDITORIA
    ),
    ("commands", "issued_by"): PiiColumn(_RETAIN, _R_OPERADOR),
    ("rule_sets", "created_by"): PiiColumn(_RETAIN, _R_OPERADOR),
    ("visibility_grants", "created_by"): PiiColumn(_RETAIN, _R_OPERADOR),
    ("compliance_labels", "updated_by"): PiiColumn(_RETAIN, _R_OPERADOR),
    ("site_assets", "updated_by"): PiiColumn(_RETAIN, _R_OPERADOR),
    ("fw_releases", "published_by"): PiiColumn(_RETAIN, _R_OPERADOR),
    ("fw_releases", "notes"): PiiColumn(
        _RETAIN, "Notas de una versión de firmware. No es dato de un ocupante."
    ),
    ("reference_earthquakes", "notes"): PiiColumn(
        _RETAIN, "Catálogo sísmico público (SSN). No es dato personal."
    ),
}


# ---------------------------------------------------------------------------
# El acto
# ---------------------------------------------------------------------------

_ERASE_SELF = text("SELECT privacy_erase_subject(:right, :via) AS lapida")

_TOMBSTONE = text(
    "SELECT erasure_id, tenant_id, user_sub, right_exercised, requested_by, via, "
    "       affected, audit_watermark, audit_digest, erased_at "
    "FROM privacy_erasures "
    "WHERE tenant_id = CAST(:tenant AS uuid) AND user_sub = CAST(:user AS uuid)"
)

_VERIFY = text("SELECT privacy_audit_digest(CAST(:tenant AS uuid), :watermark) AS digest")


async def erase_self(conn: AsyncConnection, *, right: str, via: str) -> dict[str, Any]:
    """Ejerce ARCO sobre el titular de la SESIÓN. No hay otro sujeto posible.

    Devuelve la lápida más ``created``: ``False`` significa "ya se había
    ejercido", no "falló". Todo el acto —los cuatro anonimizados, la lápida y el
    sellado del digest— ocurre en una sola sentencia: una anonimización a medias
    no es un estado alcanzable.
    """
    crudo = await conn.scalar(_ERASE_SELF, {"right": right, "via": via})
    return crudo if isinstance(crudo, dict) else json.loads(crudo)


async def tombstone(conn: AsyncConnection, *, tenant_id: str, user_sub: str) -> Any:
    """La lápida del titular, o ``None`` si nunca ejerció ARCO."""
    return (
        (await conn.execute(_TOMBSTONE, {"tenant": tenant_id, "user": user_sub}))
        .mappings()
        .one_or_none()
    )


async def audit_digest_now(conn: AsyncConnection, *, tenant_id: str, watermark: int) -> str:
    """Recalcula HOY el digest que la lápida selló el día del borrado.

    Es la mitad que hace verificable a la otra: un sello guardado que nadie puede
    recomputar no prueba nada. Comparar este valor con ``audit_digest`` es la
    comprobación de integridad, y cualquiera con acceso al tenant puede hacerla.
    """
    return await conn.scalar(_VERIFY, {"tenant": tenant_id, "watermark": watermark})
