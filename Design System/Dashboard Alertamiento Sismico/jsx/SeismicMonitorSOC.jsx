// jsx/SeismicMonitorSOC.jsx
// =====================================================================
// SeismicMonitorSOC — TAKAB Centro de Monitoreo (videowall)
// Root with global tab router across four operator workstations:
//   CONSOLA  — Live Wall (Tab 1: C4I)
//   FLOTA    — Edge fleet / cabinet maintenance (Tab 2)
//   TRIAGE   — Post-event history + structural verdict (Tab 3)
//   TENANTS  — Multi-tenant matrix + thresholds (Tab 4)
//
// Architecture (production):
//   Edge (Raspberry Shake RS4D / SeedLink TCP) → Edge Gateway (PGA/PGV
//   feature extraction + local rules: BMS via BACnet/IP, sirens, gas
//   valves, elevators, door-holds) → MQTT bridge → Cloud BFF
//   (NATS JetStream, GraphQL subscriptions) → this UI.
//
// Operator-grade rules baked in:
//   1. Time-to-Recognition < 2s — alert hero is the only red surface,
//      sized so M and T-MINUS are legible at 5m on a videowall.
//   2. Information density without cognitive load — fixed 16:9 grid,
//      no nested scroll, mono numerals only.
//   3. Operative traceability — every actuator row carries an EDGE
//      timestamp; cloud actions are clearly distinguished from local-edge.
//   4. Two-step confirmation for every operator action that touches
//      real-world actuators or notifies stakeholders.
// =====================================================================

// ---------------------------------------------------------------------
// CONSOLA C4I — Tab 1 (the original live wall, extracted into a sub-view
// so the root can swap tabs without re-mounting the wall).
// ---------------------------------------------------------------------
const ConsoleC4I = ({ alertOn, setAlertOn, countdown, magnitude, detailOpen, setDetailOp }) => (
  <div className="soc-shell" data-screen-label="01 Consola C4I · Live Wall">
    <main className="soc-main">
      <div className="soc-stage">
        <MapPanel critical={alertOn} />
        <AlertHero
          active={alertOn}
          magnitude={magnitude}
          countdown={countdown}
          pgaMax={0.15}
          site="PLANTA CHOLULA · EDIFICIO A"
        />
      </div>
      <IncidentTable onConfirm={() => setAlertOn(false)} />
    </main>
    {detailOpen && <DetailPanel onClose={() => setDetailOp(false)} />}
  </div>
);

// ---------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------
const SeismicMonitorSOC = () => {
  const [active, setActive]       = React.useState('CONSOLA');
  const [alertOn, setAlertOn]     = React.useState(true);
  const [detailOpen, setDetailOp] = React.useState(true);
  const [countdown, setCountdown] = React.useState(15);
  const [magnitude]               = React.useState(6.8);

  // === LIVE COUNTDOWN (only ticks while Consola is mounted & alert active)
  React.useEffect(() => {
    if (!alertOn) return;
    const t = setInterval(() => setCountdown(c => (c > 0 ? c - 1 : 15)), 1000);
    return () => clearInterval(t);
  }, [alertOn]);

  // === ICON HYDRATION ================================================
  // Lucide is loaded via CDN; rebuild glyphs every render to cover icons
  // mounted in newly-rendered cards (no fade — design system forbids it).
  React.useEffect(() => {
    if (window.lucide) window.lucide.createIcons();
  });

  return (
    <div className="soc-app">
      <Topbar active={active} onNav={setActive} connected={true} />

      {active === 'CONSOLA' && (
        <ConsoleC4I
          alertOn={alertOn} setAlertOn={setAlertOn}
          countdown={countdown} magnitude={magnitude}
          detailOpen={detailOpen} setDetailOp={setDetailOp}
        />
      )}
      {active === 'FLOTA'   && <div className="soc-tabpage"><FleetEdge /></div>}
      {active === 'TRIAGE'  && <div className="soc-tabpage"><TriageHistory /></div>}
      {active === 'TENANTS' && <div className="soc-tabpage"><MultiTenantMatrix /></div>}

      {/* Demo toggles — only on the live-wall tab */}
      {active === 'CONSOLA' && (
        <div className="soc-demo">
          <span>DEMO</span>
          <button className="soc-btn soc-btn--secondary" onClick={() => { setAlertOn(a => !a); setCountdown(15); }}>
            {alertOn ? 'CLEAR ALERT' : 'TRIGGER M 6.8'}
          </button>
          <button className="soc-btn soc-btn--ghost" onClick={() => setDetailOp(d => !d)}>
            {detailOpen ? 'HIDE DETAIL' : 'SHOW DETAIL'}
          </button>
        </div>
      )}
    </div>
  );
};

window.SeismicMonitorSOC = SeismicMonitorSOC;
