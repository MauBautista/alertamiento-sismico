# Imagen del Lambda de conteo (T-3.12.b · D-24).
#
# EL MODELO Y EL FFMPEG VAN HORNEADOS, NO SE DESCARGAN AL ARRANCAR
# ────────────────────────────────────────────────────────────────
# Es la decisión que más condiciona esta imagen y tiene una razón que no es de latencia:
# un número que acaba en un DICTAMEN tiene que poder atribuirse a una versión exacta del
# modelo. Un peso que se baja al vuelo desde S3 no permite decir cuál era el día que se
# calculó, y «lo recalculamos y ahora da otra cosa» es exactamente lo que no puede pasar
# con evidencia. El coste es una imagen más gorda y tener que redesplegar para cambiar de
# modelo — que es justo lo que queremos que sea un acto deliberado.
#
# La contrapartida honesta: el arranque en frío carga ~3.5 MB de ONNX más el runtime.
# Se mide en la primera invocación real; no se estima aquí.
#
# LICENCIAS (D-24), y esta imagen es donde más se juega:
#   · ffmpeg      — build LGPL de BtbN, invocado SIEMPRE por subproceso, JAMÁS enlazado.
#   · YOLOX       — Apache-2.0 (Megvii). `ultralytics` está PROHIBIDO y no entra por aquí.
#   · onnxruntime — MIT.
# `ci/licencias.py` vigila el árbol; esta imagen no puede introducir por la puerta de atrás
# lo que aquél impide por la de delante.

FROM public.ecr.aws/lambda/python:3.12 AS ffmpeg
# Etapa aparte SOLO para traer el binario: así el tarball de 100 MB no viaja en la capa
# final y la imagen se queda con los ~80 MB del binario suelto.
ARG FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-lgpl.tar.xz
RUN dnf install -y tar xz && \
    curl -fsSL -o /tmp/ff.tar.xz "${FFMPEG_URL}" && \
    tar xf /tmp/ff.tar.xz -C /tmp && \
    mkdir -p /opt/bin && \
    cp /tmp/ffmpeg-master-latest-*/bin/ffmpeg /tmp/ffmpeg-master-latest-*/bin/ffprobe /opt/bin/ && \
    chmod 0755 /opt/bin/ffmpeg /opt/bin/ffprobe && \
    # La guarda de licencia, EN TIEMPO DE BUILD: si el tarball cambiara de variante, la
    # imagen no se construye. Fail-closed aquí cuesta un build; fail-closed en produccion
    # cuesta un incidente sin video.
    /opt/bin/ffmpeg -version | grep -q -- '--enable-version3' && \
    ! /opt/bin/ffmpeg -version | grep -q -- '--enable-gpl'

FROM public.ecr.aws/lambda/python:3.12

COPY --from=ffmpeg /opt/bin/ffmpeg /opt/bin/ffprobe /opt/bin/

# El modelo se copia del contexto de build: lo pone `make cctv-lambda-image`, que lo
# descarga y COMPRUEBA SU SHA256 antes. Bajarlo aquí dentro dejaría la imagen dependiendo
# de que una release de GitHub no cambie bajo sus pies.
COPY modelos/yolox_nano.onnx /opt/modelos/yolox_nano.onnx

COPY pyproject.toml uv.lock ./
COPY takab_cctv/ ./takab_cctv/

RUN pip install --no-cache-dir . onnxruntime psycopg[binary] boto3

ENV TAKAB_CCTV_MODELO=/opt/modelos/yolox_nano.onnx \
    TAKAB_CCTV_FFMPEG=/opt/bin/ffmpeg

CMD ["takab_cctv.lambda_handler.handler"]
