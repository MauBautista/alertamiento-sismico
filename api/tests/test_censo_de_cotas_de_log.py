"""[T-7.47] CENSO · todo contenedor RESIDENTE de la nube declara su cota de log.

`takab-db` nació sin `--log-opt`, así que su `LogConfig` era `json-file` con
configuración vacía: **sin techo**. Medido el 2026-09-17 en la instancia, llevaba
84 MB en 73 días —~1,16 MB/día— y era el único consumidor sin cota del volumen
raíz, el que la poda de `T-7.46` jamás toca. Nadie lo vio porque el contenedor de
la base **no está en el compose**: lo arranca `user_data` con un `docker run`, así
que ni el censo de servicios ni el informe de conformidad lo miraban.

## La frontera se DERIVA, no se enumera

Una lista de exentos crece y acaba tapando justo lo que el censo vigila. Aquí la
clase de cada contenedor sale de cómo se crea:

* **RESIDENTE** ⇔ su creación declara política de reinicio (`--restart` en un
  `docker run`, `restart:` en un servicio del compose). Su log se acumula mientras
  la máquina viva ⇒ **debe declarar cota, sin excepción**.
* **EFÍMERO** ⇔ lleva `--rm`, o el mismo fichero lo retira con un `docker rm`. Su
  log muere con él ⇒ exento **por construcción**, no por estar en una lista.
* Cualquier otra cosa es ROJA: si no se puede decir a cuál de las dos pertenece,
  el censo no puede afirmar nada sobre ella.

## Y las dos mitades tienen que decir el MISMO número

El par `(max-size, max-file)` vive necesariamente en dos sitios —el compose, que
Terraform no puede leer, y un `local` del módulo `database`, que el compose no
puede leer— así que lo único que impide que diverjan es este cruce. Sin él, subir
el `max-size` del compose dejaría a `takab-db` en el valor viejo y nadie se
enteraría.

⚠️ **PyYAML se exige, no se saltea.** Un censo que se salta cuando falta una
dependencia es un censo que pasa en verde sin haber mirado.
"""

from __future__ import annotations

import re
from pathlib import Path

# ⚠️ Se importa A SECAS, sin `importorskip`: si faltara PyYAML esto tiene que
# salir en ERROR, no en SKIP. Un censo que se saltea cuando falta una dependencia
# es un censo que pasa en verde sin haber mirado.
import yaml

RAIZ = Path(__file__).resolve().parents[2]
COMPOSE = RAIZ / "deploy" / "cloud" / "docker-compose.yml"
MODULO_DB = RAIZ / "infra" / "terraform" / "modules" / "database"
DEPLOY = RAIZ / "deploy" / "cloud" / "deploy.sh"

#: `docker run …` hasta el final del comando, siguiendo las continuaciones de
#: línea. Se recorta así y no con `shlex` porque estos scripts llevan `\` de
#: continuación y comillas a medio abrir que a `shlex` le hacen lanzar.
# ⚠️ La alternativa de CONTINUACIÓN va PRIMERA. Con `[^\n]` delante, el `\` de
# fin de línea lo consume ella y el comando se corta ahí: el censo veía medio
# `docker run` y daba «sin cota» sobre uno que sí la declara. Costó una corrida.
_RUN = re.compile(r"docker run\b((?:\\\n|[^\n])*)", re.M)


def _ficheros_que_corre_la_instancia() -> list[Path]:
    """El alcance, DERIVADO de lo que Terraform renderiza y el despliegue copia.

    Las plantillas salen de los `templatefile("${path.module}/…")` del módulo, no
    de un glob: si una deja de renderizarse, deja de correr en la máquina y sale
    sola del censo.
    """
    main_tf = (MODULO_DB / "main.tf").read_text(encoding="utf-8")
    plantillas = [
        MODULO_DB / n
        for n in sorted(set(re.findall(r'templatefile\("\$\{path\.module\}/([^"]+)"', main_tf)))
    ]
    return [*plantillas, DEPLOY]


def _creaciones() -> list[tuple[str, int, str]]:
    """Cada `docker run` de esos ficheros: `(fichero, línea, comando entero)`."""
    salida: list[tuple[str, int, str]] = []
    for ruta in _ficheros_que_corre_la_instancia():
        texto = ruta.read_text(encoding="utf-8")
        for m in _RUN.finditer(texto):
            linea = texto[: m.start()].count("\n") + 1
            # El heredoc del despliegue va sin comillas, así que el `\` de
            # continuación llega escapado como `\\`. Se normaliza para que el
            # comando se lea igual venga de donde venga.
            cmd = m.group(0).replace("\\\\\n", " ").replace("\\\n", " ")
            salida.append((str(ruta.relative_to(RAIZ)), linea, " ".join(cmd.split())))
    return salida


def _es_residente(cmd: str) -> bool:
    return "--restart" in cmd


def _es_efimero(cmd: str, texto_del_fichero: str) -> bool:
    if "--rm" in cmd:
        return True
    # O el fichero lo retira él mismo. Se busca `docker rm` en el mismo fichero:
    # el id se captura en una variable y se borra más abajo.
    return bool(re.search(r"docker rm\b", texto_del_fichero))


def _nombre_del_run(cmd: str) -> str | None:
    m = re.search(r"--name\s+(\S+)", cmd)
    return m.group(1).strip('"') if m else None


def _cota_impuesta_en_otro_sitio(nombre: str | None) -> bool:
    """El TERCER estado: residente cuya cota la pone otro mecanismo, comprobado.

    `takab-db` se crea SIN cota a propósito y la adquiere en la primera pasada de
    la asociación SSM. La razón está escrita en `pitr_setup.sh.tpl`: tocar
    `user_data.sh.tpl` cambiaría el atributo `user_data` de la instancia viva y el
    siguiente `terraform apply` la pararía y arrancaría, y meterlo en
    `ignore_changes` cegaría el plan PARA SIEMPRE.

    La cita NO se cree: se comprueba que el mecanismo existe, que nombra a ESE
    contenedor y que mide antes de actuar. Sin esas tres cosas, el residente vuelve
    a ser ROJO.
    """
    if nombre is None:
        return False
    tpl = (MODULO_DB / "pitr_setup.sh.tpl").read_text(encoding="utf-8")
    return (
        "HostConfig.LogConfig.Config" in tpl
        and "--log-opt max-size=${log_max_size}" in tpl
        and 'docker run -d --name "$CONT"' in tpl
        and f"CONT={nombre}" in tpl
    )


def _cota_del_run(cmd: str) -> tuple[str | None, str | None]:
    size = re.search(r"--log-opt\s+max-size=(\S+)", cmd)
    files = re.search(r"--log-opt\s+max-file=(\S+)", cmd)
    return (size.group(1) if size else None, files.group(1) if files else None)


def _servicios_del_compose() -> dict[str, dict]:
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return doc.get("services", {})


def _cota_del_servicio(spec: dict) -> tuple[str | None, str | None]:
    opciones = (spec.get("logging") or {}).get("options") or {}
    size = opciones.get("max-size")
    files = opciones.get("max-file")
    return (str(size) if size is not None else None, str(files) if files is not None else None)


def _cota_del_terraform() -> tuple[str, str]:
    main_tf = (MODULO_DB / "main.tf").read_text(encoding="utf-8")
    size = re.search(r'log_max_size\s*=\s*"([^"]+)"', main_tf)
    files = re.search(r'log_max_file\s*=\s*"([^"]+)"', main_tf)
    assert size and files, "el módulo `database` no declara `log_max_size`/`log_max_file`"
    return size.group(1), files.group(1)


# ───────────────────────────────────── las guardas de no-vacuidad, primero


def test_el_censo_MIRA_donde_debe() -> None:
    """Si el alcance dejara de derivarse, todo lo de abajo pasaría por vacuidad."""
    ficheros = _ficheros_que_corre_la_instancia()
    assert len(ficheros) >= 5, f"el alcance derivado solo trajo {len(ficheros)} ficheros"
    nombres = {f.name for f in ficheros}
    assert "user_data.sh.tpl" in nombres, "falta la plantilla que crea `takab-db`"
    assert "deploy.sh" in nombres

    creaciones = _creaciones()
    assert len(creaciones) >= 4, f"solo se vieron {len(creaciones)} `docker run`"
    assert any("takab-db" in c for _, _, c in creaciones), (
        "el barrido no ve la creación de `takab-db`, que es el contenedor que trajo esta ficha"
    )

    servicios = _servicios_del_compose()
    assert len(servicios) >= 8, f"el compose solo declaró {len(servicios)} servicios"


# ──────────────────────────────────────── la frontera, y que nadie caiga fuera


def test_TODO_docker_run_es_residente_o_EFIMERO_ACREDITADO() -> None:
    """Lo que no se pueda clasificar es rojo: el censo no afirma sobre lo que no sabe."""
    sin_clasificar: list[str] = []
    for fichero, linea, cmd in _creaciones():
        texto = (RAIZ / fichero).read_text(encoding="utf-8")
        if _es_residente(cmd) or _es_efimero(cmd, texto):
            continue
        sin_clasificar.append(f"{fichero}:{linea}")
    assert not sin_clasificar, (
        "hay `docker run` que no declaran ni política de reinicio ni retirada: no se "
        f"puede saber si su log se acumula. {sin_clasificar}"
    )


def test_TODO_contenedor_RESIDENTE_declara_su_cota_de_log() -> None:
    """El defecto que trajo la ficha, convertido en guarda.

    `takab-db` es residente —`--restart unless-stopped`— y no declaraba cota. Su
    log creció hasta 84 MB sin que nada lo mirara, porque no está en el compose y
    por tanto ni el censo de servicios ni la conformidad lo veían.
    """
    sin_cota: list[str] = []
    for fichero, linea, cmd in _creaciones():
        if not _es_residente(cmd):
            continue
        size, files = _cota_del_run(cmd)
        if size and files:
            continue
        # Tercer estado: la cota la impone otro mecanismo, y se COMPRUEBA.
        if _cota_impuesta_en_otro_sitio(_nombre_del_run(cmd)):
            continue
        sin_cota.append(f"{fichero}:{linea} (max-size={size}, max-file={files})")
    for nombre, spec in _servicios_del_compose().items():
        size, files = _cota_del_servicio(spec)
        if not size or not files:
            sin_cota.append(f"compose::{nombre} (max-size={size}, max-file={files})")
    assert not sin_cota, (
        "hay contenedores residentes sin cota de log. Su fichero JSON crece sin "
        "techo en el volumen raíz y `docker image prune` NO lo toca: es el defecto "
        f"de T-7.47. {sin_cota}"
    )


def test_TODOS_dicen_el_MISMO_par() -> None:
    """El par vive en dos sitios por necesidad; esto es lo que impide que diverjan.

    Terraform no puede leer el compose y el compose no puede leer el `local` del
    módulo. Sin este cruce, subir el `max-size` de uno dejaría al otro en el valor
    viejo y nadie se enteraría.
    """
    esperado = _cota_del_terraform()
    discrepan: list[str] = []
    for nombre, spec in _servicios_del_compose().items():
        cota = _cota_del_servicio(spec)
        if cota != esperado:
            discrepan.append(f"compose::{nombre} dice {cota}")
    for fichero, linea, cmd in _creaciones():
        if not _es_residente(cmd):
            continue
        cota = _cota_del_run(cmd)
        if cota == (None, None):
            continue
        # Una plantilla de Terraform que INTERPOLA el local es lo correcto por
        # construcción: no puede divergir porque no repite el número. Se acepta
        # exactamente la interpolación de ESOS dos locales, nada más.
        if cota == ("${log_max_size}", "${log_max_file}"):
            continue
        if cota != esperado:
            discrepan.append(f"{fichero}:{linea} dice {cota}")
    assert not discrepan, (
        f"el terraform declara {esperado} y hay quien dice otra cosa: las dos "
        f"mitades del sistema tienen que decir UN número, no dos. {discrepan}"
    )


def test_el_documento_SSM_impone_la_cota_al_contenedor_QUE_YA_EXISTE() -> None:
    """La otra mitad, y la que de verdad arregla la instancia viva.

    `LogConfig` se congela al CREAR el contenedor: ni `docker update`, ni el
    default del demonio, ni reiniciar nada lo cambian. Al contenedor que ya existe
    solo se le pone cota recreándolo, y eso lo hace el documento SSM con la misma
    guarda idempotente que usa para `archive_mode`.
    """
    tpl = (MODULO_DB / "pitr_setup.sh.tpl").read_text(encoding="utf-8")
    assert "HostConfig.LogConfig.Config" in tpl, (
        "el documento no MIDE la cota en caliente: sin esa guarda, recrearía la "
        "base en cada pasada diaria de la asociación"
    )
    assert "--log-opt max-size=${log_max_size}" in tpl
    assert "--log-opt max-file=${log_max_file}" in tpl
    # Y el par baja del MISMO local que el resto, no escrito a mano aquí.
    main_tf = (MODULO_DB / "main.tf").read_text(encoding="utf-8")
    assert "log_max_size = local.log_max_size" in main_tf


def test_la_recreacion_conserva_TODO_lo_que_la_creacion_declara() -> None:
    """Una divergencia aquí levanta una base vacía sobre un sistema en marcha.

    El `docker run` que recrea tiene que ser superconjunto del que crea: mismo
    nombre, misma política de reinicio, mismo puerto —que es lo único que hace que
    los ocho servicios con `network_mode: host` alcancen la base— y, sobre todo,
    el MISMO bind mount del datadir.
    """
    original = (MODULO_DB / "user_data.sh.tpl").read_text(encoding="utf-8")
    recreacion = (MODULO_DB / "pitr_setup.sh.tpl").read_text(encoding="utf-8")
    bloque = recreacion.split("2b.", 1)[1]
    for aguja, porque in (
        ("--restart unless-stopped", "sin política de reinicio, la base no vuelve tras un reboot"),
        ("-p 5432:5432", "sin el puerto, los ocho servicios hablan con un puerto cerrado"),
        (
            "-v /data/pgdata:/home/postgres/pgdata/data",
            "sin el bind mount, Postgres arranca sobre un datadir VACÍO",
        ),
        ("timescale/timescaledb-ha:pg16", "otra imagen es otra base"),
    ):
        assert aguja in original, f"la creación original dejó de declarar `{aguja}`"
        assert aguja in bloque, f"la recreación no conserva `{aguja}`: {porque}"


def test_la_contrasena_NO_viaja_por_linea_de_comando() -> None:
    """`ps` la delataría. El patrón de la casa es env-file 0600 en tmpfs."""
    tpl = (MODULO_DB / "pitr_setup.sh.tpl").read_text(encoding="utf-8")
    bloque = tpl.split("2b.", 1)[1].split("--- 3.", 1)[0]
    assert "--env-file" in bloque
    assert "-e POSTGRES_PASSWORD" not in bloque, (
        "la contraseña va por línea de comando en la recreación: cualquier `ps` de "
        "la instancia la vería"
    )
    assert "umask 077" in bloque, "el env-file se escribe sin `umask` restrictivo"


def test_el_censo_CAZA_un_residente_sin_cota() -> None:
    """Porque un censo que no puede fallar es una ceremonia.

    Se simula el estado anterior a esta ficha —el `docker run` de `takab-db` sin
    `--log-opt`— y se comprueba que la clasificación lo marca.
    """
    como_estaba = (
        "docker run -d --name takab-db --restart unless-stopped "
        "-p 5432:5432 -v /data/pgdata:/home/postgres/pgdata/data "
        "timescale/timescaledb-ha:pg16"
    )
    assert _es_residente(como_estaba)
    assert _cota_del_run(como_estaba) == (None, None), (
        "el detector de cota encuentra una donde no la hay: no serviría para cazar nada"
    )
    # Y el contrario: con la cota puesta, no salta.
    con_cota = como_estaba.replace(
        "--restart unless-stopped",
        "--restart unless-stopped --log-opt max-size=10m --log-opt max-file=3",
    )
    assert _cota_del_run(con_cota) == ("10m", "3")
