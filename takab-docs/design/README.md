# Referencias de diseño (T-1.45)

Artefactos exploratorios del diseño de la consola SOC que vivían sueltos en la
raíz del monorepo (hallazgo bajo #7 del análisis, regla de estructura §11).
**No son código de producción**: la consola real vive en `web/` y NO los
importa — son la referencia visual de la que se derivó.

- `SOC Console.html` + `SOC.css` + `SOC-tabs.css` — maqueta estática original.
- `jsx/` — componentes de la exploración pre-Vite.
- `design-system/` y `Design System/` — tokens, capturas y el PDF del pitch
  visual (`TAKAB · Seismic Monitor SOC · Print.pdf`). El `.zip` interno queda
  fuera de git (`.gitignore`).
