// [T-6.13] UNA TABLA.
//
// Había TRES sistemas de clases para lo mismo. Seis `<table>` en el árbol: tres
// colgaban de `.soc-table` y tres traían el suyo —`fleet__admintable`,
// `bld__table`, `audit__table`—, cada uno redeclarando `width`,
// `border-collapse`, el `th` y el `td` con valores casi iguales.
//
// Casi. Y ahí está el argumento: los tres divergían en el tamaño del cuerpo —11,
// 11 y 11.5 px— sin que nadie lo hubiera decidido, y ninguno heredaba el
// `tr:hover` ni el `tr:last-child` de la canónica. Una copia diverge; tres,
// seguro.
//
// Lo que de verdad las distinguía cabe en dos modificadores medidos:
//
//   · **`densa`** — las tres de fuera apretaban las celdas (6–10 px de padding
//     frente a los 18 de la canónica) porque viven dentro de una tarjeta, no en
//     una pantalla entera. Es una densidad, no otra tabla.
//   · **`sticky`** — la bitácora fija su cabecera al desplazarse, porque es la
//     única cuya lista no cabe nunca.
import type { ReactNode } from "react";

export interface TableProps {
  /** Celdas apretadas: la tabla vive dentro de una tarjeta, no en la pantalla. */
  densa?: boolean;
  /** La cabecera se queda fija al desplazar (listas que no caben nunca). */
  sticky?: boolean;
  /**
   * `role="grid"` para las tablas que el operador RECORRE con el teclado y en
   * las que la fila es accionable (la cola de triage). No se pone por defecto:
   * una tabla de sólo lectura anunciada como reja miente al lector de pantalla.
   */
  grid?: boolean;
  /** Clase de la pantalla anfitriona (anchos de columna, colores de fila…). */
  className?: string;
  children: ReactNode;
}

export default function Table({ densa, sticky, grid, className, children }: TableProps) {
  const clases = [
    "soc-table",
    densa === true ? "soc-table--densa" : null,
    sticky === true ? "soc-table--sticky" : null,
    className,
  ].filter((c): c is string => c !== undefined && c !== null && c !== "");
  return (
    <table role={grid === true ? "grid" : undefined} className={clases.join(" ")}>
      {children}
    </table>
  );
}
