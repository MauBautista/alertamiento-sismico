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
