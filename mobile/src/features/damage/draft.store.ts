// Borrador del reporte de daños (2.4): las evidencias capturadas en la cámara
// (2.3) se acumulan aquí para ligarlas al POST del formulario. Estado efímero
// por reporte — se limpia al enviar o al descartar.
import { create } from "zustand";

type DraftState = {
  evidenceIds: string[];
  addEvidence: (id: string) => void;
  reset: () => void;
};

export const useDamageDraft = create<DraftState>()((set) => ({
  evidenceIds: [],
  addEvidence: (id) => set((s) => ({ evidenceIds: [...s.evidenceIds, id] })),
  reset: () => set({ evidenceIds: [] }),
}));
