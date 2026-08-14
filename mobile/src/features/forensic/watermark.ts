// Marca de agua forense (2.3) — HORNEADA en el pixel (§2.1-B). Este módulo es
// PURO: arma las líneas de texto que se componen sobre el bitmap y el JSON de
// metadatos duplicado. La honestidad manda: el PGA del gabinete sale del
// backend; sin red se rotula "PGA: pendiente de sync" y JAMÁS se inventa.

export type ForensicMeta = {
  /** ISO del reloj del DISPOSITIVO al capturar (se registra tal cual). */
  tsDevice: string;
  /** Offset NTP (ms) del ÚLTIMO sync del gabinete; null = desconocido. */
  ntpOffsetMs: number | null;
  /** [lon, lat] con consentimiento; null = sin ubicación. */
  gps: [number, number] | null;
  /** PGA (g) que el gabinete registró en ese momento; null = pendiente de sync. */
  pgaG: number | null;
  /** Sub del operador táctico (identidad de la captura). */
  operatorId: string;
  /** Sitio del incidente (contexto). */
  siteId: string;
  /**
   * [T-2.135] Incidente al que se atribuye la captura. `null` = no consta.
   *
   * Va al MANIFIESTO (`forensicMetadata`) y NO al pixel: la razón de custodia,
   * entera, está en el docblock de `forensicMetadata`. Añadirlo aquí no cambia
   * `watermarkLines` ni, por tanto, el SHA-256 — hay un test que lo exige.
   *
   * `string | null` y no `""`: sale del mismo snapshot de `mobile-state` que
   * `pgaG`, y una cadena vacía en un manifiesto forense es una afirmación falsa
   * con aspecto de dato.
   */
  incidentId: string | null;
  /**
   * [T-2.118] Epoch ms del snapshot de `mobile-state` del que salieron
   * `incident_id` y `pgaG` CUANDO ese snapshot ya no era fresco; null = se
   * selló con dato vigente.
   *
   * Existe porque la cámara forense no PRESENTA el dato del servidor: lo
   * SELLA. Un número viejo pintado en pantalla se corrige al refrescar; un
   * número viejo horneado en el pixel entra en la cadena de custodia y ya no
   * se corrige nunca. La política —razón larga en `app/camera.tsx`— es sellar
   * igual y DECLARAR la edad, no negarse a sellar.
   */
  snapshotStaleSinceMs: number | null;
};

function fmtTs(iso: string, ntpOffsetMs: number | null): string {
  const base = iso.replace("T", " ").replace(/\.\d+Z$/, "Z");
  const off = ntpOffsetMs === null ? "NTP: S/D" : `NTP ${ntpOffsetMs >= 0 ? "+" : ""}${ntpOffsetMs.toFixed(1)} ms`;
  return `${base} · ${off}`;
}

function fmtGps(gps: [number, number] | null): string {
  if (gps === null) {
    return "GPS: sin ubicación";
  }
  const [lon, lat] = gps;
  return `GPS ${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

function fmtPga(pgaG: number | null): string {
  // Honestidad §2.3: sin dato del gabinete NO se inventa un número.
  return pgaG === null ? "PGA: pendiente de sync" : `PGA ${pgaG.toFixed(3)} g (gabinete)`;
}

/** ISO legible (mismo formato que `fmtTs`) del instante del snapshot. */
function isoLegible(epochMs: number): string {
  return new Date(epochMs).toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
}

/**
 * [T-2.118] La advertencia de procedencia, cuando el snapshot con el que se
 * sella NO era fresco. Instante ABSOLUTO y no relativo a propósito: un exhibit
 * se lee meses después y «hace 18 min» no significa nada en un expediente.
 */
function fmtSnapshot(staleSinceMs: number | null): string | null {
  if (staleSinceMs === null) {
    return null;
  }
  return `METADATOS RETENIDOS · SNAPSHOT ${isoLegible(staleSinceMs)} · sin conexión`;
}

/** Líneas de la marca de agua compuestas sobre el pixel (orden fijo).
 *
 *  La advertencia de snapshot retenido va en SEGUNDA posición, no al final:
 *  la lección de T-2.104 es que lo que se lee primero manda, y un deslinde
 *  escondido bajo cuatro líneas de metadatos no deslinda nada. */
export function watermarkLines(meta: ForensicMeta): string[] {
  const retenido = fmtSnapshot(meta.snapshotStaleSinceMs);
  return [
    "TAKAB AILERT · EVIDENCIA FORENSE",
    ...(retenido === null ? [] : [retenido]),
    fmtTs(meta.tsDevice, meta.ntpOffsetMs),
    fmtGps(meta.gps),
    fmtPga(meta.pgaG),
    `OP ${meta.operatorId.slice(0, 8)} · SHA-256`,
  ];
}

/**
 * Metadatos duplicados en el JSON firmado adjunto al reporte (§4.2).
 *
 * ===========================================================================
 * [T-2.126] ESTO TODAVÍA NO VIAJA CON LA EVIDENCIA, Y AQUÍ ESTÁ POR QUÉ.
 * ===========================================================================
 *
 * Medido el 2026-08-12: **cero llamadas en producción**. El único invocador es
 * el test de al lado. La foto sale de este teléfono con la marca HORNEADA en el
 * pixel (`watermarkLines`, `app/camera.tsx`) y con su SHA-256 — y con nada más.
 *
 * El pixel prueba LO QUE SE VE; este JSON prueba LA ATRIBUCIÓN (quién, dónde,
 * con qué instante y con qué procedencia del dato). Son piezas distintas del
 * mismo expediente, y hoy sólo viaja la primera.
 *
 * NO SE CABLEA EN ESTA FICHA PORQUE NO HAY POR DÓNDE. La costura entera, con el
 * cambio exacto — ninguna de las cuatro piezas vive en `mobile/`:
 *
 *  1. **El contrato no tiene campo.** `EvidenceRegisterIn`
 *     (`api/src/takab_api/schemas/mobile.py`) declara `evidence_id`, `sha256`,
 *     `content_type` y `ts_from`. Haría falta un campo de metadatos + regenerar
 *     `shared/sdk-ts`. Lo vigila el test de al lado, que se pone rojo el día que
 *     el campo aparezca.
 *  2. **La tabla no tiene columna.** `evidence_objects` (`db/schema.sql`) no
 *     lleva JSONB y es **append-only** por trigger: no es «un UPDATE luego»,
 *     es una migración y una decisión de retención (regla de oro 11: la
 *     evidencia no se poda).
 *  3. **No hay segundo objeto en S3.** `register_evidence`
 *     (`api/src/takab_api/routers/mobile_incident.py`) DERIVA la clave como
 *     `evidence/{tenant}/{incident}/photo-{id}.jpg`, una sola por registro. Un
 *     sidecar `.json` no cabe sin cambiar esa derivación — y colar el JSON como
 *     si fuera otra «foto» ensuciaría `kind` y la verificación de huella.
 *  4. **«FIRMADO» no es adorno: hoy no se puede firmar esto.** La spec §2.3/§4.2
 *     pide un JSON *firmado*. La llave de hardware existe (`security/deviceKey.ts`,
 *     `signIntent`) y el servidor ya verifica firmas contra `device_keys` para
 *     `POST /sites/{id}/commands` — pero para la evidencia no hay ni canonicalización
 *     acordada ni verificación server-side. Publicar el JSON **sin** firma sería
 *     repetir el defecto que esta ficha denuncia: una pieza que *parece* que
 *     está.
 *
 * ===========================================================================
 * [T-2.135] EL INCIDENTE ENTRA AQUÍ, EN EL MANIFIESTO — Y NO EN EL PIXEL
 * ===========================================================================
 *
 * `ForensicMeta` existe para probar «quién, dónde, CON QUÉ INCIDENTE» y no
 * llevaba el incidente: esa mitad vivía sólo en `offline/queue.ts::EvidencePayload`,
 * que es el TRANSPORTE (lo que se le dice al servidor para archivar), no el
 * manifiesto (lo que el expediente afirma por sí mismo). La decisión era de
 * custodia, no de código, y por eso `T-2.126` no la tomó: la spec §2.3 enumera
 * lo que va EN EL PIXEL, y el incidente no está — meterlo ahí cambiaría lo que
 * entra en el SHA-256.
 *
 * VA AL JSON. La spec §2.3 NO se toca, y el sello sigue significando exactamente
 * lo que significaba. Las tres razones, en orden de peso:
 *
 *  1. **El vínculo foto→incidente ya existe y es verificable sin el pixel.**
 *     `evidence_objects` guarda `(incident_id, sha256)`, es append-only por
 *     trigger y está exenta de poda (regla de oro 11), y
 *     `POST /evidence/{id}/verify` recalcula la huella del blob y la compara.
 *     Dado el archivo se llega al incidente por su hash. Lo que faltaba no era
 *     el vínculo: era que el MANIFIESTO —la pieza que existe justamente para
 *     probar la atribución— supiera decirlo.
 *
 *  2. **Lo que `T-2.118` horneó era de otra naturaleza.** El aviso de
 *     «METADATOS RETENIDOS» es una advertencia sobre la fiabilidad del propio
 *     sello: separada de la imagen, la imagen MIENTE por omisión. El incidente
 *     no advierte de nada, atribuye — y la atribución es precisamente lo que el
 *     JSON *firmado* de la spec §4.2 existe para sostener. Ponerla en el pixel
 *     sería ponerla donde no se puede firmar, y dejar sin trabajo a la pieza que
 *     sí va a llevar firma.
 *
 *  3. **La que decide, y es la que impide la tentación:** el `incidentId` sale
 *     del MISMO snapshot de `mobile-state` que `T-2.118` ya declaró que puede
 *     estar viejo. Un snapshot retenido puede nombrar el incidente ANTERIOR. En
 *     el item de la cola eso es corregible —el servidor valida el alcance y
 *     puede rechazar (404/409)—; horneado en el pixel sería PERMANENTE: un
 *     exhibit que afirma, dentro del sello y para siempre, una atribución que
 *     puede ser falsa. Frente a eso, `snapshot_retained` califica al incidente
 *     igual que al PGA: el manifiesto dice de qué snapshot salió, y quien lo
 *     lea sabe cuánta fe darle. Un pixel no puede matizarse después.
 *
 * Sigue sin viajar, como todo este JSON, y eso no cambia con esta ficha: el
 * campo nace CONSISTENTE para el día de la costura, que es exactamente lo que
 * `T-2.118` hizo con el aviso de retenidos. La ficha pedía decidir, no cablear.
 *
 * NO SE BORRA, y ésa es la otra mitad de la decisión: `T-2.118` lo dejó
 * consistente con el aviso horneado en el pixel, y esa consistencia es la parte
 * cara. Borrarlo la tiraría para tener que reescribirla el día de la costura.
 * Lo que sí cambia hoy es que la consistencia deja de depender de que alguien se
 * acuerde: el JSON lleva las LÍNEAS EXACTAS del pixel, así que ninguna de las
 * dos piezas puede moverse sin la otra.
 */
export function forensicMetadata(meta: ForensicMeta): Record<string, unknown> {
  return {
    schema: "takab-forensic-v1",
    ts_device: meta.tsDevice,
    ntp_offset_ms: meta.ntpOffsetMs,
    gps: meta.gps,
    pga_g: meta.pgaG,
    pga_pending: meta.pgaG === null,
    operator_id: meta.operatorId,
    site_id: meta.siteId,
    // [T-2.135] La tercera pata de la atribución: «con qué incidente». Va aquí y
    // no en el pixel — razón completa arriba. Queda calificada por
    // `snapshot_retained`, igual que `pga_g`: las dos salen del mismo snapshot.
    incident_id: meta.incidentId,
    // [T-2.118] Lo MISMO que declara el pixel: si el JSON callara la edad del
    // snapshot mientras la marca la declara, la contradicción dentro del propio
    // expediente valdría menos que no declarar nada.
    snapshot_stale_since:
      meta.snapshotStaleSinceMs === null ? null : new Date(meta.snapshotStaleSinceMs).toISOString(),
    snapshot_retained: meta.snapshotStaleSinceMs !== null,
    // [T-2.126] Las líneas EXACTAS que se hornean en el bitmap y entran en el
    // SHA-256. No es un campo más: es lo que hace que los dos espejos no puedan
    // divergir POR CONSTRUCCIÓN. Duplicar los campos en paralelo —como estaba—
    // deja abierta la puerta de siempre: se añade una línea al pixel (lo hizo
    // T-2.118 con el aviso de retenidos) y el JSON se queda callado sin que
    // ningún test lo eche de menos. Además le da al verificador algo que puede
    // confrontar contra la foto carácter a carácter.
    watermark_lines: watermarkLines(meta),
    integrity: "sha256",
  };
}
