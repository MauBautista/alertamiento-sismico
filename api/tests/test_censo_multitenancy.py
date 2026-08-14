"""RO-5.a · El censo de multi-tenancy, derivado del catálogo y en la dirección buena.

Regla de oro 5: *`tenant_id` en toda tabla de negocio + Row-Level Security
default-deny activa.*

EL DEFECTO QUE CIERRA ESTE FICHERO
──────────────────────────────────
La cobertura que existía corría **al revés**. `test_rls_isolation.py` prueba, muy
bien, que las tablas que YA tienen `tenant_id` aíslan de verdad; y varias tablas
nombradas tienen su prueba propia. Lo que nadie derivaba es la otra mitad de la
regla: que TODA tabla de negocio la lleve. Un cruce que parte de "las tablas con
`tenant_id`" **exime a la tabla que no la tiene**: no la tiene ⇒ no entra al
censo ⇒ no se le exige nada. La tabla desprotegida se aprueba a sí misma, que es
la forma exacta que este repo lleva una fase entera cazando.

QUÉ ES UNA "TABLA DE NEGOCIO", Y POR QUÉ EL CRITERIO ES ÉSTE
────────────────────────────────────────────────────────────
Es la decisión de esta tarea, y la tentación es definirla por una propiedad
sustantiva: "las que cuelgan de `tenants` por FK", "las que crea el migrador",
"las que tienen política de escritura". **Todas esas definiciones reintroducen el
mismo defecto.** Cualquier criterio que se apoye en algo que la tabla infractora
no tiene la deja fuera del censo justo por lo que la hace sospechosa: una tabla
nueva sin `tenant_id` tampoco tendría FK a `tenants`, y se auto-eximiría otra vez.

Así que el criterio va al revés, y por eso es **inclusivo por defecto**: es tabla
de negocio TODA relación ordinaria (`relkind = 'r'`) del esquema `public`… menos
las que pertenecen a una **extensión** (`pg_depend.deptype = 'e'`). Y esa única
resta es estructural de verdad: PostGIS y TimescaleDB registran sus tablas como
miembros de su extensión, y nada que escriba este equipo puede acabar siéndolo
por accidente. Hoy la resta se lleva exactamente `spatial_ref_sys`, y un test lo
comprueba —si el filtro dejara de funcionar, el censo pediría `tenant_id` a una
tabla de PostGIS y el fallo sería ruidoso, no silencioso—.

Los chunks y las vistas materializadas de TimescaleDB no hacen falta restarlos:
viven en `_timescaledb_internal`, fuera de `public`. Los caggs son vistas
(`relkind = 'v'`), no relaciones ordinarias.

Todo lo demás entra, y sale solo por una **exención declarada con su razón**. Las
exenciones se comparan por **igualdad**: si alguien arregla una tabla, el test
obliga a borrar su línea. Un `⊆` habría dejado que las razones envejecieran hasta
convertirse en folclore.

TRES FORMAS DE CUMPLIR, NO UNA
──────────────────────────────
"Aislada" no es sinónimo de "tiene RLS". El esquema tiene un conflicto real y
documentado: **TimescaleDB no admite RLS en una hypertable con continuous
aggregates** (timescale/timescaledb#6827), y `waveform_features_1s` los tiene.
Su aislamiento no falta: es de otra forma, y el censo tiene que saber leerla:

* `rls_default_deny` — `ENABLE ROW LEVEL SECURITY` sobre la propia tabla. Eso, y
  no el número de políticas, es lo que la regla de oro llama *default-deny*: con
  RLS activa la tabla niega por defecto y las políticas la ABREN. Una tabla con
  RLS y cero políticas está más cerrada, no menos.
* `vista_barrera` — el aislamiento del crudo. NO basta con que exista una vista
  `security_barrier` encima: eso solo, con la tabla base legible, no aísla nada.
  Hacen falta las tres cosas juntas, y las tres salen del catálogo:
    1. existe una vista con `security_barrier=true` que depende de la tabla,
    2. el rol de la API **no** tiene `SELECT` sobre la tabla base (solo sobre la
       vista) — si lo tuviera, la vista sería decoración, y
    3. esa vista se apoya en al menos una tabla que **sí** tiene RLS activa
       (`sites`, en este esquema): de ahí saca el filtro por tenant.
  Con las tres, "aislada por vista" es una forma de CUMPLIR. Sin ellas, es "sin
  aislamiento", y el censo la nombra.

QUÉ NO MIRA ESTE CENSO (dicho a propósito)
──────────────────────────────────────────
* **`FORCE ROW LEVEL SECURITY`.** FORCE solo alcanza al DUEÑO de la tabla, y el
  dueño no es la API. El esquema tiene tres excepciones deliberadas y razonadas
  en `db/schema.sql` (las hypertables `device_health`/`rule_evaluations`, porque
  los jobs de TimescaleDB corren como el dueño y con FORCE verían cero filas; y
  `tenant_retire_codes`, porque sus funciones `SECURITY DEFINER` tienen que poder
  leer el hash). Meterlo aquí habría añadido tres exenciones más para vigilar un
  vector distinto del de esta regla.
* **Qué DICEN las políticas.** Que una política sea `USING (tenant_id =
  app_tenant_id())` y no `USING (true)` lo prueba `test_rls_isolation.py`
  cruzando tenants de verdad. Este fichero comprueba que el mecanismo EXISTE;
  aquél, que funciona. Los dos hacen falta y ninguno sustituye al otro.
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import reset
from takab_api.privacy.retention import COMPLIANCE_ANCHOR, JOB_ROLE

# ---------------------------------------------------------------------------
# LAS EXENCIONES. Se comparan por IGUALDAD contra lo que diga el catálogo.
# ---------------------------------------------------------------------------

#: Tablas de negocio a las que se les perdona no llevar la columna `tenant_id`,
#: con la razón por la que se les perdona. Enumerar aquí una tabla NO la exime de
#: estar aislada: son dos comprobaciones distintas y esta solo levanta la primera.
SIN_TENANT_ID: dict[str, str] = {
    "alembic_version": (
        "Contabilidad de Alembic: una fila con el identificador de la última "
        "migración aplicada. No la crea `db/schema.sql`, la crea Alembic sola al "
        "primer `upgrade`. Se exime POR SU NOMBRE y no por un criterio "
        "estructural a propósito: cualquier regla que la excluyera sin nombrarla "
        "—«no la crea el migrador», «no tiene FK a tenants»— excluiría también a "
        "la tabla de negocio que alguien cree mañana sin `tenant_id`, que es el "
        "defecto que este fichero cierra."
    ),
    "fw_releases": (
        "Registro de PLATAFORMA (T-2.69): qué firmware EXISTE lo decide TAKAB, no "
        "el cliente, y la fila no pertenece a ningún tenant. Lo que sí es por "
        "cliente —qué gabinete corre qué versión— vive en `gateways`, que sí "
        "lleva `tenant_id`. Su aislamiento es el correcto para lo que la tabla "
        "es: lectura para cualquier rol autenticado, publicación solo para "
        "`takab_superadmin`, y `REVOKE UPDATE, DELETE`."
    ),
    "seismic_events": (
        "Un sismo no pertenece a un cliente. Excepción documentada en "
        "`db/schema.sql` («evento regional = contexto compartido»): la política "
        "de lectura es `app_role() IS NOT NULL` y la escritura solo la hace el "
        "motor de incidentes por `takab_ingest` (BYPASSRLS)."
    ),
    "quorum_votes": (
        "El voto de una estación en una correlación de RED. La tenencia está en "
        "`sensor_id`, y la RLS de `sensors` la tapa: un `sensor_id` ajeno no es "
        "resoluble por otro tenant. Poner `tenant_id` aquí sería contestar bien a "
        "la pregunta equivocada — el quórum es de la red, y por eso lo lee "
        "cualquier rol autenticado."
    ),
    "reference_earthquakes": (
        "Catálogo del SSN ratificado (T-1.46, publicado firmado nube→edge en "
        "T-2.24). Sismos históricos de referencia: dato público del país, no de "
        "un cliente. Solo lo escribe el dueño de la plataforma."
    ),
    "visibility_grants": (
        "Un grant tiene DOS tenants —`grantee_tenant_id` y `target_tenant_id`— y "
        "ningún dueño. Una columna `tenant_id` tendría que elegir uno de los dos "
        "y mentiría sobre el otro, y peor: la RLS que ya existe aísla por "
        "`grantee_tenant_id` (cada quien ve solo los suyos), así que la columna "
        "no añadiría aislamiento, solo una tercera versión de la verdad."
    ),
    "notify_template_quarantine": (
        "Estado del DESPLIEGUE, no de un cliente (T-2.77.c). Es la lista de "
        "plantillas de WhatsApp con las que Meta no nos deja hablar —pausadas o "
        "deshabilitadas por calidad—, y la plantilla pertenece a la cuenta de "
        "negocio de TAKAB: **una sola WABA para toda la flota**. Cuando Meta pausa "
        "una, el canal cae para TODOS los tenants a la vez, así que una columna "
        "`tenant_id` aquí tendría que inventarse un dueño y además mentiría sobre "
        "el alcance real de la caída. Vive en la base y no en la memoria del "
        "worker porque un reinicio levantaba la cuarentena y se volvía a "
        "martillear una plantilla pausada, que es lo que degrada su calificación "
        "de calidad. Su aislamiento es el que corresponde a lo que es: RLS activa "
        "con lectura para cualquier rol autenticado (como `seismic_events`), "
        "escritura solo del worker por `takab_ingest`, y NADIE con DELETE — "
        "levantar una cuarentena es un acto humano deliberado."
    ),
    "ops_alert_notices": (
        "Cadena de OPERACIÓN de la plataforma (T-2.78.a): el aviso que CloudWatch "
        "publicó en el topic de on-call, quién lo acusó y cuándo, y el silencio "
        "cuando nadie contestó. La alarma es de la DLQ, del archivado de WAL o del "
        "disco de la EC2 — de TAKAB, no de un cliente. Una `tenant_id` aquí "
        "tendría que inventarse un dueño (como `notify_template_quarantine`), y "
        "además abriría lo contrario de lo que la regla 5 protege: un cliente "
        "podría VER que el on-call de TAKAB no contestó a las 3 de la mañana. Por "
        "eso su aislamiento NO es 'lo lee cualquier rol autenticado' sino "
        "`app_is_takab_internal()`, que es más estrecho que el de la regla."
    ),
    "pii_retention_runs": (
        "La CONSTANCIA de cada corrida del job de retención de PII (T-2.81.a): "
        "cuándo empezó, en qué modo, si terminó bien y —si no— por qué. Una "
        "corrida recorre a TODOS los clientes de una pasada, así que es un hecho "
        "de la plataforma y no de ninguno de ellos: una `tenant_id` aquí "
        "obligaría a inventarle dueño, o a partir la corrida en tantas filas como "
        "clientes haya y perder justo lo que la fila dice (que la política se "
        "ejecutó ENTERA). Los conteos por cliente sí viajan, dentro de `report`, "
        "donde ningún cliente los alcanza. Su aislamiento no es 'lo lee cualquier "
        "rol autenticado' sino `app_is_takab_internal()`, más estrecho que el de "
        "la regla, y `takab_app` no tiene UPDATE ni DELETE: editar esta fila "
        "sería poder afirmar que se podó lo que no se podó."
    ),
    "ops_oncall_contacts": (
        "Las credenciales de guardia (T-2.78.a): etiqueta de la persona y el HASH "
        "de su secreto de acuse. No es dato de negocio de ningún cliente — es la "
        "lista de quién puede decir 'lo tengo' sobre una alarma de plataforma. Y "
        "va más allá de la exención: la tabla tiene RLS con FORCE y **cero "
        "políticas**, o sea default-deny total, y `takab_app` ni siquiera tiene "
        "SELECT. La única puerta es `app_ops_alert_ack` (SECURITY DEFINER). Una "
        "columna de tenant sería una tercera versión de una verdad que aquí no "
        "existe."
    ),
    "site_ground_refs": (
        "DEUDA DECLARADA, no diseño — es la única de esta lista que no lo es. Son "
        "las referencias de suelo por SITIO (punto cero del calibrador, ATTEN-LAW) "
        "y sí son dato de un cliente. La tenencia se deriva del `site_id` y la RLS "
        "la impone con un `EXISTS` contra `sites`, que sí tiene `tenant_id` y "
        "RLS+FORCE, así que el aislamiento es real y verificable. Lo que falta es "
        "la lectura LITERAL de la regla de oro 5: la columna. Añadirla es una "
        "migración con backfill desde `sites` y tocar dos políticas; mientras no "
        "se haga, esta línea es lo que impide que la ausencia pase por descuido."
    ),
}

#: Tablas de negocio a las que se les perdona no tener NINGÚN mecanismo de
#: aislamiento (ni RLS propia ni vista barrera). El listón es mucho más alto que
#: el de arriba: aquí una línea de más es un agujero de multi-tenancy.
SIN_AISLAMIENTO: dict[str, str] = {
    "alembic_version": (
        "No hay nada que aislar: una fila, un identificador de migración, cero "
        "datos de cliente. Es además la única tabla del esquema que la API no "
        "consulta jamás — solo la toca Alembic, con el usuario de la migración."
    ),
}

# ---------------------------------------------------------------------------
# EL CENSO. Todo sale de pg_catalog; este fichero no enumera ni una tabla buena.
# ---------------------------------------------------------------------------

_Q_CENSO = """
SELECT c.relname,
       EXISTS (
         SELECT 1 FROM pg_attribute a
          WHERE a.attrelid = c.oid AND a.attname = 'tenant_id'
            AND a.attnum > 0 AND NOT a.attisdropped
       ) AS tiene_tenant_id,
       c.relrowsecurity AS rls_default_deny,
       (
         NOT has_table_privilege(%(role)s, c.oid, 'SELECT')
         AND EXISTS (
           SELECT 1
             FROM pg_depend d
             JOIN pg_rewrite rw ON rw.oid = d.objid
             JOIN pg_class v ON v.oid = rw.ev_class
            WHERE d.classid = 'pg_rewrite'::regclass
              AND d.refclassid = 'pg_class'::regclass
              AND d.refobjid = c.oid
              AND v.oid <> c.oid
              AND v.relkind = 'v'
              AND v.reloptions @> ARRAY['security_barrier=true']
              AND has_table_privilege(%(role)s, v.oid, 'SELECT')
              AND EXISTS (
                SELECT 1
                  FROM pg_depend d2
                  JOIN pg_class anc ON anc.oid = d2.refobjid
                 WHERE d2.classid = 'pg_rewrite'::regclass
                   AND d2.objid = rw.oid
                   AND d2.refclassid = 'pg_class'::regclass
                   AND anc.relkind = 'r'
                   AND anc.relrowsecurity
              )
         )
       ) AS vista_barrera
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind = 'r'
  AND NOT EXISTS (
    SELECT 1 FROM pg_depend de
     WHERE de.classid = 'pg_class'::regclass
       AND de.objid = c.oid
       AND de.deptype = 'e'
  )
ORDER BY 1
"""


def censar(conn: psycopg.Connection) -> dict[str, dict[str, bool]]:
    """``tabla de negocio → {tenant_id, rls, vista_barrera}``, según el catálogo."""
    reset(conn)
    filas = conn.execute(_Q_CENSO, {"role": JOB_ROLE}).fetchall()
    return {
        nombre: {"tenant_id": tid, "rls": rls, "barrera": barrera}
        for nombre, tid, rls, barrera in filas
    }


def sin_tenant_id(censo: dict[str, dict[str, bool]]) -> set[str]:
    return {t for t, m in censo.items() if not m["tenant_id"]}


def sin_aislamiento(censo: dict[str, dict[str, bool]]) -> set[str]:
    return {t for t, m in censo.items() if not (m["rls"] or m["barrera"])}


@pytest.fixture
def censo(conn: psycopg.Connection) -> dict[str, dict[str, bool]]:
    return censar(conn)


# ---------------------------------------------------------------------------
# EL SUELO. Sin esto, romper la derivación pondría el censo en verde vacío.
# ---------------------------------------------------------------------------


def test_el_censo_no_esta_vacio(censo: dict[str, dict[str, bool]]) -> None:
    assert censo, (
        "el censo de tablas de negocio salió vacío. Eso no es un esquema sin "
        "negocio: es que la consulta al catálogo dejó de encontrar las tablas, y "
        "con ella todos los tests de abajo pasarían sin comprobar nada."
    )


def test_el_suelo_de_compliance_esta_censado_y_cumple(censo: dict[str, dict[str, bool]]) -> None:
    """Las cinco tablas que la regla de oro 11 nombra por su nombre tienen que
    estar EN el censo y pasarlo enteras. Es el mismo suelo que usa la precondición
    del job de retención (`privacy/retention.COMPLIANCE_ANCHOR`), y por la misma
    razón: lo que ya no se deriva, ya no se revisa."""
    ausentes = sorted(set(COMPLIANCE_ANCHOR) - set(censo))
    assert not ausentes, (
        f"{ausentes} no aparecen en el censo. O dejaron de existir, o la derivación se rompió."
    )
    incumplen = sorted(
        t
        for t in COMPLIANCE_ANCHOR
        if not censo[t]["tenant_id"] or not (censo[t]["rls"] or censo[t]["barrera"])
    )
    assert not incumplen, f"{incumplen} perdieron tenant_id o su aislamiento"


def test_el_filtro_estructural_deja_fuera_lo_que_es_de_una_extension(
    conn: psycopg.Connection, censo: dict[str, dict[str, bool]]
) -> None:
    """La ÚNICA resta del criterio, comprobada en los dos sentidos: `spatial_ref_sys`
    existe como tabla ordinaria de `public` y aun así no está censada, porque es
    miembro de PostGIS. Si el filtro dejara de funcionar, el censo empezaría a
    exigirle `tenant_id` a las tablas de las extensiones — que es ruidoso, pero
    también empujaría a alguien a "arreglarlo" ampliando exenciones."""
    reset(conn)
    existe = conn.execute(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = 'spatial_ref_sys'"
    ).fetchone()[0]
    assert existe == 1, "sin PostGIS instalado esta prueba no mide nada"
    assert "spatial_ref_sys" not in censo, (
        "el filtro de miembros de extensión dejó de funcionar: `spatial_ref_sys` "
        "es de PostGIS y se coló en el censo de tablas de negocio."
    )


# ---------------------------------------------------------------------------
# LA REGLA DE ORO 5, en sus dos mitades. Igualdad, no inclusión.
# ---------------------------------------------------------------------------


def test_toda_tabla_de_negocio_lleva_tenant_id(censo: dict[str, dict[str, bool]]) -> None:
    medido = sin_tenant_id(censo)
    declarado = set(SIN_TENANT_ID)

    sin_declarar = sorted(medido - declarado)
    assert not sin_declarar, (
        f"{sin_declarar}: tablas de negocio SIN columna `tenant_id` y sin exención "
        "declarada. Regla de oro 5. O se les añade la columna, o se añade su línea "
        "a SIN_TENANT_ID con la razón por la que no la llevan — y la razón tiene "
        "que aguantar una lectura, porque la va a leer alguien auditando."
    )
    ya_no_aplica = sorted(declarado - medido)
    assert not ya_no_aplica, (
        f"{ya_no_aplica}: declaradas exentas de `tenant_id` y resulta que YA la "
        "tienen (o ya no existen). Borra su línea de SIN_TENANT_ID: una exención "
        "que sobrevive a su motivo deja de ser una decisión y pasa a ser folclore."
    )


def test_toda_tabla_de_negocio_esta_aislada(censo: dict[str, dict[str, bool]]) -> None:
    medido = sin_aislamiento(censo)
    declarado = set(SIN_AISLAMIENTO)

    desprotegidas = sorted(medido - declarado)
    assert not desprotegidas, (
        f"{desprotegidas}: tablas de negocio SIN ningún mecanismo de aislamiento "
        "—ni RLS default-deny propia, ni vista `security_barrier` con la base "
        "revocada—. Cualquier tenant las lee enteras. Regla de oro 5."
    )
    ya_no_aplica = sorted(declarado - medido)
    assert not ya_no_aplica, (
        f"{ya_no_aplica}: declaradas sin aislamiento y resulta que ya lo tienen "
        "(o ya no existen). Borra su línea de SIN_AISLAMIENTO."
    )


def test_cada_exencion_trae_su_razon() -> None:
    """Una exención sin razón es una lista. La razón es lo que hace que borrarla
    sea barato y mantenerla, caro."""
    mudas = sorted(
        tabla
        for declaradas in (SIN_TENANT_ID, SIN_AISLAMIENTO)
        for tabla, razon in declaradas.items()
        if len(razon.strip()) < 80
    )
    assert not mudas, f"{mudas}: exentas sin una razón que se pueda auditar"


# ---------------------------------------------------------------------------
# LA VISTA BARRERA ES UNA FORMA DE CUMPLIR, NO UN AGUJERO CON PERMISO
# ---------------------------------------------------------------------------


def test_el_crudo_cumple_por_vista_barrera_y_no_por_exencion(
    censo: dict[str, dict[str, bool]],
) -> None:
    """`waveform_features_1s` no puede llevar RLS (TimescaleDB lo prohíbe en una
    hypertable con caggs). No está exenta de nada: está aislada de otra forma, y
    el censo la reconoce por esa forma."""
    crudo = censo["waveform_features_1s"]
    assert crudo["tenant_id"], "el crudo etiqueta cada fila con su tenant"
    assert not crudo["rls"], (
        "si `waveform_features_1s` ya admite RLS es que TimescaleDB levantó la "
        "restricción de los caggs: entonces sobra la vista y sobra esta prueba"
    )
    assert crudo["barrera"], (
        "el crudo dejó de estar aislado por la vista `waveform_features_1s_secure`"
    )
    assert "waveform_features_1s" not in SIN_TENANT_ID
    assert "waveform_features_1s" not in SIN_AISLAMIENTO


def test_una_vista_barrera_sobre_una_base_legible_no_aisla_nada(
    conn: psycopg.Connection,
) -> None:
    """La comprobación de que el reconocimiento de "vista barrera" no es un sello
    de goma. Se le devuelve a `takab_app` el `SELECT` sobre la tabla base —dentro
    de la transacción, que se revierte— y el crudo pasa de "aislado" a "sin
    aislamiento", nombrado. La vista sigue ahí, intacta: sola no aísla nada,
    porque quien quiera puede rodearla."""
    reset(conn)
    conn.execute("GRANT SELECT ON waveform_features_1s TO takab_app")
    caido = censar(conn)
    assert not caido["waveform_features_1s"]["barrera"]
    assert "waveform_features_1s" in sin_aislamiento(caido)
