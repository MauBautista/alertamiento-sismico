// 1.6 · Rutas de evacuación — el táctico ve EXACTAMENTE la misma pantalla que
// el ocupante, y por eso es el MISMO módulo y no una copia.
//
// [T-6.22] `RBAC-TAKAB.md §3` concede «Directorio emergencia / rutas
// evacuación» a los CINCO roles móviles, y hasta aquí sólo la tenía el
// ocupante: el brigadista que llega a un edificio ajeno no podía abrir su ruta
// de evacuación. Reexportar —en vez de extraer a `@/features/…`— mantiene el
// dato de servidor DENTRO de la ruta del ocupante, que es donde
// `screenStateCensus` lo vigila y donde `rutas-states.test.tsx` prueba sus
// cuatro estados. Una copia tendría que probarse aparte; esto es el mismo
// código, y el test de abajo lo afirma.
export { default } from "../(occupant)/rutas";
