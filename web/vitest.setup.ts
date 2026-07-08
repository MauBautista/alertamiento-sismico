import "@testing-library/jest-dom";

import { transferableAbortController } from "node:util";

// react-router v7 (data router) construye `new Request(url, { signal })` en cada
// navegación. En jsdom, AbortController es el de jsdom pero Request es el de
// undici (Node): su brand check rechaza la señal ajena. Se alinean los globals
// con los nativos de Node (recuperados vía node:util, que no está parcheado).
const nodeController = transferableAbortController();
globalThis.AbortController = nodeController.constructor as typeof AbortController;
globalThis.AbortSignal = nodeController.signal.constructor as typeof AbortSignal;
