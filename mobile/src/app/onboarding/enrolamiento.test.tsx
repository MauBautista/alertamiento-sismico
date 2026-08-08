// La salida del enrolamiento tiene que decir LO QUE HACE, no afirmar algo del
// usuario que el sistema no puede saber.
//
// [T-2.79.c] La puerta existía —un botón que llama a `finish()` sin canjear el
// código— pero se rotulaba «Ya estoy vinculado · continuar», con estilo de
// opción descartable y justo debajo de «Sin conexión con el servidor». O sea:
// a la persona que la nube dejó tirada se le ofrecía una salida cuyo texto
// AFIRMA UNA FALSEDAD SOBRE ELLA. Quien lee que no está vinculado no la pulsa,
// se queda en el paso 3 de 3 y no llega al check-in de vida ni al botón de
// pánico (reglas de oro 1 y 2).
//
// El equilibrio que estos tests fijan: el caso normal —con código y con red—
// sigue llevando a VINCULAR; lo que cambia es qué se ofrece CUANDO YA FALLÓ, y
// que quien sale sepa qué pierde.
import { enrollMeEnrollmentPost } from "@takab/sdk";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { setWatchedSite } from "@/services/mySite";
import { markOnboardingDone } from "@/services/onboarding";

import Enrolamiento from "./enrolamiento";

jest.mock("@takab/sdk", () => ({
  enrollMeEnrollmentPost: jest.fn(),
}));

jest.mock("expo-router", () => ({
  useRouter: () => mockRouter,
}));

jest.mock("@/services/mySite", () => ({
  setWatchedSite: jest.fn(async () => undefined),
}));

jest.mock("@/services/onboarding", () => ({
  markOnboardingDone: jest.fn(async () => undefined),
}));

const mockRouter = { push: jest.fn(), replace: jest.fn() };

const enrolar = enrollMeEnrollmentPost as jest.Mock;

beforeEach(() => {
  enrolar.mockReset();
  mockRouter.push.mockReset();
  mockRouter.replace.mockReset();
  (markOnboardingDone as jest.Mock).mockClear();
  (setWatchedSite as jest.Mock).mockClear();
});

/** Escribe un código y pulsa VINCULAR: el camino que la gente recorre de verdad. */
async function intentarVincular(v: ReturnType<typeof render> extends Promise<infer R> ? R : never) {
  // El `await` no es adorno: sin él el estado del código aún no ha entrado y el
  // botón sigue deshabilitado, así que el press se traga en silencio.
  await fireEvent.changeText(v.getByPlaceholderText("CÓDIGO-DE-SITIO"), "TAKAB-0001");
  await fireEvent.press(v.getByTestId("enrolamiento-vincular"));
}

describe("enrolamiento — con la nube caída hay salida, y está bien rotulada", () => {
  it("la RED caída: la salida existe, es visible y NO dice que ya esté vinculado", async () => {
    enrolar.mockRejectedValue(new TypeError("Network request failed"));

    const v = await render(<Enrolamiento />);
    await intentarVincular(v);

    // Existe un camino visible al final del onboarding...
    const salida = await waitFor(() => v.getByTestId("enrolamiento-continuar-sin-vincular"));
    expect(salida).toBeTruthy();
    // ...y se destaca precisamente porque el fallo NO es culpa del usuario.
    expect(v.getByTestId("enrolamiento-salida-destacada")).toBeTruthy();
    // ...y su texto no afirma nada sobre la persona.
    expect(v.queryByText(/ya estoy vinculado/i)).toBeNull();
    expect(v.getByText(/continuar sin vincular/i)).toBeTruthy();
  });

  it("el 503 del servidor NO se disfraza de «código inválido»", async () => {
    // Culpar al código de un fallo del servidor manda a la persona a pedir un
    // código nuevo que no arregla nada.
    enrolar.mockResolvedValue({ error: { detail: "upstream" }, response: { status: 503 } });

    const v = await render(<Enrolamiento />);
    await intentarVincular(v);

    await waitFor(() => expect(v.getByTestId("enrolamiento-salida-destacada")).toBeTruthy());
    expect(v.queryByText(/código inválido/i)).toBeNull();
  });

  it("pulsar la salida termina el onboarding de verdad (check-in y pánico al otro lado)", async () => {
    enrolar.mockRejectedValue(new TypeError("Network request failed"));

    const v = await render(<Enrolamiento />);
    await intentarVincular(v);

    await waitFor(() => expect(v.getByTestId("enrolamiento-salida-destacada")).toBeTruthy());
    await fireEvent.press(v.getByTestId("enrolamiento-continuar-sin-vincular"));

    // Sin `markOnboardingDone`, `app/index.tsx:54` vuelve a mandar al
    // onboarding para siempre: el cerrojo se vería aquí.
    await waitFor(() => expect(markOnboardingDone).toHaveBeenCalled());
    expect(mockRouter.replace).toHaveBeenCalledWith("/");
  });

  it("queda ESCRITO qué pierde quien continúa sin vincular", async () => {
    // Continuar a ciegas también es una forma de mentir: sin sitio vigilado no
    // hay check-in por zona, y hay que decir dónde se arregla (Cuenta).
    enrolar.mockRejectedValue(new TypeError("Network request failed"));

    const v = await render(<Enrolamiento />);
    await intentarVincular(v);

    const costo = await waitFor(() => v.getByTestId("enrolamiento-salida-costo"));
    expect(costo).toBeTruthy();
    expect(v.getByText(/check-in/i)).toBeTruthy();
    expect(v.getByText(/cuenta/i)).toBeTruthy();
  });

  it("en ninguna pantalla del enrolamiento se afirma «Ya estoy vinculado»", async () => {
    const v = await render(<Enrolamiento />);

    expect(v.queryByText(/ya estoy vinculado/i)).toBeNull();
  });
});

describe("enrolamiento — la salida no puede convertirse en un atajo", () => {
  it("sin fallo, VINCULAR es lo que se ofrece y la salida no se destaca", async () => {
    const v = await render(<Enrolamiento />);

    expect(v.getByTestId("enrolamiento-vincular")).toBeTruthy();
    expect(v.getByText("VINCULAR")).toBeTruthy();
    expect(v.queryByTestId("enrolamiento-salida-destacada")).toBeNull();
  });

  it("un código inválido (404) NO destaca la salida: ahí la respuesta es pedir otro código", async () => {
    enrolar.mockResolvedValue({ error: { detail: "not found" }, response: { status: 404 } });

    const v = await render(<Enrolamiento />);
    await intentarVincular(v);

    await waitFor(() => expect(v.getByText(/código inválido/i)).toBeTruthy());
    expect(v.queryByTestId("enrolamiento-salida-destacada")).toBeNull();
  });

  it("con red y código bueno, el camino normal sigue llevando a vincular", async () => {
    enrolar.mockResolvedValue({
      data: { site_id: "s1", site_name: "Torre A", zone_name: "Z3", evac_policy: "evacuate" },
      response: { status: 201 },
    });

    const v = await render(<Enrolamiento />);
    await intentarVincular(v);

    await waitFor(() => expect(setWatchedSite).toHaveBeenCalledWith("s1"));
    expect(v.getByText(/Vinculado a Torre A/)).toBeTruthy();
    expect(v.getByText("TERMINAR")).toBeTruthy();
  });
});
