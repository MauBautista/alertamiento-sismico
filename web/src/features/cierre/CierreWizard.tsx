// [T-9.41 · D-43] EL ASISTENTE «CIERRE DEL EVENTO» (`/triage/:incidentId/cierre`).
//
// Seis pasos derivados por `pasos.ts` —función pura— de lo que el SERVIDOR dice
// hoy del incidente. Esta pantalla no recuerda clics: acusar, confirmar,
// clasificar o cerrar ESPERAN la respuesta y RELEEN; el paso pasa a «hecho»
// cuando la relectura lo dice.
//
// Cada consulta pinta SU estado (regla de oro 7): la FILA del incidente es el
// marco de la página entera, y dentro cada paso con dato propio tiene su marco
// (reportes, cadena de dictámenes, clasificación, informe automático). Un paso
// cuyo dato no cargó se pinta «SIN DATO», nunca «PENDIENTE».

import {
  CheckCircle2,
  Circle,
  ClipboardCheck,
  FileText,
  HelpCircle,
  Lock,
  MinusCircle,
  ShieldCheck,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";

import { useSessionStore } from "../../auth/session.store";
import Button, { ButtonLink } from "../../components/Button";
import Card from "../../components/Card";
import ConfirmButton from "../../components/ConfirmButton";
import SiteLabel from "../../components/SiteLabel";
import StateFrame from "../../components/StateFrame";
import { staleDeLectura } from "../../components/staleDeLectura";
import { utcStamp } from "../../lib/time";
import { useIncidentAck } from "../console/useIncidentAck";
import { bandOf, chainHead, signatureOf, verdictOf } from "../triage/model";
import { CLASIFICACIONES, useClassification } from "../triage/useClassification";
import { useDamageReports } from "../triage/useDamageReports";
import { useIncidentDetail } from "../triage/useIncidentDetail";
import {
  MOTIVO_MIN_CHARS,
  derivarPasos,
  quienPuede,
  recuentoPorTipo,
  type EstadoPaso,
  type HechosDelCierre,
  type Paso,
  type Permisos,
} from "./pasos";
import { useCerrarEvento } from "./useCerrarEvento";
import { useDictamenConfirm } from "./useDictamenConfirm";
import { INCIDENTE_KEY, useIncidente, useSitio } from "./useIncidente";
import { INFORME_KEY, useInformeAutomatico } from "./useInformeAutomatico";

/** Icono Y texto: el estado nunca se dice sólo con color. */
const ESTADO_UI: Record<EstadoPaso, { texto: string; Icono: typeof Circle }> = {
  hecho: { texto: "HECHO", Icono: CheckCircle2 },
  pendiente: { texto: "PENDIENTE", Icono: Circle },
  no_aplica: { texto: "NO APLICA", Icono: MinusCircle },
  bloqueado: { texto: "BLOQUEADO", Icono: Lock },
  sin_dato: { texto: "SIN DATO", Icono: HelpCircle },
};

/** Las clasificaciones que CIERRAN el evento al enviarse (`CIERRA_EL_INCIDENTE`). */
const CIERRAN: ReadonlySet<string> = new Set(["falso_positivo", "prueba", "reproduccion"]);

const ETIQUETA_CLASIF: Record<string, string> = Object.fromEntries(
  CLASIFICACIONES.map((c) => [c.value, c.label]),
);

function EstadoPill({ estado }: { estado: EstadoPaso }) {
  const { texto, Icono } = ESTADO_UI[estado];
  return (
    <span className={`cierre-estado cierre-estado--${estado}`} data-testid="paso-estado">
      <Icono size={14} aria-hidden /> {texto}
    </span>
  );
}

function QuienPuede({ roles }: { roles: readonly string[] | undefined }) {
  if (roles === undefined) return null;
  return (
    <p className="cierre-paso__quien" data-testid="quien-puede">
      {roles.length === 0
        ? "NINGÚN ROL DE TU ORGANIZACIÓN PUEDE HACERLO"
        : `TU ROL NO PUEDE HACERLO · LO PUEDE HACER: ${roles.join(", ")}`}
    </p>
  );
}

function PasoCard({ n, paso, children }: { n: number; paso: Paso; children?: ReactNode }) {
  return (
    <Card
      className={`cierre-paso cierre-paso--${paso.estado}`}
      testId={`paso-${paso.id}`}
      title={
        <span className="cierre-paso__titulo">
          {n} · {paso.titulo}
        </span>
      }
      sub={paso.requeridoParaCerrar ? "OBLIGATORIO PARA CERRAR" : "NO IMPIDE CERRAR"}
      aside={<EstadoPill estado={paso.estado} />}
    >
      <p className="cierre-paso__porque">{paso.porque}</p>
      <QuienPuede roles={paso.quienPuede} />
      {children}
    </Card>
  );
}

function Alerta({ texto }: { texto: string | null | undefined }) {
  if (!texto) return null;
  return (
    <p className="cierre-paso__error" role="alert">
      {texto}
    </p>
  );
}

export default function CierreWizard() {
  const { incidentId = "" } = useParams();
  const qc = useQueryClient();
  const me = useSessionStore((s) => s.me);

  const fila = useIncidente(incidentId);
  const inc = fila.incidente;
  const sitio = useSitio(inc?.site_id ?? null);
  const detail = useIncidentDetail(
    incidentId,
    inc?.event_id ?? null,
    inc ? { openedAt: inc.opened_at } : null,
  );
  const clasif = useClassification(incidentId);
  const reportes = useDamageReports(incidentId);
  const informe = useInformeAutomatico(incidentId);

  const ack = useIncidentAck();
  const confirmar = useDictamenConfirm(incidentId);
  const cerrar = useCerrarEvento(incidentId);

  const [motivo, setMotivo] = useState("");
  const [porConfirmar, setPorConfirmar] = useState<string | null>(null);
  const [clasifError, setClasifError] = useState<string | null>(null);

  const acciones = me?.allowed_actions;
  const puede: Permisos = {
    ack_incident: acciones?.ack_incident === true,
    sign_dictamen: acciones?.sign_dictamen === true,
    confirm_dictamen: acciones?.confirm_dictamen === true,
    classify_incident: acciones?.classify_incident === true,
    generate_report: acciones?.generate_report === true,
    close_incident: acciones?.close_incident === true,
  };

  const hechos: HechosDelCierre = {
    incidente: inc ?? null,
    dictamenes: detail.dictamens.error === null ? (detail.dictamens.data ?? null) : null,
    clasificacion:
      clasif.loading || clasif.readError
        ? null
        : { vigente: clasif.current?.classification ?? null },
    reportes: reportes.error === null ? (reportes.reports ?? null) : null,
  };
  const pasos = derivarPasos(hechos, puede);
  const [pAcusar, pSacudida, pReportes, pDictamen, pClasificar, pCierre] = pasos;
  const head = chainHead(detail.dictamens.data);

  const clasifLectura = staleDeLectura(
    clasif.readError ? "no se pudo leer la clasificación" : null,
    clasif.items.length > 0,
    clasif.updatedAt,
  );

  /** Lo que el acuse, la clasificación o el cierre cambian en la FILA. */
  const releer = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: INCIDENTE_KEY(incidentId) }),
      qc.invalidateQueries({ queryKey: INFORME_KEY(incidentId) }),
    ]);

  const enviarClasificacion = (value: string) => {
    setPorConfirmar(null);
    setClasifError(null);
    clasif.clasificar(
      { classification: value, supersedesId: clasif.current?.classification_id },
      {
        onSuccess: () => void releer(),
        onError: () => setClasifError("NO SE CLASIFICÓ · EL SERVIDOR NO REGISTRÓ LA CLASIFICACIÓN"),
      },
    );
  };

  const motivoLimpio = motivo.trim();
  const motivoCorto = pCierre.exigeMotivo === true && motivoLimpio.length < MOTIVO_MIN_CHARS;
  const nodos = detail.event.data?.quorum_votes.length;

  return (
    <section className="cierre" data-screen-label="07 Cierre del Evento">
      <header className="cierre__hd">
        <span className="soc-meta">PROTECCIÓN CIVIL · CIERRE ASISTIDO DEL EVENTO</span>
        <h1 className="cierre__title">Cierre del Evento</h1>
        <ButtonLink
          variant="ghost"
          to={`/triage?incident=${encodeURIComponent(incidentId)}`}
          data-testid="cierre-volver"
        >
          ◀ VOLVER A EVALUACIÓN
        </ButtonLink>
      </header>

      <StateFrame
        label="INCIDENTE"
        loading={fila.loading}
        error={fila.error}
        onRetry={fila.refetch}
        // Una fila pedida por su id nunca está «vacía»: si no existe es un 404, y
        // `useIncidente` lo convierte en `error` con su causa.
        empty={false}
        staleSince={fila.staleSince}
      >
        {inc && (
          <>
            <h2 className="cierre__evento" data-testid="cierre-titulo">
              CIERRE DEL EVENTO ·{" "}
              {sitio ? (
                <SiteLabel name={sitio.name} code={sitio.code} />
              ) : (
                `SITIO ${inc.site_id.slice(0, 8)}`
              )}
            </h2>
            <div className="soc-meta">
              {inc.event_id ?? inc.incident_id} · ABIERTO {utcStamp(Date.parse(inc.opened_at))} UTC
              {inc.state === "closed" && " · CERRADO"}
            </div>

            <ol className="cierre-progreso" aria-label="Progreso del cierre">
              {pasos.map((p, i) => (
                <li
                  key={p.id}
                  className={`cierre-progreso__paso cierre-progreso__paso--${p.estado}`}
                  data-testid={`progreso-${p.id}`}
                >
                  <span className="cierre-progreso__n">{i + 1}</span>
                  <span className="cierre-progreso__lbl">{p.titulo}</span>
                  <EstadoPill estado={p.estado} />
                </li>
              ))}
            </ol>

            <div className="cierre__pasos">
              {/* 1 · ACUSAR */}
              <PasoCard n={1} paso={pAcusar}>
                {pAcusar.accion === "ack_incident" && (
                  <div className="cierre-paso__accion">
                    <Button
                      variant="primary"
                      disabled={ack.isPending}
                      onClick={() => {
                        void ack
                          .mutateAsync(incidentId)
                          .then(releer)
                          .catch(() => undefined);
                      }}
                    >
                      <ClipboardCheck size={16} aria-hidden />{" "}
                      {ack.isPending ? "ACUSANDO…" : "ACUSAR"}
                    </Button>
                  </div>
                )}
                <Alerta texto={ack.error?.message} />
              </PasoCard>

              {/* 2 · REVISAR LA SACUDIDA */}
              <PasoCard n={2} paso={pSacudida}>
                <dl className="cierre-metricas">
                  <div>
                    <dt>PGA MÁX</dt>
                    <dd>{inc.max_pga_g === null ? "—" : `${inc.max_pga_g.toFixed(3)} g`}</dd>
                  </div>
                  <div>
                    <dt>PGV MÁX</dt>
                    <dd>{inc.max_pgv_cms === null ? "—" : `${inc.max_pgv_cms.toFixed(1)} cm/s`}</dd>
                  </div>
                  <div>
                    <dt>NODOS</dt>
                    <dd>
                      {inc.event_id === null
                        ? "SIN EVENTO"
                        : nodos === undefined
                          ? "S/D"
                          : String(nodos)}
                    </dd>
                  </div>
                </dl>
                <div className="cierre-paso__accion">
                  <ButtonLink
                    variant="secondary"
                    to={`/triage?incident=${encodeURIComponent(incidentId)}`}
                  >
                    VER EL DETALLE EN EVALUACIÓN
                  </ButtonLink>
                </div>
              </PasoCard>

              {/* 3 · REPORTES DE CAMPO */}
              <PasoCard n={3} paso={pReportes}>
                <StateFrame
                  label="REPORTES DE CAMPO"
                  loading={reportes.loading}
                  error={reportes.error}
                  empty={reportes.reports?.length === 0}
                  emptyText="SIN REPORTES DE LA BRIGADA"
                  staleSince={reportes.staleSince}
                >
                  <ul className="cierre-recuento" data-testid="recuento-reportes">
                    {recuentoPorTipo(reportes.reports ?? []).map((r) => (
                      <li key={r.tipo}>
                        {r.tipo.toUpperCase()} · {r.n}
                      </li>
                    ))}
                  </ul>
                </StateFrame>
              </PasoCard>

              {/* 4 · DICTAMEN */}
              <PasoCard n={4} paso={pDictamen}>
                <StateFrame
                  label="DICTAMEN"
                  loading={detail.dictamens.loading}
                  error={detail.dictamens.error}
                  onRetry={detail.refetch}
                  empty={detail.dictamens.data?.length === 0}
                  emptyText="SIN DICTAMEN REGISTRADO PARA ESTE INCIDENTE"
                  staleSince={detail.dictamens.staleSince}
                >
                  {head && (
                    <p className="cierre-paso__dato" data-testid="dictamen-cabeza">
                      {verdictOf(head.status).label}
                      {bandOf(head.band) && ` · ${bandOf(head.band)?.label}`} · {signatureOf(head)}
                    </p>
                  )}
                </StateFrame>
                {pDictamen.accion === "confirm_dictamen" && head && (
                  <div className="cierre-paso__accion">
                    <ConfirmButton
                      label="CONFIRMAR DICTAMEN"
                      doneLabel="CONFIRMADO"
                      icon={<ShieldCheck size={16} aria-hidden />}
                      disabled={confirmar.isPending}
                      onConfirm={() => confirmar.mutateAsync(head.dictamen_id)}
                    />
                  </div>
                )}
                {pDictamen.accion === "firmar_en_evaluacion" && (
                  <div className="cierre-paso__accion">
                    <ButtonLink
                      variant="primary"
                      to={`/triage?incident=${encodeURIComponent(incidentId)}`}
                    >
                      <ShieldCheck size={16} aria-hidden /> FIRMAR EN EVALUACIÓN
                    </ButtonLink>
                  </div>
                )}
                {pDictamen.accion === "levantar_restriccion" && (
                  <div className="cierre-paso__accion">
                    <ButtonLink
                      variant="primary"
                      to={`/triage?incident=${encodeURIComponent(incidentId)}`}
                    >
                      <ShieldCheck size={16} aria-hidden /> LEVANTAR RESTRICCIÓN
                    </ButtonLink>
                  </div>
                )}
                <Alerta texto={confirmar.error?.message} />
              </PasoCard>

              {/* 5 · CLASIFICAR */}
              <PasoCard n={5} paso={pClasificar}>
                <StateFrame
                  label="CLASIFICACIÓN"
                  loading={clasif.loading}
                  error={clasifLectura.error}
                  onRetry={clasif.refetch}
                  empty={clasif.items.length === 0}
                  emptyText="SIN CLASIFICAR"
                  staleSince={clasifLectura.staleSince}
                >
                  <p className="cierre-paso__dato" data-testid="clasificacion-vigente">
                    {clasif.current === null
                      ? "SIN CLASIFICAR"
                      : `VIGENTE: ${ETIQUETA_CLASIF[clasif.current.classification] ?? clasif.current.classification}`}
                  </p>
                </StateFrame>
                {pClasificar.accion === "classify_incident" && (
                  <div className="cierre-paso__accion cierre-clasif">
                    {CLASIFICACIONES.map((c) => (
                      <Button
                        key={c.value}
                        variant={
                          clasif.current?.classification === c.value ? "primary" : "secondary"
                        }
                        title={c.hint}
                        data-testid={`cierre-clasificar-${c.value}`}
                        disabled={clasif.pending}
                        onClick={() =>
                          CIERRAN.has(c.value)
                            ? setPorConfirmar(c.value)
                            : enviarClasificacion(c.value)
                        }
                      >
                        {c.label}
                      </Button>
                    ))}
                  </div>
                )}
                {porConfirmar !== null && (
                  <div
                    className="cierre-dialogo"
                    role="alertdialog"
                    aria-labelledby="cierre-dialogo-titulo"
                  >
                    <p id="cierre-dialogo-titulo" className="cierre-dialogo__titulo">
                      {ETIQUETA_CLASIF[porConfirmar]} CIERRA EL EVENTO
                    </p>
                    <p className="cierre-paso__porque">
                      Al clasificarlo como {ETIQUETA_CLASIF[porConfirmar]} el servidor cierra el
                      evento en el acto. ¿Continuar?
                    </p>
                    <div className="cierre-paso__accion">
                      <Button variant="danger" onClick={() => enviarClasificacion(porConfirmar)}>
                        SÍ, CLASIFICAR Y CERRAR
                      </Button>
                      <Button variant="secondary" onClick={() => setPorConfirmar(null)}>
                        CANCELAR
                      </Button>
                    </div>
                  </div>
                )}
                <Alerta texto={clasifError} />
              </PasoCard>

              {/* 6 · INFORME Y CIERRE */}
              <PasoCard n={6} paso={pCierre}>
                <StateFrame
                  label="INFORME AUTOMÁTICO"
                  loading={informe.loading}
                  error={informe.error}
                  onRetry={informe.refetch}
                  empty={informe.informe === null}
                  emptyText="SIN INFORME TODAVÍA · SE GENERA AL FIRMAR EL DICTAMEN, AL CERRAR O AL VENCER EL PLAZO"
                  staleSince={informe.staleSince}
                >
                  {informe.informe && (
                    <p className="cierre-paso__dato" data-testid="informe-estado">
                      <FileText size={14} aria-hidden /> INFORME AUTOMÁTICO ·{" "}
                      {informe.informe.state === "pendiente"
                        ? "EN GENERACIÓN…"
                        : informe.informe.state === "ok"
                          ? `LISTO${informe.informe.preliminar === true ? " · PRELIMINAR" : ""}`
                          : `FALLÓ${informe.informe.error ? ` · ${informe.informe.error}` : ""}`}
                    </p>
                  )}
                </StateFrame>

                <div className="cierre-paso__accion">
                  {puede.generate_report ? (
                    <Button
                      variant="secondary"
                      disabled={detail.pdfPending}
                      onClick={() => detail.generatePdf()}
                    >
                      <FileText size={16} aria-hidden />{" "}
                      {detail.pdfPending ? "GENERANDO…" : "GENERAR INFORME DEFINITIVO"}
                    </Button>
                  ) : (
                    <QuienPuede roles={quienPuede("generate_report")} />
                  )}
                </div>
                <Alerta texto={detail.exportError} />

                {pCierre.accion === "close_incident" && pCierre.exigeMotivo === true && (
                  <label className="cierre-motivo">
                    <span className="cierre-motivo__lbl">
                      MOTIVO DEL CIERRE SIN DICTAMEN FIRMADO (MÍNIMO {MOTIVO_MIN_CHARS} CARACTERES)
                    </span>
                    <textarea
                      className="cierre-motivo__txt"
                      aria-label="Motivo del cierre"
                      value={motivo}
                      rows={3}
                      onChange={(e) => setMotivo(e.target.value)}
                    />
                    <span
                      className={`cierre-motivo__cuenta${motivoCorto ? " is-corto" : ""}`}
                      data-testid="motivo-cuenta"
                    >
                      {motivoLimpio.length} / {MOTIVO_MIN_CHARS}
                    </span>
                  </label>
                )}
                {pCierre.accion === "close_incident" && (
                  <div className="cierre-paso__accion">
                    <ConfirmButton
                      label="CERRAR EVENTO"
                      doneLabel="CERRADO"
                      icon={<Lock size={16} aria-hidden />}
                      disabled={cerrar.isPending || motivoCorto}
                      title={
                        motivoCorto
                          ? `Escribe un motivo de al menos ${MOTIVO_MIN_CHARS} caracteres`
                          : undefined
                      }
                      onConfirm={() =>
                        cerrar.mutateAsync(pCierre.exigeMotivo === true ? motivoLimpio : null)
                      }
                    />
                  </div>
                )}
                <Alerta texto={cerrar.error?.message} />
              </PasoCard>
            </div>
          </>
        )}
      </StateFrame>
    </section>
  );
}
