// [T-9.80 · D-48] CUENTA → CONTACTOS DE EMERGENCIA. El formulario de hasta tres
// personas FUERA del inmueble a las que les llega un correo si el titular marca
// NECESITO AYUDA tras un sismo.
//
// Recibe el dato ya leído (la ruta monta el `StateFrame` con loading/error/stale)
// y las dos acciones del hook. El VACÍO lo pinta esta vista y no el marco: una
// lista vacía es un estado EDITABLE —la persona tiene que poder AGREGAR desde
// ahí—, y el `empty` del marco se come a sus hijos.
//
// El consentimiento se sella contra una VERSIÓN del aviso: la casilla vale sólo
// para la versión que la persona tuvo delante. Si el servidor responde 409
// porque el aviso cambió, la versión recargada ya no es la aceptada y la casilla
// se desmarca SOLA (estado derivado, sin efecto que la limpie).
import type { ContactoIn, ContactosIn, ContactosOut } from "@takab/sdk";
import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { Pulsable } from "@/ui/Pulsable";
import { fontSize, palette, radius, space, touch } from "@/ui/theme";

import type { Desenlace } from "./useEmergencyContacts";
import {
  MAX_CONTACTOS,
  PREFIJO_SUGERIDO,
  normalizarTelefono,
  validarContactos,
  type ContactoBorrador,
  type ErroresPorCampo,
} from "./validacion";

export const EXPLICACION =
  "Si marca NECESITO AYUDA tras un sismo, les llega un correo con su nombre, el inmueble y la zona. La ubicación, solo si la compartió.";

export const SIN_CONTACTOS =
  "Sin contactos. Si marca NECESITO AYUDA, nadie fuera del inmueble recibe aviso.";

const AVISO_CAMBIO =
  "El aviso cambió mientras editaba. Lea el texto nuevo y vuelva a marcar la casilla para guardar.";

function borradorDe(data: ContactosOut): ContactoBorrador[] {
  return data.contactos.map((c) => ({
    display_name: c.display_name,
    email: c.email,
    phone: c.phone ?? "",
  }));
}

function cuerpoDe(borrador: ContactoBorrador[], version: string): ContactosIn {
  const contactos: ContactoIn[] = borrador.map((c) => ({
    display_name: c.display_name.trim(),
    email: c.email.trim(),
    phone: normalizarTelefono(c.phone),
  }));
  return { consentimiento_version: version, contactos };
}

export function EmergencyContactsScreen(props: {
  data: ContactosOut;
  guardar: (body: ContactosIn) => Promise<Desenlace>;
  borrarTodos: () => Promise<Desenlace>;
  onVolver?: () => void;
}) {
  const { data } = props;
  // Estado DERIVADO: mientras la persona no edite, el formulario refleja al
  // servidor; al teclear manda lo local hasta guardar.
  const [editado, setEditado] = useState<ContactoBorrador[] | null>(null);
  const borrador = editado ?? borradorDe(data);
  const [aceptoVersion, setAceptoVersion] = useState<string | null>(null);
  const acepto = aceptoVersion === data.aviso.version;
  const [errores, setErrores] = useState<ErroresPorCampo>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [avisoCambio, setAvisoCambio] = useState(false);
  const [guardadoOk, setGuardadoOk] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [confirmando, setConfirmando] = useState(false);

  const lleno = borrador.length >= MAX_CONTACTOS;
  const guardadoVacio = data.contactos.length === 0;

  const editar = (i: number, campo: keyof ContactoBorrador, valor: string) => {
    setEditado(borrador.map((c, k) => (k === i ? { ...c, [campo]: valor } : c)));
    setGuardadoOk(false);
    if (errores[`${i}.${campo}`]) {
      const resto = { ...errores };
      delete resto[`${i}.${campo}`];
      setErrores(resto);
    }
  };

  const agregar = () => {
    if (lleno) {
      return;
    }
    setEditado([...borrador, { display_name: "", email: "", phone: PREFIJO_SUGERIDO }]);
    setGuardadoOk(false);
  };

  const quitar = (i: number) => {
    setEditado(borrador.filter((_, k) => k !== i));
    // Los índices se corren: un error que apuntaba al 2 ya no es de ese contacto.
    setErrores({});
    setGuardadoOk(false);
  };

  const guardar = () => {
    if (!acepto || ocupado) {
      return;
    }
    setGeneral(null);
    setGuardadoOk(false);
    const locales = validarContactos(borrador);
    setErrores(locales);
    if (Object.keys(locales).length > 0) {
      return;
    }
    setOcupado(true);
    void (async () => {
      try {
        const r = await props.guardar(cuerpoDe(borrador, data.aviso.version));
        if (r.tipo === "ok") {
          setEditado(null);
          setGuardadoOk(true);
          setAvisoCambio(false);
        } else if (r.tipo === "consentimiento") {
          setAceptoVersion(null);
          setAvisoCambio(true);
        } else if (r.tipo === "validacion") {
          setErrores(r.campos);
          setGeneral(r.general);
        } else {
          setGeneral(r.mensaje);
        }
      } finally {
        setOcupado(false);
      }
    })();
  };

  const borrar = () => {
    setOcupado(true);
    setGeneral(null);
    void (async () => {
      try {
        const r = await props.borrarTodos();
        if (r.tipo === "ok") {
          setEditado(null);
          setErrores({});
          setConfirmando(false);
        } else {
          setGeneral(r.tipo === "fallo" ? r.mensaje : "No se pudieron borrar los contactos.");
        }
      } finally {
        setOcupado(false);
      }
    })();
  };

  const puedeGuardar = acepto && !ocupado;

  return (
    <View style={styles.wrap}>
      {props.onVolver ? (
        <Pulsable accessibilityRole="button" onPress={props.onVolver} style={styles.linkBtn}>
          <Text style={styles.link}>← Cuenta</Text>
        </Pulsable>
      ) : null}
      <Text style={styles.eyebrow}>CUENTA · CONTACTOS DE EMERGENCIA</Text>
      <Text style={styles.explicacion}>{EXPLICACION}</Text>
      <Text style={styles.conteo} testID="contactos-conteo">
        {borrador.length} de {MAX_CONTACTOS}
      </Text>

      {borrador.length === 0 ? (
        <View style={styles.card} testID="state-empty">
          <Text style={styles.vacio}>{SIN_CONTACTOS}</Text>
        </View>
      ) : null}

      {borrador.map((c, i) => (
        <View key={i} style={styles.card}>
          <Text style={styles.cardTitle}>CONTACTO {i + 1}</Text>
          <Text style={styles.fieldLabel}>Nombre</Text>
          <TextInput
            maxLength={80}
            onChangeText={(t) => editar(i, "display_name", t)}
            placeholder="Nombre y apellido"
            placeholderTextColor={palette.fg3}
            style={styles.input}
            testID={`contacto-nombre-${i}`}
            value={c.display_name}
          />
          {errores[`${i}.display_name`] ? (
            <Text style={styles.error} testID={`contacto-error-nombre-${i}`}>
              {errores[`${i}.display_name`]}
            </Text>
          ) : null}
          <Text style={styles.fieldLabel}>Correo</Text>
          <TextInput
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            onChangeText={(t) => editar(i, "email", t)}
            placeholder="nombre@dominio.mx"
            placeholderTextColor={palette.fg3}
            style={styles.input}
            testID={`contacto-email-${i}`}
            value={c.email}
          />
          {errores[`${i}.email`] ? (
            <Text style={styles.error} testID={`contacto-error-email-${i}`}>
              {errores[`${i}.email`]}
            </Text>
          ) : null}
          <Text style={styles.fieldLabel}>Teléfono (opcional)</Text>
          <TextInput
            keyboardType="phone-pad"
            onChangeText={(t) => editar(i, "phone", t)}
            placeholder="+52 y 10 dígitos"
            placeholderTextColor={palette.fg3}
            style={styles.input}
            testID={`contacto-telefono-${i}`}
            value={c.phone}
          />
          {errores[`${i}.phone`] ? (
            <Text style={styles.error} testID={`contacto-error-telefono-${i}`}>
              {errores[`${i}.phone`]}
            </Text>
          ) : null}
          <Pulsable
            accessibilityLabel={`Quitar contacto ${i + 1}`}
            accessibilityRole="button"
            disabled={ocupado}
            onPress={() => quitar(i)}
            style={styles.quitarBtn}
            testID={`contacto-quitar-${i}`}
          >
            <Text style={styles.quitarText}>QUITAR</Text>
          </Pulsable>
        </View>
      ))}

      <Pulsable
        accessibilityRole="button"
        disabled={lleno || ocupado}
        onPress={agregar}
        style={[styles.secundarioBtn, (lleno || ocupado) && styles.dim]}
        testID="contactos-agregar"
      >
        <Text style={styles.secundarioText}>
          {lleno ? `AGREGAR · MÁXIMO ${MAX_CONTACTOS}` : "AGREGAR"}
        </Text>
      </Pulsable>

      <View style={styles.card}>
        <View style={styles.avisoCabecera}>
          <Text style={styles.cardTitle}>AVISO A SUS CONTACTOS</Text>
          {data.aviso.provisional ? (
            <Text style={styles.provisional} testID="aviso-provisional">
              PROVISIONAL
            </Text>
          ) : null}
        </View>
        <Text style={styles.avisoTexto} testID="aviso-texto">
          {data.aviso.texto}
        </Text>
      </View>

      {avisoCambio ? (
        <View style={styles.alerta} testID="contactos-aviso-cambio">
          <Text style={styles.alertaText}>{AVISO_CAMBIO}</Text>
        </View>
      ) : null}

      <Pulsable
        accessibilityRole="checkbox"
        accessibilityState={{ checked: acepto }}
        onPress={() => {
          setAceptoVersion(acepto ? null : data.aviso.version);
          if (!acepto) {
            setAvisoCambio(false);
          }
        }}
        style={styles.casillaFila}
        testID="contactos-acepto"
      >
        <View style={[styles.casilla, acepto && styles.casillaMarcada]}>
          {acepto ? <Text style={styles.palomita}>✓</Text> : null}
        </View>
        <Text style={styles.casillaTexto}>Mis contactos saben y aceptan recibir este aviso</Text>
      </Pulsable>

      {general !== null ? (
        <View style={styles.alerta} testID="contactos-fallo">
          <Text style={styles.alertaText}>{general}</Text>
        </View>
      ) : null}

      <Pulsable
        accessibilityRole="button"
        disabled={!puedeGuardar}
        onPress={guardar}
        style={[styles.guardarBtn, !puedeGuardar && styles.dim]}
        testID="contactos-guardar"
      >
        <Text style={styles.guardarText}>{ocupado ? "GUARDANDO…" : "GUARDAR"}</Text>
      </Pulsable>
      {guardadoOk ? (
        <Text style={styles.guardado} testID="contactos-guardado">
          Contactos guardados en el servidor.
        </Text>
      ) : null}

      {!guardadoVacio && !confirmando ? (
        <Pulsable
          accessibilityRole="button"
          disabled={ocupado}
          onPress={() => setConfirmando(true)}
          style={styles.borrarBtn}
          testID="contactos-borrar"
        >
          <Text style={styles.borrarText}>BORRAR TODOS</Text>
        </Pulsable>
      ) : null}
      {!guardadoVacio && confirmando ? (
        <View style={styles.confirmacion} testID="contactos-borrar-confirmacion">
          <Text style={styles.alertaText}>
            ¿Borrar sus {data.contactos.length} contactos? Si marca NECESITO AYUDA, nadie fuera del
            inmueble recibirá aviso.
          </Text>
          <View style={styles.fila}>
            <Pulsable
              accessibilityRole="button"
              disabled={ocupado}
              onPress={() => setConfirmando(false)}
              style={[styles.secundarioBtn, styles.flex]}
              testID="contactos-borrar-cancelar"
            >
              <Text style={styles.secundarioText}>CANCELAR</Text>
            </Pulsable>
            <Pulsable
              accessibilityRole="button"
              disabled={ocupado}
              onPress={borrar}
              style={[styles.borrarBtn, styles.flex]}
              testID="contactos-borrar-confirmar"
            >
              <Text style={styles.borrarText}>{ocupado ? "BORRANDO…" : "SÍ, BORRAR"}</Text>
            </Pulsable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  explicacion: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20 },
  conteo: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 1 },
  card: {
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[2],
  },
  cardTitle: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  vacio: { color: palette.fg2, fontSize: fontSize.sm, lineHeight: 20 },
  fieldLabel: { color: palette.fg2, fontSize: fontSize.xs },
  input: {
    minHeight: touch.min,
    backgroundColor: palette.bg,
    borderColor: palette.borderStrong,
    borderWidth: 1,
    borderRadius: radius.md,
    color: palette.fg,
    paddingHorizontal: space[3],
    paddingVertical: space[2],
    fontSize: fontSize.sm,
  },
  error: { color: palette.crit, fontSize: fontSize.xs },
  quitarBtn: {
    minHeight: touch.min,
    justifyContent: "center",
    alignSelf: "flex-start",
    paddingHorizontal: space[2],
  },
  quitarText: { color: palette.crit, fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 1 },
  secundarioBtn: {
    minHeight: touch.min,
    justifyContent: "center",
    alignItems: "center",
    borderColor: palette.cyan,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[2],
  },
  secundarioText: { color: palette.cyan, fontSize: fontSize.xs, fontWeight: "700", letterSpacing: 1 },
  avisoCabecera: { flexDirection: "row", alignItems: "center", gap: space[2] },
  provisional: {
    color: palette.warn,
    borderColor: palette.warn,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space[2],
    fontSize: fontSize.xs,
    fontWeight: "700",
    letterSpacing: 1,
  },
  avisoTexto: { color: palette.fg, fontSize: fontSize.sm, lineHeight: 20 },
  alerta: {
    backgroundColor: palette.card,
    borderColor: palette.warn,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space[3],
  },
  alertaText: { color: palette.warn, fontSize: fontSize.sm, lineHeight: 20 },
  casillaFila: {
    minHeight: touch.min,
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
  },
  casilla: {
    width: 24,
    height: 24,
    borderColor: palette.borderStrong,
    borderWidth: 2,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
  casillaMarcada: { backgroundColor: palette.cyan, borderColor: palette.cyan },
  palomita: { color: palette.bg, fontWeight: "700" },
  casillaTexto: { flex: 1, color: palette.fg, fontSize: fontSize.sm, fontWeight: "600" },
  guardarBtn: {
    minHeight: touch.min,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: palette.cyan,
    borderRadius: radius.md,
    paddingVertical: space[2],
  },
  guardarText: { color: palette.bg, fontWeight: "700", fontSize: fontSize.xs, letterSpacing: 1 },
  guardado: { color: palette.ok, fontSize: fontSize.xs },
  borrarBtn: {
    minHeight: touch.min,
    justifyContent: "center",
    alignItems: "center",
    borderColor: palette.crit,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space[2],
  },
  borrarText: { color: palette.crit, fontWeight: "700", fontSize: fontSize.xs, letterSpacing: 1 },
  confirmacion: {
    backgroundColor: palette.card,
    borderColor: palette.crit,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: space[3],
    gap: space[2],
  },
  fila: { flexDirection: "row", gap: space[2] },
  flex: { flex: 1 },
  linkBtn: { minHeight: touch.min, justifyContent: "center", alignSelf: "flex-start" },
  link: { color: palette.cyan, fontSize: fontSize.sm },
  dim: { opacity: 0.5 },
});
