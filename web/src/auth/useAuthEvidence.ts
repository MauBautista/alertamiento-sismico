// [T-6.02] La constancia de autenticación de la sesión viva, desde el almacén.
import { getEnv } from "../app/env";
import { authEvidence, type AuthEvidence } from "./authEvidence";
import { useSessionStore } from "./session.store";

export function useAuthEvidence(): AuthEvidence {
  const origin = useSessionStore((s) => s.origin);
  const idToken = useSessionStore((s) => s.idToken);
  return authEvidence({ origin, idToken, authority: getEnv().cognito.authority });
}
