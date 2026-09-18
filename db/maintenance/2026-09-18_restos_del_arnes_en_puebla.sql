-- ============================================================================
-- TAKAB · Retirar los ocupantes SINTÉTICOS que el arnés dejó en Puebla (T-7.52)
--
-- ⚠️ QUÉ SE MIDIÓ, el 2026-09-18, contra la base de la nube dev:
--
--     ocupantes_sinteticos_en_puebla = 3   (todos en la zona PB-A)
--     TOTAL_ocupantes_en_puebla      = 4
--     incidentes_abiertos_en_puebla  = 2
--
-- O sea que **3 de las 4 personas que el sistema cree que hay en ese edificio no
-- existen**. En un pase de lista real —con dos incidentes abiertos ahí ahora
-- mismo— ese sitio reportaría tres ausentes inventados, y el brigadista los
-- buscaría. `site-dev` es Puebla, el sitio del gabinete REAL `gw-dev-0001`.
--
-- Los sembró `infra/scripts/seed_staging_incident.sh roster` cuando su `SITE_ID`
-- por defecto todavía era el de Puebla, con `ON CONFLICT DO NOTHING`, así que se
-- fueron acumulando corrida tras corrida sin que nada avisara. `T-7.52` movió ese
-- default a `site-e2e-900` y puso una guarda que aborta contra cualquier sitio con
-- gabinete; esto limpia lo que quedó de antes.
--
-- ⚠️ EL ALCANCE ES POR UUID SINTÉTICO, no por fecha ni por zona. El arnés los
-- numera `d5000000-0000-0000-0000-%` (`roster.sql`), que es una forma que ningún
-- alta real produce. Acotar por fecha borraría a quien se hubiera enrolado ese día;
-- acotar sólo por zona se llevaría al ocupante real, que está en la misma `PB-A`.
--
-- Se ejecuta a mano, una vez. No es una migración: no describe el esquema, y
-- re-correrla en una base limpia no tiene que hacer nada.
-- ============================================================================

BEGIN;

-- La guarda: si esto no borra exactamente lo sintético, no se borra nada. Un
-- `DELETE` sobre las asignaciones de un edificio con gente dentro no se lanza a
-- ciegas.
DO $limpieza$
DECLARE
  sinteticos int;
  reales int;
  borrados int;
BEGIN
  SELECT count(*) INTO sinteticos
    FROM user_zone_assignments uza
    JOIN zones z ON z.zone_id = uza.zone_id
   WHERE z.site_id = 'd1000000-0000-0000-0000-000000000000'
     AND uza.user_id::text LIKE 'd5000000-0000-0000-0000-%';

  SELECT count(*) INTO reales
    FROM user_zone_assignments uza
    JOIN zones z ON z.zone_id = uza.zone_id
   WHERE z.site_id = 'd1000000-0000-0000-0000-000000000000'
     AND uza.user_id::text NOT LIKE 'd5000000-0000-0000-0000-%';

  RAISE NOTICE 'Puebla antes: sinteticos=%, reales=%', sinteticos, reales;

  IF reales = 0 THEN
    RAISE EXCEPTION USING MESSAGE =
      'ABORTADO: no queda NINGUN ocupante real en Puebla. O el patron sintetico esta '
      'casando de mas, o alguien vacio el sitio: en los dos casos hay que mirarlo a '
      'mano antes de borrar nada.';
  END IF;

  DELETE FROM user_zone_assignments uza
   USING zones z
   WHERE z.zone_id = uza.zone_id
     AND z.site_id = 'd1000000-0000-0000-0000-000000000000'
     AND uza.user_id::text LIKE 'd5000000-0000-0000-0000-%';
  GET DIAGNOSTICS borrados = ROW_COUNT;

  IF borrados <> sinteticos THEN
    RAISE EXCEPTION USING MESSAGE =
      'ABORTADO: se contaron ' || sinteticos || ' sinteticos y el DELETE toco ' ||
      borrados || '. La transaccion se deshace.';
  END IF;

  RAISE NOTICE 'Puebla despues: retirados=%, quedan reales=%', borrados, reales;
END
$limpieza$;

COMMIT;
