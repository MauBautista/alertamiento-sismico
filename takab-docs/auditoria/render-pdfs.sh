#!/usr/bin/env bash
# [T-8.12 · A-055] Las diez variantes del PDF, generadas en LOCAL y rasterizadas.
#
# SIN nube y SIN base: el render es puro y se alimenta con los MISMOS modelos que
# usan las guardas (`tests/dictamen/test_pdf.py::model`,
# `tests/documentos/test_geometria.py::_modelo_con_todas_las_figuras`,
# `tests/dictamen/test_fotos_en_el_papel.py`, `tests/api/test_drill_report.py::_rep`).
# Si un modelo de prueba cambia, lo que se mira aquí cambia con él: no hay un
# segundo juego de datos que pueda quedarse atrás.
#
#   bash takab-docs/auditoria/render-pdfs.sh [DIR]      # por defecto /tmp/takab-pdf
#
# Deja en DIR:
#   01-tecnico.pdf … 09-narrativa-degradada.pdf   el dictamen / informe del evento
#   10-simulacro.pdf                              el reporte de simulacro
#   NN-*-<pág>.png                                cada página a 110 ppp (pdftoppm)
#
# Qué MIRAR en cada PNG (lo que las guardas de T-8.12 fijan, y lo que no ven):
#   01/02  portada y ejecutivo: CLASIFICACIÓN, severidad en castellano, APERTURA y
#          CIERRE con «· HH:MM:SS hora del centro», títulos del ejecutivo SIN «. »;
#          §7 columna NIVEL en castellano; §10 SENSOR ESTRUCTURAL; §12 nombres de
#          objeto; §13 hora local debajo de la UTC y QUIÉN en castellano; §15
#          rótulos del vídeo sin montarse en el valor; §17 rótulos largos
#          envueltos en su columna; §18 «FIRMÓ INSPECTOR · <nombre>», sin UUID.
#   03/04  leyenda REPRODUCCIÓN en la portada Y en el ejecutivo, y en la §7.
#   05     las siete figuras sin pisar el pie de página.
#   06     con UNA foto por reporte: nada encima del pie de foto (A-050).
#   07     fotos en VERTICAL encajadas en 88×88 mm, sin pisar el pie (A-051).
#   08/09  §16 con «Narrativa: <proveedor>» y el aviso de IA / NARRATIVA DEGRADADA.
#          La §16 de 01, 03 y 09 es la prosa DETERMINISTA REAL (`build_narrative`),
#          la que sale siempre que la IA está apagada o degrada: ni un valor de la
#          base en inglés («warning», «local_quorum», «siren_on ×1») ni un
#          instante ISO. Sólo la de 08 es relleno, porque la IA real no se llama
#          desde aquí; lo que se mira en 08 es el rótulo de asistencia.
#   10     simulacro: INICIO/FIN con hora local; nombres largos que envuelven con
#          sangría bajo el nombre y nunca pasan del margen derecho (A-143).
# Una guarda que pasa no sustituye a mirar el papel: las guardas miden lo que
# alguien pensó medir, y el ojo ve lo que nadie pensó.
set -euo pipefail

DIR="${1:-/tmp/takab-pdf}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
command -v pdftoppm >/dev/null || { echo "falta pdftoppm (poppler-utils)" >&2; exit 2; }

mkdir -p "$DIR"
rm -f "$DIR"/[01][0-9]-*.pdf "$DIR"/[01][0-9]-*.png

cd "$RAIZ/api"
# `tests` en el path porque `tests/api/test_drill_report.py` importa `auth_utils`
# y `seed_shared` por su nombre corto, como lo hace pytest. Importarlo NO abre la
# base: sólo lo harían sus tests asíncronos, que aquí no se llaman.
TAKAB_PDF_DIR="$DIR" PYTHONPATH=".:src:tests" uv run --quiet python - 2> >(grep -v "SIMULADO" >&2) <<'PY'
import asyncio
import hashlib
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from takab_api.compliance import ComplianceClaim, ComplianceDocument
from takab_api.dictamen.model import (
    ActionRow,
    CctvBlock,
    CctvObjectRow,
    DictamenRow,
    EvidenceRow,
    FotoFila,
)
from takab_api.dictamen.builder import folio_of
from takab_api.dictamen.pdf import render
from takab_api.documentos.fotos import preparar
from takab_api.drill_report import SitioReporte
from takab_api.drill_report import render as render_simulacro
from takab_api.narrative import apply_narrative, build_narrative
from takab_api.narrative.base import Narrative
from takab_api.narrative.deterministic import DeterministicProvider
from takab_api.narrative.prompts import SECTION_TITLES
from tests.api.test_drill_report import BASE, _rep
from tests.dictamen.test_fotos_en_el_papel import _dano, _foto, _jpeg
from tests.dictamen.test_pdf import _OPENED, model
from tests.documentos.test_geometria import _modelo_con_todas_las_figuras

salida = Path(os.environ["TAKAB_PDF_DIR"])


def escribe(nombre: str, datos: bytes) -> None:
    (salida / nombre).write_bytes(datos)
    print(f"  {nombre:<28} {len(datos):>9} bytes")


def retrato(semilla: int) -> FotoFila:
    """Una foto de teléfono en VERTICAL (3:4), que es la que desbordaba (A-051)."""
    crudo = _jpeg(semilla, w=1200, h=1600)
    d = preparar(crudo)
    h = hashlib.sha256(crudo).hexdigest()
    return FotoFila(
        evidence_id=f"{semilla:08d}-aaaa-bbbb-cccc-dddddddddddd",
        sha256_declarado=h,
        sha256_medido=h,
        sha256_impreso=d.sha256,
        ancho=d.ancho,
        alto=d.alto,
        jpeg=d.jpeg,
    )


def completo(**over):
    """El modelo de las pruebas con lo que el papel ROTULA: clasificación humana,
    firma con nombre, cronología con personas y sistema, custodia de los cuatro
    tipos, vídeo y marco normativo. Es lo que hay que mirar para A-144/A-145/A-053."""
    firmado = _OPENED + timedelta(hours=2)
    base = dict(
        clasificacion="real",
        clasificacion_en=_OPENED + timedelta(hours=1),
        verdict_signed=True,
        closed_at=_OPENED + timedelta(hours=3),
        state="closed",
        dictamens=[
            DictamenRow(
                "d-2",
                "inhabit_monitor",
                firmado,
                "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b",
                "dictamen-v1",
                "d-1",
                firmante_nombre="Ing. Laura Méndez",
            ),
            DictamenRow("d-1", "inhabit_monitor", _OPENED, None, "dictamen-v1", None),
        ],
        actions=[
            ActionRow(_OPENED, "siren_on", "system:edge"),
            ActionRow(_OPENED + timedelta(seconds=40), "ack", "user:7c1d2e3f-aaaa-bbbb-cccc-0000"),
            ActionRow(firmado, "dictamen_signed", "user:0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"),
        ],
        evidence=[EvidenceRow(k, "a" * 64, _OPENED) for k in ("miniseed", "photo", "report_pdf")],
        cctv=CctvBlock(
            objetos=[
                CctvObjectRow("captura", p, "b" * 64, _OPENED, "disponible")
                for p in ("pre", "egress", "peak", "reentry")
            ]
            + [CctvObjectRow("clip", None, "c" * 64, _OPENED, "PURGADO (retención de vídeo)")]
        ),
        compliance=ComplianceDocument(
            items=(
                ComplianceClaim(
                    key="regulatory_framework",
                    claim="Reglamento de Construcciones de la CDMX, Título Sexto",
                    reference="Gaceta Oficial, 29/01/2004, art. 139",
                ),
            )
        ),
        sensors=[{"kind": "structural", "model": "RS4D", "mount": "concrete_column"}],
    )
    base.update(over)
    m = model(**base)
    # El folio como lo compone `build_model`, para que 01 y 02 formen PAREJA (mismo
    # incidente, -T y -E); el del `model()` de las pruebas está tecleado.
    return replace(m, folio=folio_of(m.site_code, m.opened_at, m.incident_id, "technical"))


def ejecutivo(m):
    """El ejecutivo lleva SU folio (`-E`), como lo construye `build_model`: con el
    del técnico, el papel decía «-E resumen» en su propio texto bajo un folio -T."""
    return replace(m, folio=folio_of(m.site_code, m.opened_at, m.incident_id, "executive"))


class _ProveedorQueCae:
    """La IA que degrada (tiempo agotado): `build_narrative` cae al determinista."""

    name = "openrouter"

    async def generate(self, req):
        raise TimeoutError("el proveedor no respondió")


def prosa_real(m, proveedor=None):
    """La §16 como la pone `generate_report`: `build_narrative` + `apply_narrative`."""
    narrativa = asyncio.run(build_narrative(m, provider=proveedor or DeterministicProvider()))
    apply_narrative(m, narrativa)
    return m


def con_narrativa(proveedor: str, prosa: str, degradada: str | None = None):
    m = completo()
    secciones = tuple((t, prosa) for t in SECTION_TITLES)
    apply_narrative(
        m, Narrative(sections=secciones, provider=proveedor, degraded_reason=degradada)
    )
    return m


daño = dict(categorias=[{"key": "structural", "severity": "critical", "note": "grieta en muro"}])
escribe("01-tecnico.pdf", render(prosa_real(completo()), "technical"))
escribe("02-ejecutivo.pdf", render(ejecutivo(completo()), "executive"))
repro = dict(reproduccion=True, clasificacion="reproduccion")
escribe("03-repro-tecnico.pdf", render(prosa_real(completo(**repro)), "technical"))
escribe("04-repro-ejecutivo.pdf", render(ejecutivo(completo(**repro)), "executive"))
escribe("05-todas-figuras.pdf", render(_modelo_con_todas_las_figuras()))
escribe(
    "06-una-foto.pdf",
    render(
        model(
            danos=[
                _dano([_foto(3)], rol="security_guard", **daño),
                _dano([_foto(5)], report_id="d-2", rol="brigadista", **daño),
            ]
        )
    ),
)
escribe(
    "07-fotos-retrato.pdf",
    render(model(danos=[_dano([retrato(3), retrato(5), retrato(7)], **daño)])),
)
escribe(
    "08-narrativa-ia.pdf",
    render(con_narrativa("openrouter", "Prosa con acentos: ñ á é í ó ú ü. " * 6)),
)
escribe(
    "09-narrativa-degradada.pdf",
    render(prosa_real(completo(), _ProveedorQueCae())),
)
largo = "Torre Corporativa Reforma 222 · Edificio B Norte · Estacionamiento"
escribe(
    "10-simulacro.pdf",
    render_simulacro(
        _rep(
            SitioReporte("Planta Cholula", commandable=True, acked=True, latency_s=4.2),
            SitioReporte(
                largo,
                commandable=True,
                acked=True,
                latency_s=12.0,
                aborted_at=BASE + timedelta(minutes=1),
                abort_reason="SASMEX real · alerta recibida por el receptor WR-1",
            ),
            SitioReporte(
                largo, commandable=True, acked=False, latency_s=None, command_status="expired"
            ),
            SitioReporte(
                largo,
                commandable=True,
                acked=False,
                latency_s=None,
                command_status="rejected",
                ack_detail="command_enabled=false · el gabinete tiene los comandos apagados",
            ),
            SitioReporte(largo, commandable=False, acked=False, latency_s=None),
        )
    ),
)
PY

for f in "$DIR"/[01][0-9]-*.pdf; do
  pdftoppm -r 110 -png "$f" "${f%.pdf}"
done
echo "PNG en $DIR:"
ls -1 "$DIR"/*.png | sed 's#.*/#  #'
