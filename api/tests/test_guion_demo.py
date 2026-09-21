"""[T-7.07] El guion de la demostración, comprobado por CONDUCTA.

Aquí no se lee `deploy/demo/guion.sh`: se **corre** contra un panel de mentira y
la base de pruebas, porque lo único que importa de un preflight es su código de
salida — y lo que tiene que cazar son estados que, puestos, hacen que la
demostración falle **sin dar un error a la vista**:

* el **modo prueba del WR-1 armado**: el pulso queda en un ensayo local, no
  publica a la nube, y la consola sigue en reposo como si el radio no existiera;
* el **modo demostración encendido** (`D-27`): suprime los comandos firmados y
  los avisos, y todo contesta `201` igual;
* un **destinatario ajeno** en la cascada: el correo dice «ALERTA SÍSMICA» y no
  lleva la palabra simulacro en el asunto;
* un **teléfono sin token**: el acto 3 se queda sin la mitad que el cliente mira.

Las costuras del guion (`TAKAB_DEMO_PANEL_URL`, `TAKAB_DEMO_DSN`, …) existen
para esto y para poder correrlo desde una red que no es la del gabinete.

⚠️ Estas filas se **comitean** (el guion es otro proceso y no vería una
transacción abierta), así que el fixture las borra él mismo en orden de FK. El
`TRUNCATE` del conftest es por SESIÓN y no limpia entre tests.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import psycopg
import pytest

REPO = Path(__file__).resolve().parents[2]
GUION = REPO / "deploy" / "demo" / "guion.sh"

#: Prefijo 7e19 — libre en la suite (el 7e18 lo usa el sembrador de staging).
TENANT_D = "7e190000-0000-0000-0000-0000000000a1"
SITIO_D = "7e190000-0000-0000-0000-00000000015d"
ZONA_D = "7e190000-0000-0000-0000-0000000000e1"

#: Panel sano: el estado real del gabinete el 2026-09-12, recortado a lo que el
#: preflight mira. Cada test lo deforma en UN campo, que es la única forma de
#: afirmar que cada ✗ sale por su motivo y no por otro.
PANEL_SANO: dict = {
    "test_mode": {"active": False, "remaining_s": 0.0},
    "alert_latched": False,
    "sasmex_active": False,
    "drill": {"active": False},
    "audio": {"enabled": False},
    "cloud": {"online": True, "admin_state": "active", "mqtt_rtt_ms": 75.6, "queued": 0},
    "relays": [
        {"channel": "siren", "energized": False, "activated": False},
        {"channel": "gas", "energized": False, "activated": False},
    ],
    "relays_status": {"reason": "ok"},
    "latencies": {"reflex_s": None, "reflex_budget_s": 0.1},
}

HERRAMIENTAS = ("psql", "jq", "curl")


def _dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
    )
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(scope="module", autouse=True)
def _hay_herramientas() -> None:
    """Sin `psql`/`jq`/`curl` el guion no puede correr, y un SKIP no es un PASS.

    Se declara aquí y no en cada test para que el motivo salga UNA vez y diga
    qué instalar, en vez de once fallos de «command not found».
    """
    faltan = [h for h in HERRAMIENTAS if shutil.which(h) is None]
    assert not faltan, (
        f"el guion de la demostración necesita {faltan} y no están en el PATH.\n"
        "  En Debian/Ubuntu: apt-get install -y postgresql-client jq curl"
    )


class _Mano(BaseHTTPRequestHandler):
    cuerpo: dict = {}

    def do_GET(self) -> None:  # noqa: N802 — lo fija BaseHTTPRequestHandler
        if self.path != "/api/status":
            self.send_error(404)
            return
        crudo = json.dumps(self.cuerpo).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def log_message(self, *_: object) -> None:
        """Sin ruido: el servidor de mentira no tiene nada que contar."""


@pytest.fixture
def panel() -> Iterator[tuple[str, type[_Mano]]]:
    """Un panel de gabinete de mentira, con su estado mutable por test."""

    class Mano(_Mano):
        cuerpo = json.loads(json.dumps(PANEL_SANO))

    servidor = HTTPServer(("127.0.0.1", 0), Mano)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_port}", Mano
    finally:
        servidor.shutdown()
        servidor.server_close()


@pytest.fixture
def adb_falso(tmp_path: Path) -> Path:
    """Un `adb` que dice que el Pixel está y la app instalada."""
    ruta = tmp_path / "adb"
    ruta.write_text(
        "#!/usr/bin/env bash\n"
        'case "$1" in\n'
        "get-state) echo device ;;\n"
        "shell) echo 'package:com.takab.ailert' ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ruta.chmod(0o755)
    return ruta


@pytest.fixture
def sitio_demo() -> Iterator[psycopg.Connection]:
    """Tenant, sitio, cascada PROPIA y un teléfono enrolado. Comiteados."""
    c = psycopg.connect(_dsn(), autocommit=True)
    c.execute(
        "INSERT INTO tenants (tenant_id, code, name, visibility) "
        "VALUES (%s,'DEMO','Tenant demo','private') ON CONFLICT DO NOTHING",
        (TENANT_D,),
    )
    c.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s,%s,'S-DEMO','Sitio de la demostración', "
        "ST_SetSRID(ST_MakePoint(-98.2063, 19.0414), 4326)::geography) ON CONFLICT DO NOTHING",
        (SITIO_D, TENANT_D),
    )
    c.execute(
        "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, is_active, config) "
        "VALUES (%s,'site',%s,1,true,%s::jsonb)",
        (
            TENANT_D,
            SITIO_D,
            json.dumps(
                {"notifications": {"email": {"to": ["operaciones@takabailert.com"]}}},
            ),
        ),
    )
    c.execute(
        "INSERT INTO push_tokens (tenant_id, user_sub, platform, token, site_id) "
        "VALUES (%s, gen_random_uuid(), 'android', 'tok-demo-guion', %s)",
        (TENANT_D, SITIO_D),
    )
    try:
        yield c
    finally:
        for sql in (
            "DELETE FROM notification_jobs WHERE tenant_id = %s",
            "DELETE FROM incident_actions WHERE tenant_id = %s",
            "DELETE FROM incidents WHERE tenant_id = %s",
            "DELETE FROM push_tokens WHERE tenant_id = %s",
            "DELETE FROM rule_sets WHERE tenant_id = %s",
            "DELETE FROM demo_mode WHERE tenant_id = %s",
            "DELETE FROM user_zone_assignments WHERE tenant_id = %s",
            "DELETE FROM zones WHERE tenant_id = %s",
            "DELETE FROM sites WHERE tenant_id = %s",
            "DELETE FROM tenants WHERE tenant_id = %s",
        ):
            c.execute(sql, (TENANT_D,))
        c.close()


def correr(accion: str, panel_url: str, adb: Path, **extra: str) -> subprocess.CompletedProcess:
    entorno = {
        **os.environ,
        "TAKAB_DEMO_PANEL_URL": panel_url,
        "TAKAB_DEMO_DSN": _dsn(),
        "TAKAB_DEMO_SITE": SITIO_D,
        "TAKAB_DEMO_TENANT": TENANT_D,
        "TAKAB_DEMO_ADB": str(adb),
        "TAKAB_DEMO_ESPERA_S": "1",
        **extra,
    }
    return subprocess.run(
        ["bash", str(GUION), accion], capture_output=True, text=True, env=entorno, timeout=120
    )


# ------------------------------------------------------------------ preflight


def test_con_todo_en_orden_el_preflight_deja_tocar_el_radio(sitio_demo, panel, adb_falso) -> None:
    url, _ = panel
    r = correr("--preflight", url, adb_falso)
    assert r.returncode == 0, f"el preflight falló con todo sano:\n{r.stdout}\n{r.stderr}"
    assert "modo prueba del WR-1 DESARMADO" in r.stdout
    # El resumen SIEMPRE nombra el símbolo («0 ✗»): lo que no puede haber es una
    # línea marcada con él.
    assert "0 ✗" in r.stdout, r.stdout


def test_el_modo_prueba_ARMADO_para_la_demostracion(sitio_demo, panel, adb_falso) -> None:
    """El defecto más caro de los cuatro: el pulso no sale del gabinete.

    Con el modo prueba puesto, el WR-1 se ejercita SIN publicar a la nube. El
    operador oye la sirena, da por buena la demostración, y en la consola no hay
    incidente, en el teléfono no hay aviso y nadie sabe por qué.
    """
    url, mano = panel
    mano.cuerpo["test_mode"] = {"active": True, "remaining_s": 180.0}
    r = correr("--preflight", url, adb_falso)
    assert r.returncode != 0
    assert "modo prueba del WR-1 ARMADO" in r.stdout
    assert "NO publica a la nube" in r.stdout


def test_el_modo_demostracion_encendido_para_la_demostracion(sitio_demo, panel, adb_falso) -> None:
    """`D-27` suprime en silencio: el 201 llega igual y no se mueve nada."""
    url, _ = panel
    sitio_demo.execute(
        "INSERT INTO demo_mode (tenant_id, enabled_by, expires_at, note) "
        "VALUES (%s, gen_random_uuid(), now() + interval '1 hour', 'prueba')",
        (TENANT_D,),
    )
    r = correr("--preflight", url, adb_falso)
    assert r.returncode != 0
    assert "modo demostración ENCENDIDO" in r.stdout


def test_un_destinatario_AJENO_para_la_demostracion(sitio_demo, panel, adb_falso) -> None:
    """La cascada de una demostración no puede escribirle a un tercero."""
    url, _ = panel
    sitio_demo.execute(
        "UPDATE rule_sets SET config = %s::jsonb WHERE scope_id = %s",
        (
            json.dumps({"notifications": {"email": {"to": ["director@hospital-ajeno.mx"]}}}),
            SITIO_D,
        ),
    )
    r = correr("--preflight", url, adb_falso)
    assert r.returncode != 0
    assert "le escribiría a terceros" in r.stdout
    assert "director@hospital-ajeno.mx" in r.stdout


def test_la_cascada_del_CLIENTE_cuenta_aunque_el_sitio_no_tenga_la_suya(
    sitio_demo, panel, adb_falso
) -> None:
    """El control que hace honesto al anterior: el `rule_set` que rige puede no
    ser el del sitio. Mirando solo `scope_id = sitio`, un tenant con la cascada
    puesta arriba pasaría como «no le escribe a nadie» justo cuando escribe a
    todos — que es el modo de fallar más caro de esta comprobación."""
    url, _ = panel
    sitio_demo.execute("DELETE FROM rule_sets WHERE scope_id = %s", (SITIO_D,))
    sitio_demo.execute(
        "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, is_active, config) "
        "VALUES (%s,'tenant',%s,1,true,%s::jsonb)",
        (
            TENANT_D,
            TENANT_D,
            json.dumps({"notifications": {"email": {"to": ["director@hospital-ajeno.mx"]}}}),
        ),
    )
    r = correr("--preflight", url, adb_falso)
    assert r.returncode != 0
    assert "director@hospital-ajeno.mx" in r.stdout


def test_sin_token_de_push_el_preflight_lo_dice(sitio_demo, panel, adb_falso) -> None:
    url, _ = panel
    sitio_demo.execute("DELETE FROM push_tokens WHERE tenant_id = %s", (TENANT_D,))
    r = correr("--preflight", url, adb_falso)
    assert r.returncode != 0
    assert "ningún token de push" in r.stdout


def test_un_enclavado_vivo_para_la_demostracion(sitio_demo, panel, adb_falso) -> None:
    """Enganchado de la prueba anterior, el acto 3 no se distingue del acto 2."""
    url, mano = panel
    mano.cuerpo["alert_latched"] = True
    r = correr("--preflight", url, adb_falso)
    assert r.returncode != 0
    assert "enclavado vivo" in r.stdout


def test_sin_telefono_por_USB_no_hay_acto_3_que_ensenar(sitio_demo, panel, tmp_path) -> None:
    adb_mudo = tmp_path / "adb-mudo"
    adb_mudo.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    adb_mudo.chmod(0o755)
    url, _ = panel
    r = correr("--preflight", url, adb_mudo)
    assert r.returncode != 0
    assert "el Pixel no está por USB" in r.stdout


# ---------------------------------------------------------------------- check


def test_el_check_falla_si_el_pulso_no_produce_incidente(sitio_demo, panel, adb_falso) -> None:
    url, _ = panel
    r = correr("--check", url, adb_falso)
    assert r.returncode != 0
    assert "no llegó ningún incidente 'sasmex'" in r.stdout


def test_el_check_ve_el_incidente_del_pulso_y_la_fase_de_la_app(
    sitio_demo, panel, adb_falso, tmp_path
) -> None:
    """Y la fase la deriva con la MISMA consulta que el sembrador, que a su vez
    está atada al endpoint real por `test_seed_staging_incident.py`."""
    url, mano = panel
    mano.cuerpo["relays"][0]["activated"] = True
    mano.cuerpo["latencies"]["reflex_s"] = 0.0042
    sitio_demo.execute(
        "INSERT INTO incidents "
        "(tenant_id, site_id, event_uuid, trigger, severity, state, opened_at) "
        "VALUES (%s, %s, gen_random_uuid(), 'sasmex', 'critical', 'open', now())",
        (TENANT_D, SITIO_D),
    )
    r = correr(
        "--check",
        url,
        adb_falso,
        TAKAB_DEMO_DESDE="2000-01-01T00:00:00Z",
        TAKAB_DEMO_ULTIMO=str(tmp_path / "ultimo"),
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "incidente sasmex" in r.stdout
    assert "phase=alert_active" in r.stdout
    assert "relés accionados: siren" in r.stdout
    assert "acta del reflejo con latencia 0.0042s" in r.stdout
    assert (tmp_path / "ultimo").read_text().strip()


def test_un_incidente_VIEJO_no_cuenta_como_el_pulso_de_hoy(sitio_demo, panel, adb_falso) -> None:
    """Sin esta frontera, `--check` daría verde con el incidente de ayer y la
    demostración se creería acreditada sin que el radio hubiera hecho nada."""
    url, _ = panel
    sitio_demo.execute(
        "INSERT INTO incidents "
        "(tenant_id, site_id, event_uuid, trigger, severity, state, opened_at) "
        "VALUES (%s, %s, gen_random_uuid(), 'sasmex', 'critical', 'open', "
        "now() - interval '2 days')",
        (TENANT_D, SITIO_D),
    )
    r = correr("--check", url, adb_falso)
    assert r.returncode != 0
    assert "no llegó ningún incidente 'sasmex'" in r.stdout


def test_un_argumento_desconocido_no_hace_nada_y_lo_dice(panel, adb_falso) -> None:
    url, _ = panel
    r = correr("--despliega-todo", url, adb_falso)
    assert r.returncode == 2
    assert "uso:" in r.stderr


# ------------------------------------------------------- ensayo general (--full)
#
# [T-7.28] `--full` es un CRONÓMETRO y un director de escena: recorre los actos,
# mide cuánto dura cada uno y le pregunta a la máquina si pasó lo que el acto
# promete. Lo que se prueba aquí es su CONDUCTA, no su texto — salvo en dos
# sitios donde el texto ES la función: la declaración del reloj y el aviso de que
# una corrida sin pausas no es un ensayo. Los dos existen para que una tabla no
# se pueda pegar en el Registro afirmando algo que no ocurrió.


def _full(panel_url: str, adb: Path, **extra: str) -> subprocess.CompletedProcess:
    """`--full` sin esperar a nadie. Sin esta costura no se puede probar."""
    return correr("--full", panel_url, adb, TAKAB_DEMO_SIN_PAUSA="1", **extra)


def test_el_ensayo_recorre_los_cuatro_actos_y_saca_la_tabla_del_registro(
    sitio_demo, panel, adb_falso
) -> None:
    url, _ = panel
    r = _full(url, adb_falso)
    # Los cinco encabezados de acto, en orden y todos: un ensayo que se queda a
    # medias sin decirlo es peor que uno que falla.
    for acto in (
        "0 · Preflight",
        "1 · El SOC",
        "2 · Movimiento aislado",
        "3 · El pulso",
        "4 · Después",
    ):
        assert acto in r.stdout, f"falta el acto «{acto}»\n{r.stdout}"
    assert "REGISTRO · pega esto" in r.stdout
    assert "| Acto | Duración | Veredicto |" in r.stdout


def test_si_el_preflight_esta_en_rojo_el_ensayo_ABORTA_y_NO_manda_pulsar_el_radio(
    sitio_demo, panel, adb_falso
) -> None:
    """La que de verdad protege la demostración.

    Con el modo prueba del WR-1 armado, el pulso no publica a la nube. Si el
    ensayo siguiera adelante, le diría a quien conduce «pulsa el WR-1 AHORA» y el
    acto 3 fallaría **delante del cliente** sin un error a la vista, que es
    exactamente el fallo que este fichero entero existe para cazar.
    """
    url, mano = panel
    # `cuerpo`, no `estado`: es el nombre que lee `_Mano.do_GET`. Con el nombre
    # equivocado el panel se queda SANO y esta prueba pasa a verde sin probar nada.
    mano.cuerpo["test_mode"] = {"active": True, "remaining_s": 420.0}
    r = _full(url, adb_falso)
    assert r.returncode != 0
    assert "ENSAYO ABORTADO en el preflight" in r.stdout
    assert "pulsa el WR-1" not in r.stdout, "mandó tocar el radio con el preflight en rojo"
    # Y aun abortando deja el Registro: dónde murió el ensayo es la evidencia.
    assert "REGISTRO · pega esto" in r.stdout
    assert "0 · Preflight" in r.stdout


def test_la_tabla_DECLARA_de_que_reloj_son_los_tiempos(sitio_demo, panel, adb_falso) -> None:
    """El Registro ya guarda latencias MEDIDAS POR EL SISTEMA —el acta del reflejo,
    4,96 ms sobre 100 de presupuesto—. Estas duraciones son de otro reloj y de otra
    cosa: cuánto tardó una persona en representar el acto. Juntarlas sin decir cuál
    es cuál convierte el tiempo que se tardó en pulsar un botón en una cifra de
    rendimiento del producto.
    """
    url, _ = panel
    r = _full(url, adb_falso)
    assert "De qué reloj son estas duraciones" in r.stdout
    assert "No son latencias del" in r.stdout


def test_una_corrida_SIN_PAUSAS_se_delata_en_su_propia_tabla(sitio_demo, panel, adb_falso) -> None:
    """Sin esto, la salida de una prueba del guion es indistinguible de la de un
    ensayo de verdad, y lo primero que se hace con esa tabla es pegarla en el
    Registro — que es el documento donde se afirma que el ensayo ocurrió.
    """
    url, _ = panel
    r = _full(url, adb_falso)
    assert "SIN PAUSAS" in r.stdout
    assert "no hubo una persona" in r.stdout
    assert "NO la pegues en el Registro" in r.stdout


def test_el_cierre_manda_clasificar_reproduccion_y_desaconseja_prueba(
    sitio_demo, panel, adb_falso
) -> None:
    """`reproduccion` se creó en `T-7.14` (`D-33`) porque una corrida de
    demostración no cabía en las otras cuatro sin mentir. Las dos cierran el
    incidente y ninguna cuenta en la tasa de falsos positivos, así que elegir mal
    no se ve en ningún número — sólo en lo que el historial dice que pasó.
    """
    url, _ = panel
    r = _full(url, adb_falso)
    assert "'reproduccion', NO 'prueba'" in r.stdout


def test_sin_incidente_el_acto_2_NO_se_da_por_bueno(sitio_demo, panel, adb_falso) -> None:
    """El acto 2 promete dos cosas: que el sistema VIO el movimiento y que NO
    accionó nada. Sin incidente la primera no ocurrió, y un acto que se declarara
    bueno por no haber accionado nada estaría aprobando un gabinete mudo.
    """
    url, _ = panel
    r = _full(url, adb_falso)
    assert "no abrió incidente 'local_threshold'" in r.stdout


def test_el_ensayo_sigue_SIN_accionar_nada(sitio_demo, panel, adb_falso) -> None:
    """El invariante de este fichero. `--full` conduce y mide; lo físico lo hace
    la persona. Se comprueba por la BASE —que es donde se vería— y no por el
    texto: ninguna actuación pudo quedar registrada para este sitio.
    """
    url, _ = panel
    _full(url, adb_falso)
    with sitio_demo.cursor() as cur:
        cur.execute("SELECT count(*) FROM actuation_records WHERE site_id = %s", (SITIO_D,))
        assert cur.fetchone()[0] == 0
