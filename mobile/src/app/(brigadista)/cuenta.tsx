import { Pending } from "@/ui/Pending";

export default function Cuenta() {
  return (
    <Pending
      screen="1.8 (compartida)"
      title="Cuenta"
      task="T-2.07"
      note="Misma pantalla que el ocupante; los tácticos NO ven la fila de MFA opcional (su MFA es obligatorio a nivel de pool)."
    />
  );
}
