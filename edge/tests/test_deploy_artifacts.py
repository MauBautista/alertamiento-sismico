"""Los artefactos que DESPLIEGAN el gabinete, bajo test — hasta hoy no lo estaban.

CERO tests leían `deploy/edge/deploy.sh` y CERO leían `edge/systemd/*.service`.
Son los dos archivos que deciden si el gabinete arranca, y sus fallos no se ven
en ninguna suite: se ven en el edificio.

Lo que estos tests cierran (todos son fallos ya OCURRIDOS o medidos, no hipótesis):

1. **La lista literal de extras de `uv sync`.** El primer deploy real sincronizó
   con un solo extra, `uv` PODÓ `awsiotsdk` —desinstala lo que no está en el set
   resuelto— y el gabinete se quedó offline spooleando. Hoy la línea dice
   `--extra hardware --extra aws`, correcta, pero es una lista LITERAL: ya hay
   dos extras más declarados (`bacnet`, `lora`) que al activarse repetirían el
   fallo, y nada obliga a decidir sobre el siguiente que alguien declare. El test
   DERIVA los extras de `pyproject.toml` en vez de enumerarlos (si enumerara, se
   quedaría ciego ante el próximo, que es justo el defecto que persigue).

2. **El orden rsync → FW_VERSION → restart.** `rsync --delete` borra
   `FW_VERSION` porque no está en el fuente; por eso se escribe DESPUÉS. Es un
   invariante frágil que solo vivía en un comentario.

3. **Una unidad que se rinde para siempre — y su precio al no rendirse.** Con el
   default de systemd (5 arranques en 10 s) y `RestartSec=2`/`1`, un crash al
   arrancar agota el burst en ~10 s y la unidad queda en `failed` PARA SIEMPRE:
   un edificio sin alertamiento hasta que alguien conduzca hasta el sitio. Por
   eso ambas unidades llevan `StartLimitIntervalSec=0`.

   Lo que ESO cuesta se pasó por alto al escribirlo, y aquí queda MEDIDO: el
   ciclo de vida del proceso **mueve físicamente el gas y los retenedores de
   puerta**. `GAS_VALVE` es `FAIL_CLOSE` y `DOOR_RETAINER` es `NORMALLY_CLOSED`,
   y ambos reposan ENERGIZADOS (`normal_energized`), así que `_on_start` los
   energiza y la muerte del proceso los suelta. Sin límite de arranques Y sin
   backoff, `RestartSec=1` convierte un ciclo ACOTADO de actuación física sobre
   el edificio en uno INFINITO a 3600 ciclos/hora. El argumento original —«lo
   peor que hace un bucle de reintentos es gastar CPU»— es falso en su premisa:
   no es CPU, es una válvula de gas. La salida no es rendirse: es ESPACIAR
   (`RestartSteps=` + `RestartMaxDelaySec=`, systemd ≥ 254).

4. **La ventana de desprotección no declarada.** Ninguna unidad fija
   `TimeoutStopSec`, así que la cota superior de "cuánto tiempo el gabinete no
   protege durante un despliegue" es el default de systemd (90 s) — un número que
   nadie eligió y que no aparece escrito en ninguna parte.

5. **La guarda que vigilaba UNA de cuatro directivas** (A1/A2, la ronda de
   cierre). Los puntos 3 y 4 descubrieron, documentaron y midieron que systemd
   IGNORA EN SILENCIO una directiva puesta en la sección equivocada… y el
   `_seccion_de()` que se escribió para vigilarlo se aplicó a UNA sola
   directiva. Medido: mover `RestartSteps=`, `RestartMaxDelaySec=` y
   `TimeoutStopSec=` de `[Service]` a `[Unit]` —un reordenamiento cosmético que
   el comentario de la propia unidad invita a hacer— dejaba la suite en verde
   mientras `systemd-analyze verify` decía «Unknown key … in section [Unit],
   ignoring.» ×3 y salía 0 igual: sin backoff, `Restart=always` +
   `StartLimitIntervalSec=0` + `RestartSec=1` devolvían el crash-loop a 3600
   ciclos/hora sobre la válvula de gas.

   Y el mismo lector ingenuo cometía el otro defecto de la casa: `_directiva()`
   leía la PRIMERA asignación donde systemd aplica la ÚLTIMA — el gemelo exacto
   de `declValue` en la hoja de estilos (T-2.64), que leía la primera
   declaración donde el navegador aplica la última. Añadir un segundo
   `RestartSteps=0` al final de `[Service]` no ponía nada en rojo.

   Los dos se cierran ABAJO DEL PARSER (`_asignaciones_de()`), no test a test,
   y la sección se le pregunta a SYSTEMD (no a una lista escrita a mano) para
   que la guarda cubra también las directivas que nadie enumeró.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import tomllib

import pytest
from takab_edge.contracts import ActuatorChannel
from takab_edge.gpio import GpioController

_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_DEPLOY = _RAIZ / "deploy" / "edge" / "deploy.sh"
#: El script que INSTALA `/etc/takab/edge.env` (y que lo FUSIONA en vez de
#: pisarlo — lección del PR #13). `deploy.sh` sólo LEE ese archivo.
_PROVISION = _RAIZ / "infra" / "scripts" / "provision_gateway.sh"
_PYPROJECT = _RAIZ / "edge" / "pyproject.toml"
_UNIDADES = {
    "takab-edge": _RAIZ / "edge" / "systemd" / "takab-edge.service",
    "takab-gpio": _RAIZ / "edge" / "systemd" / "takab-gpio.service",
}


def _deploy() -> str:
    return _DEPLOY.read_text()


def _pos_comando(patron: str) -> int:
    """Posición de un COMANDO real, ignorando comentarios.

    `str.index` sobre el archivo entero encuentra la primera MENCIÓN, y el
    encabezado del script nombra varios de estos comandos al explicarlos. Un test
    anclado a esa mención mide el orden del texto, no el del despliegue — y eso
    ya dio un rojo engañoso al añadir un párrafo de documentación.
    """
    m = re.search(rf"^\s*(sudo )?{patron}", _deploy(), re.MULTILINE)
    assert m is not None, f"no hay ningún comando `{patron}` en {_DEPLOY}"
    return m.start()


def _array_bash(nombre: str) -> list[str]:
    """Lee un array bash `NOMBRE=(a b c)` del script de despliegue.

    Se leen del SCRIPT y no de un comentario a propósito: un comentario puede
    divergir del comando que se ejecuta, y esa divergencia es exactamente el
    fallo que este archivo persigue.

    Y se exige que la asignación sea ÚNICA, porque bash tiene la misma semántica
    que systemd y que CSS: **gana la última**. Un `EDGE_EXTRAS=(...)` repetido
    más abajo sería invisible para este `re.search` —que lee la primera— y
    decisivo para el `uv sync` que PODA el venv del Pi; o sea, un gabinete
    offline spooleando con la suite en verde. Es el mismo defecto que
    `_directiva()` tenía con las unidades systemd y `declValue` con la hoja de
    estilos (T-2.64), aquí anclado en el único array que este archivo lee.
    """
    asignaciones = re.findall(rf"^{nombre}=\(([^)]*)\)", _deploy(), re.MULTILINE)
    assert asignaciones, f"`{nombre}=(...)` no está en {_DEPLOY}"
    assert len(asignaciones) == 1, (
        f"`{nombre}=(...)` se asigna {len(asignaciones)} veces en {_DEPLOY}: bash aplica la "
        "ÚLTIMA y este test leería la primera. Deja una sola asignación."
    )
    return asignaciones[0].split()


def _extras_declarados() -> set[str]:
    datos = tomllib.loads(_PYPROJECT.read_text())
    return set(datos["project"]["optional-dependencies"])


# ---------------------------------------------------------------- extras


def test_todo_extra_declarado_esta_decidido_en_el_despliegue() -> None:
    """DERIVADO de `pyproject.toml`, no enumerado: declarar un extra nuevo obliga
    a decidir si va al Pi o no, y el olvido sale en rojo aquí en vez de salir en
    un gabinete mudo.

    `uv sync` DESINSTALA lo que no está en el set resuelto, así que "no decidir"
    no es neutro: es podar.
    """
    instalados = set(_array_bash("EDGE_EXTRAS"))
    omitidos = set(_array_bash("EDGE_EXTRAS_OMITIDOS"))
    declarados = _extras_declarados()

    sin_decidir = declarados - instalados - omitidos
    assert not sin_decidir, (
        f"extras declarados en pyproject.toml que el deploy no menciona: {sorted(sin_decidir)}. "
        "Añádelos a EDGE_EXTRAS (van al Pi) o a EDGE_EXTRAS_OMITIDOS (con su razón)."
    )
    inventados = (instalados | omitidos) - declarados
    assert not inventados, f"el deploy nombra extras que no existen: {sorted(inventados)}"
    assert not (instalados & omitidos), "un extra no puede estar instalado y omitido a la vez"


def test_los_dos_extras_del_pi_real_siguen_instalandose() -> None:
    """`hardware` (lgpio, backend GPIO nativo) y `aws` (awsiotsdk, transporte
    mTLS). Sin el primero el camino de vida no arranca; sin el segundo el
    gabinete queda offline spooleando — que es lo que pasó de verdad."""
    assert {"hardware", "aws"} <= set(_array_bash("EDGE_EXTRAS"))


def test_el_uv_sync_usa_la_lista_y_no_una_enumeracion_a_mano() -> None:
    """Si el comando volviera a llevar los extras escritos a mano, el test de
    arriba pasaría y el Pi seguiría recibiendo otra cosa."""
    guion = _deploy()
    assert "uv sync" in guion
    assert re.search(r"uv sync[^\n]*\$\{EDGE_EXTRA_FLAGS", guion), (
        "el `uv sync` del Pi debe construir sus flags desde EDGE_EXTRAS, no repetir la lista a mano"
    )


# ---------------------------------------------------------------- orden


def test_la_marca_de_version_se_escribe_dentro_de_la_release_y_tras_el_rsync() -> None:
    """`FW_VERSION` no está en el fuente, así que el `--delete` del rsync la
    BORRA. Escribirla antes la perdería y el gabinete reportaría «no sé» para
    siempre.

    [T-2.70] Y va DENTRO de la release (`${NUEVA}/FW_VERSION`), no en una ruta
    compartida: `version.py` la resuelve como «el directorio que contiene al
    paquete», así que cada release declara SU versión y una vuelta atrás
    devuelve también lo que el gabinete reporta a la nube. Escribirla fuera haría
    que un rollback dejara al gabinete corriendo una versión y anunciando otra.
    """
    guion = _deploy()
    rsync = _pos_comando(r'"\$ROOT/edge/" "\$HOST:\$\{DESTINO_RELEASE\}/edge/"')
    marca = _pos_comando(r"printf '%s\\n' \"\$FW_VERSION\" >")
    assert rsync < marca, "FW_VERSION debe escribirse DESPUÉS del rsync (--delete la borraría)"
    assert '> "${NUEVA}/FW_VERSION"' in guion, (
        "FW_VERSION tiene que vivir DENTRO de la release, o un rollback deja al "
        "gabinete corriendo una versión y anunciando otra"
    )


def test_el_gate_se_ejecuta_antes_de_activar_el_camino_de_vida() -> None:
    """El orden que convierte un despliegue roto en un no-evento.

    `gpio` es `critical=True` y el supervisor hace fail-fast: si el arranque
    truena, el proceso crashea, cicla gas y puertas (ver la sección del backoff)
    y el gabinete queda sin alertamiento. Comprobarlo ANTES de la activación hace
    que ese deploy ABORTE con el gabinete todavía CORRIENDO el código viejo.

    [T-2.70] El reinicio ya no lo hace este script: lo hace `canary.sh` al
    activar. El orden que importa es el mismo, así que el ancla es la llamada.
    """
    gate = _deploy().index("GATE DEL CÓDIGO DESPLEGADO")
    activacion = _pos_comando(r'"\$\{RAIZ\}/bin/canary\.sh"')
    assert gate < activacion, "el gate corre ANTES de activar nada"
    codigo = [linea for linea in _deploy().splitlines() if not linea.lstrip().startswith("#")]
    culpables = [linea for linea in codigo if "systemctl restart takab-edge" in linea]
    assert not culpables, (
        "este script no puede reiniciar al cliente por su cuenta: sin el remojo del "
        f"canary, un proceso que arranca y crashea al segundo 4 sale bueno: {culpables}"
    )


@pytest.mark.parametrize("modulo", ["lgpio", "awsiot"])
def test_el_gate_cubre_las_dependencias_que_matan_el_arranque(modulo: str) -> None:
    """Se busca DENTRO del bloque del gate, no en todo el archivo: ambos nombres
    aparecen también en comentarios, y un test que los encontrara ahí pasaría
    sin que el deploy comprobara nada."""
    guion = _deploy()
    bloque = guion[guion.index("GATE DEL CÓDIGO DESPLEGADO") : _pos_comando("systemctl restart")]
    assert modulo in bloque, f"el deploy debe comprobar que `{modulo}` importa antes de reiniciar"


# ------------------------------- el gate ciego y el gate que corría tarde (B2/B3)


def test_el_gate_ejercita_el_codigo_recien_desplegado() -> None:
    """B2. El gate original era `import lgpio, awsiot` — DOS DEPENDENCIAS DE
    TERCEROS que viven en el `.venv`, y el `.venv` está EXCLUIDO del rsync.

    O sea: el único gate que protegía el despliegue no podía fallar por culpa
    del código que se estaba desplegando. Era estructuralmente ciego justo a la
    causa más probable de que un gabinete no arranque tras un update. El gate
    tiene que importar el ÁRBOL RECIÉN COPIADO, y en concreto los dos entry
    points que ejecutan los `ExecStart=` de las unidades.
    """
    guion = _deploy()
    bloque = guion[guion.index("GATE DEL CÓDIGO DESPLEGADO") : _pos_comando("systemctl restart")]
    for entrada in ("takab_edge.supervisor", "takab_edge.gpio.__main__"):
        assert entrada in bloque, (
            f"el gate debe importar `{entrada}` (entry point de una unidad systemd): "
            "sin eso sólo comprueba paquetes de terceros que el rsync ni siquiera copia"
        )


#: [T-2.70.a·D2/P2] Console scripts que NO son un servicio, con su razón. Es una
#: lista de EXCEPCIONES declaradas: un entry point nuevo se presume unidad de
#: systemd y, si no lo es, hay que escribir aquí por qué — un `takab-*` que
#: arranca solo y que nadie supervisa sería justo el defecto que esto vigila.
_SCRIPTS_SIN_UNIDAD: dict[str, str] = {
    "takab-gpioctl": (
        "es una CLI de shell (interroga al dueño de los pines para `deploy.sh` y "
        "para el traspaso de D3), no un proceso de larga vida: no tiene ni debe "
        "tener unidad. El gate del despliegue sí la importa: si no importa, el "
        "despliegue se queda sin su único instrumento de diagnóstico."
    ),
}


def test_los_entry_points_del_gate_son_los_de_las_unidades_systemd() -> None:
    """DERIVADO de `pyproject.toml`, no enumerado: el gate importa los módulos
    de TODOS los console scripts, y los que son servicio los lanza su unidad.
    Si alguien renombra un entry point, el gate dejaría de probar lo que arranca
    — y este test lo ve.
    """
    scripts = tomllib.loads(_PYPROJECT.read_text())["project"]["scripts"]
    guion = _deploy()
    bloque = guion[guion.index("GATE DEL CÓDIGO DESPLEGADO") : _pos_comando("systemctl restart")]
    for nombre, destino in scripts.items():
        modulo = destino.split(":")[0]
        assert modulo in bloque, (
            f"el console script `{nombre}` apunta a `{modulo}` y el gate no lo importa"
        )
        if nombre in _SCRIPTS_SIN_UNIDAD:
            assert nombre not in _UNIDADES, (
                f"`{nombre}` está declarado como CLI y sin embargo tiene unidad"
            )
            continue
        assert f".venv/bin/{nombre}" in _unidad(nombre), (
            f"{nombre}.service debería ejecutar .venv/bin/{nombre}"
        )
    # …y la inversa: toda unidad que exista tiene que lanzar un script DECLARADO.
    # Sin esto, borrar un entry point dejaría un `ExecStart=` apuntando a nada.
    for nombre in _UNIDADES:
        assert nombre in scripts, f"{nombre}.service lanza un console script que ya no existe"


def test_ningun_rsync_escribe_sobre_el_arbol_desde_el_que_arranca_el_gabinete() -> None:
    """[T-2.70] LA PROPIEDAD QUE EL LAYOUT A/B COMPRA, escrita como invariante.

    El defecto que este test vigilaba era temporal —«el pre-vuelo tiene que ir
    ANTES del rsync destructivo»— y dependía de que hubiera un rsync destructivo.
    Con A/B no lo hay: el código nuevo aterriza en una release que nadie apunta,
    y la ruta desde la que arrancan las unidades sólo cambia por un `mv -T` del
    symlink, dentro de `canary.sh` y después de todos los gates.

    Así que lo que se ancla ahora es más fuerte que un orden: que NINGÚN rsync de
    este script escriba sobre `${VIVO}`. Mientras eso sea cierto, un aborto en
    cualquier punto deja el gabinete exactamente como estaba.
    """
    guion = _deploy()
    destinos = re.findall(r"^\s*rsync[^\n]*(?:\\\n[^\n]*)*", guion, re.MULTILINE)
    assert destinos, "no hay ningún rsync: ¿sigue este script copiando algo?"
    # El DESTINO es el último argumento; el origen no importa (la migración A/B
    # LEE del árbol vivo para conservarlo, que es lo contrario de pisarlo).
    culpables = [c for c in destinos if c.split()[-1].strip("\"'") in ("${VIVO}/", "${VIVO}")]
    assert not culpables, f"un rsync escribe sobre el árbol vivo: {culpables}"
    prevuelo = guion.index("compileall")
    activacion = _pos_comando(r'"\$\{RAIZ\}/bin/canary\.sh"')
    assert prevuelo < activacion, "el pre-vuelo debe correr ANTES de activar nada"


def test_el_prevuelo_compila_el_codigo_desplegado_y_no_otra_cosa() -> None:
    """El pre-vuelo es SINTÁCTICO a propósito: corre antes del `uv sync`, con el
    venv VIEJO, así que un `import` daría falsos abortos cada vez que el commit
    nuevo añada una dependencia. `compileall` no depende de nada instalado.

    Lo que sí exige este test es que compile el árbol de ENSAYO —el código que
    acaba de viajar— y no el vivo, que es el que todavía no se ha tocado.
    """
    m = re.search(r"^\s*if ! \S+ -m compileall[^\n]*", _deploy(), re.MULTILINE)
    assert m is not None, "el pre-vuelo debe compilar el árbol de ensayo"
    linea = m.group(0)
    assert '"${NUEVA}/takab_edge"' in linea, (
        "compileall debe apuntar a la RELEASE NUEVA; sobre el vivo no verifica lo que llega"
    )
    # Y con el intérprete DEL VENV, no con el del sistema: en el Pi son 3.12 y
    # 3.13, y compilar con el que no ejecuta es un gate que aprueba lo que no
    # arranca. `PY_PREVUELO` cae a `python3` sólo si el venv aún no existe.
    assert '"$PY_PREVUELO"' in linea, "el pre-vuelo debe compilar con el intérprete del venv"
    assert re.search(r'^PY_PREVUELO="\$\{VIVO\}/\.venv/bin/python"', _deploy(), re.MULTILINE)


def test_el_mensaje_de_aborto_del_prevuelo_puede_prometer_estado_seguro() -> None:
    """Antes de activar NADA se tocó, así que aquí el mensaje SÍ puede decir que
    el gabinete sigue con el código anterior — y debe decirlo."""
    guion = _deploy()
    bloque = guion[
        guion.index("el código nuevo no compila") : guion.index("MIGRACIÓN AL LAYOUT A/B")
    ]
    assert "NO se ha tocado" in bloque
    assert "Estado seguro" in bloque
    assert "sigue apuntando a la release" in bloque


def test_el_aborto_del_gate_ya_no_puede_afirmar_un_peligro_que_dejo_de_existir() -> None:
    """B3, el corazón — y cómo envejece un test cuando el defecto se extingue.

    El mensaje decía literalmente «El gabinete NO se ha reiniciado y sigue con el
    código anterior», y era FALSO: el proceso en memoria sí, pero EL DISCO YA
    TENÍA EL CÓDIGO NUEVO sin verificar, y el próximo arranque (corte de luz,
    `Restart=always`, un `systemctl`) lo ejecutaría solo. La falsedad era
    peligrosa porque invitaba a irse del sitio.

    [T-2.70] Con el layout A/B esa afirmación se volvió falsa AL REVÉS: la
    release que falla el gate es inerte y ningún arranque la ejecuta. Repetir el
    aviso ahora asustaría al operador con un peligro inexistente y —peor— lo
    entrenaría a no creerse los avisos de este script. Así que se prohíbe por su
    literal, igual que en su día se prohibió la frase anterior.
    """
    guion = _deploy()
    bloque = guion[guion.index("ESTADO DEL GABINETE") : _pos_comando("sudo install")]

    assert "intacto" in bloque, "el aborto del gate debe declarar que el gabinete no cambió"
    assert "ningún arranque la ejecutará" in bloque, (
        "debe decir POR QUÉ ya no hay peligro: la release no está en la ruta de arranque"
    )
    assert "EL DISCO YA TIENE EL CÓDIGO NUEVO" not in bloque, (
        "esa advertencia describía el layout in-place; con A/B es una mentira al revés"
    )
    assert "sigue con el código anterior" not in bloque, (
        "y la frase original sigue prohibida por su literal"
    )


def _unidad(nombre: str) -> str:
    return _UNIDADES[nombre].read_text()


def _asignaciones_de(nombre: str) -> list[tuple[str, str, str]]:
    """`(sección, clave, valor)` de CADA asignación de la unidad, EN ORDEN.

    Todo lo que este archivo afirma sobre las unidades cuelga de aquí, porque
    los dos errores que comete un lector ingenuo de un `.service` ya costaron
    una ronda cada uno en este proyecto:

    · **la sección importa** — systemd descarta con «Unknown key … ignoring» lo
      que esté en la sección equivocada y `systemd-analyze verify` SIGUE SALIENDO
      0. "La línea existe" no es "systemd la lee".
    · **manda la ÚLTIMA asignación, no la primera** — leer la primera es el
      defecto exacto de `declValue` en la hoja de estilos (T-2.64). Una segunda
      línea al final del archivo es invisible para un `re.search` y decisiva
      para systemd.

    Un parser único los cierra para TODAS las directivas a la vez; cerrarlos
    test a test es cómo se llegó a vigilar una de cuatro.

    Se ignoran comentarios (`#`/`;`) a propósito: `# WatchdogSec=10` en
    takab-gpio.service es una línea comentada de verdad, y contarla como
    asignación haría afirmar a esta suite algo que systemd no lee.
    """
    fuera: list[tuple[str, str, str]] = []
    seccion = ""
    for linea in _unidad(nombre).splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith(("#", ";")):
            continue
        if limpia.startswith("[") and limpia.endswith("]"):
            seccion = limpia[1:-1]
        elif "=" in limpia:
            clave, valor = limpia.split("=", 1)
            fuera.append((seccion, clave.strip(), valor.strip()))
    return fuera


#: Sección en la que systemd LEE cada directiva de la que esta suite afirma algo.
#:
#: Es un RESPALDO OFFLINE, no la fuente de verdad: la fuente es systemd, y
#: `test_systemd_no_ignora_en_silencio_ninguna_directiva` se la pregunta a él
#: para TODAS las claves del archivo (también las que nadie enumeró aquí). Este
#: mapa existe para que la guarda siga viva en una máquina sin
#: `systemd-analyze`, y su COBERTURA no depende de que alguien se acuerde:
#: `_directiva()` se niega a leer una clave que no esté declarada, así que no se
#: puede afirmar nada sobre una directiva nueva sin decir dónde la lee systemd.
_SECCION_CANONICA = {
    "StartLimitIntervalSec": "Unit",
    "Restart": "Service",
    "RestartSec": "Service",
    "RestartSteps": "Service",
    "RestartMaxDelaySec": "Service",
    "TimeoutStopSec": "Service",
    # [T-2.70.a·D3] El traspaso de propiedad de los pines toca estas cuatro.
    "Type": "Service",
    "TimeoutStartSec": "Service",
    "EnvironmentFile": "Service",
    "After": "Unit",
}

#: Claves que systemd ACUMULA en vez de sobrescribir (`Environment=`,
#: `ReadWritePaths=`, `ExecStartPre=`…). Hoy ninguna unidad repite ninguna, y
#: por eso está vacío: el día que haga falta repetir una, se declara AQUÍ con su
#: razón y el test de duplicados deja de verla como una sobrescritura silenciosa.
_CLAVES_ACUMULABLES: frozenset[str] = frozenset()


def _directiva(nombre: str, clave: str) -> str | None:
    """Valor EFECTIVO de una directiva: el de la ÚLTIMA asignación.

    systemd aplica la última; leer la primera fue el defecto de `declValue`.
    """
    assert clave in _SECCION_CANONICA, (
        f"`{clave}` no está en _SECCION_CANONICA: declara en qué sección la lee systemd antes "
        "de afirmar nada sobre su valor. Una directiva en la sección equivocada no la lee "
        "nadie y el test pasaría igual — que es exactamente cómo se vigiló una de cuatro."
    )
    valores = [v for _s, c, v in _asignaciones_de(nombre) if c == clave]
    return valores[-1] if valores else None


def _seccion_de(nombre: str, clave: str) -> str | None:
    """Sección `[...]` en la que cae una directiva (la de su última asignación).

    "La última" sólo es una respuesta sin ambigüedad porque
    `test_ninguna_directiva_se_asigna_dos_veces_en_la_misma_unidad` prohíbe que
    haya más de una.
    """
    secciones = [s for s, c, _v in _asignaciones_de(nombre) if c == clave]
    return secciones[-1] if secciones else None


@pytest.mark.parametrize("unidad", sorted(_UNIDADES))
def test_ninguna_unidad_del_gabinete_se_rinde_para_siempre(unidad: str) -> None:
    """`StartLimitIntervalSec=0` desactiva el límite de arranques.

    Con el default (5 en 10 s) y `RestartSec` de 1–2 s, un fallo al arrancar deja
    la unidad en `failed` DEFINITIVAMENTE: systemd no vuelve a intentarlo aunque
    la causa desaparezca (una partición que montó tarde, un venv a medio
    sincronizar que se completó luego, el reloj). Para un aparato que sostiene el
    alertamiento de un edificio, rendirse deja el edificio sin protección hasta
    que alguien viaje al sitio.

    Reintentar para siempre NO es gratis —cada intento mueve gas y puertas, ver
    `test_cada_ciclo_de_proceso_es_un_ciclo_fisico_de_gas_y_puertas`— y por eso
    esta directiva SOLO es aceptable acompañada del backoff que la de al lado
    exige. Las dos se leen juntas o ninguna de las dos dice la verdad.
    """
    assert _directiva(unidad, "StartLimitIntervalSec") == "0", (
        f"{unidad}: sin StartLimitIntervalSec=0, un update malo la deja en `failed` para siempre"
    )


@pytest.mark.parametrize("clave", sorted(_SECCION_CANONICA))
@pytest.mark.parametrize("unidad", sorted(_UNIDADES))
def test_cada_directiva_vigilada_vive_donde_systemd_la_lee(unidad: str, clave: str) -> None:
    """A1. La trampa de la sección, aplicada a las SEIS directivas y no a una.

    Medido con systemd 259: una directiva en la sección equivocada imprime
    «Unknown key 'X' in section [Y], ignoring.» y `systemd-analyze verify` SIGUE
    SALIENDO 0 igual. O sea: un "orden" cosmético que mueva unas líneas de
    `[Service]` a `[Unit]` —justo debajo de `StartLimitIntervalSec=0`, que es
    donde el comentario de la unidad invita a ponerlas— devuelve el gabinete a
    los defaults sin que nada se queje.

    Lo que cuesta cada una:
      · `StartLimitIntervalSec` fuera de `[Unit]` ⇒ vuelve el límite de arranques
        (5 en 10 s) ⇒ un update malo deja la unidad en `failed` PARA SIEMPRE y el
        edificio sin alertamiento hasta que alguien conduzca al sitio.
      · `RestartSteps`/`RestartMaxDelaySec` fuera de `[Service]` ⇒ se evapora el
        backoff ⇒ crash-loop a `RestartSec` fijo, o sea la válvula de gas y los
        retenedores de puerta ciclando 1800–3600 veces por hora INDEFINIDAMENTE
        (medido en "el precio físico de reintentar", más arriba).
      · `Restart`/`RestartSec` fuera de `[Service]` ⇒ el gabinete no se reinicia:
        una caída y se queda muerto.
      · `TimeoutStopSec` fuera de `[Service]` ⇒ vuelve el default de 90 s no
        declarado, que es el punto 4 de la cabecera de este archivo.

    El caso `StartLimitIntervalSec` fue el único vigilado durante una ronda
    entera; los otros cinco viajaban sin guarda.
    """
    seccion = _seccion_de(unidad, clave)
    esperada = _SECCION_CANONICA[clave]
    assert seccion is not None, f"{unidad}: la directiva {clave}= no está en la unidad"
    assert seccion == esperada, (
        f"{unidad}: {clave}= está en [{seccion}]; systemd solo la lee en [{esperada}] "
        "y en cualquier otra sección la ignora EN SILENCIO (verify sale 0 igual)"
    )


@pytest.mark.parametrize("unidad", sorted(_UNIDADES))
def test_ninguna_directiva_se_asigna_dos_veces_en_la_misma_unidad(unidad: str) -> None:
    """A2. El gemelo de `declValue`: systemd aplica la ÚLTIMA asignación.

    Reproducción medida: añadir un segundo `RestartSteps=0` al final de
    `[Service]` cambiaba el comportamiento real (systemd trata 0 como "intervalo
    constante" ⇒ adiós backoff ⇒ gas cada segundo) y la suite seguía en verde,
    porque el helper leía la PRIMERA. El valor efectivo ya lo arregla
    `_directiva()`; este test ataca la otra mitad: una unidad donde la misma
    clave aparece dos veces es AMBIGUA para quien la lee, aunque systemd tenga
    clara cuál gana.

    DERIVADO del archivo, no de una lista: cubre las seis directivas vigiladas y
    también `ExecStart=`, `WorkingDirectory=`, `EnvironmentFile=`… — toda clave
    presente, incluidas las que nadie enumeró.
    """
    vistas: dict[str, list[str]] = {}
    for seccion, clave, _valor in _asignaciones_de(unidad):
        if clave in _CLAVES_ACUMULABLES:
            continue
        vistas.setdefault(clave, []).append(seccion)

    repetidas = {clave: secs for clave, secs in vistas.items() if len(secs) > 1}
    assert not repetidas, (
        f"{unidad}: claves asignadas más de una vez {repetidas}. systemd aplica la ÚLTIMA, "
        "así que una segunda línea al final del archivo sobrescribe EN SILENCIO lo que dice "
        "el comentario de la primera. Si la clave es de las que systemd ACUMULA "
        "(Environment=, ReadWritePaths=…), decláralo en _CLAVES_ACUMULABLES con su razón."
    )


@pytest.mark.parametrize("unidad", sorted(_UNIDADES))
@pytest.mark.skipif(
    shutil.which("systemd-analyze") is None,
    reason="sin systemd-analyze: queda el respaldo offline de _SECCION_CANONICA",
)
def test_systemd_no_ignora_en_silencio_ninguna_directiva(unidad: str) -> None:
    """A1, la mitad DERIVADA: la sección canónica se la preguntamos a systemd.

    `_SECCION_CANONICA` es una lista escrita a mano, y esta sesión lleva cinco
    casos de guardas que enumeran y se quedan ciegas ante el siguiente elemento.
    El único mapa completo de "qué directiva se lee en qué sección" lo tiene
    systemd, así que se lo pedimos: cualquier clave que caiga donde no la lee
    —hoy o dentro de tres tareas, esté o no en el mapa— sale aquí.

    De regalo cubre el otro descarte silencioso ya medido: un `RestartSteps=` sin
    `RestartMaxDelaySec=` imprime «Service has RestartSteps= but no
    RestartMaxDelaySec= setting. Ignoring.» — misma familia, mismo `Ignoring.`.

    PUNTO CIEGO DECLARADO, y es la razón de que esto lea TEXTO y no el código de
    salida: `systemd-analyze verify` sale **1** en cualquier máquina que no sea
    el Pi, porque `ExecStart=/opt/takab/edge/.venv/bin/takab-edge` no existe
    aquí. El código de salida no distingue "la unidad está mal escrita" de "esta
    no es la máquina de destino", así que como gate no sirve; lo que sí es
    inequívoco es que systemd anuncie que ESTÁ IGNORANDO algo.
    """
    r = subprocess.run(
        ["systemd-analyze", "verify", str(_UNIDADES[unidad])],
        capture_output=True,
        text=True,
        # Mensajes en inglés pase lo que pase: el `strerror` del ExecStart
        # inexistente SÍ se traduce, y un match sobre texto localizado es una
        # guarda que sólo funciona en la máquina de quien la escribió.
        env={**os.environ, "LC_ALL": "C"},
    )
    ignoradas = [
        linea
        for linea in (r.stdout + r.stderr).splitlines()
        if "ignoring" in linea.lower() or "Unknown section" in linea
    ]
    assert not ignoradas, (
        f"{unidad}: systemd DESCARTA directivas de esta unidad y no falla al hacerlo:\n  "
        + "\n  ".join(ignoradas)
        + "\nUna directiva ignorada es una directiva que no existe: el gabinete corre con el "
        "default, no con lo que dice el archivo."
    )


# ------------------------------------------------- el precio físico de reintentar
#
# La justificación del backoff no es una opinión: es la medición de abajo. Vive
# en este archivo A PROPÓSITO, pegada a las directivas que la usan de excusa —
# el día que alguien cambie los modos fail-safe, el test que guarda el backoff
# es el que se pone rojo y obliga a releer por qué existe.

#: Canales cuyo modo fail-safe los hace reposar ENERGIZADOS: el ciclo de vida del
#: proceso los mueve. `GAS_VALVE` es FAIL_CLOSE, `DOOR_RETAINER` NORMALLY_CLOSED.
_CANALES_QUE_REPOSAN_ENERGIZADOS = (ActuatorChannel.GAS_VALVE, ActuatorChannel.DOOR_RETAINER)


def _pin_mock(settings, canal: ActuatorChannel):
    """Pin de gpiozero (MockFactory) del relé de un canal, con su historial."""
    from gpiozero import Device

    numero = {
        ActuatorChannel.GAS_VALVE: settings.pins.relay_gas_valve,
        ActuatorChannel.DOOR_RETAINER: settings.pins.relay_door_retainer,
    }[canal]
    return Device.pin_factory.pin(numero)


def _transiciones(pin) -> list[bool]:
    """Estados eléctricos por los que pasó el pin, en orden (MockPin.states)."""
    return [estado.state for estado in pin.states]


@pytest.mark.parametrize("canal", _CANALES_QUE_REPOSAN_ENERGIZADOS)
def test_arrancar_el_gabinete_energiza_gas_y_retenedores(settings, canal) -> None:
    """LA PREMISA, medida: arrancar el proceso ACTÚA sobre el edificio.

    No es un efecto secundario sutil — `_on_start` construye cada relé con
    `initial_value=normal_energized(modo)`, y para FAIL_CLOSE/NORMALLY_CLOSED eso
    es `True`. El pin se DRIVEA alto en la construcción del dispositivo.
    """
    pin = _pin_mock(settings, canal)
    assert pin.state is False, "premisa del test: el pin arranca de-energizado"

    controlador = GpioController(settings)
    controlador.start()
    try:
        assert pin.state is True, f"{canal.value}: arrancar el proceso debería energizarlo"
        assert controlador.relay_state(canal).energized is True
    finally:
        controlador.stop()


@pytest.mark.parametrize("canal", _CANALES_QUE_REPOSAN_ENERGIZADOS)
def test_cada_ciclo_de_proceso_es_un_ciclo_fisico_de_gas_y_puertas(settings, canal) -> None:
    """LA MEDICIÓN QUE JUSTIFICA EL BACKOFF.

    Tres arranques y tres paradas del proceso producen SEIS transiciones
    eléctricas en el mismo pin: energiza-desenergiza, energiza-desenergiza,
    energiza-desenergiza. Con `Restart=always`, `StartLimitIntervalSec=0` y
    `RestartSec=1`, un crash-loop es exactamente este bucle a 3600 ciclos/hora
    INDEFINIDAMENTE — sobre una válvula de gas y unos retenedores de puerta.

    Esto es lo que convierte «reintentar para siempre» de gratis en caro, y lo
    que obliga a que el reintento venga ESPACIADO.
    """
    pin = _pin_mock(settings, canal)
    ciclos = 3
    for _ in range(ciclos):
        controlador = GpioController(settings)
        controlador.start()
        controlador.stop()

    # El estado inicial (False) abre el historial; cada ciclo añade True y False.
    assert _transiciones(pin) == [False] + [True, False] * ciclos, (
        f"{canal.value}: se esperaban {2 * ciclos} transiciones físicas en {ciclos} ciclos de "
        "proceso; si esto cambia, el argumento del backoff en las unidades cambia con él"
    )


def test_un_arranque_que_falla_antes_de_los_reles_no_mueve_nada(settings, monkeypatch) -> None:
    """LA CORRECCIÓN AL DIAGNÓSTICO: no es cierto que CADA arranque fallido
    mueva el gas.

    El fallo de despliegue más probable —y el único que el gate de `deploy.sh`
    vigila— es que el venv no pueda importar `lgpio`/`awsiot`. Ese fallo revienta
    en `ensure_*_pin_factory()`, que corre ANTES del bucle que construye los
    relés: no se llega a energizar nada y el crash-loop resultante es
    eléctricamente MUDO.

    El ciclado físico aparece en los fallos que pasan de esa línea (o en los
    crashes posteriores a un arranque completo, que son los que
    `Restart=always` sirve de verdad). El backoff sigue siendo necesario por
    ESOS; que no lo sea por éste es parte de la verdad y queda anclado aquí.
    """
    import takab_edge.gpio as modulo_gpio

    def revienta() -> None:
        raise RuntimeError("lgpio ausente (venv podado)")

    monkeypatch.setattr(modulo_gpio, "ensure_dev_pin_factory", revienta)
    pines = {canal: _pin_mock(settings, canal) for canal in _CANALES_QUE_REPOSAN_ENERGIZADOS}

    with pytest.raises(RuntimeError):
        GpioController(settings).start()

    for canal, pin in pines.items():
        assert _transiciones(pin) == [False], (
            f"{canal.value}: un fallo anterior a la construcción de los relés no debe "
            "moverlos; si mueve, el diagnóstico del backoff hay que reescribirlo"
        )


@pytest.mark.parametrize("unidad", sorted(_UNIDADES))
def test_reintentar_para_siempre_viene_con_backoff_creciente(unidad: str) -> None:
    """El reintento infinito debe ESPACIARSE, o el gabinete cicla gas y puertas
    cada segundo para siempre (ver la medición de arriba).

    `RestartSteps=` + `RestartMaxDelaySec=` (systemd ≥ 254) suben el intervalo
    desde `RestartSec=` hasta el techo. El gabinete NUNCA se rinde —eso lo
    garantiza `StartLimitIntervalSec=0`— pero la actuación física se espacia
    hasta ser irrelevante en vez de repetirse 3600 veces por hora.
    """
    pasos = _directiva(unidad, "RestartSteps")
    assert pasos is not None, (
        f"{unidad}: con StartLimitIntervalSec=0 y sin RestartSteps=, un crash-loop "
        "cicla gas y retenedores cada RestartSec para siempre"
    )
    assert pasos.isdigit() and int(pasos) > 0, (
        f"{unidad}: RestartSteps={pasos!r}; systemd trata 0 como «intervalo constante»"
    )


@pytest.mark.parametrize("unidad", sorted(_UNIDADES))
def test_el_backoff_no_queda_ignorado_en_silencio_por_systemd(unidad: str) -> None:
    """LA TRAMPA, medida con systemd 259 y anclada aquí.

    Las dos directivas del backoff se necesitan MUTUAMENTE y systemd descarta el
    par incompleto sin fallar:

      · `RestartSteps=` sin `RestartMaxDelaySec=`
        → «Service has RestartSteps= but no RestartMaxDelaySec= setting. Ignoring.»
      · `RestartMaxDelaySec=` sin `RestartSteps=`
        → «Service has RestartMaxDelaySec= but no RestartSteps= setting. Ignoring.»
      · `RestartMaxDelaySec=` < `RestartSec=`
        → «RestartMaxDelaySec= has a value smaller than RestartSec=, resetting…»

    En los tres casos `systemd-analyze verify` sale 0. O sea: media configuración
    de backoff se lee igual de bien que la completa y el gabinete vuelve a ciclar
    el gas cada segundo. Este test es lo único que separa un backoff real de uno
    escrito.
    """
    techo = _directiva(unidad, "RestartMaxDelaySec")
    assert techo is not None, (
        f"{unidad}: RestartSteps= sin RestartMaxDelaySec= lo IGNORA systemd entero (sin error)"
    )
    assert techo.isdigit(), f"{unidad}: RestartMaxDelaySec debe ser segundos, no {techo!r}"

    inicial = _directiva(unidad, "RestartSec")
    assert inicial is not None and inicial.isdigit(), f"{unidad}: RestartSec debe ser explícito"
    assert int(techo) > int(inicial), (
        f"{unidad}: RestartMaxDelaySec={techo} no es mayor que RestartSec={inicial}; "
        "systemd resetea RestartSec al techo y el backoff se evapora"
    )

    # A régimen, el ciclado físico es 1 por techo. Con RestartSec=1 y sin techo son
    # 3600/hora; 60 s ya lo baja dos órdenes de magnitud. Es un SUELO, no el valor
    # elegido (hoy 300 s ⇒ 12 ciclos/hora), para no anclar el número a un test.
    assert int(techo) >= 60, (
        f"{unidad}: RestartMaxDelaySec={techo}s deja el ciclado de gas/puertas en "
        f"{3600 / int(techo):.0f} veces por hora a régimen; el suelo acordado son 60 s"
    )


@pytest.mark.parametrize("unidad", sorted(_UNIDADES))
def test_la_ventana_de_desproteccion_esta_declarada(unidad: str) -> None:
    """La cota superior de "cuánto tiempo el gabinete no protege" durante un
    reinicio NO es el arranque (0.62 s medidos): es el TIMEOUT DE PARADA. Sin
    `TimeoutStopSec` explícito rige el default de systemd —90 s— que nadie eligió
    y que no está escrito en ninguna parte. Declararlo no lo hace más corto: lo
    hace REVISABLE, y obliga a que el número salga de una medición y no de un
    silencio."""
    valor = _directiva(unidad, "TimeoutStopSec")
    assert valor is not None, f"{unidad}: TimeoutStopSec debe ser explícito, no heredado"
    assert valor.isdigit(), f"{unidad}: TimeoutStopSec debe ser un número de segundos, no {valor!r}"


@pytest.mark.parametrize("unidad", sorted(_UNIDADES))
def test_el_camino_de_vida_se_reinicia_siempre(unidad: str) -> None:
    assert _directiva(unidad, "Restart") == "always"


def test_las_dos_unidades_YA_NO_son_mutuamente_excluyentes() -> None:
    """[T-2.70.a·D3 · CRITERIO 3] INVERTIDO. Antes exigía lo contrario.

    Lo que decía este test hasta hoy —`Conflicts=takab-gpio.service` en
    `takab-edge`— era un PIN DE REALIDAD correcto mientras el gate #6 se
    implementó como «supervisor único»: ambos procesos reclamaban los mismos
    pines BCM y `Conflicts=` lo hacía imposible por construcción. Su corolario,
    escrito aquí mismo, era que `takab-gpio` NO CORRE en producción y que por
    tanto el criterio 1 de T-2.70 («takab-gpio no se detiene durante la
    actualización») se cumplía de forma VACÍA.

    D3 separa la propiedad de los pines, así que la exclusión mutua deja de ser
    la garantía y pasa a ser el obstáculo: con `Conflicts=`, arrancar el dueño
    de los pines DETENDRÍA a `takab-edge`, y arrancar `takab-edge` MATARÍA al
    dueño de los pines — la desprotección que D3 existe para eliminar.

    Lo que sustituye a la promesa de systemd es un cerrojo del KERNEL
    (`flock` exclusivo sobre `gpio_lock_file`, D1.1), que a diferencia de
    `Conflicts=` también atrapa al `python -m takab_edge.gpio` suelto de una
    sesión SSH — el caso que `Conflicts=` nunca cubrió. Ver
    `tests/test_gpio_ownership.py`.
    """
    for unidad in sorted(_UNIDADES):
        # Por el PARSER y no por `in texto`: la razón de haber retirado esta
        # directiva está escrita en un comentario de la propia unidad, y un
        # `in` la encontraría ahí. Es el mismo defecto que `_pos_comando()`
        # documenta para `deploy.sh`.
        claves = {clave for _s, clave, _v in _asignaciones_de(unidad)}
        assert "Conflicts" not in claves, (
            f"{unidad} sigue declarando `Conflicts=`. Con el dueño de los pines en "
            "`takab-gpio`, la exclusión mutua convierte cada arranque del otro "
            "servicio en una ventana de desprotección: quien queda vivo es uno solo, "
            "y systemd elige. La exclusión la impone el `flock` de D1.1, no la unidad."
        )


def test_el_edge_arranca_DESPUES_del_dueno_de_los_pines() -> None:
    """Lo que ocupa el sitio del `Conflicts=` retirado: un ORDEN, no una exclusión.

    Sin ninguna relación declarada, en un arranque en frío systemd lanza las dos
    unidades en paralelo y `takab-edge` puede pasar sus primeros segundos
    hablándole a un socket que nadie ató todavía (panel en `S/D`, latido sin
    relés). `After=` sólo ORDENA —no es `Requires=`—, así que un gabinete que
    todavía no tenga `takab-gpio` habilitado arranca exactamente igual que hoy.

    Y la dirección importa: lo que se retrasa es el edge (nube, SeedLink,
    panel), jamás la protección — que es lo que arranca primero.
    """
    despues = _directiva("takab-edge", "After") or ""
    assert "takab-gpio.service" in despues, (
        "`takab-edge` no declara `After=takab-gpio.service`: al retirar el "
        f"`Conflicts=` la relación entre las dos unidades se quedó sin declarar "
        f"(After={despues!r})"
    )
    # Por el PARSER, no por `in texto`: `Requires=` aparece en el comentario que
    # explica por qué NO se usa.
    claves = {clave for _s, clave, _v in _asignaciones_de("takab-edge")}
    assert not claves & {"Requires", "BindsTo", "Requisite"}, (
        "`takab-edge` no puede REQUERIR a `takab-gpio`: un gabinete todavía sin "
        "el dueño separado dejaría de arrancar, y un fallo del dueño se llevaría "
        f"por delante la nube, el SeedLink y el panel ({sorted(claves)})"
    )


def test_takab_gpio_lee_la_identidad_del_gabinete(settings, monkeypatch) -> None:
    """[T-2.70.a·D3 · CRITERIO 2] INVERTIDO, y con el daño MEDIDO.

    Hasta hoy este test exigía que `takab-gpio.service` NO tuviera
    `EnvironmentFile`, porque no corría (`Conflicts=`). El día que corre, arrancar
    con los defaults de código no es una molestia de inventario: **es el mapa de
    pines**. `GpioPins` sale de `EdgeSettings`, o sea de `/etc/takab/edge.env`, y
    un dueño de pines que no lo lea energiza los pines EQUIVOCADOS de un gabinete
    cableado — el peor fallo imaginable de esta tarea.

    La medición va aquí abajo y no en un comentario: con el mapa provisionado por
    entorno, el pin del relé de gas cambia. Un proceso sin `EnvironmentFile` se
    queda con el default de código y dispara otra cosa.
    """
    assert "EnvironmentFile=/etc/takab/edge.env" in _unidad("takab-gpio"), (
        "`takab-gpio` es el DUEÑO DE LOS PINES y no lee /etc/takab/edge.env: "
        "arrancaría con el mapa de pines de `GpioPins` por defecto"
    )
    # …y las dos unidades leen EL MISMO archivo, que es lo que impide que
    # difieran en `dev_mode`, en el mapa de pines o en el perfil fail-safe.
    assert _directiva("takab-gpio", "EnvironmentFile") == _directiva(
        "takab-edge", "EnvironmentFile"
    ), (
        "las dos unidades leen archivos de entorno DISTINTOS: pueden discrepar "
        "sobre el mapa de pines y sobre qué canal reposa energizado"
    )

    # NO-VACUIDAD: el mapa de pines SÍ viene del entorno, así que la diferencia
    # entre leer el archivo y no leerlo es física.
    from takab_edge.config import EdgeSettings

    por_defecto = EdgeSettings().pins.relay_gas_valve
    monkeypatch.setenv("TAKAB_EDGE_PINS__RELAY_GAS_VALVE", str(por_defecto + 1))
    provisionado = EdgeSettings().pins.relay_gas_valve
    assert provisionado != por_defecto, (
        "el mapa de pines dejó de ser configurable por entorno; si es así, revisa "
        "por qué este test exige el EnvironmentFile"
    )


@pytest.mark.parametrize("unidad", sorted(_UNIDADES))
def test_ninguna_unidad_TOLERA_arrancar_sin_la_identidad_del_gabinete(unidad: str) -> None:
    """[T-2.70.a·D3·m5] `EnvironmentFile=` SIN el prefijo `-`, y por qué ésa es
    la dirección.

    Con `-`, systemd arranca la unidad aunque el archivo falte o no se pueda
    leer. Para el DUEÑO DE LOS PINES eso significa arrancar con los defaults de
    código —**el mapa de `GpioPins` incluido**— y energizar los pines
    EQUIVOCADOS de un gabinete cableado, en silencio y con la unidad en verde.
    Y el degradado se realimenta: sin `edge.env` no hay `TAKAB_EDGE_GPIO_OWNER`,
    así que `gpio_owner` cae a `edge` y el que se queda con los pines por el mapa
    por defecto es el supervisor de 16 módulos.

    LA DECISIÓN, y por qué no repite el defecto que la auditoría de D1 rechazó en
    `_failsafe`. Aquello era un modo de fallo NUEVO; esto no lo es:
    `takab-edge.service` ya exigía este mismo archivo desde T-1.40, así que un
    gabinete sin `/etc/takab/edge.env` es, desde antes de D3, un gabinete que no
    arranca. Lo que D3 añade es un segundo proceso que lo exige, no una razón
    nueva para no arrancar.

    Y entre los dos desenlaces posibles el orden está claro:
      · exigirlo ⇒ la unidad no arranca, systemd lo dice, `Restart=always` +
        `StartLimitIntervalSec=0` la dejan reintentando PARA SIEMPRE (así que
        reponer el archivo la levanta sola) y el paso 7 de `deploy.sh` sale en
        rojo con «NADIE reclamó los pines»;
      · tolerarlo ⇒ un proceso VERDE gobernando los pines equivocados de un
        edificio real, que nada vuelve a corregir.
    Fail-closed, como todo lo que decide quién toca la válvula de gas.

    Se lee por el PARSER: `-EnvironmentFile=…` contiene la subcadena
    `EnvironmentFile=/etc/takab/edge.env`, así que un `assert … in texto` —que es
    lo que había— NO ve el prefijo. Con el parser, la clave pasa a llamarse
    `-EnvironmentFile` y `_directiva()` devuelve `None`.
    """
    assert _directiva(unidad, "EnvironmentFile") == "/etc/takab/edge.env", (
        f"{unidad}: la identidad del gabinete no se lee de /etc/takab/edge.env "
        f"(EnvironmentFile={_directiva(unidad, 'EnvironmentFile')!r})"
    )
    claves = {clave for _s, clave, _v in _asignaciones_de(unidad)}
    assert "-EnvironmentFile" not in claves, (
        f"{unidad} usa `-EnvironmentFile=`: con el `-`, un /etc/takab/edge.env "
        "ausente o ilegible NO impide arrancar, y el dueño de los pines se "
        "levanta con el mapa de `GpioPins` por defecto sobre un gabinete "
        "cableado. Un proceso verde energizando el pin equivocado es peor que "
        "una unidad que no arranca y lo grita."
    )


def test_la_identidad_del_gabinete_se_lee_SIEMPRE_con_sudo() -> None:
    """En un Pi real `edge.env` es 0600 root:root, y el despliegue NO corre como root.

    El defecto, medido contra `gw-dev-0001` el 2026-08-09: el pre-vuelo hacía
    `[ -r "$ENTORNO" ]` y `sed … "$ENTORNO"` a pelo. Como el bloque remoto corre
    con el usuario de despliegue —igual que `sudo install` y `sudo systemctl` de
    más abajo—, la lectura daba `Permission denied`, el script concluía «este
    gabinete no tiene identidad» y **abortaba todo despliegue a un gabinete de
    verdad**. Nunca se vio porque el arnés usa un fichero temporal que el usuario
    de test SÍ puede leer.

    Y el daño peor estaba detrás del guard: sin él, la lectura de
    `TAKAB_EDGE_GPIO_OWNER` habría fallado igual de callada y caído al default
    `edge` — en un gabinete D3 eso DESHABILITA `takab-gpio` y lo deja sin dueño de
    pines tras el siguiente reinicio.

    Se comprueba sobre el TEXTO del script y no ejecutándolo, porque en el arnés
    ambas formas funcionan: el sandbox no puede reproducir un root:root.
    """
    # Las continuaciones de línea se PEGAN antes de mirar: `sudo -n env \\` y su
    # `TAKAB_EDGE_ENV_FILE="$ENTORNO"` son UN comando, y separarlos hacía que
    # este test acusara de leer sin sudo a una invocación que corre como root.
    texto = re.sub(r"\\\n\s*", " ", _deploy())
    lecturas = [
        linea.strip()
        for linea in texto.splitlines()
        if '"$ENTORNO"' in linea and not linea.lstrip().startswith("#")
    ]
    assert lecturas, "nadie lee ya `$ENTORNO`: revisa si el pre-vuelo de identidad sigue ahí"
    sin_sudo = [linea for linea in lecturas if "sudo" not in linea]
    assert not sin_sudo, (
        "el despliegue toca la identidad del gabinete SIN sudo, y en un Pi real ese "
        f"archivo es 0600 root:root: {sin_sudo}"
    )


def _claves_gestionadas() -> set[str]:
    """Claves `TAKAB_EDGE_*` que el aprovisionamiento ESCRIBE de verdad.

    Sólo cuentan los `printf` cuyo destino es `edge.env.managed`, que es el
    bloque que `merge_env.py` aplica sobre el archivo del gabinete. Un `echo`
    informativo que mencione la clave NO es escribirla — y sin este recorte el
    extractor se daba por satisfecho con el mensaje final del script (medido:
    borrar el `printf` dejaba los 92 tests en verde).
    """
    escritas: set[str] = set()
    for formato in re.findall(
        r"printf '([^']*)'[^\n]*(?:\\\n[^\n]*)*edge\.env\.managed", _PROVISION.read_text()
    ):
        escritas |= set(re.findall(r"(TAKAB_EDGE_[A-Z0-9_]+)=", formato))
    return escritas


def test_el_aprovisionamiento_escribe_la_ruta_DURABLE_de_la_cola() -> None:
    """[T-2.67.b] Sin esta clave, la cola «durable» muere en cada reinicio.

    `cloud_spool_dir` vale `""` por defecto —y así debe seguir, porque es lo que
    deja correr la suite y el portátil sin tocar `/var/lib`—, pero entonces
    `_tmp_spool()` y `_default_pending_dir()` hacen un **`mkdtemp` NUEVO en cada
    arranque**: el spool a la nube y las evidencias pendientes se evaporan al
    reiniciar el gabinete. Roza la regla de oro 3, y es el hueco **H-1** del
    manual de operación, ese que hoy obliga a decirle al cliente «mientras el
    panel diga COLA NO DURABLE, no reinicies el gabinete».

    El gabinete de referencia lo tiene puesto **a mano**: por eso el defecto no
    se veía en el único Pi que miramos. Un gabinete nuevo aprovisionado hoy
    nacería sin él.

    Se escribe desde el aprovisionamiento y no como default del código porque es
    una decisión de INSTALACIÓN (qué disco, qué punto de montaje), y porque el
    default de `Settings` lo heredarían también los tests y el portátil.
    """
    assert "TAKAB_EDGE_CLOUD_SPOOL_DIR" in _claves_gestionadas(), (
        "el aprovisionamiento no escribe TAKAB_EDGE_CLOUD_SPOOL_DIR: el gabinete "
        "nace con la cola en un tempdir y pierde spool y evidencia en cada "
        "reinicio, en silencio"
    )


def test_lo_que_el_despliegue_LEE_del_edge_env_alguien_sabe_ESCRIBIRLO() -> None:
    """[T-2.70.a·D3·B2] `grep -rn "GPIO_OWNER" deploy/` no devolvía nada, y
    tampoco lo escribía nadie.

    D3 introdujo `TAKAB_EDGE_GPIO_OWNER` como la perilla que decide qué proceso
    sostiene la sirena, el gas, los ascensores y los retenedores… y no había
    forma DOCUMENTADA de ponerla en un gabinete: ni `deploy.sh` la leía ni
    `provision_gateway.sh` la escribía. El resultado es el criterio 1 de la
    ficha cumpliéndose sólo dentro de los tests.

    La regla es DERIVADA: toda clave `TAKAB_EDGE_*` que el despliegue extraiga
    del `edge.env` tiene que ser una clave que el aprovisionamiento sepa
    escribir. Así, leer una perilla nueva obliga a decidir cómo se provisiona, y
    el olvido sale en rojo aquí en vez de salir en un gabinete a medio traspasar.
    """
    # Las que `deploy.sh` saca del archivo de identidad con su `sed -n 's/…=//p'`.
    leidas = set(re.findall(r"(TAKAB_EDGE_[A-Z0-9_]+)=//p", _deploy()))
    assert leidas, (
        "el despliegue ya no lee NINGUNA clave del edge.env; si eso es cierto, "
        "revisa cómo decide a qué unidad habilitar"
    )

    escritas = _claves_gestionadas()
    assert "TAKAB_EDGE_GATEWAY_ID" in escritas, (
        "el extractor de claves gestionadas no encontró ni la identidad del "
        f"gabinete: se quedó con {sorted(escritas)} y estaría aprobando por vacío"
    )

    for clave in sorted(leidas):
        assert clave in escritas, (
            f"`deploy.sh` decide qué hacer según `{clave}` del edge.env y "
            f"{_PROVISION.name} no sabe escribirla (gestionadas: "
            f"{sorted(escritas)}): la única vía de ponerla sería editar "
            "/etc/takab/edge.env a mano en el Pi, que es justo lo que el "
            "aprovisionamiento existe para no tener que hacer"
        )


def test_la_cabecera_del_despliegue_no_afirma_una_exclusion_que_ya_no_existe() -> None:
    """[T-2.70.a·D3·B2] La narrativa del archivo que se lee ANTES de desplegar.

    `deploy/edge/deploy.sh` afirmaba COMO HECHO que «`takab-edge` es el proceso
    que sostiene el reflejo SASMEX→sirena (gate #6: supervisor único,
    `Conflicts=takab-gpio.service`)». D3 retiró esa directiva: hoy el dueño de
    los pines puede ser `takab-gpio` y quien lo decide es `TAKAB_EDGE_GPIO_OWNER`
    en el `edge.env` del gabinete. Un operador que lee esa cabecera antes de
    tocar un edificio se lleva el modelo mental equivocado de qué reinicia qué.

    DERIVADO de las unidades, no de una lista de frases prohibidas: la premisa
    (nadie declara `Conflicts=`) se mide aquí mismo, así que el día que alguien
    la reponga este test deja de exigir nada — y el que la vigila es
    `test_las_dos_unidades_YA_NO_son_mutuamente_excluyentes`.
    """
    declaran_exclusion = any(
        "Conflicts" in {clave for _s, clave, _v in _asignaciones_de(unidad)} for unidad in _UNIDADES
    )
    assert not declaran_exclusion, (
        "premisa: ninguna unidad declara `Conflicts=` (si esto cambia, es la "
        "topología la que volvió atrás, no la cabecera)"
    )
    assert "Conflicts=takab-gpio.service" not in _deploy(), (
        "la cabecera de deploy.sh sigue afirmando la exclusión mutua que D3 "
        "retiró: se lee antes de desplegar y describe un gabinete que ya no "
        "existe"
    )
    assert "TAKAB_EDGE_GPIO_OWNER" in _deploy(), (
        "y tiene que nombrar lo que HOY decide quién sostiene la sirena, el gas "
        "y los retenedores: la cabecera no puede quedarse muda sobre el dueño"
    )


def test_el_dueno_de_los_pines_avisa_a_systemd_cuando_YA_es_dueno() -> None:
    """[T-2.70.a·D3] `Type=notify` (punto 3 de D2/P2 · M10 de la auditoría D1).

    `run_gpio_process` emite `sd_notify(READY=1)` DESPUÉS de tomar el cerrojo,
    fijar la pin factory, construir los cinco relés, armar los tres botones y
    sembrar el contacto sostenido. Con `Type=simple` ese aviso era código muerto
    (sin `NOTIFY_SOCKET` es un no-op) y `systemctl start takab-gpio` volvía
    cuando el proceso EXISTÍA — no cuando era DUEÑO. Un traspaso que se declara
    terminado antes de serlo es un gabinete sin dueño de pines durante el hueco.

    `takab-edge` se queda en `Type=simple` a propósito: no emite READY y ponerle
    `notify` lo dejaría en `activating` para siempre.
    """
    assert _directiva("takab-gpio", "Type") == "notify", (
        "`takab-gpio` sigue en Type=simple: `systemctl start` vuelve cuando el "
        "proceso arrancó, no cuando sostiene los pines, y el `READY=1` que "
        "`run_gpio_process` ya emite no lo escucha nadie"
    )
    assert _directiva("takab-edge", "Type") == "simple", (
        "`takab-edge` no emite `sd_notify(READY=1)`: con Type=notify se quedaría "
        "en `activating` hasta agotar el plazo y systemd lo mataría"
    )


@pytest.mark.parametrize("unidad", sorted(_UNIDADES))
def test_la_ventana_de_ARRANQUE_esta_declarada(unidad: str) -> None:
    """[T-2.70.a·D3] La gemela de `TimeoutStopSec`, que `Type=notify` hace real.

    Con `Type=simple` el plazo de arranque es inerte (systemd da la unidad por
    arrancada en el `fork`). Con `Type=notify` deja de serlo: si el `READY=1` no
    llega, systemd MATA el proceso al vencer el plazo — y ese proceso puede estar
    perfectamente sano y sosteniendo los pines, con lo que su muerte cicla gas y
    retenedores cada plazo + backoff.

    Las dos direcciones tienen coste y por eso el número se declara en vez de
    heredarse:
      · demasiado corto ⇒ mata a un dueño sano que tardó en anunciarse;
      · infinito ⇒ un arranque colgado a mitad de `_arrancar_hardware` (relés a
        medio construir, sin reflejo) no se rescata NUNCA, y eso es un edificio
        sin alertamiento en silencio — el peor desenlace de la ficha.

    90 s es el default de systemd: la línea no cambia el comportamiento, lo hace
    revisable. Medirlo en el Pi 4 es `GATE-HW` (exec→cerrojo: 0.60 s en x86/dev,
    ~1.0 s con los imports de producción).
    """
    valor = _directiva(unidad, "TimeoutStartSec")
    assert valor is not None, f"{unidad}: TimeoutStartSec debe ser explícito, no heredado"
    assert valor.isdigit(), (
        f"{unidad}: TimeoutStartSec={valor!r}. `infinity` deja sin rescate un "
        "arranque colgado con los relés a medio construir"
    )
    assert int(valor) > 5, (
        f"{unidad}: TimeoutStartSec={valor}s está por debajo del arranque medido "
        "(~1 s con los imports de producción en x86; el Pi 4 no está medido): "
        "systemd mataría a un dueño de pines sano"
    )
    assert "EnvironmentFile=/etc/takab/edge.env" in _unidad("takab-edge")


# ---------------------------------------------------------------------------
# [T-2.70] El agente de canary/reversión, como ARTEFACTO
# ---------------------------------------------------------------------------

_CANARY = _RAIZ / "deploy" / "edge" / "canary.sh"


def test_el_reversor_no_importa_una_sola_linea_del_codigo_que_sustituye() -> None:
    """LA RAZÓN DE SER DE ESTE ARCHIVO, escrita como test.

    El caso que un rollback existe para cubrir es «la versión nueva NO ARRANCA».
    Si el reversor viviera dentro de esa versión —o dependiera de su venv, o
    importara `takab_edge`— sería justo el caso en que no puede correr. Por eso
    es bash, no toca el paquete y `deploy.sh` lo instala en `${RAIZ}/bin`, fuera
    de toda release.
    """
    # Sólo CÓDIGO: los comentarios sí nombran el paquete, y deben — es donde se
    # explica por qué el symlink apunta a `<release>/edge` y no a la release.
    codigo = [
        linea for linea in _CANARY.read_text().splitlines() if not linea.lstrip().startswith("#")
    ]
    assert not [linea for linea in codigo if "takab_edge" in linea], (
        "el reversor EJECUTA algo del paquete que sustituye: si esa versión no "
        "importa, no queda nadie que revierta"
    )
    assert not [linea for linea in codigo if "/.venv/bin/python" in linea], (
        "depende del intérprete de una release; un venv a medio sincronizar lo deja mudo"
    )
    deploy = _deploy()
    assert "canary.sh" in deploy and "/bin/canary.sh" in deploy, (
        "deploy.sh tiene que INSTALAR el reversor fuera de las releases"
    )


def test_el_reversor_no_reinicia_jamas_al_dueno_de_los_pines() -> None:
    """Regla de oro 4, sobre el TEXTO y no sólo sobre el comportamiento: una
    rama nueva que nombrara `takab-gpio` en un `systemctl restart` costaría un
    ciclo de `GAS_VALVE` y `DOOR_RETAINER` y una ventana sin sirena, y podría
    colarse por un camino que los tests de comportamiento no recorran.
    """
    lineas = [
        linea
        for linea in _CANARY.read_text().splitlines()
        if not linea.lstrip().startswith("#") and "systemctl" in linea
    ]
    culpables = [linea for linea in lineas if "takab-gpio" in linea]
    assert not culpables, f"el reversor toca al dueño de los pines: {culpables}"


def test_el_gate_del_interprete_vigila_lo_que_ProtectHome_oculta() -> None:
    """[T-2.70 · CAMPO 2026-08-23] El DEFAULT de la costura, anclado por texto.

    `TAKAB_DEPLOY_RUTAS_OCULTAS` existe para que el sandbox pueda demostrar que
    el gate muerde. Una costura así puede perder los dientes de dos formas —que
    el default encoja, o que alguien la deje vacía— y las dos serían silenciosas:
    el despliegue seguiría saliendo verde y el gabinete moriría con 203/EXEC al
    reiniciar. Los tres prefijos son exactamente los que `ProtectHome=true`
    esconde (systemd.exec(5)).
    """
    guion = _deploy()
    m = re.search(r'^RUTAS_OCULTAS="\$\{TAKAB_DEPLOY_RUTAS_OCULTAS:-\}"', guion, re.MULTILINE)
    assert m is not None, "la costura del gate del intérprete desapareció"
    respaldo = re.search(r'RUTAS_OCULTAS="([^"]*)"\s*$', guion, re.MULTILINE)
    defaults = [linea for linea in guion.splitlines() if 'RUTAS_OCULTAS="/home' in linea]
    assert defaults, f"el default dejó de nombrar /home: {respaldo}"
    for prefijo in ("/home", "/root", "/run/user"):
        assert prefijo in defaults[0], (
            f"`{prefijo}` salió del default y ProtectHome=true lo sigue ocultando"
        )


def test_el_interprete_de_uv_se_instala_FUERA_de_lo_que_ProtectHome_oculta() -> None:
    """La otra mitad del mismo defecto: no basta con RECHAZAR un venv malo, hay
    que crear uno bueno.

    `ssh host "bash -s"` es un shell NO interactivo y NO de login: no lee
    `.profile` ni `.bashrc`, así que ninguna variable del usuario llega al bloque
    remoto. Hasta esta ficha, que el intérprete del Pi viviera en
    `/opt/takab/.python` dependía de que alguien hubiera exportado
    `UV_PYTHON_INSTALL_DIR` a mano en julio — un hecho guardado en un directorio
    y en ningún archivo, que sobrevivió sólo porque el venv nunca se reconstruyó.
    """
    guion = _deploy()
    assert "export UV_PYTHON_INSTALL_DIR=" in guion, (
        "el despliegue no declara dónde instala uv su intérprete: vuelve a depender "
        "de que alguien lo exportara a mano una vez"
    )
    idx_export = guion.index("export UV_PYTHON_INSTALL_DIR")
    idx_sync = _pos_comando(r"uv sync \$\{EDGE_EXTRA_FLAGS\}")
    assert idx_export < idx_sync, "se declara DESPUÉS del `uv sync`: llega tarde"
    assert "/opt/takab/.python" in guion, "el default tiene que estar fuera de /home"
