// [T-2.75.a] El rótulo de un canal no puede ser una CREENCIA de la consola.
//
// «SIMULADO en el MVP» estaba escrito a fuego en `META`. Hoy es verdad; el día
// que T-2.76.a/T-2.77.a carguen credenciales el canal será real y el rótulo
// seguirá diciendo que no sirve — la regla de oro 7 al revés, y con la peor
// consecuencia posible: un operador que necesita avisar por SMS lee que ese
// canal no entrega y busca otra vía en mitad de un sismo.
//
// LA COSTURA: los escenarios de este test NO se escriben aquí. Salen de
// `shared/fixtures/notify-channels.json`, y `api/tests/api/test_notify_channels.py`
// comprueba que ese fichero es EXACTAMENTE lo que devuelve `GET /notify/channels`
// construyendo la app con dos configuraciones reales. Por eso esto no es un mock
// complaciente: si el registro de providers dejara de decir lo que dice el
// fichero, la suite de la API se pondría roja y el fichero tendría que moverse —
// y al moverse, cambia lo que este test ve pintado. Cadena completa:
// `build_providers()` → endpoint → UI, sin que nadie toque la web.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { NotifyChannelOut } from "@takab/sdk";

import fixtures from "../../../../shared/fixtures/notify-channels.json";
import NotificationChannels from "./NotificationChannels";
import { CASCADE_ORDER } from "./model";
import type { ChannelDraft } from "./model";

const HOY = fixtures.escenarios.sin_credenciales.channels as NotifyChannelOut[];
const TRAS_T276A = fixtures.escenarios.sms_con_credenciales.channels as NotifyChannelOut[];

const DRAFTS: ChannelDraft[] = CASCADE_ORDER.map((key) => ({
  key,
  enabled: true,
  destination: key === "webhook" ? "https://ops.cliente.mx/takab" : "+525500000000",
}));

function renderChannels(reality: NotifyChannelOut[] | undefined) {
  render(
    <NotificationChannels drafts={DRAFTS} disabled={false} onChange={vi.fn()} reality={reality} />,
  );
}

/** Rótulo de realidad del canal (el que la tarjeta pinta bajo su nombre). */
function realityText(key: string): string {
  return screen.getByTestId(`channel-reality-${key}`).textContent ?? "";
}

describe("realidad del canal · se PREGUNTA, no se cree", () => {
  it("hoy: SMS y WhatsApp SIMULADOS porque lo dice el servidor, no el código", () => {
    renderChannels(HOY);
    expect(realityText("sms")).toMatch(/SIMULAD/);
    expect(realityText("whatsapp")).toMatch(/SIMULAD/);
    expect(realityText("email")).toMatch(/SIMULAD/);
    expect(realityText("webhook")).toMatch(/REAL/);
    expect(realityText("webhook")).not.toMatch(/SIMULAD/);
  });

  // ÉSTE es el criterio 3: el único cambio entre este test y el anterior es la
  // configuración con la que arrancó la API. Ni una línea de la web se mueve.
  it("tras T-2.76.a: las MISMAS pantallas dicen que el SMS ya entrega", () => {
    renderChannels(TRAS_T276A);
    expect(realityText("sms")).toMatch(/REAL/);
    expect(realityText("sms")).not.toMatch(/SIMULAD/);
    // y solo el SMS se mueve: WhatsApp sigue sin proveedor.
    expect(realityText("whatsapp")).toMatch(/SIMULAD/);
  });

  it("sin dato (cargando o /notify/channels caído) ⇒ S/D, JAMÁS «real»", () => {
    renderChannels(undefined);
    for (const key of CASCADE_ORDER) {
      expect(realityText(key)).toContain("S/D");
      expect(realityText(key)).not.toMatch(/\bREAL\b/);
    }
  });

  it("un canal ausente de la respuesta también es S/D, no un canal real", () => {
    // El default bajo incertidumbre es la peor causa, igual que hizo T-2.75 con
    // `is_simulated`: quien no se declara no ha demostrado que entregue.
    renderChannels(HOY.filter((c) => c.channel !== "sms"));
    expect(realityText("sms")).toContain("S/D");
    expect(realityText("sms")).not.toMatch(/\bREAL\b/);
  });

  it("el rótulo estático «SIMULADO en el MVP» ya no existe en ninguna parte", () => {
    renderChannels(TRAS_T276A);
    expect(screen.queryByText(/SIMULADO en el MVP/i)).toBeNull();
  });
});
