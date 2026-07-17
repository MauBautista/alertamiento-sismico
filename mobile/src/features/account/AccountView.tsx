// 1.8 · Cuenta — presentacional puro. La fila TOTP OPCIONAL es EXCLUSIVA del
// occupant (decisión #7: su pool es mfa=OPTIONAL; los tácticos tienen MFA
// obligatorio a nivel de pool — no hay nada que optar). El flujo de asociación
// TOTP (Cognito) llega en T-2.14 (hardening) — la fila lo declara.
import { Pressable, StyleSheet, Switch, Text, TextInput, View } from "react-native";

import { fontSize, palette, radius, space } from "@/ui/theme";

export type AccountProfile = {
  displayName: string;
  phone: string;
};

export function AccountView(props: {
  role: string;
  isOccupant: boolean;
  profile: AccountProfile;
  onProfileChange: (p: AccountProfile) => void;
  onSaveProfile: () => void;
  /** El roster exige nombre (CHECK 1-80): sin nombre no hay GUARDAR. */
  canSave: boolean;
  savingProfile: boolean;
  profileSavedAt: number | null;
  gpsConsent: boolean;
  onToggleConsent: (granted: boolean) => void;
  onOpenPermisos: () => void;
  onOpenPrivacidad: () => void;
  onOpenVincular: () => void;
  onLogout: () => void;
}) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.eyebrow}>CUENTA · {props.role.toUpperCase()}</Text>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>PERFIL</Text>
        <Text style={styles.fieldLabel}>Nombre para el roster</Text>
        <TextInput
          onChangeText={(t) => props.onProfileChange({ ...props.profile, displayName: t })}
          placeholder="Su nombre"
          placeholderTextColor={palette.fg3}
          style={styles.input}
          testID="input-name"
          value={props.profile.displayName}
        />
        <Text style={styles.fieldLabel}>Teléfono (llamada de un toque)</Text>
        <TextInput
          keyboardType="phone-pad"
          onChangeText={(t) => props.onProfileChange({ ...props.profile, phone: t })}
          placeholder="+52 …"
          placeholderTextColor={palette.fg3}
          style={styles.input}
          testID="input-phone"
          value={props.profile.phone}
        />
        <Pressable
          accessibilityRole="button"
          disabled={props.savingProfile || !props.canSave}
          onPress={props.onSaveProfile}
          style={[styles.saveBtn, (props.savingProfile || !props.canSave) && styles.dim]}
          testID="save-profile"
        >
          <Text style={styles.saveText}>{props.savingProfile ? "GUARDANDO…" : "GUARDAR"}</Text>
        </Pressable>
        {props.profileSavedAt !== null ? (
          <Text style={styles.savedNote}>Perfil guardado en el servidor.</Text>
        ) : null}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>PRIVACIDAD Y PERMISOS</Text>
        <View style={styles.row}>
          <View style={styles.rowInfo}>
            <Text style={styles.rowLabel}>Enviar mi ubicación GPS si pido ayuda</Text>
            <Text style={styles.rowDetail} testID="consent-note">
              {props.gpsConsent
                ? "Consentido: su ubicación viaja SOLO en un check-in de auxilio."
                : "Revocado: si pide ayuda se enviará su zona asignada, sin GPS."}
            </Text>
          </View>
          <Switch
            onValueChange={props.onToggleConsent}
            testID="consent-switch"
            value={props.gpsConsent}
          />
        </View>
        <Pressable accessibilityRole="button" onPress={props.onOpenPermisos}>
          <Text style={styles.link}>Estado de permisos de alerta →</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={props.onOpenPrivacidad}>
          <Text style={styles.link}>Aviso de privacidad →</Text>
        </Pressable>
      </View>

      {props.isOccupant ? (
        <View style={styles.card} testID="totp-row">
          <Text style={styles.cardTitle}>SEGURIDAD DE LA CUENTA</Text>
          <Text style={styles.rowLabel}>Verificación en dos pasos — OPCIONAL</Text>
          <Text style={styles.rowDetail}>
            Disponible para su perfil (decisión #7). El flujo de activación TOTP se habilita en
            T-2.14 (hardening); mientras tanto su cuenta opera con contraseña.
          </Text>
        </View>
      ) : null}

      <Pressable accessibilityRole="button" onPress={props.onOpenVincular}>
        <Text style={styles.link}>Vincular a un edificio (código de sitio) →</Text>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        onPress={props.onLogout}
        style={styles.logoutBtn}
        testID="logout"
      >
        <Text style={styles.logoutText}>CERRAR SESIÓN</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: space[4], paddingTop: 64, gap: space[3] },
  eyebrow: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  card: {
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space[4],
    gap: space[2],
  },
  cardTitle: { color: palette.fg3, fontSize: fontSize.xs, letterSpacing: 2 },
  fieldLabel: { color: palette.fg2, fontSize: fontSize.xs },
  input: {
    backgroundColor: palette.bg,
    borderColor: palette.borderStrong,
    borderWidth: 1,
    borderRadius: radius.md,
    color: palette.fg,
    paddingHorizontal: space[3],
    paddingVertical: space[2],
    fontSize: fontSize.sm,
  },
  saveBtn: {
    backgroundColor: palette.cyan,
    borderRadius: radius.md,
    paddingVertical: space[2],
    alignItems: "center",
    marginTop: space[1],
  },
  saveText: { color: palette.bg, fontWeight: "700", fontSize: fontSize.xs, letterSpacing: 1 },
  savedNote: { color: palette.ok, fontSize: fontSize.xs },
  row: { flexDirection: "row", alignItems: "center", gap: space[2] },
  rowInfo: { flex: 1, gap: 2 },
  rowLabel: { color: palette.fg, fontSize: fontSize.sm, fontWeight: "600" },
  rowDetail: { color: palette.fg3, fontSize: fontSize.xs, lineHeight: 16 },
  link: { color: palette.cyan, fontSize: fontSize.sm, paddingVertical: space[1] },
  logoutBtn: {
    borderColor: palette.crit,
    borderWidth: 1,
    borderRadius: radius.lg,
    paddingVertical: space[3],
    alignItems: "center",
    marginTop: space[2],
  },
  logoutText: { color: palette.crit, fontWeight: "700", letterSpacing: 1 },
  dim: { opacity: 0.5 },
});
