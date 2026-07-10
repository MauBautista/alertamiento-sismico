import "@testing-library/jest-dom";

import { transferableAbortController } from "node:util";

// react-router v7 (data router) construye `new Request(url, { signal })` en cada
// navegación. En jsdom, AbortController es el de jsdom pero Request es el de
// undici (Node): su brand check rechaza la señal ajena. Se alinean los globals
// con los nativos de Node (recuperados vía node:util, que no está parcheado).
const nodeController = transferableAbortController();
globalThis.AbortController = nodeController.constructor as typeof AbortController;
globalThis.AbortSignal = nodeController.signal.constructor as typeof AbortSignal;

// maplibre-gl (T-1.27) registra su worker con URL.createObjectURL AL IMPORTARSE;
// jsdom no lo implementa. Stub inerte: los tests del mapa mockean maplibre-gl,
// pero cualquier import transitivo (routes → ConsolePage) no debe reventar.
if (typeof window.URL.createObjectURL === "undefined") {
  Object.defineProperty(window.URL, "createObjectURL", {
    value: () => "blob:vitest-stub",
    writable: true,
  });
}

// jsdom tampoco trae ResizeObserver (T-1.50: observeMapResize de mapa/picker).
// Stub con registro global para que los tests disparen resizes a demanda.
type ResizeCallback = (entries: unknown[], observer: unknown) => void;
const resizeObservers = new Set<ResizeCallback>();
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    private readonly cb: ResizeCallback;
    constructor(cb: ResizeCallback) {
      this.cb = cb;
      resizeObservers.add(cb);
    }
    observe() {}
    unobserve() {}
    disconnect() {
      resizeObservers.delete(this.cb);
    }
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
  (globalThis as Record<string, unknown>).__triggerResizeObservers = () => {
    for (const cb of resizeObservers) {
      cb([], undefined);
    }
  };
}
