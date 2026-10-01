"""El sonido OFICIAL del SASMEX, declarado y FUERA de git (T-9.70 · D-50).

Mauricio decidió el 2026-10-01 que suene con SASMEX (receptor WR-1) y con el cuórum de
red de 3 o más inmuebles; con el umbral local sigue el tono propio. El fichero es del
CIRES y se usa sin licencia escrita (D-50 revoca en parte D-19 y D-40, pendiente de
GATE-LEGAL), así que **nunca entra al repositorio**: vive en ``audios/`` del checkout
principal y se inyecta al publicar la release del gabinete (``deploy/edge/deploy.sh``)
y al compilar la APK (``mobile/plugins/withTonoOficial.js``).

Estas cifras se midieron UNA vez sobre el WAV derivado, generado así desde la raíz::

    ffmpeg -i audios/Sonido_Alerta_Sismica_Oficial.mp3 -c:a pcm_s16le /tmp/oficial.wav
    uv run --no-project --python 3.12 --with numpy==2.5.3 --with scipy==1.18.1 \\
      --with pyloudnorm==0.2.0 python tools/audio/normaliza.py --lufs -8 \\
      /tmp/oficial.wav audios/sasmex_oficial.wav

``--lufs -8`` pide la sonoridad de la sirena actual (-7,7 LUFS); el pico verdadero
(≤ -1 dBTP, sin limitador) la limita a -11,1 LUFS: lo más fuerte que da sin saturar.
Otra versión de ffmpeg podría dar otros bytes: por eso se fija la huella del WAV y no
se regenera; el gabinete y la app sólo suenan el fichero con ESTA huella.
"""

from __future__ import annotations

ID = "sasmex-oficial-v1"

#: Dónde aterriza al inyectarse en el gabinete; no existe en un clon limpio. En la app
#: va a `mobile/android/.../res/raw/alerta_oficial.wav`, que NO se declara aquí: ese
#: recurso lleva el tono PROPIO cuando se compila sin el oficial (`plugins/tonoOficial.js`).
RUTAS = [
    "edge/takab_edge/audio/assets/sasmex_oficial.wav",
]

#: El derivado que se inyecta, en el checkout principal (fuera de git).
LOCAL = "audios/sasmex_oficial.wav"

ORIGINAL = "audios/Sonido_Alerta_Sismica_Oficial.mp3"
ORIGINAL_SHA256 = "4e2f5e6f5075c5aa1e69f91377b7153831b8ed3779d6cfe431957bec0ddc61ca"

MEDIDO = {
    "sha256": "9b5e81de233a5736f0838f93550c5f03dffee1a5f0419aa194168d196a602896",
    "duracion_s": 59.5244,
    "sample_rate": 22050,
    "canales": 1,
    "lufs_integrado": -11.14,
    "pico_verdadero_dbtp": -1.1,
}
