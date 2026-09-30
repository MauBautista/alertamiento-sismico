"""T-2.81 · El PLAN de retención de PII: qué caduca, cuándo, y qué es intocable.

Este módulo no ejecuta nada. Declara la política; el que la ejecuta es
``takab_api.ops.prune_pii``. La separación es deliberada: la política se lee y se
audita sin leer un solo `UPDATE`.

LA EXCEPCIÓN DE COMPLIANCE NO ES UNA LISTA QUE ALGUIEN ESCRIBIÓ
───────────────────────────────────────────────────────────────
La ficha exige que la excepción esté **codificada en el job**, no en un
comentario. Enumerar aquí las tablas intocables sería otra vez un comentario, uno
con sintaxis de Python: el día que nazca la tabla trece nadie vendría a añadirla.

Así que la lista se DERIVA del catálogo vivo (``protected_tables``), por dos
señales independientes y en OR:

* la tabla lleva colgado un **guard de borrado** (``forbid_update_delete`` o su
  variante de ARCO), o
* al rol del job **le falta el privilegio DELETE** sobre ella.

Cualquiera de las dos basta para declararla protegida, y las dos salen de
``pg_catalog``, no de este archivo. Una tabla nueva de evidencia que nazca con su
trigger append-only —como nacen todas en este repo— queda protegida sin que nadie
edite este módulo.

Una derivación sola, sin embargo, se aprueba a sí misma: "todo lo que derivé está
protegido" es cierto por construcción y no comprueba nada. Le faltan dos suelos, y
los dos están en ``validar_proteccion``:

* un conjunto **vacío** es la derivación rota, no un esquema sin evidencia; y
* ``COMPLIANCE_ANCHOR`` nombra las cinco tablas que la regla de oro 11 cita
  explícitamente, y tienen que aparecer. Sin ese suelo, conceder ``DELETE`` sobre
  ``audit_log`` y quitarle el trigger la sacaría del conjunto **en silencio** —y
  lo que ya no se deriva, ya no se revisa.

PODAR NO ES BORRAR (Y AQUÍ, HOY, NUNCA LO ES)
─────────────────────────────────────────────
Se examinó columna por columna el inventario de la T-2.80. **Toda** la PII que
caduca vive dentro de filas que tienen que sobrevivir:

* el token de push está en una fila que documenta que hubo un dispositivo
  registrado — el hecho se conserva, muere el identificador que enruta;
* la geometría del check-in está en una fila de rescate cuyo ``COUNT(DISTINCT
  user_id)`` es "cuántas personas confirmaron estar bien en el piso 8";
* [T-2.81.b] el nombre y el teléfono están en la fila que ata el ``sub`` a su
  tenant — borrarla dejaría huérfanas las constancias de ARCO y descoseria las
  tablas de hechos. Muere el mapeo `sub → persona`, no el perfil.

Por eso el plan que se despachaba **no contenía ni una regla que borrase filas**,
y un test lo fijaba. El modo ``DELETE_ROWS`` existía de todas formas, y no por
simetría: sin él, "el job intenta podar una tabla protegida" sería inexpresable y
el test del criterio 2 no probaría nada. Existe para que el guard tenga a qué
negarse, y para que el día que aparezca PII prunable de verdad la regla se pueda
escribir y el guard la revise.

**[T-9.80] Ese día llegó: ``emergency_contacts``.** Un contacto de emergencia es
dato de un TERCERO que sólo sirve para avisarle si el titular pide ayuda. No
documenta ningún hecho —el aviso enviado vive en ``incident_actions`` sin un solo
dato del contacto—, así que anonimizarlo dejaría una fila que no significa nada:
se borra la fila, y sólo esa. El test que exigía la lista vacía exige ahora
exactamente ésta, y cualquier otra regla que borre filas lo vuelve a poner rojo.

**[T-9.80 · 0078] Y los correos de esos contactos en los avisos YA enviados.** El
aviso de NECESITO AYUDA guarda el destinatario en ``notification_jobs.target``. Ahí
la fila SÍ es un hecho (hubo un aviso, a tal hora), así que se REDACTA: su ``target``
pasa al estado borrado, con el mismo reloj que los contactos y el mismo valor que
escribe ARCO.

EL PLAZO, Y QUÉ PASA SI NADIE LO CONFIGURA
──────────────────────────────────────────
No hay plazo por defecto. Cada regla lo lee de su variable de entorno y, si no
está, la regla queda **deshabilitada** y el informe lo dice en voz alta. El
default bajo incertidumbre es no borrar nada: una retención inventada por el
programador que la escribió no es una política de privacidad, es una pérdida de
datos con buena intención.

LO QUE NO TIENE RELOJ HONESTO SE DECLARA, NO SE INVENTA
───────────────────────────────────────────────────────
``user_profiles`` guarda nombre y teléfono del roster. Su única columna temporal
era ``updated_at``, y un perfil sin tocar en dos años es lo normal en un empleado
que sigue trabajando ahí: usarla como reloj habría borrado el roster de la gente
más estable del edificio. ``SIN_RELOJ`` dejó eso escrito con su razón, y el test
recíproco impidió que la ausencia pasara por descuido.

**[T-2.81.b] Ese reloj ya existe y ``SIN_RELOJ`` está vacío.** No se buscó una
columna temporal mejor: se registró el hecho que faltaba. ``user_deactivations``
guarda la BAJA DE LA CUENTA con su instante, y la escriben los dos actos que ya
significaban "esta persona ya no está" —deshabilitar la cuenta y borrarla del
directorio—, en la misma transacción en que ya dejaban su fila de auditoría
(``routers/users.py``). Volver a habilitarla PARA el reloj (``reactivated_at``):
sin eso, una persona readmitida seguiría contando plazo y perdería su nombre
estando en el edificio.

``SIN_RELOJ`` se conserva vacío, con su validación: es la rendija por la que la
siguiente columna de PII sin reloj tendrá que declararse en vez de colarse.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from .erasure import (
    ERASED_DISPLAY_NAME,
    ERASED_NOTICE_TARGET,
    ERASED_TOKEN_PREFIX,
    PII_INVENTORY,
)

# ---------------------------------------------------------------------------
# Errores. Los dos son ruidosos a propósito (criterio 2 de la ficha).
# ---------------------------------------------------------------------------


class RetentionUnsafe(RuntimeError):
    """El job se niega a correr. No degrada, no salta la regla mala: aborta.

    Se levanta SIEMPRE antes de tocar un dato. Un job de retención que "sigue
    con lo que sí puede" es un job que poda a medias y deja al operador creyendo
    que corrió entero.
    """


class RetentionPlanError(RuntimeError):
    """El plan que se despacha está mal formado. Se levanta al IMPORTAR."""


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

#: Sobrescribe columnas de PII y conserva la fila. Es lo único que hace el plan.
REDACT = "redact"
#: Borra la fila entera. Prohibido sobre cualquier tabla protegida; ver cabecera.
DELETE_ROWS = "delete_rows"

MODES = (REDACT, DELETE_ROWS)

#: Funciones-guard que vetan el ``DELETE`` en este esquema. ``forbid_update_delete``
#: es el canónico (auditoría, evidencia, dictámenes); ``life_checkin_arco_guard``
#: es su variante de la T-2.80, que sigue vetando el DELETE y solo abre
#: ``geom → NULL``; ``cctv_purge_guard`` es la de la T-3.11.b, que abre
#: ``s3_key → NULL`` para que el objeto de vídeo se pode y la fila lo declare.
#: Cualquiera de las tres marca la tabla como protegida.
#:
#: **Protegida no quiere decir exenta de poda**, y aquí es donde más se confunde:
#: lo que una tabla protegida rechaza es el modo ``DELETE_ROWS``. ``REDACT`` sigue
#: permitido —es lo que hace hoy ``life_checkins.geom``— y es exactamente el
#: mecanismo con el que el vídeo se poda sin perder la constancia de que existió.
DELETE_GUARDS: tuple[str, ...] = (
    "forbid_update_delete",
    "life_checkin_arco_guard",
    "cctv_purge_guard",
)

#: El rol con el que corre el job. NO es el rol del DSN: el job se degrada a este
#: al abrir la transacción. Es el mismo rol de la API, y por tanto el que la
#: T-2.80 dejó sin ``DELETE`` sobre las doce tablas protegidas. Ver
#: ``ops/prune_pii.harden_session``.
JOB_ROLE = "takab_app"

#: Rol de aplicación (``app.role``) que el job declara. Interno y el más bajo de
#: los dos que ``app_is_takab_internal()`` reconoce: la retención necesita ver
#: todos los tenants, no administrarlos.
JOB_APP_ROLE = "takab_support"

#: Identificadores SQL admisibles. Nada que no case entra en una sentencia.
IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

_ENV_PREFIX = "TAKAB_API_RETENTION_"


@dataclass(frozen=True)
class RetentionRule:
    """Una caducidad: qué columna de qué tabla, con qué reloj y por qué.

    ``clock`` y ``set_clause`` son fragmentos SQL de CÓDIGO, no de datos: viven
    en este módulo y nunca vienen de una petición. Lo único que se interpola como
    dato son ``%(tenant)s`` y ``%(cutoff)s``.
    """

    key: str
    table: str
    columns: tuple[str, ...]
    mode: str
    set_clause: str
    clock: str
    why: str

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise RetentionPlanError(f"{self.key}: modo desconocido {self.mode!r}")
        if not IDENT.match(self.table):
            raise RetentionPlanError(f"{self.key}: nombre de tabla inadmisible {self.table!r}")
        for columna in self.columns:
            if not IDENT.match(columna):
                raise RetentionPlanError(f"{self.key}: columna inadmisible {columna!r}")
        if self.mode == REDACT and not self.set_clause:
            raise RetentionPlanError(f"{self.key}: una regla que redacta necesita `set_clause`")
        if self.mode == REDACT and not self.columns:
            raise RetentionPlanError(f"{self.key}: una regla que redacta necesita columnas")

    @property
    def env_var(self) -> str:
        """``push_tokens.token`` → ``TAKAB_API_RETENTION_PUSH_TOKENS_TOKEN_DAYS``."""
        return _ENV_PREFIX + self.key.upper().replace(".", "_") + "_DAYS"


def dias_configurados(rule: RetentionRule, env: Mapping[str, str] | None = None) -> int | None:
    """Plazo de la regla, o ``None`` si nadie lo configuró.

    ``None`` no es "cero días": es "esta regla no corre". Un valor no entero o
    negativo también deshabilita, y no cae a un default — un plazo mal tecleado
    tiene que dejar el dato en su sitio, no borrarlo antes de tiempo.
    """
    crudo = (env if env is not None else os.environ).get(rule.env_var, "").strip()
    if not crudo:
        return None
    try:
        dias = int(crudo)
    except ValueError:
        return None
    return dias if dias > 0 else None


# ---------------------------------------------------------------------------
# EL PLAN
# ---------------------------------------------------------------------------

_R_TOKEN = (
    "Un push token que lleva meses sin verse es un identificador de dispositivo "
    "que ya no entrega nada y sigue apuntando a una persona: puro pasivo. Se "
    "sustituye por el mismo valor inservible que usa ARCO y la fila queda marcada "
    "revocada. La FILA sobrevive: documenta que hubo un dispositivo registrado."
)

_R_IDENTIDAD = (
    "Nombre y teléfono del roster: el mapeo `sub → persona`, o sea lo que hace "
    "personales a todos los UUID opacos del resto del esquema. Caduca cuando la "
    "persona deja de estar —no cuando su perfil deja de tocarse—, así que el "
    "reloj es `user_deactivations.deactivated_at` y no `updated_at`. Van las dos "
    "columnas en la misma regla porque van en la misma fila: separarlas daría un "
    "perfil con teléfono y sin nombre, o al revés. La FILA sobrevive: es lo que "
    "mantiene el `sub` atado a su tenant y las tablas de hechos coherentes."
)

_R_GEOM = (
    "Ubicación GPS EXACTA de una persona dentro de un edificio. Es dato de "
    "RESCATE mientras el incidente está abierto y puro dato personal en cuanto "
    "cierra: `zone_id` conserva toda la granularidad que el histórico usa. Se "
    "anula la geometría y la fila entera se queda, porque `COUNT(DISTINCT "
    "user_id)` es cuántas PERSONAS confirmaron estar bien y ese número decide si "
    "sube o no una brigada."
)

#: Predicado de diferimiento, calcado del `TK409` de ARCO: con un incidente
#: ABIERTO en el sitio, la ubicación del check-in es información de rescate en
#: vivo y no se toca, tenga la edad que tenga.
_SIN_INCIDENTE_ABIERTO = """
NOT EXISTS (
  SELECT 1 FROM incidents i
   WHERE i.tenant_id = life_checkins.tenant_id
     AND i.site_id   = life_checkins.site_id
     AND i.state <> 'closed' AND i.closed_at IS NULL
)
"""

#: [T-2.81.b] El mismo diferimiento para el NOMBRE, y por la misma razón: con un
#: incidente abierto, el roster es la lista con la que una brigada pregunta
#: "¿quién falta?", y sustituir un nombre por `(titular anonimizado)` a mitad de
#: una búsqueda es el fallo que las reglas de oro 1 y 2 existen para impedir.
#:
#: Se acota al TENANT y no al sitio porque `user_profiles` no tiene sitio: un
#: perfil no vive en un edificio. Es más grosero que el de `life_checkins` a
#: propósito — de los dos errores posibles, aplazar de más solo retrasa la poda,
#: y podar de menos-de-más borra un nombre que alguien está buscando.
_SIN_INCIDENTE_ABIERTO_EN_EL_TENANT = """
NOT EXISTS (
  SELECT 1 FROM incidents i
   WHERE i.tenant_id = user_profiles.tenant_id
     AND i.state <> 'closed' AND i.closed_at IS NULL
)
"""

#: [T-2.81.b] EL RELOJ DE LA BAJA. No es una columna temporal de `user_profiles`
#: —esa era `updated_at`, y describía al empleado estable, no al que se fue—:
#: es el hecho «esta persona ya no está», con su instante, escrito por quien da
#: de baja la cuenta (`routers/users.py`). `reactivated_at IS NULL` es la mitad
#: que impide que una readmisión siga contando plazo.
_BAJA_HACE_MAS_DE = """
EXISTS (
  SELECT 1 FROM user_deactivations d
   WHERE d.tenant_id = user_profiles.tenant_id
     AND d.user_sub  = user_profiles.user_sub
     AND d.reactivated_at IS NULL
     AND d.deactivated_at < %(cutoff)s
)
"""

#: [T-9.80] El mismo reloj de la baja, para los contactos de emergencia del que se
#: fue. Unido por ``(tenant_id, user_sub)``: una baja registrada en otro cliente
#: para el mismo ``sub`` no los alcanza (regla de oro 5).
_BAJA_DEL_TITULAR_HACE_MAS_DE = """
EXISTS (
  SELECT 1 FROM user_deactivations d
   WHERE d.tenant_id = emergency_contacts.tenant_id
     AND d.user_sub  = emergency_contacts.user_sub
     AND d.reactivated_at IS NULL
     AND d.deactivated_at < %(cutoff)s
)
"""

#: [T-9.80] Y el mismo diferimiento que el nombre, acotado al tenant: con un
#: incidente abierto, estos contactos son a quien se avisa si esta persona pide
#: ayuda AHORA — aunque su cuenta se haya dado de baja a mitad del sismo.
_SIN_INCIDENTE_ABIERTO_PARA_CONTACTOS = """
NOT EXISTS (
  SELECT 1 FROM incidents i
   WHERE i.tenant_id = emergency_contacts.tenant_id
     AND i.state <> 'closed' AND i.closed_at IS NULL
)
"""

_AVISO_BORRADO = json.dumps(ERASED_NOTICE_TARGET)

#: [T-9.80 · 0078] El mismo reloj, para los avisos que ya les llegaron a esos contactos.
#: Unido por ``(tenant_id, user_sub)`` como el anterior. La idempotencia compara el
#: ``target`` ENTERO con el estado borrado, y no con ``jsonb_array_length``: WhatsApp y
#: SMS guardan ``to`` como cadena en la misma tabla, y el filtro se evalúa sobre ellas
#: antes del ``EXISTS``.
_AVISO_DE_UN_TITULAR_DADO_DE_BAJA = f"""
target <> '{_AVISO_BORRADO}'::jsonb
AND status <> 'pending'
AND EXISTS (
  SELECT 1 FROM incident_actions a
    JOIN user_deactivations d
      ON d.tenant_id = a.tenant_id AND d.user_sub::text = a.payload->>'user_sub'
   WHERE a.action_id = notification_jobs.action_id
     AND a.tenant_id = notification_jobs.tenant_id
     AND a.kind = 'need_help_contacts'
     AND d.reactivated_at IS NULL
     AND d.deactivated_at < %(cutoff)s
)
"""

_SIN_INCIDENTE_ABIERTO_PARA_AVISOS = """
NOT EXISTS (
  SELECT 1 FROM incidents i
   WHERE i.tenant_id = notification_jobs.tenant_id
     AND i.state <> 'closed' AND i.closed_at IS NULL
)
"""

_R_AVISOS = (
    "Los correos de los contactos de emergencia en los avisos que ya se les "
    "mandaron, de alguien que ya no está. Mismo reloj que los contactos (la BAJA del "
    "titular). Se REDACTA y no se borra: la fila documenta que hubo un aviso, a tal "
    "hora. Un aviso aún `pending` está en vuelo y no se toca."
)

_R_CONTACTOS = (
    "Contactos de emergencia de alguien que ya no está: datos de TERCEROS que "
    "sólo servían para avisarles si el titular pedía ayuda. Caducan con la BAJA "
    "del titular —no con `consented_at` ni `updated_at`: un contacto dado hace años "
    "sigue vigente si el titular sigue dentro—. Se borra la FILA: no documenta "
    "ningún hecho, y anonimizarla dejaría un registro que no significa nada."
)

RETENTION_PLAN: tuple[RetentionRule, ...] = (
    RetentionRule(
        key="push_tokens.token",
        table="push_tokens",
        columns=("token", "endpoint_arn"),
        mode=REDACT,
        # Idéntico al de `privacy_erase_subject`: el mismo dato muerto tiene que
        # verse igual lo haya matado el titular o el reloj.
        set_clause=(
            f"token = '{ERASED_TOKEN_PREFIX}' || push_token_id::text, "
            "endpoint_arn = NULL, "
            "revoked_at = coalesce(revoked_at, now())"
        ),
        # La segunda mitad del reloj es la idempotencia: una fila ya redactada
        # deja de cumplir el predicado, así que la segunda corrida ve cero.
        clock=(
            "last_seen_at < %(cutoff)s "
            f"AND token IS DISTINCT FROM '{ERASED_TOKEN_PREFIX}' || push_token_id::text"
        ),
        why=_R_TOKEN,
    ),
    RetentionRule(
        key="life_checkins.geom",
        table="life_checkins",
        columns=("geom",),
        mode=REDACT,
        # Solo `geom`. El trigger `life_checkin_arco_guard()` rechaza cualquier
        # otra cosa comparando la fila entera con `to_jsonb`, así que esta regla
        # no puede crecer sin que la base la pare.
        set_clause="geom = NULL",
        clock=("geom IS NOT NULL AND created_at < %(cutoff)s AND " + _SIN_INCIDENTE_ABIERTO),
        why=_R_GEOM,
    ),
    RetentionRule(
        key="user_profiles.identity",
        table="user_profiles",
        columns=("display_name", "phone"),
        mode=REDACT,
        # El MISMO estado final que escribe `privacy_erase_subject`, y no uno
        # propio: el dato muerto tiene que verse igual lo haya matado el titular
        # o el reloj. Además hace inerte el orden — ARCO después de la poda (o al
        # revés) encuentra la fila ya en su sitio y no vuelve a tocarla.
        set_clause=(f"display_name = '{ERASED_DISPLAY_NAME}', phone = NULL, updated_at = now()"),
        # Tres mitades y ninguna sobra: la baja vencida (el reloj), la de la
        # idempotencia —una fila ya redactada deja de cumplir el predicado, así
        # que la segunda corrida ve cero— y el diferimiento por incidente abierto.
        clock=(
            _BAJA_HACE_MAS_DE + f"AND (display_name IS DISTINCT FROM '{ERASED_DISPLAY_NAME}' "
            "OR phone IS NOT NULL) AND " + _SIN_INCIDENTE_ABIERTO_EN_EL_TENANT
        ),
        why=_R_IDENTIDAD,
    ),
    RetentionRule(
        key="emergency_contacts.rows",
        table="emergency_contacts",
        # La fila entera: las cuatro columnas que el inventario marca `erase`.
        columns=("display_name", "email", "phone", "user_sub"),
        mode=DELETE_ROWS,
        set_clause="",
        # Idempotente por construcción: una fila borrada no vuelve a cumplir nada.
        # El DELETE lo abre `ec_retention_delete`, que exige sesión interna SIN
        # portador —la del job—, así que el superadministrador de la consola no
        # hereda este borrado.
        clock=_BAJA_DEL_TITULAR_HACE_MAS_DE + "AND " + _SIN_INCIDENTE_ABIERTO_PARA_CONTACTOS,
        why=_R_CONTACTOS,
    ),
    RetentionRule(
        key="notification_jobs.target",
        table="notification_jobs",
        columns=("target",),
        mode=REDACT,
        # El MISMO estado final que escribe `privacy_erase_subject` (0078): ARCO
        # después de la poda, o al revés, encuentra el aviso ya borrado y no lo toca.
        # Sólo `target`, y sólo este valor: es lo único que `takab_app` puede
        # escribir aquí (`nj_solo_borrar_avisos`).
        set_clause=f"target = '{_AVISO_BORRADO}'::jsonb",
        clock=_AVISO_DE_UN_TITULAR_DADO_DE_BAJA + "AND " + _SIN_INCIDENTE_ABIERTO_PARA_AVISOS,
        why=_R_AVISOS,
    ),
)

#: Columnas que ARCO destruye y la retención NO puede tocar por falta de un reloj
#: honesto. Declararlas es la mitad del trabajo: el test recíproco compara este
#: conjunto con el inventario y no deja que una columna se quede sin decisión.
#:
#: **[T-2.81.b] Está VACÍO, y eso es el resultado de la ficha, no un descuido.**
#: Las dos únicas entradas que tuvo —`user_profiles.display_name` y `phone`—
#: decían "el reloj correcto es la baja de la cuenta, que hoy no se registra en
#: ninguna columna". Se registró (`user_deactivations`) y la regla
#: `user_profiles.identity` cuelga de él. La estructura se conserva porque su
#: valor no era la lista: es que `_validar_plan` obliga a que TODA columna
#: `erase` del inventario tenga regla **o** exclusión declarada, así que la
#: siguiente PII sin reloj honesto tendrá que escribir aquí su razón en vez de
#: colarse en silencio.
SIN_RELOJ: dict[tuple[str, str], str] = {}


def _validar_plan() -> None:
    """El plan tiene que cuadrar con el inventario de la T-2.80. Al IMPORTAR.

    Un plan que se sale del inventario está podando algo que nadie clasificó como
    PII; un plan que se queda corto está dejando PII sin decisión. Las dos cosas
    rompen el módulo antes de que arranque nada.
    """
    erase = {k for k, v in PII_INVENTORY.items() if v.action == "erase"}
    cubiertas = {(r.table, c) for r in RETENTION_PLAN for c in r.columns}
    declaradas = set(SIN_RELOJ)

    if sobra := sorted(cubiertas - erase):
        raise RetentionPlanError(
            f"el plan toca columnas que el inventario de PII no marca destruibles: {sobra}"
        )
    if solapan := sorted(cubiertas & declaradas):
        raise RetentionPlanError(f"columnas con regla Y exclusión declarada: {solapan}")
    if faltan := sorted(erase - cubiertas - declaradas):
        raise RetentionPlanError(
            "hay columnas `erase` del inventario sin decisión de retención "
            f"(ni regla ni exclusión en SIN_RELOJ): {faltan}"
        )
    claves = [r.key for r in RETENTION_PLAN]
    if len(set(claves)) != len(claves):
        raise RetentionPlanError(f"claves de regla repetidas: {claves}")


_validar_plan()


# ---------------------------------------------------------------------------
# LA DERIVACIÓN · qué es intocable, según el catálogo y no según este archivo
# ---------------------------------------------------------------------------

#: EL SUELO. No es "la lista de tablas protegidas" —esa se deriva— sino el mínimo
#: que la derivación TIENE que encontrar. Son las cinco que la regla de oro 11
#: nombra por su nombre (``CLAUDE.md §2`` y ``blueprint §9``).
#:
#: Sin este suelo la derivación sería un test que se aprueba a sí mismo: si
#: alguien concede ``DELETE`` sobre ``audit_log`` y le quita el trigger, la tabla
#: se cae del conjunto derivado en silencio y el job la trataría como podable.
#: Con el suelo, esa misma maniobra hace que el job **no arranque**.
COMPLIANCE_ANCHOR: tuple[str, ...] = (
    "audit_log",
    "incident_actions",
    "dictamens",
    "evidence_objects",
    "damage_reports",
)

_Q_PROTECCION = """
SELECT c.relname,
       NOT has_table_privilege(%(role)s, c.oid, 'DELETE') AS sin_privilegio,
       EXISTS (
         SELECT 1 FROM pg_trigger t
         JOIN pg_proc p ON p.oid = t.tgfoid
         WHERE t.tgrelid = c.oid AND NOT t.tgisinternal
           AND p.proname = ANY(%(guards)s)
           AND t.tgenabled <> 'D'
       ) AS guard_activo
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY 1
"""


def protection_report(conn, *, role: str) -> dict[str, tuple[str, ...]]:
    """``tabla → mecanismos que le niegan el DELETE a ``role``, según el catálogo.

    Solo aparecen las tablas con **al menos un** mecanismo; los mecanismos son
    ``"privilegio_ausente"`` y ``"guard_activo"``. Se miran los dos porque cada
    uno tapa el hueco del otro: el privilegio no alcanza al DUEÑO de la tabla, y
    el trigger no alcanza a una tabla que nazca sin él. ``tgenabled <> 'D'``
    importa: un trigger deshabilitado sigue en el catálogo y no para nada.
    """
    filas = conn.execute(_Q_PROTECCION, {"guards": list(DELETE_GUARDS), "role": role}).fetchall()
    informe: dict[str, tuple[str, ...]] = {}
    for nombre, sin_privilegio, guard_activo in filas:
        mecanismos = tuple(
            m
            for m, activo in (
                ("privilegio_ausente", sin_privilegio),
                ("guard_activo", guard_activo),
            )
            if activo
        )
        if mecanismos:
            informe[nombre] = mecanismos
    return informe


def validar_proteccion(informe: Mapping[str, tuple[str, ...]]) -> frozenset[str]:
    """Convierte el informe del catálogo en el conjunto protegido, o revienta.

    Función pura y separada de la consulta a propósito: es LA decisión de esta
    tarea y se puede leer, y probar, sin una base de datos delante.

    Falla CERRADA dos veces:

    * un informe **vacío** es la derivación rota, no un esquema sin evidencia
      —devolver ``frozenset()`` ahí autorizaría al job a borrar de cualquier
      sitio—; y
    * si falta cualquiera de las tablas de ``COMPLIANCE_ANCHOR``, la protección
      de la regla de oro 11 se cayó de la base y el job no corre. Este segundo
      caso es el que impide que la comprobación se apruebe a sí misma: sin el
      suelo, conceder ``DELETE`` sobre ``audit_log`` y quitarle el trigger la
      sacaría del conjunto derivado **en silencio**, y el job la trataría como
      podable.
    """
    protegidas = frozenset(informe)
    if not protegidas:
        raise RetentionUnsafe(
            "la derivación de tablas protegidas devolvió el conjunto vacío. Eso no "
            "es un esquema sin evidencia: es la derivación rota. El job no corre."
        )
    if huecos := sorted(set(COMPLIANCE_ANCHOR) - protegidas):
        raise RetentionUnsafe(
            f"la derivación NO encuentra protegidas a {huecos}, que la regla de oro 11 "
            "nombra explícitamente: ni les falta el privilegio DELETE ni tienen un "
            "guard activo. Alguien desarmó la protección de la evidencia; el job no corre."
        )
    return protegidas


def protected_tables(conn, *, role: str) -> frozenset[str]:
    """Tablas de las que este job **no puede** borrar filas, según el catálogo vivo."""
    return validar_proteccion(protection_report(conn, role=role))
