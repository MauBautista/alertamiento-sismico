import { DERIVED_STATE_PILL, UNKNOWN_DERIVED_STATE_KIND } from "@takab/design-tokens";
import { Activity, Clock, Cpu, MapPin, Radio, ToggleRight, Zap } from "lucide-react";

import type { GatewayConfigStateOut, GatewayHealthOut, MaintenanceWindowOut } from "@takab/sdk";

import Sparkline from "../../components/Sparkline";
import { useSessionStore } from "../../auth/session.store";
import { utcClock } from "../../lib/time";
import LinkPill from "./LinkPill";
import RelayGrid from "./RelayGrid";
import SyncBadge from "./SyncBadge";
import UpsGauge from "./UpsGauge";
import VersionBadge from "./VersionBadge";
import { maintenanceLabel, muteAckLine, muteHeadline, muteOutcome } from "../console/maintenance";
import { useSelfTest } from "./useSelfTest";
import type { FleetCabinet } from "./useFleet";
import { DEGRADADO, RETIRADO, SD, SIN_ENLACE } from "./estadoGlosario";
import { esDeDemostracion, ROTULO_DEMO } from "./datosDeDemostracion";

export interface SiteCardProps {
  cabinet: FleetCabinet;
  /** [T-2.37] Estado del config firmado; `undefined` = no se sabe (no se asume). */
  syncState?: GatewayConfigStateOut;
  /** [T-2.38] Historia de 24 h: tendencia y REINCIDENCIA de caídas. */
  health?: GatewayHealthOut;
  /**
   * [T-2.71] Ventana de mantenimiento que tapa a ESTE gabinete, si la hay.
   *
   * ADITIVA, jamás sustitutiva: el `derived_state` NO se toca. Un gabinete en
   * mantenimiento sigue diciendo `SIN ENLACE` y ADEMÁS lleva este rótulo.
   * Reemplazarlo por un estado neutro reproduciría el cero tranquilizador que
   * cerró T-2.59: un número apacible que nadie comprobó (regla de oro 7).
   */
  maintenance?: MaintenanceWindowOut;
  /** [T-2.37] Acciones de administración; ausentes para quien no tiene manage_fleet. */
  onEdit?: () => void;
  /**
   * [T-2.71] Abrir una ventana de mantenimiento sobre ESTE gabinete. Ausente para
   * quien no tiene `maintenance_window`, y ausente también cuando ya hay una
   * ventana viva: dos ventanas sobre el mismo gabinete no suman silencio, suman
   * confusión sobre cuál venció.
   */
  onOpenWindow?: () => void;
  onRetire?: () => void;
  onRestore?: () => void;
  restoring?: boolean;
}

/** Tarjeta de gabinete: pinta el estado YA derivado por el servidor (G7). */
export default function SiteCard({
  cabinet,
  syncState,
  health,
  maintenance,
  onEdit,
  onOpenWindow,
  onRetire,
  onRestore,
  restoring = false,
}: SiteCardProps) {
  const gw = cabinet.gateway;
  // [T-2.35/37] Un gabinete retirado (o cuyo sitio lo está) solo aparece con el
  // toggle VER RETIRADOS. Se rotula sin ambigüedad: sus métricas son historia.
  const retired = gw.status === "retired" || cabinet.siteStatus === "retired";
  const offline = gw.derived_state === SIN_ENLACE;
  // T-1.59: autodiagnóstico remoto — gate por matriz (self_test), no por rol.
  const canSelfTest = useSessionStore((s) => s.me?.allowed_actions.self_test === true);
  const selfTest = useSelfTest(gw.site_id);
  // Contrato semántico derived_state→tono en @takab/design-tokens (T-2.01);
  // desconocido ⇒ ámbar, nunca ok.
  const pill = DERIVED_STATE_PILL[gw.derived_state] ?? UNKNOWN_DERIVED_STATE_KIND;
  const linkKind = offline ? "crit" : "ok";
  const mqttValue = offline
    ? "— sin enlace —"
    : gw.mqtt_rtt_ms != null
      ? `↔ ${gw.mqtt_rtt_ms.toFixed(1)} ms`
      : "s/d";
  // [T-5.24] La pérdida de paquetes viaja pegada al lag porque es el MISMO
  // enlace (sensor→Pi) y se diagnostican juntos: un lag que sube con pérdida al
  // 0 % es otro problema que un lag que sube perdiendo el 12 %. Hasta esta ficha
  // la ingesta tiraba el dato, así que para verlo había que ir al inmueble.
  //
  // `s/d` explícito cuando no hay medición: un hueco se lee como 0 % (regla de
  // oro 7). Y NO tiñe la pill, porque esa regla ya estaba escrita en `LinkPill`
  // y es buena: «el semáforo fino por métrica NO existe aquí, los umbrales viven
  // solo en el servidor». El servidor no tiene umbral de pérdida —el 1 %/10 % es
  // consejo local del panel del gabinete—, así que teñir aquí sería que la
  // consola se inventara una salud que la API no afirma.
  const perdida = gw.packet_loss_pct != null ? `${gw.packet_loss_pct.toFixed(1)} %` : "s/d";
  const seedlinkValue = offline
    ? "— sin enlace —"
    : `${gw.seedlink_lag_s != null ? `lag ${gw.seedlink_lag_s.toFixed(2)} s` : "lag s/d"} · pérdida ${perdida}`;

  return (
    <article
      className={`fleet-card fleet-card--${pill}${retired ? " fleet-card--retired" : ""}`}
      data-gateway={gw.gateway_id}
    >
      {retired && (
        <div className="fleet-card__retired" data-testid="card-retired">
          {RETIRADO}
          {cabinet.siteStatus === "retired" ? " · LA ESTACIÓN TAMBIÉN" : ""}
          {onRestore && (
            <button
              type="button"
              className="soc-btn soc-btn--secondary"
              disabled={restoring}
              onClick={onRestore}
            >
              RESTAURAR
            </button>
          )}
        </div>
      )}
      <header className="fleet-card__hd">
        <div>
          <div className="fleet-card__name">{cabinet.siteName}</div>
          <div className="fleet-card__loc">
            <MapPin size={11} aria-hidden />
            {cabinet.siteCode}
            {gw.iot_thing && <span className="fleet-card__tenant"> · {gw.iot_thing}</span>}
          </div>
        </div>
        <div className="fleet-card__id">
          <span className={`soc-pill soc-pill--${pill}`}>
            <span className="soc-dot" /> {gw.derived_state}
          </span>
          <SyncBadge state={syncState} />
          {maintenance !== undefined && (
            <span
              className="fleet-card__maint"
              data-testid="maintenance-badge"
              // El tooltip afirmaba «Alarmas de operación silenciadas» pasara lo
              // que pasara — incluso con el `0/N` del propio payload delante, que
              // es el estado de TODA ventana con `ops_muting_enabled=False`.
              // Ahora lleva el mismo acuse que el banner: dos pantallas, una
              // sola verdad.
              data-mute={muteOutcome(maintenance)}
              title={`${muteHeadline(maintenance)} · ${muteAckLine(maintenance)} · MOTIVO: ${maintenance.reason}`}
            >
              {maintenanceLabel(maintenance)}
            </span>
          )}
          {maintenance === undefined && onOpenWindow !== undefined && (
            <button
              className="fleet-card__maint-open"
              data-testid="open-window"
              onClick={onOpenWindow}
              title="Silenciar los avisos de operación de este gabinete durante un rato"
              type="button"
            >
              VENTANA
            </button>
          )}
          {/* [T-5.05] Un gabinete de DEMOSTRACIÓN se veía idéntico a uno real.
              Gris y con borde discontinuo a propósito: el ámbar de esta consola
              ya significa simulacro y dato retenido, y un tercer significado en
              el mismo color deja de significar nada. */}
          {(esDeDemostracion(gw.serial) || esDeDemostracion(cabinet.siteCode)) && (
            <span
              className="fleet-card__demo"
              data-testid="demo-badge"
              title="Dato de demostración: este gabinete no existe"
            >
              {ROTULO_DEMO}
            </span>
          )}
          <span className="fleet-card__sid">{gw.serial}</span>
        </div>
      </header>

      {gw.derived_state === DEGRADADO && (gw.degrade_reasons?.length ?? 0) > 0 && (
        <div className="fleet-card__reasons" aria-label="métricas degradadas">
          {(gw.degrade_reasons ?? []).map((reason) => (
            <span key={reason} className="fleet-card__reason">
              {reason}
            </span>
          ))}
        </div>
      )}

      <div className="fleet-card__links">
        <LinkPill
          kind={linkKind}
          label="MQTT BROKER"
          icon={<Radio size={12} aria-hidden />}
          value={mqttValue}
        />
        <LinkPill
          kind={linkKind}
          label="SEEDLINK · RS4D"
          icon={<Activity size={12} aria-hidden />}
          value={seedlinkValue}
        />
      </div>

      <UpsGauge powerStatus={gw.power_status} batteryPct={gw.battery_pct} />

      <div className="fleet-card__section">
        <div className="fleet-card__sectionhd">
          <ToggleRight size={12} aria-hidden />
          <span>ACTUADORES LOCALES · BACnet/IP</span>
        </div>
        {cabinet.relays && cabinet.relays.length > 0 ? (
          <>
            <RelayGrid relays={cabinet.relays} />
            <div className="fleet-card__derived">CONFIG ACTIVA · ESTADO DERIVADO DEL ENLACE</div>
          </>
        ) : (
          <div className="fleet-card__derived">
            {offline
              ? `ACTUADORES · ${SD} (${SIN_ENLACE})`
              : "ARMADOS · CONFIG DE RELAYS NO VISIBLE"}
          </div>
        )}
      </div>

      {health && (
        <div className="fleet-card__history" data-testid="card-history">
          <span className="fleet-card__historylbl">RTT p95 · 24 H</span>
          <Sparkline
            values={(health.buckets ?? []).map((b) => b.mqtt_rtt_p95_ms ?? null)}
            label={`RTT MQTT p95 de las últimas 24 h de ${cabinet.siteName}`}
          />
          <span
            className={`fleet-card__outages${(health.outages ?? 0) > 0 ? " fleet-card__outages--warn" : ""}`}
          >
            CAÍDAS 24 H: {health.outages ?? 0}
            {(health.outages ?? 0) > 0 &&
              ` · ${Math.round((health.downtime_s ?? 0) / 60)} min sin enlace`}
          </span>
          <span className="fleet-card__completeness">
            LATIDOS{" "}
            {health.heartbeat_completeness == null
              ? SD
              : `${Math.round(health.heartbeat_completeness * 100)}%`}
          </span>
        </div>
      )}

      <footer className="fleet-card__ft">
        <div className="fleet-card__meta">
          {/* [T-2.69] Antes esto era `{gw.fw_version ?? "fw s/d"}`: un chip mudo
              que pintaba IGUAL la versión que un gabinete acababa de confirmar y
              la que otro reportó por última vez hace tres semanas. El badge trae
              la edad del dato y el estado derivado por el servidor. */}
          <span>
            <Cpu size={11} aria-hidden /> <VersionBadge gateway={gw} />
          </span>
          <span className="tk-sep">·</span>
          <span>
            <Clock size={11} aria-hidden /> HB{" "}
            {gw.last_heartbeat_ts ? `${utcClock(Date.parse(gw.last_heartbeat_ts))} UTC` : "—"}
          </span>
        </div>
        <button
          type="button"
          className="fleet-card__diag"
          disabled={!canSelfTest || offline || selfTest.pending || selfTest.phase === "issued"}
          title={
            !canSelfTest
              ? "Tu rol no tiene la acción self_test (dueño del sitio)"
              : offline
                ? "Gabinete sin enlace: el comando expiraría por TTL"
                : "Pulsa los relés NO audibles con verificación; la sirena no suena"
          }
          onClick={selfTest.run}
        >
          <Zap size={13} aria-hidden />{" "}
          {selfTest.phase === "issued" || selfTest.pending
            ? "DIAGNÓSTICO EN CURSO…"
            : "AUTODIAGNÓSTICO SILENCIOSO"}
        </button>
      </footer>

      {(onEdit || onRetire) && !retired && (
        <div className="fleet-card__admin" data-testid="card-admin">
          {onEdit && (
            <button type="button" className="soc-btn soc-btn--secondary" onClick={onEdit}>
              EDITAR GABINETE
            </button>
          )}
          {onRetire && (
            <button type="button" className="soc-btn soc-btn--secondary" onClick={onRetire}>
              RETIRAR
            </button>
          )}
        </div>
      )}

      {/* T-1.59: resultado del ack del edge — chips por relé, jamás inventados. */}
      {selfTest.phase !== "idle" && selfTest.phase !== "issued" && (
        <div className="fleet-card__selftest" data-testid="selftest-result">
          {selfTest.phase === "acked" && selfTest.relays ? (
            Object.entries(selfTest.relays).map(([channel, check]) => (
              <span
                key={channel}
                className={`soc-pill soc-pill--${check.readback_ok ? "ok" : "crit"}`}
              >
                {channel.toUpperCase()} {check.pulsed ? (check.readback_ok ? "✓" : "✗") : "LECTURA"}
              </span>
            ))
          ) : (
            <span className="soc-pill soc-pill--crit">
              SELF-TEST {selfTest.phase === "expired" ? "SIN ACUSE (TTL)" : "RECHAZADO"}
              {selfTest.detail ? ` · ${selfTest.detail}` : ""}
            </span>
          )}
          <button type="button" className="fleet-card__diag" onClick={selfTest.reset}>
            LIMPIAR
          </button>
        </div>
      )}
    </article>
  );
}
