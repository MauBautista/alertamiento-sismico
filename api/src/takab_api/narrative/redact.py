"""Qué sale de la nube hacia un proveedor de prosa (T-2.42).

**Allowlist, no denylist.** Se enumera campo por campo lo que viaja; cualquier cosa
que se añada al ``ReportModel`` mañana queda fuera por omisión. Una denylist tendría la
polaridad contraria: un campo nuevo saldría solo, y el día que ese campo fuera el nombre
del inmueble o la nota de un ocupante ya sería tarde.

**Nunca salen**: ``site_name``, dirección, coordenadas del sitio o del epicentro,
``user_sub``, ``signed_by``, notas de ocupantes, ``tenant_id``, ``s3_key`` ni hashes de
evidencia. Los reportes de daño entrarían solo como conteo por categoría.

**El FOLIO sí sale, entero, y hay que decirlo** (T-5.27). Esta lista afirmaba que el
``incident_id`` nunca salía, y era falso a medias: el folio lo lleva dentro. Un folio es
``TKB-<código de sitio>-<fecha>-<8 hex del incident_id>-<E|T>``, o sea que por él viajan
**el código del sitio** y un **prefijo del identificador del incidente**.

Se decidió DEJARLO, no recortarlo, por dos razones. (1) El folio es el nombre público
del documento —``folio_of`` lo dice: «se imprime y se cita por teléfono»— y la prosa
tiene que poder nombrar el dictamen que describe; un folio recortado en el texto sería
un folio que no existe, y el que lo teclee no encontrará nada. (2) Lo que viaja no es un
dato personal: es un identificador de documento, estable y correlacionable entre
dictámenes del mismo incidente, que es justo para lo que se diseñó.

**[T-7.27] Lo que esta lista deja pasar desde `D-32`**, y lo que sigue sin pasar por
esas mismas vías —que es donde una ampliación de allowlist se estropea—:

* **la tabla por estación**, sin nombre, sin código y sin el del sensor: cada estación
  de la red es OTRO edificio con gente dentro, y lo que la prosa necesita para citar
  una fila es su ORDEN en la tabla que el documento imprime;
* **la cronología** con su marca de tiempo relativa y la CLASE del actor (`user`,
  `edge`, `system`), nunca el `sub` de Cognito de una persona ni el número de serie de
  un gabinete;
* **los reportes de daño** por ROL y por categoría (`D-32`: «el brigadista aparece por
  rol, nunca por nombre»), jamás sus notas —prosa libre de hasta 2000 caracteres que
  alguien teclea en un teléfono— ni el nombre de la zona, que lo escribe el cliente;
* **las fotografías**, por su propio canal (``imagenes_de``), siempre RE-ENCODADAS y
  —desde `T-7.27·A`— **con la banda de la marca de agua forense TAPADA**.

⚠️ **Esa última no es una precaución de más, y este módulo la había dado por hecha.** La
allowlist de arriba retiene el `sub` de Cognito y las coordenadas del inmueble… del
JSON. La cámara forense del móvil los DIBUJA EN EL PÍXEL de cada fotografía de
evidencia (`GPS 19.43260, -99.13320` y `OP 9f1e4a2c`), y re-encodar quita el EXIF pero
no quita lo que está pintado encima. El sistema se contradecía a sí mismo: los dos
identificadores que esta lista existe para retener viajaban igual, renderizados, a un
tercero y fuera del país. La razón entera, con su medición, en `narrative/marca.py`.

Lo que NO sale por ninguna vía es el ``incident_id`` **completo**, ni el ``event_id``
(ver ``_BASIS_EVIDENCE_KEYS``): con 8 hex se puede correlacionar dos documentos, no
reconstruir el identificador ni cruzarlo con otra tabla. La diferencia entre las dos
cosas la fija ``tests/narrative/test_redact.py``, que ya no borra el folio antes de
mirar.
"""

from __future__ import annotations

import hashlib
import io
import logging
from collections import Counter
from typing import TYPE_CHECKING

from PIL import Image

from takab_api.dictamen.bitacora import ROTULOS
from takab_api.dictamen.model import (
    CCTV_PARCIALMENTE_PURGADO,
    CCTV_PENDIENTE,
    CCTV_PURGADO_SIN_ANALISIS,
    CCTV_SIN_CLIP,
    FELT_LABELS,
    NO_CALIBRATION,
    NO_CCTV,
    NO_SPECTRUM,
    ONDA_NO_LEIDA,
    STATUS_ACTIONS,
    lead_time_text,
)
from takab_api.dictamen.rotulos import FUENTE_DEL_EVENTO, SEVERIDAD, instante, rotulo
from takab_api.documentos import fotos as fotos_mod
from takab_api.felt import ORIGEN_INMUEBLE
from takab_api.narrative.base import (
    DanoRedactado,
    EstacionRedactada,
    HitoRedactado,
    ImagenAdjunta,
    NarrativeFacts,
)
from takab_api.narrative.marca import tapar_banda_forense

if TYPE_CHECKING:  # pragma: no cover - solo para el tipo; evita ciclo de imports
    from takab_api.dictamen.model import ReportModel

log = logging.getLogger("takab_api.narrative")

#: [T-7.27] Fotografías que ve la IA, como MÁXIMO, en todo el documento.
#:
#: El seis es de `D-32` y es el mismo que `documentos/fotos.py` tomó prestado para el
#: papel: compartirlo es lo que hace que la MISMA fotografía tenga una sola huella
#: derivada en los dos sitios. Lo que cambia respecto del papel es el ámbito: allí son
#: seis POR REPORTE y aquí seis por DOCUMENTO, porque lo que hay al otro lado es el
#: tope de una petición HTTP y con N reportes «seis por reporte» no acota nada.
MAX_FOTOS_IA = fotos_mod.MAX_FOTOS_POR_REPORTE

#: Y un tope en NÚMERO de fotos no es un tope de tamaño — es la lección que el PDF ya
#: pagó (`MAX_BYTES_FOTOS_DOCUMENTO`). Se deriva del techo por foto para que subir la
#: calidad de las derivadas mueva esta cota sola en vez de dejarla vieja y callada.
PRESUPUESTO_FOTOS_BYTES = MAX_FOTOS_IA * fotos_mod.MAX_BYTES_SALIDA

#: Clases de actor de `incident_actions`. El identificador va DESPUÉS del primer `:`
#: (`user:<sub>`, `edge:<serie>`, `system:<qué>`) y es lo único que no puede salir.
_CLASES_DE_ACTOR = frozenset({"user", "edge", "system"})
#: Lo que se dice de un actor con otra forma. No se arriesga a partirlo: si mañana
#: alguien escribe el actor de otra manera, esto declara que no se supo clasificar en
#: vez de mandar fuera la mitad de una cadena desconocida.
CLASE_DESCONOCIDA = "otro"

#: Claves del ``basis`` que pueden salir. `event_id` NO está: es un identificador
#: correlacionable, y la prosa no lo necesita para explicar un umbral.
_BASIS_EVIDENCE_KEYS = (
    "severity",
    "pga_g",
    "node_count",
    "corroborated",
    "trigger",
    "pga_source",
    "insufficient_data",
)
_BASIS_PARAM_KEYS = ("pga_no_inhabit_g", "pga_monitor_g")


def redact_basis(basis: dict | None) -> dict:
    """Umbrales y evidencia numérica del dictamen; nada identificable."""
    if not isinstance(basis, dict):
        return {}
    evidence = basis.get("evidence") if isinstance(basis.get("evidence"), dict) else {}
    params = basis.get("params") if isinstance(basis.get("params"), dict) else {}
    out: dict = {}
    version = basis.get("rule_set_version")
    if isinstance(version, str):
        out["rule_set_version"] = version
    ev = {k: evidence[k] for k in _BASIS_EVIDENCE_KEYS if k in evidence}
    pa = {k: params[k] for k in _BASIS_PARAM_KEYS if k in params}
    if ev:
        out["evidence"] = ev
    if pa:
        out["params"] = pa
    return out


#: [T-7.38·M] Estados de vídeo en los que NO hay conteo de evacuación. Se enumeran
#: por estado y no por `t90_s is None`: «análisis disponible» con `t90_s` nulo es un
#: camino real, y condicionar ahí produciría la ausencia «(1) análisis disponible».
_CCTV_SIN_ANALISIS = frozenset(
    {NO_CCTV, CCTV_SIN_CLIP, CCTV_PENDIENTE, CCTV_PURGADO_SIN_ANALISIS, CCTV_PARCIALMENTE_PURGADO}
)
SIN_CONTEO_CCTV = "No hay conteo de evacuación por vídeo para este incidente."
SIN_FUNDAMENTO_REGISTRADO = (
    "El dictamen vigente no registra evidencia instrumental en su fundamento."
)
SIN_UMBRALES_DEL_INMUEBLE = (
    "La sacudida se clasificó con la banda de referencia: no consta configuración de "
    "umbrales del inmueble anterior al incidente."
)


def absences_of(m: ReportModel) -> tuple[str, ...]:
    """Cada dato ausente, con su razón. Es lo que sostiene "Limitaciones".

    Enumerar los huecos es parte del contenido, no un descargo: un dictamen que calla
    lo que no midió afirma más de lo que sabe.
    """
    gaps: list[str] = []
    if m.peak_pga_g is None:
        gaps.append("No hubo aceleración pico medida en la ventana del incidente.")
    if m.peak_pgv_cms is None:
        gaps.append("No hubo velocidad pico medida en la ventana del incidente.")
    if not m.calibrated:
        gaps.append(NO_CALIBRATION)
    if m.felt_band == "unknown":
        gaps.append("La banda de sacudida no pudo determinarse: no hubo medición.")
    if m.lead_time_s is None:
        gaps.append(f"Tiempo de aviso: {lead_time_text(None, m.lead_time_reason)}.")
    if not m.channels:
        gaps.append("No hay features por canal archivadas para este incidente.")
    if m.station_count == 0:
        gaps.append("Ninguna otra estación de la red corroboró el evento.")
    if m.catalog_line is None:
        gaps.append("No hay sismo de catálogo (SSN) asociable a este incidente.")
    if not m.raw_waveform:
        # [T-8.12 · 2ª vuelta] La MISMA derivación que la §3 (`pdf._raw_section`,
        # T-7.38·L): con un miniSEED en la custodia que no se pudo leer, «no tiene
        # miniSEED archivado» lo desmiente el propio papel en la §12.
        consta = any(e.kind == "miniseed" for e in m.evidence)
        gaps.append(m.raw_unavailable_reason or (ONDA_NO_LEIDA if consta else NO_SPECTRUM))
    if m.epicenter_lat is None or m.epicenter_lon is None:
        gaps.append("El evento no tiene epicentro localizado.")
    if not m.dictamens:
        gaps.append("El incidente aún no tiene dictamen registrado.")
    clipped = [c.channel for c in m.channels if c.clipped]
    if clipped:
        gaps.append(
            f"Canales saturados ({', '.join(clipped)}): en ellos el pico registrado es "
            "el techo del convertidor, no la sacudida real."
        )
    # [T-7.38·M] Tres huecos que el documento YA declara en sus secciones y que esta
    # lista no miraba, de modo que podía cerrar con «No se detectaron datos ausentes»
    # una página después de haber declarado dos.
    if m.cctv.estado in _CCTV_SIN_ANALISIS:
        gaps.append(SIN_CONTEO_CCTV)
    # Gateado en que HAYA dictamen: sin él, la línea de arriba ya lo dice y ésta
    # afirmaría un «dictamen vigente» que no existe.
    if m.dictamens and not (m.verdict_basis or {}).get("evidence"):
        gaps.append(SIN_FUNDAMENTO_REGISTRADO)
    if (m.felt_thresholds or {}).get("origen") != ORIGEN_INMUEBLE:
        gaps.append(SIN_UMBRALES_DEL_INMUEBLE)
    # [T-7.22] Y los cinco que trae el informe del evento. Misma razón que el
    # bloque de arriba: el documento CIERRA sobre esta lista, así que un hueco
    # declarado en su sección y ausente aquí deja al papel diciendo «no se
    # detectaron datos ausentes» unas páginas después de haberlo declarado. Ya
    # ocurrió una vez (`T-7.38·M`); esta lista se enumera a mano y es el precio.
    if m.estaciones and not any(e.lat is not None and e.lon is not None for e in m.estaciones):
        gaps.append(
            "Ninguna estación de la red tiene coordenadas registradas: no se pudo "
            "situar el mapa de la red."
        )
    if not m.actions:
        gaps.append("No hay acciones registradas en la bitácora de este incidente.")
    sin_rotulo = [a.kind for a in m.actions if a.kind not in ROTULOS]
    if sin_rotulo:
        gaps.append(
            f"{len(sin_rotulo)} acciones de la cronología se imprimen con su "
            "identificador técnico: no hay rótulo declarado para ellas."
        )
    if not m.danos:
        gaps.append(
            "No hay reportes de daños desde el táctico. Eso no dice que el inmueble "
            "esté sin daños: dice que nadie registró una inspección."
        )
    no_impresas = sum(1 for d in m.danos for f in d.fotos if f.jpeg is None)
    omitidas = sum(d.fotos_omitidas for d in m.danos)
    if no_impresas or omitidas:
        gaps.append(
            f"{no_impresas + omitidas} fotografías de los reportes de daños no se "
            "imprimen en este documento; quedan en el expediente de evidencia."
        )
    return tuple(gaps)


def _razon_de_persona(m: ReportModel) -> bool:
    """[T-7.38·E] ¿Firmó una persona Y escribió por qué?

    La conjunción no es adorno: `sign_dictamen` inserta `basis = {}` cuando no hay
    nota, y `dictamen/rules.py` mete `notes` ENLATADO («dictamen automático
    preliminar») en todos los automáticos. Con la clave sola, una cadena de fábrica
    pasaría por el fundamento de un veredicto; con `verdict_signed` solo, un firmado
    sin razón sería indistinguible de uno con razón.
    """
    if not m.verdict_signed:
        return False
    nota = (m.verdict_basis or {}).get("notes")
    return isinstance(nota, str) and bool(nota.strip())


def _clase_de_actor(actor: str | None) -> str:
    """`user:9f1e-…` → `user`. La persona y el aparato se quedan aquí.

    El actor de `incident_actions` es `user:<sub de Cognito>`, `edge:<serie del
    gabinete>` o `system:<qué>`. Lo que la prosa necesita para contar la historia es si
    lo hizo una persona, el gabinete o el sistema; lo de después del `:` identifica a
    una persona concreta o a un aparato concreto, que es lo que esta lista existe para
    retener.
    """
    cabeza = (actor or "").split(":", 1)[0].strip().lower()
    return cabeza if cabeza in _CLASES_DE_ACTOR else CLASE_DESCONOCIDA


def _estaciones(m: ReportModel) -> tuple[EstacionRedactada, ...]:
    """La tabla de la §7, con sus cifras y sin la identidad de los vecinos."""
    return tuple(
        EstacionRedactada(
            orden=i,
            propia=e.site_code == m.site_code,
            dist_km=e.dist_km,
            t_teorico_s=e.t_teorico_s,
            t_medido_s=e.t_medido_s,
            peak_pga_g=e.peak_pga_g,
            umbral_pga_g=e.umbral_pga_g,
            umbral_origen=e.umbral_origen,
            tier=e.tier,
        )
        for i, e in enumerate(m.estaciones, start=1)
    )


def _cronologia(m: ReportModel) -> tuple[HitoRedactado, ...]:
    """La bitácora con su reloj puesto a cero en la apertura del incidente."""
    return tuple(
        HitoRedactado(
            t_desde_apertura_s=round((a.ts - m.opened_at).total_seconds(), 1),
            kind=a.kind,
            rotulo=ROTULOS.get(a.kind),
            actor=_clase_de_actor(a.actor),
        )
        for a in m.actions
    )


def _fotos_de(d) -> int:  # noqa: ANN001 - `DanoFila`, sin importarlo en runtime
    """Cuántas fotografías tiene ESE reporte, contando las que el papel no imprimió.

    `fotos_omitidas` son las que quedaron fuera del tope del documento: existen en el
    expediente y el incidente las tiene. Callarlas aquí haría que el prompt declarara
    menos fotografías de las que hay, que es la mentira que esta cuenta evita.
    """
    return len(d.fotos) + max(0, d.fotos_omitidas)


def _danos(m: ReportModel, imagenes: tuple[ImagenAdjunta, ...]) -> tuple[DanoRedactado, ...]:
    """Los reportes del brigadista: rol, categorías y cuántas fotos de cada uno viajan."""
    por_reporte = Counter(i.reporte for i in imagenes)
    return tuple(
        DanoRedactado(
            orden=i,
            rol=d.rol,
            personas_en_riesgo=bool(d.personas_en_riesgo),
            categorias=tuple(
                (str(c.get("key")), str(c.get("severity")))
                for c in (d.categorias or [])
                if isinstance(c, dict)
            ),
            fotos_adjuntas=por_reporte.get(i, 0),
            fotos_no_adjuntas=max(0, _fotos_de(d) - por_reporte.get(i, 0)),
        )
        for i, d in enumerate(m.danos, start=1)
    )


def _conteo_de_danos(m: ReportModel) -> tuple[tuple[str, int], ...]:
    """Cuántos reportes de cada categoría. El `key` es de un catálogo cerrado
    (`schemas/mobile.DAMAGE_CATEGORY_KEYS`); la `note` de la categoría, no."""
    claves = Counter(
        str(c.get("key"))
        for d in m.danos
        for c in (d.categorias or [])
        if isinstance(c, dict) and c.get("key")
    )
    return tuple(sorted(claves.items()))


#: Claves de metadatos que una derivada de `preparar` puede traer, y **solo esas**.
#: Allowlist y no denylist, por la misma razón que el resto de este módulo: mañana
#: aparece un bloque nuevo y con una lista negra saldría solo.
#:
#: MEDIDO sobre la salida de `documentos/fotos.preparar` con Pillow 12.3.0: son las
#: cuatro claves del segmento JFIF y nada más. Lo que esto deja fuera a propósito es
#: **XMP** y **IPTC**, que es donde Android escribe el GPS y el autor: `getexif()` no
#: los ve, así que la comprobación anterior —«no lleva EXIF»— daba por buena una
#: imagen con las coordenadas dentro por otra puerta.
_METADATOS_DE_UNA_DERIVADA = frozenset({"jfif", "jfif_version", "jfif_unit", "jfif_density"})


def _es_derivada(jpeg: bytes | None) -> bool:
    """¿Estos bytes son una derivada de ``documentos/fotos.preparar``?

    **Por qué se verifica en vez de confiar.** Hoy el único que rellena `FotoFila.jpeg`
    es el builder, y siempre con la derivada. Mañana, un camino nuevo que ponga ahí lo
    que bajó de S3 mandaría a un tercero **la marca del teléfono y la cadena de
    ubicación del EXIF** — medido en `T-7.22`, cuando ese mismo blob acababa dentro del
    PDF (`tests/documentos/test_fotos.py`). Aquel día el destinatario era un documento
    de la propia organización; aquí es un proveedor en otro país.

    Se comprueban TRES propiedades, y cada una tiene su prueba **discriminada**: es
    JPEG, no pasa del lado máximo y no trae ningún bloque de metadatos fuera de los
    cuatro del JFIF. Solo se lee la CABECERA — no se decodifica la imagen, así que una
    bomba de descompresión no llega a expandirse aquí.

    ⚠️ [T-7.27·A] **Eran cuatro y ahora son tres, y la que se fue es la del EXIF.** Lo
    medido: las dos primeras se solapaban sobre el único fixture que las ejercía —1600×1200
    con EXIF— y se podían borrar de una en una sin que nada se pusiera rojo; y al añadir la
    allowlist de metadatos, `not dict(im.getexif())` quedó SUBSUMIDA, porque en un JPEG el
    EXIF es el bloque `info["exif"]` y ya lo rechaza la lista. Medido también: quitando
    aquella línea, las 273 pruebas seguían verdes. Una comprobación que ninguna prueba
    puede matar no es una comprobación, así que se deja UNA con su prueba en vez de dos
    donde una sobra. Lo que sostiene la equivalencia —que un JPEG con EXIF siempre trae
    `info["exif"]`— es una propiedad de Pillow, y por eso tiene test propio: el día que
    deje de ser cierta, se pone rojo.
    """
    if not jpeg:
        return False
    try:
        with Image.open(io.BytesIO(jpeg)) as im:
            if im.format != "JPEG" or max(im.size) > fotos_mod.LADO_MAX:
                return False
            return not (set(im.info) - _METADATOS_DE_UNA_DERIVADA)
    except Exception:  # noqa: BLE001 - lo que no se puede verificar, no sale
        return False


def imagenes_de(m: ReportModel) -> tuple[ImagenAdjunta, ...]:
    """Las fotografías que viajan al proveedor. Allowlist también aquí (`D-32`).

    Cuatro cotas, y ninguna es decorativa: **seis** fotos (`MAX_FOTOS_IA`), el
    **presupuesto de bytes** (`PRESUPUESTO_FOTOS_BYTES`), la **verificación** de que
    cada blob es una derivada y —desde `T-7.27·A`— el **tapado de la banda de la marca
    de agua forense** (`narrative/marca.py`), que lleva DIBUJADOS en el píxel las
    coordenadas del inmueble y el identificador del operador. Lo que no pasa las cuatro
    no sale, y el hueco se declara en los hechos (`DanoRedactado.fotos_no_adjuntas`) en
    vez de desaparecer.

    El presupuesto se cobra sobre **lo que viaja**, no sobre la derivada del papel: son
    bytes distintos desde que hay tapado, y cobrar los otros dejaba el peso real de la
    petición sin cota.
    """
    salida: list[ImagenAdjunta] = []
    gastado = 0
    for orden, d in enumerate(m.danos, start=1):
        for f in d.fotos:
            if len(salida) >= MAX_FOTOS_IA:
                return tuple(salida)
            if not _es_derivada(f.jpeg):
                if f.jpeg:
                    log.warning(
                        "narrative: una foto del reporte %s no es una derivada y NO se manda", orden
                    )
                continue
            tapada = tapar_banda_forense(f.jpeg)
            if not tapada.ok:
                log.warning(
                    "narrative: una foto del reporte %s NO se manda: %s", orden, tapada.motivo
                )
                continue
            assert tapada.jpeg is not None  # noqa: S101 - lo garantiza `ok`
            if gastado + len(tapada.jpeg) > PRESUPUESTO_FOTOS_BYTES:
                continue
            gastado += len(tapada.jpeg)
            salida.append(
                ImagenAdjunta(
                    jpeg=tapada.jpeg,
                    sha256=f.sha256_impreso,
                    sha256_enviado=hashlib.sha256(tapada.jpeg).hexdigest(),
                    ancho=f.ancho,
                    alto=f.alto,
                    reporte=orden,
                )
            )
    return tuple(salida)


def facts_from(m: ReportModel, *, imagenes: tuple[ImagenAdjunta, ...] = ()) -> NarrativeFacts:
    """Hechos redactados del dictamen. Solo lo enumerado aquí sale de la nube.

    ⚠️ [T-7.27] `damage_counts` **era un parámetro muerto**: el canal existía y el
    único llamador de producción (`routers/reports.py`) no lo pasaba, así que el conteo
    viajaba vacío en todos los dictámenes reales mientras el dato estaba en el modelo,
    a un `Counter` de distancia. Se deriva, y el parámetro se va: un canal que solo un
    test puede rellenar es un campo que en producción no existe.

    `imagenes` entra —en vez de calcularse aquí— para que el número que los hechos
    declaran y la tupla que se adjunta SEAN LO MISMO: si cada uno lo calculara por su
    lado, el prompt podría decir «seis fotografías» con cinco dentro.
    """
    counts = tuple(sorted(Counter(a.kind for a in m.actions).items()))
    return NarrativeFacts(
        folio=m.folio,
        # [T-8.12 · 2ª vuelta] La apertura, la severidad y la fuente del epicentro
        # viajan como las IMPRIME el papel, no como las guarda la base: la prosa
        # —la de la IA y la determinista— las repetía tal cual, y el §16 salía con
        # «severidad warning», «fuente: local_quorum» y un instante ISO sólo en
        # UTC. La apertura lleva la hora local del inmueble junto a la UTC
        # (`rotulos.instante`): lo que sale con ella es el NOMBRE de la zona
        # («hora del centro»; su identificador IANA si no tiene nombre), que abarca
        # estados enteros —ni coordenadas ni dirección—.
        opened_at=instante(m.opened_at, m.zona_horaria),
        severity=rotulo(SEVERIDAD, m.severity),
        trigger=m.trigger,
        opened_trigger=m.opened_trigger,
        state=m.state,
        # Sin fuente, el hecho es la AUSENCIA (`None`), no la cadena «SIN DATO».
        event_source=rotulo(FUENTE_DEL_EVENTO, m.event_source) if m.event_source else None,
        verdict_label=m.verdict_label,
        verdict_status=m.verdict_status,
        verdict_signed=m.verdict_signed,
        verdict_actions=STATUS_ACTIONS.get(m.verdict_status or "", ()),
        rule_set_version=m.rule_set_version,
        basis=redact_basis(m.verdict_basis),
        reason_recorded=_razon_de_persona(m),
        site_criticality=m.site_criticality,
        felt_band=m.felt_band,
        felt_label=FELT_LABELS.get(m.felt_band, FELT_LABELS["unknown"]),
        calibrated=m.calibrated,
        peak_pga_g=m.peak_pga_g,
        peak_pgv_cms=m.peak_pgv_cms,
        lead_time=lead_time_text(m.lead_time_s, m.lead_time_reason),
        station_count=m.station_count,
        catalog_line=m.catalog_line,
        stations=_estaciones(m),
        reproduccion=bool(m.reproduccion),
        channel_count=len(m.channels),
        clipped_channels=tuple(c.channel for c in m.channels if c.clipped),
        action_counts=counts,
        damage_counts=_conteo_de_danos(m),
        timeline=_cronologia(m),
        damage_reports=_danos(m, imagenes),
        photos_attached=len(imagenes),
        photos_available=sum(_fotos_de(d) for d in m.danos),
        dictamen_count=len(m.dictamens),
        has_epicenter=m.epicenter_lat is not None and m.epicenter_lon is not None,
        has_raw_waveform=bool(m.raw_waveform),
        has_archived_miniseed=any(e.kind == "miniseed" for e in m.evidence),
        absences=absences_of(m),
    )
