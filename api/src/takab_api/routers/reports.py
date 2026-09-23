"""Exportación PDF por incidente (T-1.20 · B5).

``POST /incidents/{id}/report`` construye el reporte (incidente + cadena de
dictámenes + quórum con offsets + deslinde §1), lo sube al bucket de evidencia,
lo registra como ``evidence_objects kind='report_pdf'`` (sha256) con huella en
``audit_log`` y responde con la URL presignada de descarga.

Roles: los de la acción ``generate_report`` en la matriz (superadmin, inspector).
Es un subconjunto estricto de ``export``: gov_operator descarga evidencia ya
existente (``exports``), pero GENERARLA inserta una fila con el ``tenant_id`` del
incidente ajeno, que su propia RLS rechaza por diseño. La acción va separada para
que la consola no le pinte un botón condenado al 403 (regla de oro 7).
"""

from __future__ import annotations

import functools
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.dictamen.builder import build_model
from takab_api.dictamen.pdf import render
from takab_api.narrative import apply_narrative, build_narrative
from takab_api.queries import reports as q
from takab_api.routers._common import http_error
from takab_api.routers._s3 import PRESIGN_TTL_S, get_object, presign_get, put_object
from takab_api.schemas.reports import ReportOut
from takab_api.settings import Settings

# Fuente única: roles con acción generate_report en la matriz (espejo de RBAC §2).
REPORT_ROLES: tuple[str, ...] = roles_with_action("generate_report")

_require_report = require_roles(*REPORT_ROLES)

router = APIRouter()


#: Variantes del dictamen. `technical` es pericial; `executive` es para quien decide.
VARIANTS = ("technical", "executive")

#: [T-8.12] El `origen` que el certificado del móvil estampa en `export_pdf`.
ORIGEN_CERTIFICADO_MOVIL = "certificado_movil"


def _origen_desde_la_red() -> None:
    """[T-8.12 · 2ª vuelta] Desde la red, el origen es SIEMPRE la consola.

    Es una dependencia y no un parámetro de consulta a propósito: quien llama por
    HTTP no puede declararse «certificado del móvil» (`?origen=` se ignora y no
    aparece en el OpenAPI). Sólo quien llama a `generate_report` como FUNCIÓN
    —`mobile_incident._certificado`— lo pasa, explícito. Se DEDUCÍA del rol
    (`None` si el rol podía exportar), y un inspector que disparaba el
    certificado desde el móvil quedaba auditado como una exportación de consola.
    """
    return None


@router.post("/incidents/{incident_id}/report", response_model=ReportOut, status_code=201)
async def generate_report(
    incident_id: UUID,
    variant: str = Query("technical", description="technical | executive"),
    claims: Claims = Depends(_require_report),
    conn: AsyncConnection = Depends(get_session),
    origen: Annotated[str | None, Depends(_origen_desde_la_red)] = None,
) -> ReportOut:
    """Genera el PDF del incidente y lo registra como evidencia inmutable.

    [T-2.41] Dos documentos del mismo modelo. Se conserva `report_pdf` como `kind` de
    evidencia: la variante va en la key de S3 y en la auditoría, y ampliar el CHECK
    del DDL por una etiqueta no lo valdría.

    El gate de "sin dictamen no hay PDF" se retiró: un incidente sin dictamen YA tiene
    hechos que reportar —lo que midió el sensor, quién acusó, qué estaciones
    corroboraron— y el documento lo rotula como preliminar.

    [T-8.12 · A-054] Es TAMBIÉN la función que llama el certificado del móvil
    (`routers/mobile_incident._certificado`) cuando no hay un informe posterior a
    la firma: una sola tubería para el mismo documento, y un solo escritor de
    `export_pdf` —lo que hace contables los dos techos del freno
    (`tests/contracts/test_freno_de_exportacion_cuenta_lo_mismo.py`)—. Desde allí
    se llama como función, sin la puerta de rol del decorador: el certificado es
    un derivado de un dictamen YA firmado y lo pide un rol con `dictamen_read`.
    El freno sí se aplica, aquí dentro, igual que desde la consola.

    [T-8.12 · A-080] Lo SÍNCRONO va a un hilo: el render de fpdf2 es CPU pura y
    `put_object`/`presign_get` son boto3 bloqueante. La API corre con UN solo
    worker (`deploy/cloud/docker-compose.yml`), así que en el loop congelaban el
    WebSocket de la consola, `/health` y el sondeo que la app hace cada 5 s en
    crisis mientras duraba el render. Es el patrón de `commands/service.py`.
    """
    settings = Settings()
    if not settings.evidence_bucket:
        raise http_error(503, "bucket de evidencia no configurado")
    if variant not in VARIANTS:
        raise http_error(422, f"variante desconocida: {variant}")

    incident = (
        (await conn.execute(q.SELECT_INCIDENT, {"incident_id": incident_id})).mappings().first()
    )
    if incident is None:
        raise http_error(404, "incidente no encontrado")

    # [T-5.18] El freno, ANTES de renderizar: la única puerta de este endpoint era
    # de rol, así que un usuario autenticado podía reexportar el mismo incidente
    # sin límite — y cada exportación renderiza un PDF, lo sube a S3 y, con la IA
    # encendida, sale a una red de pago. Dos techos, el mismo par que los
    # comandos: el del usuario y el del EDIFICIO (dos operadores coordinados
    # agotan el segundo sin rebasar ninguno el suyo — `RO-8.e`).
    await _freno_de_exportacion(conn, claims, str(incident["site_id"]), settings)
    actor = f"user:{claims.sub}"

    model = await build_model(
        conn,
        str(incident_id),
        variant=variant,
        generated_at=datetime.now(tz=UTC),
        # La lectura del miniSEED es best-effort dentro del builder: un fallo de S3
        # degrada la sección, nunca tumba la exportación. El builder la llama en
        # un hilo (`_leer_objeto`, `_onda_de`).
        fetch_object=functools.partial(get_object, settings),
        settings=settings,
    )
    if model is None:  # pragma: no cover - el SELECT de arriba ya lo cubre
        raise http_error(404, "incidente no encontrado")

    # [T-2.42] Prosa que RODEA al veredicto. `build_narrative` nunca lanza: si el
    # proveedor falla, degrada al determinista y el PDF lo declara. El veredicto que
    # el documento afirma ya está en `model` y esta llamada no lo toca.
    #
    # [T-7.27·D-32] Las fotografías del brigadista que ve la IA salen de ESTE `model`,
    # que ya las trae leídas de S3 por el builder de arriba (`fetch_object`) y **ya
    # derivadas** por `documentos/fotos.preparar` —redimensionadas a 1024 px y sin el
    # EXIF del teléfono—. No se vuelven a leer de S3 aquí.
    #
    # ⚠️ [T-7.27·A] Lo que SÍ pasa, y este comentario decía lo contrario, es que la
    # fotografía se re-encoda una vez más antes de salir: la cámara forense hornea la
    # marca de agua EN EL PÍXEL —con las coordenadas del inmueble y el identificador del
    # operador— y esa banda se TAPA antes de mandarla (`narrative/marca.py`). Pintar
    # encima cambia los bytes, así que la fotografía que ve el modelo deja de tener la
    # huella que el papel publica. No se esconde: la procedencia de abajo anota las DOS
    # —la de lo enviado, que es la verificable contra el tercero, y la de lo impreso, que
    # es la que ata la transferencia a una fotografía del expediente— y lo que no se
    # puede tapar no se manda (`DanoRedactado.fotos_no_adjuntas` lo declara).
    narrative = await build_narrative(
        model,
        settings,
        conn=conn,
        tenant_id=str(incident["tenant_id"]),
        # [T-5.18] El actor va para que la fila de CRUCE de la cuota tenga
        # autor. Sin él la transición se sella igual —no se audita dos
        # veces— pero nadie sabría quién estaba exportando al agotarse.
        actor=actor,
    )
    apply_narrative(model, narrative)

    pdf = await anyio.to_thread.run_sync(render, model, variant)
    sha256 = hashlib.sha256(pdf).hexdigest()
    # [T-8.12] La clave lleva además la HUELLA del archivo. Con sólo el sello al
    # SEGUNDO, dos exportaciones de la misma variante en el mismo segundo —dos
    # operadores, o el certificado del móvil que se genera justo tras la firma—
    # caían en la MISMA clave: la segunda sobrescribía el objeto de la primera y
    # la fila de evidencia de aquélla quedaba citando un sha256 que ya no casaba
    # (medido: el test del certificado servía el PDF firmado bajo la clave del
    # preliminar). Es la clase de defecto de `A-142`. El nombre sigue empezando
    # por `report-`, que es la marca con que el backfill lo reconoce.
    key = (
        f"evidence/{incident['tenant_id']}/{incident_id}/"
        f"report-{variant}-{datetime.now(tz=UTC):%Y%m%dT%H%M%SZ}-{sha256}.pdf"
    )
    await anyio.to_thread.run_sync(
        functools.partial(put_object, settings, key, pdf, content_type="application/pdf")
    )

    ev_stmt, ev_params = q.insert_evidence(
        tenant_id=str(incident["tenant_id"]),
        incident_id=str(incident_id),
        s3_key=key,
        sha256=sha256,
    )
    evidence_id = (await conn.execute(ev_stmt, ev_params)).scalar_one()
    # Procedencia de la prosa. No hay tabla nueva: la narrativa queda congelada en el
    # PDF —que ya es evidencia inmutable con sha256— y su procedencia va al log
    # append-only, que por la regla de oro 11 no se poda nunca.
    #
    # ⚠️ [T-7.26] Esta fila es el registro de procedencia ENTERO de la IA y hasta esta
    # ficha no tenía ni un test: hoy la vigila
    # `tests/narrative/test_procedencia_narrative_generated.py`, que además DERIVA el
    # censo de claves de los campos de `Narrative` — un campo nuevo que no llegue aquí
    # pone la suite en rojo. En el `meta` viajan también la versión del prompt y el
    # sha256 de lo que devolvió el modelo, que son los dos que contestan «¿con qué
    # instrucciones y qué dijo exactamente?» el día que alguien audite el documento.
    await audit_async(
        conn,
        tenant_id=incident["tenant_id"],
        actor=actor,
        verb="narrative_generated",
        obj=f"evidence:{evidence_id}",
        meta=narrative.provenance(),
    )
    await audit_async(
        conn,
        tenant_id=incident["tenant_id"],
        actor=actor,
        verb="export_pdf",
        obj=f"evidence:{evidence_id}",
        # ⚠️ Un dict LITERAL y no una variable: el censo del freno
        # (`tests/contracts/test_freno_de_exportacion_cuenta_lo_mismo.py`) lee del
        # árbol de sintaxis que TODO escritor de `export_pdf` lleva `site_id`.
        meta={
            "variant": variant,
            "folio": model.folio,
            "content_sha256": model.content_sha256(),
            # [T-5.18] El sitio, para que el techo por EDIFICIO se pueda contar
            # desde aquí sin un join. El de usuario ya salía del `actor`.
            "site_id": str(incident["site_id"]),
            # [T-8.12 · 2ª vuelta] La cabeza de la cadena de dictámenes con que SE
            # RENDERIZÓ este papel. El certificado del móvil la exige igual a la
            # firma vigente (`queries/mobile.REPORT_PDF_TRAS_LA_FIRMA`): la fecha
            # sola comparaba el `now()` de dos transacciones, y una exportación
            # que leyó la cadena justo antes del commit de la firma quedaba
            # fechada después con el PRELIMINAR dentro.
            "dictamen_vigente": model.dictamens[0].dictamen_id if model.dictamens else None,
            **({"origen": origen} if origen else {}),
        },
    )
    return ReportOut(
        evidence_id=evidence_id,
        sha256=sha256,
        url=await anyio.to_thread.run_sync(presign_get, settings, key),
        expires_in=PRESIGN_TTL_S,
    )


# ──────────────────────────────── [T-5.18] el tope y el freno


_VENTANA_S = 60.0

#: Los dos conteos salen de `audit_log`, que es donde ya queda cada exportación y
#: que **no se poda nunca** (regla de oro 11): no hace falta tabla nueva ni un
#: contador que se pueda perder. El de usuario sale del `actor`; el del edificio,
#: del `site_id` que el `meta` empezó a llevar en esta misma ficha.
#:
#: ⚠️ [T-7.45] EL INVARIANTE QUE HACE CONTABLES ESTOS DOS NÚMEROS: `export_pdf`
#: tiene **un solo escritor**, `generate_report`, unas líneas más arriba —y desde
#: `T-8.12` el certificado del móvil lo LLAMA en vez de copiarlo—. Mientras
#: eso se cumpla, las dos consultas cuentan la misma población —las GENERACIONES—
#: y el techo estrecho no puede rebasarse por actos que el ancho no ve.
#:
#: Se rompió justo así: `routers/exports.py` escribía `export_pdf` al DESCARGAR y
#: sin `meta`, de modo que una descarga gastaba el techo de usuario y era invisible
#: para el del edificio. Seis descargas devolvían 429 a la primera generación.
#: Ahora la descarga tiene verbo propio (`download_<kind>`), y quien lo vigila es
#: `tests/contracts/test_freno_de_exportacion_cuenta_lo_mismo.py`, que deriva de
#: ESTAS dos cadenas quién puede escribir el verbo y qué clave tiene que llevar.
_CUENTA_USUARIO = text(
    "SELECT count(*) FROM audit_log WHERE verb = 'export_pdf' AND actor = :actor AND ts > :since"
)
_CUENTA_SITIO = text(
    "SELECT count(*) FROM audit_log "
    "WHERE verb = 'export_pdf' AND meta->>'site_id' = :site AND ts > :since"
)


async def _freno_de_exportacion(
    conn: AsyncConnection, claims: Claims, site_id: str, settings: Settings
) -> None:
    """429 si se rebasa el techo por usuario o el del edificio.

    Es el ÚNICO 429 de este endpoint, y llega antes de renderizar: rechazar
    después de haber gastado el PDF y la llamada de IA no protegería de nada.
    """
    since = datetime.now(tz=UTC) - timedelta(seconds=_VENTANA_S)
    actor = f"user:{claims.sub}"
    por_usuario = (
        await conn.execute(_CUENTA_USUARIO, {"actor": actor, "since": since})
    ).scalar_one()
    if por_usuario >= settings.report_rate_user_per_min:
        raise http_error(429, "rate-limit de exportación por usuario excedido")
    por_sitio = (await conn.execute(_CUENTA_SITIO, {"site": site_id, "since": since})).scalar_one()
    if por_sitio >= settings.report_rate_site_per_min:
        raise http_error(429, "rate-limit de exportación del sitio excedido")
