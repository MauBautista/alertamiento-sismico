"""El inventario de encargados, DERIVADO (T-5.19).

Un inventario de terceros escrito a mano dura hasta el primer proveedor nuevo, y
el día que se queda corto **nadie se entera**: no hay pantalla que falle. Aquí
las dos poblaciones se derivan y se comparan **por igualdad**:

1. las clases proveedoras del paquete `notify` que salen a un tercero;
2. los servicios de AWS que aparecen en `infra/terraform`.

Y el documento `takab-docs/ENCARGADOS-TAKAB.md` **se genera** de esta
declaración: `uv run python tests/test_encargados.py --escribir`. Un documento
tecleado a mano diverge; uno generado se pone rojo.

Ejecutar este archivo como script escribe el documento; como test, exige que lo
escrito coincida con lo que la declaración produce ahora.
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
from pathlib import Path

from takab_api.privacy import encargados as enc

_RAIZ = Path(__file__).resolve().parents[2]
_DOC = _RAIZ / "takab-docs" / "ENCARGADOS-TAKAB.md"
_TERRAFORM = _RAIZ / "infra" / "terraform"
_AVISO = _RAIZ / "api" / "src" / "takab_api" / "privacy" / "texts" / "aviso_es_mx.json"


# ─────────────────────────────────── censo 1: las clases proveedoras


def _clases_proveedoras() -> set[str]:
    """Clases del paquete `notify` que implementan el protocolo de envío.

    Se derivan del ÁRBOL DE SINTAXIS y no importando los módulos: `twilio.py`,
    `whatsapp.py` y `push.py` traen dependencias propias y se importan tarde a
    propósito. Un censo que exigiera importarlos acabaría siendo un censo de lo
    que se pudo importar hoy.
    """
    paquete = Path(inspect.getfile(enc)).resolve().parents[1] / "notify"
    fuera = set()
    for fichero in sorted(paquete.glob("*.py")):
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.ClassDef):
                continue
            metodos = {
                m.name for m in nodo.body if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef)
            }
            # `send` o `deliver` = es un proveedor. El Protocol se excluye por su
            # base, no por su nombre: renombrarlo no lo colaría.
            bases = {b.id for b in nodo.bases if isinstance(b, ast.Name)}
            if ("send" in metodos or "deliver" in metodos) and "Protocol" not in bases:
                fuera.add(nodo.name)
    return fuera


def test_toda_clase_proveedora_esta_DECLARADA_o_exenta_con_razon():
    """Un proveedor nuevo entra solo — o pone el build en rojo con su nombre."""
    encontradas = _clases_proveedoras()
    assert len(encontradas) >= 5, f"el censo se quedó ciego: solo vio {encontradas}"

    declaradas = set(enc.POR_PROVEEDOR) | set(enc.SIN_TERCERO)
    sin_declarar = encontradas - declaradas
    assert not sin_declarar, (
        "CLASES PROVEEDORAS SIN DECLARAR EN EL INVENTARIO DE ENCARGADOS. Cada una "
        "manda datos personales a alguien: decláralas en `POR_PROVEEDOR`, o en "
        f"`SIN_TERCERO` CON SU RAZÓN si no salen a ningún tercero:\n  {sorted(sin_declarar)}"
    )
    fantasmas = declaradas - encontradas
    assert not fantasmas, f"declaradas y ya inexistentes en el código: {sorted(fantasmas)}"


def test_cada_exencion_de_proveedor_lleva_su_razon():
    for clase, razon in enc.SIN_TERCERO.items():
        assert len(razon) > 60, f"{clase}: la exención no explica por qué no hay tercero"


# ─────────────────────────────────── censo 2: los servicios de AWS


def _servicios_de_terraform() -> set[str]:
    """Prefijos `aws_<servicio>` de los `resource` que terraform declara."""
    fuera = set()
    for tf in _TERRAFORM.rglob("*.tf"):
        texto = tf.read_text(encoding="utf-8")
        for m in re.finditer(r'^resource\s+"(aws_[a-z0-9_]+)"', texto, re.M):
            partes = m.group(1).split("_")
            fuera.add("_".join(partes[:2]))
    return fuera


def test_todo_servicio_de_AWS_esta_clasificado():
    """O guarda datos personales, o no — y en los dos casos, con su razón.

    Es lo que sostiene la declaración de transferencia internacional del aviso:
    la lista de servicios que tienen el dato en Ohio no se puede teclear una vez
    y olvidar.
    """
    en_terraform = _servicios_de_terraform()
    assert len(en_terraform) >= 20, f"el censo se quedó ciego: solo vio {len(en_terraform)}"

    clasificados = set(enc.AWS_CON_DATOS) | set(enc.AWS_SIN_DATOS)
    sin_clasificar = en_terraform - clasificados
    assert not sin_clasificar, (
        "SERVICIOS DE AWS SIN CLASIFICAR. Di si guardan o transportan datos "
        "personales (`AWS_CON_DATOS`) o si no (`AWS_SIN_DATOS`), con su razón en "
        f"los dos casos:\n  {sorted(sin_clasificar)}"
    )
    fantasmas = clasificados - en_terraform
    assert not fantasmas, f"clasificados y ya no usados por terraform: {sorted(fantasmas)}"


def test_ningun_servicio_esta_en_las_DOS_listas():
    solapan = set(enc.AWS_CON_DATOS) & set(enc.AWS_SIN_DATOS)
    assert not solapan, f"decide en cuál va: {sorted(solapan)}"


def test_cada_clasificacion_de_AWS_lleva_su_razon():
    for mapa in (enc.AWS_CON_DATOS, enc.AWS_SIN_DATOS):
        for servicio, razon in mapa.items():
            assert len(razon) > 20, f"{servicio}: la razón es demasiado corta para serlo"


def test_ningun_encargado_declara_sus_datos_como_UNA_CADENA():
    """La tupla que no era tupla.

    `datos=("una frase " "partida en dos")` sin coma final es una CADENA, no una
    tupla de un elemento — y el documento salía con la frase partida carácter a
    carácter. Salió al mirar el documento generado, no al leer el código: por eso
    hay test, y por eso el documento se genera en vez de escribirse.
    """
    for e in enc.encargados():
        assert isinstance(e.datos, tuple), f"{e.key}: `datos` no es una tupla"
        assert all(len(d) > 3 for d in e.datos), (
            f"{e.key}: `datos` se partió en caracteres — falta la coma final de la tupla"
        )


def test_el_pais_DESCONOCIDO_no_se_cuenta_como_transferencia_internacional():
    """Afirmar una transferencia que nadie comprobó es afirmar de más.

    El webhook lo configura el cliente y su destino puede estar en México o en
    cualquier sitio. Contarlo como internacional metería en un documento legal un
    hecho que nadie midió; callarlo del todo escondería a un tercero. Se declara
    aparte, que es lo único cierto.
    """
    fuera = {e.key for e in enc.transferencias_internacionales()}
    sin_saber = {e.key for e in enc.pais_sin_determinar()}
    assert fuera & sin_saber == set(), "un encargado cuenta en las dos listas"
    assert "webhook-del-cliente" in sin_saber
    assert "webhook-del-cliente" not in fuera
    # Y la unión de las dos NO puede ser menos que todos los no-mexicanos: si un
    # encargado se cayera de las dos, desaparecería del documento en silencio.
    todos = {e.key for e in enc.encargados() if e.pais != enc.PAIS_PROPIO}
    assert fuera | sin_saber == todos


# ─────────────────────────────────── el aviso declara los dos huecos


def test_el_aviso_nombra_a_los_encargados_y_la_transferencia():
    """Los dos huecos, DENTRO del texto provisional y por tanto dentro de la huella.

    La huella sella lo que la persona lee y el motor re-pide consentimiento al
    cambiar el texto, así que meterlos aquí no es cosmético: es lo que hace que
    quien ya consintió vuelva a ver el aviso con la información nueva.
    """
    import json

    cuerpo = json.loads(_AVISO.read_text(encoding="utf-8"))["notice"]["body"]
    assert "ENCARGADOS" in cuerpo, "el aviso no nombra a los terceros que tratan los datos"
    assert "FUERA DE MÉXICO" in cuerpo, "el aviso no declara la transferencia internacional"
    # Y el marcador de posición se declara COMO TAL: afirmar una lista completa
    # sobre un texto sin revisión jurídica sería peor que el hueco que había.
    assert "MARCADOR DE POSICIÓN" in cuerpo


def test_el_aviso_no_afirma_que_los_datos_NO_salen_de_la_organizacion():
    """El párrafo que había era fácil de leer como una negación de la transferencia.

    «SUS DATOS NO CRUZAN A OTRA ORGANIZACIÓN» hablaba del aislamiento ENTRE
    CLIENTES; junto a un aviso que callaba a siete encargados, se leía como que
    nadie más los toca. El título tiene que decir de qué habla.
    """
    import json

    cuerpo = json.loads(_AVISO.read_text(encoding="utf-8"))["notice"]["body"]
    assert "SUS DATOS NO CRUZAN A OTRA ORGANIZACIÓN." not in cuerpo


# ─────────────────────────────────── el documento se GENERA


def _documento() -> str:
    lineas = [
        "# Encargados — quién más toca los datos personales",
        "",
        "> **GENERADO. No lo edites a mano.**",
        "> `cd api && uv run python tests/test_encargados.py --escribir`",
        ">",
        "> La fuente es `api/src/takab_api/privacy/encargados.py`, y dos censos la",
        "> comparan por igualdad contra el código (`api/tests/test_encargados.py`):",
        "> un proveedor nuevo sin declarar, o un servicio de AWS sin clasificar,",
        "> ponen el build en rojo nombrándolo.",
        "",
        "> ⚠️ **Este inventario NO es el aviso de privacidad revisado.** El aviso sigue",
        "> siendo provisional y lo dice dentro de su propio texto (`D-20`: la consulta",
        "> jurídica espera a que un cliente la pida). Esto es la costura: el día que",
        "> llegue el texto revisado, la lista ya existe y está al día.",
        "",
        "## 1 · Encargados",
        "",
        "| Encargado | Para qué | Qué datos | País | De dónde sale |",
        "|---|---|---|---|---|",
    ]
    for e in enc.encargados():
        lineas.append(
            f"| **{e.nombre}** | {e.finalidad} | {'; '.join(e.datos)} | {e.pais} | `{e.via}` |"
        )
    fuera = enc.transferencias_internacionales()
    sin_saber = enc.pais_sin_determinar()
    lineas += [
        "",
        "## 2 · Transferencia internacional",
        "",
        f"**{len(fuera)} de {len(enc.encargados())}** encargados tratan los datos fuera de "
        f"México. La región de despliegue es `us-east-2` (Ohio).",
        "",
    ]
    if sin_saber:
        lineas += [
            f"Y **{len(sin_saber)}** cuyo país **no se sabe porque lo elige el cliente** al "
            "configurarlos. No se cuentan arriba: contarlos afirmaría una transferencia que nadie "
            "ha comprobado, y callarlos escondería a un tercero.",
            "",
        ]
        for e in sin_saber:
            lineas.append(f"- **{e.nombre}** — {e.pais}")
        lineas.append("")
    lineas += [
        "Los servicios de AWS que **guardan o transportan** datos personales, derivados de",
        "`infra/terraform`:",
        "",
    ]
    for servicio, razon in sorted(enc.AWS_CON_DATOS.items()):
        lineas.append(f"- `{servicio}` — {razon}")
    lineas += [
        "",
        "Y los que **no**, con su razón — están aquí porque un censo que solo enumera lo que",
        "sí es un censo que no se puede comprobar:",
        "",
    ]
    for servicio, razon in sorted(enc.AWS_SIN_DATOS.items()):
        lineas.append(f"- `{servicio}` — {razon}")
    lineas += [
        "",
        "## 3 · Lo que ningún censo alcanza",
        "",
        "Terceros que no corren en producción y que por tanto ningún análisis del código",
        "puede encontrar. Se declaran a mano y llevan su razón:",
        "",
    ]
    for e in enc.FUERA_DEL_CENSO:
        lineas.append(f"- **{e.nombre}** — {e.finalidad} · `{e.via}`")
    lineas += [
        "",
        "## 4 · Lo que esto le deja pendiente a la consulta jurídica",
        "",
        "`D-23` y `D-07` descansan **las dos** sobre la calificación de que TAKAB es",
        "**encargado** y no **responsable**, y esa calificación solo está afirmada en un",
        "texto que se declara sin revisar. Es un hecho nuevo para la lista de la consulta,",
        "no una decisión que este documento tome. Ver `PENDIENTES-MAURICIO.md §4.1`.",
        "",
    ]
    return "\n".join(lineas)


def test_el_documento_committeado_ES_el_que_genera_la_declaracion():
    escrito = _DOC.read_text(encoding="utf-8") if _DOC.exists() else ""
    assert escrito == _documento(), (
        "`ENCARGADOS-TAKAB.md` se separó de la declaración. Regenéralo:\n"
        "  cd api && uv run python tests/test_encargados.py --escribir"
    )


if __name__ == "__main__":
    if "--escribir" in sys.argv:
        _DOC.write_text(_documento(), encoding="utf-8")
        print(f"escrito {_DOC}")
