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
from pathlib import Path

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
