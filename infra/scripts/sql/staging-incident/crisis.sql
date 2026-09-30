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
-- [T-7.52] El sitio por defecto ya NO es el de Puebla: es `site-e2e-900`, y
-- `guarda.sql` aborta contra cualquier sitio que tenga gabinete. Esta línea ya no
-- puede cerrar incidentes de operación.
--
-- ⚠️ [T-9.33] `INCIDENT_ID` fijado a un incidente que YA es terminal (lo clasificó un
-- `crisis` o un `reset` anterior) no se puede reabrir: el motor lo cerraría en su
-- siguiente pasada «por clasificación» y la fase caería a `idle` sin decir por qué.
-- Tampoco se puede desclasificar: la tabla es append-only, y una clase no terminal
-- sería falsa. Así que se ABORTA, con la salida escrita. Mismo patrón que
-- `guarda.sql`: el valor entra por `set_config`, porque psql no sustituye dentro de
-- un bloque, y el mensaje va sin marcadores de formato.
SELECT set_config('takab.arnes_iid', :'iid', false);

DO $reabrir$
DECLARE
  objetivo uuid := current_setting('takab.arnes_iid')::uuid;
  clase text;
BEGIN
  SELECT cc.classification INTO clase FROM incident_classifications cc
   WHERE cc.incident_id = objetivo
     AND NOT EXISTS (SELECT 1 FROM incident_classifications s
                      WHERE s.supersedes_id = cc.classification_id)
   ORDER BY cc.classified_at DESC, cc.classification_id DESC LIMIT 1;
  IF clase IN ('falso_positivo', 'prueba', 'reproduccion') THEN
    RAISE EXCEPTION USING MESSAGE =
      'ARNÉS ABORTADO: el incidente ' || objetivo || ' ya está clasificado como '
      || clase || ', y el motor lo cerraría al reabrirlo. Corre `crisis` sin '
      || 'INCIDENT_ID para abrir uno nuevo.';
  END IF;
END
$reabrir$;

-- ⚠️ [T-9.33] Y ANTES DE CERRAR, SE CLASIFICA, como hace `reset`. Cerrar a secas
-- dejaba vinculando lo que las corridas anteriores firmaron: un NO HABITAR no
-- caduca (`T-9.04`), y por D-49 el bloqueo persistente de OTRO incidente del sitio
-- manda. Medido en el Pixel el 2026-09-30: la corrida confirmó un dictamen
-- habitable y el panel siguió diciendo «NO HABITAR» por el `9d7525e3` de una
-- corrida vieja. En el sitio del arnés todo incidente ES una prueba; la
-- clasificación terminal `prueba` lo dice, y un terminal no dice nada del
-- edificio. El incidente que se va a abrir queda fuera (y uno que se REABRE con
-- `INCIDENT_ID` ya pasó la comprobación de arriba). Es el MISMO bloque que
-- `reset.sql`: lo compara `test_crisis_clasifica_como_reset`.
INSERT INTO incident_classifications
       (tenant_id, incident_id, classification, note, classified_by, supersedes_id)
SELECT i.tenant_id, i.incident_id, 'prueba', 'crisis del arnés e2e (T-9.33)',
       gen_random_uuid(), v.classification_id
  FROM incidents i
  LEFT JOIN LATERAL (
    SELECT cc.classification_id, cc.classification FROM incident_classifications cc
     WHERE cc.incident_id = i.incident_id
       AND NOT EXISTS (SELECT 1 FROM incident_classifications s
                        WHERE s.supersedes_id = cc.classification_id)
     ORDER BY cc.classified_at DESC, cc.classification_id DESC LIMIT 1
  ) v ON true
 WHERE i.site_id = :'site'::uuid
   AND i.incident_id <> :'iid'::uuid
   AND (v.classification IS NULL
        OR v.classification NOT IN ('falso_positivo', 'prueba', 'reproduccion'));

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
