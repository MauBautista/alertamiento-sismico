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

**Qué se enseña, y ya está guionizado** (`demo/run.py`, escena **C4**, desde `T-5.29`):
la agenda, el armado, el disparo humano, la bajada del **comando firmado** a cada
gabinete, el acuse por sitio y el reporte con su `sha256`. Los tres gabinetes son
`EdgeSupervisor` reales y quien decide si el comando se ejecuta es su
`CommandDispatcher` —el mismo código que corre en el Pi—, que verifica HMAC, nonce y
ventana **antes de tocar nada**.

**La mitad que hace creíble la otra:** la escena mete además un comando con la firma
cambiada, y el gabinete **lo rechaza sin acusar** — a un emisor no autenticado no se le
responde (regla de oro 8). Queda en la bitácora del propio gabinete.

> ⚠️ **Con el modo demostración puesto NO se puede enseñar un simulacro, y es correcto.**
> `D-27` dice que el modo es «un supresor de salida de la nube: notificaciones y comandos
> firmados», y un simulacro **es** un comando firmado. La consecuencia operativa, que no
> estaba escrita en ninguna parte hasta `T-5.29`: para enseñar esta escena delante de un
> cliente hay que **apagar la ventana** primero, y volver a ponerla al terminar. El guion
> lo hace explícito y ruidoso, y enseña antes la supresión con su fila de auditoría.
>
> Y un detalle que conviene conocer antes de que lo vea el cliente: con el modo puesto el
> simulacro **se registra igual** —201, sus tres sitios, cero comandos—, porque el alta es
> best-effort por sitio (un gabinete sin clave no puede dejar sin simulacro a los demás).
> Que no sonó en ninguna parte se ve **después**, en el reporte (`no acusaron`), no en el
> momento de dispararlo.

---

## 2. Lo que NO se toca, pase lo que pase

| No tocar | Por qué |
|---|---|
| Los botones del panel del gabinete | Hasta `T-5.01` **mandaban órdenes de verdad**. Ya no, pero el recorrido es en **solo lectura**: un actuador no es una diapositiva. |
| El entorno desplegado | La demo es local. `db/seeds/sim_fleet.sql` declara en su cabecera que **jamás** se aplica a la nube. |
| Apagar el modo demostración | Mientras esté puesto, nada sale por ningún canal. Se apaga solo al vencer — o lo apaga un evento **real**, que es lo correcto. **La única excepción es la escena 5**: para enseñar un simulacro hay que levantar la ventana, y se vuelve a poner al terminar. |

**Y las dos frases que nunca, en ninguna escena:**

- ~~*«Le llega un SMS / un WhatsApp / una notificación al teléfono.»*~~ Los tres canales
  están en simulado por falta de altas administrativas. *«Hoy entregan el correo y el
  webhook.»*
- ~~*«Sus datos no salen de México.»*~~ Viven en Ohio. *«Hay un análisis escrito de por
  qué no migramos todavía»* (`RESIDENCIA-DE-DATOS-TAKAB.md`).

---

## 3. Lo que este guion NO cubre (y por qué)

~~**La escena de simulacro no está scripted en `demo/run.py`.**~~ **Cerrado por `T-5.29`.**
El sustituto de IoT Core de la demo era **solo edge→nube** y por eso no había por dónde
bajar un comando firmado. Ahora `demo/spool.py` tiene las dos direcciones y la escena C4
recorre el simulacro entero. Lo que la bajada **no** hace, y es lo que la hace válida:
no firma, no verifica y no interpreta — entrega el envelope intacto y decide el
dispatcher del gabinete.

**Lo que sigue sin cubrir la demo del edge:** la autenticación. En C4 el operador es un
`Claims` construido a mano, igual que las otras escenas construyen su `IncidentEngine`:
la demo no levanta Cognito en ninguna. Lo que C4 acredita es el camino del **comando**,
no el del token. Para recorrer la consola con sesión real está `make soc-local`.

**Y lo que la demo no acredita, dicho antes de que lo pregunten:** relés MOCK, sin WR-1
físico ni sirena cableada. La latencia que mide es la de la ruta **software**. El
presupuesto físico `<100 ms` se acredita con hardware y **esta demo no lo acredita**
(`G-04`).
