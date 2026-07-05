// jsx/Topbar.jsx
// Persistent SOC top navigation — logo · system status · nav · UTC/CST clock
// Wire-up note: SistemaOperativo pill should be driven by NATS/MQTT subject
// `takab.system.heartbeat` (last-seen <2s = CONECTADO).

const Topbar = ({ active = 'DASHBOARD', onNav, connected = true }) => {
  const [now, setNow] = React.useState(new Date());
  React.useEffect(() => {
    // 100ms tick keeps mono seconds field smooth; never use eased transitions on telemetry.
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const fmtDate = now.toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric'
  }).toUpperCase();
  const fmtCST = now.toTimeString().slice(0, 8);
  const fmtUTC = now.toISOString().slice(11, 19);

  const tabs = [
    { id: 'CONSOLA',  label: 'CONSOLA C4I',  icon: 'radar' },
    { id: 'FLOTA',    label: 'FLOTA EDGE',   icon: 'server' },
    { id: 'TRIAGE',   label: 'TRIAGE',       icon: 'file-search' },
    { id: 'TENANTS',  label: 'MULTI-TENANT', icon: 'shield' },
  ];

  return (
    <header className="soc-topbar">
      {/* === BRAND ============================================== */}
      {/* Brand lockup: official TAKAB wordmark PNG (blue, with tagline).
          Isotipo PNG is kept available at assets/icono-k-takab.png for
          places where the K mark is needed standalone (favicons, splash). */}
      <div className="soc-brand">
        <img
          src="assets/LogoTakab2.png"
          alt="TAKAB TECHNOLOGY — Lo mejor lo estamos creando"
          className="soc-brand__logo"
        />
      </div>

      {/* === SYSTEM STATUS ====================================== */}
      <div className="soc-system">
        <span className="soc-meta">SISTEMA OPERATIVO</span>
        <span className={`soc-pill ${connected ? 'soc-pill--ok' : 'soc-pill--crit'}`}>
          <span className="soc-dot soc-dot--pulse" /> {connected ? 'CONECTADO' : 'DESCONECTADO'}
        </span>
        <span className="soc-pill soc-pill--edge">
          <i data-lucide="cpu" width="12" height="12" /> EDGE · MQTT 0.42 ms
        </span>
      </div>

      {/* === NAV TABS =========================================== */}
      <nav className="soc-nav" aria-label="Primary">
        {tabs.map(t => (
          <button
            key={t.id}
            className={`soc-nav__tab${active === t.id ? ' is-active' : ''}`}
            onClick={() => onNav?.(t.id)}
            aria-current={active === t.id ? 'page' : undefined}
          >
            <i data-lucide={t.icon} width="14" height="14" />
            {t.label}
          </button>
        ))}
      </nav>

      {/* === CLOCK ============================================== */}
      <div className="soc-clock" aria-label="System time">
        <span className="meta">UTC</span>
        <span>{fmtUTC}</span>
        <span className="sep">|</span>
        <span className="meta">CST</span>
        <span>{fmtCST}</span>
        <span className="sep">|</span>
        <span>{fmtDate}</span>
      </div>
    </header>
  );
};

window.Topbar = Topbar;
