// JS único de la landing: revelado de escenas, pausa de instrumentos fuera de
// pantalla y repetición del esquema. Presupuesto: < 3 KB gz.
// Sin este script la página es completa y estática (todo visible).

const reduceMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)",
).matches;

// Marca "hay JS": los estados ocultos de [data-rv] solo existen bajo .js,
// así que sin JS nada queda invisible.
document.documentElement.classList.add("js");

// --- Control explícito para ciclos de movimiento prolongados ---
// Además de respetar prefers-reduced-motion, permite pausar los instrumentos
// sin perder el contexto visual de la página.
const motionToggle = document.querySelector<HTMLButtonElement>(
  "[data-motion-toggle]",
);
const motionLabel = motionToggle?.querySelector<HTMLElement>(
  "[data-motion-label]",
);

function setMotionPaused(paused: boolean): void {
  document.documentElement.classList.toggle("motion-paused", paused);
  motionToggle?.setAttribute("aria-pressed", String(paused));
  if (motionLabel) {
    motionLabel.textContent = paused
      ? "Reanudar movimiento"
      : "Pausar movimiento";
  }
  window.dispatchEvent(new CustomEvent("takab:motion", { detail: { paused } }));
}

motionToggle?.addEventListener("click", () => {
  setMotionPaused(
    !document.documentElement.classList.contains("motion-paused"),
  );
});

// El menú nativo funciona sin JS; al elegir un destino cerramos únicamente la
// capa desplegada para devolver espacio y foco visual al contenido.
document.querySelectorAll<HTMLDetailsElement>(".menu-movil").forEach((menu) => {
  menu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      menu.open = false;
    });
  });
});

// --- Revelado de encabezados de sección (una vez) ---
if (!reduceMotion && "IntersectionObserver" in window) {
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.classList.add("rv-in");
          io.unobserve(e.target);
        }
      }
    },
    { threshold: 0.2 },
  );
  document.querySelectorAll("[data-rv]").forEach((el) => io.observe(el));
} else {
  document
    .querySelectorAll("[data-rv]")
    .forEach((el) => el.classList.add("rv-in"));
}

// --- Instrumentos cinemáticos: corren únicamente mientras se pueden ver ---
// El canvas del sismograma también se autopausa; esta clase cubre los ciclos CSS
// del mapa y del edificio sin instalar una librería de motion.
if (!reduceMotion && "IntersectionObserver" in window) {
  const ioInstrumentos = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        entry.target.classList.toggle("pausado", !entry.isIntersecting);
      }
    },
    { rootMargin: "120px 0px", threshold: 0.01 },
  );
  document
    .querySelectorAll("[data-instrumento]")
    .forEach((el) => ioInstrumentos.observe(el));
}

// --- Simulación de cobertura física por zonas ---
const esquema = document.querySelector<HTMLElement>("[data-esquema]");
const botonSimulacro =
  document.querySelector<HTMLButtonElement>("[data-simulacro]");
const avisoSimulacro = document.querySelector<HTMLElement>(
  "[data-simulacro-aviso]",
);

function correrSimulacro(): void {
  if (!esquema) return;
  if (reduceMotion) {
    // Sin movimiento: conmuta el estado final de los actuadores, sin transición.
    esquema.classList.toggle("estatico-activado");
  } else {
    esquema.classList.remove("play");
    // Reinicia las animaciones CSS forzando un reflow antes de re-aplicar la clase.
    void esquema.offsetWidth;
    esquema.classList.add("play");
  }
  if (avisoSimulacro) {
    avisoSimulacro.textContent =
      "Simulacro ejecutado: la señal del SASMEX activa el gabinete principal, los gabinetes de apoyo, las sirenas y los estrobos por zona.";
  }
}

if (esquema) {
  if (!reduceMotion && "IntersectionObserver" in window) {
    const ioEsquema = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            esquema.classList.add("play");
            ioEsquema.disconnect();
          }
        }
      },
      { threshold: 0.35 },
    );
    ioEsquema.observe(esquema);
  }
  botonSimulacro?.addEventListener("click", correrSimulacro);
}
