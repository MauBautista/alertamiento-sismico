"""El script de migración de Cognito a los siete roles (D-42 · T-9.21).

NUNCA toca AWS: el cliente de ``cognito-idp`` es un doble en memoria que imita las
seis operaciones que el script usa (y registra el ORDEN en que se llaman, porque el
orden es parte del contrato: grupo nuevo → atributos → grupo viejo).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

_RUTA = Path(__file__).resolve().parents[1] / "scripts" / "migrar_roles_7.py"
_spec = importlib.util.spec_from_file_location("migrar_roles_7", _RUTA)
assert _spec and _spec.loader
mig = importlib.util.module_from_spec(_spec)
sys.modules["migrar_roles_7"] = mig
_spec.loader.exec_module(mig)

from takab_api.users.directory import CognitoUserDirectory  # noqa: E402

TENANT = "d0000000-0000-0000-0000-000000000001"


class FakeCognito:
    """Doble del cliente boto3 ``cognito-idp``: usuarios, atributos y grupos."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, str]] = {}
        self.groups: dict[str, set[str]] = {}
        self.calls: list[tuple[str, str, str]] = []

    def add(self, username: str, role: str, *, groups=None, scope="*", surface="web") -> None:
        self.users[username] = {
            "email": f"{username}@example.com",
            "custom:tenant_id": TENANT,
            "custom:role": role,
            "custom:site_scope": scope,
            "custom:zone_id": "",
            "custom:surface": surface,
        }
        self.groups[username] = set(groups if groups is not None else [role])

    def _attrs(self, u: str) -> list[dict]:
        return [{"Name": k, "Value": v} for k, v in self.users[u].items()]

    def _missing(self, u: str) -> None:
        if u not in self.users:
            raise ClientError(
                {"Error": {"Code": "UserNotFoundException", "Message": u}}, "AdminGetUser"
            )

    def list_users(self, UserPoolId, Limit, PaginationToken=None):  # noqa: N803
        names = sorted(self.users)
        start = int(PaginationToken or 0)
        page = names[start : start + Limit]
        out = {
            "Users": [{"Username": u, "Attributes": self._attrs(u), "Enabled": True} for u in page]
        }
        if start + Limit < len(names):
            out["PaginationToken"] = str(start + Limit)
        return out

    def admin_get_user(self, UserPoolId, Username):  # noqa: N803
        self._missing(Username)
        return {"Username": Username, "UserAttributes": self._attrs(Username), "Enabled": True}

    def admin_list_groups_for_user(self, UserPoolId, Username):  # noqa: N803
        self._missing(Username)
        return {"Groups": [{"GroupName": g} for g in sorted(self.groups[Username])]}

    def admin_add_user_to_group(self, UserPoolId, Username, GroupName):  # noqa: N803
        self.calls.append(("add_group", Username, GroupName))
        self.groups[Username].add(GroupName)
        return {}

    def admin_remove_user_from_group(self, UserPoolId, Username, GroupName):  # noqa: N803
        self.calls.append(("remove_group", Username, GroupName))
        self.groups[Username].discard(GroupName)
        return {}

    def admin_update_user_attributes(self, UserPoolId, Username, UserAttributes):  # noqa: N803
        for a in UserAttributes:
            self.calls.append(("attr", Username, f"{a['Name']}={a['Value']}"))
            self.users[Username][a["Name"]] = a["Value"]
        return {}


def _dir(fake: FakeCognito) -> CognitoUserDirectory:
    return CognitoUserDirectory(user_pool_id="us-east-2_TEST", region="us-east-2", client=fake)


def _run(fake: FakeCognito, *argv: str, capsys=None) -> int:
    return mig.main(list(argv), directory=_dir(fake))


def _pool() -> FakeCognito:
    fake = FakeCognito()
    fake.add("soc", "soc_operator")
    fake.add("guardia", "security_guard", scope="s1", surface="mobile")
    fake.add("edif", "building_admin", scope="*", surface="both")
    fake.add("admin", "tenant_admin")
    fake.add("brig", "brigadista", scope="s2", surface="mobile")
    return fake


# -- --dry-run -----------------------------------------------------------------


def test_dry_run_lista_los_viejos_y_no_escribe(capsys) -> None:
    fake = _pool()
    assert _run(fake, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "soc" in out and "soc_operator" in out and "tenant_admin" in out
    assert "guardia" in out and "security_guard" in out
    # el building_admin NO tiene destino por defecto: se le exige un --map
    assert "edif" in out and "--map" in out
    # los ya canónicos no aparecen como pendientes
    assert "admin <admin@example.com>" not in out
    assert "brig <brig@example.com>" not in out
    assert fake.calls == []


# -- --apply -------------------------------------------------------------------


def test_apply_se_niega_si_un_building_admin_no_tiene_mapeo(capsys) -> None:
    fake = _pool()
    assert _run(fake, "--apply") != 0
    assert fake.calls == [], "no debe escribir NADA si se niega"
    assert "edif" in capsys.readouterr().err


def test_apply_rechaza_un_mapeo_que_no_corresponde_a_nadie(capsys) -> None:
    fake = _pool()
    rc = _run(fake, "--apply", "--map", "edif=tenant_admin", "--map", "nadie=tenant_admin")
    assert rc != 0
    assert fake.calls == []
    assert "nadie" in capsys.readouterr().err


def test_apply_rechaza_un_destino_no_canonico_o_interno() -> None:
    for destino in ("soc_operator", "takab_superadmin", "rey"):
        fake = _pool()
        assert _run(fake, "--apply", "--map", f"edif={destino}") != 0
        assert fake.calls == []


def test_apply_orden_grupo_nuevo_atributos_grupo_viejo() -> None:
    fake = _pool()
    assert _run(fake, "--apply", "--map", "edif=tenant_admin") == 0
    soc = [c for c in fake.calls if c[1] == "soc"]
    kinds = [c[0] for c in soc]
    assert kinds[0] == "add_group" and soc[0][2] == "tenant_admin"
    assert kinds[-1] == "remove_group" and soc[-1][2] == "soc_operator"
    assert all(k == "attr" for k in kinds[1:-1]) and len(kinds) > 2
    assert fake.users["soc"]["custom:role"] == "tenant_admin"
    assert fake.groups["soc"] == {"tenant_admin"}


def test_apply_tenant_admin_recibe_alcance_de_todo_el_cliente() -> None:
    fake = _pool()
    fake.users["edif"]["custom:site_scope"] = "s9"
    assert _run(fake, "--apply", "--map", "edif=tenant_admin") == 0
    assert fake.users["edif"]["custom:role"] == "tenant_admin"
    assert fake.users["edif"]["custom:site_scope"] == "*"
    assert fake.groups["edif"] == {"tenant_admin"}


def test_apply_brigadista_conserva_su_inmueble_y_nunca_queda_web() -> None:
    fake = _pool()
    fake.users["guardia"]["custom:surface"] = "web"
    assert _run(fake, "--apply", "--map", "edif=tenant_admin") == 0
    g = fake.users["guardia"]
    assert g["custom:role"] == "brigadista"
    assert g["custom:site_scope"] == "s1"
    assert g["custom:surface"] in {"mobile", "both"}
    assert fake.groups["guardia"] == {"brigadista"}


def test_apply_building_admin_a_brigadista_con_todo_el_cliente_se_niega(capsys) -> None:
    """building_admin con '*' → brigadista = manual_activate en TODOS los inmuebles:
    una escalada que el script no hace por su cuenta."""
    fake = _pool()
    assert _run(fake, "--apply", "--map", "edif=brigadista") != 0
    assert fake.calls == []
    assert "edif" in capsys.readouterr().err


def test_apply_building_admin_a_brigadista_con_inmueble_acotado() -> None:
    fake = _pool()
    fake.users["edif"]["custom:site_scope"] = "s3"
    assert _run(fake, "--apply", "--map", "edif=brigadista") == 0
    assert fake.users["edif"]["custom:role"] == "brigadista"
    assert fake.users["edif"]["custom:site_scope"] == "s3"
    assert fake.users["edif"]["custom:surface"] == "both"


def test_map_por_email() -> None:
    fake = _pool()
    assert _run(fake, "--apply", "--map", "EDIF@example.com=tenant_admin") == 0
    assert fake.users["edif"]["custom:role"] == "tenant_admin"


def test_apply_es_idempotente_y_reejecutable() -> None:
    fake = _pool()
    assert _run(fake, "--apply", "--map", "edif=tenant_admin") == 0
    fake.calls.clear()
    assert _run(fake, "--apply", "--map", "edif=tenant_admin") == 0
    assert fake.calls == [], "la segunda pasada no debe escribir nada"


def test_apply_completa_una_migracion_a_medias() -> None:
    """custom:role ya nuevo pero sigue en el grupo viejo (corte a mitad): se remata."""
    fake = FakeCognito()
    fake.add("soc", "tenant_admin", groups=["tenant_admin", "soc_operator"])
    assert _run(fake, "--apply") == 0
    assert fake.groups["soc"] == {"tenant_admin"}
    assert ("remove_group", "soc", "soc_operator") in fake.calls


# -- --verify ------------------------------------------------------------------


def test_verify_falla_con_viejos_y_pasa_tras_migrar() -> None:
    fake = _pool()
    assert _run(fake, "--verify") != 0
    assert _run(fake, "--apply", "--map", "edif=tenant_admin") == 0
    assert _run(fake, "--verify") == 0


def test_verify_falla_si_solo_queda_el_grupo_viejo() -> None:
    fake = FakeCognito()
    fake.add("x", "tenant_admin", groups=["tenant_admin", "soc_operator"])
    assert _run(fake, "--verify") != 0


def test_verify_pagina_todo_el_pool() -> None:
    fake = FakeCognito()
    for i in range(130):
        fake.add(f"u{i:03d}", "tenant_admin")
    fake.add("zz-ultimo", "security_guard", scope="s1", surface="mobile")
    assert _run(fake, "--verify") != 0


def test_modos_excluyentes() -> None:
    with pytest.raises(SystemExit):
        _run(_pool(), "--dry-run", "--verify")
    with pytest.raises(SystemExit):
        _run(_pool())


def test_el_docstring_trae_los_tres_comandos() -> None:
    doc = mig.__doc__ or ""
    for modo in ("--dry-run", "--apply --map", "--verify"):
        assert modo in doc


def test_apply_soc_operator_a_brigadista_con_todo_el_cliente_se_niega(capsys) -> None:
    """[revisión F2] soc_operator no tenía manual_activate ni siren_silence: pasarlo a
    brigadista con '*' le daría los dos en TODOS los inmuebles."""
    fake = _pool()
    assert _run(fake, "--apply", "--map", "edif=tenant_admin", "--map", "soc=brigadista") != 0
    assert fake.calls == []
    assert "soc" in capsys.readouterr().err


def test_apply_un_guardia_con_todo_el_cliente_NO_se_bloquea() -> None:
    """security_guard ya tenía los permisos de campo con ese mismo alcance: no gana nada."""
    fake = _pool()
    fake.users["guardia"]["custom:site_scope"] = "*"
    assert _run(fake, "--apply", "--map", "edif=tenant_admin") == 0
    assert fake.users["guardia"]["custom:role"] == "brigadista"
