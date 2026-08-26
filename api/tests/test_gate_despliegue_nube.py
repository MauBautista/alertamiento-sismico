"""[T-2.153] El gate del despliegue de nube, comprobado sin desplegar nada.

`deploy/cloud/deploy.sh` levantaba contenedores y declaraba ✓ **sin preguntarle
nada a la API**. Es la misma familia de defecto que `systemctl is-active`
haciéndose pasar por canary: «arrancó» no es «sirve», y «migró» no es «la API ve
el esquema que su imagen espera».

Aquí se aísla el veredicto —el bloque de Python que el script embebe— y se le dan
las tres respuestas que puede recibir de `/api/health`. No se despliega nada: lo
que se mide es **qué decide**, que es lo único que este gate aporta.

El extractor imita la expansión del heredoc (`\\$` → `$`, `\\\\` → `\\`,
`\\<salto>` → continuación) porque el bloque vive dentro de un `cat <<EOF` sin
comillas. Sin eso se estaría probando un texto que el EC2 nunca ve — y esa
diferencia ya costó un despliegue: el `commands=` del CLI no decodificaba los
`\\n` y el script llegaba en una sola línea.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "cloud" / "deploy.sh"


def _bloque_remoto_crudo() -> str:
    """El texto TAL COMO ESTÁ ESCRITO, antes de que el shell local toque nada."""
    lineas = _DEPLOY.read_text().splitlines()
    ini = next(i for i, linea in enumerate(lineas) if linea.startswith("REMOTE_SCRIPT="))
    ini = next(i for i in range(ini, len(lineas)) if "<<" in lineas[i]) + 1
    fin = next(i for i in range(ini, len(lineas)) if lineas[i] == "EOF")
    return "\n".join(lineas[ini:fin])


def _bloque_remoto() -> str:
    """El script que de verdad corre en el EC2, tras expandir el heredoc."""
    crudo = _bloque_remoto_crudo()
    out: list[str] = []
    i = 0
    while i < len(crudo):
        c = crudo[i]
        if c == "\\" and i + 1 < len(crudo):
            sig = crudo[i + 1]
            if sig in "$`\\":
                out.append(sig)
                i += 2
                continue
            if sig == "\n":
                i += 2
                continue
        out.append(c)
        i += 1
    return "".join(out)


#: El bloque remoto tiene MÁS de un `python3 -c` desde que existe el publicador
#: de la métrica de deriva (T-2.153). Anclar al primero cogía el equivocado y
#: ponía en rojo tests que no tenían nada que ver — así que el veredicto se busca
#: DESPUÉS de su propio rótulo, que es lo único que lo identifica sin ambigüedad.
_MARCA_DEL_GATE = "verificando la API recién desplegada"


def _veredicto() -> str:
    remoto = _bloque_remoto()
    i = remoto.find(_MARCA_DEL_GATE)
    assert i != -1, "el gate del despliegue desapareció de deploy/cloud/deploy.sh"
    m = re.search(r"python3 -c '(.*?)' \"", remoto[i:], re.S)
    assert m is not None, "el gate ya no lleva su veredicto en Python"
    return m.group(1)


def _juzgar(salud: dict, *, desplegado: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _veredicto(), desplegado],
        input=json.dumps(salud),
        capture_output=True,
        text=True,
    )


def _salud(*, build: str, estado: str, aplicada: str = "0051", pendientes: int = 0) -> dict:
    return {
        "status": "ok",
        "build": build,
        "esquema": {
            "estado": estado,
            "aplicada": aplicada,
            "esperada": "0051",
            "pendientes": pendientes,
        },
    }


def test_el_despliegue_bueno_se_declara_bueno() -> None:
    r = _juzgar(_salud(build="abc1234", estado="al_dia"), desplegado="abc1234")
    assert r.returncode == 0, r.stderr
    assert "al día" in r.stdout


def test_un_esquema_ATRASADO_tumba_el_despliegue() -> None:
    """EL CASO DEL 2026-08-21, que nadie detectó.

    La nube corría `0038` con el repo en `0046` —OCHO migraciones— y no lo dijo
    ni una alarma, ni un health-check ni un test: se descubrió por un síntoma
    lateral (una alarma de retención atascada) tras media hora persiguiendo el
    script equivocado.
    """
    r = _juzgar(
        _salud(build="abc1234", estado="atrasada", aplicada="0038", pendientes=8),
        desplegado="abc1234",
    )
    assert r.returncode == 1
    assert "esquema NO está al día" in r.stderr
    assert "'0038'" in r.stderr and "8" in r.stderr, "no dice cuánto va por detrás"


def test_los_contenedores_con_la_imagen_ANTERIOR_tumban_el_despliegue() -> None:
    """`docker compose ps` en verde con la imagen de ayer tiene EXACTAMENTE el
    mismo aspecto que un despliegue bueno. Lo único que los separa es preguntarle
    a la API qué commit corre."""
    r = _juzgar(_salud(build="viejo99", estado="al_dia"), desplegado="abc1234")
    assert r.returncode == 1
    assert "imagen ANTERIOR" in r.stderr
    assert "'viejo99'" in r.stderr and "'abc1234'" in r.stderr


def test_no_poder_saber_la_revision_NO_es_estar_al_dia() -> None:
    """`desconocida` es «no se pudo preguntar», y eso no autoriza a declarar ✓.
    Es la misma doctrina que el canary del gabinete: lo que no se midió no se
    aprueba — aunque tampoco se castigue inventando una avería."""
    r = _juzgar(
        _salud(build="abc1234", estado="desconocida", aplicada="", pendientes=0),
        desplegado="abc1234",
    )
    assert r.returncode == 1
    assert "esquema NO está al día" in r.stderr


def test_los_DOS_fallos_a_la_vez_se_dicen_LOS_DOS() -> None:
    """Un gate que se para en el primer problema manda al operador a arreglar
    una cosa, desplegar otra vez y descubrir la segunda. Se dicen juntos."""
    r = _juzgar(
        _salud(build="viejo99", estado="atrasada", aplicada="0038", pendientes=8),
        desplegado="abc1234",
    )
    assert r.returncode == 1
    assert "imagen ANTERIOR" in r.stderr
    assert "esquema NO está al día" in r.stderr


@pytest.mark.parametrize("clave", ["build", "esquema"])
def test_una_salud_MUTILADA_no_pasa_por_buena(clave: str) -> None:
    """Si `/api/health` deja de declarar una de las dos mitades, el gate no puede
    seguir diciendo ✓: sería aprobar por ausencia de dato."""
    salud = _salud(build="abc1234", estado="al_dia")
    del salud[clave]
    r = _juzgar(salud, desplegado="abc1234")
    assert r.returncode == 1


def test_el_gate_ESPERA_a_que_la_api_conteste_antes_de_rendirse() -> None:
    """No es un `curl` suelto: la API tarda en levantar tras el `restart`, y un
    gate que preguntara una sola vez sería un falso rojo en cada despliegue —
    entrenando al operador a ignorar el único aviso que dice si sirve."""
    remoto = _bloque_remoto()
    assert "for _ in $(seq 1 30)" in remoto, "el gate no reintenta: sería un falso rojo"
    assert "/api/health" in remoto
    assert "logs --tail" in remoto, "si no contesta, hay que dejar el journal a mano"


def test_el_gate_pregunta_por_una_ruta_que_la_app_SIRVE_de_verdad() -> None:
    """[T-2.153] La ruta del gate, atada a la app en vez de escrita de memoria.

    **Medido contra la nube el 2026-08-25: `/api/health` en el puerto 8000
    devuelve 404.** El prefijo `/api` lo monta **Caddy** con `handle_path`, que lo
    QUITA antes de reenviar; FastAPI sirve sus rutas tal cual. El gate consulta la
    API DIRECTA en el 8000 —sin pasar por Caddy—, así que tiene que pedir
    `/health`.

    Con la ruta equivocada este gate no habría fallado a veces: habría esperado
    sus 60 s y puesto en rojo **todos** los despliegues, que es la peor forma de
    romperlo — un gate que siempre grita se acaba ignorando, y entonces ya no
    protege de nada.

    Se deriva de las rutas de la app y no de una constante: el día que alguien
    mueva `/health`, esto cae aquí y no en un despliegue a las tres de la mañana.
    """
    from takab_api.main import create_app

    remoto = _bloque_remoto()
    remoto = remoto[remoto.find(_MARCA_DEL_GATE) :]
    m = re.search(r"curl -fsS[^\n]*http://127\.0\.0\.1:8000(/\S*?)\s", remoto)
    assert m is not None, "el gate ya no consulta la API por HTTP"
    ruta = m.group(1)

    # Del OpenAPI y no de `app.routes`: este `create_app()` monta los routers de
    # forma que `routes` sólo enseña los cuatro de la propia FastAPI (`/docs`,
    # `/openapi.json`…). El esquema sí lista lo que la app SIRVE.
    servidas = set(create_app().openapi()["paths"])
    assert ruta in servidas, (
        f"el gate pide {ruta!r} y la app no la sirve. Rutas de salud disponibles: "
        f"{sorted(p for p in servidas if 'health' in p)}. "
        "Ojo: el prefijo `/api` lo pone Caddy y el gate NO pasa por Caddy."
    )


# --- El namespace del publicador, que es una frontera de DOS lados ------------
#
# `cloudwatch:PutMetricData` no admite ARN de recurso: la única llave de
# condición que ofrece AWS es `cloudwatch:namespace`. O sea que el permiso del
# rol de instancia es, literalmente, una cadena que tiene que coincidir con la
# que el script pasa en `--namespace`. Si divergen, la métrica se rechaza con
# `AccessDenied`, el cron se lo traga (`>/dev/null 2>&1`) y la alarma se queda
# ciega **sin que nada parezca roto** — el modo de fallo exacto que T-2.153
# existe para cerrar, reaparecido un nivel más abajo.
#
# Los otros cuatro publicadores (PITR, backup base, retención de PII) no
# necesitan esta prueba: viven en ficheros `.tpl` y es **Terraform** quien les
# interpola `${metric_namespace}` desde el mismo `local`, así que no pueden
# divergir. El de T-2.153 vive en `deploy/cloud/deploy.sh` —fuera de la
# plantilla, porque la ruta y el puerto de la API los sabe el despliegue— y lo
# lleva escrito a mano. Es el único expuesto, y por eso el único atado aquí.

_TERRAFORM_DB = (
    Path(__file__).resolve().parents[2] / "infra" / "terraform" / "modules" / "database" / "main.tf"
)


def _namespace_del_terraform() -> str:
    texto = _TERRAFORM_DB.read_text(encoding="utf-8")
    m = re.search(r'ops_metrics_namespace\s*=\s*"([^"]+)"', texto)
    assert m is not None, (
        "desapareció el local `ops_metrics_namespace` de infra/terraform/modules/database: "
        "es de donde sale la condición IAM que autoriza a publicar la métrica"
    )
    return m.group(1)


def test_el_publicador_usa_EL_MISMO_namespace_que_le_autoriza_el_rol() -> None:
    esperado = _namespace_del_terraform()
    hallados = set(re.findall(r"--namespace\s+(\S+)", _bloque_remoto()))
    assert hallados, "el despliegue ya no publica ninguna métrica: ¿se cayó el publicador?"
    assert hallados == {esperado}, (
        f"el script publica en {sorted(hallados)} y el rol de instancia solo autoriza "
        f"{esperado!r}. AWS rechazaría con AccessDenied, el cron se lo tragaría y la alarma "
        "takab-dev-esquema-atrasado se quedaría muda en ALARM para siempre."
    )


def test_la_condicion_IAM_sale_del_local_y_no_de_una_cadena_repetida() -> None:
    """El otro lado de la misma frontera. Atar el script al `local` no sirve de
    nada si el `Condition` del permiso lleva su propia copia literal: entonces
    habría dos cadenas que mantener y la prueba de arriba vigilaría la mitad."""
    texto = _TERRAFORM_DB.read_text(encoding="utf-8")
    m = re.search(r'"cloudwatch:namespace"\s*=\s*([^\n]+)', texto)
    assert m is not None, "el permiso PutMetricData perdió su condición de namespace"
    valor = m.group(1).strip()
    assert valor == "local.ops_metrics_namespace", (
        f"la condición IAM usa {valor!r} en vez del local. Con una cadena literal ahí, "
        "el permiso y el publicador pueden divergir sin que nadie lo note."
    )


# --- Quién expande qué, y dónde ------------------------------------------------
#
# El bloque remoto vive dentro de un `cat <<EOF` **sin comillas**, así que el
# shell LOCAL expande todo `$` que no lleve barra delante — y lo hace aunque ese
# `$` esté dentro de un heredoc anidado con comillas (`<<'EOS'`), porque el de
# fuera se procesa primero. Es contraintuitivo justo en el sitio donde más caro
# sale.
#
# Ya mordió DOS veces por la puerta de las comillas invertidas, y a la tercera
# entró por la del dólar: el publicador de T-2.153 se escribió con `$SALUD` y
# `$(curl ...)` a pelo. `set -u` lo cazó —«SALUD: variable sin asignar»— y ese
# fue el desenlace AFORTUNADO. Sin `set -u` no habría fallado nada: `$(curl ...)`
# se habría ejecutado **en el portátil**, contra un `127.0.0.1` que no es el EC2,
# y su salida habría quedado horneada como una constante en el script del
# servidor. Un publicador que siempre informa de lo mismo, y ninguna señal.
#
# De ahí que la lista se DECLARE. Que expandir en local sea a veces lo correcto
# —el `b64` que empaqueta ficheros, los valores que solo el despliegue conoce— es
# justo lo que impide prohibirlo a secas; lo que se puede exigir es que cada caso
# esté aquí escrito con su razón, y que uno nuevo tenga que pasar por este test.

_EXPANSIONES_LOCALES_DECLARADAS = {
    "$(": (
        "El helper `b64`, que codifica ficheros del repo para que VIAJEN dentro del script. "
        "Tiene que correr en local por definición: en el EC2 esos ficheros todavía no existen."
    ),
    "${REGISTRY}": "El registro ECR: lo resuelve el Makefile, el EC2 no lo sabe.",
    "${CLOUD_TAG}": "El commit que se está desplegando. Sale de HEAD, o sea de aquí.",
    "${CLOUD_ENV}": "El entorno destino (dev/prod), decidido por quien lanza el despliegue.",
    "${DEPLOY_ENV}": "La ruta del fichero de entorno remoto, parametrizada desde el Makefile.",
    "${COMPOSE_VERSION}": "La versión de docker compose que se instala, fijada en el repo.",
    "${AWS_REGION}": (
        "La región. Va horneada A PROPÓSITO y no leída del entorno remoto: el publicador de la "
        "métrica corre desde cron, con un entorno pelado donde `AWS_REGION` no existe."
    ),
}


def _expansiones_locales() -> set[str]:
    """Lo que el shell local expandirá: todo `$` con un número PAR de barras
    delante (cero incluido). Con impar, la última escapa al dólar."""
    hallados = set()
    patron = r"(\\*)\$(\{[A-Za-z_][A-Za-z0-9_]*\}|\(|[A-Za-z_][A-Za-z0-9_]*)"
    for m in re.finditer(patron, _bloque_remoto_crudo()):
        if len(m.group(1)) % 2 == 0:
            hallados.add("$(" if m.group(2) == "(" else f"${m.group(2)}")
    return hallados


def test_el_heredoc_no_expande_en_local_nada_que_no_este_declarado() -> None:
    sin_declarar = _expansiones_locales() - set(_EXPANSIONES_LOCALES_DECLARADAS)
    assert not sin_declarar, (
        f"el heredoc de deploy/cloud/deploy.sh expande {sorted(sin_declarar)} EN LA MÁQUINA QUE "
        "DESPLIEGA, no en el EC2. Si eso no es deliberado, escápalo con `\\$` — y si lo es, "
        "decláralo en _EXPANSIONES_LOCALES_DECLARADAS con su razón. Recuerda que un `<<'EOS'` "
        "anidado NO protege: el heredoc de fuera se expande primero."
    )


def test_ninguna_expansion_declarada_se_quedo_sin_uso() -> None:
    """La otra dirección, que es la que pudre las listas escritas a mano: una
    entrada que ya no corresponde a nada sigue autorizando en silencio el día que
    alguien reintroduce ese nombre por accidente."""
    huerfanas = set(_EXPANSIONES_LOCALES_DECLARADAS) - _expansiones_locales()
    assert not huerfanas, (
        f"_EXPANSIONES_LOCALES_DECLARADAS declara {sorted(huerfanas)} y el script ya no las usa: "
        "retíralas para que la lista siga siendo la decisión y no un residuo."
    )


def test_el_publicador_llega_al_EC2_con_sus_variables_INTACTAS() -> None:
    """El caso concreto que se rompió, atado por su nombre.

    Se mira sobre el texto CRUDO y no sobre el expandido, y la diferencia no es
    un detalle: el emulador de `_bloque_remoto()` quita barras, no sustituye
    variables, así que sobre él `$SALUD` sobrevive escapado o no. Un test escrito
    contra esa versión pasaría con el defecto puesto — que es exactamente lo que
    me pasó al escribirlo, y por eso se dice aquí.
    """
    crudo = _bloque_remoto_crudo()
    i = crudo.find("takab-schema-drift.sh <<")
    assert i != -1, "el publicador de la métrica de deriva desapareció del despliegue"
    publicador = crudo[i : crudo.find("\nEOS", i)]

    for var in ("SALUD", "PEND"):
        assert f"\\${var}" in publicador, (
            f"`${var}` del publicador no está escapado como `\\${var}`: el shell local se lo "
            "come y el EC2 recibe una constante en su lugar. El publicador informaría siempre "
            "de lo mismo, y ninguna señal."
        )
    assert "\\$(curl" in publicador, (
        "el `curl` del publicador no está escapado: se ejecutaría EN LA MÁQUINA QUE DESPLIEGA, "
        "contra un 127.0.0.1 que no es el EC2, y su respuesta quedaría horneada en el script."
    )
