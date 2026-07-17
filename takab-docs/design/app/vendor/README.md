# vendor/ — dependencias pineadas del design canvas

Copias locales de los scripts que `index.html` y `tools/shot.html` necesitan,
para que la regeneración de shots (`tools/regen-shots.mjs`) sea **reproducible
y sin red**. Los bytes son idénticos a los de unpkg, por lo que los atributos
`integrity` de `index.html` siguen siendo válidos cuando el check los sirve
desde aquí.

| Archivo | Origen exacto |
|---|---|
| `react.development.js` | `https://unpkg.com/react@18.3.1/umd/react.development.js` |
| `react-dom.development.js` | `https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js` |
| `babel.min.js` | `https://unpkg.com/@babel/standalone@7.29.0/babel.min.js` |
| `lucide.min.js` | `https://unpkg.com/lucide@1.24.0/dist/umd/lucide.min.js` |

Para actualizar una versión: cambia el pin en `index.html`, re-descarga aquí el
mismo archivo, actualiza el mapa `VENDOR` de `tools/regen-shots.mjs` y (si es
react/react-dom) el atributo `integrity` de `index.html`.

Las **fuentes de Google** (JetBrains Mono, Saira Condensed) no se vendorizan:
se cargan por red al regenerar y, sin red, aplica el fallback del font stack
(el script lo reporta como aviso). Geist ya es local en `../fonts/`.
