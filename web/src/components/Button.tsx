// [T-6.13] UN BOTÓN.
//
// Había 72 `soc-btn` sueltos en 30 ficheros y la variante se escribía a mano en
// el `className` cada vez —«soc-btn soc-btn--secondary»—, así que una variante
// nueva, o un cambio de la de siempre, se hacía con `grep` y buena letra. El
// censo (`src/primitivasCensus.test.ts`) impide que vuelva a escribirse fuera de
// aquí; lo que este componente añade es que la variante sea **un valor del tipo**
// y no una cadena que nadie comprueba.
//
// Dos formas, porque el producto tiene dos: el `<button>` que HACE algo y el
// enlace que LLEVA a algún sitio. No son intercambiables —un enlace se abre en
// otra pestaña, se copia y aparece en el historial; un botón no— y por eso son
// dos exportaciones y no una prop.
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";

/**
 * `base` es el botón sin modificador (fondo transparente, borde transparente):
 * el de los formularios que ya viven dentro de una tarjeta con su propio marco.
 */
export type ButtonVariant = "base" | "primary" | "secondary" | "ghost" | "danger";

function clases(variant: ButtonVariant, extra?: string): string {
  const base = variant === "base" ? "soc-btn" : `soc-btn soc-btn--${variant}`;
  return extra === undefined || extra === "" ? base : `${base} ${extra}`;
}

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> {
  variant?: ButtonVariant;
  /** Clases de POSICIÓN de la pantalla anfitriona (`triage__more`, `is-on`…). */
  className?: string;
  children: ReactNode;
}

/**
 * `type="button"` por defecto A PROPÓSITO: el defecto de HTML es `submit`, y un
 * botón que envía el formulario sin pedirlo ya costó un incidente en más de un
 * producto. Quien quiera enviar, lo dice.
 */
export default function Button({
  variant = "base",
  className,
  type = "button",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button type={type} className={clases(variant, className)} {...rest}>
      {children}
    </button>
  );
}

export interface ButtonLinkProps extends Omit<LinkProps, "className"> {
  variant?: ButtonVariant;
  className?: string;
  children: ReactNode;
}

/** El mismo vestido sobre un `<Link>`: navega, no acciona. */
export function ButtonLink({ variant = "base", className, children, ...rest }: ButtonLinkProps) {
  return (
    <Link className={clases(variant, className)} {...rest}>
      {children}
    </Link>
  );
}
