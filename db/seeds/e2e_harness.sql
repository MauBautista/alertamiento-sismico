-- ============================================================================
-- TAKAB · Seed del SITIO DEL ARNÉS de los E2E móviles (T-7.52 · D-34) — IDEMPOTENTE
--
-- ⚠️ POR QUÉ EXISTE. Hasta el 2026-09-17 el arnés de los E2E móviles apuntaba,
-- por defecto, a `site-dev` — **Puebla, el sitio del gabinete REAL `gw-dev-0001`**.
-- Su `reset`/`crisis` cierran TODOS los incidentes abiertos del sitio, así que
-- el arnés cerraba incidentes de OPERACIÓN. Lo destapó `T-7.51`: tres incidentes
-- cerrados sin hora, cuyo dictamen pericial decía «EN CURSO».
--
-- `D-34` decidió el remedio: **sitio propio para el arnés**, con su propio
-- ocupante; el de la demostración se queda en Puebla · `PB-A`.
--
-- ⚠️ ESTE SEED NO VA EN `deploy.sh`, igual que `demo_red.sql`: se aplica y se
-- retira a mano (`make cloud-e2e-site` / `make cloud-e2e-site-down`). Un sitio de
-- pruebas re-sembrado en cada despliegue acaba pareciendo inventario de verdad.
--
-- ⚠️ EL CÓDIGO `site-e2e-900` NO ES ARBITRARIO. La consola deriva la cinta de
-- «no es un edificio real» del PREFIJO del código con patrones anclados
-- (`web/src/features/fleet/datosDeDemostracion.ts`). Un código que no case con
-- ninguno se pinta como un edificio REAL, que es el error en la dirección peor.
-- Si este código cambia, cambia allí — y su censo lo caza.
--
-- El bloque de UUIDs `…900` está libre: `prod_fleet` usa `…0000`, `sim_fleet`
-- `…0001-0020` y `demo_red` `…0101-0103` (verificado, no es una suposición).
--
-- Requiere `prod_fleet.sql` aplicado antes (crea el tenant).
-- ============================================================================

BEGIN;

-- --- El sitio ----------------------------------------------------------------
-- Sin gateway A PROPÓSITO, y es lo que hace segura la guarda de `guarda.sql`:
-- el arnés aborta contra cualquier sitio que TENGA un gabinete, sin mirar el
-- reloj. Si algún día este sitio recibe uno, el arnés dejará de poder correr
-- aquí — y eso es lo correcto, no un defecto.
INSERT INTO sites (site_id, tenant_id, code, name, criticality, geom) VALUES
  ('d1000000-0000-0000-0000-000000000900', 'd0000000-0000-0000-0000-000000000001',
   'site-e2e-900', 'Arnés de pruebas E2E · NO ES UN INMUEBLE',
   'low',
   ST_SetSRID(ST_MakePoint(-98.2400, 19.0100), 4326)::geography)
ON CONFLICT (site_id) DO UPDATE
  SET code = EXCLUDED.code, name = EXCLUDED.name, criticality = EXCLUDED.criticality;

-- --- Su zona -----------------------------------------------------------------
-- `evac_policy = 'evacuate'` porque el flujo `01a-crisis` del Pixel comprueba
-- que la app pinta EVACÚE: la zona del arnés tiene que decir lo mismo que decía
-- `PB-A`, o el flujo acreditado dejaría de reproducir lo que acreditó.
INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code, evac_policy) VALUES
  ('d2000000-0000-0000-0000-000000000900', 'd0000000-0000-0000-0000-000000000001',
   'd1000000-0000-0000-0000-000000000900', 'Zona de arnés E2E', 'E2E-A', 'evacuate')
ON CONFLICT (zone_id) DO UPDATE
  SET name = EXCLUDED.name, level_code = EXCLUDED.level_code,
      evac_policy = EXCLUDED.evac_policy;

COMMIT;
