/* Arnés de render del PANEL DEL GABINETE (edge/takab_edge/local_api/index.html).
 *
 * ¿Por qué un arnés en Node dentro de una suite de Python? Porque hasta aquí el
 * panel solo se probaba por COINCIDENCIA DE CADENAS sobre el HTML servido
 * ("¿aparece el literal X?"). Eso caza que alguien borre un rótulo, pero NO caza
 * lo que de verdad importa a alguien de pie frente al gabinete: que una zona se
 * pinte, que un botón responda, y sobre todo que un dato VIEJO se vea viejo
 * (regla de oro 7). Ese comportamiento vive en `render()`, y `render()` es
 * JavaScript: para ejercitarlo hay que EJECUTARLO.
 *
 * Cero dependencias a propósito (nada de jsdom): el job `edge` del CI corre
 * `uv sync` y no instala node_modules de nadie. Node sí está en el runner y en
 * el equipo de desarrollo; el DOM que el panel necesita es pequeño y explícito,
 * y escribirlo a mano deja documentado EXACTAMENTE qué superficie del navegador
 * asume el panel. Si el panel empezara a usar algo que no está aquí, el arnés
 * revienta en vez de mentir.
 *
 * Uso:  node panel_harness.js <ruta index.html> <ruta config.json>
 * Sale: JSON por stdout con el árbol renderizado, las peticiones observadas y
 *       los errores; cualquier excepción se reporta, jamás se traga.
 *
 * [T-2.85.a] MODO LOTE. Si la configuración trae `cases: [{id, ...cfg}, …]` se
 * renderiza CADA caso en su propio contexto (mismo proceso) y sale
 * `{cases: [{id, tree, errors, …}, …]}`. Lo pide el censo de campos sin camino
 * de render: son ~120 renders y a 78 ms de proceso serían 9 s de suite.
 * `cfg.now` congela el reloj del panel — sin eso dos renders del MISMO status
 * difieren en el `hh:mm:ss` de la cabecera y todo el censo sería ruido.
 */

'use strict';

const fs = require('fs');
const vm = require('vm');

/* ============================ mini-DOM ============================ */
/* No es un navegador: es la lista EXACTA de lo que el panel toca. */

const VOID_TAGS = new Set(['meta', 'link', 'br', 'hr', 'img', 'input', 'source']);

class Style {
  constructor() {
    this._raw = {};
  }
  get cssText() {
    return this._raw.cssText || '';
  }
  set cssText(v) {
    this._raw.cssText = v;
  }
}
/* Las propiedades sueltas (color, background, width…) se guardan tal cual: el
   panel las ESCRIBE para señalizar estado (ámbar = degradado) y el test las LEE. */
const styleHandler = {
  get(target, prop) {
    if (prop === 'cssText') return target.cssText;
    if (typeof prop === 'symbol') return target[prop];
    return target._raw[prop] === undefined ? '' : target._raw[prop];
  },
  set(target, prop, value) {
    if (prop === 'cssText') target.cssText = value;
    else target._raw[prop] = value;
    return true;
  },
};

class ClassList {
  constructor(el) {
    this.el = el;
  }
  _set() {
    return new Set(this.el._class.split(/\s+/).filter(Boolean));
  }
  _write(s) {
    this.el._class = Array.from(s).join(' ');
  }
  add(c) {
    const s = this._set();
    s.add(c);
    this._write(s);
  }
  remove(c) {
    const s = this._set();
    s.delete(c);
    this._write(s);
  }
  contains(c) {
    return this._set().has(c);
  }
  toggle(c, force) {
    const on = force === undefined ? !this.contains(c) : !!force;
    if (on) this.add(c);
    else this.remove(c);
    return on;
  }
}

class Element {
  constructor(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.parentNode = null;
    this._class = '';
    this._text = ''; // texto propio (nodo de texto directo)
    this.dataset = {};
    this.attrs = {};
    this.style = new Proxy(new Style(), styleHandler);
    this.classList = new ClassList(this);
    this.listeners = {};
    this.value = '';
    /* Geometría: los canvas piden ancho/alto y con 0 el panel se salta el
       dibujo (`fitCanvas` devuelve null). Un tamaño realista ejercita el
       camino de verdad, que es donde vive el riesgo. */
    this.clientWidth = 900;
    this.clientHeight = 420;
    this.width = 0;
    this.height = 0;
  }
  get id() {
    return this.attrs.id || '';
  }
  get className() {
    return this._class;
  }
  set className(v) {
    this._class = String(v || '');
  }
  get textContent() {
    return this._text + this.children.map((c) => c.textContent).join('');
  }
  set textContent(v) {
    /* Igual que el DOM real: asignar texto DESTRUYE los hijos. El panel usa
       `el.textContent = ''` como "vaciar la zona" antes de repintar. */
    this.children.forEach((c) => {
      c.parentNode = null;
    });
    this.children = [];
    this._text = v === null || v === undefined ? '' : String(v);
  }
  appendChild(node) {
    node.parentNode = this;
    this.children.push(node);
    return node;
  }
  append(...nodes) {
    nodes.forEach((n) => this.appendChild(n));
  }
  addEventListener(type, fn) {
    (this.listeners[type] = this.listeners[type] || []).push(fn);
  }
  getContext() {
    return makeCtx(this.attrs.id || this.tagName);
  }
  getBoundingClientRect() {
    return { width: this.clientWidth, height: this.clientHeight, top: 0, left: 0 };
  }
}

/* Contexto 2D de mentira: registra que se llamó y devuelve lo mínimo con
   sentido. El test NO afirma píxeles (sería frágil y no dice nada operativo);
   afirma que el dibujo CORRE SIN REVENTAR y qué textos se estampan — que es
   donde el canvas sí comunica ("SIN SEÑAL DEL SENSOR", "PUNTO 0 FIJADO"…).
   [T-7.05 · P-2] Y ahora también DÓNDE. No son píxeles: es la geometría que el
   panel PIDE (los extremos de cada trazo, la caja de cada relleno, la línea
   base de cada texto), que es lo único que hace falta para responder «¿pinta
   algo dentro de la banda de rótulos del carril?» — la pregunta de U-10, que
   hasta aquí solo sabía contestar un navegador de verdad. Un rasterizador aquí
   sería fingir una medida; una lista de órdenes con sus coordenadas es
   exactamente lo que el panel dijo. */
const CANVAS_TEXT = [];
const CANVAS_OPS = [];
function makeCtx(lienzo) {
  const noop = () => {};
  /* El trazo se acumula como el de un canvas real: `beginPath` abre, los
     `moveTo`/`lineTo` encadenan y `stroke()` es el que pinta. Registrar el
     `lineTo` sin esperar al `stroke` delataría como tinta un camino que nadie
     llegó a pintar. */
  let camino = [];
  let cursor = null;
  const ctx = {
    setTransform: noop,
    clearRect: noop,
    beginPath: () => {
      camino = [];
      cursor = null;
    },
    moveTo: (x, y) => {
      cursor = [x, y];
    },
    lineTo: (x, y) => {
      if (cursor) camino.push([cursor[0], cursor[1], x, y]);
      cursor = [x, y];
    },
    stroke: () => {
      for (const s of camino) {
        CANVAS_OPS.push({ lienzo, op: 'stroke', x0: s[0], y0: s[1], x1: s[2], y1: s[3], lw: ctx.lineWidth, alpha: ctx.globalAlpha, color: String(ctx.strokeStyle) });
      }
    },
    arc: (cx, cy, r) => {
      camino.push([cx - r, cy - r, cx + r, cy + r]);
      cursor = null;
    },
    fill: noop,
    fillRect: (x, y, w, h) => {
      CANVAS_OPS.push({ lienzo, op: 'fillRect', x0: x, y0: y, x1: x + w, y1: y + h, alpha: ctx.globalAlpha, color: String(ctx.fillStyle) });
    },
    strokeRect: (x, y, w, h) => {
      CANVAS_OPS.push({ lienzo, op: 'strokeRect', x0: x, y0: y, x1: x + w, y1: y + h, alpha: ctx.globalAlpha, color: String(ctx.strokeStyle) });
    },
    closePath: noop,
    setLineDash: noop,
    save: noop,
    restore: noop,
    fillText: (t, x, y) => {
      CANVAS_TEXT.push(String(t));
      /* La caja del texto se deriva del cuerpo declarado en `ctx.font`: un
         glifo se pinta HACIA ARRIBA de su línea base, así que la tinta ocupa
         desde `y - cuerpo` hasta `y` (la cota alta: el descendente se ignora
         porque lo que se persigue es lo que sube hacia el rótulo). */
      const cuerpo = parseFloat((/(\d+(?:\.\d+)?)px/.exec(String(ctx.font)) || [0, 0])[1]) || 0;
      CANVAS_OPS.push({ lienzo, op: 'fillText', txt: String(t), x0: x, y0: y - cuerpo, x1: x + String(t).length * cuerpo * 0.6, y1: y, alpha: ctx.globalAlpha, color: String(ctx.fillStyle) });
    },
    measureText: (t) => ({ width: String(t).length * 6 }),
    strokeStyle: '',
    fillStyle: '',
    lineWidth: 1,
    lineCap: '',
    font: '',
    globalAlpha: 1,
  };
  return ctx;
}

/* --------- parser de HTML suficiente para el esqueleto del panel --------- */
function parseBody(html) {
  const bodyStart = html.indexOf('<body>');
  const scriptStart = html.indexOf('<script>');
  if (bodyStart < 0 || scriptStart < 0) throw new Error('index.html sin <body>/<script>');
  let frag = html.slice(bodyStart + '<body>'.length, scriptStart);
  frag = frag.replace(/<!--[\s\S]*?-->/g, '');

  const root = new Element('body');
  root.attrs.id = '__body__';
  const stack = [root];
  const byId = {};
  const withData = [];
  const re = /<\/([a-zA-Z0-9]+)\s*>|<([a-zA-Z0-9]+)((?:[^>"]|"[^"]*")*)>|([^<]+)/g;
  let m;
  while ((m = re.exec(frag)) !== null) {
    const top = stack[stack.length - 1];
    if (m[1]) {
      if (stack.length > 1) stack.pop();
    } else if (m[2]) {
      const el = new Element(m[2]);
      const attrRe = /([a-zA-Z0-9_:-]+)\s*=\s*"([^"]*)"/g;
      let a;
      while ((a = attrRe.exec(m[3] || '')) !== null) {
        el.attrs[a[1]] = a[2];
        if (a[1] === 'class') el._class = a[2];
        if (a[1] === 'value') el.value = a[2];
        if (a[1].startsWith('data-')) {
          const key = a[1]
            .slice(5)
            .replace(/-([a-z])/g, (_, c) => c.toUpperCase());
          el.dataset[key] = a[2];
          withData.push(el);
        }
      }
      top.appendChild(el);
      if (el.attrs.id) byId[el.attrs.id] = el;
      if (!VOID_TAGS.has(m[2].toLowerCase())) stack.push(el);
    } else if (m[4]) {
      const txt = m[4].replace(/\s+/g, ' ');
      if (txt.trim()) top._text += txt;
    }
  }
  return { root, byId, withData };
}

/* ============================ arranque ============================ */
const [, , htmlPath, cfgPath] = process.argv;
const html = fs.readFileSync(htmlPath, 'utf8');
const cfgRoot = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));

function jsonResponse(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

/* [T-2.85.a] Reloj congelado. El panel estampa `hh:mm:ss UTC` en la cabecera y
   en varios rótulos: sin congelarlo, dos renders del MISMO status difieren y el
   censo de campos sin camino de render mediría el segundero, no el campo. */
function frozenDate(iso) {
  const FIXED = new Date(iso).getTime();
  return class extends Date {
    constructor(...args) {
      if (args.length === 0) super(FIXED);
      else super(...args);
    }
    static now() {
      return FIXED;
    }
  };
}

const SCRIPT = html.slice(html.indexOf('<script>') + '<script>'.length, html.lastIndexOf('</script>'));

/* `tick()` es async: una excepción dentro de `render()` sale como PROMESA
   RECHAZADA, y node mata el proceso entero. El arnés la recoge y la reporta como
   un error del caso — que es la verdad operativa: el panel se quedó a medio
   repintar mostrando el estado ANTERIOR (regla de oro 7). Antes esto era un
   `Node.js v24` en stderr y ningún test que lo nombrara. */
const REJECTIONS = [];
process.on('unhandledRejection', (err) => {
  REJECTIONS.push('promesa: ' + (err && err.message ? err.message : String(err)));
});

/**
 * Renderiza el panel UNA vez con esta configuración, en su propio contexto.
 *
 * Todo el estado (DOM, colas, errores) es local a la llamada: es lo que permite
 * el modo lote sin que un caso contamine al siguiente.
 */
async function render(cfg) {
  CANVAS_TEXT.length = 0;
  CANVAS_OPS.length = 0;
  REJECTIONS.length = 0;
  const { root: body, byId, withData } = parseBody(html);

  /* Guarda de sanidad del parser: si el esqueleto trae un id que el parser no
     registró, TODO lo demás sería un falso verde. Mejor romper aquí. */
  const declaredIds = Array.from(html.slice(0, html.indexOf('<script>')).matchAll(/\sid="([^"]+)"/g))
    .map((x) => x[1])
    .filter((x) => x !== 'pin' || true);
  const missing = declaredIds.filter((i) => !byId[i]);
  if (missing.length) return { fatal: 'ids no parseados: ' + missing.join(',') };

  /* [T-7.05 · P-2] `sizes: {"wave-canvas": [412, 468]}` le da a un elemento la
     geometría que el caso quiera. Sin esto todo mide 900×420 y un test sobre la
     geometría del lienzo estaría afirmando sobre un tamaño que no existe en
     ningún gabinete: el que importa es el de CAMPO, y su alto lo declara la
     hoja (`body.mode-campo #waves-wrap{min-height:468px}`). Quien lo pide lo
     leyó de ahí; el arnés no lo inventa. */
  for (const [id, wh] of Object.entries(cfg.sizes || {})) {
    if (!byId[id]) return { fatal: 'sizes: el panel no tiene #' + id };
    byId[id].clientWidth = wh[0];
    byId[id].clientHeight = wh[1];
  }

  const errors = [];
  const fetches = [];
  const timeouts = [];
  const rafs = [];

  const document = {
    body,
    getElementById: (id) => byId[id] || null,
    createElement: (tag) => new Element(tag),
    querySelectorAll: (sel) => {
      const m = /^\[data-([a-z-]+)\]$/.exec(sel);
      if (!m) return [];
      const key = m[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      return withData.filter((el) => el.dataset[key] !== undefined);
    },
    addEventListener: () => {},
  };

  const windowObj = {
    innerWidth: cfg.innerWidth || 1920,
    devicePixelRatio: 1,
    addEventListener: () => {},
  };

  /* [T-7.05] Este mini-DOM no tiene motor de estilo ni de layout: toda custom
     property sale SIN VALOR por defecto, igual que en un navegador donde nadie
     la declaró — que es lo que pasa en MURO y en CONSOLA, donde `--lane-band`
     no se declara y `laneBand()` cae a 0.
     `cfg.customProps` DECLARA las que el caso quiera, y el test las saca de la
     HOJA en vez de teclearlas: es lo que permite ejercitar la geometría de
     CAMPO (`body.mode-campo #lanes{--lane-band:48px}`) sin un navegador. El
     arnés no inventa el valor; lo recibe de quien lo leyó del CSS.
     Se CUENTAN las llamadas: `laneBand()` vive dentro de `requestAnimationFrame`
     y leer el estilo calculado una vez por fotograma —60 veces por segundo, con
     el árbol sucio de `renderLanes()`— es lo que corrigió T-7.05. Contarlas es
     la única forma de que el arreglo tenga una prueba que falle si se deshace. */
  let computedStyleCalls = 0;
  const CUSTOM = cfg.customProps || {};
  const getComputedStyle = () => {
    computedStyleCalls += 1;
    return { getPropertyValue: (prop) => (CUSTOM[prop] === undefined ? '' : String(CUSTOM[prop])) };
  };

  const Reloj = cfg.now ? frozenDate(cfg.now) : Date;

  const sandbox = {
    document,
    window: windowObj,
    getComputedStyle,
    location: { search: cfg.search || '' },
    performance: { now: () => Reloj.now() },
    console: { log: () => {}, warn: () => {}, error: () => {} },
    URLSearchParams,
    Math,
    Date: Reloj,
    JSON,
    Set,
    Map,
    Object,
    Array,
    String,
    Number,
    Boolean,
    Error,
    isNaN,
    parseInt,
    parseFloat,
    Float32Array,
    Uint8Array,
    Promise,
    setTimeout: (fn) => {
      /* El tick se re-arma solo (`setTimeout(tick, backoff)`). Encolar en vez de
         ejecutar es lo que impide que el arnés gire para siempre. */
      timeouts.push(fn);
      return timeouts.length;
    },
    clearTimeout: () => {},
    requestAnimationFrame: (fn) => {
      rafs.push(fn);
      return rafs.length;
    },
    cancelAnimationFrame: () => {},
    fetch: async (url, opts) => {
      const method = (opts && opts.method) || 'GET';
      /* Las cabeceras se registran a propósito: "sin PIN capturado NO se manda el
         header" es un invariante del panel (un header vacío quemaba intentos del
         lockout), y solo se puede afirmar viéndolas. */
      fetches.push({ url: String(url), method, headers: (opts && opts.headers) || {} });
      const path = String(url).split('?')[0];
      if (method === 'POST') {
        const st = (cfg.actionStatus || {})[path];
        if (st === 'network') throw new Error('sin red');
        return jsonResponse(st || 200, { ok: true });
      }
      if (path === 'api/status') {
        if (cfg.statusStatus && cfg.statusStatus !== 200) return jsonResponse(cfg.statusStatus, {});
        if (cfg.statusNetworkFail) throw new Error('sin red');
        return jsonResponse(200, cfg.status);
      }
      if (path === 'api/waveform') return jsonResponse(200, cfg.waveform || { cursor: 0, reset: false, channels: {} });
      if (path === 'api/catalog') return jsonResponse(200, cfg.catalog || { available: false });
      return jsonResponse(404, {});
    },
  };
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;

  const script = SCRIPT;

  try {
    vm.createContext(sandbox);
    vm.runInContext(script, sandbox, { filename: 'panel.js' });
  } catch (err) {
    errors.push('carga: ' + err.message);
  }

  /* Deja asentar la cadena de `await` de tick() (status → waveform → catálogo). */
  const settle = async (n) => {
    for (let i = 0; i < (n || 30); i++) await new Promise((r) => setImmediate(r));
  };
  await settle();

  /* El PIN se teclea DESPUÉS de cargar (vive en memoria, jamás se guarda). */
  if (cfg.pin !== undefined) byId['pin'].value = cfg.pin;

  /* [T-7.05] Rompe un dibujo A PROPÓSITO. Es la única forma de ejercitar el
     `catch` de `frame()`, que hasta esta ficha estaba VACÍO: de los cuatro
     lienzos del fotograma sólo el de ondas se limpia solo (`fitCanvas()` hace
     su `clearRect` al entrar), así que la brújula y el mapa se quedaban con el
     fotograma anterior intacto y el panel seguía pareciendo vivo. El script del
     panel corre EN ESTE contexto, así que sus `function` de primer nivel son
     propiedades del global y `frame()` resuelve el nombre al llamarlo:
     sustituirla aquí es sustituir la que se va a ejecutar. */
  if (cfg.breakDraw) {
    sandbox[cfg.breakDraw] = () => {
      throw new Error('dibujo roto a propósito · ' + cfg.breakDraw);
    };
  }

  /* Un frame: ejercita drawWaves/drawRose (y el mapa si el overlay está abierto). */
  const runFrame = () => {
    const fn = rafs.shift();
    if (!fn) return;
    /* [T-7.05 · P-2] La geometría que se devuelve es la del ÚLTIMO fotograma.
       Acumularla entre fotogramas mezclaría dos estados —el panel arranca en la
       variante A y el caso puede conmutar a la B, que reparte los carriles
       1:3:1:1— y cualquier afirmación sobre las pistas estaría comparando las
       órdenes de un reparto contra la geometría del otro. */
    if (cfg.canvasOps) CANVAS_OPS.length = 0;
    try {
      fn();
    } catch (err) {
      errors.push('frame: ' + err.message);
    }
  };
  runFrame();
  /* `frames` pide más fotogramas SIN tocar nada entre medias: es el escenario
     en el que el panel está quieto delante de un operador, que es el 99.9 % de
     su vida y donde se mide el coste por fotograma. */
  for (let i = 1; i < (cfg.frames || 1); i++) runFrame();

  /* --------- interacción: los clics que pide la configuración --------- */
  const clickById = (id) => {
    const el = byId[id];
    if (!el) {
      errors.push('clic sobre id inexistente: ' + id);
      return;
    }
    (el.listeners.click || []).forEach((fn) => {
      try {
        fn();
      } catch (err) {
        errors.push('clic ' + id + ': ' + err.message);
      }
    });
  };
  const clickByData = (attr, value) => {
    const key = attr.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const el = withData.find((e) => e.dataset[key] === value);
    if (!el) {
      errors.push('clic sobre data-' + attr + '=' + value + ' inexistente');
      return;
    }
    (el.listeners.click || []).forEach((fn) => fn());
  };
  const clickAction = (label) => {
    const box = byId['action-btns'];
    const btn = box.children.find((b) => b.textContent.startsWith(label));
    if (!btn) {
      errors.push('botón de acción no encontrado: ' + label);
      return;
    }
    (btn.listeners.click || []).forEach((fn) => fn());
  };
  /* Segundo clic del armado: tras armar, el botón CAMBIA de rótulo — buscarlo
     otra vez por su nombre original no lo encontraría. */
  const clickArmed = () => {
    const box = byId['action-btns'];
    const btn = box.children.find((b) => b.textContent.startsWith('CLIC NUEVAMENTE'));
    if (!btn) {
      errors.push('no hay ningún botón armado que confirmar');
      return;
    }
    (btn.listeners.click || []).forEach((fn) => fn());
  };
  const clickFirstIn = (containerId) => {
    const box = byId[containerId];
    const btn = box.children[0];
    if (!btn) {
      errors.push('sin filas en ' + containerId);
      return;
    }
    (btn.listeners.click || []).forEach((fn) => fn());
  };

  for (const step of cfg.clicks || []) {
    if (step.startsWith('#')) clickById(step.slice(1));
    else if (step.startsWith('data:')) {
      const [, attr, value] = step.split(':');
      clickByData(attr, value);
    } else if (step.startsWith('action:')) clickAction(step.slice('action:'.length));
    else if (step === 'confirm') clickArmed();
    else if (step.startsWith('row:')) clickFirstIn(step.slice('row:'.length));
    else if (step === 'frame') runFrame();
    else if (step === 'tick') {
      /* Un ciclo más del poll: es la única forma de llegar a los estados de
         conexión que dependen del CONTADOR de fallos (2 = dato retenido,
         3 = sin conexión). */
      const fn = timeouts.shift();
      if (fn) {
        try {
          fn();
        } catch (err) {
          errors.push('tick: ' + err.message);
        }
      }
    } else if (step === 'settle') await settle(10);
    else errors.push('paso desconocido: ' + step);
    await settle(6);
  }
  if (cfg.finalFrame) runFrame();

  /* --------------------------- instantánea --------------------------- */
  const dump = (el, depth) => ({
    tag: el.tagName,
    id: el.attrs.id || '',
    cls: el._class,
    txt: el._text,
    color: el.style.color || '',
    bg: el.style.background || '',
    /* [T-2.85.a] `cssText` también. El panel señaliza estado por ahí (el punto
       de color de cada gabinete LoRa se pinta con `style.cssText = '…background:'
       + dotColor`), y sin esto el censo de campos sin camino de render leía como
       "no se pinta" un campo que sí cambia de color. */
    css: el.style.cssText || '',
    /* [T-7.05 · P-2] Las TRES formas de declarar un cuerpo inline, que es lo que
       mata en silencio a una regla `body.mode-*`: el atributo `style=` del
       marcado, el `style.cssText` que escribe el JS y la propiedad suelta
       `style.font`/`style.fontSize`. Van juntas porque el censo que las vigila
       se deriva de la hoja y no sabe de antemano cuál de las tres usó quien
       escribió el elemento. */
    inline: el.attrs.style || '',
    font: el.style.font || '',
    fontSize: el.style.fontSize || '',
    kids: depth > 0 ? el.children.map((c) => dump(c, depth - 1)) : [],
  });

  /* Las promesas rechazadas se drenan al final: node las entrega en un turno
     posterior al `await`, así que antes de este punto todavía no están. */
  await new Promise((r) => setImmediate(r));

  return {
    tree: dump(body, 12),
    canvasText: CANVAS_TEXT.slice(),
    /* La geometría del canvas SOLO va de vuelta si se pide: son ~200 órdenes
       por fotograma y el censo de render hace ~120 casos en un lote. */
    canvasOps: cfg.canvasOps ? CANVAS_OPS.slice() : undefined,
    computedStyleCalls,
    fetches,
    pendingTimeouts: timeouts.length,
    errors: errors.concat(REJECTIONS),
  };
}

(async () => {
  if (Array.isArray(cfgRoot.cases)) {
    /* Modo lote (T-2.85.a). El `id` viaja de vuelta SIEMPRE: quien lo lee tiene
       que poder confirmar que el caso que pidió es el caso que se renderizó, en
       vez de inferirlo del orden de la lista. */
    const out = [];
    for (const caso of cfgRoot.cases) {
      const base = Object.assign({}, cfgRoot.base || {}, caso);
      let res;
      try {
        res = await render(base);
      } catch (err) {
        res = { fatal: 'render: ' + err.message, errors: [] };
      }
      out.push(Object.assign({ id: caso.id }, res));
    }
    process.stdout.write(JSON.stringify({ cases: out }));
    return;
  }
  process.stdout.write(JSON.stringify(await render(cfgRoot)));
})();
