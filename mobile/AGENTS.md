# Agentes: reglas de mobile/

- **Expo cambia rápido:** consulta los docs VERSIONADOS
  <https://docs.expo.dev/versions/v57.0.0/> antes de escribir código de Expo
  (este árbol usa SDK 57 · RN 0.86 · React 19).
- **Fuentes de verdad:** `takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md`
  (spec canónica; §13 = prohibiciones) y `takab-docs/TASKS.md · ## Fase 2`
  (una tarea por sesión). El `CLAUDE.md` de la raíz del repo gobierna commits
  (sin coautoría de IA) y método.
- **No rompas:** nada de cuenta regresiva/magnitud preliminar en crisis
  (§2.1-A); el teléfono jamás habla directo con el gabinete; roles canónicos
  (`occupant`/`brigadista`/`security_guard`); colores/espaciados SOLO desde
  `@takab/design-tokens`; tokens de sesión SOLO en `expo-secure-store`;
  placeholders siempre declaran su tarea (sin stubs silenciosos).
- **Antes de cerrar cualquier cambio:** `npm test` + `npm run typecheck` +
  `npx expo lint` en verde (es el job `mobile` de CI).
