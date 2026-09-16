"""[T-7.36] El papel dice con qué se ABRIÓ el incidente, no con qué escaló.

`incidents.trigger` lo sobrescribe el UPSERT de la ingesta con el disparo de la
última escalada. El dictamen —documento con peso legal— lo presentaba como el
origen («se abrió … a partir de X») y el mismo campo decidía el tiempo de aviso
ganado. Las dos direcciones del error son reales y opuestas, y las dos se
comprueban aquí sobre el DOCUMENTO GENERADO, no sobre una constante.

Cómo se comprueba: espiando `MembretePDF.text_of`, que es por donde pasa todo el
texto que se dibuja. El PDF no se puede leer (flujo comprimido y fuentes
embebidas ⇒ el texto viaja como índices de glifo), y comparar bytes pasa en verde
sobre cualquier defecto porque la portada imprime `content_sha256()`, que se
mueve con cualquier cambio del modelo.
"""

from __future__ import annotations

from takab_api.documentos.membrete import MembretePDF
from takab_api.dictamen.model import TRIGGER_LABELS
from takab_api.dictamen.pdf import render
from tests.dictamen.test_pdf import model

#: Abrió el receptor SASMEX; después la red corroboró y la ingesta pisó `trigger`.
_ESCALADO = {"opened_trigger": "sasmex", "trigger": "quorum"}
_SIN_ESCALAR = {"opened_trigger": "sasmex", "trigger": "sasmex"}


def _texto(m, variante: str) -> str:
    visto: list[str] = []
    # ⚠️ [T-7.21] Se espía la BASE `MembretePDF`, no `TakabPDF`. Parchear la
    # SUBCLASE y luego «restaurar» le instala un atributo PROPIO que sombrea la base
    # PARA SIEMPRE —medido: `'text_of' in TakabPDF.__dict__` pasa de False a True—, y
    # a partir de ahí cualquier otro espía puesto sobre el membrete recoge CERO. No
    # rompía nada mientras el único espía era éste; con el espía general de
    # `tests/documentos/test_membrete_compartido.py` sale «verde en aislado, rojo en
    # la suite». Lo vigila `test_la_subclase_NO_sombrea_el_text_of_de_la_base`.
    original = MembretePDF.text_of

    def espia(self: MembretePDF, value: str) -> str:
        visto.append(value)
        return original(self, value)

    MembretePDF.text_of = espia  # type: ignore[method-assign]
    try:
        render(m, variante)
    finally:
        MembretePDF.text_of = original  # type: ignore[method-assign]
    return "\n".join(visto)


def test_sin_escalada_no_se_INVENTA_una() -> None:
    """El 99 % de los incidentes no escala: no puede aparecer una frase de escalada."""
    texto = _texto(model(**_SIN_ESCALAR), "technical")
    assert "escaló" not in texto.lower(), "declara una escalada que no ocurrió"


def test_el_EJECUTIVO_atribuye_la_apertura_a_quien_la_abrio() -> None:
    """«…se abrió un incidente en <inmueble> por <disparo>» decía la ESCALADA.

    Es el documento que lee quien decide, y el que más se enseña.
    """
    texto = _texto(model(**_ESCALADO), "executive")
    assert TRIGGER_LABELS["sasmex"] in texto, "el ejecutivo atribuye la apertura al que escaló"
    assert TRIGGER_LABELS["quorum"] in texto, "y se calla que escaló"


def test_el_EJECUTIVO_sin_escalada_no_INVENTA_una() -> None:
    texto = _texto(model(**_SIN_ESCALAR), "executive")
    assert "escaló" not in texto.lower()


def test_la_portada_declara_los_DOS_cuando_difieren() -> None:
    """La celda «SEVERIDAD · DISPARO» de la portada mostraba solo la escalada."""
    texto = _texto(model(**_ESCALADO), "technical")
    assert TRIGGER_LABELS["sasmex"] in texto, "la portada no dice quién abrió"
    assert TRIGGER_LABELS["quorum"] in texto, "la portada se calla la escalada"


def test_el_espia_NO_esta_ciego() -> None:
    """Control de ceguera: si el espía no viera nada, todo lo de arriba pasaría."""
    texto = _texto(model(**_ESCALADO), "technical")
    assert len(texto) > 2000, "el espía no recogió el texto del documento"


def test_los_rotulos_del_disparo_no_estan_VACIOS() -> None:
    """Control de ceguera de los dos tests de arriba: con un rótulo vacío, un
    `in texto` pasa siempre. Y dos rótulos iguales harían indistinguibles la
    apertura y la escalada."""
    assert all(v.strip() for v in TRIGGER_LABELS.values())
    assert len(set(TRIGGER_LABELS.values())) == len(TRIGGER_LABELS)
