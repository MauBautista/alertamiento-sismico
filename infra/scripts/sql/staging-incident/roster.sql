-- Ocupante SINTÉTICO no reportado, para que el pase de lista tenga a quién
-- marcar. `role` no tiene CHECK; el pase de lista cuenta TODOS los roles.
INSERT INTO user_zone_assignments (user_id, tenant_id, site_id, zone_id, role)
VALUES (:'uid'::uuid, :'tenant'::uuid, :'site'::uuid, :'zone'::uuid, 'occupant')
ON CONFLICT (user_id, site_id) DO NOTHING;
