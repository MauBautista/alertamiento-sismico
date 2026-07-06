"""local_api — dashboard/control local del edificio (LAN, sin internet).

T-1.13: servidor HTTP mínimo (stdlib `http.server`, sin dependencias pesadas) accesible
en la LAN del edificio SIN internet (RBAC §4.2: fallback cuando la WAN está caída). Muestra
estado, último evento y estado de relés; permite **prueba de sirena** y **silencio por LAN**.
El acceso lo controla la segmentación de red del gabinete (LAN física del edificio).
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from takab_edge.gpio import GpioController
from takab_edge.health import HealthMonitor
from takab_edge.module import EdgeModule
from takab_edge.rules import RuleEngine

log = logging.getLogger("takab_edge.local_api")

_INDEX_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TAKAB Ailert — Gabinete</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#0b0f14;color:#e6edf3}
 header{padding:1rem;font-weight:700}
 #banner{padding:1rem;text-align:center;font-size:1.4rem;font-weight:800;display:none}
 #banner.alert{display:block;background:#b91c1c;color:#fff;animation:blink 1s step-start infinite}
 @keyframes blink{50%{opacity:.55}}
 main{padding:1rem;max-width:640px;margin:0 auto}
 .row{display:flex;justify-content:space-between;padding:.4rem 0;border-bottom:1px solid #22303c}
 .state{padding:.6rem;border-radius:.4rem;margin:.5rem 0}
 .stale{background:#78350f}.error{background:#7f1d1d}.loading{opacity:.6}
 button{padding:.7rem 1rem;margin:.3rem .3rem 0 0;border:0;
   border-radius:.4rem;font-weight:700;cursor:pointer}
 .silence{background:#ca8a04}.test{background:#2563eb;color:#fff}
 .reset{background:#334155;color:#fff}
</style></head><body>
<header>TAKAB Ailert · <span id="gw">—</span></header>
<div id="banner">ALERTA SÍSMICA · PROTÉJASE</div>
<main>
 <div id="state" class="state loading">Cargando…</div>
 <div id="rows"></div>
 <button class="silence" onclick="cmd('silence')">Silenciar audibles</button>
 <button class="test" onclick="cmd('siren-test')">Probar sirena</button>
 <button class="reset" onclick="cmd('reset')">Cerrar alerta</button>
</main>
<script>
 async function cmd(name){ try{ await fetch('/api/'+name,{method:'POST'}); refresh(); }catch(e){} }
 function row(k,v){ return '<div class="row"><span>'+k+'</span><b>'+v+'</b></div>'; }
 async function refresh(){
   const el=document.getElementById('state');
   try{
     const r=await fetch('/api/status'); if(!r.ok) throw 0;
     const s=await r.json();
     document.getElementById('gw').textContent=s.gateway_id;
     const alert = s.sasmex_active || s.last_tier==='evacuate_or_hold';
     document.getElementById('banner').className = alert ? 'alert' : '';
     const age=(Date.now()-Date.parse(s.captured_at))/1000;
     el.className='state'+(age>10?' stale':'');
     el.textContent = age>10 ? ('DATO VIEJO ('+age.toFixed(0)+'s)') : 'En línea';
     document.getElementById('rows').innerHTML =
       row('Tier', s.last_tier||'normal')+row('SASMEX activo', s.sasmex_active)+
       row('Sirena sonando', s.siren_sounding)+row('Audibles silenciados', s.audible_silenced);
   }catch(e){ el.className='state error'; el.textContent='SIN CONEXIÓN con el gabinete'; }
 }
 refresh(); setInterval(refresh,2000);
</script></body></html>
"""


class _DashboardHandler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, content_type: str = "application/json") -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        dashboard = self.server.dashboard  # type: ignore[attr-defined]
        if self.path in ("/", "/index.html"):
            self._send(200, _INDEX_HTML, "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self._send(200, json.dumps(dashboard.status()))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self) -> None:
        dashboard = self.server.dashboard  # type: ignore[attr-defined]
        actions = {
            "/api/silence": dashboard.silence,
            "/api/siren-test": dashboard.run_siren_test,
            "/api/reset": dashboard.reset_alert,
        }
        action = actions.get(self.path)
        if action is None:
            self._send(404, json.dumps({"error": "not found"}))
            return
        action()
        self._send(200, json.dumps({"ok": True}))

    def log_message(self, *args: object) -> None:  # no spamear stdout del edge
        pass


class _DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], dashboard: LocalDashboard) -> None:
        self.dashboard = dashboard
        super().__init__(address, _DashboardHandler)


class LocalDashboard(EdgeModule):
    """Expone estado del gabinete y acepta prueba de sirena / silencio por LAN (HTTP)."""

    name = "local_api"
    depends_on = ("gpio", "rules", "health")

    def __init__(
        self,
        gpio: GpioController,
        rules: RuleEngine,
        health: HealthMonitor,
        host: str = "0.0.0.0",  # noqa: S104 — LAN del gabinete por diseño
        port: int = 8080,
    ) -> None:
        super().__init__()
        self._gpio = gpio
        self._rules = rules
        self._health = health
        self._host = host
        self._port = port
        self._server: _DashboardServer | None = None
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        """Snapshot para el dashboard LAN (loading/error/empty/stale los maneja la UI)."""
        decision = self._rules.last_decision
        snap = self._health.snapshot()
        return {
            "gateway_id": snap.gateway_id,
            # Distinguir alerta REAL vs. sirena sonando vs. silenciado (regla de oro 7):
            "sasmex_active": self._gpio.sasmex_active,
            "siren_sounding": self._gpio.siren_sounding,
            "audible_silenced": self._gpio.audible_silenced,
            "last_tier": decision.tier.value if decision else None,
            "relays": [r.model_dump(mode="json") for r in self._gpio.relay_states()],
            "captured_at": snap.captured_at.isoformat(),
        }

    def silence(self) -> None:
        """Comando de silencio por LAN: apaga los audibles YA (sin tocar el estrobo)."""
        self._gpio.silence_audibles(True)
        log.warning("silencio solicitado por LAN")

    def run_siren_test(self) -> None:
        """Prueba de sirena por LAN (self-test acotado, no es una alerta real)."""
        self._gpio.run_siren_test()
        log.warning("prueba de sirena solicitada por LAN")

    def reset_alert(self) -> None:
        """Cierra/re-arma la alerta enclavada por LAN (vuelve a operación normal)."""
        self._gpio.reset()
        log.warning("alerta cerrada/re-armada por LAN")

    @property
    def address(self) -> tuple[str, int] | None:
        """Dirección real de escucha (útil con puerto efímero en tests)."""
        return self._server.server_address if self._server else None

    def _on_start(self) -> None:
        self._server = _DashboardServer((self._host, self._port), self)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="local-api", daemon=True
        )
        self._thread.start()
        host, port = self._server.server_address
        log.info("dashboard LAN en http://%s:%d (sin internet)", host, port)

    def _on_stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
