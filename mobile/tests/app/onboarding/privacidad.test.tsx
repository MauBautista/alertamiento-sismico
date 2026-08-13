// UBICACIÓN: este test vive FUERA de `src/app/` a propósito, y no es estilo.
// `expo-router` construye su tabla de rutas con un `require.context` sobre
// `src/app`, que barre TODOS los ficheros de ahí — los `*.test.tsx` incluidos.
// Con este archivo dentro, el bundle arrastraba `@testing-library/react-native`
// → `console` de Node, que no existe en el runtime de React Native, y la app
// NO ARRANCABA. Estuvo así desde el 2026-08-08 sin que nadie lo viera: la suite
// de móvil corre jest, tsc y eslint, y ninguno construye un bundle.
// Lo vigila ahora el gate `expo export` del job `mobile` en CI.
//
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

import Privacidad from "@/app/onboarding/privacidad";

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

// [T-2.79.f] El título SERVIDO no puede ser «Aviso de privacidad» a secas: es
// palabra por palabra el encabezado que la pantalla lleva escrito a mano, así
// que un test que lo buscara no distinguiría el texto de la organización del
// rótulo del repositorio de la app — que es EXACTAMENTE el agujero que T-2.79
// cerró. Con un título propio del tenant, encontrarlo prueba que llegó el
// servido.
const NOTICE = {
  purpose: "app_mobile",
  locale: "es-MX",
  version: "1.0.0",
  title: "Aviso de privacidad integral · Hospital Metropolitano",
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

/** El aviso CAMBIÓ desde que esta persona lo aceptó: `stale`, con su consentimiento viejo. */
function sirveUnAvisoQueCambio(): void {
  get.mockResolvedValue({
    data: {
      notice: { ...NOTICE, version: "2.0.0", digest: "b".repeat(64) },
      state: "stale",
      consent: {
        notice_digest: NOTICE.digest,
        notice_version: "1.0.0",
        decided_at: "2026-08-01T00:00:00Z",
      },
      blocks_emergency_actions: false,
    },
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

/* =====================================================================
   T-2.79.f · LO QUE LA PERSONA LEE ANTES DE DECIDIR
   =====================================================================

   Todo lo de arriba prueba que el botón no encierra a nadie. Ninguna de esas
   once pruebas mira el AVISO: medido el 2026-08-13 dejando la tarjeta
   `privacy-notice` con el título y nada más —sin párrafos, sin versión, sin
   sello y sin el texto de «este aviso cambió»— la suite entera seguía en
   **11/11 verde**. Es decir: la pantalla podía dejar de enseñar el aviso
   entero y nadie se enteraba.

   El criterio 2 de T-2.79 («cambiar el aviso no reescribe consentimientos»)
   está probado en el motor, que es donde importa para la INTEGRIDAD DEL
   REGISTRO. Lo que no estaba probado es que la pantalla se lo CUENTE a quien
   tiene que decidir. Un consentimiento que la persona da sin ver lo que acepta
   no es consentimiento — y el registro sería impecable y vacío a la vez.

   Por eso estas pruebas assertan TEXTO VISIBLE y no la presencia del `testID`:
   `privacy-notice` puede seguir montándose con la tarjeta hueca, que es
   exactamente el estado en que se midió el hueco.
   ===================================================================== */

describe("privacidad · el aviso SERVIDO se pinta, con su versión y su sello", () => {
  it("el cuerpo servido se lee entero — no un resumen del repositorio de la app", async () => {
    // El agujero original de T-2.79 era que la pantalla llevaba cuatro viñetas
    // ESCRITAS A MANO aquí. Si el cuerpo servido dejara de pintarse, la persona
    // volvería a aceptar un texto que no es el que se sella.
    sirveElAviso();

    const v = await montar();

    expect(v.getByTestId("privacy-notice")).toBeTruthy();
    // El título del TENANT, no el encabezado de la pantalla (ver `NOTICE`).
    expect(v.getByText(NOTICE.title)).toBeTruthy();
    for (const parrafo of NOTICE.paragraphs) {
      expect(v.getByText(parrafo)).toBeTruthy();
    }
  });

  it("pinta TODOS los párrafos servidos, no sólo el primero", async () => {
    // Un `paragraphs[0]` en vez de un `.map` enseñaría un aviso truncado y
    // sellaría el completo: la persona firmaría lo que no leyó. Se prueba con
    // tres para que un corte silencioso tenga dónde verse.
    const largo = ["Primero: para qué usamos sus datos.", "Segundo: con quién.", "Tercero: ARCO."];
    get.mockResolvedValue({
      data: {
        notice: { ...NOTICE, paragraphs: largo },
        state: "missing",
        consent: null,
        blocks_emergency_actions: false,
      },
      response: { status: 200 },
    });

    const v = await montar();

    for (const parrafo of largo) {
      expect(v.getByText(parrafo)).toBeTruthy();
    }
  });

  it("la versión y el origen del texto están A LA VISTA, no sólo en el POST", async () => {
    // `v1.0.0 · de su organización`. Sin esto, dos avisos distintos se leen
    // idénticos en pantalla y la persona no puede saber cuál está aceptando.
    sirveElAviso();

    const v = await montar();

    expect(v.getByText(/v1\.0\.0/)).toBeTruthy();
    expect(v.getByText(/de su organización/)).toBeTruthy();
  });

  it("el sello del texto se enseña, y es el MISMO digest que se registra", async () => {
    // Es la bisagra entera de T-2.79: lo que se registra es el digest que
    // estaba EN PANTALLA. Enseñar un sello distinto del que se manda sería
    // peor que no enseñar ninguno, así que se comprueban los dos contra el
    // mismo valor y en la misma prueba.
    sirveElAviso();
    post.mockResolvedValue({ data: { consent_id: "c1" }, response: { status: 201 } });

    const v = await montar();

    expect(v.getByText(`Sello del texto: ${NOTICE.digest.slice(0, 16)}…`)).toBeTruthy();

    await fireEvent.press(v.getByTestId("privacy-accept"));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][0].body.digest).toBe(NOTICE.digest);
  });

  it("un texto PROVISIONAL lo dice en pantalla", async () => {
    // Sin este rótulo la persona no puede saber que está aceptando un borrador
    // sin revisión jurídica, y el aviso se lee como definitivo.
    get.mockResolvedValue({
      data: {
        notice: { ...NOTICE, provisional: true, provisional_reason: "sin revisión jurídica" },
        state: "missing",
        consent: null,
        blocks_emergency_actions: false,
      },
      response: { status: 200 },
    });

    const v = await montar();

    expect(v.getByText(/TEXTO PROVISIONAL/)).toBeTruthy();
  });

  it("aviso de la PLATAFORMA: el origen se dice distinto, no se calla", async () => {
    get.mockResolvedValue({
      data: {
        notice: { ...NOTICE, source: "platform" },
        state: "missing",
        consent: null,
        blocks_emergency_actions: false,
      },
      response: { status: 200 },
    });

    const v = await montar();

    expect(v.getByText(/de la plataforma/)).toBeTruthy();
    expect(v.queryByText(/de su organización/)).toBeNull();
  });
});

describe("privacidad · «este aviso cambió» — el estado que pide decidir OTRA VEZ", () => {
  it("`stale`: se dice que el aviso cambió Y que el consentimiento anterior se conserva", async () => {
    // Las DOS mitades importan y son de la misma frase. «Cambió» sin «lo suyo
    // se conserva» hace pensar que aceptar de nuevo reescribe lo ya dado —que
    // es justo lo que el motor de T-2.79 GARANTIZA que no pasa (append-only)—,
    // y callar el cambio deja a alguien re-aceptando sin saber que el texto es
    // otro. La integridad del registro ya está probada en el motor; esto es lo
    // único que se lo cuenta a quien tiene que decidir.
    sirveUnAvisoQueCambio();

    const v = await montar();

    const cambio = v.getByTestId("privacy-changed");
    expect(cambio).toHaveTextContent(/Este aviso cambió desde que usted lo aceptó/);
    expect(cambio).toHaveTextContent(/Su consentimiento anterior se conserva tal como lo dio/);
  });

  it("`stale`: se lee el texto NUEVO y el sello NUEVO, no los que ya había aceptado", async () => {
    // El fallo silencioso a cazar: pintar el aviso viejo (el del `consent`) con
    // la advertencia de que cambió. La persona leería el texto que ya conocía y
    // aceptaría otro distinto.
    sirveUnAvisoQueCambio();

    const v = await montar();

    expect(v.getByText(/v2\.0\.0/)).toBeTruthy();
    expect(v.getByText(`Sello del texto: ${"b".repeat(16)}…`)).toBeTruthy();
    expect(v.queryByText(/v1\.0\.0/)).toBeNull();
  });

  it("`stale`: el botón vuelve a PEDIR la decisión y registra el digest NUEVO", async () => {
    // `stale` es el estado en que alguien que YA consintió tiene que decidir de
    // nuevo. Si el botón dijera «CONTINUAR» y no mandara nada, el aviso nuevo
    // se quedaría sin consentimiento y nadie lo vería.
    sirveUnAvisoQueCambio();
    post.mockResolvedValue({ data: { consent_id: "c2" }, response: { status: 201 } });

    const v = await montar();

    expect(v.getByTestId("privacy-accept")).toHaveTextContent("ACEPTAR Y CONTINUAR");

    await fireEvent.press(v.getByTestId("privacy-accept"));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][0].body.digest).toBe("b".repeat(64));
  });

  it("`current`: NO se dice que cambió — sería una alarma falsa sobre un texto vigente", async () => {
    // El recíproco, que es lo que impide «arreglar» esto pintando el aviso
    // siempre. Aquí el botón dice CONTINUAR porque no hay nada que decidir.
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

    expect(v.queryByTestId("privacy-changed")).toBeNull();
    expect(v.getByTestId("privacy-notice")).toBeTruthy();
    // Anclado: `toHaveTextContent("CONTINUAR")` a secas también casa con
    // «ACEPTAR Y CONTINUAR», así que pasaría aunque la pantalla siguiera
    // pidiendo una decisión que ya está dada.
    expect(v.getByTestId("privacy-accept")).toHaveTextContent(/^CONTINUAR$/);
  });

  it("sin aviso publicado no hay tarjeta que leer, y se dice — nunca una tarjeta vacía", async () => {
    // Cierra el recíproco del criterio 1: `privacy-notice` no se monta hueco.
    get.mockResolvedValue({
      data: { notice: null, state: "missing", consent: null, blocks_emergency_actions: false },
      response: { status: 200 },
    });

    const v = await montar();

    expect(v.queryByTestId("privacy-notice")).toBeNull();
    expect(v.getByText(/NO TIENE AVISO PUBLICADO/)).toBeTruthy();
  });
});
