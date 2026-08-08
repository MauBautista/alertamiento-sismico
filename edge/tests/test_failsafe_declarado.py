"""[T-2.70.a · D1·auditoría 2026-08-08] QUE EL FALLO DURO SEA INALCANZABLE POR CONFIG.

D1.2 hizo bien en quitar el default silencioso de `_failsafe`: un canal de relé
sin modo declarado ya no cae en `NORMALLY_OPEN` —que para `GAS_VALVE`
(FAIL_CLOSE) y `DOOR_RETAINER` (NORMALLY_CLOSED) INVIERTE los dos extremos del
canal—, sino que truena. Pero ese fallo duro se quedó sin guarda propia:

* **nada anclaba `LOCAL_RELAY_CHANNELS ⊆ EdgeSettings.failsafe`**: el día que
  entre un sexto relé, nadie se enteraría hasta que el gabinete no arranque; y
* **`TAKAB_EDGE_FAILSAFE` SUSTITUÍA el diccionario entero** en vez de
  completarlo, así que un `edge.env` que sólo quisiera corregir la polaridad de
  la sirena borraba las otras cuatro y **tumbaba el arranque del gabinete**.

Este archivo cierra las dos mitades: la guarda es DERIVADA (sigue a la tupla, no
a una lista escrita a mano — hay un test que lo demuestra inyectando un canal) y
el perfil del entorno se FUSIONA sobre los modos de fábrica.

**Por qué fusionar y no fallar al construir la config.** Fallar temprano es la
regla general y aquí sería lo peor de los dos: `EdgeSettings` es también el
documento FIRMADO del config sync (`ConfigStore.apply_signed_update` hace
`EdgeSettings.model_validate_json`), y `_high_water` sólo sube tras validar — un
doc con `failsafe` parcial tiraría el documento ENTERO (umbrales,
`command_enabled`…) y se reintentaría idéntico para siempre. Es exactamente el
razonamiento ya ratificado para `cloud_admin_state`: lo que puede volcar el
documento completo degrada hacia PROTEGER. Y en el gabinete, la alternativa a
fusionar es un edificio sin alertamiento sísmico por un JSON a medio escribir.

Lo que NO vuelve con la fusión es lo que hacía peligroso al default de D1.2:
aquel respondía `NORMALLY_OPEN` a TODO, o sea inventaba una polaridad uniforme
para canales que no la tienen; `DEFAULT_FAILSAFE` da a cada canal SU modo, que
es una propiedad del actuador (una solenoide fail-close lo es en todos los
edificios), no del sitio. Y el fallo duro de `_failsafe` NO se toca: sigue vivo
para los mapas que llegan por caminos que no validan (`model_copy`), lo cual se
ancla abajo para que nadie lo borre argumentando que la config ya lo garantiza.
"""

from __future__ import annotations

import pytest
from takab_edge import gpio as modulo_gpio
from takab_edge.config import load_settings
from takab_edge.config.settings import DEFAULT_FAILSAFE, EdgeSettings
from takab_edge.contracts import ActuatorChannel, FailSafeMode
from takab_edge.gpio import GpioController, UndeclaredFailSafeError, normal_energized


def _canales_de_rele_sin_modo(perfil) -> list[str]:  # noqa: ANN001 — dict del modelo
    """Canales de RELÉ que ese perfil deja sin modo fail-safe declarado.

    DERIVADO de `takab_edge.gpio.LOCAL_RELAY_CHANNELS` y leído por atributo del
    módulo (no importado por nombre) para que la derivación sea DEMOSTRABLE:
    `test_la_guarda_es_DERIVADA…` inyecta un canal ahí y exige que salga aquí.
    """
    return sorted(c.value for c in modulo_gpio.LOCAL_RELAY_CHANNELS if c not in perfil)


def _pin_del_rele(settings, canal: ActuatorChannel):  # noqa: ANN001, ANN202 — EdgeSettings
    from gpiozero import Device

    return Device.pin_factory.pin(getattr(settings.pins, f"relay_{canal.value}"))


# --------------------------------------------------- la inclusión, DERIVADA


def test_todo_canal_de_rele_nace_con_su_modo_fail_safe_declarado():
    """`LOCAL_RELAY_CHANNELS ⊆ failsafe`, sin enumerar ni un canal.

    El día que entre un sexto relé a `LOCAL_RELAY_CHANNELS` sin su línea en
    `DEFAULT_FAILSAFE`, esto se pone en rojo SOLO. Hasta hoy el aviso llegaba
    por otra vía: el gabinete no arrancaba.
    """
    assert _canales_de_rele_sin_modo(DEFAULT_FAILSAFE) == [], (
        "hay un canal de relé sin modo en DEFAULT_FAILSAFE: el gabinete tronaría "
        "al construir ese relé (UndeclaredFailSafeError), y con razón — para "
        "FAIL_CLOSE/NORMALLY_CLOSED no existe un default que no invierta la "
        "polaridad. Declara su modo junto a los otros cuatro."
    )
    assert _canales_de_rele_sin_modo(EdgeSettings().failsafe) == [], (
        "los defaults del modelo no coinciden con DEFAULT_FAILSAFE"
    )


def test_la_guarda_es_DERIVADA_y_no_una_lista_de_canales_a_mano(monkeypatch):
    """EL ANTI-TEATRO de la guarda de arriba.

    Un test que enumerase los cinco canales pasaría igual el día que entre el
    sexto, que es justo el día que importa. Aquí se inyecta un canal nuevo en
    `LOCAL_RELAY_CHANNELS` —se usa `SYSTEM`, que no tiene modo declarado ni lo
    tendrá— y se exige que la guarda lo delate sin que nadie toque una lista.
    """
    monkeypatch.setattr(
        modulo_gpio,
        "LOCAL_RELAY_CHANNELS",
        (*modulo_gpio.LOCAL_RELAY_CHANNELS, ActuatorChannel.SYSTEM),
    )
    assert _canales_de_rele_sin_modo(EdgeSettings().failsafe) == ["system"], (
        "la guarda no siguió a LOCAL_RELAY_CHANNELS: está enumerando canales a "
        "mano y no vería el próximo relé que se declare"
    )


# ------------------------------------- el entorno COMPLETA, no SUSTITUYE


def test_un_failsafe_parcial_del_entorno_no_desprotege_el_gabinete(monkeypatch):
    """El `edge.env` que sólo quiere corregir UN canal ya no borra los otros cuatro.

    Escenario real de aprovisionamiento: un sitio con la sirena en un lazo
    supervisado declara `TAKAB_EDGE_FAILSAFE={"siren": "NC"}`. Con la sustitución,
    `GAS_VALVE`, `ELEVATOR`, `DOOR_RETAINER` y `STROBE` se quedaban SIN modo y
    `gpio` —que es `critical=True`— tronaba: el edificio se quedaba sin
    alertamiento sísmico por un JSON a medio escribir.

    Se mide hasta el PIN: el gabinete arranca y el gas reposa donde debe.
    """
    monkeypatch.setenv("TAKAB_EDGE_FAILSAFE", '{"siren": "NC"}')
    ajustes = load_settings()

    assert ajustes.failsafe[ActuatorChannel.SIREN] is FailSafeMode.NORMALLY_CLOSED, (
        "lo declarado por el operador MANDA: la fusión completa, no pisa"
    )
    assert _canales_de_rele_sin_modo(ajustes.failsafe) == [], (
        "una variable de entorno parcial dejó canales de relé sin modo declarado"
    )
    assert ajustes.failsafe[ActuatorChannel.GAS_VALVE] is FailSafeMode.FAIL_CLOSE, (
        "el relleno tiene que ser el modo PROPIO de cada canal; un default uniforme "
        "(NORMALLY_OPEN) es exactamente lo que D1.2 quitó porque INVIERTE el gas"
    )

    controlador = GpioController(ajustes)
    controlador.start()  # ← lo que tronaba
    try:
        for canal in modulo_gpio.LOCAL_RELAY_CHANNELS:
            esperado = normal_energized(ajustes.failsafe[canal])
            assert _pin_del_rele(ajustes, canal).state is esperado, (
                f"{canal.value} no reposa en el nivel de su modo declarado"
            )
    finally:
        controlador.stop()


def test_un_documento_firmado_con_failsafe_parcial_tampoco_tumba_el_gabinete():
    """La misma fusión por el camino de la NUBE, que es el otro que construye settings.

    `ConfigStore.apply_signed_update` hace `EdgeSettings.model_validate_json(raw)`
    con el documento firmado ENTERO. Si un `failsafe` parcial dejara canales sin
    modo, el gabinete aplicaría una config que no puede arrancar; y si en vez de
    eso se lanzara en la construcción, el doc COMPLETO (umbrales,
    `command_enabled`, `cloud_admin_state`…) se rechazaría y —como `_high_water`
    sólo sube tras validar— se reintentaría idéntico para siempre.
    """
    desde_la_nube = EdgeSettings.model_validate_json('{"failsafe": {"elevator": "NO"}}')
    assert _canales_de_rele_sin_modo(desde_la_nube.failsafe) == []
    assert desde_la_nube.failsafe[ActuatorChannel.DOOR_RETAINER] is FailSafeMode.NORMALLY_CLOSED


def test_la_fusion_NO_deroga_el_fallo_duro_de_failsafe(settings):
    """La mitad que impide que esta tarea borre la de D1.2.

    Alguien podría leer la fusión como «ya no hace falta que `_failsafe` truene».
    No: `model_copy(update=...)` NO pasa por validadores —lo usan los tests y
    cualquier código que ajuste settings en caliente—, así que un perfil
    mutilado sigue siendo construible y el fallo duro sigue siendo la última
    línea antes del pin.
    """
    mutilado = settings.model_copy(
        update={
            "failsafe": {
                c: m for c, m in settings.failsafe.items() if c is not ActuatorChannel.GAS_VALVE
            }
        }
    )
    assert ActuatorChannel.GAS_VALVE not in mutilado.failsafe, (
        "la fusión se metió en model_copy: entonces ningún test puede volver a "
        "medir el fallo duro, y el gate de D1.2 queda sin ancla"
    )
    with pytest.raises(UndeclaredFailSafeError, match="gas_valve"):
        GpioController(mutilado).start()
