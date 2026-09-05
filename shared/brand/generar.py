#!/usr/bin/env python3
"""Deriva TODOS los iconos de producto de los maestros de `shared/brand/`.

POR QUÉ ESTO ES UN SCRIPT Y NO UNA CARPETA DE PNG SUELTOS
---------------------------------------------------------
Los iconos viven en tres sitios que nadie mira a la vez —la consola, el panel
del gabinete y la app— y cada uno los quiere en un tamaño y con una regla
distinta. Hechos a mano, la primera vez salen bien y la segunda divergen: uno se
queda con el logotipo viejo y no se nota hasta que un cliente lo ve. Aquí la
identidad se declara UNA vez y el resto se deriva.

Los resultados SÍ se comitean: ni la consola, ni el gabinete, ni la app deben
necesitar Pillow para construirse. Este script solo hace falta cuando cambian
los maestros.

    uv run --with pillow python shared/brand/generar.py

REGLAS QUE NO SON ESTÉTICAS, SON REQUISITOS
-------------------------------------------
- **El icono de iOS no puede tener canal alfa.** La App Store rechaza el envío,
  y el error llega días después de subirlo. Por eso `icon.png` se aplana sobre
  el navy de marca y se guarda en RGB, no en RGBA.
- **El icono adaptativo de Android se recorta.** El sistema garantiza solo el
  66 % central del lienzo (72dp de 108dp): lo que se salga puede desaparecer
  bajo una máscara circular. El primer plano se dibuja al 52 % del lienzo.
- **El favicon necesita fondo propio.** El isotipo negativo es blanco y el
  positivo es navy: cualquiera de los dos desaparece en la mitad de los temas de
  navegador. Se compone sobre el navy de marca, que funciona en los dos.
"""

from __future__ import annotations

import pathlib

from PIL import Image

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MARCA = RAIZ / "shared" / "brand"

# Paleta oficial, leída de `sistema-de-identidad.png`.
NAVY = (11, 29, 58)  # #0B1D3A
AZUL = (18, 58, 122)  # #123A7A
ROJO = (255, 45, 26)  # #FF2D1A

# El navy de las SUPERFICIES de producto (`--tk-surface-0`) no es el de marca:
# la consola y el panel llevan #0E2336 desde su propio sistema de diseño, y el
# splash de la app hereda ese mismo valor. Donde el icono se pega a una
# superficie del producto se usa este; donde vuela solo (favicon, icono de app)
# se usa el de marca.
SUPERFICIE = (14, 35, 54)  # #0E2336


def maestro(nombre: str) -> Image.Image:
    return Image.open(MARCA / nombre).convert("RGBA")


def encaja(arte: Image.Image, lienzo: int, ocupacion: float) -> Image.Image:
    """Centra `arte` dentro de un cuadrado de `lienzo` px ocupando `ocupacion`.

    La ocupación se mide sobre el lado MAYOR del arte, así que un isotipo casi
    cuadrado y un logotipo apaisado quedan ópticamente equivalentes.
    """
    objetivo = int(lienzo * ocupacion)
    escala = objetivo / max(arte.width, arte.height)
    nuevo = arte.resize(
        (max(1, round(arte.width * escala)), max(1, round(arte.height * escala))),
        Image.LANCZOS,
    )
    fuera = Image.new("RGBA", (lienzo, lienzo), (0, 0, 0, 0))
    fuera.paste(nuevo, ((lienzo - nuevo.width) // 2, (lienzo - nuevo.height) // 2), nuevo)
    return fuera


def sobre(fondo: tuple[int, int, int], arte: Image.Image) -> Image.Image:
    plano = Image.new("RGBA", arte.size, (*fondo, 255))
    plano.alpha_composite(arte)
    return plano


def silueta(arte: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """Monocromo a partir del ALFA del maestro, no del SVG.

    El SVG trazado pierde el epicentro rojo; el alfa del isotipo negativo
    conserva la forma entera —anillos incluidos— y es lo que Android quiere para
    su capa monocroma de iconos temáticos.
    """
    fuera = Image.new("RGBA", arte.size, (*color, 0))
    fuera.putalpha(arte.getchannel("A"))
    return fuera


def guarda(im: Image.Image, destino: pathlib.Path, *, rgb: bool = False) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if rgb:
        im = im.convert("RGB")
    im.save(destino, optimize=True)
    print(f"  {destino.relative_to(RAIZ)!s:56} {im.size[0]}x{im.size[1]}  {destino.stat().st_size // 1024} KB")


def main() -> None:
    iso_neg = maestro("isotipo-negativo.png")
    logo_neg = maestro("logotipo-negativo.png")

    print("consola (web):")
    # Favicon: fondo propio para sobrevivir a los dos temas de navegador.
    #
    # Cada tamaño se DIBUJA a su resolución en vez de dejar que el ICO reescale
    # uno solo: partiendo del de 16 px, Pillow interpolaba hacia ARRIBA para 32 y
    # 48 y el icono llegaba emborronado a la pestaña. El grande va primero
    # porque es el que Pillow toma de base para cualquier tamaño que le falte.
    # La ocupación sube al bajar el tamaño (ajuste ÓPTICO, no aritmético): a
    # 16 px el aire alrededor se come la única lectura que queda, la de la K.
    # Más de 0.86 tampoco: el trazo toca el borde y se pierde el marco.
    ico = {n: sobre(NAVY, encaja(iso_neg, n, oc)).convert("RGB") for n, oc in ((48, 0.78), (32, 0.80), (16, 0.86))}
    ico[48].save(
        RAIZ / "web/public/favicon.ico",
        sizes=[(48, 48), (32, 32), (16, 16)],
        append_images=[ico[32], ico[16]],
    )
    print(f"  {'web/public/favicon.ico':56} 16/32/48  {(RAIZ / 'web/public/favicon.ico').stat().st_size // 1024} KB")
    guarda(sobre(NAVY, encaja(iso_neg, 180, 0.72)), RAIZ / "web/public/apple-touch-icon.png", rgb=True)
    guarda(sobre(NAVY, encaja(iso_neg, 192, 0.74)), RAIZ / "web/public/icon-192.png")
    guarda(sobre(NAVY, encaja(iso_neg, 512, 0.74)), RAIZ / "web/public/icon-512.png")
    # Logotipo de la topbar y de las pantallas de estado: la consola es
    # dark-only (`--tk-surface-0`), así que SIEMPRE va el negativo.
    ancho = 880
    guarda(
        logo_neg.resize((ancho, round(logo_neg.height * ancho / logo_neg.width)), Image.LANCZOS),
        RAIZ / "web/src/assets/logotipo-takab-ailert.png",
    )

    print("panel del gabinete (edge):")
    # Un único PNG servido por la whitelist del panel. 32 px: el panel se sirve
    # sin red y no conviene engordarlo por un icono de pestaña.
    guarda(sobre(NAVY, encaja(iso_neg, 32, 0.80)), RAIZ / "edge/takab_edge/local_api/favicon.png", rgb=True)

    print("app movil:")
    # iOS: SIN alfa (ver cabecera).
    guarda(sobre(NAVY, encaja(iso_neg, 1024, 0.62)), RAIZ / "mobile/assets/images/icon.png", rgb=True)
    guarda(sobre(NAVY, encaja(iso_neg, 48, 0.78)), RAIZ / "mobile/assets/images/favicon.png")
    # Adaptativo de Android: el primer plano se recorta al 66 % ⇒ 52 %.
    guarda(encaja(iso_neg, 512, 0.52), RAIZ / "mobile/assets/images/android-icon-foreground.png")
    guarda(
        Image.new("RGBA", (512, 512), (*NAVY, 255)),
        RAIZ / "mobile/assets/images/android-icon-background.png",
    )
    guarda(
        silueta(encaja(iso_neg, 432, 0.52), (255, 255, 255)),
        RAIZ / "mobile/assets/images/android-icon-monochrome.png",
    )
    # Splash: `imageWidth: 76` en app.json ⇒ 3x = 228 px, sobre `SUPERFICIE`.
    guarda(encaja(iso_neg, 228, 0.92), RAIZ / "mobile/assets/images/splash-icon.png")


if __name__ == "__main__":
    main()
