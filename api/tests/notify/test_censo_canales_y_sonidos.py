"""El censo cruzado nube↔app: un push no puede nombrar lo que la app no construye.

`notify/push.py::_DELIVERY_STYLE` declara, por clase de push, **el canal Android**
por el que se entrega y **el sonido** con el que suena. Las dos son mitades de un
contrato de dos lados cuya otra mitad vive en la app — y las dos fallan hacia el
lado malo, en silencio y sin un solo error:

- **Canal que la app no crea.** FCM, ante un ``channel_id`` inexistente, cae al canal
  por defecto: importancia ``DEFAULT``, **sin bypass de No Molestar**. El push llega,
  no despierta a nadie, y nada lo denuncia. `android.priority: "high"` no lo salva —
  en Android 8+ quien gobierna el heads-up y el DND es la **importancia del canal**.
- **Sonido que el bundle no trae.** iOS, ante un ``name`` que no está empaquetado,
  cae al sonido por defecto. El sistema afirma un sonido crítico que no puede sonar.

Los dos se han pagado ya. `T-2.147.a` cerró el push de pánico con un test que fija
que su canal sea **distinto** del sísmico (`test_push_class_panic.py`) y ninguno que
fije que **exista**: `building_alarm` se declaró aquí y no se construyó nunca. Y
`push.py` pidió a APNs un ``seismic_alert.caf`` que no estaba en el repo.

Este fichero no juzga si el canal es el correcto: fija que **exista el que se nombra**.
Es lo que hace que una clase de push nueva se ponga roja en vez de degradarse a
notificación normal — la doctrina del repo aplicada aquí, porque *un censo que enumera
a mano acaba divergiendo*. Mismo idioma que `tests/commands/test_sync_mirror.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from takab_api.notify.push import _DELIVERY_STYLE

REPO_ROOT = Path(__file__).resolve().parents[3]
PUSH_TS = REPO_ROOT / "mobile/src/services/push.ts"
APP_JSON = REPO_ROOT / "mobile/app.json"

#: `export const SEISMIC_CHANNEL_ID = "…";` y su hermana sin exportar (el id
#: legacy que se retira no forma parte de la API del módulo, pero sí se cita aquí).
_CONST = re.compile(r"""(?:export\s+)?const\s+(\w+)\s*=\s*["'`]([^"'`]+)["'`]""")
#: `await Notifications.setNotificationChannelAsync(SEISMIC_CHANNEL_ID, {`
_CREA = re.compile(r"""setNotificationChannelAsync\(\s*(?:(\w+)|["']([^"']+)["'])""")
#: `await Notifications.deleteNotificationChannelAsync("seismic_alert")`
_BORRA = re.compile(r"""deleteNotificationChannelAsync\(\s*(?:(\w+)|["']([^"']+)["'])""")


def _fuente() -> str:
    assert PUSH_TS.exists(), (
        f"no existe {PUSH_TS.relative_to(REPO_ROOT)}: o se movió el cliente de push de la "
        "app, o este censo dejó de mirar donde debe. Las dos cosas hay que arreglarlas — "
        "un censo que no encuentra su otra mitad NO puede pasar en verde."
    )
    return PUSH_TS.read_text(encoding="utf-8")


def _resolver(fuente: str, patron: re.Pattern[str]) -> set[str]:
    """Ids de canal citados por `patron`, resolviendo las constantes del módulo."""
    consts = dict(_CONST.findall(fuente))
    ids: set[str] = set()
    for nombre, literal in patron.findall(fuente):
        if literal:
            ids.add(literal)
        elif nombre in consts:
            ids.add(consts[nombre])
        else:  # pragma: no cover - defensa: constante importada de otro módulo
            pytest.fail(
                f"`{nombre}` se usa como id de canal en push.ts pero no se declara ahí. "
                "El censo solo resuelve constantes locales; si se mueve a otro módulo, "
                "hay que enseñarle a mirarlo — no darlo por bueno."
            )
    return ids


def _sonidos_declarados_por_la_nube() -> dict[str, str]:
    """`clase → fichero de sonido`, solo los que NO son el del sistema."""
    fuera: dict[str, str] = {}
    for clase, estilo in _DELIVERY_STYLE.items():
        sonido = estilo["sound"]
        nombre = sonido["name"] if isinstance(sonido, dict) else sonido
        if nombre != "default":
            fuera[clase] = nombre
    return fuera


def _sounds_del_plugin() -> list[str]:
    plugins = json.loads(APP_JSON.read_text(encoding="utf-8"))["expo"]["plugins"]
    for entrada in plugins:
        if isinstance(entrada, list) and entrada and entrada[0] == "expo-notifications":
            return list(entrada[1].get("sounds", []))
    return []


def test_todo_canal_que_la_nube_nombra_lo_crea_la_app() -> None:
    """El defecto de `building_alarm`, fijado para que no vuelva."""
    declarados = {estilo["channel_id"] for estilo in _DELIVERY_STYLE.values()}
    creados = _resolver(_fuente(), _CREA)
    faltan = declarados - creados
    assert not faltan, (
        f"la nube entrega por {sorted(faltan)} y `configureAndroidChannels` no lo(s) crea. "
        "FCM caerá al canal por defecto: importancia DEFAULT, sin bypass de No Molestar. "
        "El push llega y NO despierta a nadie, sin un solo error a la vista."
    )


def test_ningun_canal_se_crea_y_se_borra_a_la_vez() -> None:
    """Versionar un canal exige borrar el viejo — pero nunca el que está en uso.

    La importancia y el sonido de un canal Android son **inmutables tras crearlo**:
    cambiar el tono obliga a estrenar id y a retirar el anterior. Si el borrado se
    quedara apuntando al id vivo, el teléfono perdería el canal en cada arranque y
    con él las preferencias que el usuario haya tocado.
    """
    fuente = _fuente()
    solapan = _resolver(fuente, _CREA) & _resolver(fuente, _BORRA)
    assert not solapan, (
        f"`configureAndroidChannels` crea y borra {sorted(solapan)} en la misma pasada. "
        "El borrado es para el id ANTERIOR, no para el vigente."
    )


def test_todo_sonido_propio_que_la_nube_nombra_viaja_en_el_bundle() -> None:
    """El defecto del `.caf` fantasma, fijado para que no vuelva."""
    empaquetados = {Path(p).name for p in _sounds_del_plugin()}
    for clase, fichero in _sonidos_declarados_por_la_nube().items():
        assert fichero in empaquetados, (
            f"la clase {clase} pide el sonido {fichero!r} y `mobile/app.json` no lo "
            f"empaqueta (lleva {sorted(empaquetados)}). iOS cae al sonido por defecto "
            "EN SILENCIO: el sistema afirmaría un sonido crítico que no puede sonar."
        )


def test_los_sonidos_empaquetados_existen_en_disco() -> None:
    """Un `sounds` que apunta a un fichero ausente rompe el prebuild, no el test —
    y lo rompe lejos de aquí, donde ya nadie lo relaciona con este cambio."""
    for ruta in _sounds_del_plugin():
        f = (APP_JSON.parent / ruta).resolve()
        assert f.is_file(), f"`app.json` empaqueta {ruta!r} y el fichero no existe: {f}"
