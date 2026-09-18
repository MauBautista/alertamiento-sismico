-- ============================================================================
-- TAKAB · LA GUARDA DEL ARNÉS (T-7.52 · D-34 §4) — sin excepción y sin bandera
--
-- El arnés de los E2E móviles ABORTA si el sitio destino tiene un gabinete.
-- Corre ANTES que cualquier otra fase, y su fallo detiene el script entero
-- (`ON_ERROR_STOP=1` ⇒ exit 3).
--
-- ⚠️ SIN RELOJ, y no es un detalle: la ficha y `D-34` decían «un gateway con
-- LATIDO RECIENTE». Eso deja el agujero justo donde más duele — mientras
-- `gw-dev-0001` está CAÍDO (ha pasado dos veces: la energía del 28-jul y el hilo
-- de reconexión que lo dejó mudo), Puebla no tiene latido y la guarda dejaría
-- pasar al arnés contra el sitio real. Además obligaría a un segundo umbral de
-- «vivo» fuera de `sin_enlace_min`, que es justo la clase de divergencia que
-- este repositorio ya tiene fichada.
--
-- La condición es EXISTENCIA: si el sitio tiene **cualquier** fila en
-- `gateways`, no es un sitio de arnés. Es estrictamente más fuerte que el
-- criterio, no puede desincronizarse de nada, y casa con la definición que da
-- `D-34` del sitio del arnés: «uno que ningún gabinete usa».
--
-- ⚠️ POR QUÉ `set_config` Y NO `:'site'` DENTRO DEL BLOQUE. **Medido el
-- 2026-09-18 contra Postgres**: psql NO interpola sus variables dentro de un
-- cuerpo `$$ … $$` —llegan literales—, pero el `_sustituir` del arnés de pruebas
-- SÍ las sustituye. Una guarda escrita de la forma obvia saldría **verde en CI y
-- llegaría INERTE a la nube**: exactamente el patrón de espejo que este repo ya
-- ha pagado cuatro veces (el `GRANT` que sólo falla en la nube, el import del
-- SDK que tumba dos suites a «0 test»…). El valor entra FUERA del bloque y se
-- lee DENTRO con `current_setting`.
-- ============================================================================

SELECT set_config('takab.arnes_site', :'site', false);

DO $guarda$
DECLARE
  destino uuid := current_setting('takab.arnes_site')::uuid;
  gabinetes int;
  codigo text;
BEGIN
  SELECT count(*) INTO gabinetes FROM gateways WHERE site_id = destino;
  IF gabinetes > 0 THEN
    SELECT code INTO codigo FROM sites WHERE site_id = destino;
    -- ⚠️ `USING MESSAGE` y concatenación, NO los marcadores de formato de `RAISE`.
    -- El arnés de pruebas corre este mismo fichero por **psycopg**, que toma el
    -- signo de porcentaje como marcador SUYO y revienta con «only 's', 'b', 't'
    -- are allowed» antes de llegar aquí.
    --
    -- ⚠️ Y LOS COMENTARIOS VIAJAN DENTRO: psycopg escanea la cadena entera, así
    -- que ni siquiera se puede explicar el problema usando el signo. Es la misma
    -- trampa que `T-7.47` midió con los documentos de SSM, en otro lenguaje.
    --
    -- Medido el 2026-09-18: con el signo dentro, las dos pruebas de aborto
    -- pasaban por la razón EQUIVOCADA — casaban el texto contra el SQL que el
    -- error viene citando, no contra la excepción de la guarda.
    RAISE EXCEPTION USING MESSAGE =
      'ARNÉS ABORTADO: el sitio destino ' || destino
      || ' (' || coalesce(codigo, 'sin código') || ') tiene ' || gabinetes
      || ' gabinete(s). Este script CIERRA todos los incidentes abiertos del sitio, así que '
      || 'contra un sitio con gabinete cerraría incidentes de OPERACIÓN — es lo que pasó '
      || 'hasta T-7.51 con Puebla. Usa el sitio del arnés (site-e2e-900) o siémbralo con '
      || '`make cloud-e2e-site`. No hay bandera para saltarse esto.';
  END IF;
END
$guarda$;
