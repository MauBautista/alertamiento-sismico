"""Construcción del ``ReportModel`` desde la base (T-2.41).

Aísla el acceso a datos del render y del modelo: ``pdf.py`` no toca la DB y
``model.py`` no sabe que existe. Así el contenido del dictamen —donde puede haber una
mentira— se prueba sin abrir un PDF ni levantar Postgres.

La forma de onda cruda y el espectro son **best-effort**: llegan de un objeto de S3 que
puede no existir, estar a medias o venir en un encoding que el lector no soporta.
Cualquiera de esas cosas degrada la sección con su razón — jamás tumba la exportación
de una evidencia de compliance.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api import procedencia as pr
from takab_api.cctv import build_cctv
from takab_api.dictamen.duracion import significativa
from takab_api.dictamen.espectrograma import calcular as calcular_espectrograma
from takab_api.dictamen.model import (
    CCTV_PARCIALMENTE_PURGADO,
    CCTV_PENDIENTE,
    CCTV_PURGADO,
    CCTV_PURGADO_SIN_ANALISIS,
    CCTV_SIN_CLIP,
    CONSULTA_EXTERNA_EN_VUELO,
    CORRELACION_EN_DISPUTA,
    ESTADO_DE_CONSULTA_NO_INTERPRETABLE,
    NO_CCTV,
    SIN_CONSULTA_A_FUENTE_EXTERNA,
    STATUS_LABELS,
    TS_FMT,
    ActionRow,
    AnilloFila,
    CctvBlock,
    CctvObjectRow,
    ChannelRow,
    DanoFila,
    DictamenRow,
    EstacionFila,
    EvidenceRow,
    FotoFila,
    NivelFueraFila,
    ReportModel,
    SacudidaFila,
    ShakemapBlock,
    VoteRow,
    fuentes_line,
)
from takab_api.dictamen.mseed import MseedError, read_traces
from takab_api.documentos import fotos as fotos_mod
from takab_api.estaciones import build_estaciones
from takab_api.felt import umbral_congelado
from takab_api.forensics import build_forensics, umbral_de_comparacion
from takab_api.queries import compliance as qc
from takab_api.queries import forensics as qf
from takab_api.schemas import cctv as esq_cctv
from takab_api.schemas.forensics import CatalogCorrelation, ForensicsOut
from takab_api.settings import Settings
from takab_api.shakemap.lectura import leer as leer_shakemap

log = logging.getLogger(__name__)

#: Muestras máximas por canal para la FFT. 60 s a 100 sps es de sobra para ver el
#: contenido de una sacudida y acota el coste dentro de un request HTTP.
MAX_FFT_SAMPLES = 6000

_INCIDENT = text(
    """
    SELECT i.incident_id, i.site_id, i.tenant_id, i.event_id, i.opened_at, i.closed_at,
           i.cierre_sin_hora,
           i.severity, i.state, i.trigger, i.opened_trigger,
           s.name AS site_name, s.code AS site_code, s.criticality,
           ST_Y(s.geom::geometry)::float8 AS site_lat,
           ST_X(s.geom::geometry)::float8 AS site_lon,
           e.source AS event_source,
           (e.meta ? 'manual_override') AS epi_manual,
           ST_Y(e.epicenter::geometry)::float8 AS epi_lat,
           ST_X(e.epicenter::geometry)::float8 AS epi_lon
    FROM incidents i
    JOIN sites s ON s.site_id = i.site_id
    LEFT JOIN seismic_events e ON e.event_id = i.event_id
    WHERE i.incident_id = CAST(:id AS uuid)
    """
)

_DICTAMENS = text(
    "SELECT dictamen_id, status, created_at, signed_by, basis, supersedes_dictamen_id "
    "FROM dictamens WHERE incident_id = CAST(:id AS uuid) ORDER BY created_at DESC"
)

_ACTIONS = text(
    "SELECT ts, kind, actor FROM incident_actions "
    "WHERE incident_id = CAST(:id AS uuid) ORDER BY ts ASC"
)

_EVIDENCE = text(
    # [T-7.22] `evidence_id` para poder resolver el `uuid[]` de
    # `damage_reports.evidence_ids` contra ESTAS filas, en Python. La alternativa
    # —una segunda consulta a `evidence_objects`— daría dos lecturas
    # independientes de la misma tabla que pueden acabar diciendo cosas distintas
    # en dos páginas del mismo papel.
    "SELECT evidence_id, kind, sha256, created_at, s3_key FROM evidence_objects "
    "WHERE incident_id = CAST(:id AS uuid) ORDER BY created_at ASC"
)

_DANOS = text(
    # El ROL, nunca el nombre (`D-32`). `user_zone_assignments` lo resuelve en la
    # misma consulta: llamar a Cognito desde un render de evidencia sería meter
    # una dependencia de red en la generación de un documento.
    """
    SELECT d.report_id, d.zone_id, d.categories, d.people_at_risk, d.notes,
           d.evidence_ids, COALESCE(d.ts_device, d.created_at) AS ts,
           z.name AS zona, a.role AS rol
    FROM damage_reports d
    LEFT JOIN zones z ON z.zone_id = d.zone_id
    LEFT JOIN user_zone_assignments a
           ON a.user_id = d.user_sub AND a.site_id = d.site_id
    WHERE d.incident_id = CAST(:id AS uuid)
    ORDER BY ts ASC
    """
)


def folio_of(site_code: str, opened_at: datetime, incident_id: str, variant: str) -> str:
    """Identificador legible del documento. Se imprime y se cita por teléfono."""
    suffix = "E" if variant == "executive" else "T"
    short = incident_id.replace("-", "")[:8].upper()
    return f"TKB-{site_code}-{opened_at:%Y%m%d}-{short}-{suffix}"


async def _cctv_block(conn: AsyncConnection, incident_id: str) -> CctvBlock:
    """Traduce el objeto de la API al bloque del documento. **Best-effort a propósito.**

    Un fallo leyendo el CCTV no puede impedir que se genere el dictamen: el vídeo es un
    anexo y el dictamen es lo que autoriza reocupar un edificio. Se degrada a la razón
    escrita —misma disciplina que `_raw_waveform`— en vez de tumbar el documento.
    """
    try:
        datos = await build_cctv(conn, incident_id)
    except Exception:  # noqa: BLE001 — el anexo no puede costar el dictamen
        return CctvBlock(estado="CCTV NO DISPONIBLE al generar este documento")
    if datos is None:
        return CctvBlock()

    objetos = [
        CctvObjectRow(
            tipo="clip",
            papel=None,
            sha256=c.sha256,
            momento=c.started_at,
            estado=CCTV_PURGADO if c.purged_at else "disponible",
        )
        for c in datos.clips
    ] + [
        CctvObjectRow(
            tipo="captura",
            papel=cap.papel,
            sha256=cap.sha256,
            momento=cap.captured_at,
            estado=CCTV_PURGADO if cap.purged_at else "disponible",
        )
        for cap in datos.capturas
        if cap.still_id is not None
    ]

    if datos.evacuacion is None:
        # [T-7.38·F] El estado se decide por lo que QUEDA del vídeo, no por que exista
        # la fila: la fila sobrevive a la poda a propósito —es la cadena de custodia—
        # y tomarla por «hay vídeo» anunciaba como archivado un clip ya destruido,
        # prometiendo cifras de evacuación que no van a llegar nunca.
        estado = {
            esq_cctv.CLIPS_VIVOS: CCTV_PENDIENTE,
            esq_cctv.CLIPS_PURGADOS: CCTV_PURGADO_SIN_ANALISIS,
            esq_cctv.CLIPS_MIXTOS: CCTV_PARCIALMENTE_PURGADO,
            esq_cctv.CLIPS_SIN: CCTV_SIN_CLIP if datos.con_camara else NO_CCTV,
        }[esq_cctv.clase_del_material([c.disponible for c in datos.clips])]
        return CctvBlock(estado=estado, objetos=objetos)

    e = datos.evacuacion
    return CctvBlock(
        estado="análisis disponible",
        objetos=objetos,
        t50_s=e.t50_s,
        t90_s=e.t90_s,
        peak_n=e.peak_n,
        correlacion=e.correlacion,
        veredicto_reingreso=e.veredicto_reingreso,
        reingreso_antes_del_dictamen=e.reingreso_antes_del_dictamen,
        discrepancia=datos.discrepancia.lectura if datos.discrepancia else None,
    )


async def leer_bloque_de_shakemap(conn: AsyncConnection, incident_id: str, s, site_code: str):  # noqa: ANN001, ANN201
    """Lee el snapshot y lo traduce. **Best-effort a propósito**, como el CCTV.

    ⚠️ La lectura del mapa era la ÚNICA del builder que iba desnuda, con la
    doctrina contraria escrita a cinco líneas de aquí (`_cctv_block`: «un fallo
    leyendo el CCTV no puede impedir que se genere el dictamen: el vídeo es un
    anexo y el dictamen es lo que autoriza reocupar un edificio»). El miniSEED
    hace lo mismo desde siempre.

    Medido el 2026-09-21 con `ALTER TABLE incident_shakemap RENAME TO …` dentro de
    una transacción con rollback: `build_model` moría con
    `UndefinedTable: relation "incident_shakemap" does not exist` y el inmueble se
    quedaba **sin dictamen**. La ventana de despliegue es estrecha —`deploy.sh`
    corre `alembic upgrade head` antes de tocar la API— pero no es la única puerta:
    un `puntos` jsonb que no valide contra `PuntoProps` (`site_name` es
    obligatorio) explota igual y ese orden no lo cubre.

    El fallo se DECLARA (`ShakemapBlock.fallo_de_lectura`) en vez de degradarse a
    `pendiente`: «no ha corrido el cálculo» y «no pude leerlo» son dos hechos
    distintos sobre el mismo incidente, y el papel no puede imprimir el primero
    cuando lo que pasó es el segundo (regla de oro 7).
    """
    try:
        mapa = await leer_shakemap(conn, incident_id, s)
    except Exception:  # noqa: BLE001 — el anexo no puede costar el dictamen
        return ShakemapBlock(fallo_de_lectura="la lectura del snapshot falló")
    return bloque_de_shakemap(mapa, site_code)


def bloque_de_shakemap(mapa, site_code: str):  # noqa: ANN001, ANN201 - ShakemapOut|None
    """[T-7.24] Traduce el mapa ya leído a las filas que el papel imprime.

    **Sólo traduce.** El cálculo vive en `takab_api.shakemap.calculo` y la lectura
    en `…shakemap.lectura`, que es la misma que sirve al endpoint: si el PDF
    consultara por su cuenta, el papel y la pantalla dibujarían cada uno su mapa
    del mismo sismo, y el que discrepa lleva una firma debajo.

    Es una función y no unas líneas dentro de `build_model` porque lo que puede
    tener una mentira es justo esto: el GeoJSON viene `[lon, lat]` —el revés de
    como se dice— y un `None` convertido en cero afirmaría que un inmueble no se
    movió cuando lo que pasó es que no publicó.

    `mapa is None` (el incidente no existe para quien pide) cae en `pendiente`
    como la ausencia de snapshot: el papel no puede afirmar que no sacudió cuando
    lo que le pasa es que no lo sabe.
    """
    if mapa is None:
        return ShakemapBlock()
    epi = mapa.epicentro
    return ShakemapBlock(
        estado=mapa.estado,
        ley=mapa.ley,
        calculado_en=mapa.calculado_en,
        cobertura_km=mapa.cobertura_km,
        epicentro_lat=epi.lat if epi else None,
        epicentro_lon=epi.lon if epi else None,
        epicentro_magnitud=epi.magnitud if epi else None,
        epicentro_fuente=epi.fuente if epi else None,
        epicentro_procedencia=epi.procedencia if epi else None,
        puntos=[
            SacudidaFila(
                site_code=f.properties.site_code,
                site_name=f.properties.site_name,
                # ⚠️ GeoJSON es `[lon, lat]`. El croquis proyecta `(lat, lon)`, y
                # cambiarlos de orden no rompe nada visible: sale igual de bonito
                # con los inmuebles en otro continente.
                lat=f.geometry.coordinates[1],
                lon=f.geometry.coordinates[0],
                pga_g=f.properties.pga_g,
                pgv_cms=f.properties.pgv_cms,
                dist_km=f.properties.dist_km,
                pga_g_modelada=f.properties.pga_g_modelada,
                residuo_log10=f.properties.residuo_log10,
                propio=f.properties.site_code == site_code,
            )
            for f in mapa.observado.features
        ],
        # `modelado is None` significa que NO se modeló, y una lista vacía es lo
        # que sale de ahí: la sección lo distingue por `anillos` vacío y lo dice.
        anillos=[
            AnilloFila(
                pga_g=f.properties.pga_g,
                radio_km=f.properties.radio_km,
                umbral=f.properties.umbral,
            )
            for f in (mapa.modelado.features if mapa.modelado else [])
        ],
        # ⚠️ [T-7.24 · 3ª vuelta] Esto NO se tira. Sin los niveles suprimidos la
        # sección no puede decir por qué no hay anillos, y decía una razón falsa
        # —«falta la capa modelada del snapshot»— sobre un snapshot que traía el
        # modelo dentro, por punto. El motivo viene del vocabulario cerrado del
        # cálculo, así que aquí tampoco se escribe ninguna frase: se copia el
        # código y lo traduce quien imprime.
        fuera_de_alcance=[
            NivelFueraFila(umbral=n.umbral, pga_g=n.pga_g, motivo=n.motivo)
            for n in mapa.fuera_de_alcance
        ],
    )


async def build_model(
    conn: AsyncConnection,
    incident_id: str,
    *,
    variant: str = "technical",
    generated_at: datetime,
    fetch_object=None,
    settings: Settings | None = None,
) -> ReportModel | None:
    """Modelo completo del dictamen, o ``None`` si la RLS no ve el incidente.

    ``fetch_object`` es la lectura del miniSEED de S3 (``s3_key -> bytes``). Se inyecta
    para que el modelo sea probable sin red; si es ``None``, la sección de onda cruda se
    declara no disponible.
    """
    s = settings or Settings()
    row = (await conn.execute(_INCIDENT, {"id": incident_id})).first()
    if row is None:
        return None
    inc = dict(row._mapping)

    forensics = await build_forensics(conn, incident_id, s)
    if forensics is None:  # pragma: no cover - el SELECT de arriba ya lo cubriría
        return None

    # [T-7.17] La red de estaciones, de la MISMA función que sirve a la consola y
    # al muro. Dos caminos para los mismos números acabarían discrepando, y un
    # dictamen que no coincide con lo que el operador vio en pantalla es peor que
    # ninguno — es exactamente el razonamiento del bloque de forensics.
    red = await build_estaciones(conn, incident_id, s)

    dictamen_rows = (await conn.execute(_DICTAMENS, {"id": incident_id})).all()

    # [T-7.37] Primero se busca el umbral CONGELADO en la cadena de dictámenes.
    # `T-7.35` resuelve bien los vigentes en la apertura, pero lo hace al
    # EXPORTAR: si alguien podara versiones antiguas de `rule_sets`, un PDF
    # regenerado el año que viene clasificaría el mismo pico contra otra banda, y
    # un dictamen es un documento histórico. Se recorre la CADENA, no solo la
    # cabeza: al firmar, el `basis` de la fila nueva es `{}` o `{"notes": …}`.
    #
    # El respaldo —resolver ahora— se queda para los incidentes sin dictamen y
    # para los documentos anteriores a esta ficha. Es la MISMA resolución que usa
    # la banda: dos caminos para el mismo número acaban discrepando.
    umbral_dict = umbral_congelado([r.basis for r in dictamen_rows])
    if umbral_dict is None:
        umbral_dict = (
            await umbral_de_comparacion(
                conn,
                site_id=str(inc["site_id"]),
                tenant_id=str(inc["tenant_id"]),
                at=inc["opened_at"],
            )
        ).as_dict()
    dictamens = [
        DictamenRow(
            dictamen_id=str(r.dictamen_id),
            status=r.status,
            created_at=r.created_at,
            signed_by=str(r.signed_by) if r.signed_by else None,
            rule_set_version=(r.basis or {}).get("rule_set_version", "sin versión"),
            supersedes=str(r.supersedes_dictamen_id) if r.supersedes_dictamen_id else None,
        )
        for r in dictamen_rows
    ]
    head = dictamens[0] if dictamens else None
    # [T-2.42] El `basis` del dictamen vigente viaja al modelo para que la prosa pueda
    # explicar QUÉ umbral lo determinó, con qué valor y de qué versión de reglas.
    head_basis = dict(dictamen_rows[0].basis or {}) if dictamen_rows else {}

    actions = [
        ActionRow(ts=r.ts, kind=r.kind, actor=r.actor)
        for r in (await conn.execute(_ACTIONS, {"id": incident_id})).all()
    ]
    evidence_rows = (await conn.execute(_EVIDENCE, {"id": incident_id})).all()
    evidence = [
        EvidenceRow(kind=r.kind, sha256=r.sha256, created_at=r.created_at) for r in evidence_rows
    ]

    series = await _series(conn, site_id=str(inc["site_id"]), f=forensics)
    raw, rate, spectrum, peak_hz, espectrograma, duracion, reason = await _raw_waveform(
        evidence_rows, fetch_object, variant
    )

    danos = await _danos(conn, incident_id, evidence_rows, fetch_object)

    estaciones = [
        EstacionFila(
            site_name=e.site_name,
            site_code=e.site_code,
            sensor_code=e.sensor_code,
            dist_km=e.dist_km,
            t_teorico_s=e.t_arribo_teorico_s,
            t_medido_s=e.t_arribo_medido_s,
            peak_pga_g=e.peak_pga_g,
            tier=e.tier,
            # [T-7.22] Lo que `EstacionOut` ya traía y este mapeo tiraba: sin
            # coordenadas no hay mapa de la red, y sin umbral el pico de la tabla
            # es un número sin escala.
            lat=e.lat,
            lon=e.lon,
            umbral_pga_g=e.umbral_pga_g,
            umbral_origen=e.umbral_origen,
        )
        for e in (red.items if red is not None else [])
    ]

    return ReportModel(
        folio=folio_of(inc["site_code"], inc["opened_at"], incident_id, variant),
        incident_id=incident_id,
        site_name=inc["site_name"],
        site_code=inc["site_code"],
        site_criticality=inc["criticality"],
        site_lat=inc["site_lat"],
        site_lon=inc["site_lon"],
        opened_at=inc["opened_at"],
        closed_at=inc["closed_at"],
        cierre_sin_hora=bool(inc["cierre_sin_hora"]),
        severity=inc["severity"],
        trigger=inc["trigger"],
        opened_trigger=inc["opened_trigger"],
        state=inc["state"],
        event_id=inc["event_id"],
        event_source=inc["event_source"],
        epicenter_relocated=bool(inc["epi_manual"]),
        epicenter_lat=inc["epi_lat"],
        epicenter_lon=inc["epi_lon"],
        verdict_status=head.status if head else None,
        verdict_label=(
            STATUS_LABELS.get(head.status, head.status) if head else "SIN DICTAMEN REGISTRADO"
        ),
        verdict_signed=bool(head and head.signed_by),
        rule_set_version=head.rule_set_version if head else None,
        peak_pga_g=forensics.peak_pga_g,
        peak_pgv_cms=forensics.peak_pgv_cms,
        peak_ts=forensics.peak_ts,
        felt_band=forensics.felt_band,
        felt_thresholds=umbral_dict,
        calibrated=forensics.calibrated,
        lead_time_s=forensics.lead_time_s,
        lead_time_reason=forensics.lead_time_reason,
        station_count=forensics.station_count,
        catalog_line=_catalog_line(forensics),
        fuentes_externas=fuentes_line(s.catalog_usgs_enabled),
        generated_at=generated_at,
        channels=[
            ChannelRow(
                channel=c.channel,
                peak_pga_g=c.peak_pga_g,
                peak_pgv_cms=c.peak_pgv_cms,
                peak_rms=c.peak_rms,
                peak_stalta=c.peak_stalta,
                energy_sum=c.energy_sum,
                clipped=c.clipped,
                samples=c.samples,
                peak_ts=c.peak_ts,
            )
            for c in forensics.channels
        ],
        dictamens=dictamens,
        votes=[
            VoteRow(
                label=p.site_code or (str(p.sensor_id)[:8] + " · OTRA RED"),
                delta_s=p.delta_s,
                pga_g=p.pga_g,
                counted=p.counted,
            )
            for p in forensics.peers
        ],
        actions=actions,
        evidence=evidence,
        sensors=[sn.model_dump() for sn in forensics.sensors],
        peers=[p.model_dump() for p in forensics.peers],
        series=series,
        raw_waveform=raw,
        raw_sample_rate=rate,
        spectrum=spectrum,
        spectrum_peak_hz=peak_hz,
        spectrogram=espectrograma,
        shaking_duration=duracion,
        raw_unavailable_reason=reason,
        estaciones=estaciones,
        estaciones_ancla=(red.ancla if red is not None else "incident"),
        # [T-7.22] De `seismic_events.meta->'reproduccion'`, que es lo que lee
        # la consola. Sin `red` no se puede afirmar que NO lo sea, pero un
        # incidente sin evento enlazado tampoco tiene sismo histórico detrás.
        reproduccion=(red.reproduccion if red is not None else False),
        danos=danos,
        verdict_basis=head_basis,
        # [T-2.82] Marco DECLARADO por el cliente. Sale de la MISMA función que lo
        # sirve a la pantalla de Triage (`queries.compliance.document_for_incident`):
        # si el papel y la pantalla lo leyeran cada uno a su manera, acabarían
        # discrepando — y aquí el que discrepa lleva una firma debajo.
        compliance=await qc.document_for_incident(conn, incident_id),
        # [T-3.12.c] CCTV. Sale del MISMO ensamblador que lo sirve a la pantalla
        # (`takab_api.cctv.build_cctv`), por la misma razón que el marco normativo de
        # arriba: si el papel y la pantalla lo leyeran cada uno a su manera acabarían
        # discrepando, y aquí el que discrepa lleva una firma debajo.
        cctv=await _cctv_block(conn, incident_id),
        # [T-7.24] El mapa de la sacudida. Se LEE ya calculado, con la misma
        # función que sirve al endpoint (`shakemap/lectura.py`), por la misma
        # razón que las dos líneas de arriba: dos lecturas del mismo snapshot
        # acabarían discrepando en el detalle que más se mira.
        shakemap=await leer_bloque_de_shakemap(conn, incident_id, s, inc["site_code"]),
    )


def _motivos(corr: CatalogCorrelation) -> str:
    """Los tres primeros descartes con su motivo. El papel tiene un ancho."""
    return " · ".join(f"{d.catalog_key}: {d.detalle}" for d in corr.descartes[:3])


def _hora_de_la_fuente(cuando: datetime | None) -> str:
    """`` el <ts> UTC``, o nada. Degrada, jamás inventa una fecha.

    ``astimezone(UTC)`` explícito: :data:`TS_FMT` estampa el literal «UTC» al
    final, así que un instante en otro huso saldría rotulado con el huso
    equivocado. Está aquí y no dentro de cada rama porque lo formatean dos —la
    pregunta en vuelo y la discrepancia—, y la copia es donde una de las dos se
    habría quedado sin el `astimezone`.
    """
    return "" if cuando is None else f" el {cuando.astimezone(UTC):{TS_FMT}}"


def _linea_sin_acierto(corr: CatalogCorrelation | None) -> str | None:
    """[T-7.25] Sin acierto hay CINCO hechos distintos, y el papel los separa.

    Esta función existe porque se imprimían todos igual, y el que se imprimía
    era el más comprometido de todos::

        (a) no se preguntó                →  SIN_CONSULTA_A_FUENTE_EXTERNA
        (b) se preguntó, no contestaron   →  CONSULTA_EXTERNA_EN_VUELO
        (c) contestaron, ninguno casa     →  SIN CORRELACIÓN (o el aviso del PDF)
        (d) correlacionó · preliminar     →  CORRELACION_EN_DISPUTA
        (e) correlacionó · confirmado     →  CORRELACION_EN_DISPUTA

    (d) y (e) comparten frase y se separan por el rótulo del glosario: una
    solución que la propia fuente declara PRELIMINAR puede cambiar mañana, y
    discrepar de ella no es lo mismo que discrepar de una que ya revisó.

    (c) es una afirmación **sobre el sismo**: exonera al catálogo de referencia.
    Firmarla en (a) o en (b) es dar por concluido lo que nadie concluyó, y va
    debajo de una firma que después no se retira. (a) es además el caso NORMAL:
    la consulta automática se despliega apagada.

    **(d) y (e) son la cuarta vuelta de la misma familia.** Nacieron sin rama:
    cuando la consulta CORRELACIONÓ pero el ensamblado forense no encuentra el
    acierto entre sus candidatos, el estado derivado es `preliminar` o
    `confirmado` y aquí no había nada que los recogiera. Medido antes del
    arreglo, con el mismo escenario: sin descartes la línea salía ``None`` —y el
    PDF rellena el hueco con :data:`SIN_CORRELACION_EN_CATALOGO`— y con un
    descarte salía «SIN CORRELACIÓN · 1 evento(s) … ninguno es éste». Las dos
    cosas son el papel exonerando al catálogo de un incidente que **sí**
    correlacionó. Que los dos procedimientos discrepen no es un fallo de ninguno
    —preguntan cosas distintas, y el criterio de identidad de `T-5.11` es más
    estricto que la ventana de la consulta—; lo que no puede pasar es que el
    documento elija el desenlace más tranquilizador y lo firme.

    El orden de las ramas es el del glosario y no es libre: (d)/(e) van ANTES de
    la de (c), que hasta aquí era el `else` de todo y por eso se tragaba lo que
    nadie había traducido. Lo que hoy no encaja en ninguna sale por
    :data:`ESTADO_DE_CONSULTA_NO_INTERPRETABLE`, que declara la ignorancia en vez
    de exonerar: un sexto estado en el glosario compartido ya no hereda la
    afirmación más cara del bloque, y la guarda derivada de `pr.estados()` lo
    caza en la primera corrida.

    ``None`` sólo en (c) sin candidatos, que es cuando el aviso por defecto del
    PDF —:data:`SIN_CORRELACION_EN_CATALOGO`— dice exactamente lo que pasó.
    """
    if corr is None:
        return None

    # Los descartes son del catálogo YA CARGADO en la base, y eso no cierra la
    # pregunta a la fuente viva: en (a), (b), (d) y (e) se dicen porque son
    # información, pero encabezados por el hecho que manda.
    cargado = (
        ""
        if not corr.descartes
        else (
            f" En el catálogo ya cargado había {len(corr.descartes)} evento(s) en la "
            f"ventana y ninguno es éste — {_motivos(corr)}."
        )
    )

    if corr.estado == pr.SIN_DATO_EXTERNO:
        return f"{SIN_CONSULTA_A_FUENTE_EXTERNA}{cargado}"

    if corr.estado == pr.CONSULTANDO:
        # Quién y cuándo, porque un «en curso» sin fecha es otra forma de no
        # decir nada: con la hora, quien lea el dictamen sabe si la pregunta es
        # de hace un minuto o lleva seis horas sin respuesta.
        quien = (
            f" Se preguntó a {corr.fuente or 'la fuente externa'}"
            f"{_hora_de_la_fuente(corr.consultado_en)}."
        )
        return f"{CONSULTA_EXTERNA_EN_VUELO}{quien}{cargado}"

    if corr.estado in (pr.PRELIMINAR, pr.CONFIRMADO):
        # El rótulo del glosario va SIEMPRE, y no sólo porque separe estas dos
        # líneas: una solución que la propia fuente declara PRELIMINAR puede
        # cambiar, y una discrepancia contra una preliminar no pesa lo mismo que
        # contra una que la fuente ya revisó. Sale del glosario compartido para
        # que el papel diga la misma palabra que la consola.
        quien = (
            f" Contestó {corr.fuente or 'la fuente externa'}"
            f"{_hora_de_la_fuente(corr.consultado_en)} y su solución es "
            f"{pr.rotulo(corr.estado, 'consola')}."
        )
        return f"{CORRELACION_EN_DISPUTA}{quien}{cargado}"

    if corr.estado == pr.SIN_CORRELACION:
        if corr.descartes:
            return (
                f"SIN CORRELACIÓN · {len(corr.descartes)} evento(s) del catálogo en la "
                f"ventana y ninguno es éste — {_motivos(corr)}"
            )
        return None

    # Un estado que este documento no sabe traducir. No se calla y no exonera.
    return (
        f"{ESTADO_DE_CONSULTA_NO_INTERPRETABLE} El estado registrado es {corr.estado!r}.{cargado}"
    )


def _catalog_line(f: ForensicsOut) -> str | None:
    """La correlación con el catálogo, tal como se imprime en un papel FIRMADO.

    [T-5.11] Tres cosas cambian respecto de lo que se imprimía antes.

    **(1) Un acierto sin epicentro propio ya no se presenta como contraste.** Era
    la línea `"… · sin epicentro propio que comparar"` bajo el rótulo «contraste
    con catálogo»: una verificación anunciada que no había ocurrido. En la ruta
    del receptor —la normal— no hay nada nuestro que contrastar, y eso se dice.

    **(2) «No casó» deja de ser un hueco.** Si hubo eventos en la ventana y
    ninguno es éste, se imprime con su motivo: es la diferencia entre «el
    catálogo no tiene nada» y «lo que tiene no es esto».

    **(3) La magnitud del catálogo solo se imprime con procedencia** (regla de
    `T-5.10`). Casar no la concede: una fila sin hora de consulta ni estado de
    revisión es un dato que existe y no es citable, y el dictamen es justamente
    el sitio donde una cifra ajena sin procedencia se lee como propia.

    [T-7.25] Y sin acierto no hay UN caso sino CINCO, que no se pueden imprimir
    igual: los separa :func:`_linea_sin_acierto`. Los dos últimos —la consulta
    correlacionó y este criterio de identidad no reconoce el acierto— son los que
    esta condición manda aquí con `catalog` en `None` y un estado que SÍ pinta
    cifra: por eso la rama de abajo no puede ser el único sitio donde
    `preliminar` y `confirmado` se traducen.
    """
    corr = f.catalog_correlation
    if not f.catalog or not f.catalog_delta:
        return _linea_sin_acierto(corr)

    d = f.catalog_delta
    partes = [f"{f.catalog.source} {f.catalog.catalog_key}"]
    if f.catalog.magnitude is not None and corr and pr.pinta_cifra(corr.estado):
        partes.append(f"M {f.catalog.magnitude:.1f} ({pr.rotulo(corr.estado, 'consola')})")
    elif f.catalog.magnitude is not None:
        partes.append(f"magnitud no citable ({pr.rotulo(corr.estado, 'consola') if corr else '—'})")
    partes.append(f"Δt {d.dt_s:.0f} s")
    if d.km is not None:
        partes.append(f"CONTRASTE {d.km:.0f} km {d.bearing or ''}".strip())
    else:
        sitio = (
            f"{f.catalog.km_al_sitio:.0f} km del sitio"
            if f.catalog.km_al_sitio is not None
            else "distancia al sitio no calculable"
        )
        partes.append(f"{sitio} · NO VERIFICABLE: sin epicentro propio que contrastar")
    return " · ".join(partes)


async def _series(
    conn: AsyncConnection, *, site_id: str, f: ForensicsOut
) -> dict[str, list[tuple[datetime, float | None, bool]]]:
    """Serie 1 Hz por canal para las trazas de envolvente."""
    out: dict[str, list[tuple[datetime, float | None, bool]]] = {}
    rows = await qf.series(conn, site_id=site_id, from_ts=f.window_from, to_ts=f.window_to)
    for r in rows:
        out.setdefault(r.channel, []).append((r.ts, r.pga_g, bool(r.clipping)))
    return out


async def _danos(conn, incident_id: str, evidence_rows, fetch_object) -> list[DanoFila]:
    """Los reportes de daños del brigadista, con sus fotografías preparadas.

    [T-7.22] Best-effort y fail-soft, igual que el miniSEED: un fallo de S3
    degrada la FOTO —que imprime su razón— y nunca tumba la exportación. Es el
    criterio escrito del endpoint, y con N fotos la superficie de fallo es N
    veces mayor que con un solo objeto.

    Las claves de S3 salen de las filas de `evidence_objects` que el modelo YA
    leyó: `damage_reports.evidence_ids` es un `uuid[]` sin clave foránea, así que
    el cruce se hace aquí, contra lo que ya está en memoria. Abrir una segunda
    consulta a la misma tabla daría dos lecturas que pueden discrepar en dos
    páginas del mismo papel.

    **La huella se MIDE además de leerse.** `evidence_objects.sha256` es lo que
    declaró el dispositivo al registrar y el servidor nunca verificó —por eso
    existe `POST /evidence/{id}/verify` como operación aparte—. Medirlo aquí es
    gratis: los bytes hay que bajarlos de todos modos para dibujarlos. Y un
    desajuste es lo más importante que esta sección puede decir de una fotografía
    de evidencia.
    """
    filas = (await conn.execute(_DANOS, {"id": incident_id})).all()
    if not filas:
        return []

    por_id = {str(r.evidence_id): r for r in evidence_rows}
    presupuesto = fotos_mod.MAX_BYTES_FOTOS_DOCUMENTO
    salida: list[DanoFila] = []

    for fila in filas:
        ids = [str(v) for v in (fila.evidence_ids or [])]
        cabe = ids[: fotos_mod.MAX_FOTOS_POR_REPORTE]
        fotos: list[FotoFila] = []
        for evidence_id in cabe:
            objeto = por_id.get(evidence_id)
            if objeto is None:
                # La fila de daños apunta a una evidencia que no está en el
                # incidente. No se calla: el `uuid[]` no tiene clave foránea que
                # lo impida, así que puede pasar de verdad.
                fotos.append(
                    FotoFila(
                        evidence_id=evidence_id,
                        sha256_declarado="",
                        motivo=fotos_mod.SIN_BLOB,
                    )
                )
                continue
            if presupuesto <= 0 or fetch_object is None:
                fotos.append(
                    FotoFila(
                        evidence_id=evidence_id,
                        sha256_declarado=objeto.sha256 or "",
                        motivo=fotos_mod.DOCUMENTO_LLENO
                        if presupuesto <= 0
                        else fotos_mod.SIN_BLOB,
                    )
                )
                continue
            try:
                crudo = fetch_object(objeto.s3_key)
            except Exception as exc:  # noqa: BLE001 - un fallo de S3 no tumba la evidencia
                log.warning("dictamen: foto ilegible (%s): %s", objeto.s3_key, exc)
                crudo = None
            derivada = fotos_mod.preparar(crudo)
            if derivada.ok and derivada.jpeg is not None:
                presupuesto -= len(derivada.jpeg)
            fotos.append(
                FotoFila(
                    evidence_id=evidence_id,
                    sha256_declarado=objeto.sha256 or "",
                    sha256_medido=hashlib.sha256(crudo).hexdigest() if crudo else None,
                    sha256_impreso=derivada.sha256,
                    ancho=derivada.ancho,
                    alto=derivada.alto,
                    motivo=derivada.motivo,
                    jpeg=derivada.jpeg,
                )
            )
        salida.append(
            DanoFila(
                report_id=str(fila.report_id),
                rol=fila.rol,
                zona=fila.zona,
                categorias=list(fila.categories or []),
                personas_en_riesgo=bool(fila.people_at_risk),
                notas=fila.notes,
                ts=fila.ts,
                fotos=fotos,
                fotos_omitidas=max(0, len(ids) - len(cabe)),
            )
        )
    return salida


async def _raw_waveform(evidence_rows, fetch_object, variant: str):
    """`(waveform, rate, spectrum, peak_hz, espectrograma, duracion, reason)`.

    Best-effort y fail-soft: cualquier fallo devuelve la razón escrita y el
    documento sale igual. El espectrograma acompaña al espectro en todas las
    salidas —incluidas las tempranas— porque un `None` suelto en una de ellas
    sería un hueco donde hay una razón.
    """
    if variant != "technical":
        return {}, None, None, None, None, None, "El resumen ejecutivo no incluye análisis de onda."
    if fetch_object is None:
        return {}, None, None, None, None, None, None

    mseed = next((r for r in evidence_rows if r.kind == "miniseed"), None)
    if mseed is None:
        return {}, None, None, None, None, None, None

    try:
        blob = fetch_object(mseed.s3_key)
        traces = read_traces(blob)
    except MseedError as exc:
        log.warning("dictamen: miniSEED ilegible (%s): %s", mseed.s3_key, exc)
        return {}, None, None, None, None, None, f"MINISEED ARCHIVADO ILEGIBLE · {exc}"
    except Exception as exc:  # noqa: BLE001 - un fallo de S3 no puede tumbar la evidencia
        log.warning("dictamen: no se pudo leer el miniSEED (%s): %s", mseed.s3_key, exc)
        return {}, None, None, None, None, None, "NO SE PUDO RECUPERAR EL MINISEED ARCHIVADO"

    if not traces:
        return {}, None, None, None, None, None, "EL MINISEED ARCHIVADO NO CONTIENE TRAZAS"

    waveform = {t.channel: t.samples for t in traces}
    rate = traces[0].sample_rate
    # [T-3.14] El MISMO canal que el espectro, y no el que más sacudió: dos figuras del
    # mismo dictamen que describieran trazas distintas serían una trampa para quien las
    # compare. Si algún día se mide por canal, se declaran los tres, no se cambia éste.
    dominante = max(traces, key=lambda t: len(t.samples))
    spectrum, peak_hz = _spectrum(dominante, rate)
    # [T-5.23] El MISMO canal dominante que el espectro y que la duración. Dos
    # figuras del mismo dictamen que describieran trazas distintas serían una
    # trampa para quien las compare (es la razón que ya dejó escrita `T-3.14`).
    espectrograma = calcular_espectrograma(
        dominante.samples, rate, dominante.channel, max_muestras=MAX_FFT_SAMPLES
    )
    duracion = significativa(dominante.samples, sample_rate=rate, canal=dominante.channel)
    return waveform, rate, spectrum, peak_hz, espectrograma, duracion, None


def _spectrum(trace, rate: float):
    """Espectro de amplitud del canal con más muestras.

    Se le quita la media antes de transformar: el waveform crudo del RS4D trae una
    componente DC enorme (millones de cuentas) que, sin restarla, domina el espectro
    entero y esconde todo lo demás. Es el mismo hallazgo de T-2.25 sobre el panel.
    """
    import numpy as np  # noqa: PLC0415 - import perezoso: solo el técnico lo necesita

    # [T-7.39] La ventana se centra en el PICO, no en el principio de la traza.
    # Con `evidence_pre_s = 60` y 100 sps, `samples[:6000]` eran exactamente los
    # 60 segundos ANTERIORES al evento: el espectro que el documento presenta como
    # contenido espectral del sismo se calculaba sobre el ruido de fondo previo y
    # no llegaba a tocar la sacudida. Las cifras eran ciertas y describían otra cosa.
    crudo = np.asarray(trace.samples, dtype=np.float64)
    if crudo.size > MAX_FFT_SAMPLES:
        pico = int(np.argmax(np.abs(crudo - crudo.mean())))
        inicio = max(0, min(pico - MAX_FFT_SAMPLES // 2, crudo.size - MAX_FFT_SAMPLES))
        samples = crudo[inicio : inicio + MAX_FFT_SAMPLES]
    else:
        samples = crudo
    if samples.size < 32 or rate <= 0:
        return None, None
    samples = samples - samples.mean()
    windowed = samples * np.hanning(samples.size)
    amps = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / rate)

    # Se descarta la primera muestra (DC residual) para el pico: no es una frecuencia.
    peak_hz = float(freqs[1:][int(np.argmax(amps[1:]))]) if amps.size > 1 else None
    # Se diezma a ~400 puntos: más no se distingue en la banda útil del papel
    # (185.9 mm en Carta desde `T-7.21`; eran 180 en A4).
    step = max(1, freqs.size // 400)
    return (freqs[::step].tolist(), amps[::step].tolist()), peak_hz
