-- `incidents` NO es append-only ⇒ cerrar por UPDATE devuelve la fase a idle.
-- Se cierran TODOS los abiertos del sitio: desde T-6.18 cada corrida de
-- `crisis` abre uno nuevo, así que cerrar solo el último dejaría cola.
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
