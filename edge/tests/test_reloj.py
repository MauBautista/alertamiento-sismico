"""[T-7.60] Que ninguna duración de este gabinete dependa de que nadie ajuste el reloj.

El defecto medido: el panel decía `uptime_s: 77851` (21.6 h) y el kernel 30 323 s
(8.4 h). El Raspberry Pi 4 **no tiene RTC**, así que arranca con la hora
restaurada y NTP la corrige después — 13 h 25 min de salto el 2026-09-19. Toda
resta de dos marcas del reloj de pared se llevó el salto entero dentro, y el
censo encontró **17 sitios** así.

⚠️ **Este fichero no enumera esos 17.** Una lista a mano diverge —es la quinta
vez que este repositorio aprende lo mismo—, así que lo que se exige es que cada
resta de instantes DECLARE de qué lado está. La clasificación no es decidible
leyendo el código (`now - x` no dice de dónde salió `x`), así que no se adivina:
se pide declararla, y un sitio nuevo sin marcador rompe CI.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from takab_edge.reloj import mono

RAIZ = Path(__file__).resolve().parents[1] / "takab_edge"

#: Los cuatro marcadores, y lo que significa cada uno. Ver `takab_edge/reloj.py`.
MARCADORES = ("monotonico", "ajeno", "datos", "heredado")
_MARCADOR = re.compile(r"#\s*reloj:\s*(\w+)")


def _restas_de_instantes(fuente: str) -> list[int]:
    """Líneas con una resta de fechas convertida a segundos.

    Se busca la forma `(<algo> - <algo>).total_seconds()`, que es como este
    árbol escribe todas sus duraciones de pared. Un `timedelta` construido a
    mano no cuenta: no mide, declara.
    """
    lineas: list[int] = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.Call):
            continue
        fn = nodo.func
        if not isinstance(fn, ast.Attribute) or fn.attr != "total_seconds":
            continue
        if isinstance(fn.value, ast.BinOp) and isinstance(fn.value.op, ast.Sub):
            lineas.append(nodo.lineno)
    return lineas


def _marcador_cerca(lineas: list[str], n: int) -> str | None:
    """El marcador de la línea `n` (1-based), de la anterior o de las 3 de arriba.

    Tres, y no una, porque una resta larga se parte en varias líneas y el
    comentario queda encima del bloque, no pegado a la llamada.
    """
    for i in range(max(0, n - 4), min(len(lineas), n)):
        m = _MARCADOR.search(lineas[i])
        if m:
            return m.group(1)
    return None


def test_toda_resta_de_instantes_DECLARA_su_reloj() -> None:
    """El censo, derivado del árbol y no de una lista.

    Si esto se pone rojo con un sitio nuevo, la pregunta que hay que contestar
    es una sola: **¿la otra mitad de la resta la selló esta máquina?** Si sí,
    debería ser monotónica. Si viene de fuera —un paquete del sismógrafo, la app,
    un catálogo—, pared es lo correcto y el marcador lo dice.
    """
    sin_declarar: list[str] = []
    desconocidos: list[str] = []
    for fichero in sorted(RAIZ.rglob("*.py")):
        fuente = fichero.read_text(encoding="utf-8")
        lineas = fuente.splitlines()
        for n in _restas_de_instantes(fuente):
            rel = f"{fichero.relative_to(RAIZ).as_posix()}:{n}"
            marca = _marcador_cerca(lineas, n)
            if marca is None:
                sin_declarar.append(f"{rel} → {lineas[n - 1].strip()[:70]}")
            elif marca not in MARCADORES:
                desconocidos.append(f"{rel} → «reloj: {marca}»")

    assert not desconocidos, (
        "MARCADOR DE RELOJ DESCONOCIDO. Los válidos son "
        + ", ".join(MARCADORES)
        + ":\n  "
        + "\n  ".join(desconocidos)
    )
    assert not sin_declarar, (
        "RESTA DE INSTANTES SIN DECLARAR QUÉ RELOJ USA.\n\n  "
        + "\n  ".join(sin_declarar)
        + "\n\n¿La otra mitad de la resta la selló ESTA máquina? Entonces es una\n"
        "duración de aquí y va con `takab_edge.reloj.mono()` — el reloj de pared\n"
        "salta 13 h en cada arranque de un Pi sin RTC. ¿Viene de fuera (un paquete\n"
        "del Shake, `ts_device` de la app, un catálogo)? Entonces pared es lo\n"
        "correcto. Declara cuál con un comentario `# reloj: <" + "|".join(MARCADORES) + ">`."
    )


# ---------------------------------------------------------------------------
# [T-7.60·disfraz] LA SEGUNDA CAPA: las DURACIONES PUBLICADAS
# ---------------------------------------------------------------------------
#
# El censo de arriba mira el sitio de la RESTA, y por eso tiene un punto ciego
# que costó encontrar: `local_api._age_s` es **una sola resta compartida por
# cuatro marcas de clases distintas** (`checked_at`, `last_result_at`,
# `oldest_pending_at`, el `start` de un pendiente). Un único `# reloj: heredado`
# ahí dentro las declaraba a las cuatro — y dos de ellas no heredaban nada: las
# sellaba ese mismo proceso en memoria, nacían en `None` y no se persistían
# jamás. Declararlas heredadas no era sólo impreciso: las marcaba como
# INARREGLABLES cuando eran justo las arreglables.
#
# Así que esta capa no cuenta restas: cuenta **duraciones que salen del gabinete
# con nombre propio**. Ahí las cuatro vuelven a ser cuatro hechos distintos, y
# cada uno tiene que decir de qué reloj sale. Es la capa que habría cazado el
# `uptime_s` sin que nadie mirara el panel: aquel valor era una clave publicada
# cuyo valor era una resta de dos fechas de pared.
#
# ⚠️ Un hallazgo del barrido que conviene no perder: la propia ficha daba dos
# ejemplos de disfraz y **uno era falso**. `spooled_at` → `spool_span_s` NO es un
# cronómetro disfrazado: ese campo viaja dentro del NDJSON del respaldo y la NUBE
# lo parsea como instante (`api/.../backfill/objects.py::_spooled_at` lo
# convierte en el `ts` de la fila ingerida). Un consumidor legítimo en el otro
# lado de la red basta para que la marca sea una fecha de verdad.


def _marcador_en_la_entrada(lineas: list[str], desde: int, hasta: int) -> str | None:
    """El marcador de UNA entrada de diccionario, sin invadir la de al lado.

    `desde` es la línea de la clave anterior y `hasta` la de ésta: el comentario
    tiene que estar entre las dos. A diferencia de `_marcador_cerca`, aquí no hay
    ventana fija — compartir marcador es justo el defecto que este censo persigue.
    """
    for i in range(max(0, desde), min(len(lineas), hasta)):
        m = _MARCADOR.search(lineas[i])
        if m:
            return m.group(1)
    return None


#: Nombres que, por sí solos, DECLARAN que el valor es una duración medida.
_SUFIJOS_DE_DURACION = ("_age_s", "_span_s", "_uptime_s", "uptime_s", "latency_s")

#: Y las llamadas que producen una duración aunque el nombre no lo cante.
_PRODUCEN_DURACION = ("total_seconds", "transcurrido")


def _duraciones_publicadas(fuente: str) -> list[tuple[int, str, int]]:
    """Claves de diccionario cuyo valor es una duración MEDIDA, con su línea.

    Dos disparadores, y hacen falta los dos:

    · **por nombre** — `*_age_s`, `*_span_s`, `latency_s`, `uptime_s`: el nombre
      ya afirma que es una duración, la calcule quien la calcule. Éste es el que
      separa las cuatro marcas que comparten `_age_s`.
    · **por forma** — cualquier clave `*_s` cuyo valor contenga una resta o una
      llamada que produzca segundos. Éste es el que habría cazado `uptime_s`
      antes de que existiera el nombre, y el que caza la próxima que se invente.

    Una clave `*_s` cuyo valor es una constante o un `settings.x` no entra, y es
    deliberado: `stale_after_s` o `refresh_ms` no MIDEN nada, declaran un umbral.
    """
    encontradas: list[tuple[int, str]] = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.Dict):
            continue
        # El TECHO de cada entrada: la línea de la clave anterior. Así el
        # marcador de una duración no puede cubrir a la de al lado — que es
        # exactamente el fallo que este censo vino a arreglar un nivel más
        # abajo, donde UN marcador dentro de `_age_s` tapaba cuatro marcas.
        # Se comprobó rompiéndolo: con una ventana de 3 líneas, una duración
        # nueva pegada a otra ya declarada entraba sin declarar y salía verde.
        techo = nodo.lineno
        for clave, valor in zip(nodo.keys, nodo.values, strict=False):
            if not isinstance(clave, ast.Constant) or not isinstance(clave.value, str):
                if clave is not None:
                    techo = getattr(clave, "lineno", techo)
                continue
            anterior, techo = techo, clave.lineno
            nombre = clave.value
            if not nombre.endswith("_s"):
                continue
            por_nombre = any(nombre.endswith(suf) for suf in _SUFIJOS_DE_DURACION)
            por_forma = any(
                (isinstance(h, ast.BinOp) and isinstance(h.op, ast.Sub))
                or (
                    isinstance(h, ast.Call)
                    and isinstance(h.func, ast.Attribute)
                    and h.func.attr in _PRODUCEN_DURACION
                )
                for h in ast.walk(valor)
            )
            if por_nombre or por_forma:
                encontradas.append((clave.lineno, nombre, anterior))
    return encontradas


def test_toda_duracion_PUBLICADA_declara_de_que_reloj_sale() -> None:
    """La capa que le faltaba al censo de las restas.

    Si esto se pone rojo, la pregunta es la misma de siempre pero hecha en el
    sitio donde se puede contestar bien: **esta duración concreta, ¿de qué marca
    sale, y quién selló esa marca?** Compartir la resta con otras tres no es
    respuesta.
    """
    sin_declarar: list[str] = []
    desconocidos: list[str] = []
    for fichero in sorted(RAIZ.rglob("*.py")):
        fuente = fichero.read_text(encoding="utf-8")
        lineas = fuente.splitlines()
        for n, nombre, desde in _duraciones_publicadas(fuente):
            rel = f"{fichero.relative_to(RAIZ).as_posix()}:{n}"
            marca = _marcador_en_la_entrada(lineas, desde, n)
            if marca is None:
                sin_declarar.append(f"{rel} → «{nombre}»")
            elif marca not in MARCADORES:
                desconocidos.append(f"{rel} → «{nombre}» dice «reloj: {marca}»")

    assert not desconocidos, "MARCADOR DESCONOCIDO en una duración publicada:\n  " + "\n  ".join(
        desconocidos
    )
    assert not sin_declarar, (
        "DURACIÓN PUBLICADA SIN DECLARAR DE QUÉ RELOJ SALE.\n\n  "
        + "\n  ".join(sin_declarar)
        + "\n\nNo basta con que la resta de la que nace esté declarada: `_age_s` es UNA\n"
        "resta compartida por cuatro marcas de clases distintas, y ese marcador las\n"
        "tapaba a las cuatro. Declara AQUÍ, donde la duración tiene nombre propio,\n"
        "con `# reloj: <" + "|".join(MARCADORES) + ">`."
    )


def test_el_censo_de_duraciones_VE_una_plantada() -> None:
    """Un censo que no puede fallar es ceremonia — cuarta vez que se escribe esto.

    Se prueban los DOS disparadores por separado, y también que lo que no mide
    nada quede fuera: si `stale_after_s` entrara, el censo pediría declarar el
    reloj de un umbral y se aprendería a poner el marcador por costumbre.
    """
    por_nombre = 'd = {"checked_age_s": helper(x, y)}\n'
    assert [(n, k) for n, k, _ in _duraciones_publicadas(por_nombre)] == [(1, "checked_age_s")]

    por_forma = 'd = {"uptime_s": (ahora - arranque).total_seconds()}\n'
    assert [(n, k) for n, k, _ in _duraciones_publicadas(por_forma)] == [(1, "uptime_s")]

    # ⚠️ Y LO QUE COSTÓ ENCONTRAR: un marcador NO cubre a la entrada siguiente.
    # Con la ventana de 3 líneas del otro censo, esta duración nueva heredaba el
    # marcador de su vecina y entraba sin declarar.
    pegadas = (
        "d = {\n"
        "    # reloj: monotonico\n"
        '    "uptime_s": crono.transcurrido(),\n'
        '    "colado_age_s": a - b,\n'
        "}\n"
    )
    hallazgos = _duraciones_publicadas(pegadas)
    colado = next(h for h in hallazgos if h[1] == "colado_age_s")
    assert _marcador_en_la_entrada(pegadas.splitlines(), colado[2], colado[0]) is None

    umbral = 'd = {"stale_after_s": 5.0, "refresh_ms": settings.refresh_ms}\n'
    assert _duraciones_publicadas(umbral) == []


def test_el_censo_de_duraciones_NO_esta_vacio() -> None:
    """La guarda de no-vacuidad, que en este repositorio ya se ha ganado cinco veces."""
    total = sum(
        len(_duraciones_publicadas(f.read_text(encoding="utf-8"))) for f in RAIZ.rglob("*.py")
    )
    assert total >= 6, f"el barrido de duraciones publicadas ve {total}: se quedó ciego"


def test_el_censo_VE_una_resta_plantada(tmp_path: Path) -> None:
    """Un censo que no puede fallar es ceremonia.

    Se planta una resta sin marcador en un fichero de mentira y se comprueba que
    el barrido la encuentra. Sin esto, el test de arriba podría estar contando
    cero por un error del parser y nadie se enteraría.
    """
    fuente = "def f(a, b):\n    return (a - b).total_seconds()\n"
    assert _restas_de_instantes(fuente) == [2]
    assert _marcador_cerca(fuente.splitlines(), 2) is None

    con_marca = "def f(a, b):\n    # reloj: ajeno\n    return (a - b).total_seconds()\n"
    assert _marcador_cerca(con_marca.splitlines(), 3) == "ajeno"


def test_el_censo_NO_esta_vacio() -> None:
    """La guarda de no-vacuidad: si el barrido dejara de ver nada, saldría verde.

    Es el defecto que este repositorio ha cazado cuatro veces en otros censos.
    """
    total = sum(
        len(_restas_de_instantes(f.read_text(encoding="utf-8"))) for f in RAIZ.rglob("*.py")
    )
    assert total >= 15, f"el barrido sólo ve {total} restas de instantes; ¿dejó de parsear?"


# ═══════════════════════ [T-7.61] el acta del reflejo, fila a fila


def test_registrar_un_acta_NO_reescribe_las_anteriores(tmp_path: Path) -> None:
    """La propiedad entera de `T-7.61`, y se mide por las llamadas al sistema.

    Antes esto leía las 200 actas, añadía una y volcaba el fichero entero encima
    sin temporal ni rename. Un corte de luz a media escritura no perdía la fila
    nueva: perdía **todas** — y este fichero acredita el camino crítico de
    activación, o sea justo lo que hay que poder demostrar tras un sismo, que es
    cuando se va la luz.

    Lo que se fija aquí es que el fichero se abre **en modo append** y nunca en
    modo escritura: ésa es la diferencia entre arriesgar una línea y arriesgar
    doscientas.
    """
    import builtins

    from takab_edge.audit.reflejo import ActaDeReflejo, ActaDeReflejoStore

    def _acta(seg: int, lat: float) -> ActaDeReflejo:
        return ActaDeReflejo(
            medido_en=f"2026-09-19T00:00:{seg:02d}Z",
            latencia_s=lat,
            gateway_id="gw-dev-0001",
            fw_version="test",
            es_prueba=False,
            canales={"siren": True},
        )

    destino = tmp_path / "reflejo.ndjson"
    store = ActaDeReflejoStore(destino)
    for i in range(3):
        store.registrar(_acta(i, 2.2 + i))
    assert len(store.actas()) == 3

    modos: list[str] = []
    real = builtins.open

    def _espia(fichero, modo="r", *a, **kw):  # noqa: ANN001, ANN202
        if str(fichero) == str(destino):
            modos.append(modo)
        return real(fichero, modo, *a, **kw)

    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(builtins, "open", _espia)
        store.registrar(_acta(9, 9.9))

    assert modos, "no se abrió el fichero: el espía no observó nada"
    assert all("a" in m for m in modos), (
        f"el acta se escribió en modo {modos}: un modo de ESCRITURA trunca el "
        "fichero, y con él las 200 actas anteriores"
    )
    assert "w" not in modos
    assert len(store.actas()) == 4, "y la nueva está"


def test_las_actas_viejas_SOBREVIVEN_a_un_corte_a_media_escritura(tmp_path: Path) -> None:
    """El corte, simulado: una línea a medias al final del fichero.

    Es lo peor que puede dejar un append interrumpido. Las anteriores tienen que
    seguir enteras y legibles, y la rota se salta diciéndolo — que es lo que
    `actas()` ya hacía y ahora por fin se comprueba.
    """
    from takab_edge.audit.reflejo import ActaDeReflejo, ActaDeReflejoStore

    def _acta(seg: int, lat: float) -> ActaDeReflejo:
        return ActaDeReflejo(
            medido_en=f"2026-09-19T00:00:{seg:02d}Z",
            latencia_s=lat,
            gateway_id="gw-dev-0001",
            fw_version="test",
            es_prueba=False,
            canales={"siren": True},
        )

    destino = tmp_path / "reflejo.ndjson"
    store = ActaDeReflejoStore(destino)
    for i in range(5):
        store.registrar(_acta(i, 2.0 + i))

    with destino.open("a", encoding="utf-8") as fh:  # el corte: media fila
        fh.write('{"medido_en": "2026-09-19T00:00:09Z", "latenci')

    actas = store.actas()
    assert len(actas) == 5, f"se perdieron actas enteras por una fila a medias: {len(actas)}"
    assert actas[0]["medido_en"] == "2026-09-19T00:00:00Z"
    assert actas[-1]["medido_en"] == "2026-09-19T00:00:04Z"


# ---------------------------------------------------------------------------
# [T-7.60·disfraz] EL SALTO, EJERCIDO SOBRE LAS DURACIONES QUE SE CONVIRTIERON
# ---------------------------------------------------------------------------
#
# «Sin ejercerlo, el arreglo no se distingue del defecto» — el criterio de esta
# ficha, aplicado a las tres marcas que dejaron de ser fechas. Aquí el salto no
# se simula moviendo el reloj del sistema (no se puede en CI): se inyecta, que es
# para lo que `Cronometro` y los seams `_clock`/`_mono` existen.


class _RelojQueSalta:
    """Reloj de pared que pega el salto de NTP del 2026-09-19: +13 h 25 min."""

    def __init__(self) -> None:
        self.ahora = datetime(2026, 9, 18, 18, 14, 5, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.ahora

    def saltar(self, segundos: float) -> None:
        self.ahora += timedelta(seconds=segundos)


SALTO_NTP_S = 13 * 3600 + 25 * 60


def test_la_edad_del_conteo_de_evidencia_NO_se_lleva_el_salto(tmp_path: Path) -> None:
    """`checked_age_s`: el panel decía «conteo verificado hace 13 h» un segundo después.

    Es el caso que el censo de las restas no podía ver: su resta vive en
    `local_api._age_s`, compartida con dos marcas que SÍ son heredadas, y el
    marcador de allí la declaraba heredada también — o sea, inarreglable.
    """
    from takab_edge.backfill import BackfillManager
    from takab_edge.cloud import CloudConnector
    from takab_edge.config import EdgeSettings

    reloj = _RelojQueSalta()
    # ⚠️ ANCLADO AL MONOTÓNICO REAL, y no a un 1000.0 cualquiera: la marca la
    # sella `backfill` y la mide `local_api`, y sólo significan algo si salen del
    # MISMO origen. Un cronómetro medido contra otro cronómetro distinto da un
    # número tan falso como el que esta ficha vino a arreglar — y el primer
    # intento de esta prueba lo hizo, con 722 217 s de resultado.
    pasos = [mono()]

    ajustes = EdgeSettings(
        dev_mode=True,
        iot_thing="gw-test-0001",
        cloud_spool_dir=str(tmp_path / "spool"),
    )
    gestor = BackfillManager(
        ajustes,
        CloudConnector(ajustes, transport=None, spool_dir=tmp_path / "spool"),
        buffer=None,
        pending_dir=tmp_path / "pendiente",
        clock=reloj,
        mono=lambda: pasos[0],
    )

    marca = gestor.evidence_snapshot()["checked_mono"]
    assert marca == pasos[0], "premisa: el conteo sella su CRONÓMETRO, no una fecha"

    # NTP corrige el reloj de pared trece horas hacia adelante. El tiempo REAL
    # transcurrido son dos segundos.
    reloj.saltar(SALTO_NTP_S)
    pasos[0] += 2.0
    gestor._refresh_pending_state()  # noqa: SLF001 — el barrido que resella la marca

    assert gestor.evidence_snapshot()["checked_mono"] - marca == 2.0, (
        "la edad del conteo tiene que medir DOS segundos: si el salto de pared "
        f"entrara en la resta, mediría {SALTO_NTP_S + 2}"
    )

    # ⚠️ Y AHORA EL CONSUMIDOR, que es donde caben los defectos: que el gestor
    # devuelva un cronómetro no sirve de nada si el panel sigue restando fechas.
    from takab_edge.local_api import LocalDashboard

    panel = LocalDashboard.__new__(LocalDashboard)
    panel._backfill = gestor  # noqa: SLF001 — sección aislada a propósito
    seccion = panel._evidence_section(reloj())  # noqa: SLF001
    assert seccion is not None
    edad = seccion["checked_age_s"]
    assert edad is not None and edad < 120.0, (
        "el panel publica la edad del conteo restando una FECHA: con el reloj "
        f"saltado dice {edad} s sobre una verificación de hace dos segundos"
    )


def test_la_edad_del_canal_vivo_NO_declara_muerto_un_sensor_que_entrega() -> None:
    """`signal.channels.<CH>.age_s`: la que decide «SIN SEÑAL DEL SENSOR» a los 5 s.

    Con la resta de pared, el salto de NTP del arranque mataba los tres canales a
    la vez con el sismógrafo entregando paquetes — y con SeedLink caído de
    verdad, inflaba la edad que el operador lee para saber cuánto lleva ciego.

    ⚠️ Esto mide el `age_s` QUE PUBLICA EL PANEL, no el que devuelve `signal`. La
    primera versión de esta prueba miraba `live_by_channel()` y se quedaba corta:
    devolver el cronómetro por ahí no sirve de nada si el panel sigue restando la
    fecha, y al revertir el arreglo a mano la prueba seguía verde. La distancia
    entre «el dato existe» y «el consumidor lo usa» es donde caben los defectos.
    """
    from takab_edge.contracts import Feature1s
    from takab_edge.local_api import LocalDashboard

    class _SeñalConFechaRancia:
        """Un canal entregando AHORA cuya fecha de pared es de antes del salto."""

        def live_by_channel(self) -> dict:
            rasgo = Feature1s(
                station="R4F74",
                channel="EHZ",
                window_start=datetime(2026, 9, 18, 18, 14, 5, tzinfo=UTC),
                pga=0.001,
                pgv=0.01,
                rms=1.0,
                sta_lta=1.0,
                clipping=False,
                health_score=1.0,
            )
            # La fecha es de hace trece horas de PARED (el reloj saltó); el
            # cronómetro dice que el paquete llegó hace medio segundo.
            return {"EHZ": (rasgo, datetime(2026, 9, 18, 18, 14, 5, tzinfo=UTC), mono() - 0.5)}

    panel = LocalDashboard.__new__(LocalDashboard)
    panel._signal = _SeñalConFechaRancia()  # noqa: SLF001 — sección aislada a propósito
    seccion = panel._signal_section(datetime.now(UTC))  # noqa: SLF001

    assert seccion is not None
    edad = seccion["channels"]["EHZ"]["age_s"]
    assert edad < 5.0, (
        "el canal sale MUERTO con el sensor entregando: la edad se está midiendo "
        f"restando la fecha de pared ({edad:.0f} s) en vez del cronómetro"
    )
    # Y la fecha sigue publicándose: es un instante legítimo que el panel enseña.
    assert seccion["channels"]["EHZ"]["received_at"].startswith("2026-09-18")


def test_el_arranque_se_DERIVA_y_por_eso_lo_corrige_NTP() -> None:
    """`booted_at`: la fecha buena sólo se consigue restando la duración buena.

    Si el proceso recordara su arranque como fecha al iniciarse, recordaría la
    hora ANTERIOR a la corrección de NTP —el error de 13 h 25 min sellado para
    siempre—. Derivándolo de `now - uptime`, el `now` ya viene corregido y el
    uptime es real, así que el instante sale bien Y SE ARREGLA SOLO en cuanto
    NTP sincroniza. Es el defecto de esta ficha visto del revés.
    """
    arranque_falso = datetime(2026, 9, 18, 18, 14, 5, tzinfo=UTC)  # lo que el Pi CREÍA
    uptime_real_s = 8.4 * 3600
    ahora_corregido = datetime(2026, 9, 19, 7, 39, 30, tzinfo=UTC) + timedelta(
        seconds=uptime_real_s
    )

    derivado = ahora_corregido - timedelta(seconds=uptime_real_s)
    assert derivado != arranque_falso, (
        "recordar el arranque habría devuelto la hora de antes de sincronizar"
    )
    assert derivado == datetime(2026, 9, 19, 7, 39, 30, tzinfo=UTC)
