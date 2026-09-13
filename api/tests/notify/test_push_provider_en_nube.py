"""[T-7.03] El entorno de DESPLIEGUE elige el proveedor de push REAL, no el simulado.

Por qué este test y no uno de `build_push_provider`: esa función ya estaba bien
—devuelve `SnsPushProvider` en cuanto hay un ARN— y aun así la nube llevaba meses
mandando avisos al limbo. Lo que fallaba no era el código: era que **el despliegue
nunca le pasaba el ARN**, así que la API construía el simulado en cada arranque y
cada aviso quedaba en `notification_jobs` con estado ``simulated`` y ``sent_at``
en NULL. Un fallback que se declara «entregado» sin haber despertado un teléfono.

Medido el 2026-09-12, antes de cablearlo: con la app EN PRIMER PLANO la pantalla
de crisis tardaba 21 s en aparecer (el sondeo en reposo es de 30 s); con la app
detrás no aparecía nunca, porque el sondeo no corre en segundo plano.

Así que lo que hay que defender es la COSTURA, y se defiende leyendo el fichero
que la materializa —el heredoc de `deploy.sh`— igual que hacen
`test_settings_produccion.py` y `test_compose_cubre_los_workers.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

from takab_api.notify.push import SimulatedPushProvider, SnsPushProvider, build_push_provider
from takab_api.settings import Settings

RAIZ = Path(__file__).resolve().parents[3]
DEPLOY = RAIZ / "deploy" / "cloud" / "deploy.sh"

#: Las dos superficies. iOS espera a `GATE-STORE`, así que su ARN puede venir
#: vacío del terraform; lo que NO puede es faltar la línea que lo exporta.
VARIABLES = ("TAKAB_API_PUSH_FCM_APPLICATION_ARN", "TAKAB_API_PUSH_APNS_APPLICATION_ARN")


def _heredoc() -> str:
    return DEPLOY.read_text(encoding="utf-8")


def test_el_despliegue_exporta_los_dos_arn_de_push() -> None:
    """Sin estas líneas la nube corre con el default vacío de `Settings`."""
    texto = _heredoc()
    faltan = [v for v in VARIABLES if not re.search(rf"^{v}=", texto, re.M)]
    assert not faltan, (
        f"`deploy/cloud/deploy.sh` no exporta {faltan}.\n"
        "  Sin ellas `build_push_provider` devuelve el SIMULADO y cada aviso queda\n"
        "  en `notification_jobs` como 'simulated' con `sent_at` NULL — sin que nada\n"
        "  falle a la vista. Es el defecto que T-7.03 cerró."
    )


def test_los_arn_se_DERIVAN_del_terraform_y_no_se_teclean() -> None:
    """Un ARN tecleado envejece en silencio: apunta a una aplicación que ya no existe.

    Derivarlo de la salida de terraform tiene además una propiedad que un literal
    no tiene: si la platform application no existe, la salida es la cadena vacía y
    la API vuelve sola al proveedor simulado, que es la degradación correcta.
    """
    texto = _heredoc()
    for var in VARIABLES:
        linea = re.search(rf"^{var}=(.*)$", texto, re.M)
        assert linea is not None, f"{var} no está en el despliegue"
        valor = linea.group(1).strip()
        assert valor.startswith("$(tf "), (
            f"{var} se asigna con {valor!r}, que no sale del terraform.\n"
            "  Un ARN literal sobrevive a que alguien borre la platform application."
        )


def test_con_ARN_el_proveedor_es_el_REAL_y_sin_el_el_simulado() -> None:
    """El control positivo y su negativo, que es lo que hace honesto al de arriba."""
    real = build_push_provider(
        Settings(push_fcm_application_arn="arn:aws:sns:us-east-2:1:app/GCM/takab-dev-fcm")
    )
    assert isinstance(real, SnsPushProvider)
    assert getattr(real, "simulated", False) is False

    simulado = build_push_provider(Settings())
    assert isinstance(simulado, SimulatedPushProvider)
    assert simulado.simulated is True


#: El módulo de terraform que otorga los permisos de SNS al rol donde corre el
#: worker de notify. La otra mitad de la costura: el despliegue puede pasar los
#: ARN perfectamente y aun así no sonar un teléfono si el rol no puede publicar.
PUSH_TF = RAIZ / "infra" / "terraform" / "modules" / "push" / "main.tf"


def _politica() -> str:
    return PUSH_TF.read_text(encoding="utf-8")


def test_el_rol_puede_PUBLICAR_en_la_platform_application() -> None:
    """[T-7.03] SNS autoriza el publish contra la APLICACIÓN, no contra el endpoint.

    Medido contra la nube el 2026-09-12 con el primer push real del producto:

        not authorized to perform: SNS:Publish on resource:
        arn:aws:sns:us-east-2:…:app/GCM/takab-dev-fcm

    …y eso pese a que la llamada lleva el `TargetArn` del endpoint del
    dispositivo. Con el recurso acotado a `endpoint/*/takab-*/*`, crear el
    endpoint funcionaba —ese permiso sí está sobre la aplicación— y publicar
    rebotaba: el aviso agotaba sus tres intentos, quedaba en `failed` y ningún
    teléfono sonaba. Verde en el despliegue, verde en el registro del token, y
    silencio donde importa.
    """
    politica = _politica()
    bloque = re.search(r'Sid\s*=\s*"PushPublish".*?\n      \},', politica, re.S)
    assert bloque is not None, "desapareció el bloque PushPublish de la política de push"
    recurso = re.search(r"Resource\s*=\s*(.+)", bloque.group(0))
    assert recurso is not None and "app_arns" in recurso.group(1), (
        "`sns:Publish` no incluye las platform applications "
        f"({recurso.group(1).strip() if recurso else '?'}).\n"
        "  Sin ellas TODO push falla con AuthorizationError aunque el endpoint\n"
        "  del dispositivo se cree sin problema. Es el defecto que cerró T-7.03."
    )
