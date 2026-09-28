// [T-9.80 · D-48] Validación de los contactos de emergencia EN EL CLIENTE. El
// servidor valida igual (`schemas/contactos_emergencia.py`); esto sólo evita un
// viaje de ida y vuelta y dice el problema junto al campo que lo tiene.
// `toHaveProperty("0.email")` leería una RUTA anidada; la clave va en un arreglo.
import {
  MAX_CONTACTOS,
  erroresDelServidor,
  normalizarTelefono,
  validarContactos,
  type ContactoBorrador,
} from "./validacion";

const BIEN: ContactoBorrador = { display_name: "Ana López", email: "ana@example.com", phone: "" };

describe("validarContactos", () => {
  it("un contacto correcto no tiene errores, y el teléfono es opcional", () => {
    expect(validarContactos([BIEN])).toEqual({});
    expect(validarContactos([{ ...BIEN, phone: "+525512345678" }])).toEqual({});
  });

  it("el nombre va de 1 a 80 caracteres (sin contar espacios de los bordes)", () => {
    expect(validarContactos([{ ...BIEN, display_name: "   " }])).toHaveProperty(["0.display_name"]);
    expect(validarContactos([{ ...BIEN, display_name: "x".repeat(81) }])).toHaveProperty(["0.display_name"]);
    expect(validarContactos([{ ...BIEN, display_name: "x".repeat(80) }])).toEqual({});
  });

  it("el correo necesita la forma mínima algo@algo.algo", () => {
    for (const malo of ["", "ana", "ana@example", "ana @example.com", "@example.com"]) {
      expect(validarContactos([{ ...BIEN, email: malo }])).toHaveProperty(["0.email"]);
    }
  });

  it("el teléfono, si viene, es E.164: + y de 8 a 15 dígitos, el primero no cero", () => {
    for (const malo of ["5512345678", "+0512345678", "+52 55 1234 5678", "+1234567", "+5"]) {
      expect(validarContactos([{ ...BIEN, phone: malo }])).toHaveProperty(["0.phone"]);
    }
    expect(validarContactos([{ ...BIEN, phone: "+12345678" }])).toEqual({});
  });

  it("el prefijo sugerido «+52» sin más dígitos cuenta como teléfono vacío", () => {
    expect(normalizarTelefono("+52")).toBeNull();
    expect(normalizarTelefono("  +52 ")).toBeNull();
    expect(normalizarTelefono("")).toBeNull();
    expect(normalizarTelefono(" +525512345678 ")).toBe("+525512345678");
    expect(validarContactos([{ ...BIEN, phone: "+52" }])).toEqual({});
  });

  it("los errores van POR CONTACTO y por campo", () => {
    const e = validarContactos([BIEN, { ...BIEN, email: "mal" }]);
    expect(Object.keys(e)).toEqual(["1.email"]);
  });

  it("el tope es 3", () => {
    expect(MAX_CONTACTOS).toBe(3);
  });
});

describe("erroresDelServidor (422)", () => {
  it("traduce el `loc` de FastAPI a la misma clave por campo", () => {
    const detail = [
      { loc: ["body", "contactos", 1, "email"], msg: "Value error, correo inválido", type: "value_error" },
      { loc: ["body", "contactos", 0, "phone"], msg: "Value error, teléfono inválido", type: "value_error" },
    ];
    expect(erroresDelServidor(detail)).toEqual({
      campos: { "1.email": "correo inválido", "0.phone": "teléfono inválido" },
      general: null,
    });
  });

  it("lo que no apunta a un campo (p. ej. más de 3) va al mensaje general", () => {
    const detail = [
      { loc: ["body", "contactos"], msg: "List should have at most 3 items after validation", type: "too_long" },
    ];
    const r = erroresDelServidor(detail);
    expect(r.campos).toEqual({});
    expect(r.general).toMatch(/3/);
  });

  it("un `detail` que no es la lista de FastAPI no revienta", () => {
    expect(erroresDelServidor("algo")).toEqual({ campos: {}, general: expect.any(String) });
    expect(erroresDelServidor(undefined)).toEqual({ campos: {}, general: expect.any(String) });
  });
});
