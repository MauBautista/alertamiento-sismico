// jsx/AlertHero.jsx
// Critical alert overlay — anchored top-left of map stage.
// Wire-up note: bind to MQTT topic `takab.event.{event_id}.preliminary`
// Edge gateway publishes M/PGA estimates within 250ms of S-wave detection.

const AlertHero = ({
  active   = true,
  magnitude = 6.8,
  countdown = 15,
  pgaMax    = 0.15,
  site     = 'PLANTA CHOLULA · EDIFICIO A',
  eventId  = 'EVT-20260510-0843',
}) => {
  if (!active) return null;
  // T-MINUS visual emphasis: when ≤ 5s, force the warning numerals to status-critical color
  const imminent = countdown <= 5;

  return (
    <div className="soc-alert" role="alert" aria-live="assertive">
      <div className="soc-alert__strip">
        <i data-lucide="alert-octagon" width="16" height="16" />
        ALERTA SÍSMICA ACTIVA
      </div>

      <div className="soc-alert__site">{site}</div>
      <div className="soc-alert__sub">EVENT_ID {eventId}</div>

      <div className="soc-alert__grid">
        <div>
          <div className="soc-alert__num">
            M&nbsp;{magnitude.toFixed(1)}
          </div>
          <div className="soc-alert__lbl">PRELIMINAR</div>
        </div>
        <div>
          <div className="soc-alert__lbl soc-alert__lbl--warn">T-MINUS</div>
          <div
            className="soc-alert__num soc-alert__num--warn"
            style={imminent ? { color: 'var(--tk-status-critical)' } : undefined}
          >
            {String(countdown).padStart(2, '0')}
            <span className="soc-alert__num--unit">s</span>
          </div>
          <div className="soc-alert__lbl soc-alert__lbl--warn">COUNTDOWN</div>
        </div>
      </div>

      <div className="soc-alert__pga">
        <span className="soc-alert__pga-label">PGA MAX</span>
        <span className="soc-alert__pga-value">
          {pgaMax.toFixed(2)}<span className="unit">g</span>
        </span>
      </div>

      <div className="soc-alert__ack">
        <span>EDGE · RS4D · LOCAL RULES FIRED</span>
        <span style={{ color: 'var(--tk-status-normal)' }}>● AUTO</span>
      </div>
    </div>
  );
};

window.AlertHero = AlertHero;
