// jsx/DetailPanel.jsx
// Right-column site detail — Sismograma + BMS + CCTV
// Wire-up notes:
//   * Waveform pulled from MQTT subject `takab.sensor.{site}.rs4d.stream` (200 Hz Z-axis).
//   * BMS row state pulled from BACnet/IP scrape via edge gateway, surfaced on
//     NATS subject `takab.actuator.{site}.{point}`. Writes are NEVER auto-issued
//     from the cloud — only acknowledged here.
//   * CCTV thumbnail = ONVIF Profile S snapshot (still). Live RTSP over WebRTC
//     in production; here a deterministic SVG placeholder.

const Sismograma = ({ active = true }) => {
  // Animated SVG waveform — synthesized as an array of points so we can render
  // realistic shaking (high-amplitude clipping + secondary noise) without canvas.
  // Fixed buffer length, scrolling left as new samples come in.
  const WIDTH = 600;
  const HEIGHT = 80;
  const N = 200;
  const [samples, setSamples] = React.useState(() => {
    // Pre-roll: ambient micro-tremor before P-wave
    return Array.from({ length: N }, () => 40 + (Math.random() - 0.5) * 4);
  });
  const tRef = React.useRef(0);

  React.useEffect(() => {
    let raf;
    const loop = () => {
      tRef.current += 1;
      const t = tRef.current;

      setSamples(prev => {
        // Envelope models the strong-motion event: ramp into clipping, decay
        const eventPos = (t % 600);            // 600 frames cycle = ~10s @ 60fps
        let env;
        if (eventPos < 60)        env = 0.05;            // pre-event ambient
        else if (eventPos < 90)   env = (eventPos - 60) / 30 * 0.8 + 0.2; // ramp
        else if (eventPos < 240)  env = 1.0 + Math.sin(eventPos * 0.18) * 0.15; // strong shaking
        else if (eventPos < 480)  env = Math.max(0.15, 1.0 * Math.exp(-(eventPos - 240) / 90));
        else                      env = 0.05; // back to ambient

        const gain = active ? env : 0.04;
        // Mix of frequencies — high-frequency S-wave + low-frequency body wave
        const sample = 40
          + Math.sin(t * 0.41) * 24 * gain
          + Math.sin(t * 1.13) * 16 * gain
          + Math.sin(t * 0.21) * 14 * gain
          + (Math.random() - 0.5) * 30 * gain;
        // Hard clipping at the canvas extents — visual cue of saturation
        const clipped = Math.max(4, Math.min(HEIGHT - 4, sample));
        return [...prev.slice(1), clipped];
      });
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active]);

  const path = React.useMemo(() => {
    const step = WIDTH / (N - 1);
    return samples.map((y, i) => `${i === 0 ? 'M' : 'L'} ${(i * step).toFixed(1)} ${y.toFixed(1)}`).join(' ');
  }, [samples]);

  // Instantaneous PGA / PGV derived from the buffer
  const peak = Math.max(...samples.map(s => Math.abs(s - 40)));
  const pga = (peak / 40 * 0.30).toFixed(3); // mapped 0..0.30g
  const pgv = (peak / 40 * 12.0).toFixed(1); // mapped 0..12.0 cm/s (SI seismology unit)

  return (
    <>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="soc-sismograma" preserveAspectRatio="none">
        {/* Center reference line */}
        <line x1="0" y1={HEIGHT / 2} x2={WIDTH} y2={HEIGHT / 2} stroke="rgba(0,191,255,0.10)" strokeWidth="1" strokeDasharray="2 3" />
        {/* Major gridlines */}
        <line x1="0" y1="20" x2={WIDTH} y2="20" stroke="rgba(0,191,255,0.05)" strokeWidth="1" />
        <line x1="0" y1="60" x2={WIDTH} y2="60" stroke="rgba(0,191,255,0.05)" strokeWidth="1" />
        {/* Waveform */}
        <path d={path} stroke="#00BFFF" strokeWidth="1.4" fill="none" />
        {/* Trailing leading edge dot */}
        <circle cx={WIDTH - 1} cy={samples[samples.length - 1]} r="2.4" fill="#00E5FF" />
      </svg>
      <div className="soc-sismograma__readout">
        <div>
          <div className="soc-readout__label">PGA</div>
          <div className="soc-readout__value">{pga}<span className="unit">g</span></div>
        </div>
        <div>
          <div className="soc-readout__label">PGV</div>
          <div className="soc-readout__value">{pgv}<span className="unit">cm/s</span></div>
        </div>
      </div>

      {/* === SOH BADGES — Sensor Health (State of Health) ============
          Push-based from edge: NTP discipline, ADC clipping flag, and
          packet-loss rolling 30s. All-green means the trace is trustable. */}
      <div className="soc-soh">
        <div className="soc-soh__badge soc-soh__badge--ok">
          <span className="soc-dot" />
          <span className="soc-soh__label">NTP OFFSET</span>
          <span className="soc-soh__value">±4 ms</span>
        </div>
        <div className="soc-soh__badge soc-soh__badge--ok">
          <span className="soc-dot" />
          <span className="soc-soh__label">CLIPPING</span>
          <span className="soc-soh__value">NORMAL</span>
        </div>
        <div className="soc-soh__badge soc-soh__badge--ok">
          <span className="soc-dot" />
          <span className="soc-soh__label">PACKET LOSS</span>
          <span className="soc-soh__value">0 %</span>
        </div>
      </div>

      <div className="soc-edge-tag">
        <i data-lucide="cpu" width="11" height="11" />
        DATOS PRELIMINARES · PROCESAMIENTO EDGE
      </div>
    </>
  );
};

const BmsRow = ({ label, state, kind = 'ok', timestamp }) => (
  <div className="soc-bms__row">
    <span className={`soc-check soc-check--${kind}`}>
      <i data-lucide="check" width="14" height="14" style={{ strokeWidth: 3 }} />
    </span>
    <span>
      <div className="soc-bms__label">{label}</div>
      <div style={{ fontSize: 10, color: 'var(--tk-fg-3)', fontFamily: 'var(--tk-font-mono)', letterSpacing: '0.04em', marginTop: 2 }}>
        EDGE · {timestamp}
      </div>
    </span>
    <span className={`soc-bms__state soc-bms__state--${kind}`}>{state}</span>
  </div>
);

const CCTVFeed = () => {
  // ONVIF stub — deterministic monochrome corridor still
  return (
    <div className="soc-cctv__feed-wrap">
      <svg viewBox="0 0 320 130" preserveAspectRatio="xMidYMid slice" className="soc-cctv__feed">
        {/* corridor */}
        <defs>
          <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#1c1c1c" />
            <stop offset="1" stopColor="#0a0a0a" />
          </linearGradient>
          <linearGradient id="wallL" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#161616" />
            <stop offset="1" stopColor="#0c0c0c" />
          </linearGradient>
          <linearGradient id="wallR" x1="1" y1="0" x2="0" y2="0">
            <stop offset="0" stopColor="#161616" />
            <stop offset="1" stopColor="#0c0c0c" />
          </linearGradient>
        </defs>
        <rect width="320" height="130" fill="#070808" />
        {/* perspective walls */}
        <polygon points="0,0 0,130 100,90 100,40" fill="url(#wallL)" />
        <polygon points="320,0 320,130 220,90 220,40" fill="url(#wallR)" />
        <polygon points="100,40 220,40 220,90 100,90" fill="#0e0e0e" />
        {/* floor lines */}
        <polygon points="0,130 100,90 220,90 320,130" fill="url(#floor)" />
        {/* doors */}
        <rect x="22" y="55" width="20" height="50" fill="#1f1f1f" />
        <rect x="60" y="60" width="18" height="40" fill="#1a1a1a" />
        <rect x="244" y="60" width="18" height="40" fill="#1a1a1a" />
        <rect x="280" y="55" width="20" height="50" fill="#1f1f1f" />
        {/* far doorway */}
        <rect x="146" y="50" width="28" height="40" fill="#262626" />
        <rect x="152" y="56" width="16" height="28" fill="#0a0a0a" />
        {/* ceiling lights */}
        <rect x="155" y="42" width="10" height="2" fill="#3a3a3a" />
        <rect x="120" y="35" width="6" height="2" fill="#2a2a2a" />
        <rect x="195" y="35" width="6" height="2" fill="#2a2a2a" />
        {/* scan lines */}
        <g opacity="0.06" stroke="#fff" strokeWidth="0.4">
          {Array.from({ length: 26 }, (_, i) => (
            <line key={i} x1="0" y1={i * 5} x2="320" y2={i * 5} />
          ))}
        </g>
      </svg>
      <div className="soc-cctv__overlay">
        <span className="soc-cctv__live">REC</span>
        <span className="soc-cctv__camlbl">CAM-04 · PISO 1 · PASILLO NORTE</span>
      </div>
      <div className="soc-cctv__ts">10:41:32 CST</div>
    </div>
  );
};

const DetailPanel = ({ onClose, site = 'Planta Cholula', siteCode = 'CHL-A · 19.0633°N · 98.3014°W' }) => {
  return (
    <aside className="soc-detail">
      <header className="soc-detail__hd">
        <div>
          <span className="soc-meta">DETALLE DEL SITIO · EDGE+CLOUD</span>
          <h2 className="soc-detail__site">{site}</h2>
          <div className="soc-detail__sub">{siteCode}</div>
        </div>
        <button className="soc-icon-btn" onClick={onClose} aria-label="Cerrar">
          <i data-lucide="x" width="16" height="16" />
        </button>
      </header>

      {/* Sismograma RS4D ============================================ */}
      <div className="soc-card">
        <div className="soc-card__hd">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <i data-lucide="activity" width="14" height="14" style={{ color: 'var(--tk-cyan)' }} />
              Sensor RS4D · Live Sismograma
            </div>
            <div className="soc-card__sub">Z-AXIS · 200 Hz · SeedLink TCP</div>
          </div>
          <span className="soc-pill soc-pill--ok" style={{ fontSize: 9 }}>
            <span className="soc-dot soc-dot--pulse" /> LIVE
          </span>
        </div>
        <Sismograma active />
      </div>

      {/* BMS ======================================================== */}
      <div className="soc-card">
        <div className="soc-card__hd">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <i data-lucide="toggle-right" width="14" height="14" style={{ color: 'var(--tk-cyan)' }} />
              Automatización y Actuadores (BMS)
            </div>
            <div className="soc-card__sub">REGLAS LOCALES · EJECUTADAS POR EDGE</div>
          </div>
          <span className="soc-bacnet">⬢ BACnet®</span>
        </div>
        <div className="soc-bms">
          <BmsRow label="Sirena General"     state="ACTIVADA"   kind="critical" timestamp="T+0.42s" />
          <BmsRow label="Válvulas de Gas"    state="CERRADAS"   kind="warning"  timestamp="T+0.51s" />
          <BmsRow label="Ascensores"         state="RETORNADOS" kind="warning"  timestamp="T+1.20s" />
          <BmsRow label="Retenedores Puerta" state="LIBERADOS"  kind="ok"       timestamp="T+0.45s" />
        </div>
      </div>

      {/* CCTV ======================================================= */}
      <div className="soc-card">
        <div className="soc-card__hd">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <i data-lucide="video" width="14" height="14" style={{ color: 'var(--tk-cyan)' }} />
              Verificación Visual · CCTV ONVIF
            </div>
            <div className="soc-card__sub">PROFILE S · RTSP/H.264 · 1280×720</div>
          </div>
          <span className="soc-bacnet">⬢ ONVIF</span>
        </div>
        <div className="soc-cctv">
          <CCTVFeed />
          <div className="soc-cctv__controls">
            <button className="soc-icon-btn" aria-label="Reproducir"><i data-lucide="play" width="14" height="14" /></button>
            <input type="range" defaultValue={5} className="soc-cctv__seek" />
            <button className="soc-icon-btn" aria-label="Volumen"><i data-lucide="volume-2" width="14" height="14" /></button>
            <button className="soc-icon-btn" aria-label="Pantalla completa"><i data-lucide="maximize" width="14" height="14" /></button>
          </div>
        </div>
      </div>
    </aside>
  );
};

window.DetailPanel = DetailPanel;
