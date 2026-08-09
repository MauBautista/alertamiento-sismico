"""T-2.79 · Los artefactos de aviso del repo: sello, defectos y provisionalidad.

Sin DB: aquí se mide el objeto versionado y su candado, que es lo que hace que
sustituir el texto sea una versión nueva y no una edición silenciosa.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from takab_api.privacy.artifacts import (
    APPROVED,
    TEXTS_DIR,
    NoticeCatalog,
    NoticeSpec,
    notice_digest,
)

_CUERPO = (
    "Cuerpo de aviso suficientemente largo para pasar el minimo, con dos parrafos.\n\n"
    "Segundo parrafo, para poder medir el troceado."
)


def _doc(**over) -> dict:
    base = {
        "purpose": "privacy_notice",
        "notice": {
            "locale": "es-MX",
            "version": "1.0.0",
            "title": "Aviso de privacidad",
            "body": _CUERPO,
        },
        "legal_review": {"status": "PROVISIONAL", "approved_digest": ""},
    }
    base["notice"].update(over.pop("notice", {}))
    base["legal_review"].update(over.pop("legal_review", {}))
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# El sello de revisión legal
# ---------------------------------------------------------------------------


def test_sin_revisar_es_provisional_y_dice_por_que() -> None:
    spec = NoticeSpec.from_document(_doc(), source="t.json")
    assert spec.provisional is True
    assert "PROVISIONAL" in spec.provisional_reason
    # Provisional NO es inservible: se sirve, marcado. Servir un aviso
    # provisional bien etiquetado es mejor que no servir ninguno.
    assert spec.usable is True


def test_aprobado_con_el_digest_correcto_deja_de_ser_provisional() -> None:
    doc = _doc()
    dig = notice_digest("es-MX", "Aviso de privacidad", _CUERPO)
    doc["legal_review"] = {"status": APPROVED, "approved_digest": dig}
    spec = NoticeSpec.from_document(doc, source="t.json")
    assert spec.provisional is False
    assert spec.provisional_reason == ""


def test_aprobado_pero_con_el_texto_cambiado_vuelve_a_ser_provisional() -> None:
    """EL CANDADO. Sellar y luego editar el cuerpo no deja el sello quieto.

    Es el mismo mecanismo que ``notify/whatsapp_templates`` usa contra Meta, y
    aquí protege lo mismo: que el texto revisado y el texto servido no se separen
    sin que nadie lo note.
    """
    doc = _doc()
    dig_revisado = notice_digest("es-MX", "Aviso de privacidad", _CUERPO)
    doc["legal_review"] = {"status": APPROVED, "approved_digest": dig_revisado}
    doc["notice"]["body"] = _CUERPO + " Coma anadida despues de la revision."
    spec = NoticeSpec.from_document(doc, source="t.json")
    assert spec.provisional is True
    assert "no coincide con el revisado" in spec.provisional_reason


def test_aprobado_sin_digest_no_cuenta_como_aprobado() -> None:
    doc = _doc(legal_review={"status": APPROVED, "approved_digest": ""})
    spec = NoticeSpec.from_document(doc, source="t.json")
    assert spec.provisional is True
    assert "approved_digest" in spec.provisional_reason


# ---------------------------------------------------------------------------
# Defectos: un artefacto roto NO se sirve, y no revienta el arranque
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("over", "trozo"),
    [
        ({"purpose": "otra_cosa"}, "purpose"),
        ({"notice": {"locale": "es_MX"}}, "locale"),
        ({"notice": {"version": "  "}}, "versión"),
        ({"notice": {"title": "corto"}}, "título"),
        ({"notice": {"body": "TODO"}}, "corto"),
    ],
)
def test_un_artefacto_roto_nace_con_defecto_y_no_es_utilizable(over: dict, trozo: str) -> None:
    spec = NoticeSpec.from_document(_doc(**over), source="t.json")
    assert spec.usable is False
    assert trozo in spec.defect


def test_el_catalogo_no_revienta_con_un_json_ilegible(tmp_path: Path) -> None:
    """Levantar aquí dejaría la API sin arrancar y, con ella, sin aviso ninguno."""
    (tmp_path / "roto.json").write_text("{ esto no es json", encoding="utf-8")
    (tmp_path / "sano.json").write_text(json.dumps(_doc()), encoding="utf-8")
    cat = NoticeCatalog.load(tmp_path)
    assert len(cat.notices) == 1
    assert cat.get("privacy_notice", "es-MX") is not None


def test_no_hay_caso_alterno_por_idioma(tmp_path: Path) -> None:
    """Servir el aviso en un idioma que la persona no pidió es servirle un texto
    que puede no entender, y consentir lo que no se entiende no es consentir."""
    (tmp_path / "es.json").write_text(json.dumps(_doc()), encoding="utf-8")
    cat = NoticeCatalog.load(tmp_path)
    assert cat.get("privacy_notice", "es-MX") is not None
    assert cat.get("privacy_notice", "en-US") is None
    assert cat.get("whatsapp_alerts", "es-MX") is None


def test_los_parrafos_salen_del_cuerpo_y_no_de_un_resumen_aparte() -> None:
    spec = NoticeSpec.from_document(_doc(), source="t.json")
    assert len(spec.paragraphs) == 2
    assert "".join(spec.paragraphs) in spec.body.replace("\n\n", "")


# ---------------------------------------------------------------------------
# Los artefactos REALES del repo
# ---------------------------------------------------------------------------


def test_los_avisos_del_repo_son_servibles_y_declaran_su_provisionalidad() -> None:
    cat = NoticeCatalog.load(TEXTS_DIR)
    por_proposito = {n.purpose: n for n in cat.notices}
    assert set(por_proposito) == {"privacy_notice", "whatsapp_alerts"}
    for spec in cat.notices:
        assert spec.usable, f"{spec.source}: {spec.defect}"
        assert spec.provisional, f"{spec.source} se declara revisado por LEGAL y no lo está"
        # El cuerpo lo dice EN EL TEXTO, no solo en un campo de metadatos: así
        # viaja hasta la pantalla y entra en el digest, de modo que el día que
        # LEGAL entregue el definitivo el digest cambia y todos re-consienten.
        assert "TEXTO PROVISIONAL" in spec.body


def test_el_digest_de_los_dos_avisos_del_repo_es_distinto() -> None:
    cat = NoticeCatalog.load(TEXTS_DIR)
    digests = {n.digest for n in cat.notices}
    assert len(digests) == len(cat.notices)
