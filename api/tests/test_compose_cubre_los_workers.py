"""[T-7.01 · T-3.11.c] Todo módulo ejecutable de `takab_api` tiene quien lo corra.

El defecto que cierra: `python -m takab_api.backfill` existía, se decía a sí mismo
«corre CO-LOCADO con los demás workers desde la MISMA imagen», `deploy.sh` le
exportaba sus dos colas (`TAKAB_API_QUEUE_URL_BACKFILL` / `_DLQ_URL_BACKFILL`)…
y ningún servicio de `deploy/cloud/docker-compose.yml` lo arrancaba. `git log -S
backfill` sobre ese fichero no devuelve nada: no se quitó, **nunca estuvo**.
Medido contra la nube el 2026-09-11: 42 mensajes en `takab-dev-q-backfill` y 0 en
su DLQ — nadie los recibe, así que no agotan el `maxReceiveCount`; envejecen y
expiran, y la alarma `dlq_depth` no ve una ausencia. Entorno preparado para un
proceso que nadie arranca, que es justo lo que hace creíble lo contrario.

Aquí NO se lee una lista escrita a mano. Los módulos ejecutables se DERIVAN del
árbol (`__main__.py` y guardas `if __name__ == "__main__"`), los servicios se
derivan del compose —con el `ENTRYPOINT` de la imagen como default, leído del
Dockerfile y no recordado—, y cada módulo tiene que estar en un lado o en el
otro: o un servicio lo corre, o figura en `NO_RESIDENTES` con su razón escrita.
La tercera opción —no estar en ninguno— es exactamente cómo llegó `backfill` y
cómo estuvo a punto de llegar la cola del CCTV.

La segunda regla es la que pidió la ficha: *toda cola que `deploy.sh` exporta como
`TAKAB_API_QUEUE_URL_*` tiene un servicio que la consume*. Escrita así caza
también la próxima cola que se añada, que es como llegó ésta.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover — el fallback textual de abajo lo cubre
    yaml = None

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "api" / "src" / "takab_api"
DOCKERFILE = REPO / "api" / "Dockerfile"
COMPOSE = REPO / "deploy" / "cloud" / "docker-compose.yml"
DEPLOY = REPO / "deploy" / "cloud" / "deploy.sh"

#: Módulos ejecutables que, A PROPÓSITO, no son un servicio residente del compose.
#: Cada entrada lleva su razón y, cuando alguien SÍ los programa, la ruta del fichero
#: que lo hace (se comprueba que existe y que nombra al módulo: una cita que se pudre
#: pone esto en rojo). `None` significa «hoy no lo programa nadie», y se dice así.
NO_RESIDENTES: dict[str, tuple[str, str | None]] = {
    "takab_api.billing": (
        "Pasada ONE-SHOT (`--day`), no un worker: en dev la lanza `make billing`; en AWS "
        "el programador (EventBridge→run-task) sigue siendo un TODO en su propio docstring.",
        "Makefile",
    ),
    "takab_api.ops.prune_pii": (
        "Cron diario que instala Terraform en la instancia (asociación SSM `prune_pii`), "
        "no un proceso residente.",
        "infra/terraform/modules/database/prune_pii_setup.sh.tpl",
    ),
    "takab_api.ops.restore_check": (
        "Corre dentro del respaldo nocturno que instala Terraform (`--save-baseline` sobre "
        "el mismo snapshot que el dump), no un proceso residente.",
        "infra/terraform/modules/database/backup_setup.sh.tpl",
    ),
    "takab_api.ops.prune_cctv": (
        "SIN PROGRAMADOR CONOCIDO (medido con grep sobre *.tf/*.tpl/*.sh/Makefile el "
        "2026-09-11): T-3.10 lo dejó invocable y nadie lo llama. Es una poda, no un worker, "
        "así que no pertenece al compose; la ficha que lo programe está por abrir.",
        None,
    ),
    "takab_api.ops.oncall": (
        "Herramienta de operador (acuñar/listar/revocar credenciales de guardia): se ejecuta "
        "A MANO y enseña el secreto una sola vez. Un residente aquí no tendría sentido.",
        None,
    ),
    "takab_api.ops.restore_drill": (
        "Ensayo LOCAL de restore (`make restore-drill`): crea su propia instancia y mide el "
        "RTO. No corre en la nube.",
        "Makefile",
    ),
}

_GUARDA_MAIN = re.compile(r'^if __name__ == ["\']__main__["\']:', re.M)


# ---------------------------------------------------------------------------
# Derivaciones: del árbol, del Dockerfile, del compose y del despliegue
# ---------------------------------------------------------------------------


def _modulo_de(ruta: Path) -> str:
    """`api/src/takab_api/ops/oncall.py` → `takab_api.ops.oncall`."""
    rel = ruta.relative_to(SRC.parent).with_suffix("")
    partes = list(rel.parts)
    if partes[-1] == "__main__":
        partes.pop()
    return ".".join(partes)


def _modulos_ejecutables() -> dict[str, Path]:
    """Todo lo que se puede lanzar con `python -m`, derivado del árbol."""
    hallados: dict[str, Path] = {}
    for ruta in sorted(SRC.rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        if ruta.name == "__main__.py" or _GUARDA_MAIN.search(ruta.read_text(encoding="utf-8")):
            hallados[_modulo_de(ruta)] = ruta
    return hallados


def _entrypoint_de_la_imagen() -> list[str]:
    """El `ENTRYPOINT` del Dockerfile: lo que corre un servicio que no declara el suyo."""
    m = re.search(r"^ENTRYPOINT\s+(\[.*\])\s*$", DOCKERFILE.read_text(encoding="utf-8"), re.M)
    assert m is not None, f"{DOCKERFILE} ya no declara un ENTRYPOINT en forma exec"
    return json.loads(m.group(1))


def _como_lista(valor: object) -> list[str]:
    if valor is None:
        return []
    if isinstance(valor, str):
        return valor.split()
    return [str(v) for v in valor]


def _servicios_por_yaml() -> dict[str, dict]:
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return {nombre: (spec or {}) for nombre, spec in doc["services"].items()}


def _servicios_por_texto() -> dict[str, dict]:
    """Fallback sin PyYAML: lee el compose por su sangría. Robusto a lo que hay hoy
    (arrays JSON inline, listas `- item`, anclas `x-…: &a` fusionadas con `<<: *a`),
    no a cualquier YAML."""
    anclas: dict[str, dict] = {}
    servicios: dict[str, dict] = {}
    actual: dict | None = None
    clave_lista: str | None = None
    en_services = False
    for linea in COMPOSE.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\S", linea):
            en_services = linea.startswith("services:")
            m = re.match(r"^x-[\w-]+:\s*&([\w-]+)\s*$", linea)
            actual = anclas.setdefault(m.group(1), {}) if m else None
            clave_lista = None
            continue
        if actual is not None and not en_services:
            m = re.match(r"^  ([A-Za-z_]+):\s*(\S.*)$", linea)
            if m:
                actual[m.group(1)] = m.group(2).strip()
            continue
        if not en_services:
            continue
        m = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", linea)
        if m:
            actual = servicios.setdefault(m.group(1), {})
            clave_lista = None
            continue
        if actual is None:
            continue
        m = re.match(r"^    <<:\s*\*([\w-]+)\s*$", linea)
        if m:
            actual.update(anclas.get(m.group(1), {}))
            continue
        m = re.match(r"^    ([A-Za-z_]+):\s*(.*)$", linea)
        if m:
            clave, valor = m.group(1), m.group(2).strip()
            if valor.startswith("["):
                actual[clave] = json.loads(valor)
                clave_lista = None
            elif valor == "":
                actual[clave] = []
                clave_lista = clave
            else:
                actual[clave] = valor
                clave_lista = None
            continue
        m = re.match(r"^      - (.+)$", linea)
        if m and clave_lista is not None:
            actual[clave_lista].append(m.group(1).strip())
    return servicios


def _servicios() -> dict[str, dict]:
    return _servicios_por_yaml() if yaml is not None else _servicios_por_texto()


def _variable_de_la_imagen_api() -> str:
    """`TAKAB_CLOUD_IMAGE`, derivada: la variable a la que deploy.sh asigna la imagen
    construida de `api/Dockerfile` (`…/takab/cloud:<tag>`)."""
    m = re.search(r"^(TAKAB_[A-Z_]+)=\S*/takab/cloud:", DEPLOY.read_text(encoding="utf-8"), re.M)
    assert m is not None, "deploy.sh ya no asigna `…/takab/cloud:<tag>` a ninguna variable"
    return m.group(1)


def _es_imagen_api(spec: dict) -> bool:
    return f"${{{_variable_de_la_imagen_api()}" in str(spec.get("image", ""))


def _argv(spec: dict, entrypoint_imagen: list[str]) -> list[str]:
    """Lo que ejecuta el contenedor: su `entrypoint` o, si no declara uno y corre la
    imagen del api, el `ENTRYPOINT` del Dockerfile; más su `command`. Un servicio de
    otra imagen (Caddy) sin entrypoint no hereda nada: no sabemos qué corre."""
    if "entrypoint" in spec:
        entrypoint = _como_lista(spec["entrypoint"])
    elif _es_imagen_api(spec):
        entrypoint = entrypoint_imagen
    else:
        entrypoint = []
    return entrypoint + _como_lista(spec.get("command"))


def _modulo_que_corre(argv: list[str]) -> str | None:
    """`python -m takab_api.X …` → `takab_api.X`; `uvicorn …` / Caddy → None."""
    for i, tok in enumerate(argv[:-1]):
        if tok == "-m" and argv[i + 1].startswith("takab_api."):
            return argv[i + 1]
    return None


def _modulos_por_servicio() -> dict[str, str]:
    imagen = _entrypoint_de_la_imagen()
    resultado: dict[str, str] = {}
    for nombre, spec in _servicios().items():
        modulo = _modulo_que_corre(_argv(spec, imagen))
        if modulo is not None:
            resultado[nombre] = modulo
    return resultado


def _colas_exportadas() -> set[str]:
    """Las `TAKAB_API_QUEUE_URL_<X>=` del heredoc de deploy.sh, en minúsculas."""
    texto = DEPLOY.read_text(encoding="utf-8")
    return {m.lower() for m in re.findall(r"^TAKAB_API_QUEUE_URL_([A-Z0-9]+)=", texto, re.M)}


def _dlqs_exportadas() -> set[str]:
    texto = DEPLOY.read_text(encoding="utf-8")
    return {m.lower() for m in re.findall(r"^TAKAB_API_DLQ_URL_([A-Z0-9]+)=", texto, re.M)}


def _fuentes_del_modulo(modulo: str) -> str:
    """El código del módulo: el paquete entero si es `pkg/__main__.py`, el fichero si no."""
    ruta = SRC.parent.joinpath(*modulo.split("."))
    if ruta.is_dir():
        return "\n".join(p.read_text(encoding="utf-8") for p in sorted(ruta.rglob("*.py")))
    return ruta.with_suffix(".py").read_text(encoding="utf-8")


def _colas_que_consume(servicio: str, spec: dict, imagen: list[str]) -> set[str]:
    """Qué cola atiende un servicio, derivado: `--queue=X` si lo lleva; si no, las
    `settings.queue_url_<x>` que lee el código del módulo que corre."""
    argv = _argv(spec, imagen)
    modulo = _modulo_que_corre(argv)
    if modulo is None:
        return set()
    for i, tok in enumerate(argv):
        if tok.startswith("--queue="):
            return {tok.split("=", 1)[1]}
        if tok == "--queue" and i + 1 < len(argv):
            return {argv[i + 1]}
    return set(re.findall(r"\bqueue_url_([a-z0-9]+)\b", _fuentes_del_modulo(modulo)))


# ---------------------------------------------------------------------------
# El censo no puede estar vacío (un regex roto pasaría por ausencia)
# ---------------------------------------------------------------------------


def test_el_censo_no_esta_vacio() -> None:
    """Si un cambio de nombre o de patrón dejara de encontrar módulos o servicios, los
    tests de abajo pasarían POR VACÍO. Los mínimos son lo que hay hoy con margen: seis
    `__main__.py` + cinco `ops/*.py`, siete servicios, tres colas."""
    assert len(_modulos_ejecutables()) >= 5, "el derivador de módulos ejecutables no ve nada"
    assert len(_servicios()) >= 6, "el lector del compose no ve los servicios"
    de_la_imagen_api = [n for n, spec in _servicios().items() if _es_imagen_api(spec)]
    assert len(de_la_imagen_api) >= 5, (
        f"solo {de_la_imagen_api} corren la imagen del api: o cambió la variable de la imagen "
        "en deploy.sh o el lector del compose no fusiona las anclas"
    )
    assert len(_colas_exportadas()) >= 3, "el heredoc de deploy.sh ya no exporta colas"
    assert _entrypoint_de_la_imagen()[:2] == ["python", "-m"], (
        "el ENTRYPOINT de la imagen ya no es `python -m …`: los servicios sin entrypoint "
        "propio (ingest-*) correrían otra cosa y esta derivación dejaría de valer"
    )


# ---------------------------------------------------------------------------
# Regla 1: cada módulo ejecutable, o lo corre un servicio o tiene razón escrita
# ---------------------------------------------------------------------------


def test_todo_modulo_ejecutable_tiene_servicio_o_razon_escrita() -> None:
    """EL CASO DE `takab_api.backfill` (T-3.11.c), cazado por construcción.

    Un módulo que se puede lanzar con `python -m`, que no arranca ningún servicio del
    compose y que tampoco figura en `NO_RESIDENTES` es un proceso que el repo cree
    que corre y la nube no conoce. Que se añada un servicio o se escriba la razón.
    """
    modulos = set(_modulos_ejecutables())
    residentes = set(_modulos_por_servicio().values())
    huerfanos = sorted(modulos - residentes - set(NO_RESIDENTES))
    assert not huerfanos, (
        f"módulos ejecutables SIN servicio en deploy/cloud/docker-compose.yml y SIN razón "
        f"en NO_RESIDENTES: {huerfanos}. O se añade un servicio que los corra (misma imagen, "
        "`entrypoint: [python, -m, <módulo>]`, `db-ingest.env` si escribe de todos los "
        "tenants), o se escribe aquí por qué no residen."
    )


def test_ninguna_razon_de_no_residente_esta_podrida() -> None:
    """Una lista escrita a mano se pudre por dos puertas, y las dos se cierran aquí:
    la entrada cuyo módulo ya no existe (o ya lo corre un servicio: sobra), y la cita a
    un fichero que ya no lo programa."""
    modulos = set(_modulos_ejecutables())
    residentes = set(_modulos_por_servicio().values())

    inexistentes = sorted(set(NO_RESIDENTES) - modulos)
    assert not inexistentes, f"NO_RESIDENTES nombra módulos que ya no existen: {inexistentes}"

    ya_residen = sorted(set(NO_RESIDENTES) & residentes)
    assert not ya_residen, (
        f"{ya_residen} ya tienen servicio en el compose: la entrada de NO_RESIDENTES sobra y, "
        "de quedarse, autorizaría en silencio a quitarles el servicio"
    )

    for modulo, (razon, evidencia) in NO_RESIDENTES.items():
        assert len(razon) > 40, f"la razón de {modulo} no explica nada: {razon!r}"
        if evidencia is None:
            assert "SIN PROGRAMADOR" in razon or "A MANO" in razon or "LOCAL" in razon, (
                f"{modulo} no cita quién lo programa y su razón no lo confiesa"
            )
            continue
        fichero = REPO / evidencia
        assert fichero.exists(), f"{modulo} cita {evidencia}, que ya no existe"
        assert modulo in fichero.read_text(encoding="utf-8"), (
            f"{modulo} cita {evidencia} como su programador, y ese fichero ya no lo nombra"
        )


# ---------------------------------------------------------------------------
# Regla 2: toda cola que el despliegue exporta tiene consumidor
# ---------------------------------------------------------------------------


def test_toda_cola_exportada_por_el_despliegue_tiene_consumidor() -> None:
    """La regla que pidió T-3.11.c, escrita para la PRÓXIMA cola y no solo para ésta.

    `deploy.sh` exportaba `TAKAB_API_QUEUE_URL_BACKFILL` desde T-1.38 y nadie la leía:
    los mensajes envejecen sin tocar la DLQ, así que la alarma `dlq_depth` calla. Un
    entorno que exporta una cola sin consumidor no está «preparado»: está mintiendo.
    """
    imagen = _entrypoint_de_la_imagen()
    consumidas: dict[str, set[str]] = {}
    for nombre, spec in _servicios().items():
        for cola in _colas_que_consume(nombre, spec, imagen):
            consumidas.setdefault(cola, set()).add(nombre)

    sin_consumidor = sorted(_colas_exportadas() - set(consumidas))
    assert not sin_consumidor, (
        f"deploy.sh exporta TAKAB_API_QUEUE_URL_{[c.upper() for c in sin_consumidor]} y ningún "
        f"servicio del compose las consume. Consumidores hoy: "
        f"{ {c: sorted(s) for c, s in sorted(consumidas.items())} }. Un mensaje en esas colas "
        "envejece y expira sin llegar a la DLQ: ninguna alarma lo verá."
    )


def test_toda_cola_exportada_lleva_su_dlq() -> None:
    """GAP-1 (T-1.38): los consumidores EXIGEN la URL de su DLQ al arrancar (`SystemExit`).
    Exportar la cola sin la DLQ es un servicio que arranca y muere en bucle."""
    sin_dlq = sorted(_colas_exportadas() - _dlqs_exportadas())
    assert not sin_dlq, f"colas exportadas sin TAKAB_API_DLQ_URL_*: {sin_dlq}"


# ---------------------------------------------------------------------------
# Invariantes del compose que el fallo de backfill habría podido saltarse
# ---------------------------------------------------------------------------


def test_los_workers_escriben_con_el_dsn_de_ingesta_y_la_api_con_el_suyo() -> None:
    """El invariante de tenancy que el propio compose declara en su cabecera, MEDIDO.

    Los workers escriben filas de todos los tenants: con el DSN de `takab_app` (RLS
    forzada) la política se lo negaría —el backfill fallaría en silencio en cada
    inserción—; la API con el de `takab_ingest` (BYPASSRLS) serviría datos ajenos sin
    que nada la detuviera. Por eso son dos `env_file` y no uno con override.
    """
    imagen = _entrypoint_de_la_imagen()
    for nombre, spec in _servicios().items():
        env_files = [Path(p).name for p in _como_lista(spec.get("env_file"))]
        if _modulo_que_corre(_argv(spec, imagen)) is not None:
            assert "db-ingest.env" in env_files and "db-app.env" not in env_files, (
                f"el servicio {nombre} corre un worker con {env_files}: los workers van con "
                "db-ingest.env (BYPASSRLS), nunca con db-app.env"
            )
        elif "uvicorn" in _argv(spec, imagen):
            assert "db-app.env" in env_files and "db-ingest.env" not in env_files, (
                f"la API ({nombre}) va con {env_files}: tiene que ser db-app.env (RLS forzada)"
            )


def test_los_contenedores_legado_que_borra_el_despliegue_no_son_los_de_compose() -> None:
    """`deploy.sh` hace `docker rm -f` de los workers ad-hoc del smoke de 2026-07-08
    (`takab-worker-*`). Si uno de esos nombres coincidiera con el contenedor que compose
    crea para un servicio (`<name>-<servicio>-1`), cada despliegue mataría al worker
    recién levantado —y `docker compose ps` lo enseñaría reiniciándose, en verde—.
    Se deriva del `name:` del compose, que por eso tiene que estar declarado."""
    texto_compose = COMPOSE.read_text(encoding="utf-8")
    m = re.search(r"^name:\s*(\S+)\s*$", texto_compose, re.M)
    assert m is not None, (
        "el compose ya no declara `name:`; el nombre de los contenedores es imprevisible"
    )
    proyecto = m.group(1)
    de_compose = {f"{proyecto}-{svc}-1" for svc in _servicios()}

    legado: set[str] = set()
    for linea in DEPLOY.read_text(encoding="utf-8").splitlines():
        mm = re.match(r"^\s*docker rm -f (.+?)(?:\s+2>|\s*\|\||\s*$)", linea)
        if mm:
            legado |= set(mm.group(1).split())
    assert legado, (
        "deploy.sh ya no borra los workers legado: revisa que este test siga mirando algo"
    )
    choque = sorted(legado & de_compose)
    assert not choque, f"deploy.sh borraría contenedores que compose acaba de crear: {choque}"


@pytest.mark.parametrize("modulo", sorted(NO_RESIDENTES))
def test_cada_no_residente_sigue_siendo_ejecutable(modulo: str) -> None:
    """Parametrizado para que el nombre del módulo salga en el informe de pytest."""
    assert modulo in _modulos_ejecutables()


@pytest.mark.skipif(yaml is None, reason="sin PyYAML solo existe el lector textual")
def test_el_lector_textual_dice_lo_mismo_que_pyyaml() -> None:
    """PyYAML llega a este entorno de forma TRANSITIVA (nadie lo declara en
    `api/pyproject.toml`): el día que desaparezca, el censo caería al lector textual
    sin avisar. Que los dos vean los mismos servicios, el mismo argv y los mismos
    `env_file`, o el fallback sería OTRO censo con el mismo nombre."""
    imagen = _entrypoint_de_la_imagen()
    por_yaml, por_texto = _servicios_por_yaml(), _servicios_por_texto()
    assert set(por_yaml) == set(por_texto)
    for nombre, spec in por_yaml.items():
        otro = por_texto[nombre]
        assert _argv(spec, imagen) == _argv(otro, imagen), nombre
        assert _como_lista(spec.get("env_file")) == _como_lista(otro.get("env_file")), nombre
        assert _es_imagen_api(spec) == _es_imagen_api(otro), nombre
