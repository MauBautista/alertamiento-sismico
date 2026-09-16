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
from datetime import datetime

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
    NO_CCTV,
    STATUS_LABELS,
    ActionRow,
    CctvBlock,
    CctvObjectRow,
    ChannelRow,
    DanoFila,
    DictamenRow,
    EstacionFila,
    EvidenceRow,
    FotoFila,
    ReportModel,
    VoteRow,
)
from takab_api.dictamen.mseed import MseedError, read_traces
from takab_api.documentos import fotos as fotos_mod
from takab_api.estaciones import build_estaciones
from takab_api.felt import umbral_congelado
from takab_api.forensics import build_forensics, umbral_de_comparacion
from takab_api.queries import compliance as qc
from takab_api.queries import forensics as qf
from takab_api.schemas import cctv as esq_cctv
from takab_api.schemas.forensics import ForensicsOut
from takab_api.settings import Settings

log = logging.getLogger(__name__)

#: Muestras máximas por canal para la FFT. 60 s a 100 sps es de sobra para ver el
#: contenido de una sacudida y acota el coste dentro de un request HTTP.
MAX_FFT_SAMPLES = 6000

_INCIDENT = text(
    """
    SELECT i.incident_id, i.site_id, i.tenant_id, i.event_id, i.opened_at, i.closed_at,
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
    """
    corr = f.catalog_correlation
    if not f.catalog or not f.catalog_delta:
        if corr and corr.descartes:
            motivos = " · ".join(f"{d.catalog_key}: {d.detalle}" for d in corr.descartes[:3])
            return (
                f"SIN CORRELACIÓN · {len(corr.descartes)} evento(s) del catálogo en la "
                f"ventana y ninguno es éste — {motivos}"
            )
        return None

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
