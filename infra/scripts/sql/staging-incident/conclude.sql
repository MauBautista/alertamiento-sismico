-- `rule_evaluations` es append-only: la fase se "cambia" insertando una fila
-- más reciente, jamás con UPDATE.
INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, prev_tier, new_tier)
VALUES (now(), :'tenant'::uuid, :'site'::uuid, gen_random_uuid(), 'evacuate_or_hold', 'normal');
