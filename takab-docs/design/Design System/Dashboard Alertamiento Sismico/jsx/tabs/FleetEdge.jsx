// jsx/tabs/FleetEdge.jsx
// Tab 2 — Flota Edge y Estado de Gabinetes
// Maintenance-oriented grid view for the field-engineering team.
// Wire-up:
//   Each card subscribes to `takab.gateway.{site_id}.heartbeat` (1Hz)
//   plus `takab.gateway.{site_id}.health` (UPS/SOC/relay snapshot).
//   Autodiagnóstico Silencioso publishes a job to `takab.diag.run`,
//   which the gateway acks in ~12s without producing any audible/visible
//   activation at the site (sirens, valves untouched).

const SITES = [
  {
    id: 'CHL-A', name: 'Planta Cholula',
    location: 'Cholula, Puebla', tenant: 'INDUSTRIAS DEL VALLE S.A.',
    mqtt: 'ok',      mqttLatency: '0.42 ms',
    seedlink: 'ok',  seedlinkLag: '0.18 s',
    ups: { state: 'mains', level: 100, autonomy: '8 h 12 m' },
    relays: [
      { id: 'R1', label: 'Sirena',     state: 'armed' },
      { id: 'R2', label: 'Gas',        state: 'armed' },
      { id: 'R3', label: 'Ascensores', state: 'armed' },
      { id: 'R4', label: 'Puertas',    state: 'armed' },
    ],
    fw: 'edge-3.4.2', lastDiag: 'hace 2 h',
  },
  {
    id: 'HGP-1', name: 'Hospital General',
    location: 'Puebla, Pue.', tenant: 'SECRETARÍA DE SALUD',
    mqtt: 'ok',      mqttLatency: '0.51 ms',
    seedlink: 'ok',  seedlinkLag: '0.22 s',
    ups: { state: 'mains', level: 96, autonomy: '7 h 48 m' },
    relays: [
      { id: 'R1', label: 'Sirena',     state: 'armed' },
      { id: 'R2', label: 'Gas Med.',   state: 'armed' },
      { id: 'R3', label: 'Quirófanos', state: 'armed' },
      { id: 'R4', label: 'Puertas',    state: 'armed' },
    ],
    fw: 'edge-3.4.2', lastDiag: 'hace 14 min',
  },
  {
    id: 'CDX-T1', name: 'Corporativo CDMX',
    location: 'Polanco, CDMX', tenant: 'GRUPO TAKAB',
    mqtt: 'warn',    mqttLatency: '24.6 ms',
    seedlink: 'ok',  seedlinkLag: '0.31 s',
    ups: { state: 'battery', level: 72, autonomy: '5 h 40 m' },
    relays: [
      { id: 'R1', label: 'Sirena',     state: 'armed' },
      { id: 'R2', label: 'Gas',        state: 'armed' },
      { id: 'R3', label: 'Ascensores', state: 'fault' },
      { id: 'R4', label: 'Puertas',    state: 'armed' },
    ],
    fw: 'edge-3.4.1', lastDiag: 'hace 3 h',
  },
  {
    id: 'TEH-CD', name: 'CD Tehuacán',
    location: 'Tehuacán, Pue.', tenant: 'LOGÍSTICA NACIONAL',
    mqtt: 'ok',      mqttLatency: '0.68 ms',
    seedlink: 'ok',  seedlinkLag: '0.19 s',
    ups: { state: 'mains', level: 100, autonomy: '9 h 02 m' },
    relays: [
      { id: 'R1', label: 'Sirena',     state: 'armed' },
      { id: 'R2', label: 'Gas',        state: 'armed' },
      { id: 'R3', label: 'Montacargas', state: 'armed' },
      { id: 'R4', label: 'Puertas',    state: 'armed' },
    ],
    fw: 'edge-3.4.2', lastDiag: 'hace 1 h',
  },
  {
    id: 'ATX-BG', name: 'Bodega Atlixco',
    location: 'Atlixco, Pue.', tenant: 'INDUSTRIAS DEL VALLE S.A.',
    mqtt: 'ok',      mqttLatency: '0.49 ms',
    seedlink: 'warn', seedlinkLag: '4.20 s',
    ups: { state: 'mains', level: 88, autonomy: '6 h 50 m' },
    relays: [
      { id: 'R1', label: 'Sirena',     state: 'armed' },
      { id: 'R2', label: 'Gas',        state: 'armed' },
      { id: 'R3', label: 'Cortinas',   state: 'armed' },
      { id: 'R4', label: 'Puertas',    state: 'armed' },
    ],
    fw: 'edge-3.4.2', lastDiag: 'hace 6 h',
  },
  {
    id: 'ZCT-PL', name: 'Planta Zacatlán',
    location: 'Zacatlán, Pue.', tenant: 'AGROINDUSTRIA NORTE',
    mqtt: 'crit',    mqttLatency: '— sin enlace —',
    seedlink: 'crit', seedlinkLag: '— sin enlace —',
    ups: { state: 'battery', level: 34, autonomy: '2 h 10 m' },
    relays: [
      { id: 'R1', label: 'Sirena',     state: 'unknown' },
      { id: 'R2', label: 'Gas',        state: 'unknown' },
      { id: 'R3', label: 'Ascensores', state: 'unknown' },
      { id: 'R4', label: 'Puertas',    state: 'unknown' },
    ],
    fw: 'edge-3.4.0', lastDiag: 'hace 2 d',
  },
];

// ---------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------
const LinkPill = ({ kind, label, value, icon }) => {
  // kind ∈ ok | warn | crit
  return (
    <div className={`fleet-link fleet-link--${kind}`}>
      <span className="fleet-link__hd">
        <i data-lucide={icon} width="12" height="12" />
        <span>{label}</span>
        <span className={`soc-dot ${kind === 'ok' ? 'soc-dot--pulse' : ''}`} />
      </span>
      <span className="fleet-link__val">{value}</span>
    </div>
  );
};

const UpsGauge = ({ ups }) => {
  const onBattery = ups.state === 'battery';
  const kind = ups.level < 40 ? 'crit' : ups.level < 80 ? 'warn' : 'ok';
  return (
    <div className="fleet-ups">
      <div className="fleet-ups__hd">
        <i data-lucide={onBattery ? 'battery-low' : 'plug-zap'} width="13" height="13" />
        <span className="fleet-ups__lbl">{onBattery ? 'EN BATERÍA' : 'RED ELÉCTRICA'}</span>
        <span className={`fleet-ups__pct fleet-ups__pct--${kind}`}>{ups.level}%</span>
      </div>
      <div className="fleet-ups__bar">
        <div className={`fleet-ups__fill fleet-ups__fill--${kind}`} style={{ width: `${ups.level}%` }} />
      </div>
      <div className="fleet-ups__ft">
        <span className="soc-meta" style={{ fontSize: 10 }}>RESPALDO</span>
        <span className="fleet-ups__autonomy">{ups.autonomy} restantes</span>
      </div>
    </div>
  );
};

const RelayGrid = ({ relays }) => (
  <div className="fleet-relays">
    {relays.map(r => {
      const kind = r.state === 'armed' ? 'ok' : r.state === 'fault' ? 'crit' : 'warn';
      const lbl = r.state === 'armed' ? 'ARMADO'
                : r.state === 'fault' ? 'FALLA'
                : 'S/D';
      return (
        <div key={r.id} className={`fleet-relay fleet-relay--${kind}`}>
          <span className="fleet-relay__id">{r.id}</span>
          <span className="fleet-relay__label">{r.label}</span>
          <span className="fleet-relay__state">{lbl}</span>
        </div>
      );
    })}
  </div>
);

const SiteCard = ({ site }) => {
  const [diagState, setDiagState] = React.useState('idle'); // idle | running | done
  const [progress, setProgress] = React.useState(0);

  const runDiag = () => {
    if (diagState !== 'idle') return;
    setDiagState('running'); setProgress(0);
    let p = 0;
    const t = setInterval(() => {
      p += 8 + Math.random() * 6;
      if (p >= 100) {
        clearInterval(t);
        setProgress(100);
        setDiagState('done');
        setTimeout(() => { setDiagState('idle'); setProgress(0); }, 2200);
      } else {
        setProgress(p);
      }
    }, 250);
  };

  const overall =
    site.mqtt === 'crit' || site.seedlink === 'crit' ? 'crit'
    : site.mqtt === 'warn' || site.seedlink === 'warn' || site.ups.level < 80 || site.relays.some(r => r.state === 'fault') ? 'warn'
    : 'ok';

  return (
    <article className={`fleet-card fleet-card--${overall}`}>
      <header className="fleet-card__hd">
        <div>
          <div className="fleet-card__name">{site.name}</div>
          <div className="fleet-card__loc">
            <i data-lucide="map-pin" width="11" height="11" />
            {site.location} · <span className="fleet-card__tenant">{site.tenant}</span>
          </div>
        </div>
        <div className="fleet-card__id">
          <span className={`soc-pill soc-pill--${overall === 'ok' ? 'ok' : overall === 'warn' ? 'warn' : 'crit'}`}>
            <span className="soc-dot" /> {overall === 'ok' ? 'OPERATIVO' : overall === 'warn' ? 'DEGRADADO' : 'SIN ENLACE'}
          </span>
          <span className="fleet-card__sid">{site.id}</span>
        </div>
      </header>

      <div className="fleet-card__links">
        <LinkPill
          kind={site.mqtt}
          label="MQTT BROKER"
          icon="radio"
          value={site.mqtt === 'crit' ? site.mqttLatency : `↔ ${site.mqttLatency}`}
        />
        <LinkPill
          kind={site.seedlink}
          label="SEEDLINK · RS4D"
          icon="activity"
          value={site.seedlink === 'crit' ? site.seedlinkLag : `lag ${site.seedlinkLag}`}
        />
      </div>

      <UpsGauge ups={site.ups} />

      <div className="fleet-card__section">
        <div className="fleet-card__sectionhd">
          <i data-lucide="toggle-right" width="12" height="12" />
          <span>ACTUADORES LOCALES · BACnet/IP</span>
        </div>
        <RelayGrid relays={site.relays} />
      </div>

      <footer className="fleet-card__ft">
        <div className="fleet-card__meta">
          <span><i data-lucide="cpu" width="11" height="11" /> {site.fw}</span>
          <span className="tk-sep">·</span>
          <span><i data-lucide="clock" width="11" height="11" /> diag {site.lastDiag}</span>
        </div>
        <button
          className={`fleet-card__diag ${diagState !== 'idle' ? `fleet-card__diag--${diagState}` : ''}`}
          onClick={runDiag}
          disabled={diagState !== 'idle' || overall === 'crit'}
        >
          {diagState === 'idle'    && (<><i data-lucide="zap" width="13" height="13" /> AUTODIAGNÓSTICO SILENCIOSO</>)}
          {diagState === 'running' && (<><i data-lucide="loader" width="13" height="13" /> EJECUTANDO · {progress.toFixed(0)}%</>)}
          {diagState === 'done'    && (<><i data-lucide="check-circle-2" width="13" height="13" /> COMPLETADO · OK</>)}
          {diagState === 'running' && (
            <span className="fleet-card__diag-bar" style={{ width: `${progress}%` }} />
          )}
        </button>
      </footer>
    </article>
  );
};

// ---------------------------------------------------------------------
// Tab root
// ---------------------------------------------------------------------
const FleetEdge = () => {
  const total   = SITES.length;
  const healthy = SITES.filter(s => s.mqtt === 'ok' && s.seedlink === 'ok' && s.ups.level >= 80 && !s.relays.some(r => r.state === 'fault')).length;
  const warns   = SITES.filter(s => (s.mqtt === 'warn' || s.seedlink === 'warn' || s.ups.level < 80 || s.relays.some(r => r.state === 'fault'))
                                    && s.mqtt !== 'crit' && s.seedlink !== 'crit').length;
  const offline = SITES.filter(s => s.mqtt === 'crit' || s.seedlink === 'crit').length;

  return (
    <section className="fleet" data-screen-label="02 Flota Edge">
      <header className="fleet__hd">
        <div>
          <span className="soc-meta">MANTENIMIENTO · CAMPO</span>
          <h1 className="fleet__title">Flota Edge y Estado de Gabinetes</h1>
          <p className="fleet__sub">
            Inventario de gateways industriales TAKAB · enlace MQTT/SeedLink, UPS, actuadores BACnet/IP.
          </p>
        </div>
        <div className="fleet__kpis">
          <div className="fleet__kpi">
            <span className="fleet__kpi-val">{total}</span>
            <span className="fleet__kpi-lbl">GABINETES</span>
          </div>
          <div className="fleet__kpi fleet__kpi--ok">
            <span className="fleet__kpi-val">{healthy}</span>
            <span className="fleet__kpi-lbl">OPERATIVOS</span>
          </div>
          <div className="fleet__kpi fleet__kpi--warn">
            <span className="fleet__kpi-val">{warns}</span>
            <span className="fleet__kpi-lbl">DEGRADADOS</span>
          </div>
          <div className="fleet__kpi fleet__kpi--crit">
            <span className="fleet__kpi-val">{offline}</span>
            <span className="fleet__kpi-lbl">SIN ENLACE</span>
          </div>
        </div>
      </header>

      <div className="fleet__grid">
        {SITES.map(s => <SiteCard key={s.id} site={s} />)}
      </div>
    </section>
  );
};

window.FleetEdge = FleetEdge;
