// jsx/tabs/MultiTenantMatrix.jsx
// Tab 4 — Matriz Multi-Tenant y Umbrales
// Tenant-isolation visualizer + per-facility threshold configuration.
//
// Wire-up:
//   Tenants live as `tenant_id` rows in the CRM-backed BFF; each one owns
//   N facilities. Thresholds are PUT to `takab.config.tenant.{tid}.threshold`
//   (cloud) which the gateway pulls on next config-sync (≤60s).
//   Notification channels are credentialed in Vault; the toggles here only
//   flip "use this channel as fallback for this tenant".

const TENANTS = [
  {
    id: 'TKB-001', name: 'INDUSTRIAS DEL VALLE S.A.',
    industry: 'Industrial · Química',
    isolation: 'logical',
    sites: 4, users: 12,
    facility: 'Planta Química Tipo II',
    color: '#00BFFF',
    thresholds: { pga: 0.080, pgv: 6.0 },
    channels: { api: true, whatsapp: true, sms: true, email: false },
  },
  {
    id: 'TKB-002', name: 'SECRETARÍA DE SALUD',
    industry: 'Hospitalario · Crítico',
    isolation: 'dedicated',
    sites: 6, users: 18,
    facility: 'Hospital Nivel 2',
    color: '#00E676',
    thresholds: { pga: 0.040, pgv: 3.5 },
    channels: { api: true, whatsapp: true, sms: true, email: true },
  },
  {
    id: 'TKB-003', name: 'GRUPO TAKAB',
    industry: 'Corporativo · Oficinas',
    isolation: 'logical',
    sites: 2, users: 6,
    facility: 'Edificio Tipo A',
    color: '#FFC107',
    thresholds: { pga: 0.120, pgv: 9.0 },
    channels: { api: true, whatsapp: false, sms: true, email: true },
  },
  {
    id: 'TKB-004', name: 'LOGÍSTICA NACIONAL',
    industry: 'Centro Distribución',
    isolation: 'logical',
    sites: 3, users: 9,
    facility: 'CD · Almacén Tipo III',
    color: '#FF5252',
    thresholds: { pga: 0.100, pgv: 7.5 },
    channels: { api: false, whatsapp: true, sms: true, email: false },
  },
  {
    id: 'TKB-005', name: 'AGROINDUSTRIA NORTE',
    industry: 'Agro · Procesamiento',
    isolation: 'logical',
    sites: 2, users: 4,
    facility: 'Planta Agro Tipo I',
    color: '#9B6FFF',
    thresholds: { pga: 0.140, pgv: 11.0 },
    channels: { api: true, whatsapp: true, sms: false, email: false },
  },
];

// ---------------------------------------------------------------------
// Threshold slider — labelled scale w/ unit, snaps, danger/safe zones
// ---------------------------------------------------------------------
const ThresholdSlider = ({ label, value, min, max, step, unit, hint, dangerAt, onChange }) => {
  const pct = ((value - min) / (max - min)) * 100;
  const dangerPct = ((dangerAt - min) / (max - min)) * 100;
  const zone = value >= dangerAt ? 'crit' : value >= dangerAt * 0.6 ? 'warn' : 'ok';
  return (
    <div className="mt-slider">
      <div className="mt-slider__hd">
        <span className="soc-meta">{label}</span>
        <span className={`mt-slider__val mt-slider__val--${zone}`}>
          {value.toFixed(step < 1 ? 3 : 1)}<span className="unit">{unit}</span>
        </span>
      </div>
      <div className="mt-slider__track-wrap">
        <div
          className="mt-slider__track"
          style={{
            // Three-zone background — green safe → amber caution → red trigger.
            // Stops align with the slider's danger threshold for clear visual
            // semantics: dragging past the red zone means accepting auto-trigger.
            background: `linear-gradient(to right,
              var(--tk-status-normal-15) 0%,
              var(--tk-status-normal-15) ${dangerPct * 0.6}%,
              var(--tk-status-warning-15) ${dangerPct * 0.6}%,
              var(--tk-status-warning-15) ${dangerPct}%,
              var(--tk-status-critical-15) ${dangerPct}%,
              var(--tk-status-critical-15) 100%)`,
          }}
        >
          <div className={`mt-slider__fill mt-slider__fill--${zone}`} style={{ width: `${pct}%` }} />
          <div className={`mt-slider__thumb mt-slider__thumb--${zone}`} style={{ left: `${pct}%` }} />
        </div>
        <input
          type="range"
          min={min} max={max} step={step}
          value={value}
          onChange={e => onChange?.(parseFloat(e.target.value))}
          className="mt-slider__input"
        />
      </div>
      <div className="mt-slider__scale">
        <span>{min.toFixed(step < 1 ? 2 : 1)}{unit}</span>
        <span style={{ color: 'var(--tk-status-warning)' }}>{(dangerAt * 0.6).toFixed(step < 1 ? 2 : 1)}{unit} caut.</span>
        <span style={{ color: 'var(--tk-status-critical)' }}>{dangerAt.toFixed(step < 1 ? 2 : 1)}{unit} disp.</span>
        <span>{max.toFixed(step < 1 ? 2 : 1)}{unit}</span>
      </div>
      <div className="mt-slider__hint">{hint}</div>
    </div>
  );
};

// ---------------------------------------------------------------------
// Notification channel card
// ---------------------------------------------------------------------
const ChannelCard = ({ id, label, sub, icon, enabled, onToggle }) => (
  <button
    className={`mt-channel${enabled ? ' is-on' : ''}`}
    onClick={() => onToggle?.(id)}
    aria-pressed={enabled}
  >
    <span className="mt-channel__icon"><i data-lucide={icon} width="16" height="16" /></span>
    <span className="mt-channel__body">
      <span className="mt-channel__label">{label}</span>
      <span className="mt-channel__sub">{sub}</span>
    </span>
    <span className={`mt-channel__switch${enabled ? ' is-on' : ''}`}>
      <span className="mt-channel__knob" />
    </span>
  </button>
);

// ---------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------
const MultiTenantMatrix = () => {
  const [tenants, setTenants] = React.useState(TENANTS);
  const [selId, setSelId] = React.useState(TENANTS[0].id);
  const sel = tenants.find(t => t.id === selId);

  const updateSel = (patch) => {
    setTenants(ts => ts.map(t => t.id === selId ? { ...t, ...patch } : t));
  };
  const updateThr = (key, val) => updateSel({ thresholds: { ...sel.thresholds, [key]: val } });
  const toggleCh  = (k)         => updateSel({ channels: { ...sel.channels, [k]: !sel.channels[k] } });

  const channelsList = [
    { id: 'api',      label: 'API · Webhook',      sub: 'POST JSON con firma HMAC',          icon: 'webhook' },
    { id: 'whatsapp', label: 'WhatsApp Business',  sub: 'Plantilla aprobada · Cloud API',    icon: 'message-circle' },
    { id: 'sms',      label: 'SMS · Telcel/AT&T',  sub: 'Ruta dedicada · entrega ≤30s',      icon: 'smartphone' },
    { id: 'email',    label: 'Correo Electrónico', sub: 'SMTP-relay con DKIM/SPF',           icon: 'mail' },
  ];

  return (
    <section className="mt" data-screen-label="04 Multi-Tenant">
      <header className="mt__hd">
        <div>
          <span className="soc-meta">PLATAFORMA · ADMINISTRACIÓN</span>
          <h1 className="mt__title">Matriz Multi-Tenant y Umbrales</h1>
          <p className="mt__sub">
            Aislamiento lógico de clientes · umbrales locales por tipo de instalación · canales de respaldo.
          </p>
        </div>
        <div className="mt__legend">
          <div><span className="mt__leg-sw mt__leg-sw--ded" /> Tenant dedicado · DB aislada</div>
          <div><span className="mt__leg-sw mt__leg-sw--log" /> Tenant lógico · row-level security</div>
        </div>
      </header>

      <div className="mt__grid">
        {/* ===================== TENANT LIST ===================== */}
        <nav className="mt__list" aria-label="Tenants">
          <div className="mt__list-hd">
            <span className="soc-meta">{tenants.length} CLIENTES ACTIVOS</span>
            <button className="soc-btn soc-btn--ghost" style={{ padding: '4px 8px' }}>
              <i data-lucide="plus" width="11" height="11" /> NUEVO
            </button>
          </div>
          {tenants.map(t => (
            <button
              key={t.id}
              className={`mt-tenant${selId === t.id ? ' is-selected' : ''}`}
              onClick={() => setSelId(t.id)}
            >
              <span className="mt-tenant__swatch" style={{ background: t.color }} />
              <span className="mt-tenant__body">
                <span className="mt-tenant__name">{t.name}</span>
                <span className="mt-tenant__meta">
                  {t.industry} · {t.sites} sitios · {t.users} usuarios
                </span>
              </span>
              <span className={`mt-tenant__iso mt-tenant__iso--${t.isolation}`}>
                {t.isolation === 'dedicated' ? 'DEDICADO' : 'LÓGICO'}
              </span>
            </button>
          ))}

          <div className="mt-isolation">
            <div className="mt-isolation__hd">
              <i data-lucide="shield" width="12" height="12" />
              <span className="soc-meta">AISLAMIENTO DE DATOS</span>
            </div>
            <div className="mt-isolation__rows">
              <div className="mt-isolation__row">
                <span>Schema por tenant</span>
                <span style={{ color: 'var(--tk-status-normal)' }}>● ACTIVO</span>
              </div>
              <div className="mt-isolation__row">
                <span>Row-Level Security</span>
                <span style={{ color: 'var(--tk-status-normal)' }}>● ACTIVO</span>
              </div>
              <div className="mt-isolation__row">
                <span>Encriptación AES-256 at-rest</span>
                <span style={{ color: 'var(--tk-status-normal)' }}>● ACTIVO</span>
              </div>
              <div className="mt-isolation__row">
                <span>Llaves KMS por tenant</span>
                <span style={{ color: 'var(--tk-status-normal)' }}>● ACTIVO</span>
              </div>
            </div>
          </div>
        </nav>

        {/* ===================== TENANT DETAIL ===================== */}
        <div className="mt__detail">
          <header className="mt__detail-hd">
            <div>
              <div className="mt__detail-id">{sel.id}</div>
              <h2 className="mt__detail-name" style={{ borderLeft: `4px solid ${sel.color}`, paddingLeft: 12 }}>
                {sel.name}
              </h2>
              <div className="mt__detail-meta">
                {sel.industry} · {sel.facility} · {sel.sites} sitios · {sel.users} usuarios
              </div>
            </div>
            <span className={`soc-pill ${sel.isolation === 'dedicated' ? 'soc-pill--edge' : 'soc-pill--ok'}`}>
              <i data-lucide="shield-check" width="11" height="11" />
              {sel.isolation === 'dedicated' ? 'TENANT DEDICADO' : 'TENANT LÓGICO'}
            </span>
          </header>

          <div className="soc-card">
            <div className="soc-card__hd">
              <div>
                <div>Umbrales de Disparo Local</div>
                <div className="soc-card__sub">EDGE GATEWAY · APLICA AL TIPO &laquo;{sel.facility}&raquo;</div>
              </div>
              <span className="soc-bacnet">⬢ EDGE · LOCAL RULES</span>
            </div>
            <div className="mt-sliders">
              <ThresholdSlider
                label="PGA · Aceleración Pico del Suelo"
                value={sel.thresholds.pga}
                min={0.020} max={0.300} step={0.005}
                unit="g"
                dangerAt={0.180}
                hint="Disparo de sirena + cierre de gas. Hospitales: 0.040–0.060g · Industriales: 0.080–0.120g · Corporativos: 0.100–0.150g."
                onChange={v => updateThr('pga', v)}
              />
              <ThresholdSlider
                label="PGV · Velocidad Pico del Suelo"
                value={sel.thresholds.pgv}
                min={1.0} max={20.0} step={0.5}
                unit="cm/s"
                dangerAt={12.0}
                hint="Mejor indicador de daño estructural medio/largo plazo. Calibrar con tipología y altura del edificio."
                onChange={v => updateThr('pgv', v)}
              />
            </div>
          </div>

          <div className="soc-card">
            <div className="soc-card__hd">
              <div>
                <div>Canales de Notificación · Cascada de Respaldo</div>
                <div className="soc-card__sub">SI EL EDGE NO ALCANZA RED, LA NUBE DISPARA TODOS EN PARALELO</div>
              </div>
              <span className="soc-bacnet">⬢ FAIL-OPEN</span>
            </div>
            <div className="mt-channels">
              {channelsList.map(c => (
                <ChannelCard
                  key={c.id}
                  {...c}
                  enabled={sel.channels[c.id]}
                  onToggle={toggleCh}
                />
              ))}
            </div>
            <div className="mt-channels__cascade">
              <span className="soc-meta">CASCADA APLICADA</span>
              <span className="mt-channels__cascade-trace">
                {channelsList.filter(c => sel.channels[c.id]).map((c, i, arr) => (
                  <React.Fragment key={c.id}>
                    <span className="mt-channels__step">{i + 1}. {c.label.split(' · ')[0]}</span>
                    {i < arr.length - 1 && <i data-lucide="chevron-right" width="12" height="12" />}
                  </React.Fragment>
                ))}
                {!channelsList.some(c => sel.channels[c.id]) && (
                  <span style={{ color: 'var(--tk-status-critical)' }}>SIN CANAL · TENANT DESPROTEGIDO</span>
                )}
              </span>
            </div>
          </div>

          <footer className="mt__detail-ft">
            <span className="mt__detail-chain">
              <i data-lucide="git-commit-vertical" width="11" height="11" />
              Cambios pendientes de sync al edge · ≤60s · firmado JWT
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="soc-btn soc-btn--secondary">
                <i data-lucide="rotate-ccw" width="12" height="12" /> RESTAURAR
              </button>
              <button className="soc-btn soc-btn--primary">
                <i data-lucide="upload-cloud" width="12" height="12" /> APLICAR Y SINCRONIZAR
              </button>
            </div>
          </footer>
        </div>
      </div>
    </section>
  );
};

window.MultiTenantMatrix = MultiTenantMatrix;
