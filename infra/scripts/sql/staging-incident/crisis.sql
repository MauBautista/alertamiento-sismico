-- [T-6.18] Un incidente FRESCO por corrida, y el anterior cerrado.
--
-- Antes el id era una constante (`d4000000-…-0001`) y `crisis` REABRÍA el mismo
-- incidente. En cuanto una corrida pasaba por `reentry`, ese incidente quedaba
-- con un dictamen firmado — y `dictamens` es append-only, así que ahí se queda
-- para siempre—. La derivación de `mobile_site.py` busca el dictamen POR
-- INCIDENTE y `reentry_approved` gana a `alert_active`: a partir de ese momento
-- `PHASE=crisis` dejaba de producir la toma de crisis y el flujo 01 no podía
-- pasar. Cerrar y abrir uno nuevo devuelve el arnés a lo que promete.
-- ⚠️ [T-7.51] `closed_at` NO es opcional. Sin él, este UPDATE dejaba filas con
-- `state='closed'` y la hora en nulo, y el dictamen imprime «CIERRE: EN CURSO»
-- cuando ese campo falta: el papel pericial de un incidente cerrado afirmaba que
-- seguía abierto. Se midieron TRES así en la nube dev el 2026-09-17, y una de
-- ellas era un incidente REAL ingerido de `gw-dev-0001`.
--
-- ⚠️ Y LO QUE ESTO SIGUE HACIENDO, que el software no puede decidir solo: el
-- `SITE_ID` por defecto del arnés es `d1000000-…-0000` = `site-dev`, **el sitio
-- del gabinete real de Puebla**. Así que esta línea cierra incidentes de
-- OPERACIÓN, no sólo los que el arnés abre. Separar el sitio del arnés está
-- fichado; hasta entonces, al menos el cierre queda fechado.
UPDATE incidents SET state = 'closed', closed_at = now()
 WHERE site_id = :'site'::uuid AND state <> 'closed';

-- severity/state/trigger según el CHECK de schema.sql; event_uuid NOT NULL UNIQUE.
-- `sasmex` no es decorativo: la derivación descarta el incidente que no AUTORIZA
-- evacuación (`autoriza_evacuacion`), y un instrumental de una estación no lo hace.
INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, event_id,
                       opened_at, severity, state, trigger)
VALUES (:'iid'::uuid, :'euuid'::uuid, :'tenant'::uuid, :'site'::uuid, NULL,
        now(), 'warning', 'open', 'sasmex')
ON CONFLICT (incident_id) DO UPDATE SET state = 'open';

-- Tier de crisis. gateway_id es uuid NOT NULL SIN FK ⇒ cualquiera vale.
INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, prev_tier, new_tier)
VALUES (now(), :'tenant'::uuid, :'site'::uuid, gen_random_uuid(), 'normal', 'evacuate_or_hold');
