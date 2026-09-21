#!/usr/bin/env python3
"""Guardas de los documentos de gobierno que hablan de la capa narrativa (T-7.27).

Nacieron porque el escéptico de `T-7.27` encontró que los documentos le decían al
cliente TRES cosas que el propio código y el propio aviso de privacidad desmienten,
y una de ellas estaba en el párrafo que se le LEE EN VOZ ALTA antes de firmar.
Ninguna daba error: un documento no compila.

   CENSO_DE_CITAS   la tabla «Quién cita / Qué cita» de RESIDENCIA se deriva del
                    barrido del repositorio, en vez de enumerarse a mano — que es
                    como nació desactualizada respecto de su propio diff.
   CITAS_DEL_AVISO  toda cita entre « » atribuida al aviso de privacidad existe
                    LITERAL y en EL PÁRRAFO QUE SE LE ATRIBUYE. Es la que caza el
                    defecto de origen: se citaba como «la finalidad declarada» una
                    oración que ni era literal ni era la finalidad — era el
                    propósito del párrafo de encargados.
   TOPE_DE_FOTOS    ninguna frase que enuncie el tope de fotografías de la capa
                    narrativa puede callar su ámbito: son seis por INFORME.
   POR_CLIENTE      nada afirma un interruptor «por cliente» que hoy no existe.

⚠️ QUÉ **NO** HACE, y va en el nombre para que nadie le suponga más:
   · No comprueba que el `§n` citado exista ni que diga lo que el citador cree.
     Eso es lectura humana.
   · `TOPE_DE_FOTOS` y `POR_CLIENTE` **vigilan frases, no entienden castellano**:
     cazan las formas que ya se escribieron mal y exigen la que las corrige.
   · **No corre en CI.** Engancharla al gate toca `api/tests/test_docs_consistency.py`,
     fuera del alcance del cambio que la trajo. Se corre a mano:

       python3 takab-docs/tools/guardas-de-citas.py

Salida: 0 si todo cuadra; 1 con el detalle de cada divergencia.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
RESIDENCIA = RAIZ / "takab-docs" / "RESIDENCIA-DE-DATOS-TAKAB.md"
AVISO = RAIZ / "api" / "src" / "takab_api" / "privacy" / "texts" / "aviso_es_mx.json"

#: Lo que el barrido no mira. `graphify-out/` es un volcado derivado del propio
#: repositorio: contarlo duplicaría cada cita.
EXCLUIDOS = ("node_modules", ".git", "graphify-out", "dist", "build", ".venv")


def ficheros_de_texto() -> list[Path]:
    """Ficheros versionados, que es lo único que cuenta como «lo que dice el repo»."""
    # `--others --exclude-standard` incluye lo NUEVO todavía sin comitear. Sin
    # eso la guarda nace ciega al fichero que la ficha acaba de estrenar: medido
    # el 2026-09-21 con `avisoIA.ts`, que era exactamente ese caso.
    salida = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    out: list[Path] = []
    for rel in salida.split("\0"):
        if not rel or any(part in EXCLUIDOS for part in Path(rel).parts):
            continue
        p = RAIZ / rel
        if not p.is_file():
            continue
        try:
            p.read_text(encoding="utf8")
        except (UnicodeDecodeError, OSError):
            continue
        out.append(p)
    return out


def rel(p: Path) -> str:
    return str(p.relative_to(RAIZ))


# ===========================================================================
# CENSO_DE_CITAS
# ===========================================================================

#: Forma canónica de la regla 2 del propio censo: para citar a otro documento se
#: nombra el fichero. Un `§6.3` pelado desde fuera es invisible aquí — y lo fue:
#: `D-32` tenía uno y el censo contaba una cita donde había dos.
CITA = re.compile(r"RESIDENCIA-DE-DATOS-TAKAB\.md\s*§(\d+(?:\.\d+)*)")

#: La tabla del documento. Se lee de sus propias filas, no de una copia aquí.
FILA = re.compile(
    r"^\|\s*(?P<quien>.+?)\s*\|\s*`§(?P<sec>[\d.]+)`\s*\|\s*(?P<veces>\d+)\s*\|\s*$"
)
#: El fichero de la columna «Quién cita», con o sin enlace markdown.
FICHERO_EN_FILA = re.compile(r"`([^`]+\.(?:md|ts|tsx|py))`")


def barrido_de_citas() -> dict[tuple[str, str], int]:
    cuenta: dict[tuple[str, str], int] = {}
    for p in ficheros_de_texto():
        if p == RESIDENCIA:
            continue  # una autorreferencia no es una cita externa
        for sec in CITA.findall(p.read_text(encoding="utf8")):
            cuenta[(rel(p), sec)] = cuenta.get((rel(p), sec), 0) + 1
    return cuenta


def censo_declarado() -> dict[tuple[str, str], int]:
    dentro = False
    declarado: dict[tuple[str, str], int] = {}
    for linea in RESIDENCIA.read_text(encoding="utf8").splitlines():
        if linea.startswith("| Quién cita |"):
            dentro = True
            continue
        if dentro and not linea.startswith("|"):
            break
        m = FILA.match(linea)
        if not m:
            continue
        f = FICHERO_EN_FILA.search(m.group("quien"))
        if f is None:
            continue
        nombre = f.group(1)
        # Los `.md` de la tabla se escriben sin ruta: viven en `takab-docs/`.
        ruta = nombre if "/" in nombre else f"takab-docs/{nombre}"
        clave = (ruta, m.group("sec"))
        declarado[clave] = declarado.get(clave, 0) + int(m.group("veces"))
    return declarado


def censo_de_citas() -> list[str]:
    real, dicho = barrido_de_citas(), censo_declarado()
    if not dicho:
        return [
            "CENSO_DE_CITAS: no se pudo leer NINGUNA fila de la tabla — el censo mide el vacío"
        ]
    fallos = []
    for clave in sorted(set(real) | set(dicho)):
        a, b = dicho.get(clave, 0), real.get(clave, 0)
        if a != b:
            fallos.append(
                f"CENSO_DE_CITAS: {clave[0]} · §{clave[1]} — la tabla dice {a}, el barrido ve {b}"
            )
    return fallos


# ===========================================================================
# CITAS_DEL_AVISO
# ===========================================================================

#: `«…»` con la marca del párrafo detrás. La cita es el ÚLTIMO `«…»` que cierra
#: antes del marcador, así que el marcador puede llevar el suyo sin ambigüedad.
MARCA = re.compile(r"\(aviso de privacidad\s*·\s*párrafo\s*«([^»]+)»\)")
ANGULAR = re.compile(r"«([^»]+)»")


def parrafos_del_aviso() -> dict[str, str]:
    body = json.loads(AVISO.read_text(encoding="utf8"))["notice"]["body"]
    out: dict[str, str] = {}
    for bloque in body.split("\n\n"):
        cabeza = bloque.split(".", 1)[0].strip()
        out[cabeza] = re.sub(r"\s+", " ", bloque).strip()
    return out


def citas_del_aviso() -> list[str]:
    parrafos = parrafos_del_aviso()
    if not parrafos:
        return [
            "CITAS_DEL_AVISO: el aviso no tiene párrafos — la guarda mediría el vacío"
        ]
    fallos, vistas = [], 0
    for p in ficheros_de_texto():
        if p.resolve() == Path(__file__).resolve():
            continue  # el propio marcador de esta docstring no es una cita
        # Una cita larga se parte en varias líneas y, dentro de un blockquote o
        # de una lista, cada línea nueva llega con su `>`, su `-` o su sangría
        # pegados. Se quitan ANTES de comparar: si no, ninguna cita de más de un
        # renglón sería «literal» jamás y la guarda gritaría siempre.
        plano = aplanar(p.read_text(encoding="utf8"))
        angulares = [(m.start(), m.end(), m.group(1)) for m in ANGULAR.finditer(plano)]
        for m in MARCA.finditer(plano):
            titulo = m.group(1).strip()
            previas = [a for a in angulares if a[1] <= m.start()]
            if not previas:
                fallos.append(
                    f"CITAS_DEL_AVISO: {rel(p)} — marca sin cita «…» delante ({titulo})"
                )
                continue
            cita = re.sub(r"\s+", " ", previas[-1][2]).strip()
            vistas += 1
            if titulo not in parrafos:
                fallos.append(
                    f"CITAS_DEL_AVISO: {rel(p)} — el aviso no tiene párrafo «{titulo}»"
                )
                continue
            if cita not in parrafos[titulo]:
                fallos.append(
                    f"CITAS_DEL_AVISO: {rel(p)} — «{cita[:70]}…» NO está literal "
                    f"en el párrafo «{titulo}» del aviso"
                )
    if vistas == 0:
        fallos.append("CITAS_DEL_AVISO: ninguna cita marcada — la guarda no mide nada")
    return fallos


# ===========================================================================
# TOPE_DE_FOTOS
# ===========================================================================

CANTIDAD = re.compile(
    r"\b(?:hasta|máximo|como máximo|un máximo de)\s+(?:seis|6)\b", re.I
)
FOTO = re.compile(r"fotograf\w*|\bfotos\b", re.I)
#: Se parte por PUNTO Y ESPACIO y por nada más. Con `;` y `:` dentro del
#: separador, la oración de `D-32` —«…y las fotos del reporte de daños, con
#: estas condiciones: como máximo seis por reporte…»— se rompía justo entre el
#: sustantivo y la cifra, y la guarda no la veía: una exención que nunca se
#: ejerce es código muerto con aspecto de red de seguridad.
FIN_DE_FRASE = re.compile(r"(?<=[.!?])\s")


def aplanar(texto: str) -> str:
    """Sin énfasis, sin marcas de cita ni de lista al empezar renglón, en una línea."""
    plano = re.sub(r"[*`]", "", texto)
    plano = re.sub(r"\n[ \t]*(?:>[ \t]*)*(?:[-*·][ \t]+)?", " ", plano)
    return re.sub(r"\s+", " ", plano)


#: Excepciones, cada una con su razón, la FRASE concreta que exime y un ANCLA en
#: el fichero. Tres cosas y no una: una exención de fichero entero habría dejado
#: pasar la frase siguiente que alguien escribiera mal ahí dentro, y una sin
#: ancla sobrevive a la desaparición del texto que la justificaba.
EXENTOS: dict[str, dict[str, str]] = {
    "takab-docs/DECISIONES-MAURICIO.md": {
        "en": "como máximo seis por reporte",
        "porque": (
            "es el texto ORIGINAL de `D-32` y la bitácora no reescribe decisiones; "
            "lo construido quedó MÁS ESTRECHO y se anota debajo sin tocarlo"
        ),
        "exige": "Lo construido son seis por INFORME, no seis por reporte",
    },
    "takab-docs/TASKS.md": {
        "en": "contenido multimodal",
        "porque": (
            "la ficha dice «máximo seis» sin ámbito; TASKS.md quedó fuera del "
            "alcance del cambio que trajo esta guarda y va a `pendiente`"
        ),
        "exige": "fotos como contenido multimodal (máximo seis,",
    },
}


def tope_de_fotos() -> list[str]:
    fallos, medidas, exenciones_usadas = [], 0, set()
    for p in ficheros_de_texto():
        if p.resolve() == Path(__file__).resolve():
            continue  # este fichero CITA las frases malas para cazarlas
        plano = aplanar(p.read_text(encoding="utf8"))
        for frase in FIN_DE_FRASE.split(plano):
            if not (CANTIDAD.search(frase) and FOTO.search(frase)):
                continue
            medidas += 1
            if re.search(r"\binforme\b", frase, re.I):
                continue
            exento = EXENTOS.get(rel(p))
            if exento is not None and exento["en"] in frase:
                exenciones_usadas.add(rel(p))
                if exento["exige"] not in plano:
                    fallos.append(
                        f"TOPE_DE_FOTOS: {rel(p)} está exento «{exento['porque']}» pero ya NO "
                        f"contiene el texto que lo justifica ({exento['exige']!r})"
                    )
                continue
            fallos.append(
                f"TOPE_DE_FOTOS: {rel(p)} enuncia el tope sin decir el ámbito "
                f"(son seis por INFORME): …{frase.strip()[:130]}…"
            )
    if medidas == 0:
        fallos.append(
            "TOPE_DE_FOTOS: no se encontró NINGUNA frase del tope — la guarda no mide"
        )
    for ruta in EXENTOS:
        if ruta not in exenciones_usadas:
            fallos.append(
                f"TOPE_DE_FOTOS: la exención de {ruta} ya no la ejerce ninguna frase — "
                "sobra, y una exención que nadie usa acaba tapando la de al lado"
            )
    return fallos


# ===========================================================================
# POR_CLIENTE
# ===========================================================================

#: La forma exacta que estaba escrita dos veces en `mobile/`. Es una guarda de
#: CADENA y se llama así: caza la regresión literal, no la idea.
POR_CLIENTE = re.compile(r"se enciende (?:por despliegue )?y por cliente", re.I)
#: Si algún día `select_provider` recibe el tenant, la afirmación deja de ser
#: falsa y esta guarda sobra. Se comprueba para que no siga mordiendo de balde.
SELECT_PROVIDER = RAIZ / "api" / "src" / "takab_api" / "narrative" / "__init__.py"


def por_cliente() -> list[str]:
    if SELECT_PROVIDER.exists():
        firma = re.search(
            r"def select_provider\((.*?)\)", SELECT_PROVIDER.read_text("utf8"), re.S
        )
        if firma and re.search(r"tenant|site_id", firma.group(1)):
            return []  # ya existe el interruptor por cliente: la frase sería cierta
    return [
        f"POR_CLIENTE: {rel(p)} afirma que la capa narrativa se enciende «por cliente», y hoy "
        "el interruptor es del despliegue entero (`select_provider` no recibe tenant)"
        for p in ficheros_de_texto()
        if POR_CLIENTE.search(re.sub(r"[\n*`]", " ", p.read_text(encoding="utf8")))
    ]


def main() -> int:
    fallos = censo_de_citas() + citas_del_aviso() + tope_de_fotos() + por_cliente()
    if fallos:
        print(f"GUARDAS DE CITAS · {len(fallos)} divergencia(s):\n")
        for f in fallos:
            print(f"  · {f}")
        return 1
    print(
        "GUARDAS DE CITAS · censo, citas del aviso, tope de fotos e interruptor: cuadran."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
