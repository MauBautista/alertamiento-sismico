-- `incidents` NO es append-only ⇒ cerrar por UPDATE devuelve la fase a idle.
-- Se cierran TODOS los abiertos del sitio: desde T-6.18 cada corrida de
-- `crisis` abre uno nuevo, así que cerrar solo el último dejaría cola.
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
-- ⚠️ [T-7.55] EL CIERRE VA RETRODATADO, y no es un truco: desde que la
-- autorización de reingreso sobrevive al cierre durante `reentry_declare_s` (8 h),
-- un `reset` con `closed_at = now()` dejaría el sitio diciendo «REINGRESO
-- AUTORIZADO» toda esa ventana — o sea, `reset` dejaría de resetear. Y no se puede
-- borrar el dictamen: `dictamens` es append-only a propósito. Retrodatar el cierre
-- es decir lo que de verdad se quiere decir: «esto ya es historia vieja».
-- Los 30 días tienen que superar la ventana, y que no se separen lo comprueba
-- `test_la_ventana_de_reingreso_no_se_separa_del_ajuste`.
--
-- ⚠️ [T-7.62] Y EL `WHERE` YA NO MIRA EL `state`, que es donde `T-7.55` se quedó
-- corta sin que nada lo viera. Aquel arreglo retrodató el cierre precisamente
-- para que el sitio volviera a `idle`, pero lo ató a `state <> 'closed'` — y el
-- incidente de una corrida de `reentry` **ya viene cerrado**: lo cierra el motor
-- por `dictamen_signed` tres segundos después de firmar (`D-33`,
-- `incident/lifecycle.py`). Así que el `UPDATE` lo saltaba, su `closed_at` se
-- quedaba en `now()` y la autorización de reingreso sobrevivía las 8 h de
-- `reentry_declare_s`: **`reset` no reseteaba**.
--
-- Medido en la nube el 2026-09-20 corriendo la tanda de diez del flujo `03`:
--     tras reset:    phase=reentry_approved   ← debería ser idle
--     tras crisis:   phase=alert_active
--     tras reentry:  phase=reentry_approved
--
-- Ahora se retrodata TODO incidente del sitio, cerrado o no, que es lo que
-- aquella línea quería decir. Sobre los ya retrodatados el UPDATE es un no-op
-- de contenido, así que sigue siendo idempotente.
--
-- ⚠️ Y el `state = 'closed'` se mantiene en el SET aunque la mayoría ya lo
-- estén: quitarlo dejaría de cerrar los abiertos, que es la otra mitad del
-- trabajo de este fichero.
--
-- La guarda de arriba (`guarda.sql`) sigue siendo lo que impide que esto toque
-- un sitio con gabinete: ampliar el alcance del UPDATE no amplía el de la
-- purga, porque el sitio ya estaba acotado antes de llegar aquí.
UPDATE incidents SET state = 'closed', closed_at = now() - interval '30 days'
 WHERE site_id = :'site'::uuid
   AND (state <> 'closed' OR closed_at IS NULL OR closed_at > now() - interval '30 days');

-- ⚠️ [T-9.04] RETRODATAR YA NO BASTA, y la línea de arriba se queda sólo por lo
-- que dice («esto ya es historia vieja»). Desde `T-9.04` las 8 h de «REINGRESO
-- AUTORIZADO» cuentan desde la FIRMA del dictamen —no desde el cierre— y un NO
-- HABITAR firmado NO caduca: retrodatar `closed_at` no mueve ninguna de las dos
-- cosas, y `dictamens` es append-only. Medido en la suite: tras `reentry` +
-- `reset` el endpoint seguía en `reentry_approved`, que es el falso verde de
-- `T-7.62` otra vez.
--
-- Lo que el arnés quiere decir es que estos incidentes FUERON PRUEBAS, y eso ya
-- tiene su palabra: la clasificación terminal `prueba` («prueba, mantenimiento o
-- puesta en marcha», `incident/classification.py`). Un incidente terminal no
-- dice nada del edificio (`reingreso.deriva_reingreso`): ni autoriza, ni bloquea,
-- ni deja un pendiente. Append-only como el resto: si ya había una clasificación
-- vigente no terminal, ésta la SUSTITUYE (`supersedes_id`), igual que corregir
-- desde la consola. Idempotente: un incidente que ya es terminal no se toca.
--
-- ⚠️ La lista de terminales es el espejo de `TERMINALES`; si se separa, lo peor
-- que pasa es re-clasificar como `prueba` algo que ya era terminal. Y el sitio
-- sigue acotado por `guarda.sql`: nunca uno con gabinete.
INSERT INTO incident_classifications
       (tenant_id, incident_id, classification, note, classified_by, supersedes_id)
SELECT i.tenant_id, i.incident_id, 'prueba', 'reset del arnés e2e (T-9.04)',
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
   AND (v.classification IS NULL
        OR v.classification NOT IN ('falso_positivo', 'prueba', 'reproduccion'));
