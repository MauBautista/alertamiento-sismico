"""[T-9.73 · D-47 · D-30] El movimiento del panel jamás toca el texto de la alerta.

`#banner-alert` parpadeaba con `tk-blink` sobre la caja ENTERA: la opacidad de
un elemento la heredan sus hijos, así que «ALERTA SÍSMICA · PROTÉJASE» bajaba
a 0.35 medio ciclo de cada 900 ms, justo cuando hay que leerla. Eso viola la
condición 1 de D-30 (el texto nunca se mueve). Ahora el fondo es fijo y el pulso
vive en `#banner-alert::after`, una capa sin texto que sólo cambia `opacity`.

Estas guardas leen la HOJA del panel —no el DOM renderizado— porque el defecto
es de declaración: el arnés de render no ejecuta animaciones.
"""

from __future__ import annotations

import re
from pathlib import Path

_INDEX = Path(__file__).resolve().parents[1] / "takab_edge" / "local_api" / "index.html"


def _hoja() -> str:
    html = _INDEX.read_text("utf-8")
    estilo = re.search(r"<style>([\s\S]*?)</style>", html)
    assert estilo, "el panel perdió su hoja de estilos"
    return re.sub(r"/\*[\s\S]*?\*/", "", estilo.group(1))


def _reglas(css: str) -> list[tuple[str, str]]:
    """(selector, cuerpo) de cada regla hoja; los `@media` se abren un nivel."""
    return [(s.strip(), c) for s, c in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def _animadas(css: str) -> list[tuple[str, str]]:
    """Reglas que ENCIENDEN una animación (`animation:none` no cuenta)."""
    out = []
    for sel, cuerpo in _reglas(css):
        for nombre in re.findall(r"animation:\s*([a-z-]+)", cuerpo):
            if nombre != "none":
                out.append((sel, nombre))
    return out


def _capa(css: str) -> str:
    """Cuerpo de la regla BASE de `#banner-alert::after` (la que lleva `content`);
    la del bloque de reducción también se llama así y aparece antes en la hoja."""
    bases = [c for c in re.findall(r"#banner-alert::after\{([^}]*)\}", css) if "content:" in c]
    assert len(bases) == 1, f"se esperaba UNA regla base de la capa, hay {len(bases)}"
    return bases[0]


def test_ninguna_declaracion_tk_blink():
    """El parpadeo de la caja entera desaparece: ni la regla ni su keyframe."""
    hoja = _hoja()
    assert "tk-blink" not in hoja, "sigue declarado el parpadeo de la caja con texto"


def test_el_banner_de_alerta_tiene_el_fondo_FIJO():
    hoja = _hoja()
    base = re.search(r"#banner-alert\{([^}]*)\}", hoja)
    assert base, "el banner de alerta perdió su regla"
    cuerpo = base.group(1).replace(" ", "")
    assert "animation" not in cuerpo, f"la caja con texto vuelve a animarse: {base.group(1)}"
    assert "background:var(--tk-crit)" in cuerpo, "el rojo de actuación real dejó de ser fijo"
    # El ::after se posiciona contra el banner: sin esto la capa cubriría la página.
    assert "position:relative" in cuerpo


def test_el_pulso_de_la_alerta_vive_en_un_pseudo_elemento_sin_texto():
    hoja = _hoja()
    cuerpo = _capa(hoja).replace(" ", "")
    assert "content:''" in cuerpo or 'content:""' in cuerpo
    assert "position:absolute" in cuerpo and "inset:0" in cuerpo
    assert "pointer-events:none" in cuerpo, "la capa del pulso se comería los toques"
    assert re.search(r"animation:tk-[a-z-]+", cuerpo), "la capa no anima nada"


def test_ninguna_animacion_aplica_a_un_elemento_con_texto():
    """Toda regla animada apunta a un pseudo-elemento o al halo VACÍO del punto.

    Es la guarda general de la condición 1: un `animation:` sobre cualquier otro
    selector puede alcanzar texto —de la alerta o de lo que sea— y hace falta
    decidirlo a propósito, no por descuido.
    """
    hoja = _hoja()
    animadas = _animadas(hoja)
    assert animadas, "el panel dejó de animar: la negación pasaría vacía"
    html = _INDEX.read_text("utf-8")
    for sel, nombre in animadas:
        for parte in sel.split(","):
            parte = parte.strip()
            if parte.endswith(("::before", "::after")):
                continue
            # La única excepción: el halo del punto de vida, un <span> vacío.
            assert parte == ".dot.pulse .halo", f"`{parte}` anima `{nombre}` y puede tener texto"
            assert re.search(r'<span class="halo"></span>', html), "el halo dejó de estar vacío"
    # Y en particular, nada dentro del banner de alerta que no sea su capa.
    for sel, _ in animadas:
        if "#banner-alert" in sel:
            assert sel == "#banner-alert::after", f"se anima texto de la alerta: {sel}"


def test_los_keyframes_de_la_capa_solo_mueven_opacity_o_transform():
    hoja = _hoja()
    nombre = re.search(r"animation:\s*([a-z-]+)", _capa(hoja)).group(1)
    kf = re.search(r"@keyframes " + re.escape(nombre) + r"\{([\s\S]*?\})\}", hoja)
    assert kf, f"la capa anima `{nombre}` y no existe su @keyframes"
    props = set(re.findall(r"([a-z-]+)\s*:", kf.group(1)))
    assert props, "keyframes vacíos"
    assert props <= {"opacity", "transform"}, f"la capa anima algo que mueve layout: {props}"


def test_reducir_movimiento_esta_presente_y_apaga_la_capa():
    """El `*{animation:none}` global NO alcanza a `::after`: `*` no selecciona
    pseudo-elementos, así que la capa necesita su propia línea en el bloque."""
    hoja = _hoja()
    bloque = re.search(
        r"@media \(prefers-reduced-motion:\s*reduce\)\{((?:[^{}]*\{[^{}]*\})+)\}", hoja
    )
    assert bloque, "el panel dejó de honrar `prefers-reduced-motion`"
    reglas = dict(_reglas(bloque.group(1)))
    assert "*" in reglas and "animation:none!important" in reglas["*"].replace(" ", "")
    capa = reglas.get("#banner-alert::after")
    assert capa is not None, "la reducción no alcanza a la capa del pulso"
    assert "animation:none!important" in capa.replace(" ", "")
    # Se apaga QUIETA y PUESTA: el borde queda visible, no desaparece.
    base = _capa(hoja).replace(" ", "")
    reposo = re.search(r"opacity:([\d.]+)", base)
    assert reposo is None or float(reposo.group(1)) >= 0.5, (
        "sin animación la capa quedaría invisible o casi"
    )
