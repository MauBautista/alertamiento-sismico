// jsx/tabs/TriageHistory.jsx
// Tab 3 — Triage Estructural e Historial
// Post-event analytical workbench for Civil Protection / compliance.
// Wire-up:
//   Queries `events` aggregate via GraphQL with filter facets.
//   Per-event detail joins `stations_activated` (the 3-node rule trace),
//   PGA/PGV/duration features, and downloadable miniSEED bundles signed
//   with the SOC's HSM key for chain-of-custody.

const EVENTS = [
  { id: 'EVT-20260510-0843', dt: '10/MAY/2026 · 10:41 CST', mag: 6.8, depth: 32, epicenter: 'Puebla', pga: 0.150, pgv: 11.8, dur: 42, sev: 'crit', sites: 4, dictamen: 'NO HABITAR · INSPECCIÓN', operator: 'M. Rodríguez' },
  { id: 'EVT-20260428-1601', dt: '28/ABR/2026 · 16:01 CST', mag: 5.2, depth: 41, epicenter: 'Tehuacán', pga: 0.045, pgv: 3.2, dur: 28, sev: 'warn', sites: 2, dictamen: 'HABITAR · MONITOREO', operator: 'J. López' },
  { id: 'EVT-20260415-0922', dt: '15/ABR/2026 · 09:22 CST', mag: 4.4, depth: 18, epicenter: 'Atlixco', pga: 0.022, pgv: 1.6, dur: 19, sev: 'ok',   sites: 1, dictamen: 'OPERACIÓN NORMAL',   operator: 'M. Rodríguez' },
  { id: 'EVT-20260322-2245', dt: '22/MAR/2026 · 22:45 CST', mag: 5.8, depth: 26, epicenter: 'Tezuitlán', pga: 0.078, pgv: 6.4, dur: 35, sev: 'warn', sites: 3, dictamen: 'HABITAR · MONITOREO', operator: 'J. López' },
  { id: 'EVT-20260218-0511', dt: '18/FEB/2026 · 05:11 CST', mag: 4.1, depth: 22, epicenter: 'Acatlán', pga: 0.014, pgv: 0.9, dur: 14, sev: 'ok',   sites: 0, dictamen: 'OPERACIÓN NORMAL',   operator: 'M. Rodríguez' },
  { id: 'EVT-20260117-1733', dt: '17/ENE/2026 · 17:33 CST', mag: 6.1, depth: 38, epicenter: 'Puebla',   pga: 0.092, pgv: 7.9, dur: 51, sev: 'warn', sites: 3, dictamen: 'HABITAR · MONITOREO', operator: 'M. Rodríguez' },
  { id: 'EVT-20251204-1108', dt: '04/DIC/2025 · 11:08 CST', mag: 4.6, depth: 28, epicenter: 'Cholula', pga: 0.031, pgv: 2.1, dur: 22, sev: 'ok',   sites: 1, dictamen: 'OPERACIÓN NORMAL',   operator: 'J. López' },
  { id: 'EVT-20251119-1959', dt: '19/NOV/2025 · 19:59 CST', mag: 7.1, depth: 45, epicenter: 'Oaxaca',  pga: 0.182, pgv: 14.3, dur: 64, sev: 'crit', sites: 6, dictamen: 'NO HABITAR · INSPECCIÓN', operator: 'M. Rodríguez' },
];

const SEV_LABEL = { crit: 'CRÍTICO', warn: 'MODERADO', ok: 'LEVE' };

// Mini event waveform (deterministic per magnitude — just a stylised trace)
const MiniWaveform = ({ mag, dur }) => {
  const path = React.useMemo(() => {
    const W = 320, H = 60, N = 160;
    const env = Math.min(1, mag / 8);
    const pts = [];
    for (let i = 0; i < N; i++) {
      const x = (i / (N - 1)) * W;
      // sin-blended envelope, peak around 30% then decay
      const t = i / N;
      const wave =
        Math.sin(i * 0.45 + mag) * 18 * env +
        Math.sin(i * 1.21) * 10 * env +
        Math.sin(i * 0.13) * 8 * env;
      const e = t < 0.25 ? t / 0.25 : Math.max(0.1, 1 - (t - 0.25) / 0.85);
      const y = H / 2 + wave * e;
      pts.push(`${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`);
    }
    return pts.join(' ');
  }, [mag, dur]);
  return (
    <svg viewBox="0 0 320 60" className="triage-detail__waveform" preserveAspectRatio="none">
      <line x1="0" y1="30" x2="320" y2="30" stroke="rgba(0,191,255,0.10)" strokeWidth="1" strokeDasharray="2 3" />
      <path d={path} stroke="#00BFFF" strokeWidth="1.3" fill="none" />
    </svg>
  );
};

const TriageHistory = () => {
  const [sel, setSel] = React.useState(EVENTS[0]);
  const [filters, setFilters] = React.useState({ q: '', sev: 'all', range: '90d' });

  const filtered = EVENTS.filter(e => {
    if (filters.sev !== 'all' && e.sev !== filters.sev) return false;
    if (filters.q && !(`${e.epicenter} ${e.id}`.toLowerCase().includes(filters.q.toLowerCase()))) return false;
    return true;
  });

  return (
    <section className="triage" data-screen-label="03 Triage Estructural">
      <header className="triage__hd">
        <div>
          <span className="soc-meta">PROTECCIÓN CIVIL · CUMPLIMIENTO NOM-003-SCT</span>
          <h1 className="triage__title">Triage Estructural e Historial</h1>
        </div>
        <div className="triage__filters">
          <div className="triage__search">
            <i data-lucide="search" width="14" height="14" />
            <input
              type="text"
              placeholder="Buscar por epicentro o EVENT_ID…"
              value={filters.q}
              onChange={e => setFilters(f => ({ ...f, q: e.target.value }))}
            />
          </div>
          <div className="triage__segment">
            {[
              { id: 'all',  lbl: 'TODOS' },
              { id: 'crit', lbl: 'CRÍTICOS' },
              { id: 'warn', lbl: 'MODERADOS' },
              { id: 'ok',   lbl: 'LEVES' },
            ].map(o => (
              <button
                key={o.id}
                className={`triage__seg-btn${filters.sev === o.id ? ' is-active' : ''}`}
                onClick={() => setFilters(f => ({ ...f, sev: o.id }))}
              >
                {o.lbl}
              </button>
            ))}
          </div>
          <select
            className="soc-select"
            value={filters.range}
            onChange={e => setFilters(f => ({ ...f, range: e.target.value }))}
          >
            <option value="7d">ÚLT. 7 DÍAS</option>
            <option value="30d">ÚLT. 30 DÍAS</option>
            <option value="90d">ÚLT. 90 DÍAS</option>
            <option value="1y">ÚLT. AÑO</option>
          </select>
        </div>
      </header>

      <div className="triage__grid">
        {/* ===================== TABLE ===================== */}
        <div className="triage__tablewrap">
          <div className="triage__tablehd">
            <span className="soc-meta">{filtered.length} EVENTOS · ORDENADOS POR FECHA</span>
            <span className="soc-meta" style={{ color: 'var(--tk-cyan)' }}>
              <i data-lucide="download" width="11" height="11" /> EXPORTAR LOTE
            </span>
          </div>
          <table className="soc-table triage-table">
            <thead>
              <tr>
                <th style={{ width: '22%' }}>Fecha · ID</th>
                <th style={{ width: '8%' }}>Mag</th>
                <th style={{ width: '14%' }}>Epicentro</th>
                <th style={{ width: '10%' }}>PGA</th>
                <th style={{ width: '12%' }}>Severidad</th>
                <th style={{ width: '8%' }}>Sitios</th>
                <th style={{ width: '18%' }}>Dictamen</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(e => (
                <tr
                  key={e.id}
                  className={sel?.id === e.id ? 'is-selected' : ''}
                  onClick={() => setSel(e)}
                >
                  <td>
                    <div className="triage-table__dt">{e.dt}</div>
                    <div className="triage-table__id">{e.id}</div>
                  </td>
                  <td><span className="soc-mono triage-table__mag">M&nbsp;{e.mag.toFixed(1)}</span></td>
                  <td>{e.epicenter}</td>
                  <td className={`soc-mono ${e.sev !== 'ok' ? 'soc-table__pga' : ''}`}>{e.pga.toFixed(3)}g</td>
                  <td>
                    <span className={`soc-sev soc-sev--${e.sev === 'crit' ? 'red' : e.sev === 'warn' ? 'warn' : 'ok'}`}>
                      {SEV_LABEL[e.sev]}
                    </span>
                  </td>
                  <td className="soc-mono">{e.sites}/8</td>
                  <td className="triage-table__dictamen">{e.dictamen}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ===================== DETAIL ===================== */}
        {sel && (
          <aside className="triage-detail">
            <header className="triage-detail__hd">
              <span className="soc-meta">DICTAMEN AUTOMÁTICO PRELIMINAR</span>
              <h2 className="triage-detail__title">M&nbsp;{sel.mag.toFixed(1)} · {sel.epicenter}</h2>
              <div className="triage-detail__id">{sel.id} · {sel.dt}</div>
            </header>

            <div className={`triage-detail__verdict triage-detail__verdict--${sel.sev}`}>
              <i data-lucide={sel.sev === 'crit' ? 'alert-octagon' : sel.sev === 'warn' ? 'alert-triangle' : 'check-circle-2'} width="18" height="18" />
              <div>
                <div className="triage-detail__verdict-lbl">VEREDICTO</div>
                <div className="triage-detail__verdict-val">{sel.dictamen}</div>
              </div>
            </div>

            <div className="soc-card">
              <div className="soc-card__hd">
                <div>
                  <div>Traza Sintética · Estación Activadora</div>
                  <div className="soc-card__sub">CHL-A · CANAL Z · 200 Hz</div>
                </div>
                <span className="soc-bacnet">⬢ miniSEED</span>
              </div>
              <MiniWaveform mag={sel.mag} dur={sel.dur} />
            </div>

            <div className="triage-detail__metrics">
              <div className="triage-metric">
                <div className="triage-metric__lbl">PGA MÁX</div>
                <div className="triage-metric__val">{sel.pga.toFixed(3)}<span className="unit">g</span></div>
              </div>
              <div className="triage-metric">
                <div className="triage-metric__lbl">PGV MÁX</div>
                <div className="triage-metric__val">{sel.pgv.toFixed(1)}<span className="unit">cm/s</span></div>
              </div>
              <div className="triage-metric">
                <div className="triage-metric__lbl">DURACIÓN</div>
                <div className="triage-metric__val">{sel.dur}<span className="unit">s</span></div>
              </div>
              <div className="triage-metric">
                <div className="triage-metric__lbl">PROFUNDIDAD</div>
                <div className="triage-metric__val">{sel.depth}<span className="unit">km</span></div>
              </div>
            </div>

            <div className="soc-card">
              <div className="soc-card__hd">
                <div>
                  <div>Regla &laquo;3 Nodos&raquo; · Estaciones Activadas</div>
                  <div className="soc-card__sub">CORROBORACIÓN MULTI-SENSOR (anti-falso-positivo)</div>
                </div>
                <span className="soc-pill soc-pill--ok" style={{ fontSize: 9 }}>
                  <i data-lucide="check" width="11" height="11" /> CUÓRUM CUMPLIDO
                </span>
              </div>
              <div className="triage-nodes">
                {['CHL-A', 'PUE-01', 'PUE-02', 'ATX-BG', 'HGP-1', 'TEH-CD'].slice(0, Math.max(3, sel.sites)).map((s, i) => (
                  <div key={s} className={`triage-node ${i < 3 ? 'triage-node--active' : 'triage-node--idle'}`}>
                    <span className="soc-dot" />
                    <span className="triage-node__id">{s}</span>
                    <span className="triage-node__t soc-mono">+{(0.18 + i * 0.21).toFixed(2)}s</span>
                  </div>
                ))}
              </div>
            </div>

            <footer className="triage-detail__actions">
              <button className="soc-btn soc-btn--secondary">
                <i data-lucide="file-down" width="13" height="13" /> EXPORTAR miniSEED
              </button>
              <button className="soc-btn soc-btn--primary">
                <i data-lucide="printer" width="13" height="13" /> DICTAMEN PDF
              </button>
            </footer>

            <div className="triage-detail__chain">
              <i data-lucide="shield-check" width="11" height="11" />
              CADENA DE CUSTODIA · Firmado HSM · op: {sel.operator}
            </div>
          </aside>
        )}
      </div>
    </section>
  );
};

window.TriageHistory = TriageHistory;
