// 1.8 · Cuenta — pantalla COMPARTIDA por occupant y táctico. Perfil (GET/PUT
// /me/profile), consentimiento GPS revocable (LFPDPPP), permisos, privacidad y
// logout. La fila TOTP OPCIONAL solo aparece para el occupant (isOccupant lo
// deriva del grupo del perfil; el táctico tiene MFA obligatorio de pool).
import { getProfileMeProfileGet, putProfileMeProfilePut } from "@takab/sdk";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet } from "react-native";

import { useSessionStore } from "@/auth/session.store";
import { AccountView, type AccountProfile } from "@/features/account/AccountView";
import { getGpsConsent, setGpsConsent } from "@/services/onboarding";
import { StateFrame } from "@/ui/StateFrame";
import { palette, space } from "@/ui/theme";

export function AccountScreen() {
  const router = useRouter();
  const me = useSessionStore((s) => s.me);
  const profileGroup = useSessionStore((s) => s.profile);
  const signOut = useSessionStore((s) => s.signOut);

  const remote = useQuery({
    queryKey: ["me-profile"],
    queryFn: async () => {
      const res = await getProfileMeProfileGet({});
      if (!res.data) {
        throw new Error("perfil no disponible");
      }
      return res.data;
    },
  });

  // Estado DERIVADO (lint v6: sin setState en effects): mientras el usuario no
  // edite, el formulario refleja el perfil del servidor; al teclear, manda lo
  // local hasta guardar.
  const [edited, setEdited] = useState<AccountProfile | null>(null);
  const form: AccountProfile = edited ?? {
    displayName: remote.data?.display_name ?? "",
    phone: remote.data?.phone ?? "",
  };
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [gpsConsent, setConsent] = useState(false);

  useEffect(() => {
    let alive = true;
    getGpsConsent().then((granted) => {
      if (alive) {
        setConsent(granted === true);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  const saveProfile = () => {
    const displayName = form.displayName.trim();
    if (displayName.length === 0) {
      return; // el botón va deshabilitado; el roster exige nombre (CHECK 1-80)
    }
    setSaving(true);
    setSavedAt(null);
    void (async () => {
      try {
        const res = await putProfileMeProfilePut({
          body: { display_name: displayName, phone: form.phone.trim() || null },
        });
        if (res.data) {
          setSavedAt(Date.now());
        }
      } finally {
        setSaving(false);
      }
    })();
  };

  const toggleConsent = (granted: boolean) => {
    setConsent(granted);
    void setGpsConsent(granted);
  };

  return (
    <StateFrame
      empty={false}
      emptyText=""
      error={remote.isError && !remote.data ? "No se pudo cargar su perfil." : null}
      loading={remote.isLoading}
      staleSinceMs={remote.isError && remote.data ? remote.dataUpdatedAt : null}
    >
      <ScrollView contentContainerStyle={styles.wrap} style={styles.scroll}>
        <AccountView
          canSave={form.displayName.trim().length > 0}
          gpsConsent={gpsConsent}
          isOccupant={profileGroup === "occupant"}
          onLogout={signOut}
          onOpenPermisos={() => router.push("/onboarding/permisos")}
          onOpenPrivacidad={() => router.push("/onboarding/privacidad")}
          onOpenVincular={() => router.push("/onboarding/enrolamiento")}
          onProfileChange={setEdited}
          onSaveProfile={saveProfile}
          onToggleConsent={toggleConsent}
          profile={form}
          profileSavedAt={savedAt}
          role={me?.role ?? profileGroup ?? "occupant"}
          savingProfile={saving}
        />
      </ScrollView>
    </StateFrame>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: palette.bg },
  wrap: { paddingBottom: space[6] },
});
