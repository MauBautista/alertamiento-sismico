// T-2.71 · El banner que declara que hay alarmas mudas.
//
// Criterio 2 de la ficha: "la consola lo dice en pantalla mientras dure; nadie
// debe deducirlo". Lo que se mide aquí:
//
// - Se ve MIENTRAS DURE, incluso bajo alerta real. Es el precedente exacto del
//   `banner-wr1` violeta del panel LAN (T-1.69): un modo que calla algo hacia
//   fuera se declara SIEMPRE, "porque el operador DEBE saber". El simulacro se
//   degrada a badge bajo alerta viva; esto NO — un simulacro que no se ve es
//   ruido, unas alarmas mudas que no se ven es un edificio sin vigilancia.
// - Los 4 estados obligatorios, y en particular que un fallo de lectura JAMÁS
//   pinte "no hay ventana". Decir que no hay ventana cuando las alarmas están
//   mudas es el peor fallo posible de esta pantalla.

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ useMaintenanceWindows: vi.fn() }));
vi.mock("./useMaintenanceWindows", () => ({
  useMaintenanceWindows: mocks.useMaintenanceWindows,
}));

import { expectFourStates, type UiState } from "../../test-utils/states";
import MaintenanceBanner from "./MaintenanceBanner";
import type { MaintenanceData } from "./useMaintenanceWindows";

const NOW = Date.parse("2026-08-06T03:35:00Z");

const WINDOW = {
  window_id: "w-1",
  tenant_id: "t-1",
  gateway_id: "gw-1",
  gateway_serial: "SER-1",
  site_name: "Torre Dev",
  scope: "gateway",
  opened_by: "u-1",
  reason: "cambio del cable de red del Shake",
  duration_s: 1800,
  opened_at: "2026-08-06T03:30:12Z",
  starts_at: "2026-08-06T03:31:00Z",
  ends_at: "2026-08-06T04:01:00Z",
  closed_at: null,
  active: true,
  alarm_names: ["takab-dev-gateway-offline-gw-a", "takab-dev-sensor-mudo-gw-a"],
  requested: 2,
  silenced: 2,
  missing_names: [],
  missing: 0,
  mute_rule: "takab-dev-mw-w-1",
};

function data(over: Partial<MaintenanceData> = {}): MaintenanceData {
  return {
    items: [],
    loading: false,
    readError: null,
    updatedAt: NOW - 5_000,
    refetch: vi.fn(),
    close: vi.fn(),
    pending: false,
    error: null,
    ...over,
  } as MaintenanceData;
}

beforeEach(() => {
  vi.setSystemTime(NOW);
  mocks.useMaintenanceWindows.mockReturnValue(data());
});

describe("MaintenanceBanner", () => {
  it("declara la ventana con su hora UTC de cierre y su acuse", () => {
    mocks.useMaintenanceWindows.mockReturnValue(data({ items: [WINDOW] as never }));
    render(<MaintenanceBanner hasLiveIncident={false} />);
    const banner = screen.getByTestId("maintenance-banner");
    expect(banner.textContent).toContain("VENTANA DE MANTENIMIENTO");
    expect(banner.textContent).toContain("TERMINA 04:01 UTC");
    expect(banner.textContent).toContain("2/2 ALARMAS SILENCIADAS");
    // El motivo va EN PANTALLA: una ventana sin dueño visible es una alarma
    // apagada sin dueño.
    expect(banner.textContent).toContain("cambio del cable de red del Shake");
  });

  it("nombra el gabinete tapado, no solo 'una ventana'", () => {
    mocks.useMaintenanceWindows.mockReturnValue(data({ items: [WINDOW] as never }));
    render(<MaintenanceBanner hasLiveIncident={false} />);
    expect(screen.getByTestId("maintenance-banner").textContent).toContain("Torre Dev");
  });

  it("SIGUE VISIBLE bajo alerta real (a diferencia del simulacro)", () => {
    // T-1.69, literal: un modo que calla algo se declara con banner SIEMPRE
    // VISIBLE, incluso bajo alerta real, porque el operador DEBE saberlo. Si el
    // gabinete está mudo justo durante el sismo, ese es el momento en el que más
    // falta hace saber que su alarma no va a sonar.
    mocks.useMaintenanceWindows.mockReturnValue(data({ items: [WINDOW] as never }));
    render(<MaintenanceBanner hasLiveIncident={true} />);
    const banner = screen.getByTestId("maintenance-banner");
    expect(banner.textContent).toContain("TERMINA 04:01 UTC");
    expect(banner.textContent).toContain("2/2 ALARMAS SILENCIADAS");
  });

  it("una ventana que no silenció nada NO se pinta como éxito", () => {
    mocks.useMaintenanceWindows.mockReturnValue(
      data({
        items: [
          { ...WINDOW, requested: 2, silenced: 0, missing: 2, missing_names: ["a", "b"] },
        ] as never,
      }),
    );
    render(<MaintenanceBanner hasLiveIncident={false} />);
    expect(screen.getByTestId("maintenance-banner").textContent).toContain(
      "0/2 ALARMAS SILENCIADAS · 2 SIN SILENCIAR: NO EXISTEN O LA REGLA NO LAS GUARDÓ",
    );
  });

  // --- [B8] El titular obedece al servidor, no al deseo del que abrió --------

  it("con TODAS mudas afirma el silencio y lo marca en el DOM", () => {
    mocks.useMaintenanceWindows.mockReturnValue(data({ items: [WINDOW] as never }));
    render(<MaintenanceBanner hasLiveIncident={false} />);
    const banner = screen.getByTestId("maintenance-banner");
    expect(banner.textContent).toContain("ALARMAS DE OPERACIÓN SILENCIADAS");
    expect(banner.querySelector('[data-mute="all"]')).not.toBeNull();
  });

  it("con el silenciador APAGADO —el default de producción— NO afirma el silencio", () => {
    // `ops_muting_enabled=False` ⇒ `mute_rule` NULL y `silenced=0`. El banner
    // decía «ALARMAS DE OPERACIÓN SILENCIADAS» igual: una afirmación que el
    // servidor desmiente en el mismo payload, mientras el on-call sigue
    // recibiendo los correos que cree haber callado.
    mocks.useMaintenanceWindows.mockReturnValue(
      data({
        items: [
          {
            ...WINDOW,
            requested: 2,
            silenced: 0,
            missing: 2,
            missing_names: ["a", "b"],
            mute_rule: null,
          },
        ] as never,
      }),
    );
    render(<MaintenanceBanner hasLiveIncident={false} />);
    const banner = screen.getByTestId("maintenance-banner");
    expect(banner.textContent).toContain("LAS ALARMAS DE OPERACIÓN SIGUEN SONANDO");
    expect(banner.textContent).not.toContain("ALARMAS DE OPERACIÓN SILENCIADAS");
    // …y la causa no se disfraza de "esa alarma no existe".
    expect(banner.textContent).toContain("SILENCIADOR APAGADO O CON FALLO");
    expect(banner.textContent).not.toContain("SIN ALARMA EXISTENTE");
    expect(banner.querySelector('[data-mute="none"]')).not.toBeNull();
  });

  it("con ALGUNAS mudas dice que el resto sigue sonando", () => {
    mocks.useMaintenanceWindows.mockReturnValue(
      data({
        items: [
          { ...WINDOW, requested: 2, silenced: 1, missing: 1, missing_names: ["a"] },
        ] as never,
      }),
    );
    render(<MaintenanceBanner hasLiveIncident={false} />);
    const banner = screen.getByTestId("maintenance-banner");
    expect(banner.textContent).toContain("PARTE DE LAS ALARMAS DE OPERACIÓN SIGUE SONANDO");
    expect(banner.textContent).toContain("1/2 ALARMAS SILENCIADAS");
    expect(banner.querySelector('[data-mute="partial"]')).not.toBeNull();
  });

  it("una ventana sin alarmas que callar no insinúa que haya callado alguna", () => {
    mocks.useMaintenanceWindows.mockReturnValue(
      data({
        items: [
          { ...WINDOW, requested: 0, silenced: 0, missing: 0, missing_names: [], mute_rule: null },
        ] as never,
      }),
    );
    render(<MaintenanceBanner hasLiveIncident={false} />);
    const banner = screen.getByTestId("maintenance-banner");
    expect(banner.textContent).toContain("SIN ALARMAS DE OPERACIÓN QUE SILENCIAR");
    expect(banner.querySelector('[data-mute="none_requested"]')).not.toBeNull();
  });

  // --- [C2] El acuse A CIEGAS no puede pintarse como uno medido -------------
  //
  // Reproducido en el servidor con un doble cuyo `put_alarm_mute_rule` responde
  // y cuyo `get_alarm_mute_rule` lanza `TimeoutError`: el acuse sale con
  // `verified=False` y las cifras rellenas al valor peligroso (`silenced =
  // requested`), que es la decisión correcta ALLÍ. Aquí llegaba como un `2/2` y
  // la consola lo pintaba idéntico a un silencio comprobado — misma familia que
  // B8 (afirmar lo que el servidor no sostiene), por el otro camino.

  it("un acuse SIN COMPROBAR no se pinta como el mismo payload comprobado", () => {
    const render1 = (verified: boolean) => {
      mocks.useMaintenanceWindows.mockReturnValue(
        data({ items: [{ ...WINDOW, mute_verified: verified }] as never }),
      );
      const view = render(<MaintenanceBanner hasLiveIncident={false} />);
      const banner = screen.getByTestId("maintenance-banner");
      const texto = banner.textContent ?? "";
      const marca = banner.querySelector("[data-mute]")?.getAttribute("data-mute");
      view.unmount();
      return { texto, marca };
    };
    const medido = render1(true);
    const aCiegas = render1(false);
    expect(aCiegas.texto).not.toBe(medido.texto);
    expect(aCiegas.marca).toBe("assumed");
    expect(medido.marca).toBe("all");
  });

  it("el acuse a ciegas NO afirma el silencio ni imprime la cifra como medida", () => {
    mocks.useMaintenanceWindows.mockReturnValue(
      data({ items: [{ ...WINDOW, mute_verified: false }] as never }),
    );
    render(<MaintenanceBanner hasLiveIncident={false} />);
    const banner = screen.getByTestId("maintenance-banner");
    expect(banner.textContent).toContain("SILENCIO SUPUESTO");
    expect(banner.textContent).not.toContain("ALARMAS DE OPERACIÓN SILENCIADAS");
    // `2/2 ALARMAS SILENCIADAS` con `verified=false` es el 2 que el servidor
    // escribió asumiendo lo peor. Pintarlo sería inventar la medición.
    expect(banner.textContent).not.toContain("2/2 ALARMAS SILENCIADAS");
    expect(banner.textContent).toContain("2 ALARMAS PEDIDAS");
  });

  // --- [C·anclaje] REABRIR VIGILANCIA que FALLA ------------------------------
  //
  // Encontrado al cerrar C1/C2, de la misma familia y en la dirección más cara:
  // el botón es la ÚNICA vía con re-disparo documentado (`DeleteAlarmMuteRule`
  // desilencia en el acto y, si la alarma quedó en ALARM, su correo sale). Si la
  // mutación falla y la pantalla se lo traga, el operador pulsa, ve desaparecer
  // nada, se va convencido de haber devuelto la vigilancia — y el edificio se
  // queda mudo hasta que la mute rule expire sola, hasta 4 h después.
  //
  // El componente YA lo pinta; lo que no había era nada que lo sujetara, así que
  // borrar ese `error !== null` no ponía roja ninguna prueba. Esto lo ancla: no
  // persigue un defecto, impide que vuelva a serlo.
  it("un REABRIR VIGILANCIA que falla se declara: la ventana sigue ahí y el fallo también", () => {
    mocks.useMaintenanceWindows.mockReturnValue(
      data({ items: [WINDOW] as never, error: "la ventana no se cerró (HTTP 502)" }),
    );
    render(<MaintenanceBanner hasLiveIncident={false} />);
    const banner = screen.getByTestId("maintenance-banner");
    // El fallo se dice, y con `role="alert"`: es una acción que el operador cree
    // haber completado.
    expect(screen.getByRole("alert").textContent).toContain("LA VENTANA NO SE CERRÓ");
    // Y la ventana NO desaparece del banner por haber intentado cerrarla: las
    // alarmas siguen mudas, así que el aviso de que lo están sigue siendo cierto.
    expect(banner.textContent).toContain("TERMINA 04:01 UTC");
    expect(banner.textContent).toContain("ALARMAS DE OPERACIÓN SILENCIADAS");
  });

  it("un fallo de lectura CON ventana conocida la conserva y la rotula RETENIDO", () => {
    mocks.useMaintenanceWindows.mockReturnValue(
      data({ items: [WINDOW] as never, readError: "GET /maintenance-windows falló (500)" }),
    );
    const { container } = render(<MaintenanceBanner hasLiveIncident={false} />);
    // Sigue anunciando el silencio…
    expect(screen.getByTestId("maintenance-banner").textContent).toContain("TERMINA 04:01 UTC");
    // …y avisa de que el dato es viejo.
    expect(container.querySelector('[data-state="stale"]')).not.toBeNull();
  });

  it("un fallo de lectura SIN ventana conocida muestra el fallo, jamás 'no hay ventana'", () => {
    mocks.useMaintenanceWindows.mockReturnValue(
      data({ items: [], readError: "GET /maintenance-windows falló (500)" }),
    );
    const { container } = render(<MaintenanceBanner hasLiveIncident={false} />);
    expect(container.querySelector('[data-state="error"]')).not.toBeNull();
    expect(container.textContent).not.toContain("SIN VENTANA DE MANTENIMIENTO");
  });

  it("cumple los 4 estados obligatorios", () => {
    expectFourStates((state: UiState) => {
      mocks.useMaintenanceWindows.mockReturnValue(
        data({
          loading: state === "loading",
          readError: state === "error" || state === "stale" ? "fallo" : null,
          items: state === "stale" ? ([WINDOW] as never) : [],
        }),
      );
      return <MaintenanceBanner hasLiveIncident={false} />;
    });
  });
});
