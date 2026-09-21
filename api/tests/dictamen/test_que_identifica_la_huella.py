"""[T-7.43] Qué identifica el número que el dictamen manda verificar.

El docstring de `ReportModel.content_sha256()` prometía que la huella «permite
comparar dos exportaciones del mismo incidente sin abrirlas». `T-7.42` retiró la
frase y dejó escrito que la decisión era ésta; aquí se toma, y se fija.

## La decisión: el número identifica ESTA EXPORTACIÓN

No el incidente, no «el contenido» en abstracto: **esta exportación concreta**.
La promesa de comparación no se puede cumplir, y **no es culpa del reloj**:

**1 · Exportar cambia el contenido del incidente.** `routers/reports.py` inserta
una fila `kind='report_pdf'` (`queries/reports.py`) que la exportación siguiente
relee —`builder.py::_EVIDENCE` no filtra por `kind`— y **imprime en §12** (era la
§11 hasta que `T-7.24` insertó el mapa de la sacudida). Medido con el reloj
congelado y el mundo idéntico: `77e75b30c0038ce6` → `76973b9c08d3d56a`.
Es un bucle autorreferente. Sacar `generated_at` del payload convertiría una frase
falsa en otra frase falsa más pequeña, que es exactamente lo que `T-7.38·I`
prohíbe.

**2 · El esquema ya lo decidió, y desde la migración `0002`.**
`uq_evidence_incident_sha256` sobre `(incident_id, sha256)`: dos exportaciones del
mismo incidente **no pueden** ser el mismo archivo. La pregunta de la ficha tiene
respuesta escrita en el DDL, y es «no».

**3 · Con ese significado, el reloj PERTENECE.** Si el número identifica esta
exportación, la hora de la exportación es parte legítima de su identidad. Sacarlo
dejaría un número que no identifica ni la exportación ni el contenido — y abriría
la colisión del punto 2: `insert_evidence` no lleva `ON CONFLICT` y se resuelve
con `.scalar_one()`, y `put_object` corre ANTES del INSERT, así que el resultado
sería un 500 **con el objeto ya subido a S3, huérfano**. Dos exportaciones caben
de sobra en el mismo segundo.

**4 · Nadie lo consume.** Cero ocurrencias de `content_sha256` en `web/src`,
`mobile/src` y el SDK; cero lectores de `meta->>'content_sha256'`. Construirle un
lector a un número que nadie pidió, para sostener una promesa que el esquema
prohíbe, sería trabajar al revés.

## Las cuatro puertas por las que se mueve

Van impresas en el papel, porque un número que se mueve sin decir por qué se lee
como inestable: (1) el contenido del expediente; (2) la propia exportación, que se
añade a la cadena de custodia; (3) una lectura degradada del miniSEED o de las
fotografías —que el papel DECLARA, y por eso debe mover el número—; (4) la prosa,
cuando la redacta un proveedor de red, que se re-muestrea sin `temperature` ni
`seed`.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from takab_api.dictamen.model import EvidenceRow, ReportModel
from takab_api.dictamen.pdf import render
from takab_api.documentos import membrete
from tests.dictamen.test_pdf import _OPENED, model
from tests.documentos.espia import espia_del_render

#: Valor con el que el censo sustituye un campo. Cualquier cosa que serialice
#: distinto sirve; se usa una cadena para que `asdict` no intente recorrerla.
MARCA = "«campo mutado por el censo de T-7.43»"

_RAIZ = Path(__file__).resolve().parents[2]


# ───────────────────────── criterio 2 · la prueba en los DOS sentidos


def test_NINGUN_campo_del_modelo_es_CIEGO_a_la_huella() -> None:
    """El censo DERIVADO, que es lo que la ficha pide y lo que no había.

    Muta los campos uno a uno —salen de `dataclasses.fields`, no de una lista— y
    exige que la huella se mueva en TODOS. Hoy son 58 campos y 0 ciegos, y ésa es
    la propiedad: **el número identifica el modelo entero**.

    ⚠️ Es el sentido que las guardas de hoy NO cubrían. Las dos que hablan de
    estabilidad se apoyan en la fixture compartida, que clava
    `generated_at=_OPENED` (`tests/dictamen/test_pdf.py`): con el reloj congelado
    pasan en verde tanto si el reloj entra en la huella como si no, y por eso la
    ficha llegó a afirmar que este cambio las pondría rojas. No las pone.
    """
    m = model()
    campos = dataclasses.fields(m)
    assert len(campos) > 50, f"el censo sólo vio {len(campos)} campos: ¿se derivó de verdad?"

    base = m.content_sha256()
    ciegos = [
        f.name for f in campos if dataclasses.replace(m, **{f.name: MARCA}).content_sha256() == base
    ]
    assert not ciegos, (
        "hay campos del modelo que NO mueven la huella: el papel imprime ese número "
        "en la portada y al pie de todas sus páginas como identidad de lo que "
        f"afirma, y estos campos podrían cambiar sin que el número se entere: {ciegos}"
    )


def test_el_censo_de_campos_CAZA_un_campo_que_dejara_de_contar() -> None:
    """Porque un censo que no puede fallar no censa nada.

    Se reproduce el defecto —una receta que excluye un campo— y se comprueba que
    el barrido de arriba lo vería. Sin esto, cualquier exención futura entraría en
    verde.
    """
    m = model()

    def huella_sin(nombre: str, modelo: ReportModel) -> str:
        import hashlib
        import json

        from takab_api.documentos.huella import para_la_huella

        payload = dataclasses.asdict(modelo)
        payload.pop(nombre)
        return hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), default=para_la_huella
            ).encode()
        ).hexdigest()

    base = huella_sin("generated_at", m)
    mutado = huella_sin("generated_at", dataclasses.replace(m, generated_at=MARCA))
    assert base == mutado, (
        "excluir un campo de la receta dejó de volverlo ciego: si Python o `asdict` "
        "cambiaron, el censo de arriba ya no mide lo que dice medir"
    )


# ───────────────────── por qué la promesa NO se puede cumplir (las dos razones)


def test_EXPORTAR_cambia_el_contenido_del_incidente() -> None:
    """El bucle autorreferente, medido. Es la razón principal de la decisión.

    La exportación inserta su propia fila `report_pdf`; la siguiente la lee —el
    builder no filtra por `kind`— y la imprime en §12. Así que dos exportaciones
    del mismo incidente difieren aunque el mundo no se haya movido y aunque el
    reloj estuviera congelado.
    """
    primera = model()
    dejada_atras = EvidenceRow("report_pdf", "a" * 64, _OPENED)
    segunda = dataclasses.replace(primera, evidence=[*primera.evidence, dejada_atras])

    assert primera.content_sha256() != segunda.content_sha256(), (
        "si estas dos coincidieran, la promesa de comparar exportaciones sería "
        "alcanzable y habría que revisar la decisión de T-7.43"
    )


def test_el_builder_relee_la_evidencia_SIN_filtrar_el_report_pdf() -> None:
    """Y que el bucle es del código, no de esta prueba.

    Si algún día se filtrara `kind='report_pdf'` al construir el modelo, la razón
    1 de la decisión dejaría de valer — pero antes habría que resolver lo que dice
    `test_el_esquema_PROHIBE_dos_exportaciones_identicas`: sin la realimentación,
    dos exportaciones pueden dar bytes idénticos y el INSERT revienta.
    """
    fuente = (_RAIZ / "src/takab_api/dictamen/builder.py").read_text(encoding="utf-8")
    consulta = re.search(r"_EVIDENCE = text\((.*?)\n\)", fuente, re.S)
    assert consulta, "no se encontró la consulta de evidencia del builder"
    assert "kind" not in consulta.group(1).split("SELECT")[1].split("WHERE")[1], (
        "el builder empezó a filtrar la evidencia por `kind`: revisa la razón 1 de "
        "T-7.43 y, sobre todo, la colisión contra uq_evidence_incident_sha256"
    )


def test_el_esquema_PROHIBE_dos_exportaciones_identicas() -> None:
    """La segunda razón, y la que no es opinión: está en el DDL desde la `0002`.

    `uq_evidence_incident_sha256` sobre `(incident_id, sha256)` declara que dos
    exportaciones del mismo incidente no pueden ser el mismo archivo. Si este
    índice desapareciera, la decisión de esta ficha tendría que re-tomarse.
    """
    migracion = (_RAIZ / "migrations/versions/0002_ingest_support.py").read_text(encoding="utf-8")
    assert "uq_evidence_incident_sha256" in migracion
    assert "(incident_id, sha256)" in migracion.replace('"', "").replace("\n", " ")


# ──────────────────────── criterio 1 · lo que el papel dice, y lo que ya no dice


@pytest.mark.parametrize("variante", ["technical", "executive"])
def test_el_papel_dice_QUE_identifica_la_huella(variante: str) -> None:
    """Las dos variantes, con la misma definición.

    T-7.42 encontró que la portada del pericial y la del ejecutivo decían cosas
    distintas del MISMO número. Aquí se exige que las dos digan lo que se decidió.
    """
    with espia_del_render() as cap:
        render(model(), variante)
    texto = cap.texto.lower()
    assert len(texto) > 1000, "el espía no recogió el documento"
    assert "esta exportación" in texto, (
        f"la portada del {variante} no dice que la huella identifica ESTA "
        "exportación: un número sin sujeto invita a suponer que identifica el "
        "incidente, y entonces dos exportaciones legítimas parecen una falsificación"
    )


@pytest.mark.parametrize("variante", ["technical", "executive"])
def test_el_papel_NO_promete_comparar_exportaciones(variante: str) -> None:
    """La promesa retirada, comprobada donde vive: en el papel.

    No basta con quitarla del docstring —`T-7.42` lo hizo— porque lo que el
    perito lee es el documento.
    """
    with espia_del_render() as cap:
        render(model(), variante)
    texto = cap.texto.lower()
    for prohibida in ("sin abrirlas", "sin abrirlos", "compare dos exportaciones"):
        assert prohibida not in texto, (
            f"el {variante} promete comparar exportaciones («{prohibida}»), y no se "
            "puede: exportar inserta una fila de evidencia que la siguiente imprime"
        )


def _sin_comentarios(ts: str) -> str:
    """El marcado SIN sus comentarios, para poder contar lo que de verdad hace.

    ⚠️ CUARTA VEZ que este repositorio paga esto. Un barrido estructural que no
    enmascara los comentarios cuenta la prosa que EXPLICA el defecto como si
    fuera el defecto: aquí, el comentario que documenta «antes se pintaba
    `sha.slice(0, 16)`» hacía creer a la guarda que el truncado seguía vivo.
    Escribir bien por qué algo se arregló no puede poner rojo el arreglo.
    """
    import re as _re

    sin_bloque = _re.sub(r"/\*.*?\*/", " ", ts, flags=_re.S)
    return _re.sub(r"(^|[^:])//[^\n]*", r"\1 ", sin_bloque)


def _capacidades_reales() -> dict[str, bool]:
    """Las TRES capacidades que la frase del papel presupone, leídas de su fuente.

    ⚠️ [T-7.48] Esto sustituye a un `assert "desde la consola" not in texto` y el
    cambio es de clase, no de redacción. Aquella guarda tenía dos agujeros:

    · **Enumeraba una cadena a mano.** «en la consola» o «desde el panel» la
      evadían sin tocar una línea de esta prueba, y el papel volvía a prometer lo
      que no se puede.
    · **Y no ataba la prohibición a NADA.** El día que las tres capacidades
      existieran, el único modo de reponer la frase era borrar el assert — o sea,
      apagar la guarda para usar lo que la guarda protegía.

    Ahora se lee de dónde salen de verdad. Si mañana alguien vuelve a truncar el
    hash en la consola o reintroduce el filtro por `kind`, esta prueba lo dice
    **y** el papel deja de poder afirmarlo.
    """
    verificador = (_RAIZ / "src/takab_api/queries/mobile.py").read_text(encoding="utf-8")
    consulta = re.search(r"EVIDENCE_FOR_VERIFY = text\((.*?)\n\)", verificador, re.S)
    assert consulta, "no se encontró EVIDENCE_FOR_VERIFY: la guarda quedó ciega"

    alcance = (_RAIZ / "src/takab_api/routers/mobile_incident.py").read_text(encoding="utf-8")
    esquema = (_RAIZ / "src/takab_api/schemas/reports.py").read_text(encoding="utf-8")
    panel = _sin_comentarios(
        (_RAIZ.parent / "web/src/features/triage/TriageDetail.tsx").read_text(encoding="utf-8")
    )
    modelo = _sin_comentarios(
        (_RAIZ.parent / "web/src/features/triage/model.ts").read_text(encoding="utf-8")
    )

    return {
        # 1· la API devuelve la huella del ARCHIVO, en espejo con el simulacro
        "la_api_lo_devuelve": "sha256: str" in esquema.split("class ReportOut")[1],
        # 2· el verificador acepta ese `kind` — ni filtrado en la consulta ni
        #    excluido del reparto de alcances del router
        "el_verificador_lo_acepta": (
            "kind = 'photo'" not in consulta.group(1)
            and '"report_pdf":' in alcance.split("_ALCANCE_DE_VERIFICACION")[1]
        ),
        # 3· la consola lo busca, y lo pinta ENTERO. El truncado es el defecto
        #    que `T-5.26` cerró en el papel y que seguía vivo en la pantalla.
        "la_consola_lo_pinta_entero": (
            "report_pdf" in modelo and "dictamenPdfOf" in panel and ".slice(0, 16)" not in panel
        ),
    }


def test_el_papel_SOLO_manda_lo_que_HOY_SE_PUEDE() -> None:
    """⚠️ La frase de `T-7.42`, atada a las capacidades que presupone.

    `T-7.42` dejó escrito «compárelo contra ese registro desde la consola» y era
    falso por tres vías medidas: `ReportOut` no devolvía el sha del archivo
    —`DrillReportOut` sí—, el verificador filtraba `kind = 'photo'` y devolvía
    404 para un `report_pdf`, y la consola sólo buscaba `miniseed` y lo pintaba
    truncado a 16 de 64 caracteres.

    `T-7.48` construyó las tres. Esta prueba ya no prohíbe una frase: **exige que
    el papel y el código digan lo mismo**, en la dirección que toque.
    """
    capacidades = _capacidades_reales()
    with espia_del_render() as cap:
        render(model())
    texto = cap.texto.lower()
    manda_comprobar = "sha256sum" in texto or "consola" in texto

    if manda_comprobar:
        faltan = [nombre for nombre, hay in capacidades.items() if not hay]
        assert not faltan, (
            "el papel manda comprobar la huella del ARCHIVO y eso HOY no se puede. "
            f"Falta: {faltan}. O se construye la capacidad, o el papel deja de "
            "mandarlo — pero no las dos cosas a la vez, que es como nació T-7.48."
        )
    else:
        assert not all(capacidades.values()), (
            "las tres capacidades existen y el papel NO lo dice. Un dictamen que "
            "se puede verificar y no explica cómo deja al perito sin la única "
            "comprobación que puede hacer solo."
        )


@pytest.mark.parametrize("variante", ["technical", "executive"])
def test_la_guarda_del_papel_mira_LAS_DOS_variantes(variante: str) -> None:
    """El segundo agujero de la guarda vieja, y costaba un descuido.

    Renderizaba `render(model())` a secas, o sea **sólo la variante técnica**
    (`variant="technical"` es el default de `render`), mientras sus dos vecinas
    de este mismo fichero sí están parametrizadas con las dos. El resumen
    ejecutivo podía prometer lo que quisiera sin que nada lo mirara.
    """
    with espia_del_render() as cap:
        render(model(), variant=variante)
    texto = cap.texto.lower()
    if "sha256sum" in texto or "consola" in texto:
        faltan = [nombre for nombre, hay in _capacidades_reales().items() if not hay]
        assert not faltan, f"la variante {variante} promete lo que no se puede: {faltan}"


# ──────────────── criterio 3 · la degradación best-effort, DECLARADA


def test_una_lectura_DEGRADADA_mueve_la_huella() -> None:
    """Y debe moverla: un papel que dice «no pude leer la onda» afirma otra cosa.

    Es la tercera de las cuatro puertas. No se esconde de la huella —eso haría
    que dos papeles distintos compartieran número, que es peor—: se declara.
    """
    completo = model()
    degradado = dataclasses.replace(
        completo,
        raw_waveform=[],
        raw_sample_rate=None,
        spectrum=[],
        raw_unavailable_reason="el miniSEED archivado no se pudo leer",
    )
    assert completo.content_sha256() != degradado.content_sha256(), (
        "un documento degradado comparte huella con uno completo: el número diría "
        "que los dos afirman lo mismo, y no lo hacen"
    )


def test_el_papel_DECLARA_que_una_lectura_degradada_mueve_el_numero() -> None:
    """Criterio 3 de la ficha, comprobado en el papel y no en un comentario.

    Un número que se mueve sin decir por qué se lee como inestable, y un lector
    que compara dos exportaciones degradadas de distinta manera concluiría que
    alguien alteró el expediente.
    """
    with espia_del_render() as cap:
        render(model())
    texto = cap.texto.lower()
    assert "una sección que no se pudo leer" in texto, (
        "el papel no dice que una lectura degradada cambia la huella, así que el "
        "lector no tiene cómo distinguir «cambió el dato» de «no se pudo leer una "
        "sección» — y concluiría lo primero"
    )
    assert "no prueba que el dato" in texto, (
        "el papel no dice la DIRECCIÓN: huellas iguales implican la misma "
        "afirmación, pero huellas distintas no implican que el dato cambiara"
    )


# ──────────────────── el contraste: los dos papeles NO prometen lo mismo


def test_la_huella_del_SIMULACRO_si_es_ESTABLE_y_por_eso_dice_otra_cosa() -> None:
    """La asimetría es real y el papel tiene que respetarla.

    El reporte de simulacro no tiene reloj de generación, su clave S3 es FIJA y su
    fila de evidencia no realimenta su propio modelo. Ahí sí dos exportaciones
    coinciden —medido— y por eso puede decir algo que el dictamen no puede.
    Si los dos papeles dijeran lo mismo, el lector trasladaría del uno al otro una
    garantía que sólo tiene uno.
    """
    from takab_api.drill_report import render as render_simulacro
    from tests.api.test_drill_report import _rep

    assert render_simulacro(_rep()) == render_simulacro(_rep())
    assert _rep().content_sha256() == _rep().content_sha256()

    dictamen = model()
    con_su_exportacion = dataclasses.replace(
        dictamen, evidence=[*dictamen.evidence, EvidenceRow("report_pdf", "b" * 64, _OPENED)]
    )
    assert dictamen.content_sha256() != con_su_exportacion.content_sha256()


def test_el_espia_NO_esta_ciego() -> None:
    """Todo lo de arriba que mira el papel pasaría por vacuidad si el espía fallara."""
    with espia_del_render() as cap:
        render(model())
    assert len(cap.texto) > 3000, f"el espía sólo recogió {len(cap.texto)} caracteres"
    assert membrete.MembretePDF.text_of.__qualname__.startswith("MembretePDF"), (
        "el espía dejó su parche puesto sobre el membrete"
    )
