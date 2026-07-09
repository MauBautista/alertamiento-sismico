"""Resolución per-gateway de la clave HMAC de comandos (T-1.38).

Sin AWS y sin DB: el cliente de Secrets Manager es un fake duck-typed y el
reloj se inyecta. Lo que se ancla aquí es la SEMÁNTICA del cache:

- la clave es LA DEL GATEWAY (SecretId = "<prefix>/<iot_thing>", campo hmac_key);
- hit positivo con TTL: una rotación se ve al expirar, sin reiniciar procesos;
- miss definitivo (secreto inexistente / JSON malformado) con cache negativa
  corta: una ráfaga contra un thing sin secreto no martillea Secrets Manager;
- error transitorio (throttle/red) ⇒ None SIN cachear: el request actual falla
  cerrado y el siguiente reintenta;
- None significa SIEMPRE fail-closed (503 / sync skip), jamás clave compartida.
"""

from __future__ import annotations

import json

import pytest
from botocore.exceptions import ClientError

from takab_api.commands.keys import (
    SecretsManagerKeyProvider,
    StaticKeyProvider,
    build_key_provider,
)
from takab_api.settings import Settings

PREFIX = "takab/dev/gateway-hmac"


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "GetSecretValue")


class _FakeSecretsClient:
    """``get_secret_value`` programable; registra cada SecretId consultado."""

    def __init__(self) -> None:
        self.secrets: dict[str, str] = {}
        self.errors: dict[str, Exception] = {}
        self.calls: list[str] = []

    def put(self, thing: str, key: str) -> None:
        self.secrets[f"{PREFIX}/{thing}"] = json.dumps({"thing_name": thing, "hmac_key": key})

    def get_secret_value(self, *, SecretId: str) -> dict:  # noqa: N803 — firma boto3
        self.calls.append(SecretId)
        if SecretId in self.errors:
            raise self.errors[SecretId]
        if SecretId not in self.secrets:
            raise _client_error("ResourceNotFoundException")
        return {"SecretString": self.secrets[SecretId]}


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def sm() -> _FakeSecretsClient:
    return _FakeSecretsClient()


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


def _provider(
    sm: _FakeSecretsClient, clock: _Clock, *, ttl: float = 300.0, negative_ttl: float = 30.0
) -> SecretsManagerKeyProvider:
    settings = Settings(
        command_hmac_secret_prefix=PREFIX,
        command_hmac_cache_ttl_s=ttl,
        command_hmac_negative_ttl_s=negative_ttl,
    )
    return SecretsManagerKeyProvider(settings, client=sm, clock=clock)


def test_static_provider_resolves_only_known_things() -> None:
    p = StaticKeyProvider({"gw-a": "ka", "gw-b": "kb", "gw-vacia": ""})
    assert p.key_for("gw-a") == b"ka"
    assert p.key_for("gw-b") == b"kb"
    assert p.key_for("gw-c") is None
    assert p.key_for("gw-vacia") is None  # clave vacía = no clave (fail-closed)


def test_build_key_provider_precedence_and_fail_closed() -> None:
    inline = Settings(command_hmac_keys_json='{"gw-x": "k"}', command_hmac_secret_prefix=PREFIX)
    assert isinstance(build_key_provider(inline), StaticKeyProvider)  # inline gana
    remote = Settings(command_hmac_keys_json="", command_hmac_secret_prefix=PREFIX)
    assert isinstance(build_key_provider(remote), SecretsManagerKeyProvider)
    nada = Settings(command_hmac_keys_json="", command_hmac_secret_prefix="")
    assert build_key_provider(nada).key_for("gw-x") is None  # todo fail-closed


def test_build_key_provider_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="JSON"):
        build_key_provider(Settings(command_hmac_keys_json="{no json"))
    with pytest.raises(ValueError, match="objeto"):
        build_key_provider(Settings(command_hmac_keys_json='["lista"]'))


def test_secret_id_is_prefix_slash_thing(sm: _FakeSecretsClient, clock: _Clock) -> None:
    sm.put("gw-dev-0001", "clave-real")
    p = _provider(sm, clock)
    assert p.key_for("gw-dev-0001") == b"clave-real"
    assert sm.calls == [f"{PREFIX}/gw-dev-0001"]


def test_positive_hit_cached_and_rotation_visible_after_ttl(
    sm: _FakeSecretsClient, clock: _Clock
) -> None:
    sm.put("gw-a", "k1")
    p = _provider(sm, clock, ttl=300.0)
    assert p.key_for("gw-a") == b"k1"
    assert p.key_for("gw-a") == b"k1"
    assert len(sm.calls) == 1  # el segundo key_for salió del cache

    sm.put("gw-a", "k2")  # rotación del secreto
    clock.now += 299.0
    assert p.key_for("gw-a") == b"k1"  # aún dentro del TTL
    clock.now += 2.0
    assert p.key_for("gw-a") == b"k2"  # visible sin reinicio
    assert len(sm.calls) == 2


def test_missing_secret_negative_cached_until_provisioned(
    sm: _FakeSecretsClient, clock: _Clock
) -> None:
    p = _provider(sm, clock, negative_ttl=30.0)
    assert p.key_for("gw-nuevo") is None
    assert p.key_for("gw-nuevo") is None
    assert len(sm.calls) == 1  # dentro de la ventana negativa no re-consulta

    sm.put("gw-nuevo", "ya-existe")  # provisión tardía del gabinete
    clock.now += 31.0
    assert p.key_for("gw-nuevo") == b"ya-existe"


def test_transient_error_fails_closed_without_caching(
    sm: _FakeSecretsClient, clock: _Clock
) -> None:
    sid = f"{PREFIX}/gw-a"
    sm.errors[sid] = _client_error("ThrottlingException")
    p = _provider(sm, clock)
    assert p.key_for("gw-a") is None  # ESTE request falla cerrado
    assert p.key_for("gw-a") is None
    assert len(sm.calls) == 2  # sin cache: cada intento re-consulta

    del sm.errors[sid]
    sm.put("gw-a", "k")
    assert p.key_for("gw-a") == b"k"  # se recupera sin esperar TTL alguno


def test_malformed_secret_is_fail_closed_and_negative_cached(
    sm: _FakeSecretsClient, clock: _Clock
) -> None:
    sm.secrets[f"{PREFIX}/gw-a"] = json.dumps({"thing_name": "gw-a"})  # sin hmac_key
    sm.secrets[f"{PREFIX}/gw-b"] = "esto no es json"
    sm.secrets[f"{PREFIX}/gw-c"] = json.dumps({"hmac_key": ""})  # vacía
    p = _provider(sm, clock)
    assert p.key_for("gw-a") is None
    assert p.key_for("gw-b") is None
    assert p.key_for("gw-c") is None
    assert p.key_for("gw-a") is None
    assert len(sm.calls) == 3  # el repetido salió de la cache negativa


def test_invalidate_forces_refetch(sm: _FakeSecretsClient, clock: _Clock) -> None:
    sm.put("gw-a", "k1")
    p = _provider(sm, clock)
    assert p.key_for("gw-a") == b"k1"
    sm.put("gw-a", "k2")
    p.invalidate("gw-a")
    assert p.key_for("gw-a") == b"k2"
    assert len(sm.calls) == 2
