import { ChevronRight, Mail, MessageCircle, Smartphone, Webhook } from "lucide-react";

import type { NotifyChannelOut } from "@takab/sdk";

import { channelRealityOf } from "./model";
import type { ChannelDraft, ChannelKey, ChannelReality } from "./model";

/**
 * Lo FIJO del canal: cómo se llama, qué destino admite y con qué icono se pinta.
 *
 * [T-2.75.a] Lo que YA NO vive aquí es si el canal entrega. `sub` decía
 * «SIMULADO en el MVP» para WhatsApp y SMS: verdad escrita a fuego, que el día
 * que T-2.76.a/T-2.77.a carguen credenciales se convierte en la mentira
 * inversa. Eso se le pregunta al servidor (`GET /notify/channels`), que lo
 * deriva del registro de providers.
 */
const META: Record<
  ChannelKey,
  { label: string; sub: string; placeholder: string; Icon: typeof Webhook }
> = {
  webhook: {
    label: "API · Webhook",
    sub: "POST JSON firmado con HMAC",
    placeholder: "https://ops.cliente.mx/takab",
    Icon: Webhook,
  },
  whatsapp: {
    label: "WhatsApp Business",
    sub: "Cloud API · plantilla aprobada por Meta",
    placeholder: "+52 55 0000 0000",
    Icon: MessageCircle,
  },
  sms: {
    label: "SMS",
    sub: "SLA de entrega ≤30 s",
    placeholder: "+52 55 0000 0000",
    Icon: Smartphone,
  },
  email: {
    label: "Correo electrónico",
    sub: "SES · uno o varios, separados por coma",
    placeholder: "ops@cliente.mx, cc@cliente.mx",
    Icon: Mail,
  },
};

/** Rótulo de la realidad del provider. Tres estados, y el tercero NO es «real». */
const REALITY_LABEL: Record<ChannelReality, string> = {
  real: "REAL · ENTREGA DE VERDAD",
  simulated: "SIMULADO · NADIE LO RECIBE",
  unknown: "S/D · EL SERVIDOR NO LO DECLARA",
};

export interface NotificationChannelsProps {
  drafts: ChannelDraft[];
  disabled: boolean;
  onChange: (drafts: ChannelDraft[]) => void;
  /**
   * [T-2.75.a] Realidad de cada provider según `GET /notify/channels`.
   * `undefined` = cargando o la consulta falló ⇒ todos los canales se pintan
   * `S/D`. No se inventa un default optimista: afirmar que un canal entrega
   * cuando no se sabe es exactamente el tablero mentiroso de T-2.75.
   */
  reality: NotifyChannelOut[] | undefined;
}

/**
 * Cascada de notificación configurable (`config.notifications`, vía PUT /rule-sets).
 *
 * Lo CONFIGURABLE es qué canales existen y su destino. Lo FIJO es el orden
 * (`notify/plan.CASCADE_ORDER`: webhook→whatsapp→sms→email) y los tiempos
 * (`Settings.notify_step_s`, globales, no por tenant): se muestran, no se editan.
 *
 * Desviaciones honestas frente al mockup:
 * - El mockup llamaba `api` al canal; el real se llama `webhook`.
 * - Un canal NO es un booleano: lleva un objeto de destino (`url`/`to`). Un canal
 *   presente sin destino lo OMITE `resolve_destinations` con un warning, así que
 *   aquí se marca INCOMPLETO en vez de pintarse como activo.
 * - El `secret` del webhook nunca viaja al cliente ni se edita aquí.
 * - No hay estado vivo de la cascada (`notification_jobs` no tiene endpoint).
 */
export default function NotificationChannels({
  drafts,
  disabled,
  onChange,
  reality,
}: NotificationChannelsProps) {
  const active = drafts.filter((d) => d.enabled && d.destination.trim() !== "");

  function update(key: ChannelKey, patch: Partial<ChannelDraft>): void {
    onChange(drafts.map((d) => (d.key === key ? { ...d, ...patch } : d)));
  }

  return (
    <div className="soc-card">
      <div className="soc-card__hd">
        <div>
          <div>Canales de notificación · Cascada de respaldo</div>
          <div className="soc-card__sub">
            SI EL EDGE NO ALCANZA RED, LA NUBE DISPARA TODOS EN PARALELO (FAIL-OPEN)
          </div>
        </div>
        <span className="soc-bacnet">⬢ ORDEN Y TIEMPOS FIJOS</span>
      </div>

      <div className="mt-channels">
        {drafts.map((d) => {
          const { label, sub, placeholder, Icon } = META[d.key];
          const incomplete = d.enabled && d.destination.trim() === "";
          const on = d.enabled && !incomplete;
          const providerReality = channelRealityOf(reality, d.key);
          return (
            <div
              key={d.key}
              className={`mt-channel${on ? " is-on" : ""}`}
              data-testid={`channel-${d.key}`}
            >
              <span className="mt-channel__icon">
                <Icon size={16} aria-hidden />
              </span>
              <span className="mt-channel__body">
                <span className="mt-channel__label">{label}</span>
                <span className="mt-channel__sub">
                  {incomplete ? "INCOMPLETO · sin destino, el backend lo omite" : sub}
                </span>
                <span
                  className={`mt-channel__reality mt-channel__reality--${providerReality}`}
                  data-testid={`channel-reality-${d.key}`}
                >
                  {REALITY_LABEL[providerReality]}
                </span>
                {d.enabled && (
                  <input
                    type="text"
                    className="soc-select"
                    aria-label={`Destino de ${label}`}
                    placeholder={placeholder}
                    value={d.destination}
                    disabled={disabled}
                    onChange={(e) => update(d.key, { destination: e.target.value })}
                  />
                )}
              </span>
              <button
                type="button"
                className={`mt-channel__switch${on ? " is-on" : ""}`}
                aria-pressed={d.enabled}
                aria-label={`Habilitar ${label}`}
                disabled={disabled}
                onClick={() => update(d.key, { enabled: !d.enabled })}
              >
                <span className="mt-channel__knob" />
              </button>
            </div>
          );
        })}
      </div>

      <div className="mt-channels__cascade">
        <span className="soc-meta">CASCADA APLICADA · ORDEN FIJO DEL SERVIDOR</span>
        <span className="mt-channels__cascade-trace">
          {active.length === 0 ? (
            <span style={{ color: "var(--tk-status-critical)" }}>
              SIN CANAL CON DESTINO · TENANT DESPROTEGIDO
            </span>
          ) : (
            active.map((d, i) => (
              <span key={d.key} className="mt-channels__step">
                {i + 1}. {META[d.key].label.split(" · ")[0]}
                {i < active.length - 1 && <ChevronRight size={12} aria-hidden />}
              </span>
            ))
          )}
        </span>
      </div>
    </div>
  );
}
