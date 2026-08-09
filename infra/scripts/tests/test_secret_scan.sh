#!/usr/bin/env bash
# Gate de la regla de oro 6 (T-2.86.c · hueco RO-6.a): NO hay secretos en el árbol.
#
# Corre en el job `secretos` de ci.yml (bloquea el PR) y en `make test`. El
# barrido en sí, con su alcance y sus tablas razonadas, vive en `secret_scan.py`
# — leer su cabecera antes de tocar nada de aquí.
#
# QUÉ COMPRUEBA, en este orden:
#   1. EL ÁRBOL ESTÁ LIMPIO. Es el gate propiamente dicho.
#   2. LA BATERÍA DE MUTACIONES. Cada regla tiene que CAZAR un secreto sintético
#      con la forma del real. Sin esto, un barrido que no encuentra nada es
#      indistinguible de un barrido roto: una regex mal escrita da verde para
#      siempre y nadie se entera. Y va más allá de probar las que hay: si
#      `secret_scan.py` gana una regla y nadie le escribe su mutación, este
#      fichero sale en ROJO con el id de la regla huérfana.
#   3. LOS CONTROLES NEGATIVOS. Las contraseñas de desarrollo LEGÍTIMAS de este
#      repo (`takab_dev` del docker-compose y de los DSN de test, el SID de
#      relleno `ACffff…`, `${VAR}` sin expandir, `token = au.make_token(...)`)
#      NO se marcan. Es la mitad que decide si el gate se sigue mirando: un
#      barrido que grita por el DSN de los tests se desactiva en dos semanas y
#      entonces tampoco ve el secreto de verdad.
#   4. QUE LAS EXCLUSIONES NO SEAN VACUAS. Toda entrada de `PERMITIDOS` tiene
#      que estar siendo USADA por el árbol de hoy. Una exclusión que ya no
#      perdona nada es una puerta abierta sin motivo, y este test la delata en
#      vez de dejarla envejecer.
#   5. QUE UN FICHERO NUEVO SIN `git add` SE VEA. `git ls-files` a secas no lo
#      ve: en local daba VERDE y en CI (donde todo está rastreado) ROJO. Es la
#      familia de fallo que `test_ci_parity.sh` persigue, un piso más arriba.
#
# Sin dependencias: `git` + el `python3` del sistema, igual que sus dos hermanos
# de este directorio. Nada que descargar en el runner.
#
# Corre con: bash infra/scripts/tests/test_secret_scan.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
SCAN="$HERE/secret_scan.py"

fallos=0
ok() { printf '  ok   %s\n' "$1"; }
fallo() { printf '  FALLO %s\n' "$1" >&2; fallos=$((fallos + 1)); }
nota() { printf '  --   %s\n' "$1"; }

[ -f "$SCAN" ] || {
  printf 'no existe %s\n' "$SCAN" >&2
  exit 1
}

cd "$ROOT"

# ---------------------------------------------------------------------------
# 1. El árbol está limpio (EL gate)
# ---------------------------------------------------------------------------
#
# Va en una FUNCIÓN CON NOMBRE, y no suelto, por una razón que no es de estilo:
# la matriz de trazabilidad (T-2.84) ancla sus citas de bash a
# `^\s*(?:function\s+)?<nombre>\s*\(\)\s*\{`, así que un script lineal **no se
# puede citar**. Sin nombre, `RO-6.a` seguiría figurando como hueco aunque el
# control exista y corra en cada PR — y citar `ok`/`fallo` (los únicos nombres
# que había) sería exactamente la mentira que la matriz existe para impedir.
#
# Los tres scripts de `infra/scripts/tests/` eran lineales, así que la rama bash
# del resolutor nunca se había ejercitado contra el árbol real. Ésta es la
# primera. Los otros dos siguen sin poder citarse; está fichado.
test_el_arbol_de_trabajo_no_tiene_secretos() {
  echo "== no hay secretos en el árbol de trabajo =="
  if salida="$(python3 "$SCAN" 2>&1)"; then
    printf '%s\n' "$salida" | while IFS= read -r l; do nota "$l"; done
    ok "barrido limpio"
  else
    fallo "el barrido encontró secretos en el árbol"
    printf '%s\n' "$salida" >&2
  fi
}

test_el_arbol_de_trabajo_no_tiene_secretos

# ---------------------------------------------------------------------------
# 2-4. Mutaciones, controles negativos y exclusiones no vacuas
# ---------------------------------------------------------------------------
SALIDA="$(
  python3 - "$HERE" <<'PYFIN'
import sys
import pathlib
import tempfile

HERE = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(HERE))
import secret_scan as ss  # noqa: E402

# --- 2. MUTACIONES: id de regla → línea con un secreto SINTÉTICO de esa forma.
# Ninguno es real: están inventados con la longitud y el alfabeto del emisor,
# que es lo único que la regla mira. Si añades una regla a REGLAS, añade su
# mutación aquí o este fichero te lo dirá por su nombre.
#
# POR QUÉ VAN PARTIDOS EN TROZOS QUE SE UNEN EN RUNTIME, y no escritos enteros:
# este fichero está DENTRO del árbol que el barrido recorre. Con los literales
# completos, el propio gate se marcaba a sí mismo — 11 hallazgos, medido. La
# salida fácil habría sido excluir esta ruta, y es justo la que `secret_scan.py`
# argumenta que se pudre: a partir de ese día, un secreto de verdad metido aquí
# no lo ve nadie. Partiéndolos no hay NINGUNA exclusión por ruta en todo el
# barrido, y las reglas se siguen ejercitando enteras sobre la cadena ya unida.
# Efecto secundario que hay que decir en voz alta: partir un literal en dos
# ESCONDE un secreto de este barrido y de cualquier otro que lea por líneas.
# Es una limitación declarada, no un descuido (ver la cabecera de secret_scan.py).
MUTACIONES = {
    "aws-access-key-id": ('AWS_ACCESS_KEY_ID = "AKIA', 'QYLPMN5HXV3TR2WD"'),
    # Las dos reglas ANCLADAS AL NOMBRE (nombre + hueco corto + valor) necesitan
    # además que los trozos vivan en LÍNEAS distintas: partir el literal no basta
    # cuando el nombre y el valor siguen cabiendo en el mismo renglón, porque el
    # `\W{0,20}` de la regla se traga las comillas y la coma de en medio. Ninguna
    # regla cruza saltos de línea, así que esto sí lo separa.
    "aws-secret-access-key": (
        "aws_secret_access_key = ",
        '"kR7v2QpLm4XzT9wBc1NdYeH6JgAs3FuZoP0iVrEx"',
    ),
    "twilio-account-sid": ("TAKAB_API_NOTIFY_SMS_ACCOUNT_SID: AC", "7d4f19b2a83c05e61f2947db8ac35e10"),
    "twilio-api-key-sid": ("twilio_api_key = SK", "1a2b3c4d5e6f708192a3b4c5d6e7f809"),
    "twilio-auth-token": (
        "TAKAB_API_NOTIFY_SMS_AUTH_TOKEN: ",
        "8f2c41d9b7e0a6534cbd1e97f20a5b3d",
    ),
    "clave-privada": ("-----BEGIN RSA ", "PRIVATE KEY-----"),
    "uri-con-contrasena": ("DSN = postgresql+psycopg://takab_app:", "Xq9vR2mTz7Kd@db.takab.internal:5432/takab"),
    "slack-token": ("SLACK = xoxb-", "2401987654321-2398765432109-8fJk2mNpQr5sTvWx7yZa3Bc4"),
    "github-token": ("GH_TOKEN=ghp_", "9sKd3Lm2Pq7Rt1Vx5Zb8Nc4Hf6Jg0Ay2Wu3B"),
    "google-api-key": ("firebaseApiKey: AIza", "SyD4k1Lm9Pq7Rt2Vx5Zb8Nc4Hf6Jg0Ay2Wu"),
    "openai-openrouter-key": ('openrouter_api_key = "sk-or-', 'v1-a1b2c3d4e5f60718293a4b5c6d7e8f90"'),
    "stripe-key": ("STRIPE=sk_live_", "4eC39HqLyjWDarjtT1zdp7dc"),
    "meta-graph-token": ("WHATSAPP_TOKEN=EAA", "Gk3Zb9Qm2Xv7Rt4Lp1Nc8Hf5Jd0Ay6Wu3Ei9Os2Pa7Tb4Yc1Zd8Xe5Vf2Ug9Rh6"),
    "jwt-firmado": (
        "Authorization: Bearer eyJ",
        "hbGciOiJSUzI1NiIsImtpZCI6ImRldiJ9.",
        "eyJzdWIiOiJvcHMiLCJ0ZW5hbnQiOiJ0ZW5hbnQtZGV2In0.",
        "Qm2Xv7Rt4Lp1Nc8Hf5Jd0Ay6Wu3Ei9Os2Pa7Tb4Yc1Zd8Xe5Vf2Ug9Rh6Kj3",
    ),
}
MUTACIONES = {k: "".join(v) for k, v in MUTACIONES.items()}

# Cobertura: una regla sin mutación es una regla nunca probada.
ids = {r.id for r in ss.REGLAS}
for huerfana in sorted(ids - set(MUTACIONES)):
    print("FALLO\tregla `%s` sin mutación\tañádele una línea a MUTACIONES en "
          "test_secret_scan.sh: una regla que nunca ha cazado nada es una regla "
          "sin probar, y una regex mal escrita daría verde para siempre" % huerfana)
for sobrante in sorted(set(MUTACIONES) - ids):
    print("FALLO\tmutación `%s` sin regla\tla regla desapareció de REGLAS; "
          "quita también su mutación" % sobrante)

for rid in sorted(set(MUTACIONES) & ids):
    hallazgos, _ = ss.escanear_texto("<mutacion>", MUTACIONES[rid])
    cazada = {h.regla.id for h in hallazgos}
    if rid in cazada:
        print("OK\tcaza %s\t" % rid)
    else:
        print("FALLO\tNO caza %s\tla regla no reconoce `%s`; el barrido diría "
              "'sin secretos' con ese secreto delante"
              % (rid, MUTACIONES[rid][:90]))

# --- 3. CONTROLES NEGATIVOS: valores LEGÍTIMOS del repo que NO pueden marcarse.
# Cada uno con la razón por la que está aquí. Si alguno empieza a marcarse, el
# barrido se ha vuelto ruidoso y hay que arreglar la regla — no ampliar la lista.
LEGITIMOS = [
    ('postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_test',
     "DSN de la suite de api; la contraseña es la del contenedor local"),
    ("POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-takab_dev}",
     "docker-compose.yml: contraseña de desarrollo, declarada en PERMITIDOS"),
    ("MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-takab_dev_secret}",
     "raíz del MinIO local (S3 de evidencia en desarrollo)"),
    ('_SID = "ACffffffffffffffffffffffffffffffff"',
     "SID de relleno de api/tests/notify/test_twilio.py: un carácter repetido"),
    ('token = au.make_token("soc_operator", tenant=au.TENANT_A)',
     "el patrón MÁS común de la suite de auth: `token = ...` no es un secreto, "
     "y marcarlo era lo que hacía inservible el enfoque por nombre de variable"),
    ('DSN = "postgresql://usuario:${DB_PASSWORD}@host:5432/db"',
     "interpolación: el fichero tiene el hueco, no el valor"),
    ('f"postgresql+psycopg://u:{contrasena}@h:5432/takab"',
     "f-string de api/tests/test_settings_produccion.py: mismo caso"),
    ("arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/gateway-hmac-AbCdEf",
     "ARN de un secreto: la REFERENCIA a un secreto es justo lo que queremos ver "
     "en el código en vez del secreto"),
    ('"integrity": "sha512-Yd3kIPZ5aE9K2mHTQmDsGxDPCEBcvtQTOgWXFZM8Wq5qGrTVxHqBXCjF+HZOw3xBcE="',
     "hash de integridad de un lockfile: 64+ caracteres base64 que no son un secreto"),
    ("password = random_password.db[each.key].result",
     "terraform: la contraseña se GENERA, no está escrita"),
    ('"postgresql+psycopg://takab_app:REDACTADO@127.0.0.1:5432/takab"',
     "fixture con la contraseña rotulada como tal"),
    ("uses: aws-actions/configure-aws-credentials@v4",
     "acción de CI que resuelve credenciales por OIDC: la forma correcta"),
]
for linea, razon in LEGITIMOS:
    hallazgos, _ = ss.escanear_texto("<legitimo>", linea)
    if hallazgos:
        print("FALLO\tfalso positivo: %s\t`%s` marcó `%s`. Es legítimo (%s): "
              "arregla la REGLA, no amplíes la lista de excepciones"
              % (razon, hallazgos[0].regla.id, linea[:80], razon))
    else:
        print("OK\tno marca: %s\t" % razon)

# --- 4. Las exclusiones declaradas NO son vacuas: el árbol de hoy las usa.
rutas = ss.rutas_rastreadas()
_, perdonados, _ = ss.escanear_arbol(rutas)
usadas = set()
for valor, razon in perdonados:
    for literal in ss.PERMITIDOS:
        if literal == valor or literal in valor:
            usadas.add(literal)
for literal in sorted(ss.PERMITIDOS):
    if literal in usadas:
        print("OK\tla exclusión `%s` sigue haciendo falta\t" % literal)
    else:
        print("FALLO\texclusión muerta: `%s`\tya no la perdona nada en el árbol. "
              "Una excepción que no excluye nada es una puerta abierta sin motivo: "
              "bórrala de PERMITIDOS en secret_scan.py" % literal)

# --- 5. Un fichero NUEVO sin `git add` entra en el barrido.
with tempfile.NamedTemporaryFile(
    "w", suffix=".txt", prefix="takab-mutacion-", dir=".", delete=False
) as fh:
    fh.write("DSN = postgresql://svc:" + "Zk8mQr3TvXd1@db.interno:5432/takab\n")
    temporal = pathlib.Path(fh.name)
try:
    nombre = temporal.name
    if nombre not in ss.rutas_rastreadas():
        print("FALLO\tel barrido no ve los ficheros nuevos\t`%s` no aparece en la "
              "lista de rutas: `git ls-files` a secas ignora lo que no se ha hecho "
              "`git add`, y entonces el gate dice cosas distintas en local y en CI"
              % nombre)
    else:
        hallazgos, _, _ = ss.escanear_arbol([nombre])
        if hallazgos:
            print("OK\tun fichero nuevo sin `git add` entra en el barrido\t")
        else:
            print("FALLO\tel barrido no marcó el secreto del fichero nuevo\t")
finally:
    temporal.unlink(missing_ok=True)
PYFIN
)"

echo "== la batería de mutaciones: cada regla caza su secreto sintético =="
while IFS=$'\t' read -r estado desc detalle; do
  case "$estado" in
  OK) ok "$desc" ;;
  FALLO)
    fallo "$desc"
    if [ -n "$detalle" ]; then printf '        %s\n' "$detalle" >&2; fi
    ;;
  NOTA) nota "$desc" ;;
  esac
done <<<"$SALIDA"

if [ "$fallos" -ne 0 ]; then
  printf '\n%d prueba(s) FALLARON\n' "$fallos" >&2
  exit 1
fi
printf '\ntodo en verde\n'
