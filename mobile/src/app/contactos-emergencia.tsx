// [T-9.80 · D-48] CUENTA → CONTACTOS DE EMERGENCIA. Ruta de stack (como
// `checkin.tsx`) que abren el ocupante y los tácticos desde su pestaña CUENTA.
//
// Sin `@takab/sdk` aquí: expo-router barre `src/app` y el SDK se queda en el hook
// (`features/emergencyContacts/useEmergencyContacts.ts`).
//
// `empty={false}` con razón: una lista VACÍA es un estado editable —desde ahí se
// AGREGA— y el vacío del marco se comería el formulario. El vacío lo pinta la
// vista (`state-empty`, con el texto que explica qué significa no tener a nadie).
import { useRouter } from "expo-router";
import { useRef } from "react";
import { ScrollView, StyleSheet } from "react-native";

import { EmergencyContactsScreen } from "@/features/emergencyContacts/EmergencyContactsScreen";
import { useEmergencyContacts } from "@/features/emergencyContacts/useEmergencyContacts";
import { StateFrame } from "@/ui/StateFrame";
import { palette, space } from "@/ui/theme";

export default function ContactosEmergencia() {
  const router = useRouter();
  const lista = useRef<ScrollView>(null);
  const contactos = useEmergencyContacts();
  const data = contactos.data;

  return (
    <StateFrame
      empty={false}
      emptyText=""
      error={contactos.error}
      loading={contactos.loading}
      onRetry={contactos.refetch}
      staleSinceMs={contactos.staleSinceMs}
    >
      {data !== null ? (
        <ScrollView
          contentContainerStyle={styles.contenido}
          ref={lista}
          keyboardShouldPersistTaps="handled"
          style={styles.scroll}
        >
          <EmergencyContactsScreen
            // La confirmación va al final, debajo de GUARDAR: se baja hasta ella.
            alConfirmarGuardado={() => lista.current?.scrollToEnd({ animated: true })}
            borrarTodos={contactos.borrarTodos}
            data={data}
            guardar={contactos.guardar}
            onVolver={() => router.back()}
          />
        </ScrollView>
      ) : null}
    </StateFrame>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  contenido: { paddingBottom: space[6] },
});
