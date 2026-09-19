-- Réplica de la derivación de `mobile_site.py` para el operador que corre el
-- sembrador. La VERDAD es el endpoint `GET /sites/{id}/mobile-state`; esta copia
-- existe para no tener que levantar la app solo para mirar. Que no divergiera
-- no lo garantizaba nadie hasta T-6.18: ahora
-- `api/tests/api/test_seed_staging_incident.py` compara las dos en las cuatro
-- fases, y si se separan el job `api` se pone rojo.
-- ⚠️ [T-7.55] LA AUTORIZACIÓN SOBREVIVE AL CIERRE. Desde `D-33` el motor cierra
-- el incidente en cuanto se firma el dictamen —medido: TRES SEGUNDOS—, y el
-- endpoint sigue declarando `reentry_approved` durante `reentry_declare_s`
-- (8 h). Sin esta rama, la réplica diría `idle` donde la app dice «REINGRESO
-- AUTORIZADO», que es justo la divergencia que `T-6.18` puso a vigilar.
--
-- El `8 hours` es el ESPEJO de `Settings.reentry_declare_s`, y que no se separen
-- lo comprueba `test_la_ventana_de_reingreso_no_se_separa_del_ajuste`.
SELECT 'phase=' || CASE
  WHEN NOT EXISTS (SELECT 1 FROM incidents WHERE site_id = :'site'::uuid AND state <> 'closed')
    THEN CASE WHEN EXISTS (
           SELECT 1 FROM incidents i
            JOIN LATERAL (SELECT status, signed_by FROM dictamens dd
                           WHERE dd.incident_id = i.incident_id
                           ORDER BY dd.created_at DESC LIMIT 1) d ON true
            WHERE i.site_id = :'site'::uuid AND i.state = 'closed'
              AND i.closed_at IS NOT NULL
              AND i.closed_at > now() - interval '8 hours'
              AND d.signed_by IS NOT NULL
              AND d.status IN ('normal_operation','inhabit_monitor'))
         THEN 'reentry_approved' ELSE 'idle' END
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
