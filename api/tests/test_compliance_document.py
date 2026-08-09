"""Documento de etiquetas de cumplimiento (T-2.82): lo PURO, sin DB ni HTTP.

Una etiqueta de cumplimiento es una AFIRMACIÓN NORMATIVA. Este repo ya se quemó con
una: la consola llegó a citar "NOM-003-SCT", que es una norma de transporte y no tiene
nada que ver con alertamiento sísmico (``CLAUDE.md`` regla de oro 11;
``ESPECIFICACION-APP-MOVIL.md §13`` la lista como PROHIBIDA). El remedio de entonces
fue servir los strings por tenant — pero servir un ``jsonb`` libre y pintarlo con aire
oficial en un dictamen firmado reproduce el mismo error a escala, y esta vez con la
firma de alguien debajo.

Estos tests fijan las cerraduras que lo impiden:

1. Un ``key`` fuera del catálogo cerrado no existe, y el catálogo no cita normas.
2. La procedencia no es un campo: es estructural. No hay dónde escribir "verificado".
3. Toda afirmación exige una referencia citable no vacía.
4. Un documento que el sistema no entiende se DECLARA ilegible; no se ignora ni se
   transcribe a medias.
5. Lo que sale hacia una pantalla va SIEMPRE enmarcado como declaración del cliente.
"""

from __future__ import annotations

import pytest

from takab_api.compliance import (
    CATALOG,
    DECLARED_SHORT,
    DOCUMENT_VERSION,
    MAX_CLAIMS,
    MAX_TEXT,
    PROVENANCE,
    UNREADABLE_LEGACY,
    UNREADABLE_MALFORMED,
    UNREADABLE_VERSION,
    ComplianceClaim,
    ComplianceDocument,
    ComplianceError,
    build_claims,
    mobile_projection,
    parse_document,
    to_storage,
)

CLAIM_TEXT = "Reglamento de Construcciones del Distrito Federal, Título Sexto"
REF_TEXT = "Gaceta Oficial del DF, 29/01/2004, art. 139"


def _claim(key: str = "regulatory_framework", **over: object) -> dict:
    base: dict = {"key": key, "claim": CLAIM_TEXT, "reference": REF_TEXT}
    base.update(over)
    return base


# --- 1. Catálogo cerrado ------------------------------------------------------


def test_el_catalogo_no_cita_ninguna_norma_concreta() -> None:
    """El catálogo nombra CLASES de afirmación, jamás una norma.

    Si aquí apareciera "NOM-003" o cualquier clave/título con nombre de norma, la
    plataforma estaría afirmando por su cuenta un marco citable — y GATE-LEGAL sigue
    abierto: TAKAB no tiene ninguno confirmado (``blueprint §9``).
    """
    prohibidas = {"nom", "nom-003", "iso", "nfpa", "astm", "lfpdppp"}
    for key, title in CATALOG.items():
        palabras = {p.strip(".,·").lower() for p in f"{key} {title}".replace("_", " ").split()}
        assert palabras.isdisjoint(prohibidas), (
            f"el catálogo cita una norma en {key!r}: {title!r} — GATE-LEGAL sigue abierto"
        )


@pytest.mark.parametrize(
    "key",
    ["nom_003_sct", "cumple_todo", "", "REGULATORY_FRAMEWORK", "regulatory_framework "],
)
def test_una_clave_fuera_del_catalogo_no_se_puede_declarar(key: str) -> None:
    with pytest.raises(ComplianceError):
        build_claims([_claim(key)])


@pytest.mark.parametrize("key", sorted(CATALOG))
def test_toda_clave_del_catalogo_si_se_puede_declarar(key: str) -> None:
    assert [c.key for c in build_claims([_claim(key)])] == [key]


def test_dos_afirmaciones_de_la_misma_clase_se_rechazan() -> None:
    """Dos "marcos normativos" a la vez serían dos verdades sobre lo mismo, y la
    proyección móvil (mapa plano clave→texto) perdería una en silencio."""
    with pytest.raises(ComplianceError):
        build_claims([_claim(), _claim(claim="Otra cosa distinta")])


def test_hay_tope_de_afirmaciones_por_cliente() -> None:
    uno = sorted(CATALOG)[0]
    assert build_claims([_claim(k) for k in sorted(CATALOG)[:MAX_CLAIMS]]) or MAX_CLAIMS == 0
    with pytest.raises(ComplianceError):
        build_claims([_claim(uno)] * (MAX_CLAIMS + 1))


# --- 2. La procedencia es estructural ----------------------------------------


def test_no_existe_forma_de_declarar_una_etiqueta_como_verificada() -> None:
    """La única procedencia posible es la declaración del cliente.

    No es un default sobrescribible: ``ComplianceClaim`` no tiene campo de
    verificación, así que ni un cuerpo HTTP ni un INSERT a mano pueden fabricar una
    etiqueta que diga "TAKAB lo verificó".
    """
    assert set(ComplianceClaim.__dataclass_fields__) == {"key", "claim", "reference"}
    assert PROVENANCE == "declared_by_tenant"


@pytest.mark.parametrize(
    "extra",
    [
        {"provenance": "verified_by_takab"},
        {"status": "verified"},
        {"verified": True},
        {"certified_by": "TAKAB"},
    ],
)
def test_un_campo_de_verificacion_colado_en_el_cuerpo_se_rechaza(extra: dict) -> None:
    with pytest.raises(ComplianceError):
        build_claims([{**_claim(), **extra}])


def test_lo_que_se_guarda_no_lleva_ninguna_marca_de_verificacion() -> None:
    assert to_storage(build_claims([_claim()])) == {
        "version": DOCUMENT_VERSION,
        "items": [{"key": "regulatory_framework", "claim": CLAIM_TEXT, "reference": REF_TEXT}],
    }


# --- 3. Referencia citable obligatoria ---------------------------------------


@pytest.mark.parametrize("blanco", ["", "   ", "\t", "\n  \n"])
@pytest.mark.parametrize("campo", ["claim", "reference"])
def test_ni_la_afirmacion_ni_su_referencia_pueden_ir_en_blanco(campo: str, blanco: str) -> None:
    with pytest.raises(ComplianceError):
        build_claims([_claim(**{campo: blanco})])


@pytest.mark.parametrize("campo", ["claim", "reference", "key"])
def test_falta_un_campo_entero_y_se_rechaza(campo: str) -> None:
    incompleto = _claim()
    del incompleto[campo]
    with pytest.raises(ComplianceError):
        build_claims([incompleto])


@pytest.mark.parametrize("campo", ["claim", "reference"])
@pytest.mark.parametrize("valor", [123, None, ["x"], {"a": 1}, True])
def test_un_texto_que_no_es_texto_se_rechaza(campo: str, valor: object) -> None:
    with pytest.raises(ComplianceError):
        build_claims([_claim(**{campo: valor})])


@pytest.mark.parametrize("campo", ["claim", "reference"])
def test_el_texto_tiene_tope_duro(campo: str) -> None:
    assert build_claims([_claim(**{campo: "x" * MAX_TEXT})])
    with pytest.raises(ComplianceError):
        build_claims([_claim(**{campo: "x" * (MAX_TEXT + 1)})])


def test_los_textos_se_normalizan_sin_espacios_de_borde() -> None:
    claim = build_claims([_claim(claim="  con bordes  ", reference="  ref citable  ")])[0]
    assert (claim.claim, claim.reference) == ("con bordes", "ref citable")


# --- 4. Un documento ilegible se DECLARA ilegible ----------------------------
#
# ``cl_admin`` (DDL) deja escribir esta tabla a cualquier identidad interna TAKAB,
# también por psql. Un documento que este código no entienda NO puede transcribirse a
# medias ni desaparecer en silencio: las dos cosas acaban en un dictamen firmado.


@pytest.mark.parametrize("vacio", [None, {}])
def test_sin_documento_el_resultado_es_vacio_y_LEGIBLE(vacio: object) -> None:
    """``'{}'`` es el DEFAULT del DDL: significa "no se declaró nada", no "ilegible"."""
    doc = parse_document(vacio)
    assert (doc.items, doc.unreadable, doc.declared) == ((), None, False)


def test_un_documento_valido_se_lee_entero() -> None:
    doc = parse_document(to_storage(build_claims([_claim(), _claim("internal_protocol")])))
    assert doc.unreadable is None
    assert [(c.key, c.claim, c.reference) for c in doc.items] == [
        ("regulatory_framework", CLAIM_TEXT, REF_TEXT),
        ("internal_protocol", CLAIM_TEXT, REF_TEXT),
    ]
    assert doc.declared is True


def test_un_mapa_plano_heredado_se_declara_ilegible_y_no_se_transcribe() -> None:
    """El shape viejo del contrato (``{clave: "texto"}``) NO se sabe interpretar: no
    consta ni su clase ni su referencia. Transcribirlo sería afirmar sin respaldo."""
    doc = parse_document({"norma": "Cumplimos la NOM-003-SCT"})
    assert doc.items == ()
    assert doc.unreadable == UNREADABLE_LEGACY


@pytest.mark.parametrize("version", [0, 2, 99, "1", None, 1.0])
def test_una_version_desconocida_se_declara_ilegible(version: object) -> None:
    doc = parse_document({"version": version, "items": []})
    assert doc.items == ()
    assert doc.unreadable == UNREADABLE_VERSION


@pytest.mark.parametrize(
    "roto",
    [
        {"version": DOCUMENT_VERSION, "items": "no es una lista"},
        {"version": DOCUMENT_VERSION},
        {"version": DOCUMENT_VERSION, "items": [{"key": "regulatory_framework"}]},
        {"version": DOCUMENT_VERSION, "items": [{**_claim(), "claim": ""}]},
        {"version": DOCUMENT_VERSION, "items": [_claim("inventada")]},
        {"version": DOCUMENT_VERSION, "items": ["no es un objeto"]},
        {"version": DOCUMENT_VERSION, "items": [_claim(), _claim()]},
    ],
)
def test_un_documento_mal_formado_se_declara_ilegible_entero(roto: dict) -> None:
    """Ilegible es TODO el documento, no la fila mala: si una afirmación del cliente
    llegó rota, no hay motivo para creerse las de al lado."""
    doc = parse_document(roto)
    assert doc.items == ()
    assert doc.unreadable == UNREADABLE_MALFORMED


@pytest.mark.parametrize("basura", ["texto", 7, [], [1, 2], True])
def test_un_documento_que_ni_siquiera_es_un_objeto_se_declara_ilegible(basura: object) -> None:
    assert parse_document(basura).unreadable == UNREADABLE_MALFORMED


def test_un_documento_valido_con_cero_afirmaciones_es_legible_y_vacio() -> None:
    doc = parse_document({"version": DOCUMENT_VERSION, "items": []})
    assert (doc.items, doc.unreadable, doc.declared) == ((), None, False)


# --- 5. Nada sale sin enmarcar -----------------------------------------------


def test_la_proyeccion_movil_enmarca_cada_afirmacion() -> None:
    """La pantalla 1.5 del móvil (``ReentryBlockedView``) pinta el VALOR y descarta la
    clave. Si el valor no se enmarca a sí mismo, el ocupante lee una afirmación
    normativa desnuda bajo un letrero de "REINGRESO PROHIBIDO"."""
    doc = parse_document(to_storage(build_claims([_claim()])))
    assert mobile_projection(doc) == {
        "regulatory_framework": (
            f"{CATALOG['regulatory_framework']}: {CLAIM_TEXT} · {DECLARED_SHORT}"
        )
    }


def test_sin_afirmaciones_la_proyeccion_movil_es_vacia() -> None:
    """Vacío ⇒ NADA normativo (``ESPECIFICACION-APP-MOVIL §2.1-C``): la app esconde la
    tarjeta. Un aviso inventado aquí sería texto normativo hardcodeado."""
    assert mobile_projection(parse_document({})) == {}


def test_un_documento_ilegible_se_anuncia_en_el_movil_en_vez_de_callarse() -> None:
    doc = parse_document({"norma": "Cumplimos la NOM-003-SCT"})
    proyeccion = mobile_projection(doc)
    assert list(proyeccion) == ["_ilegible"]
    assert proyeccion["_ilegible"] == UNREADABLE_LEGACY


def test_toda_proyeccion_movil_es_un_mapa_de_texto_a_texto() -> None:
    """El contrato publicado de ``mobile-state`` es ``dict[str, str]``. Cualquier otra
    cosa rompería a los teléfonos ya instalados, no al servidor."""
    for doc in (
        parse_document({}),
        parse_document({"version": DOCUMENT_VERSION, "items": [_claim()]}),
        parse_document({"basura": 1}),
    ):
        proyeccion = mobile_projection(doc)
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in proyeccion.items()), (
            proyeccion
        )


def test_el_aviso_corto_declara_al_cliente_como_autor_y_desmarca_a_takab() -> None:
    """El texto es parte del trabajo, no relleno: tiene que decir las DOS cosas."""
    assert DECLARED_SHORT == (
        "Declarado por el cliente; TAKAB no lo verifica ni certifica su cumplimiento."
    )


def test_un_documento_vacio_es_lo_mismo_que_no_tener_fila() -> None:
    assert parse_document(None) == ComplianceDocument()
