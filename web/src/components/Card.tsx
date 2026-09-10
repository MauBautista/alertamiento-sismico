// [T-6.13] UNA TARJETA.
//
// `DetailPanel.tsx` declaraba DIECIOCHO tarjetas a mano, y cada una repetía la
// misma cabecera de tres niveles:
//
//     <div className="soc-card">
//       <div className="soc-card__hd">
//         <div>
//           <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
//             <Icono size={14} /> Título
//           </div>
//           <div className="soc-card__sub">SUBTÍTULO</div>
//         </div>
//         {opcionalmente, un pill a la derecha}
//       </div>
//       …
//     </div>
//
// Veintiún tarjetas en el árbol, y en las seis que llevan icono la fila del
// icono era un `style` en línea escrito a mano — invisible para cualquier censo
// de la hoja, la misma familia que cazó T-6.12. Aquí la cabecera es UNA, la fila
// del icono es una CLASE, y lo que cambia de una tarjeta a otra —título, icono,
// subtítulo y lo que va a la derecha— entra por parámetro.
import type { ReactNode } from "react";

export interface CardProps {
  /** El nombre de lo que se está mirando. Va en el cuerpo de la cabecera. */
  title: ReactNode;
  /** Glifo a la izquierda del título. Decorativo: llévalo con `aria-hidden`. */
  icon?: ReactNode;
  /** La línea de procedencia: de dónde sale el dato y cada cuánto. */
  sub?: ReactNode;
  /** Lo que va a la DERECHA de la cabecera — casi siempre un pill de estado. */
  aside?: ReactNode;
  /** Clase de la pantalla anfitriona (`cctv`, `timeline`, `users`…). */
  className?: string;
  testId?: string;
  /** La línea de procedencia también se prueba en un sitio (el marco declarado). */
  subTestId?: string;
  children?: ReactNode;
}

export default function Card({
  title,
  icon,
  sub,
  aside,
  className,
  testId,
  subTestId,
  children,
}: CardProps) {
  return (
    <div
      className={className === undefined ? "soc-card" : `soc-card ${className}`}
      data-testid={testId}
    >
      <div className="soc-card__hd">
        <div>
          <div className="soc-card__title">
            {icon}
            {title}
          </div>
          {sub !== undefined && (
            <div className="soc-card__sub" data-testid={subTestId}>
              {sub}
            </div>
          )}
        </div>
        {aside}
      </div>
      {children}
    </div>
  );
}
