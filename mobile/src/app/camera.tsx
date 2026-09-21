// 2.3 · Cámara forense — captura con marca de agua HORNEADA en el pixel.
// Flujo: CameraView toma la foto → se compone con la marca (watermarkLines) en
// un View capturado por view-shot → archivo privado + SHA-256 → A LA COLA
// OFFLINE. La foto JAMÁS va a la galería del sistema.
//
// [T-2.108] Antes se registraba y subía AQUÍ mismo (POST directo). Sin red la
// llamada moría, el botón mostraba un error y la foto forense —ya capturada,
// ya con su huella— se quedaba en un archivo que nadie volvía a mirar. Ahora
// se encola: la subida la hace `offline/sync.ts` cuando hay red, y el archivo
// no se toca en el camino (la huella sellada aquí es la que se verifica).
//
// ---------------------------------------------------------------------------
// [T-2.118] QUÉ PASA CUANDO EL DATO CON EL QUE SE SELLA ESTÁ VIEJO
// ---------------------------------------------------------------------------
// Esta pantalla es el caso raro del censo de la regla de oro 7: POSEE dato de
// servidor y NO LO PRESENTA. Lee `mobile-state` para tomar `incident_id` y
// `max_pga_g` y HORNEARLOS en la marca de agua de una foto de evidencia.
//
// Por eso el defecto aquí es de otra especie. Un número viejo pintado en
// pantalla se corrige solo al refrescar; un número viejo horneado en el pixel
// entra en la cadena de custodia con una atribución que no corresponde —la foto
// queda archivada bajo un incidente que quizá ya cerró— y no se corrige nunca
// más, porque la marca está dentro del bitmap y dentro del SHA-256.
//
// SE CONSIDERARON TRES SALIDAS Y SE DESCARTARON DOS:
//
//  (a) NEGARSE A SELLAR con el snapshot viejo. Descartada. La evidencia es
//      perecedera y no se puede volver a tomar: el muro se apuntala, el
//      escombro se retira, el edificio se entrega. Y la falta de red es
//      EXACTAMENTE el escenario para el que existe esta cámara (T-2.108 movió
//      la subida a la cola offline por eso mismo). Negarse convierte un
//      problema de ETIQUETA en una pérdida TOTAL, y lo hace justo cuando más
//      falta hace la foto.
//  (b) SELLAR SIN EL DATO. Descartada. Pierde la atribución entera: la foto
//      queda huérfana y nadie puede archivarla — además de que la cola exige
//      `incident_id` para encolarla.
//  (c) SELLAR DECLARANDO LA EDAD. **Elegida.** El sello dice de qué instante
//      salieron sus metadatos, y lo dice EN EL PIXEL: es el único lugar del
//      sistema del que el aviso no se puede separar después —ni recortando,
//      ni re-codificando, ni perdiendo un JSON adjunto—, porque entra en la
//      huella junto con la imagen. Quien lea el expediente ve la salvedad en
//      la propia pieza y la pondera. Nada queda silenciosamente mal.
//
// Y dos consecuencias que van con la decisión:
//  · A la persona se le avisa ANTES de disparar (banner de retenidos sobre el
//    visor), no después: la decisión de fotografiar tiene que ser informada.
//  · SIN NINGÚN SNAPSHOT no se sella —no habría a qué incidente atribuir— y se
//    dice que NO SE PUDO PREGUNTAR. Antes esta pantalla escribía «Sin incidente
//    activo» ante cualquier `incidentId === null`, confundiendo «el servidor
//    dice que no hay incidente» con «no pudimos preguntar»: el mismo embuste
//    que T-2.111 cazó en `lista.tsx`, y aquí más caro, porque la persona que se
//    lo cree se va sin levantar la evidencia.
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Crypto from "expo-crypto";
import { useRouter } from "expo-router";
import { useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { useAlertState } from "@/features/alert/useAlertState";
import { avisoIALineas } from "@/features/forensic/avisoIA";
import { captureForensicPhoto } from "@/features/forensic/capture";
import { watermarkLines, type ForensicMeta } from "@/features/forensic/watermark";
import { useDamageDraft } from "@/features/damage/draft.store";
import { useQueueStore } from "@/offline/queue.store";
import { drainQueue } from "@/offline/sync";
import { useWatchedSiteId } from "@/services/mySite";
import { StateFrame } from "@/ui/StateFrame";
import { emergency, fontSize, palette, radius, space, touch } from "@/ui/theme";

/** Sin sitio vigilado no hay incidente al que atribuir la foto: se DICE. */
const SIN_SITIO =
  "Este teléfono no está vinculado a ningún edificio, así que una foto no podría atribuirse a ningún incidente. Vincúlese con el código de su inmueble para levantar evidencia.";

/** El servidor SÍ respondió y no hay incidente abierto: vacío honesto. */
const SIN_INCIDENTE = "Sin incidente activo en su sitio: no se levanta evidencia forense.";

/** No se pudo preguntar. Accionable y sin fingir: dice qué NO ha pasado. */
const SIN_ESTADO =
  "No se pudo consultar el incidente de su sitio, así que una foto sellada ahora no podría atribuirse a ninguno. No se ha perdido ninguna foto: reintente, o vuelva en cuanto la app recupere el estado del sitio.";

/**
 * [T-7.27 · D-32] El aviso de destino, EN LOS DOS MOMENTOS en que se decide.
 *
 * Va en el visor porque encuadrar ya es una decisión —en un pasillo evacuado
 * entran caras, matrículas y papeles que nadie eligió mandar— y va otra vez en
 * la revisión porque «USAR ESTA FOTO» es el toque que la encola: es ahí donde
 * la imagen deja de ser sólo de este teléfono. El del visor no cubre el
 * segundo: para entonces la persona ya disparó.
 *
 * Es fijo y no descartable a propósito. Tampoco entra en el sello: la razón
 * larga —las tres de T-2.135— está en `features/forensic/watermark.test.ts`.
 *
 * La tinta es la MISMA pareja que ya lleva la marca de agua sobre la imagen
 * (`veil.ink` sobre `veil.base`): estrenar un par de colores para un aviso que
 * se lee encima del visor sería estrenar un contraste que nadie ha medido. El
 * borde en `warn` acompaña, no informa — quien no distinga el color lee
 * exactamente lo mismo.
 */
function AvisoIA() {
  const [titulo, ...resto] = avisoIALineas();
  return (
    <View pointerEvents="none" style={styles.avisoIa} testID="aviso-ia">
      <Text style={styles.avisoIaTitulo}>{titulo}</Text>
      {resto.map((linea) => (
        <Text key={linea} style={styles.avisoIaTexto}>
          {linea}
        </Text>
      ))}
    </View>
  );
}

export default function Camera() {
  const router = useRouter();
  const siteId = useWatchedSiteId();
  const { data, loading, error, staleSinceMs, refetch } = useAlertState(siteId);
  const me = useSessionStore((s) => s.me);
  const addEvidence = useDamageDraft((s) => s.addEvidence);

  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const composeRef = useRef<View>(null);
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [capturaError, setCapturaError] = useState<string | null>(null);

  const incidentId = data?.incident?.incident_id ?? null;
  // La edad del snapshot con el que se SELLA. Misma expresión que usan las
  // pantallas que lo PINTAN — aquí, además, se hornea (ver cabecera).
  // [T-5.21] Del RELOJ. Esta es la que acaba IMPRESA EN EL PÍXEL de una
  // fotografía forense: un «METADATOS RETENIDOS» que solo aparecía cuando la
  // consulta fallaba dejaba fotos con metadatos de hace diez minutos sin
  // marca ninguna, y esa foto va a un dictamen.
  const snapshotStaleSinceMs = data !== null ? staleSinceMs : null;
  const meta: ForensicMeta = {
    tsDevice: new Date().toISOString(),
    ntpOffsetMs: null, // el offset del último sync se adjunta en T-2.11
    gps: null, // GPS con consentimiento se integra en el flujo de captura
    pgaG: data?.incident?.max_pga_g ?? null, // null ⇒ "pendiente de sync" honesto
    operatorId: me?.sub ?? "desconocido",
    siteId: siteId ?? "",
    // [T-2.135] La atribución al incidente entra en el MANIFIESTO, no en el
    // pixel: sale de este mismo snapshot, así que `snapshotStaleSinceMs` la
    // califica igual que al PGA. Horneada sería permanente aunque el snapshot
    // viejo nombrara el incidente anterior. Razón completa en `watermark.ts`.
    incidentId,
    snapshotStaleSinceMs,
  };

  // EXENCIÓN DECLARADA (T-2.118): el permiso de cámara DENEGADO no es uno de
  // los cuatro estados del dato de servidor. Es una precondición del APARATO y
  // tiene su propio remedio —el botón de conceder—, que el `StateFrame` no sabe
  // pintar: meterlo dentro dejaría a la persona sin acción, que es peor. El
  // permiso AÚN SIN RESOLVER sí entra en el marco, como `loading`, porque ahí
  // lo único que cabe hacer es esperar.
  if (permission != null && !permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.hint}>La cámara forense necesita permiso de cámara.</Text>
        <Pressable accessibilityRole="button" onPress={requestPermission} style={styles.btn}>
          <Text style={styles.btnText}>CONCEDER PERMISO</Text>
        </Pressable>
      </View>
    );
  }

  const take = () => {
    setBusy(true);
    setCapturaError(null);
    void (async () => {
      try {
        const shot = await cameraRef.current?.takePictureAsync({ quality: 0.9 });
        setBusy(false);
        if (shot?.uri) {
          setPhotoUri(shot.uri);
        } else {
          setCapturaError("No se pudo capturar la foto. No se ha guardado nada: vuelva a intentarlo.");
        }
      } catch {
        setBusy(false);
        setCapturaError("No se pudo capturar la foto. No se ha guardado nada: vuelva a intentarlo.");
      }
    })();
  };

  const use = () => {
    // ⚠️ [T-7.58] ESTE `return` ERA MUDO, y es el peor sitio del recorrido para
    // callarse: el brigadista toca «USAR ESTA FOTO», no pasa NADA —ni foto, ni
    // aviso, ni navegación— y se va creyendo que mandó la prueba de un daño
    // estructural. La foto forense acaba en `evidence_objects`, que no admite
    // reescritura: lo que no se capturó no se recupera después.
    //
    // Las dos causas piden cosas distintas y por eso se nombran por separado:
    // sin vista de composición no hay nada que sellar (la pantalla aún no ha
    // terminado de montarse, y reintentar funciona); sin incidente no hay a qué
    // colgar la evidencia, y reintentar no va a arreglarlo solo.
    if (composeRef.current === null) {
      setCapturaError(
        "La vista de la foto aún no está lista. No se ha guardado nada: vuelva a intentarlo.",
      );
      return;
    }
    if (incidentId === null) {
      setCapturaError(
        "No hay incidente al que adjuntar la foto. No se ha guardado nada: vuelva a la pantalla " +
          "anterior y entre otra vez desde el reporte de daños.",
      );
      return;
    }
    setBusy(true);
    setCapturaError(null);
    void (async () => {
      try {
        const id = Crypto.randomUUID();
        const captured = await captureForensicPhoto(composeRef as never, meta, id);
        // La cola guarda el PUNTERO al archivo privado y la huella sellada
        // aquí; el binario no se copia ni se reescribe.
        const item = await useQueueStore.getState().enqueueEvidence(
          {
            incident_id: incidentId,
            uri: captured.uri,
            content_type: "image/jpeg",
            bytes: captured.bytes,
            ts_device: meta.tsDevice,
          },
          captured.sha256,
        );
        // El reporte de daños referencia el id LOCAL: el `evidence_id` del
        // servidor no existe todavía y puede tardar horas en existir.
        addEvidence(item.id);
        // Con red se va ya; sin red, el listener de `OfflineSyncGate` lo hace
        // solo al reconectar (§7·2.5: "sin intervención").
        void drainQueue();
        setBusy(false);
        router.back();
      } catch (err) {
        // [T-7.31] El `catch` vacío costó una sesión de demostración: la foto
        // del brigadista no se guardaba y lo único que decía la pantalla —y lo
        // único que quedaba en el registro— era «no se pudo». Sin el motivo no
        // se puede distinguir un teléfono sin espacio de una captura que
        // reventó, y las dos se arreglan de forma distinta.
        setBusy(false);
        const motivo = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
        console.warn("evidencia forense: no se pudo guardar", motivo);
        setCapturaError(`No se pudo guardar la evidencia en este teléfono (${motivo}).`);
      }
    })();
  };

  const sinSitio = siteId === null;

  return (
    <View style={styles.fill}>
      <StateFrame
        empty={sinSitio || (data !== null && incidentId === null)}
        emptyText={sinSitio ? SIN_SITIO : SIN_INCIDENTE}
        error={data === null && error !== null ? SIN_ESTADO : null}
        // El permiso aún sin resolver y el snapshot en vuelo comparten estado:
        // en los dos casos lo único honesto es «todavía no se sabe».
        loading={permission == null || loading}
        onRetry={refetch}
        staleSinceMs={snapshotStaleSinceMs}
      >
        {incidentId !== null && photoUri === null ? (
          <View style={styles.fill}>
            <CameraView ref={cameraRef} style={styles.fill} />
            {/* El aviso de snapshot retenido ya está a la vista ANTES de
                disparar: es el banner del `StateFrame`, que envuelve también al
                visor. La marca de agua no se duplica aquí para que no haya duda
                de cuál es la que se hornea — la del `composeRef`. */}
            <View style={styles.controls}>
              <AvisoIA />
              {capturaError ? <Text style={styles.error}>{capturaError}</Text> : null}
              <Pressable
                accessibilityRole="button"
                disabled={busy}
                onPress={take}
                style={styles.shutter}
                testID="shutter"
              >
                {busy ? (
                  <ActivityIndicator color={palette.bg} />
                ) : (
                  <Text style={styles.shutterText}>CAPTURAR</Text>
                )}
              </Pressable>
              <Pressable
                accessibilityRole="button"
                onPress={() => router.back()}
                style={styles.textBtn}
              >
                <Text style={styles.cancel}>Cancelar</Text>
              </Pressable>
            </View>
          </View>
        ) : null}

        {incidentId !== null && photoUri !== null ? (
          <View style={styles.fill}>
            {/* View COMPUESTO que view-shot captura: la marca queda en el bitmap.
                El `testID` NO es decorativo: es el asidero por el que
                `camera-states.test.tsx` mide QUÉ HAY DENTRO de este árbol —lo
                único que acaba horneado en el JPEG y en el SHA-256—, y la propia
                guarda comprueba antes que el `ref` que se le pasa a
                `captureForensicPhoto` es el de este View y no otro. Moverlo de
                sitio sin mover el `testID` pone la guarda en rojo, que es lo que
                se quiere: sin ancla, medir el árbol equivocado no se nota. */}
            <View collapsable={false} ref={composeRef} style={styles.fill} testID="compose">
              <CameraView style={styles.fill} />
              <View pointerEvents="none" style={styles.watermark} testID="watermark">
                {watermarkLines(meta).map((line) => (
                  <Text key={line} style={styles.watermarkText}>
                    {line}
                  </Text>
                ))}
              </View>
            </View>
            <View style={styles.controls}>
              <AvisoIA />
              {capturaError ? <Text style={styles.error}>{capturaError}</Text> : null}
              <Pressable
                accessibilityRole="button"
                disabled={busy}
                onPress={use}
                style={styles.shutter}
                testID="use-photo"
              >
                {busy ? (
                  <ActivityIndicator color={palette.bg} />
                ) : (
                  <Text style={styles.shutterText}>USAR ESTA FOTO</Text>
                )}
              </Pressable>
              <Pressable
                accessibilityRole="button"
                onPress={() => setPhotoUri(null)}
                style={styles.textBtn}
              >
                <Text style={styles.cancel}>Repetir</Text>
              </Pressable>
            </View>
          </View>
        ) : null}
      </StateFrame>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: palette.bg },
  center: {
    flex: 1,
    backgroundColor: palette.bg,
    alignItems: "center",
    justifyContent: "center",
    gap: space[3],
    padding: space[5],
  },
  hint: { color: palette.fg2, fontSize: fontSize.sm, textAlign: "center" },
  controls: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    padding: space[4],
    gap: space[2],
    alignItems: "center",
    backgroundColor: emergency.veil.soft,
  },
  shutter: {
    minHeight: touch.min,
    justifyContent: "center",
    backgroundColor: palette.cyan,
    borderRadius: radius.pill,
    paddingVertical: space[3],
    paddingHorizontal: space[5],
    alignItems: "center",
  },
  /* [T-6.20] Un texto pulsable es un control: mide lo que mide el mínimo. */
  textBtn: {
    minHeight: touch.min,
    justifyContent: "center",
    paddingHorizontal: space[3],
  },
  shutterText: { color: palette.bg, fontWeight: "800", letterSpacing: 1 },
  avisoIa: {
    alignSelf: "stretch",
    backgroundColor: emergency.veil.base,
    borderLeftColor: palette.warn,
    borderLeftWidth: 3,
    borderRadius: radius.sm,
    padding: space[2],
    gap: 2,
  },
  avisoIaTitulo: {
    color: emergency.veil.ink,
    fontSize: fontSize.xs,
    fontWeight: "800",
    letterSpacing: 1,
  },
  avisoIaTexto: { color: emergency.veil.ink, fontSize: fontSize.xs },
  cancel: { color: palette.fg2, fontSize: fontSize.sm },
  error: { color: palette.crit, fontSize: fontSize.sm },
  btn: {
    minHeight: touch.min,
    justifyContent: "center",
    backgroundColor: palette.cyan,
    borderRadius: radius.md,
    paddingVertical: space[3],
    paddingHorizontal: space[4],
  },
  btnText: { color: palette.bg, fontWeight: "700", letterSpacing: 1 },
  watermark: {
    position: "absolute",
    left: space[3],
    bottom: space[3],
    backgroundColor: emergency.veil.base,
    padding: space[2],
    borderRadius: radius.sm,
    gap: 2,
  },
  watermarkText: { color: emergency.veil.ink, fontSize: fontSize.xs, fontWeight: "600" },
});
