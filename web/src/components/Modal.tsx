// Modal accesible del SOC (T-1.51): overlay + dialog con Esc y foco inicial.
// Primer modal real del árbol (los formularios previos eran swaps in-place);
// tokens del design system (scrim --tk-surface-overlay, sombra modal).

import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

export interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

export default function Modal({ title, onClose, children, footer }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  // [A-013 · T-8.07] El `onClose` VIGENTE, en una ref. Quien monta el modal suele
  // pasarlo como flecha nueva en cada render —`ConsoleWall` se redibuja cada 1 s—
  // y con él en las dependencias el efecto de abajo se re-ejecutaba cada tic y le
  // quitaba el foco al campo en el que se estaba escribiendo.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // Foco inicial DENTRO del diálogo (lectores de pantalla + teclado): UNA vez, al
  // montar. Después el foco es del operador.
  useEffect(() => {
    dialogRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCloseRef.current();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="soc-modal__overlay" data-testid="modal-overlay">
      <div
        ref={dialogRef}
        className="soc-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <header className="soc-modal__hd">
          <h2 className="soc-modal__title">{title}</h2>
          <button type="button" className="soc-icon-btn" aria-label="Cerrar" onClick={onClose}>
            <X size={16} aria-hidden />
          </button>
        </header>
        <div className="soc-modal__body">{children}</div>
        {footer && <footer className="soc-modal__ft">{footer}</footer>}
      </div>
    </div>
  );
}
