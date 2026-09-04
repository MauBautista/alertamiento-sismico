# GUION DE DEMOSTRACIÓN — qué se enseña, en qué orden, y qué NO se toca

> **Para quién es esto.** Para quien va a enseñar TAKAB Ailert delante de alguien que no
> lo conoce. No es documentación del producto: es el recorrido, con las frases que se
> pueden decir y las que no.
>
> **La fuente de lo que NO se puede decir es
> [`takab-docs/INFORME-V1-COMERCIAL.md §3`](../takab-docs/INFORME-V1-COMERCIAL.md), y este
> documento la cita literalmente.** Si las dos discrepan, gana el informe.

---

## 0. Antes de empezar (5 minutos, sin público delante)

```bash
make soc-local        # consola + API + worker + UN gabinete real simulado
```

Comprueba **tres cosas** antes de que entre nadie:

1. **El mapa dice `DEMO`** en los sitios. Si no lo dice, estás mirando datos reales:
   para y averigua por qué (`T-5.05` deriva el rótulo del prefijo del código).
2. **El banner de MODO DEMOSTRACIÓN está puesto** (`T-5.02`). Mientras esté, no sale
   ninguna entrega por ningún canal ni ningún comando de actuador firmado.
3. **El panel del gabinete está en `http://<pi>:8080`** y lo vas a enseñar **en solo
   lectura**.

Para la acreditación scripted (3 gabinetes, 38 comprobaciones, sin público):

```bash
make demo-fase1       # enciende el modo demostración él solo y lo verifica
```

---

## 1. El recorrido, en orden

### Escena 1 · El edificio siente un sismo (2 min)

```bash
curl -X POST http://127.0.0.1:9100/quake
```

**Qué se ve:** el mapa colorea el sitio por lo que MIDIÓ su sensor; la ficha del sitio
trae serial, firmware, modelo del sismógrafo y respaldo eléctrico (`T-5.26`).

**Qué se dice:** *«El sistema mide lo que pasó en su edificio y lo dice con sus
unidades.»*

**Qué NO se dice:** ~~*«Le decimos la magnitud y el epicentro del sismo.»*~~ La magnitud
**nunca se escribe** en la base; el receptor entrega un booleano. Si preguntan por el
epicentro: *«La magnitud y el epicentro los publica la fuente oficial; contrastarlos
automáticamente es trabajo en curso.»*

**Y ojo con esta, que es contraintuitiva:** una detección instrumental de **una sola
estación NO acciona nada** — avisa. Es política ratificada (`T-2.32`), no una carencia.
Se dice así: *«Una estación sola avisa; para accionar el edificio hacen falta SASMEX o
tres inmuebles de acuerdo.»*

### Escena 2 · Llega la alerta SASMEX (3 min)

```bash
curl -X POST http://127.0.0.1:9100/sasmex
```

**Qué se ve:** los cinco canales de actuación se activan y el panel del gabinete lo
muestra con la latencia del reflejo medida.

**Qué se dice:** *«El sistema tiene cinco canales de actuación y un adaptador para el
equipamiento del edificio. En la unidad de referencia están cableados sirena y estrobo;
gas, ascensores y puertas se acreditan canal por canal en la puesta en marcha.»*

**Qué NO se dice:** ~~*«El sistema cierra la válvula de gas, retorna los ascensores y
libera las puertas.»*~~ Ningún gabinete tiene esos canales cableados.

### Escena 3 · Se va el internet (3 min) — **la escena que más convence**

```bash
curl -X POST http://127.0.0.1:9100/wan/off
curl -X POST http://127.0.0.1:9100/sasmex
```

**Qué se ve:** la protección local ocurre **igual**, la cola durable crece y nada sale
del gabinete. Al reconectar, todo drena sin duplicados.

**Qué se dice:** *«El camino que protege el edificio no pasa por la nube ni por
internet.»*

**Qué NO se dice:** ~~*«Si el gabinete se apaga, la sirena suena igual por hardware.»*~~
Esa ruta eléctrica **no está construida**. Se dice: *«La ruta de hardware está diseñada y
decidida, y es parte de la instalación. Hasta que se acredite en el inmueble, no dé por
hecho que la sirena suena con la computadora muerta.»*

### Escena 4 · El dictamen (3 min)

**Qué se ve:** el documento ejecutivo y el técnico, con su huella de contenido y la
cadena de custodia con los hashes completos (`T-5.26`).

**Qué se dice:** *«El dictamen técnico trae la envolvente por canal y las métricas
medidas.»*

**Qué NO se dice:** ~~*«Este es el espectrograma del sismo.»*~~ Existe desde `T-5.23`,
**pero en la nube real la sección sale vacía siempre** porque el worker que archiva la
onda no está desplegado (`T-3.11.c`). En local sí se ve; no prometas que se verá allá.

Tampoco: ~~*«El sistema cumple con la norma X.»*~~ *«El sistema muestra el marco
normativo que usted declare, con el deslinde de que TAKAB no lo respalda.»*

### Escena 5 · El simulacro (5 min)

**Qué se dice:** *«El simulacro se agenda, y a la hora el botón queda armado para que una
persona autorizada lo dispare. Un sistema que abre gas y mueve ascensores no se dispara
solo.»*

**Qué NO se dice:** ~~*«Le programo el simulacro y suena solo a las 11:00.»*~~ **No existe
disparo por hora, y es correcto que no exista** (regla de oro 8).

> ⚠️ **Esta escena todavía no está guionizada en `demo/run.py`.** Ver «Lo que este guion
> no cubre», abajo.

---

## 2. Lo que NO se toca, pase lo que pase

| No tocar | Por qué |
|---|---|
| Los botones del panel del gabinete | Hasta `T-5.01` **mandaban órdenes de verdad**. Ya no, pero el recorrido es en **solo lectura**: un actuador no es una diapositiva. |
| El entorno desplegado | La demo es local. `db/seeds/sim_fleet.sql` declara en su cabecera que **jamás** se aplica a la nube. |
| Apagar el modo demostración | Mientras esté puesto, nada sale por ningún canal. Se apaga solo al vencer — o lo apaga un evento **real**, que es lo correcto. |

**Y las dos frases que nunca, en ninguna escena:**

- ~~*«Le llega un SMS / un WhatsApp / una notificación al teléfono.»*~~ Los tres canales
  están en simulado por falta de altas administrativas. *«Hoy entregan el correo y el
  webhook.»*
- ~~*«Sus datos no salen de México.»*~~ Viven en Ohio. *«Hay un análisis escrito de por
  qué no migramos todavía»* (`RESIDENCIA-DE-DATOS-TAKAB.md`).

---

## 3. Lo que este guion NO cubre (y por qué)

**La escena de simulacro no está scripted en `demo/run.py`.** El motivo es del arnés, no
del producto: el sustituto de IoT Core de la demo (`demo/spool.py`) es **solo
edge→nube**. Un simulacro son *comandos firmados de nube a gabinete*, uno por sitio, y
ese camino de bajada **no existe en la demo**. Lo que sí se puede recorrer a mano es la
mitad de nube (agenda, armado, disparo, acuse por sitio y reporte) en `make soc-local`,
donde la API y la consola están vivas.

Construir el enlace de bajada de la demo es trabajo aparte y está fichado.

**Y lo que la demo no acredita, dicho antes de que lo pregunten:** relés MOCK, sin WR-1
físico ni sirena cableada. La latencia que mide es la de la ruta **software**. El
presupuesto físico `<100 ms` se acredita con hardware y **esta demo no lo acredita**
(`G-04`).
