"""Modelo del dictamen (T-2.41): PURO, sin fpdf ni DB.

Separar el modelo del render permite probar el CONTENIDO —que es donde puede haber una
mentira— sin abrir un PDF. La regla que gobierna todo el módulo: **un dato ausente
produce un literal de ausencia con su razón, nunca 0, nunca cadena vacía, nunca un
guion suelto.** Un "0.000 g" en un dictamen que acabará ante Protección Civil no es un
detalle de formato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from takab_api.compliance import ComplianceDocument
from takab_api.dictamen.duracion import Duracion
from takab_api.dictamen.espectrograma import Espectrograma
from takab_api.documentos.huella import content_sha256 as huella_de_contenido

STATUS_LABELS: dict[str, str] = {
    "no_inhabit_inspect": "NO HABITAR · INSPECCIÓN",
    "inhabit_monitor": "HABITAR · MONITOREO",
    "normal_operation": "OPERACIÓN NORMAL",
    "restricted": "ACCESO RESTRINGIDO",
}

#: Qué hacer con cada veredicto. Tabla FIJA, no generada: son instrucciones de
#: seguridad y no pueden depender de nada que varíe entre dos ejecuciones.
STATUS_ACTIONS: dict[str, tuple[str, ...]] = {
    "no_inhabit_inspect": (
        "No reingresar al inmueble hasta contar con inspección estructural.",
        "Mantener el perímetro y las rutas de evacuación despejadas.",
        "Solicitar evaluación de un ingeniero estructural con responsiva.",
    ),
    "restricted": (
        "Restringir el acceso a las zonas señaladas por el responsable del inmueble.",
        "Documentar daños visibles antes de mover nada.",
        "Programar inspección estructural.",
    ),
    "inhabit_monitor": (
        "Se puede ocupar el inmueble; mantener vigilancia de daños visibles.",
        "Reportar grietas nuevas, puertas que dejan de cerrar o ruidos estructurales.",
        "Conservar la evidencia de este evento para la próxima revisión.",
    ),
    "normal_operation": (
        "Operación normal.",
        "Sin acciones adicionales derivadas de este evento.",
    ),
}

#: [T-7.33] Lo que el deslinde afirma SIEMPRE, firmado o no. La frase que
#: describe el ESTADO del documento no vive aquí: se deriva de si hay firma
#: (`pdf._closing`), porque escrita a fuego llamaba PRELIMINAR a un dictamen
#: firmado, en la misma página en la que el banner decía FIRMADO.
DISCLAIMER = (
    "No sustituye la evaluación estructural formal ni certifica reingreso "
    "seguro sin firma de ingeniería."
)

#: Las dos primeras frases del deslinde, según el documento tenga firma o no.
DISCLAIMER_ESTADO = {
    False: "Dictamen operativo PRELIMINAR generado por TAKAB Ailert a partir de "
    "evidencia instrumental.",
    True: "Dictamen operativo FIRMADO por inspector, sobre evidencia instrumental de TAKAB Ailert.",
}

TS_FMT = "%Y-%m-%d %H:%M:%S UTC"

#: Rótulos de ausencia. Existen como constantes para que un test pueda exigirlos y
#: para que no se cuele un "—" suelto que no explica nada.
ABSENT = "SIN DATO"
NO_CALIBRATION = (
    "SIN FUENTE DE CALIBRACIÓN DECLARADA · las aceleraciones y velocidades de este "
    "documento son valores RELATIVOS del sensor, no unidades físicas."
)
NO_SPECTRUM = (
    "ANÁLISIS ESPECTRAL NO DISPONIBLE. Requiere la forma de onda cruda; el "
    "sistema no la transmite en continuo (solo sube a evidencia en eventos "
    "confirmados). Este incidente no tiene miniSEED archivado."
)
#: [T-7.38·L] El caso que `NO_SPECTRUM` trataba como el mismo: SÍ consta un objeto
#: miniSEED en la cadena de custodia —el §10 de este documento imprime su sha256—
#: y lo que falló fue LEERLO. Decir «no tiene miniSEED archivado» ahí es falso, y
#: lo desmiente el propio papel cuarenta líneas más abajo.
ONDA_NO_LEIDA = (
    "ANÁLISIS ESPECTRAL NO DISPONIBLE. Consta un objeto miniSEED registrado en la cadena "
    "de custodia de este incidente, con su sha256 impreso en este mismo documento; esta "
    "exportación no obtuvo traza de él. Que el objeto esté registrado no garantiza que "
    "siga siendo recuperable ni legible."
)
NO_GEOMETRY = "SIN GEOMETRÍA REGISTRADA · no se puede dibujar el croquis del evento."
#: [T-7.22] La misma ausencia, en la otra figura. Se dice aparte y no se
#: reutiliza `NO_GEOMETRY` porque aquélla nombra el croquis del evento: leerla
#: bajo «RED DE ESTACIONES» haría pensar que falló el dibujo de otra sección.
SIN_GEOMETRIA_DE_RED = (
    "SIN GEOMETRÍA REGISTRADA PARA LA RED · ninguna estación tiene coordenadas "
    "y no se puede situar el mapa. La tabla de arribos que sigue no depende de esto."
)
#: [T-3.12.c] Los tres estados del CCTV. Se distinguen porque significan cosas OPUESTAS y
#: se leerían igual si el reporte solo dijera «sin datos».
NO_CCTV = (
    "SIN COBERTURA CCTV DECLARADA · este sitio no tiene cámara configurada. La ausencia "
    "de análisis de evacuación en este documento no indica que nadie evacuara."
)
CCTV_SIN_CLIP = (
    "CÁMARA DECLARADA · sin clip para este incidente. Grabó o no grabó, pero el vídeo no "
    "llegó a la nube: revísese el gabinete antes de leer esto como «no hubo evacuación»."
)
CCTV_PENDIENTE = (
    "CLIP DISPONIBLE · ANÁLISIS PENDIENTE. El vídeo está archivado y todavía no se ha "
    "contado: las cifras de evacuación llegarán en una versión posterior del documento."
)
CCTV_PURGADO_SIN_ANALISIS = (
    "CLIP PURGADO POR RETENCIÓN · SIN ANÁLISIS. El vídeo se destruyó al vencer su plazo de "
    "retención y no consta conteo de evacuación para este incidente. Permanece la custodia "
    "—sha256 y ventana— en la lista siguiente."
)
CCTV_PARCIALMENTE_PURGADO = (
    "CLIP PARCIALMENTE PURGADO POR RETENCIÓN · ANÁLISIS PENDIENTE. Parte del vídeo de este "
    "incidente se destruyó al vencer su plazo de retención; lo que queda no se ha contado. "
    "La lista siguiente dice de cada objeto si sigue archivado."
)
CCTV_PURGADO = "PURGADO (retención de vídeo)"
EPICENTRO_REUBICADO = (
    "EPICENTRO REUBICADO A MANO POR UN OPERADOR. No es el centroide de las estaciones ni "
    "una localización sísmica calculada."
)
#: La trazabilidad se AÑADE, y solo cuando consta aquí: un evento de red es
#: COMPARTIDO entre inmuebles, así que la acción puede vivir en el incidente de otro.
#: Afirmar «consta en la bitácora» sin mirarla haría que el papel contradijera a su
#: propia §10.
EPICENTRO_REUBICADO_AQUI = " La reubicación consta en la bitácora de este incidente."
EPICENTRO_REUBICADO_EN_LA_RED = (
    " La reubicó un operador de la red sobre el evento compartido; no consta en la "
    "bitácora de este incidente."
)
CENTROID_NOTE = (
    "EPICENTRO = CENTROIDE DE LAS ESTACIONES QUE DETECTARON EL SISMO. No es una "
    "localización sísmica: está entre las estaciones, no en la falla."
)
SKETCH_NOTE = "SIN CARTOGRAFÍA BASE · PROYECCIÓN EQUIRECTANGULAR LOCAL"
ENVELOPE_NOTE = (
    "ENVOLVENTE DE PICO POR SEGUNDO (1 Hz). NO es la forma de onda cruda: el sistema "
    "no transmite el crudo en continuo."
)
#: [T-5.07] Aviso de asistencia automatizada. Vivía como literal dentro de
#: `pdf.py`, así que el censo de avisos impresos —que se DERIVA de este módulo— no
#: podía verlo, y era justo el aviso con la regla más fácil de romper: **solo debe
#: salir cuando la prosa NO la escribió el proveedor determinista**. El render le
#: añade la versión del rule_set; lo que se fija aquí es la frase que un lector
#: reconoce.
NARRATIVE_AI_NOTE = (
    "Las secciones en prosa se redactaron con asistencia automatizada. El "
    "VEREDICTO y todos los valores medidos de este documento son deterministas"
)

#: [T-7.22] La leyenda que un documento firmado NO puede callarse. El evento de
#: una reproducción trae el epicentro y la magnitud de un sismo HISTÓRICO: sin
#: esta frase, el papel afirma con todas las letras que el 19-S de 2017 ocurrió
#: hoy en este inmueble. Es el riesgo residual que `db/schema.sql` deja escrito
#: al lado de `meta.reproduccion`, y la consola ya lo rotula — el papel no.
#:
#: Va como TEXTO del cuerpo, no como rótulo dentro del dibujo: la meta de F4
#: exige encontrar «REPRODUCCIÓN» extrayendo el texto del PDF, y lo que se pinta
#: dentro de una figura se extrae mal o no se extrae.
REPRODUCCION_NOTE = (
    "REPRODUCCIÓN: este incidente se construyó sobre un sismo HISTÓRICO del "
    "catálogo para ensayo. El epicentro, la magnitud y los arribos son los de "
    "aquel evento; la sacudida de este inmueble NO ocurrió."
)

#: [T-7.22] Cuando la bitácora del incidente está vacía. No es lo mismo que
#: «no pasó nada»: `incident_actions` recoge lo que hicieron el gabinete, la nube
#: y las personas, y que no haya ni una fila es un hecho sobre el incidente que
#: merece decirse —y que en un incidente con sirena disparada sería un defecto—.
SIN_CRONOLOGIA = (
    "SIN ACCIONES REGISTRADAS PARA ESTE INCIDENTE: ni el gabinete, ni la nube, ni "
    "ninguna persona dejaron constancia de una acción en la bitácora."
)

#: [T-7.22] El recuento de verbos que el documento no supo traducir. Marcar las
#: filas no basta: quien audita tiene que poder saber de un vistazo cuánto de la
#: cronología se entrega sin rotular.
#:
#: El número va al FINAL y no delante a propósito: con el recuento por delante la
#: frase habría que declinarla («1 acciones») y un documento firmado no puede
#: permitirse esa errata. Así la constante es una sola y vale para cualquier
#: cantidad.
CRONOLOGIA_SIN_ROTULO = (
    "Hay acciones sin rótulo declarado: se imprimen con su identificador técnico y su "
    "significado está en el registro de la consola. Filas afectadas: "
)

#: [T-7.22] Cuando nadie reportó daños desde el táctico. No es «el edificio está
#: bien»: es que nadie entró a mirarlo, o que quien entró no reportó. Un hueco
#: mudo aquí se lee como «sin daños», que es una afirmación que este documento no
#: puede hacer.
SIN_DANOS = (
    "SIN REPORTES DE DAÑOS DESDE EL TÁCTICO. La ausencia de reportes NO significa "
    "que el inmueble esté sin daños: significa que nadie registró una inspección."
)

#: [T-7.22] `D-32` manda que el brigadista aparezca por ROL, nunca por nombre. Si
#: la asignación ya no existe se dice, en vez de rellenar con «brigadista» por
#: costumbre: quien firma el documento no puede afirmar un rol que no consta.
ROL_NO_RESUELTO = "rol no resuelto en el padrón del inmueble"

#: [T-7.22] Lo más importante que puede decir un reporte de campo. No puede
#: quedarse como una casilla más de la tabla de categorías.
PERSONAS_EN_RIESGO = (
    "PERSONAS EN RIESGO REPORTADAS EN ESTE PUNTO por quien hizo la inspección. "
    "Este documento no verifica ese reporte: lo registra tal como se recibió."
)

#: [T-7.22] Un reporte con fotografías y sin categorías es válido —el brigadista
#: fotografió y no clasificó— y el papel lo dice en vez de dejar la tabla ausente.
SIN_CATEGORIAS = (
    "Este reporte no clasificó el daño por categorías; lo que sigue son sus "
    "observaciones y fotografías tal como se recibieron."
)

#: [T-7.22] El recuento de fotografías que NO entraron. Entregar seis de once sin
#: decirlo es recortar la evidencia en silencio. El número va al final por la
#: misma razón que en la cronología: para no tener que declinar la frase.
FOTOS_OMITIDAS = (
    "Este reporte tiene más fotografías de las que el documento imprime; el resto "
    "queda en el expediente de evidencia. Impresas: "
)

#: [T-7.22] El hueco del mapa de intensidad, declarado POR SU CAUSA.
#:
#: ⚠️ La ficha pedía literalmente «NO DISPONIBLE · SIN MAGNITUD hasta `T-7.24`», y
#: esa frase se escribe aquí de otra manera a propósito. Dos razones medidas:
#:
#: 1. **«sin magnitud» es falso en el escenario de la demostración.** Un evento de
#:    reproducción SÍ trae magnitud —la del sismo histórico— y la §8 la imprime en
#:    la línea de catálogo. Un papel que diga «no hay mapa porque no hay magnitud»
#:    tres páginas después de imprimir «M 7.1» se desmiente a sí mismo, que es la
#:    familia de defectos que costó `T-7.34`, `T-7.38` y `T-7.39`.
#: 2. **La causa real está escrita en otro sitio:** la viñeta
#:    `[DIFERIDO · mini-ShakeMap]` de `blueprint §14`, que sólo `T-7.24` puede
#:    derogar. Nombrarla es lo que permite que el día que se derogue alguien
#:    encuentre esta frase.
#:
#: El texto anterior decía «TAKAB no las calcula», que era categórico y que
#: `T-7.24` volverá falso dentro de dos fichas — una frase ya impresa en
#: documentos firmados que habría que derogar.
NO_MMI = (
    "No se reporta mapa de intensidad macrosísmica (MMI) ni isosistas: el cálculo "
    "está DIFERIDO y su ficha es T-7.24. No depende del dato de este incidente. "
    "La banda que sigue es la sacudida MEDIDA por el sensor del propio inmueble."
)

#: [T-5.11] Lo que se imprime cuando NINGÚN sismo del catálogo es éste y no había
#: siquiera candidatos en la ventana. Decía «SIN COINCIDENCIA EN CATÁLOGO», que
#: sonaba a fallo de búsqueda; lo que afirma es un HECHO sobre el evento —el
#: catálogo no tiene un sismo compatible, probablemente porque fue local y
#: pequeño—, y es el mismo vocabulario que el estado `sin_correlacion` del
#: glosario compartido (`shared/glossary/procedencia.json`, T-5.10).
SIN_CORRELACION_EN_CATALOGO = (
    "SIN CORRELACIÓN EN EL CATÁLOGO DE REFERENCIA: ningún sismo publicado "
    "satisface el criterio de identidad con este incidente."
)


def num(value: object, digits: int = 3, unit: str = "") -> str:
    """Número con unidad, o el literal de ausencia. Nunca 0 por defecto."""
    if value is None:
        return ABSENT
    text = f"{float(value):.{digits}f}"
    return f"{text} {unit}".strip()


@dataclass(frozen=True, slots=True)
class ChannelRow:
    channel: str
    peak_pga_g: float | None
    peak_pgv_cms: float | None
    peak_rms: float | None
    peak_stalta: float | None
    energy_sum: float | None
    clipped: bool
    samples: int
    peak_ts: datetime | None


@dataclass(frozen=True, slots=True)
class DictamenRow:
    dictamen_id: str
    status: str
    created_at: datetime
    signed_by: str | None
    rule_set_version: str
    supersedes: str | None


@dataclass(frozen=True, slots=True)
class VoteRow:
    label: str
    delta_s: float | None
    pga_g: float | None
    counted: bool


@dataclass(frozen=True, slots=True)
class EstacionFila:
    """[T-7.17] Una estación de la red frente a este incidente, en el papel.

    Lleva lo MEDIDO y lo ESPERADO juntos, y `None` donde no hay dato en vez de un
    cero: un `0.0 g` impreso en un dictamen firmado es una afirmación de que la
    estación midió calma, y no es lo mismo que no haber medido.
    """

    site_name: str
    site_code: str
    sensor_code: str | None
    dist_km: float | None
    t_teorico_s: float | None
    t_medido_s: float | None
    peak_pga_g: float | None
    tier: str | None

    #: [T-7.22] Dónde está, para poder dibujarla. `None` en las dos o en
    #: ninguna: media coordenada no sitúa nada, y el mapa declara la ausencia en
    #: vez de colocar el punto en el meridiano cero.
    lat: float | None = None
    lon: float | None = None

    #: [T-7.22] El umbral contra el que se decidió «sobre umbral», CON su
    #: procedencia. La tabla imprimía el pico a secas: sin el umbral al lado, un
    #: `0.0123 g` no dice si esa estación se movió mucho o poco, y sin la
    #: procedencia el número parece del edificio aunque sea el de referencia
    #: —que es la razón por la que `T-7.35` añadió `umbral_origen`—.
    umbral_pga_g: float | None = None
    umbral_origen: str | None = None


@dataclass(frozen=True, slots=True)
class FotoFila:
    """[T-7.22] Una fotografía del reporte de daños, tal como llega al papel.

    **Tres huellas y no una, y la distinción no es pedantería.**

    * `sha256_declarado` es lo que dijo el DISPOSITIVO al registrar la evidencia
      (`POST /evidence`), y el servidor nunca lo verificó — por eso existe
      `POST /evidence/{id}/verify` como operación aparte.
    * `sha256_medido` es lo que el servidor calculó del blob al leerlo para
      imprimirlo. Es gratis: el render tiene que bajar los bytes de todos modos.
    * `sha256_impreso` es el de la DERIVADA redimensionada, que es lo que el
      lector tiene delante.

    Rotular el primero como «huella del original» junto a una portada que manda
    hacer `sha256sum` repetiría la clase de defecto de `T-5.26`: un dato
    inverificable presentado como verificable. Y un desajuste entre el declarado y
    el medido es lo más importante que esta sección puede decir de una foto de
    evidencia, así que se imprime.
    """

    evidence_id: str
    sha256_declarado: str
    sha256_medido: str | None = None
    sha256_impreso: str | None = None
    ancho: int | None = None
    alto: int | None = None
    #: Por qué no se imprime, si es el caso. Nunca un hueco mudo.
    motivo: str | None = None
    #: Los bytes JPEG a embeber. **No entran crudos en `content_sha256`**: ver
    #: `documentos/huella.para_la_huella`. Su `sha256_impreso` sí, que identifica el
    #: contenido sin arrastrar megabytes por el serializador en cada llamada.
    jpeg: bytes | None = None


@dataclass(frozen=True, slots=True)
class DanoFila:
    """[T-7.22] Un reporte de daños del brigadista.

    `rol` y no nombre: lo fija `D-32` («el brigadista aparece por **rol**, nunca
    por nombre») y es lo único que este documento necesita para que la observación
    tenga procedencia. `None` cuando la asignación ya no existe — se declara, no se
    rellena con «brigadista» por costumbre.
    """

    report_id: str
    rol: str | None
    zona: str | None
    #: `[{key, severity, note?}]` tal como lo escribió la app.
    categorias: list[dict]
    personas_en_riesgo: bool
    notas: str | None
    ts: datetime
    fotos: list[FotoFila] = field(default_factory=list)
    #: Cuántas fotografías tiene el reporte MÁS ALLÁ del tope del documento. Se
    #: imprime: entregar seis de once sin decirlo es recortar la evidencia en
    #: silencio.
    fotos_omitidas: int = 0


@dataclass(frozen=True, slots=True)
class ActionRow:
    ts: datetime
    kind: str
    actor: str


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    kind: str
    sha256: str | None
    created_at: datetime | None


@dataclass
class CctvObjectRow:
    """Un clip o una captura, para la cadena de custodia.

    Conserva `sha256` y fecha **aunque el objeto ya no exista**: es lo que permite que el
    documento siga siendo verificable después de que la retención de vídeo haga su trabajo.
    Por eso `estado` es un campo y no se deriva de la presencia de la fila.
    """

    tipo: str  # clip | captura
    papel: str | None  # pre/egress/peak/reentry para capturas; None para clips
    sha256: str | None
    momento: datetime | None
    estado: str  # "disponible" | CCTV_PURGADO


@dataclass
class CctvBlock:
    """Lo que la sección de CCTV del reporte afirma. Sin métricas sigue siendo útil: la
    cadena de custodia y el estado son parte del documento aunque nadie haya contado."""

    estado: str = NO_CCTV
    objetos: list[CctvObjectRow] = field(default_factory=list)
    t50_s: float | None = None
    t90_s: float | None = None
    peak_n: int | None = None
    correlacion: str | None = None
    veredicto_reingreso: str | None = None
    #: `True` ⇒ la sección lo dice en un recuadro, no en una celda de tabla.
    reingreso_antes_del_dictamen: bool = False
    discrepancia: str | None = None


#: [T-7.36] Rótulos de celda del disparo. La versión en PROSA vive en
#: `narrative/deterministic._TRIGGER_TEXT`; ésta es la corta, para portada y
#: resumen. Son dos registros distintos del mismo hecho, no dos verdades.
TRIGGER_LABELS = {
    "sasmex": "SASMEX",
    "local_threshold": "umbral local",
    "quorum": "cuórum de red",
    "manual": "activación manual",
    "drill": "simulacro",
}


def disparo_line(opened_trigger: str, trigger: str) -> str:
    """[T-7.36] Qué ABRIÓ el incidente y, si no es lo mismo, a qué escaló.

    La portada y el resumen ejecutivo salen de aquí para que no puedan discrepar
    entre sí sobre el mismo incidente — el mismo criterio que `umbral_line`.

    La escalada NO se esconde: sustituir una frase falsa («se abrió por el
    cuórum») por una incompleta («se abrió por SASMEX», callando que el cuórum
    corroboró) sería cambiar de defecto. Y el cuórum es justo lo que autoriza a
    evacuar.
    """
    abrio = TRIGGER_LABELS.get(opened_trigger, opened_trigger) or "SIN DATO"
    if not trigger or trigger == opened_trigger:
        return abrio
    return f"{abrio} · escaló a {TRIGGER_LABELS.get(trigger, trigger)}"


@dataclass
class ReportModel:
    """Todo lo que el dictamen puede afirmar. Nada se calcula durante el render."""

    folio: str
    incident_id: str
    site_name: str
    site_code: str
    site_criticality: str | None
    site_lat: float | None
    site_lon: float | None
    opened_at: datetime
    closed_at: datetime | None
    severity: str
    #: La escalada VIGENTE. La ingesta la sobrescribe (`ON CONFLICT DO UPDATE`).
    trigger: str
    #: [T-7.36] Con qué se ABRIÓ. Lo estampa la base y es inmutable. Es lo que la
    #: prosa tiene que decir: «se abrió por X» con el disparo de la última escalada
    #: es falso en cuanto un incidente escala, y es el mismo campo del que sale el
    #: tiempo de aviso ganado.
    opened_trigger: str
    state: str
    event_id: str | None
    event_source: str | None
    epicenter_lat: float | None
    epicenter_lon: float | None

    verdict_status: str | None
    verdict_label: str
    verdict_signed: bool
    rule_set_version: str | None

    peak_pga_g: float | None
    peak_pgv_cms: float | None
    peak_ts: datetime | None
    felt_band: str
    # [T-7.35] Contra qué números se clasificó `felt_band` y de quién son. Con
    # default para no romper los modelos que aún no lo traen; la línea del papel
    # lo declara como «banda de referencia» cuando falta.
    felt_thresholds: dict | None
    calibrated: bool
    lead_time_s: float | None
    lead_time_reason: str | None
    station_count: int
    catalog_line: str | None
    generated_at: datetime

    #: [T-7.38·H] ¿Movió un operador el epicentro a mano? Sale de
    #: `seismic_events.meta ? 'manual_override'`. Con esto puesto, el papel NO puede
    #: seguir llamándolo «centroide de las estaciones»: es un punto humano.
    #: [T-7.51] El incidente se cerró y NADIE registró la hora. Declara la
    #: ausencia en vez de que el papel la disimule: sin esto, el campo CIERRE
    #: imprimía «EN CURSO» de un incidente cerrado, que es el papel
    #: desmintiendo al dato — la clase de defecto de `T-7.38`/`T-7.42`/`T-7.43`.
    cierre_sin_hora: bool = False
    epicenter_relocated: bool = False

    channels: list[ChannelRow] = field(default_factory=list)
    dictamens: list[DictamenRow] = field(default_factory=list)
    votes: list[VoteRow] = field(default_factory=list)
    actions: list[ActionRow] = field(default_factory=list)
    evidence: list[EvidenceRow] = field(default_factory=list)
    sensors: list[dict] = field(default_factory=list)
    peers: list[dict] = field(default_factory=list)
    #: Serie 1 Hz por canal: `{canal: [(ts, pga_g, clipping), …]}`.
    series: dict[str, list[tuple[datetime, float | None, bool]]] = field(default_factory=dict)
    #: Forma de onda cruda decodificada del miniSEED, si lo hubo.
    raw_waveform: dict[str, list[int]] = field(default_factory=dict)
    raw_sample_rate: float | None = None
    #: Espectro de amplitud del canal dominante: `(frecuencias_hz, amplitudes)`.
    spectrum: tuple[list[float], list[float]] | None = None
    spectrum_peak_hz: float | None = None
    #: [T-5.23] Espectrograma del MISMO canal dominante: tiempo × frecuencia, con
    #: escala RELATIVA. `None` cuando no hubo traza de la que calcularlo — y eso
    #: se declara con el mismo texto de ausencia que la onda cruda, no con un hueco.
    spectrogram: Espectrograma | None = None
    #: [T-3.14] Duración instrumental **medida** de la sacudida: D5-95 sobre la Intensidad
    #: de Arias del canal dominante. `None` cuando no se pudo medir — que NO es lo mismo
    #: que cero, y el reporte lo dice con palabras.
    shaking_duration: Duracion | None = None
    #: Por qué no hay onda cruda ni espectro, si es el caso.
    raw_unavailable_reason: str | None = None
    #: `basis` del dictamen vigente (T-2.42): qué umbral, con qué valor, de qué versión
    #: de reglas. Es lo que hace auditable el "por qué este veredicto" de la prosa.
    verdict_basis: dict = field(default_factory=dict)
    #: [T-7.17] La red de estaciones: qué midió cada una y qué le tocaba. Entra en
    #: ``content_sha256`` como todo lo demás — cambiar lo que el documento afirma
    #: sobre lo que midió otro inmueble tiene que mover la huella.
    estaciones: list[EstacionFila] = field(default_factory=list)
    #: Desde dónde se cuentan los arribos de arriba (`event` u `incident`). Sin
    #: declararlo, dos dictámenes con anclas distintas se comparan como si
    #: midieran lo mismo.
    estaciones_ancla: str = "incident"
    #: [T-7.22] ¿El evento enlazado es una reproducción de un sismo histórico?
    #:
    #: Se DERIVA de `seismic_events.meta->'reproduccion'` —lo que escribe el
    #: propio replay— y no de `incident_classifications.classification`, que la
    #: pone una PERSONA y que la reproducción no escribe. Las dos compiten: un
    #: incidente real clasificado a mano como reproducción no llevaría el rótulo,
    #: y uno vestido por el replay lo llevaría sin que nadie lo clasificara. Se
    #: elige la del evento porque es la misma que lee la consola, y papel y
    #: pantalla no pueden discrepar sobre si lo que se enseña ocurrió.
    reproduccion: bool = False
    #: Prosa opcional (T-2.42). El veredicto NO sale de aquí.
    narrative: list[tuple[str, str]] = field(default_factory=list)
    narrative_provider: str | None = None
    narrative_degraded: str | None = None
    #: [T-2.82] Marco normativo DECLARADO por el cliente (``compliance_labels``). Es
    #: la única parte del documento que TAKAB no midió ni verificó, y por eso viaja
    #: como documento con su propio estado de legibilidad en vez de como lista suelta.
    #: Entra en ``content_sha256``: cambiar lo que el dictamen afirma tiene que mover
    #: la huella. ⚠️ [T-7.43] La razón NO es «para poder comparar dos exportaciones»
    #: —eso no se puede y ya no se promete—: es que el número identifica ESTA
    #: exportación, y un campo que no lo moviera quedaría fuera de esa identidad.
    #: Lo vigila el censo derivado, no esta nota.
    compliance: ComplianceDocument = field(default_factory=ComplianceDocument)
    #: [T-3.12.c] CCTV: analítica de evacuación y cadena de custodia del vídeo. Entra en
    #: ``content_sha256`` como todo lo demás — cambiar lo que el documento afirma sobre
    #: cuánto tardó la gente en salir tiene que mover la huella.
    cctv: CctvBlock = field(default_factory=CctvBlock)

    #: [T-7.22] Los reportes de daños del brigadista, con sus fotografías. Entran
    #: en ``content_sha256`` como todo lo demás — sus HUELLAS, no sus bytes.
    danos: list[DanoFila] = field(default_factory=list)

    def content_sha256(self) -> str:
        """Huella del CONTENIDO (no del archivo): identifica qué se afirmó.

        El sha256 del PDF no puede imprimirse dentro de sí mismo; éste sí, y desde
        `T-7.42` va en la portada Y en el pie de todas las páginas.

        ⚠️ **La segunda frase de este docstring prometía «comparar dos
        exportaciones del mismo incidente sin abrirlas», y es FALSA**: medido en
        `T-7.43`, `generated_at` es campo del modelo, así que dos exportaciones
        separadas por un segundo dan huellas distintas y nunca coinciden. Se retira
        la promesa en vez de dejarla: elegir entre sacar `generated_at` del payload
        o decir qué identifica este número de verdad **es `T-7.43`**, y no se
        adelanta aquí. Lo que sí se puede decir hoy es lo que este número identifica
        con certeza: una exportación concreta. El del simulacro sí es estable
        (`drill_report.ReporteSimulacro.content_sha256`), porque su modelo no tiene
        reloj de generación.
        """
        return huella_de_contenido(self)


#: [T-5.26] Lo que se imprime donde va la huella de un objeto de evidencia.
#:
#: Existe como función —y no como un `or` en el sitio del render— porque la
#: regla que encierra es la que estuvo rota: el sha256 se imprimía a **32 de 64**
#: caracteres (y a 16 en la custodia del vídeo) mientras la portada del mismo
#: documento instruye verificarlo con `sha256sum`. Con medio hash no se puede, y
#: un dato inverificable presentado como verificable es peor que no imprimirlo:
#: quien lo intente concluirá que la evidencia está corrupta.
#:
#: No había razón de espacio: 64 hex miden 108.7 mm de los 133.9 que deja la
#: columna del PDF, así que caben en una sola línea.
SIN_HASH = "sin hash"


def huella_de_custodia(sha: str | None) -> str:
    """El sha256 ENTERO, o la ausencia declarada. Nunca un trozo."""
    return sha or SIN_HASH


# [T-7.35] El rótulo dice la BANDA, no de quién es el umbral.
#
# Decía «supera el umbral de actuación del inmueble» y afirmaba dos cosas que el
# documento no comprobaba: que el umbral era el de ese edificio —se clasificaba
# con la banda de fábrica— y que superarlo acciona algo, cuando desde `T-2.32`
# una detección instrumental sola NO mueve un relé. Los números y su procedencia
# los imprime `umbral_line()` en la línea de debajo, que es donde se pueden
# verificar.
FELT_LABELS: dict[str, str] = {
    "trip": "SACUDIDA FUERTE (supera el umbral de disparo)",
    "watch": "SACUDIDA MODERADA (supera el umbral de vigilancia)",
    "normal": "SACUDIDA LEVE (por debajo de los umbrales)",
    "unknown": "SIN MEDICIÓN DE SACUDIDA",
}


def umbral_line(u) -> str:  # noqa: ANN001 - felt.UmbralComparacion (import circular si se anota)
    """Contra qué números se clasificó la sacudida, y de dónde salieron.

    Va debajo de la BANDA porque es lo que la hace verificable: sin esta línea,
    «SACUDIDA FUERTE» es una palabra sin escala. Con `origen == 'referencia'` se
    DICE que son los de fábrica en vez de fingir que son los del edificio.
    """
    th = u.thresholds
    numeros = (
        f"PGA {th.pga_watch_g:.3f}/{th.pga_trip_g:.3f} g · "
        f"PGV {th.pgv_watch_cms:.1f}/{th.pgv_trip_cms:.1f} cm/s"
    )
    if u.origen == "inmueble":
        version = f" v{u.rule_set_version}" if u.rule_set_version is not None else ""
        return f"{numeros} · umbrales del inmueble{version}, vigentes en la apertura"
    return (
        f"{numeros} · banda de referencia: no consta configuración del inmueble "
        "anterior al incidente"
    )


LEAD_REASONS: dict[str, str] = {
    "not_sasmex": "no aplica: el incidente no se disparó por SASMEX",
    "no_peak": "no hubo pico medido en la ventana del incidente",
    "peak_before_alert": "el pico precedió a la alerta",
    # [T-7.35] No hubo sacudida que avisar: el pico de la ventana no superó el
    # umbral de vigilancia del inmueble. Presentar segundos de «aviso ganado»
    # sobre ruido ambiente es presumir un logro que no ocurrió.
    "sin_sacudida": "no aplica: la sacudida no superó el umbral de vigilancia del inmueble",
}


def cierre_text(closed_at: datetime | None, state: str, cierre_sin_hora: bool, fmt: str) -> str:
    """[T-7.51] Qué dice el papel en el campo CIERRE. Tres casos, no dos.

    Decía `"EN CURSO"` siempre que `closed_at` fuera nulo — y en la nube dev
    había TRES incidentes con `state='closed'` y la hora en nulo, así que **el
    dictamen pericial de un incidente cerrado afirmaba que seguía abierto**.

    El tercer caso no se rellena con una hora inventada: se DECLARA. La hora real
    de aquellos cierres no existe en ninguna parte, y fabricarla contaminaría la
    tabla de la que cuelga este documento — es la doctrina que `T-7.42` y
    `T-7.43` acaban de imponer en este mismo papel.
    """
    if closed_at is not None:
        return f"{closed_at:{fmt}}"
    if state == "closed":
        return "CERRADO · HORA DE CIERRE NO REGISTRADA"
    return "EN CURSO"


def lead_time_text(seconds: float | None, reason: str | None) -> str:
    """Tiempo de aviso ganado, o su ausencia explicada. Jamás '0 s' por defecto."""
    if seconds is not None:
        return f"{seconds:.1f} s"
    return f"NO CALCULABLE · {LEAD_REASONS.get(reason or '', reason or 'razón no registrada')}"
