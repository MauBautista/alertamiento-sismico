# E2E de la app móvil (T-2.14 · Maestro)

Flujos end-to-end de los caminos críticos de la spec §4.2. Corren contra un
**development build** (no Expo Go: la app usa módulos nativos — biometría,
SQLCipher, cámara). Requieren un occupant y un táctico sembrados en Cognito
(pool de ocupantes `us-east-2_P818WYSql`) y un sitio con incidente activo en
staging.

## Requisitos
- [Maestro](https://maestro.mobile.dev) instalado (`curl -Ls "https://get.maestro.mobile.dev" | bash`).
- Build de desarrollo instalado en un dispositivo/emulador: `eas build --profile development`
  o `npx expo run:android` / `run:ios`.
- Variables en `.maestro/.env` (NO commitear): `OCCUPANT_EMAIL`, `OCCUPANT_PASSWORD`,
  `TACTICO_EMAIL`, `TACTICO_PASSWORD`, `SITE_CODE`.

## Correr
```bash
maestro test .maestro/            # toda la carpeta
maestro test .maestro/01-crisis-checkin-sync.yaml
```

## Cobertura (criterios de aceptación T-2.14)
| Flujo | Archivo | Acceptance |
|---|---|---|
| Crisis → check-in → sync | `01-crisis-checkin-sync.yaml` | crisis takeover, check-in encolado, sync visible |
| Táctico: foto → daños → Triage | `02-tactico-foto-danos.yaml` | evidencia forense + reporte llegan a Triage con hash |
| Dictamen → liberación | `03-dictamen-liberacion.yaml` | consola-firma → push → PDF → reingreso liberado |
| Pánico quórum-de-2 | `04-panico-quorum.yaml` | 2 votos/30 s ⇒ sirena; NO es alerta sísmica |
| Offline en modo avión | `05-offline-avion.yaml` | captura+formulario offline → sync al reconectar |

> Estos flujos son la **evidencia ejecutable de `GATE-HW`** (ver
> `takab-docs/runbooks/RUNBOOK-cierre-fase2.md`): se corren en dispositivo real
> antes de cerrar la fase, incluyendo la verificación de que los modos de prueba
> del gabinete (T-1.67/T-1.69) NO disparan pantallas de crisis en el móvil.
