// Fecha y hora LOCALES DE MÉXICO de un instante ISO, con `Intl` como el resto de
// la app (`toLocaleString("es-MX", …)`). Se fija la zona de la Ciudad de México
// porque el sismo y el inmueble están aquí, aunque el teléfono viaje; si el
// motor de `Intl` del aparato no conociera la zona (lanza `RangeError`), se cae a
// la del teléfono en vez de romper la fila.
const OPCIONES: Intl.DateTimeFormatOptions = {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
};

export function fechaLocal(iso: string): string {
  const d = new Date(iso);
  try {
    return d.toLocaleString("es-MX", { ...OPCIONES, timeZone: "America/Mexico_City" });
  } catch {
    return d.toLocaleString("es-MX", OPCIONES);
  }
}
