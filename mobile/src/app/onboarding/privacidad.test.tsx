// La pantalla de privacidad NO puede encerrar a nadie en el onboarding.
//
// Este fichero existe porque `privacidad.tsx` prometía en su cabecera y en su
// pie ("NUNCA BLOQUEA EL CHECK-IN DE VIDA NI LA PETICIÓN DE AYUDA") algo que el
// código no cumplía, y no había NI UN test que renderizara la pantalla para
// desmentirlo. El escenario que cierra el agujero es el primero: la nube sirve
// el aviso pero rechaza la escritura (503) y el ocupante tiene que salir igual
// del onboarding — al otro lado están el check-in de vida y el botón de pánico
// (reglas de oro 1 y 2: proteger no depende de que la nube esté sana).
//
// Se moquea SOLO la frontera HTTP (`client` del SDK): la pantalla y
// `services/privacy` corren de verdad, que es donde vivía el fallo.
import { client } from "@takab/sdk";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { markOnboardingDone, setGpsConsent } from "@/services/onboarding";

import Privacidad from "./privacidad";

jest.mock("@takab/sdk", () => ({
  client: { get: jest.fn(), post: jest.fn() },
}));

jest.mock("expo-router", () => ({
  useRouter: () => mockRouter,
}));

jest.mock("@/auth/session.store", () => ({
  useSessionStore: (sel: (s: { profile: string }) => unknown) => sel({ profile: mockPerfil }),
}));

jest.mock("@/services/onboarding", () => ({
  getGpsConsent: jest.fn(async () => false),
  setGpsConsent: jest.fn(async () => undefined),
  markOnboardingDone: jest.fn(async () => undefined),
}));

const mockRouter = { push: jest.fn(), replace: jest.fn() };
let mockPerfil = "brigadista";

const get = client.get as jest.Mock;
const post = client.post as jest.Mock;

const NOTICE = {
  purpose: "app_mobile",
  locale: "es-MX",
  version: "1.0.0",
  title: "Aviso de privacidad",
  body: "cuerpo",
  paragraphs: ["Sus datos se usan para alertarle."],
  digest: "a".repeat(64),
  source: "tenant" as const,
  provisional: false,
  provisional_reason: "",
};

/** El servidor sí contesta el aviso: `missing` = falta consentir. */
function sirveElAviso(): void {
  get.mockResolvedValue({
    data: { notice: NOTICE, state: "missing", consent: null, blocks_emergency_actions: false },
    response: { status: 200 },
  });
}

async function montar() {
  const v = await render(<Privacidad />);
  // El aviso se pide en un efecto: sin esperar, se asertaría sobre el spinner.
  await waitFor(() => expect(v.queryByTestId("state-loading")).toBeNull());
  return v;
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  mockRouter.push.mockReset();
  mockRouter.replace.mockReset();
  (markOnboardingDone as jest.Mock).mockClear();
  (setGpsConsent as jest.Mock).mockClear();
  mockPerfil = "brigadista";
});

describe("privacidad — el consentimiento JAMÁS encierra en el onboarding", () => {
  it("503 al REGISTRAR la decisión: el ocupante llega igual al enrolamiento", async () => {
    // La nube medio caída —sirve el aviso, rechaza la escritura— era la trampa:
    // el registro fallaba, la pantalla hacía `return` y el ocupante se quedaba
    // sin check-in de vida ni botón de pánico. Reintentar no ayudaba: el estado
    // seguía `missing` y se repetía el mismo `return`.
    mockPerfil = "occupant";
    sirveElAviso();
    post.mockResolvedValue({ error: { detail: "upstream" }, response: { status: 503 } });

    const v = await montar();
    await fireEvent.press(v.getByTestId("privacy-accept"));

    await waitFor(() =>
      expect(mockRouter.push).toHaveBeenCalledWith("/onboarding/enrolamiento"),
    );
  });

  it("503 al REGISTRAR: el táctico termina el onboarding (queda marcado como hecho)", async () => {
    // Sin `markOnboardingDone`, `app/index.tsx` vuelve a redirigir a
    // /onboarding/permisos para siempre: el encierro se ve aquí.
    sirveElAviso();
    post.mockResolvedValue({ error: { detail: "upstream" }, response: { status: 503 } });

    const v = await montar();
    await fireEvent.press(v.getByTestId("privacy-accept"));

    await waitFor(() => expect(markOnboardingDone).toHaveBeenCalled());
    expect(mockRouter.replace).toHaveBeenCalledWith("/");
  });

  it("la RED caída al registrar (el cliente lanza) tampoco encierra", async () => {
    // Cuando `fetch` rechaza, el cliente del SDK sí lanza. Es el otro modo de
    // fallo del mismo botón y tiene que desembocar en lo mismo: pasar.
    sirveElAviso();
    post.mockRejectedValue(new TypeError("Network request failed"));

    const v = await montar();
    await fireEvent.press(v.getByTestId("privacy-accept"));

    await waitFor(() => expect(markOnboardingDone).toHaveBeenCalled());
  });

  it("409 (el aviso cambió bajo el lector): tampoco encierra", async () => {
    // No se registró nada sobre el texto leído —y así queda en el servidor, que
    // seguirá diciendo `missing`/`stale` y volverá a pedirlo desde Cuenta—, pero
    // la persona YA decidió: retenerla aquí no arregla el consentimiento y sí la
    // deja fuera de la app de emergencias.
    sirveElAviso();
    post.mockResolvedValue({ error: { detail: "cambió" }, response: { status: 409 } });

    const v = await montar();
    await fireEvent.press(v.getByTestId("privacy-accept"));

    await waitFor(() => expect(markOnboardingDone).toHaveBeenCalled());
  });

  it("403 al registrar: tampoco encierra", async () => {
    sirveElAviso();
    post.mockResolvedValue({ error: { detail: "forbidden" }, response: { status: 403 } });

    const v = await montar();
    await fireEvent.press(v.getByTestId("privacy-accept"));

    await waitFor(() => expect(markOnboardingDone).toHaveBeenCalled());
  });

  it("201: el camino feliz registra y avanza", async () => {
    sirveElAviso();
    post.mockResolvedValue({ data: { consent_id: "c1" }, response: { status: 201 } });

    const v = await montar();
    await fireEvent.press(v.getByTestId("privacy-accept"));

    await waitFor(() => expect(markOnboardingDone).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith({
      url: "/privacy/consent",
      body: { decision: "accept", digest: NOTICE.digest, via: "mobile" },
    });
  });

  it("el ÚNICO desenlace que retiene es no haber decidido: sin pulsar, no navega", async () => {
    sirveElAviso();
    post.mockResolvedValue({ data: {}, response: { status: 201 } });

    await montar();

    expect(post).not.toHaveBeenCalled();
    expect(mockRouter.push).not.toHaveBeenCalled();
    expect(mockRouter.replace).not.toHaveBeenCalled();
    expect(markOnboardingDone).not.toHaveBeenCalled();
  });

  it("el aviso ya aceptado (`current`) no vuelve a registrarse, y pasa", async () => {
    get.mockResolvedValue({
      data: {
        notice: NOTICE,
        state: "current",
        consent: {
          notice_digest: NOTICE.digest,
          notice_version: "1.0.0",
          decided_at: "2026-08-01T00:00:00Z",
        },
        blocks_emergency_actions: false,
      },
      response: { status: 200 },
    });

    const v = await montar();
    await fireEvent.press(v.getByTestId("privacy-accept"));

    await waitFor(() => expect(markOnboardingDone).toHaveBeenCalled());
    expect(post).not.toHaveBeenCalled();
  });
});

describe("privacidad — 'no se pudo preguntar' no se pinta como 'no hay aviso'", () => {
  it("503 al PEDIR el aviso: error honesto, JAMÁS el vacío 'no tiene aviso publicado'", async () => {
    // Afirmar una ausencia sin haberla comprobado es el fallo de la regla de
    // oro 7: peor que no mostrar nada.
    get.mockResolvedValue({ error: { detail: "upstream" }, response: { status: 503 } });

    const v = await montar();

    expect(v.getByTestId("state-error")).toBeTruthy();
    expect(v.queryByTestId("state-empty")).toBeNull();
    expect(v.queryByText(/NO TIENE AVISO PUBLICADO/i)).toBeNull();
  });

  it("200 sin aviso publicado: ESE sí es el vacío honesto", async () => {
    get.mockResolvedValue({
      data: { notice: null, state: "missing", consent: null, blocks_emergency_actions: false },
      response: { status: 200 },
    });

    const v = await montar();

    expect(v.getByTestId("state-empty")).toBeTruthy();
    expect(v.queryByTestId("state-error")).toBeNull();
  });

  it("con el aviso incomprobable, el botón SIGUE dejando pasar", async () => {
    // El error se pinta, pero no se convierte en un cerrojo: no hay digest que
    // registrar, así que se pasa sin inventarse un consentimiento.
    get.mockResolvedValue({ error: { detail: "upstream" }, response: { status: 503 } });

    const v = await montar();
    await fireEvent.press(v.getByTestId("privacy-accept"));

    await waitFor(() => expect(markOnboardingDone).toHaveBeenCalled());
    expect(post).not.toHaveBeenCalled();
  });
});
