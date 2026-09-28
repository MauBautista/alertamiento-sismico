// UBICACIÓN: fuera de `src/app/` a propósito (ver `crisis-states.test.tsx`).
//
// [T-9.80 · D-48] CUENTA → CONTACTOS DE EMERGENCIA: nació con su prueba de cuatro
// estados. El VACÍO lo pinta la vista (una lista vacía se edita: AGREGAR sigue a
// mano), así que aquí se mide además que el vacío NO se coma el formulario.
import type { ContactosOut } from "@takab/sdk";
import { act, fireEvent, render } from "@testing-library/react-native";

import { expectFourStates } from "@/test-utils/expectFourStates";

import ContactosEmergencia from "@/app/contactos-emergencia";

jest.mock("expo-router", () => ({ useRouter: () => ({ back: jest.fn(), push: jest.fn() }) }));

const AHORA = Date.now();
const AVISO = { version: "2026-09-v1", texto: "Aviso.", provisional: true };

function datos(n: number): ContactosOut {
  return {
    aviso: AVISO,
    contactos: Array.from({ length: n }, (_, k) => ({
      consent_version: AVISO.version,
      consented_at: "2026-09-27T10:00:00Z",
      display_name: `C${k + 1}`,
      email: `c${k + 1}@example.com`,
      phone: null,
      posicion: k + 1,
    })),
  };
}

type Lectura = {
  data: ContactosOut | null;
  loading: boolean;
  error: string | null;
  staleSinceMs: number | null;
  refetch: jest.Mock;
  guardar: jest.Mock;
  borrarTodos: jest.Mock;
};
let mockLectura: Lectura;
jest.mock("@/features/emergencyContacts/useEmergencyContacts", () => ({
  ...jest.requireActual("@/features/emergencyContacts/useEmergencyContacts"),
  useEmergencyContacts: () => mockLectura,
}));

function lectura(over: Partial<Lectura> = {}): Lectura {
  return {
    data: null,
    loading: false,
    error: null,
    staleSinceMs: null,
    refetch: jest.fn(),
    guardar: jest.fn(),
    borrarTodos: jest.fn(),
    ...over,
  };
}

beforeEach(() => {
  mockLectura = lectura({ data: datos(1) });
});

async function asentar(): Promise<void> {
  await act(async () => {});
}

describe("CONTACTOS DE EMERGENCIA · qué lee la persona cuando algo falta", () => {
  it("sin contactos: el vacío y, debajo, AGREGAR y el aviso", async () => {
    mockLectura = lectura({ data: datos(0) });
    const v = await render(<ContactosEmergencia />);
    await asentar();
    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.getByTestId("contactos-agregar")).toBeTruthy();
    expect(v.getByTestId("aviso-texto")).toBeTruthy();
  });

  it("el error ofrece REINTENTAR y reintentar RE-CONSULTA", async () => {
    mockLectura = lectura({ error: "No se pudieron consultar sus contactos de emergencia." });
    const v = await render(<ContactosEmergencia />);
    await asentar();
    await act(async () => {
      fireEvent.press(v.getByTestId("state-retry"));
    });
    expect(mockLectura.refetch).toHaveBeenCalledTimes(1);
  });
});

describe("CONTACTOS DE EMERGENCIA · contrato de 4 estados (regla de oro 7)", () => {
  it("materializa los cuatro", async () => {
    await expectFourStates(
      (e) => {
        mockLectura = lectura({
          loading: e === "loading",
          error: e === "error" ? "No se pudieron consultar sus contactos de emergencia." : null,
          data: e === "empty" ? datos(0) : e === "stale" ? datos(2) : null,
          staleSinceMs: e === "stale" ? AHORA - 20 * 60_000 : null,
        });
        return <ContactosEmergencia />;
      },
      { asentar },
    );
  });
});
