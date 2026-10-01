"""Catálogo de tonos del gabinete (T-2.49).

La nube elige QUÉ tono suena, pero **solo por identificador de este catálogo**. Nunca
manda binarios ni rutas:

- **Binarios no**: el documento de config viaja FIRMADO por MQTT hacia un dispositivo
  que toca sirena, gas, ascensores y puertas (regla de oro 8). Un WAV arbitrario en ese
  canal convierte una superficie de configuración en una de ejecución de contenido.
- **Rutas absolutas no**: la nube no conoce el disco del gabinete. Una ruta que allá no
  existe deja al inmueble mudo sin que nadie lo note.

Los IDs se resuelven contra archivos que viajan EMPAQUETADOS con la release del edge,
así que el gabinete solo puede sonar lo que se auditó antes de desplegarlo.

**``sasmex-oficial-v1`` NO se elige por ranura.** El tono oficial de la Alerta
Sísmica Mexicana es propiedad del CIRES. Hasta el 2026-10-01 estaba reservado y ausente
(D-19); desde D-50 suena, decidido por Mauricio, pero **sólo con SASMEX y con el cuórum
de red** — lo elige el módulo de audio según POR QUÉ suena la sirena, no la nube. La
ranura ``siren`` también suena con el umbral local, donde la decisión deja el tono
propio, así que el ID sigue fuera de ``CATALOG`` y pedirlo en una ranura se rechaza.

El fichero viaja FUERA de git: ``deploy/edge/deploy.sh`` lo inyecta en la release como
``assets/OFICIAL_ARCHIVO``, y el gabinete sólo lo suena si su huella es
``OFICIAL_SHA256`` (la de ``tools/audio/oficial.py`` y ``shared/audio/MANIFEST.json``).
Sin él, o con otra huella, suena el tono propio y se declara. Pendiente de GATE-LEGAL.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("takab_edge.audio")

_ASSETS = Path(__file__).parent / "assets"

#: ID de catálogo → archivo empaquetado. Añadir uno exige empaquetar su WAV.
CATALOG: dict[str, str] = {
    "takab-siren-v1": "siren.wav",
    "takab-prueba-v1": "prueba.wav",
    # [T-5.17] Tono de SIMULACRO. **No es el mensaje hablado**: el voceo grabado
    # (`audio_simulacro_path`) sigue siendo un asset local y su gate de hardware
    # sigue abierto (`RUNBOOK-gate-hw-movil-y-voceo.md §C.2` pide dos grabaciones
    # distinguibles a oído, y nadie las ha hecho). Esto es lo que la nube SÍ puede
    # elegir mientras tanto, y está construido para no confundirse con la sirena:
    # carillón de tres pulsos con dos segundos de silencio — el patrón de la
    # megafonía, no el de una alarma. Ver `edge/scripts/gen_simulacro.py`.
    "takab-simulacro-v1": "simulacro.wav",
    # [T-9.71 · D-41] Simulacro HABLADO: «Esto es un simulacro.» sin tono en los
    # primeros 2,5 s, y después la frase cada 4,5 s sobre el tono de ALERTA, 15 dB
    # por debajo de la voz. Sólo en la ranura `simulacro` (ver RANURAS). Sustituye,
    # para este id, la regla de v1: ahora sí suena a alerta, y la voz es la barrera.
    # Ninguna configuración lo elige por defecto; se enciende por la firmada tras
    # escucharlo. Ver `tools/audio/gen_simulacro_hablado.py`.
    "takab-simulacro-v2": "simulacro_hablado.wav",
}

#: [T-9.71] En qué ranura puede sonar cada id. Sin esto, una config con las ranuras
#: cruzadas (`siren: takab-simulacro-v2`) se aplicaba sin queja, y en una alerta
#: REAL el jack habría dicho «Esto es un simulacro». Un id sin ranura declarada no
#: suena en ninguna: el censo de las pruebas exige que todo el catálogo esté aquí.
RANURAS: dict[str, frozenset[str]] = {
    "takab-siren-v1": frozenset({"siren"}),
    "takab-prueba-v1": frozenset({"test"}),
    "takab-simulacro-v1": frozenset({"simulacro"}),
    "takab-simulacro-v2": frozenset({"simulacro"}),
}


def reason_wrong_slot(asset_id: str, slot: str) -> str | None:
    """Por qué `asset_id` no puede sonar en `slot`, o ``None`` si puede.

    Como un id desconocido, conserva el tono anterior; pero se dice aparte, porque
    un cruce de ranuras no es un tecleo: es una alerta que sonaría a simulacro.
    """
    ranuras = RANURAS.get(asset_id, frozenset())
    if slot in ranuras:
        return None
    if not ranuras:
        return f"el tono {asset_id!r} no declara ranura"
    return f"el tono {asset_id!r} es de la ranura {', '.join(sorted(ranuras))}, no de {slot!r}"


#: [T-9.70 · D-50] El sonido oficial: su id, el nombre con el que la release lo trae y
#: la huella del ÚNICO fichero que el gabinete acepta sonar como tal.
OFICIAL_ID = "sasmex-oficial-v1"
OFICIAL_ARCHIVO = "sasmex_oficial.wav"
OFICIAL_SHA256 = "9b5e81de233a5736f0838f93550c5f03dffee1a5f0419aa194168d196a602896"

#: IDs que existen como concepto pero NO se pueden servir POR RANURA. Se distinguen de
#: un ID inventado para poder decir POR QUÉ no suena, en vez de un "desconocido" opaco.
RESERVED: dict[str, str] = {
    OFICIAL_ID: (
        "el tono oficial de SASMEX (propiedad de CIRES) no se elige por ranura: suena "
        "sólo con SASMEX y con el cuórum de red, y viaja fuera de git (D-50)"
    ),
}


def reason_reserved(asset_id: str) -> str | None:
    """Por qué un ID reservado no se puede servir, o ``None`` si no lo está.

    [T-5.17] Existe para que el reporte pueda decir «reservado por licencia» en
    vez de «desconocido». Los dos conservan el tono anterior, pero un descuido de
    tecleo y una infracción legal no son el mismo hecho.
    """
    return RESERVED.get(asset_id)


def resolve(asset_id: str) -> Path | None:
    """Ruta del tono, o ``None`` si el ID no se puede servir.

    ``None`` NUNCA significa "suena otra cosa": el llamador conserva el asset que ya
    tenía (ver ``AudioProfile.apply``). Sustituir en silencio un tono por otro es
    exactamente cómo un gabinete acaba sonando distinto de lo que su config declara.
    """
    if asset_id in RESERVED:
        log.warning("audio: el tono %r está reservado — %s", asset_id, RESERVED[asset_id])
        return None
    name = CATALOG.get(asset_id)
    if name is None:
        log.warning(
            "audio: tono %r desconocido para esta versión del edge (catálogo: %s); "
            "se conserva el tono anterior",
            asset_id,
            ", ".join(sorted(CATALOG)),
        )
        return None
    path = _ASSETS / name
    if not path.is_file():
        log.error(
            "audio: el tono %r está en el catálogo pero su archivo falta (%s)", asset_id, path
        )
        return None
    return path
