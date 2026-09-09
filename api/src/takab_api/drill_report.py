"""Reporte post-simulacro (T-5.14) — la evidencia que se le enseña a Protección Civil.

**El problema que cierra.** El acuse por sitio estaba bien hecho y era honesto —
distingue *sin gabinete comandable* de *sin acuse*, dos cosas que colapsar sería
mentir—, pero le faltaban las dos que el cliente pide: **el tiempo** (no existía
en ninguna capa) y **la salida** (no había PDF ni CSV; el propio código llamaba a
esto «la evidencia de cumplimiento» y solo se podía mirar en una pantalla).

**Las tres categorías no se colapsan, y ése es el punto del documento.** Un sitio
que no tenía gabinete comandable **no es** un sitio que no acusó: el primero es un
problema de inventario y el segundo de operación, y la reacción de quien lee el
reporte es distinta. Van en tres bloques con su conteo.

**Y un sitio sin acuse NO cuenta como cero en el tiempo.** Meterlo en la media la
hundiría hacia abajo justo con los sitios que peor están, que es la forma más
elegante de que un número diga lo contrario de lo que pasa.

El documento es **determinista** (mismo modelo, mismos bytes) porque su sello fija
la fecha de creación al arranque del simulacro y no al reloj de quien exporta —
sin eso, dos exportaciones del mismo simulacro darían hashes distintos y la
huella no probaría nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from fpdf.enums import XPos, YPos

from takab_api.dictamen.layout import MUTED, TakabPDF

#: Lo que el documento declara que NO es. Va impreso, como el del dictamen.
DESLINDE = (
    "Reporte operativo de simulacro. Acredita QUÉ gabinetes acusaron la orden y en cuánto "
    "tiempo; no acredita que las personas evacuaran ni sustituye el acta del simulacro que "
    "levanta la brigada del inmueble."
)


@dataclass(frozen=True)
class SitioReporte:
    site_name: str
    commandable: bool
    acked: bool
    latency_s: float | None
    #: [T-5.17] Lo que sonó en este sitio, tal como lo acusó el gabinete.
    #: `None` = el acuse no lo trae (firmware anterior). NO es «no sonó».
    audio: dict | None = None
    #: [T-6.16] El estado CRUDO del comando (`pending`/`acked`/`rejected`/
    #: `expired`). La consola ya distinguía un rechazo de un silencio y el
    #: documento los colapsaba en un guion; sin este campo no hay con qué.
    command_status: str | None = None
    #: [T-6.16] La razón que el propio gabinete dio al rechazar (`ack.detail`):
    #: `command_enabled=false`, `demo_mode`… Es lo único accionable del rechazo.
    ack_detail: str | None = None
    #: [T-6.17] Este sitio cortó el simulacro por una alerta real.
    aborted_at: datetime | None = None
    abort_reason: str | None = None


#: Cuántos caracteres del sha256 caben —y bastan— en una línea del reporte. Los
#: 16 primeros identifican el binario contra el catálogo; los 64 no caben por
#: sitio y nadie los teclea para comparar.
_HUELLA = 16


def linea_de_audio(sitio: SitioReporte) -> str:
    """Qué sonó en este sitio, en una línea del documento.

    TRES desenlaces, y ninguno se puede confundir con otro:

    * el gabinete voceó ⇒ el asset y su huella;
    * el gabinete resolvió y NO había voceo ⇒ «SIN VOCEO» **y la razón**, porque
      un lector que no sabe por qué no puede arreglarlo;
    * el gabinete no reportó nada ⇒ «NO REPORTADO». Es firmware anterior a
      `T-5.17`, y colapsarlo con el anterior afirmaría un silencio que nadie
      midió.
    """
    audio = sitio.audio
    if not isinstance(audio, dict):
        return "AUDIO NO REPORTADO POR EL GABINETE"
    sha = audio.get("sha256")
    if not sha or not audio.get("will_sound"):
        razon = str(audio.get("reason") or "el gabinete no declaró la razón")
        return f"SIN VOCEO — {razon}"
    origen = audio.get("asset_id") or "asset local del sitio"
    return f"{origen} · sha256 {str(sha)[:_HUELLA]}…"


#: [T-6.16] Cómo terminó, en castellano. El documento se entrega a Protección
#: Civil: `stop_reason='manual'` no es una frase que nadie pueda leer, y la
#: ausencia de la línea obligaba a preguntar por teléfono cómo acabó aquello.
_CIERRE = {
    "manual": "DETENIDO POR EL OPERADOR",
    "aborted": "ABORTADO POR UNA ALERTA REAL",
    "cancelled": "CANCELADO ANTES DE EJECUTARSE",
    "executed": "AGENDA EJECUTADA",
}


def nombre_presentable(name: str | None, code: str | None, site_id: str) -> str:
    """El nombre del sitio para un documento que se entrega, nunca su UUID.

    El reporte imprimía `str(site_id)[:8]` cuando faltaba el nombre, y ocho
    caracteres de un uuid **se leen como si fueran un nombre**. Se cae al CÓDIGO
    —lo que el operador teclea y reconoce— y, si tampoco hay, se declara que el
    sitio no tiene nombre registrado sin perder el identificador para buscarlo.
    """
    if name and name.strip():
        return name.strip()
    if code and code.strip():
        return code.strip()
    return f"SITIO SIN NOMBRE REGISTRADO ({str(site_id)[:8]})"


def linea_de_cierre(rep: ReporteSimulacro) -> str:
    """Cómo terminó el simulacro, en una línea.

    **No mira el reloj**, y eso no es un detalle: si dijera «en curso» o «ventana
    cumplida» según la hora de quien exporta, dos exportaciones del mismo
    simulacro darían bytes distintos y el sha256 registrado dejaría de probar
    nada (es la misma razón por la que el sello va con la fecha de arranque).
    """
    if rep.stopped_at is None:
        return f"SIN CERRAR — la ventana de {rep.duration_s} s corre desde el inicio"
    frase = _CIERRE.get(rep.stop_reason or "", "CERRADO SIN MOTIVO REGISTRADO")
    if rep.stop_reason == "aborted":
        motivo = next((s.abort_reason for s in rep.sitios if s.abort_reason), None)
        if motivo:
            return f"{frase} ({motivo})"
    return frase


def motivo_sin_acuse(sitio: SitioReporte) -> str:
    """POR QUÉ falta el acuse de este sitio. La consola ya lo sabía.

    Un RECHAZO es un gabinete que recibió la orden, verificó la firma y dijo que
    no —y su razón se puede arreglar—; un SILENCIO es un gabinete que no
    contestó. Colapsarlos en un guion, como hacía el documento, es pedirle al
    lector que reaccione igual a dos cosas distintas.
    """
    if not sitio.commandable:
        return "SIN GABINETE COMANDABLE — no había a quién mandarle la orden"
    estado = (sitio.command_status or "").lower()
    if estado == "rejected":
        razon = sitio.ack_detail or "el gabinete no declaró la razón"
        return f"RECHAZADO POR EL GABINETE — {razon}"
    if estado == "expired":
        return "EXPIRADO — la orden venció antes de que el gabinete la recogiera"
    return "SIN ACUSE — la orden salió y el gabinete no contestó"


def linea_de_aborto(sitio: SitioReporte) -> str:
    """[T-6.17] Un sitio que acusó y DESPUÉS cortó el simulacro por lo real.

    Cadena vacía si no abortó: quien lee no tiene por qué ver una línea que
    diga que no pasó nada.
    """
    if sitio.aborted_at is None:
        return ""
    razon = sitio.abort_reason or "el gabinete no declaró la razón"
    return f"ABORTADO {sitio.aborted_at:%H:%M:%S} UTC — {razon}"


@dataclass
class ReporteSimulacro:
    folio: str
    tenant_name: str
    drill_id: str
    started_at: datetime | None
    stopped_at: datetime | None
    duration_s: int
    note: str
    sitios: list[SitioReporte] = field(default_factory=list)
    #: [T-6.16] `manual` | `aborted` | `cancelled` | `executed` | None.
    stop_reason: str | None = None

    # --- los tres grupos, derivados y sin colapsar -------------------------
    @property
    def acusaron(self) -> list[SitioReporte]:
        return [s for s in self.sitios if s.commandable and s.acked]

    @property
    def no_acusaron(self) -> list[SitioReporte]:
        return [s for s in self.sitios if s.commandable and not s.acked]

    @property
    def sin_gabinete(self) -> list[SitioReporte]:
        return [s for s in self.sitios if not s.commandable]

    @property
    def latencias(self) -> list[float]:
        return sorted(s.latency_s for s in self.acusaron if s.latency_s is not None)

    @property
    def latencia_mediana_s(self) -> float | None:
        """`None` si nadie acusó. Los que no acusaron NO entran como cero."""
        v = self.latencias
        if not v:
            return None
        m = len(v) // 2
        return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2

    @property
    def latencia_maxima_s(self) -> float | None:
        v = self.latencias
        return v[-1] if v else None


def _t(segundos: float | None) -> str:
    """`252.0` → `4 min 12 s`. Sin dato dice SIN ACUSE, jamás `0 s`."""
    if segundos is None:
        return "SIN ACUSE"
    s = int(round(segundos))
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def render(rep: ReporteSimulacro) -> bytes:
    """PDF determinista del post-simulacro."""
    pdf = TakabPDF(rep.folio, f"REPORTE DE SIMULACRO · {rep.tenant_name}")
    # La fecha del sello es la del SIMULACRO, no la de la exportación: si fuera la
    # segunda, dos exportaciones del mismo simulacro darían hashes distintos y la
    # huella dejaría de probar nada.
    pdf.seal(rep.started_at)
    pdf.add_page()

    pdf.section("1", "EL SIMULACRO")
    pdf.field("IDENTIFICADOR", rep.drill_id)
    pdf.field("INICIO", f"{rep.started_at:%Y-%m-%d %H:%M:%S} UTC" if rep.started_at else "S/D")
    pdf.field("FIN", f"{rep.stopped_at:%Y-%m-%d %H:%M:%S} UTC" if rep.stopped_at else "SIN CERRAR")
    pdf.field("DURACIÓN PEDIDA", f"{rep.duration_s} s")
    # [T-6.16] CÓMO TERMINÓ. Sin esta línea, quien recibe el documento tiene que
    # llamar por teléfono para saber si el simulacro se cumplió, lo paró alguien
    # o lo cortó un sismo de verdad — tres desenlaces que no se parecen en nada.
    pdf.field("CIERRE", linea_de_cierre(rep))
    if rep.note:
        pdf.field("NOTA", rep.note)

    pdf.section("2", "ACUSE POR SITIO")
    # Las tres categorías con su conteo, y SIN colapsar: «no tenía gabinete» es un
    # problema de inventario y «no acusó» uno de operación.
    pdf.field("SITIOS QUE ACUSARON", f"{len(rep.acusaron)} de {len(rep.sitios)}")
    pdf.field("SITIOS QUE NO ACUSARON", str(len(rep.no_acusaron)))
    # [T-6.16] «SITIOS SIN GABINETE COMANDABLE» no cabe en la columna de
    # rótulos (52 mm) y el número se pegaba al texto. La categoría se explica
    # entera en la línea de cada sitio, aquí basta con nombrarla.
    pdf.field("SITIOS SIN GABINETE", str(len(rep.sin_gabinete)))

    pdf.ln(1)
    pdf.set_font(pdf.mono_font, "", 7.5)
    for s in rep.acusaron:
        pdf.cell(
            0,
            3.8,
            pdf.text_of(f"ACUSÓ           {s.site_name:<34} {_t(s.latency_s)}"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        # [T-5.17] Qué sonó, debajo del acuse y no en una sección aparte: quien
        # lee esta línea está preguntando por ESE edificio.
        pdf.cell(
            0,
            3.4,
            pdf.text_of(f"                  ↳ {linea_de_audio(s)}"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        # [T-6.17] Acusar y después cortar por una alerta real son DOS hechos;
        # el sitio cuenta como acuse y el corte se lee debajo, con su hora.
        aborto = linea_de_aborto(s)
        if aborto:
            pdf.cell(
                0,
                3.4,
                pdf.text_of(f"                  ↳ {aborto}"),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
    # [T-6.16] El guion de antes decía «falta el acuse» y nada más. Ahora va el
    # PORQUÉ, que es lo que la consola ya distinguía y el documento colapsaba.
    for s in rep.no_acusaron:
        pdf.cell(
            0,
            3.8,
            pdf.text_of(f"NO ACUSÓ        {s.site_name:<34} {motivo_sin_acuse(s)}"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    for s in rep.sin_gabinete:
        pdf.cell(
            0,
            3.8,
            pdf.text_of(f"SIN GABINETE    {s.site_name:<34} {motivo_sin_acuse(s)}"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    pdf.section("3", "TIEMPOS")
    if rep.latencia_mediana_s is None:
        pdf.callout(
            "NINGÚN SITIO ACUSÓ · no hay tiempos que reportar. La ausencia no es un cero: "
            "significa que no hubo un solo acuse, no que fueran instantáneos.",
            MUTED,
        )
    else:
        pdf.field("MEDIANA", _t(rep.latencia_mediana_s))
        pdf.field("MÁXIMO", _t(rep.latencia_maxima_s))
        pdf.para(
            "Calculados SOLO sobre los sitios que acusaron. Los que no acusaron no entran "
            "como cero: meterlos hundiría la media justo con los sitios que peor están.",
            size=7.5,
            muted=True,
        )

    pdf.section("4", "DESLINDE")
    pdf.callout(DESLINDE, (20, 24, 30))
    return bytes(pdf.output())
