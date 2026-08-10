// Borrador del reporte de daños (2.4): las evidencias capturadas en la cámara
// (2.3) se acumulan aquí para ligarlas al reporte. Estado efímero por reporte
// — se limpia al enviar o al descartar.
//
// [T-2.108] Lo que se acumula son ids LOCALES de la cola offline, NO los
// `evidence_id` del servidor: en modo avión esos todavía no existen (los
// inventa el backend al registrar la foto). El motor de la cola los traduce al
// despachar el reporte, cuando sus fotos ya aterrizaron.
import { create } from "zustand";

type DraftState = {
  /** Ids de items `evidence` de la cola offline, en orden de captura. */
  evidenceIds: string[];
  addEvidence: (id: string) => void;
  reset: () => void;
};

export const useDamageDraft = create<DraftState>()((set) => ({
  evidenceIds: [],
  addEvidence: (id) => set((s) => ({ evidenceIds: [...s.evidenceIds, id] })),
  reset: () => set({ evidenceIds: [] }),
}));
