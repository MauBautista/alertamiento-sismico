# Identidad visual de TAKAB Ailert

Los maestros de esta carpeta son la **única** fuente de la marca. Los iconos que
usan la consola, el panel del gabinete y la app **se derivan** de aquí con
`generar.py`; no se editan a mano, no se descargan y no se rehacen en Figma cada
vez. Si alguno se toca a mano, la próxima ejecución lo pisa — que es exactamente
lo que se quiere.

```bash
uv run --with pillow python shared/brand/generar.py
```

Los resultados **se comitean**: ni la consola, ni el gabinete, ni la app deben
necesitar Pillow para construirse.

## Paleta

Leída de `sistema-de-identidad.png`, que es la hoja que entregó el diseño.

| | hex | dónde |
|---|---|---|
| Navy de marca | `#0B1D3A` | fondo de los iconos que **vuelan solos**: favicon, icono de app |
| Azul | `#123A7A` | del isotipo positivo |
| Rojo epicentro | `#FF2D1A` | el punto rojo del isotipo; es la marca, no un adorno |
| Blanco | `#FFFFFF` | isotipo y logotipo negativos |

⚠️ **El navy de marca (`#0B1D3A`) NO es el de las superficies del producto**
(`--tk-surface-0` = `#0E2336`). La consola, el panel y el splash de la app llevan
el segundo porque viene de su propio sistema de diseño. Donde el icono se pega a
una superficie del producto se usa `#0E2336`; donde vuela solo, el de marca.

Tipografía secundaria de la identidad: **Montserrat**. El producto no la usa —
la consola y el panel van con Geist/JetBrains Mono, y eso es deliberado.

## Maestros

| archivo | qué es | uso |
|---|---|---|
| `isotipo-negativo.png` | la K con los anillos y el epicentro, en blanco | **el caballo de batalla**: de aquí salen casi todos los iconos |
| `isotipo-positivo.png` | la misma K en navy/azul | para fondos claros; hoy no lo usa ningún producto |
| `logotipo-negativo.png` | «TAKAB AILERT» en blanco+rojo | topbar y pantallas de estado de la consola |
| `logotipo-positivo.png` | «TAKAB AILERT» en navy+rojo | fondos claros |
| `imagotipo-negativo.png` | isotipo + logotipo + traza de sismograma, en blanco | piezas grandes; **no** para tamaños pequeños (ver abajo) |
| `imagotipo-positivo.png` | el mismo, en navy+rojo, con transparencia | fondos claros; hoy no lo usa ningún producto |
| `imagotipo-positivo-sin-traza-sobre-blanco.jpg` | la variante **sin** la traza, JPEG sobre blanco | referencia: es la única copia de esa variante |
| `isotipo.svg` | trazado monocromo del isotipo | referencia vectorial |
| `isotipo-negativo-monocromatico.png` | el monocromo tal como lo entregó diseño | referencia |
| `sistema-de-identidad.png` | la hoja de marca completa, a resolución íntegra | documentación: aquí se leen los hex |
| `logotipo-takab-technology.png` | la marca de la EMPRESA, no la del producto | ninguno; vivía en la consola hasta que entró la identidad del producto |

Los originales llegaron en `/img` (con un `.rar` de 7,8 MB y duplicados en
`.jfif`). Todo lo que traía de único está aquí; `/img` queda fuera de git.

### Los límites del juego de maestros

- **El imagotipo positivo con transparencia llegó el 2026-09-05** y sustituyó al
  JPEG sobre blanco con el que se abrió esta carpeta. Sigue faltando la variante
  **sin traza** con transparencia; de esa solo hay JPEG sobre blanco, y
  recortarle el fondo deja halos, así que no se hace aquí: se pide a diseño.
- **El SVG es una silueta monocroma**: pierde el epicentro rojo y la separación
  de color. Por eso los iconos salen de los PNG y no del SVG.

## Reglas que no son estéticas

Están implementadas en `generar.py` y vigiladas por tests. Se documentan aquí
porque el porqué no cabe en el código:

1. **El icono de iOS no puede llevar canal alfa.** La App Store rechaza el envío
   y el error llega días después de subirlo. `icon.png` se aplana sobre navy y se
   guarda en RGB.
2. **El icono adaptativo de Android se recorta.** El sistema solo garantiza el
   66 % central (72dp de 108dp); el primer plano se dibuja al 52 % del lienzo.
3. **El favicon necesita fondo propio.** El isotipo negativo es blanco y el
   positivo es navy: cada uno desaparece en la mitad de los temas de navegador.
   Se compone sobre navy, que aguanta los dos.
4. **Cada tamaño del `.ico` se dibuja a su resolución.** Dejar que el formato
   reescale uno solo emborrona la pestaña, que es el sitio donde más se mira.
5. **A 16 px la ocupación sube a 0.86.** Es un ajuste óptico: con el aire de los
   tamaños grandes, la K —la única lectura que sobrevive ahí— se pierde.
6. **El imagotipo no baja de tamaño.** A 40 px de alto la traza del sismograma se
   convierte en suciedad; por eso la topbar lleva el logotipo, no el imagotipo.

## Dónde acaba cada cosa

| destino | archivo | derivado de |
|---|---|---|
| consola | `web/public/favicon.ico` (16/32/48) | isotipo negativo sobre navy |
| consola | `web/public/apple-touch-icon.png`, `icon-192.png`, `icon-512.png` | ídem |
| consola | `web/src/assets/logotipo-takab-ailert.png` | logotipo negativo |
| gabinete | `edge/takab_edge/local_api/favicon.png` | isotipo negativo sobre navy |
| app | `mobile/assets/images/icon.png` (**sin alfa**) | isotipo negativo sobre navy |
| app | `mobile/assets/images/favicon.png` | ídem |
| app | `mobile/assets/images/android-icon-{foreground,background,monochrome}.png` | isotipo negativo |
| app | `mobile/assets/images/splash-icon.png` | isotipo negativo, transparente |

El panel del gabinete sirve su favicon por la **whitelist** de `_load_static`,
no por una ruta abierta: el panel se sirve sin build y sin red, así que el icono
viaja empaquetado con el módulo igual que las fuentes.
