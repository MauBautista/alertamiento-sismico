import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { alertKind } from "../scene/scene";
import AlertBanner from "./AlertBanner";
import { alertaViva } from "./alertaViva";
import type { LiveIncident } from "./useLiveIncidents";

const INCIDENT: LiveIncident = {
  incident_id: "abcdef12-0000-0000-0000-000000000000",
  tenant_id: "t-1",
  site_id: "s-1",
  event_id: "EVT-20260708-1041",
  opened_at: "2026-07-08T10:41:30Z",
  closed_at: null,
  severity: "critical",
  state: "open",
  trigger: "sasmex",
  max_pga_g: 0.15,
  max_pgv_cms: 4.2,
};

const con = (trigger: string): LiveIncident => ({ ...INCIDENT, trigger });

describe("AlertBanner", () => {
  it("sin incidente crítico no renderiza nada", () => {
    const { container } = render(<AlertBanner incident={null} siteName={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("banner MVP: PROTÉJASE + sitio + EVENT_ID + PGA MAX; sin magnitud ni T-MINUS", () => {
    // El contacto seco del WR-1 ES la alerta oficial: el único caso que lleva
    // este titular. Hasta T-5.03 el fixture de este test traía
    // `trigger: "local_threshold"` y aun así esperaba «PROTÉJASE» — o sea que la
    // prueba del invariante estaba escrita ALREDEDOR del defecto que T-5.03 cierra.
    render(<AlertBanner incident={INCIDENT} siteName="Planta Cholula · Edificio A" />);
    expect(screen.getByRole("alert")).toHaveTextContent("ALERTA SÍSMICA · PROTÉJASE");
    expect(screen.getByRole("alert")).toHaveTextContent("Planta Cholula · Edificio A");
    expect(screen.getByRole("alert")).toHaveTextContent("EVENT_ID EVT-20260708-1041");
    expect(screen.getByRole("alert")).toHaveTextContent("0.150");
    // El WR-1 es booleano: NUNCA magnitud preliminar ni countdown (desviación ratificada).
    expect(screen.getByRole("alert")).not.toHaveTextContent(/T-MINUS/);
    expect(screen.getByRole("alert")).not.toHaveTextContent(/M\s*\d\.\d/);
  });
});

// [T-5.03] EL BANNER NO PUEDE LLAMAR SISMO A UN BOTÓN DE PÁNICO.
//
// Medido en la auditoría del 2026-09-02: el incidente se elegía sólo por
// `severity` y los dos textos estaban a fuego, así que `trigger='manual'` —el
// quórum de pánico de D-11— salía en el videowall como «ALERTA SÍSMICA ·
// PROTÉJASE» + «EDGE · RS4D · REGLAS LOCALES EJECUTADAS», mientras la app móvil
// pintaba «NO ES UNA ALERTA SÍSMICA» para ese mismo incidente. Dos pantallas del
// mismo evento contradiciéndose delante del mismo cliente.
describe("AlertBanner · el titular se atribuye a quien lo dijo", () => {
  it("una activación manual NO se titula como sismo ni se le cuelga al sensor", () => {
    render(<AlertBanner incident={con("manual")} siteName="Torre B" />);
    const caja = screen.getByRole("alert");
    expect(caja).toHaveTextContent("ALERTA ACTIVADA MANUALMENTE");
    expect(caja).toHaveAttribute("data-seismic", "false");
    // Las dos mentiras que traía: ni sísmica, ni ejecutada por el RS4D.
    expect(caja).not.toHaveTextContent(/SÍSMIC/);
    expect(caja).not.toHaveTextContent(/SISMO/);
    expect(caja).not.toHaveTextContent(/RS4D/);
    expect(caja).not.toHaveTextContent(/SASMEX/);
  });

  it("el umbral de una sola estación dice AVISO, no PROTÉJASE (política T-2.32)", () => {
    render(<AlertBanner incident={con("local_threshold")} siteName="Torre B" />);
    const caja = screen.getByRole("alert");
    expect(caja).toHaveTextContent("AVISO SÍSMICO · UMBRAL INSTRUMENTAL");
    expect(caja).toHaveTextContent("SOLO AVISO, SIN ACTUACIÓN");
    expect(caja).not.toHaveTextContent("PROTÉJASE");
    expect(caja).not.toHaveTextContent(/SASMEX/);
    // [T-6.01 · U-28] …y tampoco viste la carcasa roja: la hoja lo viste de
    // ámbar por este atributo, que sale de la tabla de escena.
    expect(caja).toHaveAttribute("data-authorizes", "false");
  });

  it("[U-28] sólo SASMEX y el cuórum autorizan: el resto lo declara en el DOM", () => {
    for (const [trigger, esperado] of [
      ["sasmex", "true"],
      ["quorum", "true"],
      ["local_threshold", "false"],
      ["manual", "false"],
      ["teletransporte", "false"],
    ] as const) {
      const { unmount } = render(<AlertBanner incident={con(trigger)} siteName="Torre B" />);
      expect(screen.getByRole("alert"), trigger).toHaveAttribute("data-authorizes", esperado);
      unmount();
    }
  });

  it("el quórum se atribuye a la red y declara que el comando iba firmado", () => {
    render(<AlertBanner incident={con("quorum")} siteName="Torre B" />);
    const caja = screen.getByRole("alert");
    expect(caja).toHaveTextContent("SISMO CONFIRMADO POR LA RED");
    expect(caja).toHaveTextContent("COMANDO FIRMADO");
    expect(caja).not.toHaveTextContent(/SASMEX/);
  });

  it("un trigger que nadie mapeó se rotula desconocido, no sísmico", () => {
    render(<AlertBanner incident={con("teletransporte")} siteName="Torre B" />);
    const caja = screen.getByRole("alert");
    expect(caja).toHaveTextContent("ORIGEN NO RECONOCIDO");
    expect(caja).toHaveTextContent("TELETRANSPORTE");
    expect(caja).toHaveAttribute("data-seismic", "false");
    expect(caja).not.toHaveTextContent("PROTÉJASE");
  });
});

// [T-7.19 · D-30] LA ALERTA RESPIRA, Y DEJA DE HACERLO POR ESTADO
describe("AlertBanner · la carcasa viva", () => {
  const conEstado = (state: string): LiveIncident => ({ ...INCIDENT, state });

  it("declara VIVA la alerta que el servidor todavía sostiene", () => {
    for (const state of ["open", "acked"]) {
      const { unmount } = render(<AlertBanner incident={conEstado(state)} siteName={null} />);
      expect(screen.getByTestId("alert-banner").dataset.alive, state).toBe("true");
      unmount();
    }
  });

  it("en REVISIÓN y CERRADO deja de estarlo: el estado la apaga, no un reloj", () => {
    for (const state of ["in_review", "closed"]) {
      const { unmount } = render(<AlertBanner incident={conEstado(state)} siteName={null} />);
      expect(screen.getByTestId("alert-banner").dataset.alive, state).toBe("false");
      unmount();
    }
  });

  it("el TEXTO no depende de que esté viva: se lee igual con la animación apagada", () => {
    // Condición 2 de `D-30`: siempre hay un portador que no es movimiento. Con
    // la alerta viva y el halo apagado (`reduce-motion`) el titular es el mismo.
    render(<AlertBanner incident={conEstado("acked")} siteName="Edificio Central" />);
    const banner = screen.getByTestId("alert-banner");
    expect(banner.textContent).toContain("ALERTA SÍSMICA");
    expect(banner.dataset.authorizes).toBe("true");
  });

  it("[T-7.20] en REVISIÓN el muro DEJA DE GRITAR: dice SISMO CONCLUIDO", () => {
    // ⚠️ Este caso usaba `in_review` para decir «sin animación», y al hacerlo
    // dejaba fijado el defecto: la tarjeta seguía diciendo «ALERTA SÍSMICA ·
    // PROTÉJASE» con el sismo ya terminado. `T-7.16` le dio la revisión a la
    // franja del shell, que NO se pinta en el muro, así que el videowall —la
    // pantalla que alguien mira de pie— era la única superficie que no se
    // enteraba. Lo cazó la corrida real del e2e, no una prueba de unidad.
    render(
      <AlertBanner
        incident={conEstado("in_review")}
        siteName="Edificio Central"
        now={Date.parse(INCIDENT.opened_at) + 90_000}
      />,
    );
    const banner = screen.getByTestId("alert-banner");
    expect(banner.textContent).toContain("SISMO CONCLUIDO · ANALIZANDO");
    expect(banner.textContent).not.toContain("ALERTA SÍSMICA");
    expect(banner.textContent).not.toContain("PROTÉJASE");
    // La carcasa se viste de revisión, y la fuente sigue escrita: que el sismo
    // concluyera no borra de dónde vino el aviso.
    expect(banner.dataset.kind).toBe("review");
    expect(banner.textContent).toContain("SASMEX");
    // Y el sello «● AUTO» se va: afirma una actuación que ya no está en curso.
    expect(banner.textContent).not.toContain("AUTO");
    expect(banner.textContent).toContain("SISMO HACE 01:30");
  });

  it("[T-7.20] pasadas seis horas sin clasificar, el muro habla en PASADO", () => {
    render(
      <AlertBanner
        incident={conEstado("in_review")}
        siteName="Edificio Central"
        now={Date.parse(INCIDENT.opened_at) + 7 * 3600_000}
      />,
    );
    expect(screen.getByTestId("alert-banner").textContent).toContain(
      "SISMO CONCLUIDO · SIN CLASIFICAR",
    );
  });

  it("`alertaViva` y `alertKind` miran el MISMO estado y no pueden divergir", () => {
    // Las dos deciden cosas distintas —una si la carcasa respira, la otra qué
    // escena manda— pero sobre el mismo hecho. Si una dijera `review` y la otra
    // «viva», el muro tendría una tarjeta respirando bajo una franja que dice
    // SISMO CONCLUIDO.
    for (const state of ["open", "acked", "in_review", "closed"]) {
      const inc = conEstado(state);
      expect(alertaViva(inc), state).toBe(alertKind(inc) !== "review" && state !== "closed");
    }
  });
});
