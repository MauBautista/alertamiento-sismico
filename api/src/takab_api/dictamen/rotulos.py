"""[T-8.12] Lo que la base guarda en inglés, dicho en castellano en el papel.

El papel se entrega en castellano y se imprimían CRUDOS (`A-144`): la severidad
del incidente en la portada (`warning`), el nivel de cada estación en la §7
(`evacuate_or_hold`, partido en dos renglones), el tipo de sensor en la §10
(`STRUCTURAL`), el tipo de objeto en la custodia (`REPORT_PDF`), el autor de cada
acción de la cronología (`system:edge`), el rol, la categoría y la severidad de
cada reporte de daños (`security_guard`, `structural`, `critical`) y el papel de
cada captura del CCTV (`egress`). Es la clase de defecto que `bitacora.py` ya
cerró para los verbos de la cronología: el papel decía `gas_closed` donde la
pantalla dice «VÁLVULAS DE GAS CERRADAS».

## Un valor sin rótulo se DECLARA, no se cuela

Mismo criterio que `bitacora.py`, y por la misma razón: varias de estas columnas
son `jsonb` sin CHECK (`damage_reports.categories`) o tablas append-only exentas
de poda, así que puede llegar un valor que este registro no conozca. Se imprime
con su identificador **y** con el aviso de que no tiene rótulo, en vez de pasar
por castellano.

## Completo por construcción, no por convención

`tests/dictamen/test_rotulos.py` DERIVA cada vocabulario de su fuente —el CHECK
del DDL, `settings.SEVERITY_RANK`/`RANK`, `schemas.mobile`, `cctv.PAPELES`, la
matriz de roles, `incident.classification.CLASIFICACIONES`, `shakemap.calculo.
UMBRALES`— y exige que cada valor tenga rótulo aquí. Un valor nuevo en cualquiera
de ellos pone la suite en rojo en el mismo commit, en vez de salir crudo en el
papel que se entrega.

Los rótulos de nivel son el ESPEJO de los del panel del gabinete
(`edge/takab_edge/local_api/index.html::TIERS`, sin sus glifos): quien lee el
papel y quien miró el panel durante el sismo tienen que reconocer la misma
palabra.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from takab_api.dictamen.bitacora import SIN_ROTULO

# Los AVISOS viven en `model.py` y se importan: el censo de avisos impresos
# (`tests/dictamen/test_avisos_impresos.py`) los deriva de `vars(model)`, y
# declararlos aquí los habría dejado fuera de él.
from takab_api.dictamen.model import (
    CLASIFICACION_NO_LEGIBLE,
    SIN_CLASIFICAR,
    ZONA_POR_DEFECTO,
)

#: `incidents.severity` (CHECK del DDL; espejo en `settings.SEVERITY_RANK`).
SEVERIDAD: dict[str, str] = {
    "info": "INFORMATIVA",
    "watch": "VIGILANCIA",
    "warning": "ADVERTENCIA",
    "critical": "CRÍTICA",
}

#: Nivel del motor de reglas del gabinete (`settings.RANK`). Espejo del panel.
NIVEL: dict[str, str] = {
    "normal": "NORMAL · SIN ALERTA",
    "watch": "VIGILANCIA",
    "restricted": "ACCESO RESTRINGIDO",
    "evacuate_or_hold": "EVACUAR / RESGUARDO",
    "manual_only": "MODO MANUAL — SENSORES DEGRADADOS",
}

#: `sensors.kind` (CHECK del DDL).
SENSOR: dict[str, str] = {
    "structural": "SENSOR ESTRUCTURAL",
    "ground": "SENSOR DE TERRENO",
}

#: `sensors.mount` (CHECK del DDL).
MONTAJE: dict[str, str] = {
    "concrete_column": "en columna de concreto",
    "steel": "en estructura de acero",
    "floor": "en piso",
    "buried": "enterrado",
}

#: `evidence_objects.kind` (CHECK del DDL).
EVIDENCIA: dict[str, str] = {
    "miniseed": "FORMA DE ONDA (miniSEED)",
    "photo": "FOTOGRAFÍA",
    "report_pdf": "INFORME PDF",
    "log": "BITÁCORA",
}

#: `damage_reports.categories[].key` (`schemas.mobile.DAMAGE_CATEGORY_KEYS`). Espejo
#: de las etiquetas del formulario de la app (`mobile/src/features/damage/
#: categories.ts`): el papel dice lo mismo que eligió quien reportó.
CATEGORIA_DE_DANO: dict[str, str] = {
    "structural": "Daño estructural",
    "non_structural": "Daño no estructural",
    "water_leak": "Fuga de agua",
    "gas_leak": "Fuga de gas",
    "electrical": "Daño eléctrico",
    "people_trapped": "Personas atrapadas o heridas",
}

#: `damage_reports.categories[].severity` (`schemas.mobile.DAMAGE_SEVERITIES`).
#: ⚠️ `high` va aunque la API hoy no lo acepta: la app SÍ lo ofrece
#: (`mobile/src/features/damage/categories.ts::SEVERITIES`) y la columna es `jsonb`
#: sin CHECK, así que el día que alguien alinee los dos lados el papel no lo
#: imprime crudo.
SEVERIDAD_DE_DANO: dict[str, str] = {
    "low": "Baja",
    "medium": "Media",
    "high": "Alta",
    "critical": "Crítica",
}

#: Los roles de la matriz RBAC (`auth.matrix.ROLE_ACTION_MATRIX`).
ROL: dict[str, str] = {
    "takab_superadmin": "SUPERADMINISTRACIÓN TAKAB",
    "takab_support": "SOPORTE TAKAB",
    "tenant_admin": "ADMINISTRACIÓN DEL CLIENTE",
    "soc_operator": "OPERACIÓN SOC",
    "gov_operator": "PROTECCIÓN CIVIL",
    "building_admin": "ADMINISTRACIÓN DEL INMUEBLE",
    "inspector": "INSPECTOR",
    "brigadista": "BRIGADISTA",
    "security_guard": "SEGURIDAD",
    "occupant": "OCUPANTE",
}

#: El papel de cada captura del CCTV (`cctv.PAPELES`), con el sentido de
#: `cctv._SIN_FOTO`.
PAPEL_CCTV: dict[str, str] = {
    "pre": "CAPTURA PREVIA A LA SEÑAL",
    "egress": "CAPTURA DE LA MAYOR SALIDA",
    "peak": "CAPTURA DEL AFORO MÁXIMO",
    "reentry": "CAPTURA DEL INICIO DEL REINGRESO",
}

#: El tipo de objeto de vídeo cuando no trae papel (los clips).
TIPO_CCTV: dict[str, str] = {
    "clip": "CLIP DE VÍDEO",
    "captura": "CAPTURA",
}

#: `incident_classifications.classification` (`incident.classification.
#: CLASIFICACIONES`). Espejo de las etiquetas de la consola
#: (`web/src/features/triage/useClassification.ts`).
CLASIFICACION: dict[str, str] = {
    "real": "REAL",
    "falso_positivo": "FALSO POSITIVO",
    "prueba": "PRUEBA",
    "indeterminado": "INDETERMINADO",
    "reproduccion": "REPRODUCCIÓN",
}

#: Los niveles del modelo del mapa de la sacudida (`shakemap.calculo.UMBRALES`).
UMBRAL: dict[str, str] = {
    "pga_watch_g": "umbral de vigilancia",
    "pga_trip_g": "umbral de disparo",
}

#: `seismic_events.source` (CHECK del DDL): quién localizó el epicentro.
FUENTE_DEL_EVENTO: dict[str, str] = {
    "sasmex": "SASMEX",
    "local_quorum": "cuórum de la red propia",
    "manual": "situado a mano por un operador",
    "external": "fuente externa",
}

#: El rol que imprime el FIRMÓ cuando no hay un único rol con la acción de
#: firmar y la persona no tiene nombre registrado.
FIRMANTE_GENERICO = "FIRMANTE AUTORIZADO"


def rotulo(tabla: dict[str, str], valor: str | None) -> str:
    """El rótulo en castellano, o el identificador DECLARADO como sin rótulo.

    Nunca lanza y nunca devuelve vacío: una celda en blanco no dice que falte
    nada. `None` se imprime como ausencia, no como la cadena `None`.
    """
    if valor is None or valor == "":
        return "SIN DATO"
    conocido = tabla.get(valor)
    if conocido is not None:
        return conocido
    return f"{valor} · {SIN_ROTULO}"


def clasificacion(
    valor: str | None,
    en: datetime | None,
    *,
    legible: bool = True,
    zona: str = ZONA_POR_DEFECTO,
) -> str:
    """[T-8.12 · A-053] La línea «CLASIFICACIÓN» de la portada y del ejecutivo.

    Tres casos que no se pueden confundir: clasificada (con su rótulo y cuándo),
    sin clasificar (nadie la revisó) y no legible (quien exporta no puede verla).
    """
    if not legible:
        return CLASIFICACION_NO_LEGIBLE
    if valor is None:
        return SIN_CLASIFICAR
    cuando = f" · clasificada el {instante(en, zona, segundos=False)}" if en else ""
    return f"{rotulo(CLASIFICACION, valor)}{cuando}"


def rol_que_firma() -> str:
    """El rol de quien firma un dictamen, DERIVADO de la matriz y no escrito a fuego.

    Firmar es la acción `sign_dictamen`, que hoy sólo tiene `inspector` (el
    superadmin la tiene negada a propósito: `routers/dictamens.py`). Si mañana la
    tuvieran dos roles, el papel no puede elegir uno: dice «firmante autorizado».
    """
    from takab_api.auth.matrix import roles_with_action  # noqa: PLC0415 - sin ciclo en import

    roles = roles_with_action("sign_dictamen")
    if len(roles) == 1:
        return rotulo(ROL, roles[0])
    return FIRMANTE_GENERICO


def firmante(nombre: str | None) -> str:
    """[T-8.12 · A-145] Lo que imprime el FIRMÓ: el rol y, si lo hay, el nombre.

    Imprimía `dictamens.signed_by` —el `sub` de Cognito, un UUID entero— en la
    línea de más peso del documento. El nombre sale de `user_profiles.display_name`
    si existe; si no, sólo el rol: un nombre inventado sería peor que ninguno.
    """
    rol = rol_que_firma()
    limpio = (nombre or "").strip()
    return f"{rol} · {limpio}" if limpio else rol


#: Autores de sistema de `incident_actions.actor` (`system:<quién>`), por su
#: primer segmento.
_SISTEMA: dict[str, str] = {
    "edge": "gabinete",
    "ingest": "ingesta de la nube",
    "incident": "ciclo del incidente",
    "quorum_engine": "motor de cuórum",
    "notify": "notificaciones",
    "backfill": "recuperación de datos",
    "demo_mode": "modo demostración",
    "config_sync": "sincronización de configuración",
}


def firmantes_de_la_cadena(cadena: Sequence[tuple[str | None, str | None]]) -> dict[str, str]:
    """`sub` → cómo se nombra en la cronología a quien firmó un dictamen de la cadena.

    `cadena` son pares `(signed_by, firmante_nombre)` de la CABEZA a la cola. Quien
    firmó la cabeza sale exactamente como en el FIRMÓ (`firmante`). Quien firmó un
    dictamen ya sustituido sale por su rol y el prefijo de la consola, SIN nombre:
    el papel no imprime en ningún otro sitio el nombre de un firmante sustituido, y
    la cronología no puede ser la puerta por la que entre un dato personal nuevo.
    """
    salida: dict[str, str] = {}
    for i, (sub, nombre) in enumerate(cadena):
        if not sub or sub in salida:
            continue
        salida[sub] = firmante(nombre) if i == 0 else f"{rol_que_firma()} {sub[:8]}"
    return salida


def actor(valor: str, firmantes: Mapping[str, str] | None = None) -> str:
    """Quién hizo una acción de la cronología, en castellano.

    ESPEJO de `actorLabel` de la consola (`web/src/features/triage/
    IncidentTimeline.tsx`) para las personas: «OPERADOR» y los ocho primeros
    caracteres de su identificador, que es lo que el operador ve en pantalla. Un
    nombre aquí sería un dato personal más en un papel que se entrega a terceros,
    y la consola tampoco lo pinta.

    [T-8.12 · 2ª vuelta] Salvo quien FIRMÓ un dictamen de la cadena
    (`firmantes`, de `firmantes_de_la_cadena`): rotularlo «OPERADOR 0f1e2d3c»
    cuatro renglones encima del «FIRMÓ INSPECTOR · <nombre>» lo presentaba como
    otra persona, y con el papel equivocado.
    """
    prefijo, _, resto = valor.partition(":")
    if prefijo == "user":
        if firmantes and resto in firmantes:
            return firmantes[resto]
        return f"OPERADOR {resto[:8]}" if resto else "OPERADOR"
    if prefijo == "system":
        cabeza, _, cola = resto.partition(":")
        quien = _SISTEMA.get(cabeza, cabeza)
        return f"SISTEMA · {quien}" + (f" ({cola})" if cola else "")
    if prefijo == "edge":
        return f"GABINETE {resto}".strip()
    if prefijo == "cloud":
        return f"NUBE · {resto}".strip(" ·")
    return valor


# ─────────────────────────────────────────── [T-8.12 · A-150] la hora local

#: Cómo se llama cada zona en México, en la lengua de quien lee el papel. Lo que no
#: está aquí se imprime con su identificador IANA, que es exacto aunque no bonito.
_NOMBRE_DE_ZONA: dict[str, str] = {
    "America/Mexico_City": "hora del centro",
    "America/Monterrey": "hora del centro",
    "America/Merida": "hora del centro",
    "America/Bahia_Banderas": "hora del centro",
    "America/Cancun": "hora del sureste",
    "America/Mazatlan": "hora del Pacífico",
    "America/Hermosillo": "hora del Pacífico",
    "America/Tijuana": "hora del noroeste",
}


def nombre_de_zona(zona: str) -> str:
    return _NOMBRE_DE_ZONA.get(zona, f"hora local ({zona})")


def instante(cuando: datetime, zona: str = ZONA_POR_DEFECTO, *, segundos: bool = True) -> str:
    """`2026-09-22 18:02:05 UTC · 12:02:05 hora del centro`.

    La UTC va PRIMERO y entera, como hasta ahora: es la que casa con la consola,
    con la bitácora y con el sello del pie. La local va detrás, para quien lee el
    papel en México (`A-150`). Si la fecha local no es la de la UTC —de 18:00 a
    medianoche en el centro— se dice también la fecha local: «02:00 UTC · 20:00»
    sin fecha pondría el suceso en el día equivocado.

    Sin base de zonas horarias NO se inventa un desfase: se declara. (Medido el
    2026-09-22: la imagen de la nube trae `/usr/share/zoneinfo`.)
    """
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=UTC)
    utc = cuando.astimezone(UTC)
    fmt_hora = "%H:%M:%S" if segundos else "%H:%M"
    base = f"{utc:%Y-%m-%d} {utc:{fmt_hora}} UTC"
    try:
        local = utc.astimezone(ZoneInfo(zona))
    except (ZoneInfoNotFoundError, ValueError):
        return f"{base} · hora local no disponible ({zona})"
    fecha = "" if local.date() == utc.date() else f"{local:%Y-%m-%d} "
    return f"{base} · {fecha}{local:{fmt_hora}} {nombre_de_zona(zona)}"


def hora_local(cuando: datetime, zona: str = ZONA_POR_DEFECTO) -> str:
    """`04:00 hora del centro`, o `20:00 del 22/09/2026 hora del centro` si es otro día.

    Para la prosa del ejecutivo, que ya dijo la fecha y la hora UTC y sólo
    necesita la local entre paréntesis.
    """
    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=UTC)
    utc = cuando.astimezone(UTC)
    try:
        local = utc.astimezone(ZoneInfo(zona))
    except (ZoneInfoNotFoundError, ValueError):
        return f"hora local no disponible ({zona})"
    fecha = "" if local.date() == utc.date() else f" del {local:%d/%m/%Y}"
    return f"{local:%H:%M}{fecha} {nombre_de_zona(zona)}"
