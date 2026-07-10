// Re-export de compatibilidad (T-1.49): el canal live vive en src/live —
// AppShell posee el socket y las páginas lo consumen. Los hooks de la consola
// (useLiveIncidents, useMapState, useSiteSoh, useIncidentActions,
// useSiteFeatures), BuildingPage y test-utils siguen importando de aquí sin
// cambios.

export { LiveSocketContext, useLiveSocket, type LiveSocketLike } from "../../live/socket";
