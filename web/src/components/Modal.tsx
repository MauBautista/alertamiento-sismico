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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    // Foco inicial DENTRO del diálogo (lectores de pantalla + teclado).
    dialogRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

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
