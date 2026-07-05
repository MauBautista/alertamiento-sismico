// jsx/IncidentTable.jsx
// Bottom table — open incidents queue + critical operator action bar
// Wire-up note: rows are GraphQL `subscription openIncidents` from the BFF;
// CONFIRMAR ACUSE writes to NATS subject `takab.event.{id}.acknowledge`
// with operator JWT. NEVER acknowledge for them — force human signoff.

const ROWS = [
  { site: 'Planta Cholula · Edificio A', sev: 'crit', coords: '19.0633°N · 98.3014°W', pga: '0.150g', time: '10:41:30 UTC', age: 'T+02s' },
  { site: 'Planta Cholula · Edificio B', sev: 'warn', coords: '19.0628°N · 98.3019°W', pga: '0.082g', time: '10:41:31 UTC', age: 'T+03s' },
  { site: 'Bodega Atlixco',              sev: 'ok',   coords: '18.9072°N · 98.4364°W', pga: '0.014g', time: '10:41:34 UTC', age: 'T+06s' },
  { site: 'CD Tehuacán',                 sev: 'ok',   coords: '18.4621°N · 97.3925°W', pga: '0.008g', time: '10:41:36 UTC', age: 'T+08s' },
];

const SevTag = ({ sev }) => {
  const map = {
    crit: { cls: 'soc-sev soc-sev--red',  label: 'CRÍTICO',  icon: 'alert-octagon' },
    warn: { cls: 'soc-sev soc-sev--warn', label: 'ADVERTENCIA', icon: 'alert-triangle' },
    ok:   { cls: 'soc-sev soc-sev--ok',   label: 'NORMAL',   icon: 'check-circle-2' },
  }[sev];
  return (
    <span className={map.cls}>
      <i data-lucide={map.icon} width="11" height="11" />
      {map.label}
    </span>
  );
};

const IncidentTable = ({ onConfirm }) => {
  return (
    <section className="soc-incidents" data-screen-label="Incidents queue">
      <header className="soc-incidents__hd">
        <h3 className="soc-incidents__title">
          <i data-lucide="list" width="16" height="16" style={{ color: 'var(--tk-cyan)' }} />
          Incidentes Abiertos
          <span className="soc-incidents__count">{ROWS.length} ACTIVOS</span>
        </h3>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', color: 'var(--tk-fg-3)', fontSize: 11, fontFamily: 'var(--tk-font-mono)', letterSpacing: '0.04em' }}>
          <span>SUBSCRIPTION · GraphQL</span>
          <span style={{ color: 'var(--tk-status-normal)' }}>● LIVE</span>
        </div>
      </header>

      <table className="soc-table">
        <thead>
          <tr>
            <th style={{ width: '26%' }}>Sitio</th>
            <th style={{ width: '14%' }}>Severidad</th>
            <th style={{ width: '24%' }}>Coordenadas</th>
            <th style={{ width: '10%' }}>PGA</th>
            <th style={{ width: '14%' }}>Hora UTC</th>
            <th style={{ width: '12%' }}>Edad</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r, i) => (
            <tr key={i}>
              <td className="soc-table__site">
                <span className="soc-dot" style={{
                  color: r.sev === 'crit' ? 'var(--tk-status-critical)'
                       : r.sev === 'warn' ? 'var(--tk-status-warning)'
                       : 'var(--tk-status-normal)'
                }} />
                {r.site}
              </td>
              <td><SevTag sev={r.sev} /></td>
              <td className="soc-mono" style={{ color: 'var(--tk-fg-2)' }}>{r.coords}</td>
              <td className={`soc-mono ${r.sev !== 'ok' ? 'soc-table__pga' : ''}`}>{r.pga}</td>
              <td className="soc-mono">{r.time}</td>
              <td className="soc-mono" style={{ color: 'var(--tk-fg-3)' }}>{r.age}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <footer className="soc-incidents__ft">
        <div className="soc-incidents__operator">
          <span className="soc-meta">Operador</span>
          <select className="soc-select" defaultValue="MR">
            <option value="MR">M. RODRÍGUEZ · TURNO A</option>
            <option value="JL">J. LÓPEZ · TURNO B</option>
          </select>
          <span className="soc-pill soc-pill--ok" style={{ fontSize: 9 }}>
            <i data-lucide="user-check" width="11" height="11" /> AUTH · MFA
          </span>
        </div>
        <div className="soc-incidents__actions">
          <ConfirmButton
            icon="map-pin"
            label="REUBICAR EPICENTRO"
            armedLabel="CONFIRMAR REUBICACIÓN"
            variant="secondary"
          />
          <ConfirmButton
            icon="file-search"
            label="SOLICITAR DICTAMEN TÉCNICO"
            armedLabel="CONFIRMAR SOLICITUD"
            variant="secondary"
          />
          <ConfirmButton
            icon="check-circle-2"
            label="CONFIRMAR ACUSE"
            armedLabel="CLIC DE NUEVO PARA ACUSAR"
            variant="primary"
            onConfirm={onConfirm}
          />
        </div>
      </footer>
    </section>
  );
};

window.IncidentTable = IncidentTable;
