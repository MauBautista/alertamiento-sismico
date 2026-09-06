"""La poda de la landing no puede borrar de producción un fichero que el sitio usa.

EL DEFECTO
----------
`deploy/landing/deploy.sh` calcula qué claves sobran en el bucket restando la
lista local de la remota. Lo hacía ordenando con `sort` y restando con `comm`, y
en el despliegue de v3 (2026-09-06) el log soltó, entre doscientas líneas de
`aws s3 sync`:

    comm: archivo 1 no está en orden ordenado
    comm: archivo 2 no está en orden ordenado

`sort` colaciona según la locale; `comm` compara byte a byte. Bajo `es_ES.UTF-8`
la colación ignora el guion bajo, así que `sort` intercala `apple-touch-icon.png`
entre `404.html` y `_astro/...`, mientras que para `comm` `_astro` va antes. Con
las entradas desincronizadas, `comm -23` puede emitir una clave que **sí** está
en la lista local — y esa lista es la de borrados contra el sitio vivo.

Aquel día no pasó nada: salió un único huérfano legítimo y el bucket quedó
idéntico a `dist`. Pero eso fue suerte, no diseño.

POR QUÉ LA MAYORÍA DE ESTOS TESTS NO FIJAN LA LOCALE
---------------------------------------------------
La tentación es correr todo con `LC_ALL=es_ES.UTF-8` y ver el fallo. Colgar de eso
la cobertura entera sería un error: esa locale puede no estar generada en el runner
—y `C.utf8`, la que suele traer, es de las dos únicas que NO reproducen el defecto—,
así que el fichero pasaría en verde **por no haber podido reproducirlo**. Un
fallback disfrazado de OK, que es la forma exacta en que esto sobrevivió a meses de
CI verde: el defecto sólo aparece al desplegar desde una máquina con locale de
persona, y CI nunca lo es.

Así que el peso lo llevan tests que no dependen de ninguna locale: se entrega la
entrada YA DESORDENADA —en el mismo orden que produce la colación española, que es
lo que llegaba en producción— y se exige la respuesta correcta, porque la
corrección de verdad fue **quitarle a la función su precondición de orden**. Y
`test_la_resta_fija_LC_ALL_C`, que también corre siempre, ancla la otra mitad.

Encima de eso, y sólo como refuerzo,
`test_bajo_una_colacion_hostil_la_respuesta_sigue_siendo_la_correcta` reproduce el
caso real si la máquina tiene con qué; si no, se SALTA diciéndolo, que no es lo
mismo que pasar.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PODA = REPO / "deploy" / "lib" / "poda.sh"
DEPLOY_LANDING = REPO / "deploy" / "landing" / "deploy.sh"

#: El orden EXACTO que `sort` da bajo `es_ES.UTF-8` (medido en la máquina desde la
#: que se despliega): `apple-touch-icon.png` intercalado entre `404.html` y el
#: bloque `_astro/`, que es lo que `comm` considera desordenado.
ORDEN_ESPANOL = [
    "404.html",
    "apple-touch-icon.png",
    "_astro/archivo-400.Cx-XgIRR.woff2",
    "_astro/imagotipo-takab-ailert-negativo.BrzINhC9_19lxoY.webp",
    "_astro/saira-condensed-700.Cc219yMQ.woff2",
    "aviso-de-privacidad.html",
    "deploy-info.json",
    "favicon.png",
    "index.html",
    "og-v3.png",
]


def _huerfanas(tmp_path: Path, remoto: list[str], copia_local: list[str]) -> list[str]:
    """Corre `claves_huerfanas` DE VERDAD; no reimplementa la resta.

    Reimplementarla aquí sería tener dos copias de la operación que decide qué se
    borra de producción, y la que divergiría en silencio es la de este fichero.
    """
    f_remoto = tmp_path / "remoto.txt"
    f_local = tmp_path / "local.txt"
    f_remoto.write_text("".join(f"{k}\n" for k in remoto))
    f_local.write_text("".join(f"{k}\n" for k in copia_local))
    hecho = subprocess.run(
        ["bash", "-c", f'. "{PODA}" && claves_huerfanas "{f_remoto}" "{f_local}"'],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "no está en orden" not in hecho.stderr, (
        f"la resta volvió a mezclar colaciones: {hecho.stderr!r}"
    )
    return hecho.stdout.split()


def test_una_clave_que_esta_en_local_JAMAS_sale_para_borrar(tmp_path: Path) -> None:
    """El caso que de verdad muerde, y que la implementación vieja SÍ borraba.

    Medido contra el código anterior, con `apple-touch-icon.png` ya huérfano y
    `_astro/vivo.css` vivo::

        $ vieja rem.txt loc.txt
        apple-touch-icon.png
        _astro/vivo.css          <-- ESTÁ EN LOCAL, y salía en la lista de borrado

    El icono huérfano descoloca las dos listas —`comm` da por buenos los bytes,
    `sort` había puesto `apple...` delante— y a partir de ahí todo `_astro/` cae.
    O sea: CSS, JS y fuentes del sitio. Y el smoke posterior no lo habría visto,
    porque sólo pide `/`, `/no-existe` y la rev: tres peticiones que siguen
    respondiendo con la página desnuda.

    Ojo al elegir el caso: con las dos listas IDÉNTICAS esto no se reproduce
    —nunca llegan a desincronizarse— y el test pasa en verde con el defecto
    dentro. Fue la primera versión de esta prueba, y sobrevivió a la mutación.
    """
    huerfano = "apple-touch-icon.png"
    vivos = ["_astro/vivo.css", "_astro/vivo.js", "index.html"]
    assert _huerfanas(tmp_path, [huerfano, *vivos], vivos) == [huerfano]


def test_el_huerfano_de_verdad_SI_sale(tmp_path: Path) -> None:
    """El contrapeso: una poda que no poda nada también estaría rota.

    Sin este test, `claves_huerfanas() { :; }` pasaría el resto del fichero.
    """
    remoto = [*ORDEN_ESPANOL, "og-v1.png"]
    assert _huerfanas(tmp_path, remoto, ORDEN_ESPANOL) == ["og-v1.png"]


def test_el_desorden_de_la_entrada_no_cambia_la_respuesta(tmp_path: Path) -> None:
    """Mismo contenido, cuatro órdenes distintos, una sola respuesta.

    Es la propiedad que sustituye al contrato roto: antes el llamador *debía*
    entregar las listas ordenadas y coincidiendo con la colación de `comm`, y ese
    contrato no estaba escrito en ninguna parte ni podía cumplirse con `sort`.
    """
    remoto = [*ORDEN_ESPANOL, "og-v1.png", "_astro/viejo.DEADBEEF.css"]
    esperado = ["_astro/viejo.DEADBEEF.css", "og-v1.png"]
    for variante in (
        remoto,
        sorted(remoto),
        sorted(remoto, reverse=True),
        [*remoto[5:], *remoto[:5]],
    ):
        assert _huerfanas(tmp_path, variante, ORDEN_ESPANOL) == esperado


def test_los_repetidos_no_duplican_un_borrado(tmp_path: Path) -> None:
    """`aws s3api` pagina: la misma clave puede llegar dos veces."""
    remoto = [*ORDEN_ESPANOL, "og-v1.png", "og-v1.png"]
    assert _huerfanas(tmp_path, remoto, ORDEN_ESPANOL) == ["og-v1.png"]


def test_una_lista_ilegible_no_se_lee_como_bucket_vacio(tmp_path: Path) -> None:
    """Sin fichero, la función se NIEGA; no devuelve «no sobra nada».

    El fallo silencioso peligroso es el contrario —que un remoto ilegible parezca
    vacío y no se pode—, pero el que se niega es el único honesto: si no se pudo
    mirar, no se responde.
    """
    hecho = subprocess.run(
        [
            "bash",
            "-c",
            f'. "{PODA}" && claves_huerfanas "{tmp_path}/no-existe" "{tmp_path}/tampoco"',
        ],
        capture_output=True,
        text=True,
    )
    assert hecho.returncode != 0
    # El prefijo `poda:` NO es cosmético: `sort` también dice «no se puede leer»
    # —en español, en esta máquina— así que sin él la aserción casaba con el
    # mensaje de `sort` y pasaba igual con la guarda quitada. Lo cazó la mutación.
    assert "poda: no se puede leer" in hecho.stderr, hecho.stderr


def test_el_deploy_de_la_landing_no_se_guarda_su_propia_resta() -> None:
    """Una sola implementación: la de `deploy/lib/poda.sh`.

    Este es el test que impide que el defecto vuelva por donde vino. La correción
    no fue «poner `LC_ALL=C` en aquellas líneas» —eso se deshace en el primer
    editor que reordene el bloque— sino que la resta viva en un solo sitio, sin
    precondición de orden, y que el script la LLAME.
    """
    guion = DEPLOY_LANDING.read_text()
    assert "lib/poda.sh" in guion, "el deploy de la landing no sourcea la poda compartida"
    assert "claves_huerfanas" in guion, "el deploy de la landing no llama a la poda compartida"
    assert "comm -23" not in guion, "el deploy de la landing volvió a restar por su cuenta"


@pytest.mark.parametrize("guion", sorted((REPO / "deploy").glob("*/deploy.sh")))
def test_ningun_deploy_resta_claves_a_mano(guion: Path) -> None:
    """El censo lo pone el árbol: un `deploy/<algo>/deploy.sh` nuevo tampoco puede.

    Mismo criterio que `test_guarda_de_rama.py`: enumerar los scripts a mano es lo
    que hace que el siguiente entre sin guardia y nadie se entere.
    """
    assert "comm -23" not in guion.read_text(), (
        f"{guion.relative_to(REPO)} resta claves con `comm` por su cuenta: usa "
        "`claves_huerfanas` de deploy/lib/poda.sh (mezclar colaciones puede "
        "proponer para borrado una clave que sí existe en local)"
    )


def _locale_hostil() -> str | None:
    """Una locale del sistema cuya colación NO coincide con el orden de bytes.

    No es cosa del español: `en_US.utf8` también coloca `apple.png` antes que
    `_astro/x` (la colación UTF-8 ignora el guion bajo), mientras que para `comm`
    —que compara bytes— `_` (0x5F) va antes que `a` (0x61). Las únicas que
    coinciden son `C` y `C.utf8`, y `C.utf8` es justo la del runner de CI: por eso
    este defecto sobrevivió a todas las corridas verdes y sólo apareció al
    desplegar desde una máquina con locale de persona.
    """
    disponibles = subprocess.run(
        ["locale", "-a"], capture_output=True, text=True, check=False
    ).stdout.split()
    for nombre in disponibles:
        orden = subprocess.run(
            ["sort"],
            input="_astro/x\napple.png\n",
            capture_output=True,
            text=True,
            env={"LC_ALL": nombre, "PATH": "/usr/bin:/bin"},
            check=False,
        ).stdout.split()
        if orden[:1] == ["apple.png"]:
            return nombre
    return None


def test_bajo_una_colacion_hostil_la_respuesta_sigue_siendo_la_correcta(
    tmp_path: Path,
) -> None:
    """El caso real, reproducido: se despliega desde una locale de persona.

    Si el runner sólo tiene `C`/`C.utf8` esto se SALTA en vez de pasar: un verde
    aquí sin colación hostil no significaría nada, y decirlo en voz alta es la
    diferencia entre una prueba omitida y una prueba mentirosa. La cobertura no
    depende de este test —`test_la_resta_fija_LC_ALL_C` corre siempre—.
    """
    hostil = _locale_hostil()
    if hostil is None:
        pytest.skip("sin locale de colación hostil instalada; no se puede reproducir")

    f_remoto = tmp_path / "remoto.txt"
    f_local = tmp_path / "local.txt"
    f_remoto.write_text("".join(f"{k}\n" for k in [*ORDEN_ESPANOL, "og-v1.png"]))
    f_local.write_text("".join(f"{k}\n" for k in ORDEN_ESPANOL))

    hecho = subprocess.run(
        ["bash", "-c", f'. "{PODA}" && claves_huerfanas "{f_remoto}" "{f_local}"'],
        capture_output=True,
        text=True,
        env={"LC_ALL": hostil, "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        check=True,
    )
    assert hecho.stdout.split() == ["og-v1.png"]
    assert hecho.stderr == "", f"la resta se quejó del orden bajo {hostil}: {hecho.stderr!r}"


def test_la_resta_fija_LC_ALL_C() -> None:
    """Siempre corre, aunque el runner no tenga una locale hostil que reproduzca.

    Es implementación, sí, y a propósito: `LC_ALL=C` **es** la corrección. Un
    editor futuro que reordene el subshell y lo deje fuera devuelve el defecto
    entero, y en un CI con `C.utf8` ninguna prueba de conducta lo notaría.
    """
    fuente = PODA.read_text()
    assert "export LC_ALL=C" in fuente, (
        "poda.sh dejó de fijar LC_ALL=C: `sort` y `comm` vuelven a hablar idiomas "
        "distintos y la resta puede proponer borrar una clave que sí existe"
    )


def test_el_smoke_de_la_landing_mira_DENTRO_de_la_portada() -> None:
    """`/` en 200 no significa que el sitio se vea.

    La otra mitad de lo que enseñó este defecto. Las tres comprobaciones que traía
    el smoke —`/`, `/no-existe` y la rev— siguen respondiendo con la portada
    desnuda: sin tipografías y sin logotipo, porque el HTML se sirve igual. Un
    despliegue podía borrar `_astro/` entero de producción y aun así imprimir
    `== OK ==`.

    Se ancla como texto, no por conducta: probar el smoke de verdad pediría el
    arnés completo de `edge/tests/test_deploy_sh.py` (aws, terraform, npm y curl
    falsos) y esto es una línea de defensa, no el sujeto de la ficha. Lo que el
    ancla impide es que desaparezca sin que nadie lo note.
    """
    guion = DEPLOY_LANDING.read_text()
    assert "_astro/" in guion.split("--- Smoke")[-1], (
        "el smoke dejó de comprobar los assets de la portada: `/` puede devolver "
        "200 con el sitio desnudo"
    )
    assert "done < <(" in guion, (
        "el bucle del smoke de assets volvió a colgar de una tubería: en un "
        "subshell `FALTAN` sale vacía y el smoke no falla nunca"
    )
    # El mismo defecto de esta ficha, cometido DENTRO del arreglo: la primera
    # versión de este smoke no imprimía nada en verde y no contaba nada, así que
    # si el `grep` dejaba de casar —`_astro/` es el directorio por DEFECTO de
    # Astro y `build.assets` lo renombra— comprobaba CERO assets y pasaba igual.
    assert 'MIRADOS" -gt 0' in guion, (
        "el smoke de assets ya no tumba el despliegue cuando no encuentra ningún "
        "asset: un guardia que no mira nada vuelve a pasar en verde"
    )
    assert "smoke de assets: $MIRADOS" in guion, (
        "el smoke de assets dejó de decir cuántos miró: en verde sería "
        "indistinguible de no haberse ejecutado"
    )


@pytest.mark.parametrize("guion", sorted((REPO / "deploy").glob("*/deploy.sh")))
def test_todo_deploy_sh_es_EJECUTABLE(guion: Path) -> None:
    """El bit de ejecución se pierde en silencio y git lo arrastra al commit.

    `deploy/landing/deploy.sh` llegó a `main` en 644 —el único de los tres— porque
    una comprobación de mutación hizo `mv` de un temporal de `/tmp` encima suyo:
    `mv` se trae el modo del origen, y el `cp` de restauración conserva el del
    destino, así que restaurar el CONTENIDO no restauró el MODO. Nada falló: el
    Makefile invoca con `bash`, y el cambio sólo aparece como una línea
    `mode change 100755 => 100644` al final de un diff que nadie relee.

    El censo lo pone el árbol, no una lista: un `deploy/<algo>/deploy.sh` nuevo
    también tiene que poder ejecutarse por sí mismo.
    """
    assert guion.stat().st_mode & 0o111, (
        f"{guion.relative_to(REPO)} no es ejecutable (chmod 755). Suele ser un "
        "`mv` de /tmp encima del fichero; `git ls-files -s deploy/` lo enseña"
    )
