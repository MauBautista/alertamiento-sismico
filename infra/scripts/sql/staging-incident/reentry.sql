-- Dictamen FIRMADO (signed_by no nulo) y habitable (inhabit_monitor).
-- `basis` es jsonb NOT NULL sin default ⇒ '{}'. Append-only ⇒ fila nueva.
INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by)
VALUES (:'tenant'::uuid, :'iid'::uuid, 'inhabit_monitor', '{}'::jsonb, gen_random_uuid());
