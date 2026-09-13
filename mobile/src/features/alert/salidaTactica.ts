// [T-7.29] El TÁCTICO puede salir de la toma de crisis. El ocupante no.
//
// POR QUÉ EXISTE, medido el 2026-09-12 con el WR-1 real: durante la alerta la
// toma de pantalla es TOTAL y se re-impone en cada render («de una evacuación
// no se sale con el dedo»). Para el ocupante eso es exactamente lo que se
// quiere. Para el brigadista **no**: es la persona que tiene que abrir TRIAGE,
// mirar la lista, llamar al directorio — y durante el acto 3 de la demostración
// su teléfono le enseñaba «PROTÉJASE» y nada más, con las pestañas fuera de
// alcance. La app no estaba atascada: estaba haciendo lo que se le dijo, a la
// persona equivocada.
//
// Tres propiedades que no son detalles:
//
//   1. **Se recuerda por EPISODIO, no para siempre.** La llave es el incidente:
//      una alerta NUEVA vuelve a tomar la pantalla aunque el mismo brigadista
//      hubiera salido de la anterior. Si esto fuera un booleano global, el
//      segundo sismo de la noche no le tomaría la pantalla a nadie.
//   2. **Vive en memoria.** Al reabrir la app la toma se re-impone. Es la
//      degradación segura: olvidar que salió cuesta un toque; recordarlo de más
//      cuesta que alguien no vea la instrucción.
//   3. **Salir NO silencia la alerta, solo esta pantalla.** El incidente sigue
//      abierto y la franja de aviso lo declara en todas las pestañas: quien sale
//      tiene que seguir viendo que hay una alerta viva (regla de oro 7).

let episodioAbandonado: string | null = null;

/** Registra que este táctico salió de la toma de ESTE incidente. */
export function marcarSalidaTactica(
  incidentId: string | null | undefined,
): void {
  if (!incidentId) {
    return;
  }
  episodioAbandonado = incidentId;
}

/** ¿Salió ya de la toma de este incidente? Sin incidente, nunca. */
export function salioDeLaCrisis(
  incidentId: string | null | undefined,
): boolean {
  return Boolean(incidentId) && episodioAbandonado === incidentId;
}

/** Vuelve a imponer la toma (cierre de sesión, y las pruebas). */
export function reiniciarSalidaTactica(): void {
  episodioAbandonado = null;
}
