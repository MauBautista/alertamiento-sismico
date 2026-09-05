"""Una cifra medida se cita, no se copia (T-5.22).

EL DEFECTO QUE CIERRA
---------------------
`contacto SASMEX → relé` es la cifra más citada del producto y estaba
**replicada a mano en ocho documentos**. Ocho copias no son una fuente: son ocho
sitios donde el número puede desactualizarse por separado y nadie se entera —
que es exactamente lo que le pasó al conteo de decisiones (`H-39`) y al espejo
de la matriz RBAC (`T-5.28`).

LA REGLA, Y POR QUÉ ES ESTA Y NO «PROHIBIDO REPETIRLA»
------------------------------------------------------
Prohibir el número habría sido inmanejable: hay documentos que **deben** citarlo
—el de entrega, el de consulta legal, el manual—. Lo que no puede haber es una
cita **sin fuente**. Así que la regla es: *si una cifra medida aparece en un
documento, ese documento tiene que enlazar a `MEDICIONES-TAKAB.md`*.

El día que la cifra cambie, `git grep` sobre el enlace da la lista exacta de
quién hay que revisar — y hoy esa lista no existía.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DOCS = _REPO / "takab-docs"
_FUENTE = _DOCS / "MEDICIONES-TAKAB.md"

#: Las cifras medidas que el producto cita. La clave es la cadena tal como
#: aparece; el valor, qué es — para que el fallo diga de qué habla.
CIFRAS: dict[str, str] = {
    "6.65 ms": "contacto WR-1 → reflejo (2026-07-14)",
    "4.16 ms": "contacto WR-1 → reflejo en frío (2026-07-31)",
    "214 ms": "commit del incidente → frame en la consola",
}

#: Documentos exentos, **con su razón**. Se comparan por igualdad: uno nuevo no
#: se cuela, y uno que deje de existir pone el test en rojo.
EXENTOS: dict[str, str] = {
    "MEDICIONES-TAKAB.md": "es la fuente: aquí es donde vive el número",
    "INFORME-V1-COMERCIAL.md": (
        "es una instantánea FECHADA de la auditoría del 2026-09-02 y no se toca: "
        "su cabecera dice que el estado vivo de cada hallazgo es su ficha en TASKS.md. "
        "Reescribirlo para que enlace aquí falsearía lo que se auditó aquel día."
    ),
    "PLAN-V1-COMERCIAL.md": (
        "espejo del bloque de fichas de TASKS.md, y sus fichas citan el número "
        "al DIAGNOSTICAR el defecto. Cuando TASKS.md enlaza, este también."
    ),
}


def _documentos() -> list[Path]:
    """Los `.md` de producto. `design/` queda fuera: son maquetas y volcados."""
    return sorted(
        p
        for p in _DOCS.rglob("*.md")
        if "design/" not in p.relative_to(_DOCS).as_posix() and "archive/" not in p.as_posix()
    )


def test_la_fuente_existe_y_trae_las_tres_cifras():
    """Sin esto, el barrido pasaría en verde por no encontrar nada que citar."""
    texto = _FUENTE.read_text(encoding="utf-8")
    for cifra, que in CIFRAS.items():
        assert cifra in texto, f"la fuente no trae {cifra} ({que})"


def test_el_barrido_ve_los_documentos():
    docs = _documentos()
    assert len(docs) >= 15, f"el barrido se quedó ciego: solo vio {len(docs)}"


def test_toda_cita_de_una_cifra_ENLAZA_a_la_fuente():
    sin_fuente: list[str] = []
    for doc in _documentos():
        rel = doc.relative_to(_DOCS).as_posix()
        if rel in EXENTOS:
            continue
        texto = doc.read_text(encoding="utf-8")
        citadas = [c for c in CIFRAS if c in texto]
        if citadas and "MEDICIONES-TAKAB.md" not in texto:
            sin_fuente.append(f"  · {rel} cita {citadas} y no enlaza a la fuente")

    assert not sin_fuente, (
        "CIFRAS MEDIDAS CITADAS SIN FUENTE. Ocho copias a mano no son una fuente: "
        "son ocho sitios donde el número se desactualiza por separado. Añade un "
        "enlace a `MEDICIONES-TAKAB.md` en el documento, o declara la exención en "
        "`EXENTOS` CON SU RAZÓN:\n" + "\n".join(sin_fuente)
    )


def test_cada_exencion_lleva_su_razon_y_el_documento_existe():
    for rel, razon in EXENTOS.items():
        assert (_DOCS / rel).is_file(), f"exento inexistente: {rel}"
        assert len(razon) > 40, f"{rel}: la razón es demasiado corta para serlo"


def test_la_fuente_NO_llama_percentil_a_una_observacion_unica():
    """La otra mitad de la ficha: donde se declara un percentil, o se mide o se dice.

    `214 ms` y las dos del reflejo son observaciones ÚNICAS. Llamarlas p95 sería
    inventarse una distribución que nadie midió.
    """
    texto = _FUENTE.read_text(encoding="utf-8")
    assert "observaciones únicas" in texto or "observación" in texto
    # Y ninguna línea pega un percentil a una de las tres cifras.
    for linea in texto.splitlines():
        if any(c in linea for c in CIFRAS) and re.search(r"\bp\d{2}\b", linea):
            assert "nunca se ha medido" in linea or "sería falso" in linea, (
                f"una cifra y un percentil en la misma línea sin deslinde: {linea.strip()}"
            )
