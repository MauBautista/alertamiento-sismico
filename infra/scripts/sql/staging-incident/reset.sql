-- `incidents` NO es append-only ⇒ cerrar por UPDATE devuelve la fase a idle.
-- Se cierran TODOS los abiertos del sitio: desde T-6.18 cada corrida de
-- `crisis` abre uno nuevo, así que cerrar solo el último dejaría cola.
UPDATE incidents SET state = 'closed'
 WHERE site_id = :'site'::uuid AND state <> 'closed';
