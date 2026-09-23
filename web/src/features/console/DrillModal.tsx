// Alta de simulacro (T-2.48): a quién, cuánto, cuándo y por qué.
//
// Hasta T-2.47 la consola solo sabía lanzar "5 minutos a TODOS los gabinetes
// del tenant": `POST /drills` aceptaba `site_ids`, `duration_s`, `note` y
// `scheduled_at` desde T-1.60/T-2.03 y nadie los mandaba. Un simulacro real se
// hace por edificio y con aviso previo, no de golpe en todo el corporativo.
//
// AHORA vs PROGRAMAR son dos cosas distintas y el modal no las mezcla:
// programar NO emite nada — deja una agenda que después alguien ejecuta con un
// clic (regla de oro 8).
//
// [T-5.13] PLANTILLAS. Hasta aquí un simulacro recurrente se tecleaba entero cada
// vez: los sitios, la duración y la nota, para el macrosimulacro de septiembre y
// para el trimestral. Ahora se define una vez y se lanza en dos clics.
//
// Lo que este modal NO puede hacer es callar una plantilla degradada. Un edificio
// que perdió el gabinete —o que se dio de baja— desaparecería del conjunto sin
// que nadie lo note, y el operador creería haber lanzado el simulacro a diez
// torres cuando sonó en ocho. El servidor evalúa el estado de cada sitio AL LEER
// (no lo congela) y aquí se pinta antes de lanzar.
//
// [A-016 · T-8.07] UN ROL INTERNO NOMBRA AL CLIENTE. «Sin selección ⇒ todos los
// comandables del tenant» es verdad para un rol de cliente, cuya RLS le acota los
// sitios; para un interno TAKAB era TODA LA PLATAFORMA. Aquí elige el cliente, ve
// sólo sus sitios y sus plantillas, y sin selección no se lanza (la API responde
// 400 igual: esto es para que no tenga que descubrirlo).
//
// [A-094 · T-8.07] «INICIAR AHORA» vocea en edificios reales: es de dos pasos,
// como todo lo que toca un gabinete. BORRAR una plantilla, también.

import { useCallback, useMemo, useState } from "react";

import { listSitesSitesGet, listTenantsTenantsGet } from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";

import { useSessionStore } from "../../auth/session.store";
import Button from "../../components/Button";
import ConfirmButton from "../../components/ConfirmButton";
import Modal from "../../components/Modal";
import StateFrame from "../../components/StateFrame";
import type { StartDrillInput } from "./useActiveDrill";
import { sitiosNoUsables, useDrillTemplates } from "./useDrillTemplates";
import SiteLabel from "../../components/SiteLabel";

/** Ventanas ofrecidas; el CHECK de DB acota a 30 s..1 h. */
const DURATIONS: readonly { value: number; label: string }[] = [
  { value: 60, label: "1 MIN" },
  { value: 180, label: "3 MIN" },
  { value: 300, label: "5 MIN" },
  { value: 600, label: "10 MIN" },
  { value: 900, label: "15 MIN" },
  { value: 1800, label: "30 MIN" },
];

export interface DrillModalProps {
  pending: boolean;
  error: string | null;
  /**
   * [T-8.07] Puede devolver si el servidor lo registró (`useActiveDrill.start`):
   * con `false` el botón de dos pasos vuelve a reposo en vez de afirmar nada.
   */
  onSubmit: (input: StartDrillInput) => void | Promise<boolean>;
  onClose: () => void;
}

/** Mismo plazo que el catálogo de clientes de la flota: cambia por acto humano. */
const CLIENTES_STALE_MS = 120_000;

/** `datetime-local` → ISO UTC. Devuelve null si el navegador no dio nada útil. */
function localToUtcIso(value: string): string | null {
  if (value.trim() === "") return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : new Date(ms).toISOString();
}

export default function DrillModal({ pending, error, onSubmit, onClose }: DrillModalProps) {
  // [A-016 · T-8.07] Lo dice el SERVIDOR (`/me.is_internal`), no el nombre del rol.
  const isInternal = useSessionStore((s) => s.me?.is_internal === true);
  // Los NOMBRES de los clientes, sólo si el rol puede leer el catálogo: no se
  // amplía nada. Sin ellos se rotula con el identificador (no se inventa).
  const canReadClients = useSessionStore(
    (s) => s.me?.is_internal === true && s.me.allowed_actions.manage_tenants === true,
  );
  const clientCatalog = useQuery({
    // La MISMA clave que el resto de la consola (`useTenantOptions`, `useTenants`):
    // una sola caché del catálogo de clientes.
    queryKey: ["tenants"],
    enabled: canReadClients,
    queryFn: async () => {
      const { data, response } = await listTenantsTenantsGet();
      if (data === undefined) throw new Error(`GET /tenants falló (${response.status})`);
      return data;
    },
    staleTime: CLIENTES_STALE_MS,
  });
  const [clientId, setClientId] = useState<string | null>(null);

  const sites = useQuery({
    queryKey: ["sites"],
    queryFn: async () => {
      const { data, response } = await listSitesSitesGet();
      if (data === undefined) throw new Error(`GET /sites falló (${response.status})`);
      return data;
    },
    staleTime: 300_000,
  });

  const plantillas = useDrillTemplates();

  const [selected, setSelected] = useState<string[]>([]);
  const [durationS, setDurationS] = useState(300);
  const [note, setNote] = useState("");
  const [scheduling, setScheduling] = useState(false);
  const [when, setWhen] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);
  // Plantilla elegida. Se guarda el id porque lo que se manda al servidor es
  // `from_template`: la COPIA la hace él, en la misma transacción que lanza. Si
  // el navegador copiara los valores y los mandara sueltos, dos operadores con la
  // pestaña abierta desde ayer lanzarían versiones distintas de la misma
  // plantilla sin que quedara constancia de cuál.
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [nombreNuevo, setNombreNuevo] = useState("");

  const elegida = plantillas.items.find((t) => t.template_id === templateId) ?? null;
  const noUsables = elegida ? sitiosNoUsables(elegida) : 0;

  const usar = (id: string) => {
    const plantilla = plantillas.items.find((t) => t.template_id === id);
    if (plantilla === undefined) return;
    setTemplateId(id);
    // Se PRECARGA el formulario para que se pueda revisar y ajustar antes de
    // lanzar; lo que gana en el servidor es lo explícito, igual que con una
    // agenda armada.
    setSelected(plantilla.sites.map((s) => s.site_id));
    setDurationS(plantilla.duration_s);
    setNote(plantilla.note ?? "");
  };

  const guardarComoPlantilla = () => {
    if (nombreNuevo.trim() === "") {
      setInvalid("PONLE NOMBRE A LA PLANTILLA");
      return;
    }
    setInvalid(null);
    plantillas.crear({
      name: nombreNuevo.trim(),
      site_ids: selected,
      duration_s: durationS,
      note: note.trim() === "" ? null : note.trim(),
    });
    setNombreNuevo("");
  };

  const live = useMemo(
    () => (sites.data ?? []).filter((s) => s.status !== "retired"),
    [sites.data],
  );

  // [A-016 · T-8.07] Los clientes que se pueden elegir son los que tienen sitios
  // vivos a la vista; el nombre sale del catálogo si se pudo leer.
  const nombreCliente = useCallback(
    (id: string): string =>
      clientCatalog.data?.find((t) => t.tenant_id === id)?.name ?? `CLIENTE ${id}`,
    [clientCatalog.data],
  );
  const clientes = useMemo(() => {
    if (!isInternal) return [];
    const ids = [...new Set(live.map((s) => s.tenant_id))];
    return ids
      .map((id) => ({ id, name: nombreCliente(id) }))
      .sort((a, b) => a.name.localeCompare(b.name, "es"));
  }, [isInternal, live, nombreCliente]);
  const sitiosVisibles = isInternal
    ? clientId === null
      ? []
      : live.filter((s) => s.tenant_id === clientId)
    : live;
  const plantillasVisibles = isInternal
    ? clientId === null
      ? []
      : plantillas.items.filter((t) => t.tenant_id === clientId)
    : plantillas.items;
  const elegirCliente = (id: string | null) => {
    setClientId(id);
    // Lo elegido era de OTRO cliente: arrastrarlo mezclaría dos en un simulacro.
    setSelected([]);
    setTemplateId(null);
  };
  // Por qué no se puede lanzar todavía (sólo roles internos): el botón lo dice.
  const bloqueoInterno: string | null = !isInternal
    ? null
    : clientId === null
      ? "ELIGE EL CLIENTE: UN ROL INTERNO NO LANZA UN SIMULACRO A TODA LA PLATAFORMA"
      : selected.length === 0 && templateId === null
        ? "ELIGE LOS SITIOS DEL CLIENTE (O UNA PLANTILLA SUYA): SIN SELECCIÓN NO SE LANZA"
        : null;

  const toggle = (siteId: string) =>
    setSelected((prev) =>
      prev.includes(siteId) ? prev.filter((s) => s !== siteId) : [...prev, siteId],
    );

  /** Lo que se manda, o `null` si el formulario no está listo (y dice por qué). */
  const armar = (): StartDrillInput | null => {
    if (bloqueoInterno !== null) {
      setInvalid(bloqueoInterno);
      return null;
    }
    let scheduledAt: string | null = null;
    if (scheduling) {
      scheduledAt = localToUtcIso(when);
      if (scheduledAt === null) {
        setInvalid("INDICA LA FECHA Y HORA DEL SIMULACRO");
        return null;
      }
      if (Date.parse(scheduledAt) <= Date.now()) {
        setInvalid("LA HORA PROGRAMADA DEBE ESTAR EN EL FUTURO");
        return null;
      }
    }
    setInvalid(null);
    return {
      // Lista vacía = "todos los comandables": el servidor decide quién lo es,
      // el navegador no tiene forma honesta de saberlo (`/sites` no trae
      // gabinetes) y adivinarlo sería inventar la lista de destinatarios.
      siteIds: selected.length === 0 ? null : selected,
      durationS,
      note: note.trim() === "" ? null : note.trim(),
      scheduledAt,
      // Deja constancia de DE DÓNDE salió. El servidor copia los valores; esto
      // es procedencia, y por eso editar la plantilla después no reescribe este
      // simulacro.
      fromTemplate: templateId,
    };
  };

  /** PROGRAMAR: no emite nada, un clic basta. */
  const submit = () => {
    const input = armar();
    if (input !== null) void onSubmit(input);
  };

  /**
   * INICIAR AHORA (segundo clic del botón de dos pasos). Devuelve la promesa del
   * alta cuando la hay: el botón dice «ENVIANDO…» y sólo afirma con el servidor
   * de acuerdo; con `false` se rechaza para que vuelva a reposo.
   */
  const lanzar = (): Promise<void> | undefined => {
    const input = armar();
    if (input === null) return undefined;
    const resultado = onSubmit(input);
    if (resultado === undefined) return undefined;
    return resultado.then((ok) => {
      if (!ok) throw new Error("el simulacro no arrancó");
    });
  };

  return (
    <Modal title="SIMULACRO INSTITUCIONAL" onClose={onClose}>
      <div className="soc-drillform" data-testid="drill-modal">
        <p className="soc-drillform__notice" role="note">
          UN SIMULACRO PINTA EL BANNER NO-REAL Y VOCEA EL AVISO EN LOS GABINETES ELEGIDOS ·{" "}
          <strong>CERO RELÉS</strong> · NO CREA INCIDENTES · UNA ALERTA REAL LO ABORTA
        </p>

        {isInternal && (
          <fieldset className="soc-drillform__group">
            <legend>CLIENTE</legend>
            {/* Los clientes salen de los SITIOS a la vista: mismo dato, mismos
                cuatro estados que la lista de sitios de abajo. */}
            <StateFrame
              label="CLIENTES"
              loading={sites.isPending}
              error={sites.error ? sites.error.message : null}
              onRetry={() => void sites.refetch()}
              empty={!sites.isPending && sites.error === null && clientes.length === 0}
              emptyText="SIN CLIENTES CON SITIOS VISIBLES"
              // Igual que PLANTILLAS: se lee al abrir un diálogo de segundos; no
              // hay dato viejo que rotular y el silencio sería la mentira.
              staleSince={null}
            >
              <label className="soc-meta" htmlFor="drill-client">
                CLIENTE
              </label>
              <select
                id="drill-client"
                className="soc-user__input"
                value={clientId ?? ""}
                onChange={(e) => elegirCliente(e.target.value === "" ? null : e.target.value)}
              >
                <option value="">— ELIGE EL CLIENTE —</option>
                {clientes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <p className="soc-meta" data-testid="drill-cliente" role="note">
                {clientId === null
                  ? "UN ROL INTERNO VE LOS GABINETES DE TODOS LOS CLIENTES: EL SIMULACRO ES DE UNO"
                  : `SIMULACRO PARA ${nombreCliente(clientId).toUpperCase()}`}
              </p>
              {clientCatalog.error !== null && clientCatalog.data === undefined && (
                <p className="soc-meta" data-testid="drill-clientes-error" role="status">
                  SIN NOMBRES DE CLIENTE · {clientCatalog.error.message.toUpperCase()} · SE MUESTRA
                  EL IDENTIFICADOR
                </p>
              )}
            </StateFrame>
          </fieldset>
        )}

        <fieldset className="soc-drillform__group">
          <legend>PLANTILLA</legend>
          <StateFrame
            label="PLANTILLAS"
            loading={plantillas.loading}
            error={plantillas.error}
            onRetry={plantillas.refetch}
            empty={
              !plantillas.loading && plantillas.error === null && plantillasVisibles.length === 0
            }
            emptyText={
              isInternal && clientId === null
                ? "ELIGE PRIMERO EL CLIENTE"
                : "SIN PLANTILLAS GUARDADAS · DEFINE UNA ABAJO Y REÚSALA"
            }
            // El cuarto estado se DECLARA, no se calla: esta lista se pide al
            // abrir el modal y el modal es un diálogo de segundos, así que no
            // hay dato viejo que rotular. El silencio sería la mentira.
            staleSince={null}
          >
            <ul className="soc-drillform__templates" data-testid="drill-templates">
              {plantillasVisibles.map((p) => (
                <li key={p.template_id}>
                  <label>
                    <input
                      type="radio"
                      name="drill-template"
                      aria-label={p.name}
                      checked={templateId === p.template_id}
                      onChange={() => usar(p.template_id)}
                    />
                    <span>{p.name}</span>
                    <span className="soc-meta soc-mono">
                      {p.todos_los_sitios ? "TODOS LOS COMANDABLES" : `${p.sites.length} SITIO(S)`}{" "}
                      · {Math.round(p.duration_s / 60)} MIN
                    </span>
                    {sitiosNoUsables(p) > 0 && (
                      <span className="soc-drillform__warn" role="note">
                        {sitiosNoUsables(p)} SITIO(S) NO UTILIZABLES HOY
                      </span>
                    )}
                  </label>
                  {/* [A-094 · T-8.07] Borrar una plantilla es de dos pasos: un
                      clic suelto se llevaba el macrosimulacro de septiembre. Y
                      ESPERA al DELETE: «BORRADA» sólo si el servidor la borró, y
                      la selección se suelta sólo entonces (con un fallo la
                      plantilla sigue viva y el error lo pinta `mutationError`). */}
                  <ConfirmButton
                    label="BORRAR"
                    ariaLabel={`BORRAR ${p.name}`}
                    armedLabel="CLIC DE NUEVO PARA BORRAR"
                    doneLabel="BORRADA"
                    variant="secondary"
                    disabled={plantillas.pending}
                    onConfirm={() =>
                      plantillas.borrar(p.template_id).then(() => {
                        setTemplateId((actual) => (actual === p.template_id ? null : actual));
                      })
                    }
                  />
                </li>
              ))}
            </ul>

            {/* [T-5.13] Criterio 3. Se declara ANTES de lanzar y con el motivo de
                cada sitio: «no disponible» a secas dejaría al operador sin saber a
                quién llamar —al de inventario, al de campo o al de permisos—. Y no
                se bloquea el lanzamiento: un edificio que perdió el enlace no puede
                dejar sin simulacro a los otros. */}
            {elegida !== null && noUsables > 0 && (
              <div className="soc-drillform__degradada" role="alert" data-testid="drill-degradada">
                <strong>
                  ESTA PLANTILLA YA NO PUEDE USAR {noUsables} DE SUS {elegida.sites.length} SITIO(S)
                </strong>
                <ul>
                  {elegida.sites
                    .filter((s) => s.estado !== "usable")
                    .map((s) => (
                      <li key={s.site_id}>
                        <span className="soc-mono">{s.site_code ?? s.site_id}</span> —{" "}
                        {s.motivo?.toUpperCase()}
                      </li>
                    ))}
                </ul>
                <span className="soc-meta">
                  EL SIMULACRO SE LANZA IGUAL A LOS DEMÁS Y ESTOS QUEDAN EN EL REGISTRO SIN COMANDO
                </span>
              </div>
            )}
          </StateFrame>

          <label className="soc-meta" htmlFor="drill-template-name">
            GUARDAR LO DE ABAJO COMO PLANTILLA
          </label>
          <div className="soc-drillform__save">
            <input
              id="drill-template-name"
              className="soc-user__input"
              value={nombreNuevo}
              maxLength={120}
              placeholder="P.EJ. MACROSIMULACRO SEPTIEMBRE"
              onChange={(e) => setNombreNuevo(e.target.value)}
            />
            {/* [A-016 · T-8.07] `POST /drill-templates` escribe en el tenant DEL
                TOKEN: para un interno, el de TAKAB, y la plantilla no aparecería
                nunca bajo el cliente al que apunta. Se deja de pedir. */}
            <Button
              variant="secondary"
              disabled={plantillas.pending || isInternal}
              title={
                isInternal
                  ? "Un rol interno no guarda plantillas: quedarían en el cliente de TAKAB, no en el elegido"
                  : undefined
              }
              onClick={guardarComoPlantilla}
            >
              GUARDAR
            </Button>
          </div>
          {plantillas.mutationError !== null && (
            <p className="soc-user__error" role="alert">
              {plantillas.mutationError}
            </p>
          )}
        </fieldset>

        <fieldset className="soc-drillform__group">
          <legend>SITIOS</legend>
          <StateFrame
            label="SITIOS"
            loading={sites.isPending}
            error={sites.error ? sites.error.message : null}
            onRetry={() => void sites.refetch()}
            empty={!sites.isPending && sites.error === null && sitiosVisibles.length === 0}
            emptyText={
              isInternal && clientId === null ? "ELIGE PRIMERO EL CLIENTE" : "SIN SITIOS VISIBLES"
            }
          >
            <ul className="soc-drillform__sites">
              {sitiosVisibles.map((s) => (
                <li key={s.site_id}>
                  <label>
                    <input
                      type="checkbox"
                      aria-label={s.name}
                      checked={selected.includes(s.site_id)}
                      onChange={() => toggle(s.site_id)}
                    />
                    <SiteLabel name={s.name} code={s.code} />
                    <span className="soc-meta soc-mono">{s.code}</span>
                  </label>
                </li>
              ))}
            </ul>
            {/* Dentro del marco: para un interno nombra al cliente, que sale del
                mismo dato que la lista. */}
            <p className="soc-meta">
              {selected.length > 0
                ? `${selected.length} SITIO(S) SELECCIONADO(S)`
                : !isInternal
                  ? "SIN SELECCIÓN ⇒ TODOS LOS SITIOS CON GABINETE COMANDABLE DEL TENANT"
                  : clientId === null
                    ? "ELIGE EL CLIENTE Y SUS SITIOS"
                    : templateId !== null
                      ? `PLANTILLA SIN SITIOS ⇒ TODOS LOS COMANDABLES DE ${nombreCliente(clientId).toUpperCase()}`
                      : `SIN SELECCIÓN NO SE LANZA: ELIGE LOS SITIOS DE ${nombreCliente(clientId).toUpperCase()}`}
            </p>
          </StateFrame>
        </fieldset>

        <label className="soc-meta" htmlFor="drill-duration">
          DURACIÓN DE LA VENTANA
        </label>
        <select
          id="drill-duration"
          className="soc-user__input"
          value={durationS}
          onChange={(e) => setDurationS(Number(e.target.value))}
        >
          {DURATIONS.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label}
            </option>
          ))}
        </select>

        <fieldset className="soc-drillform__group">
          <legend>CUÁNDO</legend>
          <label>
            <input
              type="radio"
              name="drill-when"
              checked={!scheduling}
              onChange={() => setScheduling(false)}
            />
            <span>AHORA</span>
          </label>
          <label>
            <input
              type="radio"
              name="drill-when"
              checked={scheduling}
              onChange={() => setScheduling(true)}
            />
            <span>PROGRAMAR</span>
          </label>
          {scheduling && (
            <>
              <label className="soc-meta" htmlFor="drill-when-at">
                FECHA Y HORA (LOCAL)
              </label>
              <input
                id="drill-when-at"
                className="soc-user__input soc-mono"
                type="datetime-local"
                value={when}
                onChange={(e) => setWhen(e.target.value)}
              />
              <p className="soc-meta">
                PROGRAMAR NO EMITE NADA: DEJA EL SIMULACRO ARMADO Y ALGUIEN LO EJECUTA CON UN CLIC A
                LA HORA PREVISTA
              </p>
            </>
          )}
        </fieldset>

        <label className="soc-meta" htmlFor="drill-note">
          NOTA (OPCIONAL — P.EJ. SIMULACRO TRIMESTRAL)
        </label>
        <input
          id="drill-note"
          className="soc-user__input"
          value={note}
          maxLength={500}
          onChange={(e) => setNote(e.target.value)}
        />

        {(invalid !== null || error !== null) && (
          <p className="soc-user__error" role="alert">
            {invalid ?? error?.toUpperCase()}
          </p>
        )}

        <div className="soc-drillform__actions">
          <Button variant="secondary" onClick={onClose}>
            VOLVER
          </Button>
          {scheduling ? (
            <Button
              variant="primary"
              disabled={pending || bloqueoInterno !== null}
              title={bloqueoInterno ?? undefined}
              onClick={submit}
            >
              PROGRAMAR SIMULACRO
            </Button>
          ) : (
            <ConfirmButton
              label="INICIAR AHORA"
              armedLabel="CLIC DE NUEVO PARA INICIAR"
              variant="primary"
              disabled={pending || bloqueoInterno !== null}
              title={bloqueoInterno ?? "Vocea el aviso de simulacro en los gabinetes elegidos"}
              onConfirm={lanzar}
            />
          )}
        </div>
      </div>
    </Modal>
  );
}
