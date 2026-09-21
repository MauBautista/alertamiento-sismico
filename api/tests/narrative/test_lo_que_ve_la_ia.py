"""T-7.27 · Lo que la IA ve del evento, y lo que sigue sin salir de la nube.

`D-32` decidió que la IA recibe **la tabla por estación, la cronología, las categorías
de daño y las fotografías del brigadista**. Lo medido antes de escribir esto es que de
esos cuatro **no llegaba ninguno completo**:

* la tabla por estación no viajaba: solo el entero `station_count`;
* la cronología viajaba agregada a conteos por tipo, **sin marca de tiempo ni actor**;
* `damage_counts` estaba **muerto** —el canal existía (`facts_from(…, damage_counts=)`)
  y el único llamador de producción, `routers/reports.py`, no lo pasaba, así que viajaba
  vacío siempre—;
* y la reproducción histórica no viajaba en absoluto, aunque el PDF la declara en su §7
  con letra propia (`REPRODUCCION_NOTE`).

Este fichero fija las dos mitades del trato: **lo nuevo que sale** y **lo que sigue sin
salir por las vías nuevas**, que es donde una ampliación de allowlist se estropea. Cada
familia trae su control de no-vacuidad: un `not in` sobre un payload vacío es verde.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict

import pytest
from PIL import Image

from takab_api.dictamen.model import ActionRow, DanoFila, FotoFila
from takab_api.documentos import fotos as fotos_mod
from takab_api.narrative import apply_narrative
from takab_api.narrative.base import ROTULO_ASISTENCIA, Narrative
from takab_api.narrative.prompts import (
    INSTRUCCION_FOTOS,
    SECTION_TITLES,
    prompt_version,
    system_prompt,
    user_prompt,
)
from takab_api.narrative.redact import (
    MAX_FOTOS_IA,
    PRESUPUESTO_FOTOS_BYTES,
    _es_derivada,
    facts_from,
    imagenes_de,
)
from tests.dictamen.test_pdf import model

# El EXIF que pone un teléfono, con la misma forma que `tests/documentos/test_fotos.py`
# —de donde sale la medición que cita `D-32`—: marca, modelo y una cadena de ubicación.
MARCA = "TAKAB-Pixel8Pro"
LUGAR = "GPS 19.4326N 99.1332W domicilio del cliente"

_OPENED = model().opened_at


def _foto_cruda(w: int = 1600, h: int = 1200, *, exif: bool = True, ruido: int = 5) -> bytes:
    """Una foto sintética REPRODUCIBLE con el EXIF del teléfono dentro."""
    im = Image.new("RGB", (w, h), (120, 90, 60))
    px = im.load()
    for y in range(0, h, ruido):
        for x in range(0, w, ruido):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, (x + y) % 256)
    buf = io.BytesIO()
    if exif:
        datos = Image.Exif()
        datos[0x010F] = MARCA
        datos[0x0110] = "Pixel 8 Pro"
        datos[0x0112] = 6
        datos[0x010E] = LUGAR
        im.save(buf, format="JPEG", quality=92, exif=datos)
    else:
        im.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _foto_fila(crudo: bytes, evidence_id: str = "ev-1") -> FotoFila:
    """La fila tal como la deja el builder: la DERIVADA de `preparar`, jamás el crudo."""
    d = fotos_mod.preparar(crudo)
    return FotoFila(
        evidence_id=evidence_id,
        sha256_declarado="b" * 64,
        sha256_medido="c" * 64,
        sha256_impreso=d.sha256,
        ancho=d.ancho,
        alto=d.alto,
        motivo=d.motivo,
        jpeg=d.jpeg,
    )


def _dano(fotos: list[FotoFila], **over) -> DanoFila:
    base = {
        "report_id": "rep-1",
        "rol": "tactical",
        "zona": "Nivel 3 · Ala Norte",
        "categorias": [{"key": "structural", "severity": "critical", "note": "grieta en columna"}],
        "personas_en_riesgo": True,
        "notas": "el Sr. Pérez del 302 dice que hay olor a gas",
        "ts": _OPENED,
        "fotos": fotos,
        "fotos_omitidas": 0,
    }
    return DanoFila(**{**base, **over})


def _con_danos(n_fotos: int = 1, **over):
    fotos = [_foto_fila(_foto_cruda(), f"ev-{i}") for i in range(n_fotos)]
    return model(danos=[_dano(fotos)], **over)


def _payload(m) -> str:
    """Exactamente lo que se serializa como prompt de usuario."""
    return json.dumps(asdict(facts_from(m)), ensure_ascii=False, default=str)


# ─────────────────────────────── 1 · la tabla por estación


def test_la_tabla_por_estacion_VIAJA_con_sus_cifras() -> None:
    """Antes viajaba el entero `station_count` y nada más: la prosa no podía decir una
    sola cosa de una estación concreta sin inventársela."""
    f = facts_from(model())
    assert len(f.stations) == 2, "la tabla por estación no llega al proveedor"
    propia, vecina = f.stations
    assert propia.propia is True and vecina.propia is False
    assert (vecina.dist_km, vecina.peak_pga_g) == (112.0, 0.012)
    assert vecina.umbral_pga_g == 0.07 and vecina.umbral_origen == "referencia"
    assert propia.t_medido_s == 0.4 and propia.tier == "evacuate_or_hold"


def test_de_la_estacion_vecina_NO_sale_ni_su_nombre_ni_su_codigo_ni_su_sensor() -> None:
    """Una estación de la red es OTRO edificio con gente dentro.

    `redact.py` lleva escrito que el nombre del inmueble no sale; la tabla por estación
    es la vía por la que saldrían los nombres de todos los demás. Se identifican por su
    ORDEN en la tabla, que es lo que la prosa necesita para hablar de «la estación 2».
    """
    payload = _payload(model())
    for secreto in ("Torre CDMX", "CDMX-1", "AM.R4F74", "Planta Cholula"):
        assert secreto not in payload, f"la tabla por estación filtra {secreto!r}"
    assert "19.43" not in payload and "-99.13" not in payload, "las coordenadas viajan"
    assert '"orden": 2' in payload, "sin orden, la prosa no puede citar una fila"


# ─────────────────────────────── 2 · la cronología


def test_la_cronologia_viaja_con_MARCA_DE_TIEMPO_y_no_solo_conteos() -> None:
    m = model(
        actions=[
            ActionRow(_OPENED, "siren_on", "system:edge"),
            ActionRow(_OPENED.replace(second=42), "gas_closed", "user:abc-123-def"),
        ]
    )
    f = facts_from(m)
    assert [h.kind for h in f.timeline] == ["siren_on", "gas_closed"]
    assert f.timeline[1].t_desde_apertura_s == 42.0, "sin el desplazamiento no hay secuencia"
    assert f.timeline[0].rotulo == "SIRENA ACTIVADA", "el papel rotula y el prompt no"
    # Y el conteo por tipo SIGUE: es lo que la prosa usa para resumir.
    assert dict(f.action_counts)["siren_on"] == 1


def test_el_ACTOR_viaja_por_su_CLASE_y_nunca_el_identificador() -> None:
    """`incident_actions.actor` es `user:<sub de Cognito>`, `edge:<serie del gabinete>`
    o `system:<qué>`. La prosa necesita saber si lo hizo una persona, el gabinete o el
    sistema; el identificador es de una persona o de un aparato concreto."""
    m = model(
        actions=[
            ActionRow(_OPENED, "ack", "user:9f1e-cognito-sub"),
            ActionRow(_OPENED, "siren_on", "edge:RS-0007-SERIE"),
        ]
    )
    assert [h.actor for h in facts_from(m).timeline] == ["user", "edge"]
    payload = _payload(m)
    assert "9f1e-cognito-sub" not in payload
    assert "RS-0007-SERIE" not in payload, "la serie del gabinete identifica un aparato"


def test_un_verbo_sin_rotulo_se_declara_en_vez_de_inventarse() -> None:
    """`incident_actions` es append-only y exenta de poda: puede traer verbos que el
    registro de rótulos no conozca. Mismo criterio que el papel (`bitacora.py`)."""
    m = model(actions=[ActionRow(_OPENED, "verbo_de_otro_productor", "system:x")])
    hito = facts_from(m).timeline[0]
    assert hito.kind == "verbo_de_otro_productor"
    assert hito.rotulo is None, "un rótulo inventado es peor que declarar que no lo hay"


# ─────────────────────────────── 3 · los daños


def test_damage_counts_DEJA_DE_ESTAR_MUERTO_y_se_deriva_del_modelo() -> None:
    """El dato estaba en el modelo, a un `Counter` de distancia del prompt."""
    assert dict(facts_from(_con_danos()).damage_counts) == {"structural": 1}
    assert facts_from(model()).damage_counts == (), "sin reportes, el conteo es vacío de verdad"


def test_el_brigadista_aparece_POR_ROL_y_su_nota_NO_sale() -> None:
    """`D-32` por su nombre: «el brigadista aparece por **rol**, nunca por nombre».

    La nota es prosa libre que una persona escribe en el teléfono, con tope de 2000
    caracteres y sin validar: es exactamente para lo que existe esta allowlist.
    """
    m = _con_danos()
    d = facts_from(m).damage_reports[0]
    assert d.rol == "tactical"
    assert d.personas_en_riesgo is True
    assert d.categorias == (("structural", "critical"),)
    payload = _payload(m)
    assert "Sr. Pérez" not in payload and "olor a gas" not in payload
    assert "grieta en columna" not in payload, "la nota de la categoría es prosa libre igual"
    assert "Nivel 3" not in payload, "el nombre de la zona lo teclea el cliente"


def test_un_reporte_sin_asignacion_declara_que_NO_consta_el_rol() -> None:
    """`rol` es `None` cuando la asignación ya no existe. Rellenarlo con «brigadista»
    por costumbre sería inventar procedencia (mismo criterio que `DanoFila`)."""
    m = model(danos=[_dano([], rol=None)])
    assert facts_from(m).damage_reports[0].rol is None


# ─────────────────────────────── 4 · la reproducción


def test_la_REPRODUCCION_viaja_porque_el_papel_la_declara() -> None:
    """El §7 del informe imprime `REPRODUCCION_NOTE`: sin este booleano la prosa puede
    redactar como sismo de hoy un evento histórico que el mismo documento rotula."""
    assert facts_from(model(reproduccion=True)).reproduccion is True
    assert facts_from(model()).reproduccion is False


# ─────────────────────────────── 5 · las fotos


def test_las_fotos_van_REENCODADAS_y_el_EXIF_del_telefono_NO_viaja() -> None:
    """La decisión del integrador, con su medición.

    `documentos/fotos.py` la dejó medida en `T-7.22`: embebiendo el JPEG tal cual,
    **la marca del teléfono y la cadena de ubicación del EXIF viajan dentro** —lo fija
    `tests/documentos/test_fotos.py::test_la_derivada_NO_lleva_la_marca_del_telefono_ni_el_LUGAR`.
    Allí el destinatario era el PDF; aquí es un TERCERO fuera del país.
    """
    crudo = _foto_cruda()
    assert MARCA.encode() in crudo and LUGAR.encode() in crudo, (
        "la foto de prueba no lleva lo que hay que quitar: la guarda sería vacua"
    )
    imagenes = imagenes_de(_con_danos())
    assert len(imagenes) == 1
    assert MARCA.encode() not in imagenes[0].jpeg
    assert LUGAR.encode() not in imagenes[0].jpeg
    assert imagenes[0].jpeg != crudo, "viajó el blob crudo"


def test_la_foto_que_ve_la_IA_sale_DE_LA_MISMA_derivada_y_lleva_las_DOS_huellas() -> None:
    """Una sola derivada, y desde `T-7.27·A` **dos huellas**, porque son dos imágenes.

    La regla original —«una sola derivada y una sola huella»— existía para que el
    «SHA-256 DE LO IMPRESO» del documento casara con lo que vio el modelo. Tapar la banda
    de la marca de agua rompe esa igualdad por construcción: pintar encima cambia los
    píxeles. Lo que se conserva es el PROPÓSITO —poder atar lo que vio el modelo con lo
    que imprime el papel— y para eso viajan las dos: `sha256` es la del papel y
    `sha256_enviado` es la de los bytes que cruzaron la frontera.
    """
    m = _con_danos()
    imagen = imagenes_de(m)[0]
    impresa = m.danos[0].fotos[0]
    assert imagen.sha256 == impresa.sha256_impreso, "se perdió el vínculo con el papel"
    assert imagen.sha256_enviado == hashlib.sha256(imagen.jpeg).hexdigest()
    assert imagen.sha256_enviado != imagen.sha256, (
        "la huella de lo enviado es la de lo impreso: o no se tapó la marca, o se está "
        "anotando el número que no se puede verificar contra el tercero"
    )
    assert imagen.jpeg != impresa.jpeg, "viajó la derivada del papel, con la marca dentro"
    assert (imagen.ancho, imagen.alto) == (impresa.ancho, impresa.alto), (
        "el tapado recortó la fotografía en vez de pintar encima"
    )


def test_una_foto_CRUDA_colada_en_el_modelo_NO_sale_de_la_nube() -> None:
    """La guarda de la decisión, no su comentario.

    Hoy el builder solo pone derivadas ahí. Mañana, un camino nuevo que rellene
    `FotoFila.jpeg` con lo que bajó de S3 mandaría el EXIF a un tercero sin que nada se
    pusiera rojo. Lo que viaja se VERIFICA: JPEG, sin EXIF, sin otros metadatos y dentro
    del lado máximo.
    """
    crudo = _foto_cruda()
    colada = FotoFila(evidence_id="ev-x", sha256_declarado="b" * 64, jpeg=crudo)
    m = model(danos=[_dano([colada])])
    assert imagenes_de(m) == (), "una foto sin preparar viajó al proveedor"


# ⚠️ [T-7.27·A] Las CUATRO comprobaciones de `_es_derivada`, una a una y DISCRIMINADAS.
#
# La prueba de arriba las ejercía todas a la vez sobre el mismo blob —1600×1200 con
# EXIF— y por eso se podían borrar de una en una sin que nada se pusiera rojo: el lado
# máximo lo rechazaba cuando faltaba el EXIF, y el EXIF cuando faltaba el lado. Dos
# comprobaciones solapadas no son dos comprobaciones. Y el formato y el `except` no los
# ejercía nadie: ni un PNG, ni un blob corrupto, ni `jpeg=None` aparecían en la suite.


def _png_pequeno() -> bytes:
    """Un PNG dentro del lado máximo y sin metadato ninguno: lo ÚNICO que lo distingue
    de una derivada es el formato."""
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_con_exif(w: int = 768, h: int = 1024) -> bytes:
    """Un JPEG DENTRO del lado máximo y con el EXIF del teléfono. Es el caso que la
    comprobación del lado tapaba: un blob así viajaría con la marca del aparato y la
    cadena de ubicación dentro y ninguna prueba se pondría roja."""
    datos = Image.Exif()
    datos[0x010F] = MARCA
    datos[0x010E] = LUGAR
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (90, 90, 90)).save(buf, format="JPEG", quality=85, exif=datos)
    return buf.getvalue()


def _jpeg_con_xmp() -> bytes:
    """Un JPEG dentro del lado máximo, SIN EXIF y con XMP — que es donde Android escribe
    el GPS y el autor. `getexif()` no lo ve: con la comprobación anterior este blob
    viajaba con las coordenadas dentro."""
    xmp = (
        '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description exif:GPSLatitude="19,25.956000N" '
        f'tiff:Model="Pixel 8 Pro" dc:creator="{LUGAR}"/></rdf:RDF></x:xmpmeta>'
        '<?xpacket end="w"?>'
    ).encode()
    buf = io.BytesIO()
    Image.new("RGB", (768, 1024), (90, 90, 90)).save(buf, format="JPEG", quality=85, xmp=xmp)
    return buf.getvalue()


def test_la_derivada_de_PRODUCCION_pasa_la_verificacion() -> None:
    """El control positivo, y es el que hace que la allowlist de metadatos no sea una
    lista de deseos: lo que `preparar` produce tiene que pasar."""
    assert _es_derivada(fotos_mod.preparar(_foto_cruda()).jpeg) is True


def test_lo_que_NO_es_JPEG_no_sale_aunque_todo_lo_demas_cuadre() -> None:
    blob = _png_pequeno()
    with Image.open(io.BytesIO(blob)) as im:
        assert im.format == "PNG" and max(im.size) <= fotos_mod.LADO_MAX and not dict(im.getexif())
    assert _es_derivada(blob) is False, "un PNG pasó por derivada"


def test_un_JPEG_DENTRO_DEL_LADO_pero_CON_EXIF_no_sale() -> None:
    blob = _jpeg_con_exif()
    with Image.open(io.BytesIO(blob)) as im:
        assert max(im.size) <= fotos_mod.LADO_MAX, "lo rechazaría el lado, no el EXIF"
    assert MARCA.encode() in blob and LUGAR.encode() in blob
    assert _es_derivada(blob) is False, "un JPEG con el EXIF del teléfono pasó por derivada"


def test_el_EXIF_lo_rechaza_la_ALLOWLIST_DE_METADATOS_y_por_eso_no_hay_dos_guardas() -> None:
    """La equivalencia en la que se apoya haber quitado `not dict(im.getexif())`.

    En un JPEG el EXIF es el bloque `info["exif"]`, así que la allowlist de metadatos ya
    lo rechaza y la comprobación aparte no la podía matar ninguna prueba. Eso es una
    propiedad de Pillow y no una ley: si algún día deja de poblar `info["exif"]`, esta
    guarda se pone roja y hay que volver a poner la comprobación del EXIF.
    """
    with Image.open(io.BytesIO(_jpeg_con_exif())) as im:
        assert dict(im.getexif()), "el fixture perdió el EXIF: la guarda sería vacua"
        assert "exif" in im.info, (
            "Pillow ya no expone el EXIF como bloque de `info`: la allowlist de metadatos "
            "dejó de cubrirlo y `_es_derivada` necesita otra vez su propia comprobación"
        )


def test_un_JPEG_SIN_EXIF_pero_con_XMP_no_sale() -> None:
    blob = _jpeg_con_xmp()
    with Image.open(io.BytesIO(blob)) as im:
        assert not dict(im.getexif()), "lo rechazaría el EXIF, no el XMP"
        assert "xmp" in im.info
    assert b"GPSLatitude" in blob
    assert _es_derivada(blob) is False, "un JPEG con GPS en el XMP pasó por derivada"


def test_un_JPEG_SIN_EXIF_pero_MAS_GRANDE_que_el_lado_maximo_no_sale() -> None:
    blob = _foto_cruda(1600, 1200, exif=False)
    with Image.open(io.BytesIO(blob)) as im:
        assert not dict(im.getexif()), "lo rechazaría el EXIF, no el lado"
        assert max(im.size) > fotos_mod.LADO_MAX
    assert _es_derivada(blob) is False, "una foto por encima del lado máximo pasó por derivada"


@pytest.mark.parametrize(
    "blob",
    [
        pytest.param(None, id="S3 caído: `jpeg` es None"),
        pytest.param(b"", id="blob vacío"),
        pytest.param(b"\xff\xd8\xff\xe0" + b"truncado" * 30, id="JPEG truncado"),
        pytest.param(b"esto no es una imagen", id="no es una imagen"),
    ],
)
def test_lo_que_NO_SE_PUEDE_VERIFICAR_no_sale(blob: bytes | None) -> None:
    """El `except` que nadie ejercía. Lo que no se puede abrir no se puede verificar, y
    lo que no se puede verificar no sale."""
    assert _es_derivada(blob) is False


def test_nunca_viajan_mas_de_SEIS_fotos() -> None:
    """El número es de `D-32` y lo comparte `documentos/fotos.py`."""
    fotos = [_foto_fila(_foto_cruda(ruido=3 + i), f"ev-{i}") for i in range(4)]
    m = model(danos=[_dano(fotos[:3]), _dano(fotos[3:] + fotos[:3], report_id="rep-2")])
    imagenes = imagenes_de(m)
    assert MAX_FOTOS_IA == 6
    assert len(imagenes) == 6, "el tope de seis no se aplica sobre el DOCUMENTO entero"


def test_lo_que_VIAJA_cabe_en_el_presupuesto_de_bytes_y_lo_hace_por_construccion() -> None:
    """Un tope en número de fotos NO es un tope de tamaño — y desde `T-7.27·A` el tamaño
    lo acota otra pieza, así que hay que decir CUÁL.

    ⚠️ La prueba anterior fabricaba sus fotos con `_jpeg_de(PRESUPUESTO_FOTOS_BYTES // 2)`:
    el fixture dependía de la constante que una mutación cambiaría, de modo que al mover
    el presupuesto el test se rompía en el `raise` del fixture —«no se pudo fabricar un
    JPEG del tamaño pedido»— y las dos aserciones que importan no llegaban a correr. Se
    ponía rojo por la razón equivocada, que es una forma de verde.

    Hoy el techo de lo que viaja es el de `marca.tapar_banda_forense`, que re-encoda a
    `min(peso de la impresa, MAX_BYTES_SALIDA)`: seis fotografías por documento con ese
    techo son exactamente `PRESUPUESTO_FOTOS_BYTES`. El presupuesto queda de cinturón, y
    lo que hay que ejercer —y se ejerce aquí— es que **ninguna colada legítima pero gorda
    lo rebase**.
    """
    gordas = [
        FotoFila(evidence_id=f"ev-{i}", sha256_declarado="b" * 64, jpeg=_jpeg_gordo())
        for i in range(MAX_FOTOS_IA)
    ]
    assert all(len(f.jpeg) > fotos_mod.MAX_BYTES_SALIDA for f in gordas), (
        "las coladas no rebasan el techo por foto: la guarda sería vacua"
    )
    m = model(danos=[_dano(gordas)])
    imagenes = imagenes_de(m)
    assert len(imagenes) == MAX_FOTOS_IA, "el presupuesto acotó de más"
    assert all(len(i.jpeg) <= fotos_mod.MAX_BYTES_SALIDA for i in imagenes)
    assert sum(len(i.jpeg) for i in imagenes) <= PRESUPUESTO_FOTOS_BYTES


def test_el_presupuesto_se_cobra_sobre_LO_QUE_VIAJA_y_no_sobre_lo_impreso() -> None:
    """Son bytes distintos desde que hay tapado. Cobrar los otros dejaba el peso real de
    la petición sin cota, que es justo lo que el presupuesto existe para impedir."""
    m = model(danos=[_dano([_foto_fila(_foto_cruda(ruido=2))])])
    imagen = imagenes_de(m)[0]
    assert len(imagen.jpeg) != len(m.danos[0].fotos[0].jpeg), (
        "lo que viaja pesa exactamente lo que lo impreso: no se tapó nada"
    )


def _jpeg_gordo() -> bytes:
    """Una derivada LEGÍTIMA —pasa la verificación— pero más gorda de lo que `preparar`
    produce: 768×1024 a calidad 100. El tamaño NO se deriva de ninguna cota del sistema,
    a propósito: un fixture que depende de la constante que se está midiendo se rompe
    antes de llegar a la propiedad."""
    im = Image.new("RGB", (768, 1024))
    px = im.load()
    for y in range(1024):
        for x in range(768):
            px[x, y] = ((x * 7 + y * 3) % 256, (y * 13) % 256, (x * x + y) % 256)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=100)
    return buf.getvalue()


def test_los_hechos_declaran_CUANTAS_fotos_hay_y_cuantas_se_mandan() -> None:
    """Sin esto, el modelo lee seis fotografías y cree que las ha visto todas.

    Es la misma honestidad que el papel: «entregar seis de once sin decirlo es recortar
    la evidencia en silencio» (`DanoFila.fotos_omitidas`).
    """
    fotos = [_foto_fila(_foto_cruda(ruido=3 + i), f"ev-{i}") for i in range(4)]
    m = model(danos=[_dano(fotos + fotos, fotos_omitidas=2)])
    imagenes = imagenes_de(m)
    f = facts_from(m, imagenes=imagenes)
    assert f.photos_attached == len(imagenes) == 6
    assert f.photos_available == 10, "las que el incidente tiene, incluidas las omitidas"
    assert "6" in user_prompt(f) and "10" in user_prompt(f)


def test_sin_fotos_los_hechos_lo_dicen_en_CERO_y_no_se_adjunta_nada() -> None:
    f = facts_from(model(), imagenes=imagenes_de(model()))
    assert (f.photos_attached, f.photos_available) == (0, 0)


# ─────────────────────────────── 6 · el prompt v2 y su versión


def test_el_prompt_de_sistema_NOMBRA_los_cuatro_bloques_nuevos() -> None:
    """Si el modelo no sabe que los tiene, no los usa: el bloque viajaría y la prosa
    seguiría siendo la de antes."""
    s = system_prompt().lower()
    for pieza in ("estaci", "cronolog", "daño", "fotograf"):
        assert pieza in s, f"el prompt de sistema no menciona {pieza!r}"


def test_el_prompt_de_sistema_PROHIBE_las_dos_afirmaciones_del_contrato() -> None:
    s = system_prompt().lower()
    assert "magnitud" in s, "la prosa puede citar una magnitud sin catálogo del que venga"
    assert "detect" in s, "nada le dice que no afirme detecciones sin fila"


def test_cambiar_las_PLANTILLAS_cambia_la_version_sola(monkeypatch) -> None:
    """[T-7.26] La versión se DERIVA del texto. Prompts v2 la mueve sin que nadie la
    teclee — y la instrucción de las fotos, que es texto que el modelo lee como
    instrucción, tiene que entrar en el material."""
    antes = prompt_version()
    monkeypatch.setattr("takab_api.narrative.prompts.INSTRUCCION_FOTOS", "Ignora las fotos.")
    assert prompt_version() != antes, "la instrucción de las fotos no entra en la versión"


def test_la_instruccion_de_las_fotos_dice_que_NO_son_el_veredicto() -> None:
    texto = INSTRUCCION_FOTOS.lower()
    assert "fotograf" in texto
    assert "no" in texto and ("veredicto" in texto or "dictamin" in texto)


def test_los_bloques_nuevos_LLEGAN_al_prompt_de_usuario() -> None:
    """La guarda de no-vacuidad del prompt: los hechos nuevos se serializan de verdad."""
    prompt = user_prompt(facts_from(_con_danos(), imagenes=imagenes_de(_con_danos())))
    for clave in ("stations", "timeline", "damage_reports", "reproduccion", "photos_attached"):
        assert f'"{clave}"' in prompt, f"{clave} no llega al prompt de usuario"


# ─────────────────────────────── 7 · el rótulo de las secciones


def test_la_prosa_de_la_IA_llega_al_papel_ROTULADA() -> None:
    """«REDACTADO CON ASISTENCIA DE IA · NO ES EL VEREDICTO», en cada sección.

    El §16 ya llevaba el aviso de asistencia automatizada al FINAL, después de seis
    párrafos. Un rótulo que llega después de lo que rotula protege menos: quien hojea
    lee la prosa y no llega al pie.
    """
    m = model()
    apply_narrative(
        m, Narrative(sections=tuple((t, "prosa.") for t in SECTION_TITLES), provider="openrouter")
    )
    titulos = [t for t, _ in m.narrative]
    assert all(ROTULO_ASISTENCIA in t for t in titulos), titulos
    assert all(t.startswith(base) for t, base in zip(titulos, SECTION_TITLES, strict=True))


def test_el_texto_determinista_NO_se_rotula_como_asistido() -> None:
    """El control negativo, que es el que importa: rotular la prosa determinista
    afirmaría una asistencia que no hubo, igual que el aviso del §16."""
    m = model()
    apply_narrative(m, Narrative(sections=(("Resumen ejecutivo", "x"),), provider="deterministic"))
    assert m.narrative == [("Resumen ejecutivo", "x")]


def test_el_rotulo_y_el_AVISO_DEL_16_salen_juntos_en_el_PAPEL() -> None:
    """Los dos dicen lo mismo con distinta longitud, y por eso hay que atarlos.

    `NARRATIVE_AI_NOTE` (T-5.07) es la frase larga del pie del §16; el rótulo es la
    etiqueta del título. Dos textos para el mismo hecho es exactamente cómo el papel
    acabó con dos vocabularios en `T-7.26`, así que aquí se exige que aparezcan **los
    dos o ninguno**: el rótulo sin el aviso dejaría el documento sin la frase que el
    censo de avisos impresos vigila, y el aviso sin el rótulo es el estado de antes.

    Se mide sobre lo que el render DIBUJA, no sobre el modelo: del PDF no se raspa
    texto (doctrina del repositorio) y el espía de `text_of` es lo que hay.
    """
    from takab_api.dictamen.model import NARRATIVE_AI_NOTE
    from tests.dictamen.test_avisos_impresos import _texto_dibujado

    con_ia = model()
    apply_narrative(
        con_ia,
        Narrative(
            sections=tuple((t, "Prosa de la sección.") for t in SECTION_TITLES),
            provider="openrouter",
        ),
    )
    papel = _texto_dibujado(con_ia, "technical")
    assert ROTULO_ASISTENCIA in papel, "la prosa asistida llega al papel SIN rótulo"
    assert NARRATIVE_AI_NOTE in papel, "el rótulo salió y el aviso del §16 no"

    determinista = model()
    apply_narrative(
        determinista,
        Narrative(
            sections=tuple((t, "Prosa de la sección.") for t in SECTION_TITLES),
            provider="deterministic",
        ),
    )
    papel_det = _texto_dibujado(determinista, "technical")
    assert ROTULO_ASISTENCIA not in papel_det, "se rotula como asistida una prosa que no lo es"
    assert NARRATIVE_AI_NOTE not in papel_det


def test_el_rotulo_CABE_en_el_ancho_del_papel() -> None:
    """Un rótulo que desborda el ancho se pinta encima del margen y no se lee.

    Se mide con la tipografía y el tamaño reales del encabezado de sección del §16
    (`pdf.set_font(pdf.body_font, "B", 8)`), no a ojo.
    """
    from takab_api.dictamen.layout import TakabPDF
    from takab_api.documentos.membrete import CONTENT_W

    m = model()
    pdf = TakabPDF(m.folio, "DICTAMEN OPERATIVO PRELIMINAR", sellado=m.opened_at)
    pdf.add_page()
    util = CONTENT_W
    pdf.set_font(pdf.body_font, "B", 8)
    for titulo in SECTION_TITLES:
        ancho = pdf.get_string_width(pdf.text_of(f"{titulo} · {ROTULO_ASISTENCIA}".upper()))
        assert ancho <= util, f"«{titulo}» rotulado mide {ancho:.1f} mm y caben {util:.1f} mm"


# ─────────────────────────── 8 · [T-7.27·A] el hueco se DECLARA, en las cinco vías
#
# `DanoRedactado.fotos_no_adjuntas` se justifica con la doctrina del papel —«seis de once
# sin decirlo es recortar la evidencia en silencio»— y **ninguna prueba lo miraba**:
# medido, se podía fijar a 0 y las 201 seguían verdes. Es además el campo que declara el
# camino degradado: con `jpeg=None` en las tres fotos de un reporte es lo único que le
# dice al modelo que el incidente tiene evidencia que él no vio.


def _sin_blob(evidence_id: str) -> FotoFila:
    """La fila que deja el builder cuando S3 no contestó: la foto EXISTE y no hay bytes."""
    return FotoFila(
        evidence_id=evidence_id,
        sha256_declarado="b" * 64,
        jpeg=None,
        motivo=fotos_mod.SIN_BLOB,
    )


def _corrupta(evidence_id: str) -> FotoFila:
    return FotoFila(evidence_id=evidence_id, sha256_declarado="b" * 64, jpeg=b"\xff\xd8no")


def test_con_S3_CAIDO_el_modelo_sabe_que_hay_evidencia_que_NO_ha_visto() -> None:
    m = model(danos=[_dano([_sin_blob(f"ev-{i}") for i in range(3)])])
    f = facts_from(m, imagenes=imagenes_de(m))
    d = f.damage_reports[0]
    assert (f.photos_attached, f.photos_available) == (0, 3)
    assert (d.fotos_adjuntas, d.fotos_no_adjuntas) == (0, 3), (
        "el prompt no declara las tres fotografías que el modelo no vio"
    )


def test_una_foto_ILEGIBLE_entre_dos_buenas_se_cuenta_como_no_adjunta() -> None:
    fotos = [
        _foto_fila(_foto_cruda(ruido=3), "ev-0"),
        _corrupta("ev-1"),
        _foto_fila(_foto_cruda(ruido=4), "ev-2"),
    ]
    m = model(danos=[_dano(fotos)])
    d = facts_from(m, imagenes=imagenes_de(m)).damage_reports[0]
    assert (d.fotos_adjuntas, d.fotos_no_adjuntas) == (2, 1)


def test_las_que_el_PAPEL_omitio_tambien_cuentan_como_no_adjuntas() -> None:
    """`fotos_omitidas` son las que quedaron fuera del tope del documento: existen en el
    expediente y el incidente las tiene."""
    m = model(danos=[_dano([_foto_fila(_foto_cruda())], fotos_omitidas=4)])
    d = facts_from(m, imagenes=imagenes_de(m)).damage_reports[0]
    assert (d.fotos_adjuntas, d.fotos_no_adjuntas) == (1, 4)


def test_lo_que_queda_fuera_del_TOPE_DE_SEIS_se_declara_reporte_a_reporte() -> None:
    """Con dos reportes y ocho fotografías, el segundo se queda corto y tiene que
    decirlo: el tope es del DOCUMENTO, no de cada reporte."""
    fotos = [_foto_fila(_foto_cruda(ruido=3 + i), f"ev-{i}") for i in range(4)]
    m = model(danos=[_dano(fotos), _dano(fotos, report_id="rep-2")])
    imagenes = imagenes_de(m)
    assert len(imagenes) == MAX_FOTOS_IA
    uno, dos = facts_from(m, imagenes=imagenes).damage_reports
    assert (uno.fotos_adjuntas, uno.fotos_no_adjuntas) == (4, 0)
    assert (dos.fotos_adjuntas, dos.fotos_no_adjuntas) == (2, 2), (
        "el segundo reporte no declara las dos que no cupieron"
    )
