-- [T-7.03] La acción que SÍ despierta un teléfono.
--
-- El resto de subcomandos mueve la FASE que la app deriva al sondear
-- (`mobile-state`), y eso no despierta a nadie: el sondeo no corre con la app
-- detrás. El único camino a un push real es una fila de `incident_actions` de
-- las dos clases que el notificador busca —`headcount_notify` (T-2.11) y
-- `dictamen_signed` (T-2.12)—, y ninguna nacía aquí.
--
-- `headcount_notify` es la de menor privilegio de las dos: no firma nada, no
-- cambia la fase y su significado —«falta gente por reportarse»— es exactamente
-- lo que el ensayo quiere enseñar sonando en el bolsillo.
--
-- Append-only (trigger `forbid_update_delete`) ⇒ fila nueva cada vez. La
-- idempotencia la pone el notificador con su índice único (action_id, channel),
-- así que repetir el subcomando encola UN push por acción, que es lo correcto:
-- dos peticiones de pase de lista son dos avisos.
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
VALUES (:'iid'::uuid, :'tenant'::uuid, 'headcount_notify', 'system:staging',
        jsonb_build_object('unreported', 0, 'requested_by', 'seed_staging_incident'));
