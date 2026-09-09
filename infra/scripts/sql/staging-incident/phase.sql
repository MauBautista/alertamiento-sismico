-- Réplica de la derivación de `mobile_site.py` para el operador que corre el
-- sembrador. La VERDAD es el endpoint `GET /sites/{id}/mobile-state`; esta copia
-- existe para no tener que levantar la app solo para mirar. Que no divergiera
-- no lo garantizaba nadie hasta T-6.18: ahora
-- `api/tests/api/test_seed_staging_incident.py` compara las dos en las cuatro
-- fases, y si se separan el job `api` se pone rojo.
SELECT 'phase=' || CASE
  WHEN NOT EXISTS (SELECT 1 FROM incidents WHERE site_id = :'site'::uuid AND state <> 'closed')
    THEN 'idle'
  WHEN (SELECT (signed_by IS NOT NULL) AND status IN ('normal_operation','inhabit_monitor')
          FROM dictamens WHERE incident_id = NULLIF(:'iid','')::uuid ORDER BY created_at DESC LIMIT 1)
    THEN 'reentry_approved'
  WHEN (SELECT new_tier FROM rule_evaluations WHERE site_id = :'site'::uuid ORDER BY ts DESC LIMIT 1) = 'normal'
    THEN 'shaking_concluded'
  ELSE 'alert_active'
END
|| '   | incidente=' || COALESCE(NULLIF(:'iid',''), '∅')
|| '   | tier=' || COALESCE((SELECT new_tier FROM rule_evaluations WHERE site_id = :'site'::uuid ORDER BY ts DESC LIMIT 1), '∅')
|| '   | roster=' || (SELECT count(*) FROM user_zone_assignments WHERE site_id = :'site'::uuid)::text
|| '   | no_reportados=' || (
     SELECT count(*) FROM user_zone_assignments uza
     WHERE uza.site_id = :'site'::uuid
       AND NOT EXISTS (SELECT 1 FROM life_checkins lc
                       WHERE lc.incident_id = NULLIF(:'iid','')::uuid AND lc.user_id = uza.user_id))::text;
