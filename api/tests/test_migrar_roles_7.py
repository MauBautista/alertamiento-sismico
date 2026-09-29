"""El script de migración de Cognito a los siete roles (D-42 · T-9.21 · T-9.81).

[T-9.81] La migración ya se hizo (``--verify`` dio cero) y los grupos viejos se borran
por terraform: del script queda ``--verify``. ``--apply`` y ``--dry-run`` lo DICEN y
salen 2 sin tocar el pool.

NUNCA toca AWS: el cliente de ``cognito-idp`` es un doble en memoria; registra toda
escritura, y aquí ninguna prueba admite una sola.
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


# -- los modos retirados -------------------------------------------------------


@pytest.mark.parametrize("modo", ["--apply", "--dry-run"])
def test_los_modos_de_migrar_se_retiraron_y_salen_2(capsys, modo: str) -> None:
    fake = _pool()
    assert _run(fake, modo) == 2
    assert fake.calls == [], "un modo retirado no escribe NADA"
    err = capsys.readouterr().err
    assert "T-9.81" in err and "--verify" in err


def test_apply_con_map_tampoco_escribe() -> None:
    fake = _pool()
    with pytest.raises(SystemExit) as exc:
        _run(fake, "--apply", "--map", "edif=tenant_admin")
    assert exc.value.code == 2
    assert fake.calls == []


# -- --verify ------------------------------------------------------------------


def test_verify_falla_con_viejos(capsys) -> None:
    fake = _pool()
    assert _run(fake, "--verify") == 1
    out = capsys.readouterr().out
    for u in ("soc", "guardia", "edif"):
        assert f"{u} <{u}@example.com>" in out
    assert "admin <admin@example.com>" not in out
    assert "brig <brig@example.com>" not in out
    assert fake.calls == []


def test_verify_pasa_sin_viejos(capsys) -> None:
    fake = FakeCognito()
    fake.add("admin", "tenant_admin")
    fake.add("brig", "brigadista", scope="s2", surface="mobile")
    assert _run(fake, "--verify") == 0
    assert "ningún usuario" in capsys.readouterr().out


def test_verify_falla_si_solo_queda_el_grupo_viejo() -> None:
    fake = FakeCognito()
    fake.add("x", "tenant_admin", groups=["tenant_admin", "soc_operator"])
    assert _run(fake, "--verify") == 1


def test_verify_falla_si_solo_queda_el_atributo_viejo() -> None:
    """Grupo ya canónico pero ``custom:role`` viejo: su token sería «role not in groups»,
    y sigue siendo una migración a medias."""
    fake = FakeCognito()
    fake.add("x", "building_admin", groups=["brigadista"])
    assert _run(fake, "--verify") == 1


def test_verify_se_apoya_en_ROLES_RETIRADOS() -> None:
    from takab_api.auth.roles import ROLES_RETIRADOS

    assert mig.ROLES_RETIRADOS is ROLES_RETIRADOS


def test_verify_pagina_todo_el_pool() -> None:
    fake = FakeCognito()
    for i in range(130):
        fake.add(f"u{i:03d}", "tenant_admin")
    fake.add("zz-ultimo", "security_guard", scope="s1", surface="mobile")
    assert _run(fake, "--verify") == 1


def test_modos_excluyentes() -> None:
    with pytest.raises(SystemExit):
        _run(_pool(), "--dry-run", "--verify")
    with pytest.raises(SystemExit):
        _run(_pool())


def test_el_docstring_trae_el_comando_de_verify() -> None:
    assert "migrar_roles_7.py --verify" in (mig.__doc__ or "")
