// Punto de entrada de @takab/sdk: cliente REST generado (src/gen) + canal WS.
// `client` no sale por ./gen/index (generado): se re-exporta aquí para que la
// app configure baseUrl/interceptores (auth) sobre la instancia única.
export * from './gen';
export { client } from './gen/client.gen';
export * from './ws';
// [T-2.08] Canal live compartido (web + móvil) y agrupación BMS de consola.
export * from './live';
export * from './bms';
