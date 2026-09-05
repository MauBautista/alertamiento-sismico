import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AlertBanner from "./AlertBanner";
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
