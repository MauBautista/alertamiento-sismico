// jsx/MapPanel.jsx
// Schematic GIS view — Puebla / Cholula with live propagation rings
// Real impl: Mapbox GL JS vector layer; sensor pins driven by NATS subject
// `takab.sensor.*.state`; ring radius reflects S-wave travel-time from epicenter.

const SENSORS = [
  // Cholula cluster (target plant) — sits on the western flank
  { id: 'CHL-01', x: 280, y: 360, status: 'critical', label: 'Cholula' },
  { id: 'CHL-02', x: 268, y: 380, status: 'warning' },
  { id: 'CHL-03', x: 296, y: 348, status: 'warning' },
  // Puebla metro — close to epicenter
  { id: 'PUE-01', x: 470, y: 320, status: 'normal' },
  { id: 'PUE-02', x: 504, y: 332, status: 'normal' },
  { id: 'PUE-03', x: 480, y: 360, status: 'normal' },
  { id: 'PUE-04', x: 520, y: 360, status: 'normal' },
  // Outer ring of telemetry sites
  { id: 'TEH-01', x: 710, y: 390, status: 'normal' },
  { id: 'TEZ-01', x: 410, y: 220, status: 'normal' },
  { id: 'ATX-01', x: 200, y: 250, status: 'normal' },
  { id: 'ATL-01', x: 620, y: 200, status: 'normal' },
  { id: 'ZCT-01', x: 380, y: 470, status: 'normal' },
  { id: 'CRD-01', x: 760, y: 280, status: 'normal' },
  { id: 'TEC-01', x: 600, y: 470, status: 'normal' },
  { id: 'XAL-01', x: 820, y: 360, status: 'normal' },
];

const STATUS_COLOR = {
  normal:   '#00E676',
  warning:  '#FFC107',
  critical: '#FF5252',
};

// Epicenter location in viewBox (Puebla city)
const EPI = { x: 540, y: 320 };

const MapPanel = ({ critical = true, onSelectSite }) => {
  // Animated "now" used to drive S-wave propagation rings.
  // Linear easing — design system says data motion is never bounced.
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => {
    let raf;
    const start = performance.now();
    const loop = (t) => {
      setTick((t - start) / 1000);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  // Three concentric pulses, 4s period, staggered by 1.3s
  const pulses = [0, 1.3, 2.6].map(offset => {
    const phase = ((tick - offset) % 4) / 4; // 0..1
    if (phase < 0) return null;
    return { r: 30 + phase * 240, opacity: 1 - phase };
  });

  return (
    <div className="soc-map">
      <svg viewBox="0 0 900 540" preserveAspectRatio="xMidYMid slice" className="soc-map__svg" role="img" aria-label="Sensor map — Puebla / Cholula">
        <defs>
          {/* Hatched pattern for high-relief mountains */}
          <pattern id="relief" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(35)">
            <line x1="0" y1="0" x2="0" y2="6" stroke="#1f3a5a" strokeWidth="0.6" />
          </pattern>
          {/* Crosshair pattern for the tile-grid feel */}
          <pattern id="grid" patternUnits="userSpaceOnUse" width="60" height="60">
            <path d="M 60 0 L 0 0 0 60" fill="none" stroke="rgba(0,191,255,0.04)" strokeWidth="0.5" />
          </pattern>
        </defs>

        {/* Base water tone */}
        <rect width="900" height="540" fill="#0d2034" />
        <rect width="900" height="540" fill="url(#grid)" />

        {/* Land mass — Puebla state silhouette (abstracted) */}
        <path
          d="M 80 240 Q 130 170 240 180 Q 320 188 380 160 Q 460 130 540 165 Q 600 195 680 175 Q 760 158 830 195
             Q 870 235 855 320 Q 830 410 760 450 Q 670 490 580 470 Q 480 450 390 460 Q 290 470 210 430 Q 110 390 85 320 Z"
          fill="#173352" stroke="#2f5277" strokeWidth="1.2"
        />

        {/* Relief / mountain bands */}
        <path
          d="M 200 320 Q 280 280 380 300 Q 460 320 540 300 Q 620 280 700 310"
          fill="none" stroke="url(#relief)" strokeWidth="22" opacity="0.6"
        />

        {/* Internal state borders (dashed) */}
        <g stroke="#2c4a6c" strokeWidth="1" fill="none" strokeDasharray="3 4" opacity="0.65">
          <path d="M 200 260 Q 280 280 380 260 Q 460 240 540 260" />
          <path d="M 380 230 Q 460 260 540 240 Q 620 220 700 250" />
          <path d="M 240 380 Q 320 360 410 380 Q 500 400 580 380" />
        </g>

        {/* Place labels */}
        <g fontFamily="Geist, sans-serif" fontSize="11" fill="#7f93ad" letterSpacing="0.04em">
          <text x="180" y="200">Tlaxcala</text>
          <text x="420" y="200">Tezuitlán</text>
          <text x="600" y="180">Atlixco</text>
          <text x="700" y="170">Teziutlán</text>
          <text x="290" y="510">Acatlán</text>
          <text x="600" y="510">Tehuacán</text>
          <text x="780" y="350">Xalapa</text>
          <text x="100" y="300" fill="#9fb2c9">Edo. de Puebla</text>
        </g>

        {/* === LIVE PROPAGATION RINGS ============================ */}
        {critical && pulses.map((p, i) =>
          p && (
            <circle
              key={i}
              cx={EPI.x} cy={EPI.y} r={p.r}
              fill="none"
              stroke={p.r < 80 ? '#FF5252' : p.r < 160 ? '#FFC107' : '#FFE066'}
              strokeWidth="1.4"
              opacity={p.opacity * 0.7}
            />
          )
        )}
        {/* Static intensity bands behind the live pulses */}
        {critical && (
          <g>
            <circle cx={EPI.x} cy={EPI.y} r="55"  fill="rgba(255,82,82,0.16)" stroke="#FF5252" strokeWidth="1.4" />
            <circle cx={EPI.x} cy={EPI.y} r="100" fill="rgba(255,193,7,0.07)" stroke="#FFC107" strokeWidth="1" opacity="0.7" />
            <circle cx={EPI.x} cy={EPI.y} r="150" fill="none" stroke="#FFE066" strokeWidth="0.8" opacity="0.45" strokeDasharray="3 3" />
          </g>
        )}

        {/* === EPICENTER MARKER ================================== */}
        {critical && (
          <g>
            <line x1={EPI.x - 12} y1={EPI.y} x2={EPI.x + 12} y2={EPI.y} stroke="#fff" strokeWidth="1.4" />
            <line x1={EPI.x} y1={EPI.y - 12} x2={EPI.x} y2={EPI.y + 12} stroke="#fff" strokeWidth="1.4" />
            <circle cx={EPI.x} cy={EPI.y} r="5" fill="#FF5252" stroke="#fff" strokeWidth="1.5" />
            <rect x={EPI.x - 56} y={EPI.y - 38} width="112" height="22" rx="3" fill="#7B1818" stroke="#FF5252" strokeWidth="1" />
            <text x={EPI.x} y={EPI.y - 23} textAnchor="middle" fontFamily="Geist" fontSize="11" fontWeight="700" letterSpacing="0.10em" fill="#fff">CRITICAL ALERT</text>
            <text x={EPI.x} y={EPI.y + 30} textAnchor="middle" fontFamily="Geist" fontSize="13" fontWeight="600" fill="#fff">Puebla</text>
            <text x={EPI.x} y={EPI.y + 46} textAnchor="middle" fontFamily="JetBrains Mono" fontSize="10" fill="#FFE066">19.0414°N · 98.2063°W</text>
          </g>
        )}

        {/* === SITE CONNECTION LINE (epicenter → target) ========= */}
        {critical && (
          <line
            x1={EPI.x} y1={EPI.y}
            x2={SENSORS[0].x} y2={SENSORS[0].y}
            stroke="#FF5252" strokeWidth="1" strokeDasharray="2 4" opacity="0.55"
          />
        )}

        {/* === SENSOR PINS ====================================== */}
        {SENSORS.map(p => (
          <g key={p.id} onClick={() => onSelectSite?.(p)} style={{ cursor: 'pointer' }}>
            <circle cx={p.x} cy={p.y} r={p.status === 'critical' ? 16 : 12}
                    fill={STATUS_COLOR[p.status]} opacity="0.18" />
            <circle cx={p.x} cy={p.y} r={p.status === 'critical' ? 7 : 5}
                    fill={STATUS_COLOR[p.status]} stroke="#0d2034" strokeWidth="1.5" />
            {p.status === 'critical' && (
              <circle cx={p.x} cy={p.y} r="11" fill="none"
                      stroke="#FF5252" strokeWidth="1.2"
                      style={{ animation: 'soc-pulse 1.6s linear infinite', transformOrigin: `${p.x}px ${p.y}px` }} />
            )}
            {p.label && (
              <text x={p.x} y={p.y + 22} textAnchor="middle"
                    fontFamily="Geist" fontSize="10" fontWeight="600" fill="#fff">
                {p.label}
              </text>
            )}
          </g>
        ))}
      </svg>

      {/* Map UI overlays */}
      <button className="soc-map__expand" aria-label="Expandir mapa">
        <i data-lucide="maximize-2" width="14" height="14" />
      </button>

      <div className="soc-map__legend">
        <div className="soc-map__legend-title">INTENSIDAD MMI</div>
        <div className="soc-map__legend-row"><span className="soc-map__sw" style={{ background: '#7B1818' }} /> Severa</div>
        <div className="soc-map__legend-row"><span className="soc-map__sw" style={{ background: '#FF5252' }} /> Alta</div>
        <div className="soc-map__legend-row"><span className="soc-map__sw" style={{ background: '#FFC107' }} /> Moderada</div>
        <div className="soc-map__legend-row"><span className="soc-map__sw" style={{ background: '#FFE066' }} /> Leve</div>
        <div className="soc-map__legend-row"><span className="soc-map__sw" style={{ background: '#00E676' }} /> Sitios OK</div>
      </div>

      <div className="soc-map__attribution">
        <span>◐ mapbox · vector tiles</span>
        <span>Map data © 2026 OSM · Powered by Raspberry Shake® RS4D</span>
      </div>
    </div>
  );
};

window.MapPanel = MapPanel;
