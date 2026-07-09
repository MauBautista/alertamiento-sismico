"""HostProbes reales (T-1.40): parsers puros + ejecución inyectada, sin tocar el SO.

Los formatos de referencia son los REALES capturados del Pi 5 en producción
(2026-07-09): `timedatectl timesync-status` con `Offset: +800us` (timesyncd;
`show-timesync` NO expone el offset) y `openssl x509 -enddate` del cert de AWS
IoT (`notAfter=Dec 31 23:59:59 2049 GMT`). Contrato transversal: toda falla
degrada a None («sin dato») — jamás a un número inventado, y jamás lanza.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from takab_edge.contracts import UpsStatus
from takab_edge.health import (
    HostProbes,
    UpsReading,
    _parse_cert_days,
    _parse_chrony_offset,
    _parse_timesync_offset,
)

TIMESYNC_REAL = """\
       Server: 201.174.182.214 (2.debian.pool.ntp.org)
Poll interval: 34min 8s (min: 32s; max 34min 8s)
         Leap: normal
      Version: 4
      Stratum: 2
    Reference: A0B1108
    Precision: 1us (-25)
Root distance: 1.273ms (max: 5s)
       Offset: +800us
        Delay: 39.525ms
       Jitter: 706us
 Packet count: 162
"""

# `chronyc -c tracking` CSV: campo 5 (índice 4) = offset actual del sistema (s).
CHRONY_CSV = "A0B1108,160.16.113.133,2,1751980729.123,-0.000123456,0.000234,0.000456,..."

CERT_2049 = "notAfter=Dec 31 23:59:59 2049 GMT\n"


class _Runner:
    """Ejecutor fake: mapa comando[0..1] → stdout; registra invocaciones."""

    def __init__(self, outputs: dict[str, str | None]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> str | None:
        self.calls.append(cmd)
        return self.outputs.get(" ".join(cmd[:2]))


def _probes(settings, outputs: dict[str, str | None]) -> HostProbes:
    return HostProbes(settings, run=_Runner(outputs))


# --- parsers puros -------------------------------------------------------------


def test_parse_timesync_offset_units():
    assert _parse_timesync_offset(TIMESYNC_REAL) == pytest.approx(800e-6)
    assert _parse_timesync_offset("  Offset: -12.5ms\n") == pytest.approx(-0.0125)
    assert _parse_timesync_offset("Offset: 1.5s\n") == pytest.approx(1.5)
    assert _parse_timesync_offset("sin linea de offset") is None
    assert _parse_timesync_offset("Offset: garbage\n") is None


def test_parse_chrony_offset_csv():
    assert _parse_chrony_offset(CHRONY_CSV) == pytest.approx(-0.000123456)
    assert _parse_chrony_offset("corto,csv") is None
    assert _parse_chrony_offset("a,b,c,d,not-a-float,f") is None


def test_parse_cert_days_real_aws_cert():
    now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=UTC)
    days = _parse_cert_days(CERT_2049, now=now)
    assert days == (datetime(2049, 12, 31, 23, 59, 59, tzinfo=UTC) - now).days
    assert days > 8000  # el cert de AWS IoT vence en 2049: número grande pero HONESTO
    assert _parse_cert_days("notAfter=basura", now=now) is None


# --- HostProbes con ejecutor inyectado ------------------------------------------


def test_ntp_prefers_chrony_then_timesyncd(settings):
    con_chrony = _probes(settings, {"chronyc -c": CHRONY_CSV})
    assert con_chrony.ntp_offset_s() == pytest.approx(-0.000123456)

    solo_timesyncd = _probes(settings, {"timedatectl timesync-status": TIMESYNC_REAL})
    assert solo_timesyncd.ntp_offset_s() == pytest.approx(800e-6)

    sin_fuentes = _probes(settings, {})
    assert sin_fuentes.ntp_offset_s() is None  # sin dato, no 0.0 fingido


def test_cert_days_from_settings_path(settings):
    with_cert = settings.model_copy(update={"mqtt_cert_path": "/etc/takab/certs/cert.pem"})
    probes = _probes(with_cert, {"openssl x509": CERT_2049})
    days = probes.cert_days_remaining()
    assert days is not None and days > 8000

    sin_path = settings.model_copy(update={"mqtt_cert_path": ""})
    assert _probes(sin_path, {"openssl x509": CERT_2049}).cert_days_remaining() is None

    ilegible = _probes(with_cert, {})  # openssl falla → None
    assert ilegible.cert_days_remaining() is None


def test_ups_without_hardware_is_unknown(settings, tmp_path, monkeypatch):
    import takab_edge.health as health_mod

    monkeypatch.setattr(health_mod, "_POWER_SUPPLY", tmp_path / "power_supply")  # vacío
    probes = _probes(settings, {})  # sin upsc
    assert probes.ups() == UpsReading(UpsStatus.UNKNOWN, None, None)


def test_ups_via_nut(settings):
    outputs = {
        "upsc -l": "apc900\n",
        "upsc apc900": "battery.charge: 87\nbattery.runtime: 1260\nups.status: OL\n",
    }
    reading = _probes(settings, outputs).ups()
    assert reading == UpsReading(UpsStatus.LINE, 87.0, 1260.0)


def test_ups_via_nut_on_battery(settings):
    outputs = {
        "upsc -l": "apc900\n",
        "upsc apc900": "battery.charge: 42\nups.status: OB DISCHRG\n",
    }
    reading = _probes(settings, outputs).ups()
    assert reading.status is UpsStatus.BATTERY
    assert reading.battery_pct == 42.0


def test_ups_via_sysfs(settings, tmp_path, monkeypatch):
    import takab_edge.health as health_mod

    root = tmp_path / "power_supply"
    bat = root / "BAT0"
    ac = root / "AC0"
    bat.mkdir(parents=True)
    ac.mkdir(parents=True)
    (bat / "type").write_text("Battery\n")
    (bat / "capacity").write_text("64\n")
    (ac / "type").write_text("Mains\n")
    (ac / "online").write_text("1\n")
    monkeypatch.setattr(health_mod, "_POWER_SUPPLY", root)

    reading = _probes(settings, {}).ups()
    assert reading == UpsReading(UpsStatus.LINE, 64.0, None)
