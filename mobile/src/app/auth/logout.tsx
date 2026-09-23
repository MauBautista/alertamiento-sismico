// [T-8.11 · A-021] Retorno del `/logout` de la Hosted UI de Cognito.
//
// `logout()` (auth/logout.ts, paso 3) abre `https://<dominio>/logout` con
// `logout_uri=takab://auth/logout` para borrar la cookie de la Hosted UI. En
// ANDROID el polyfill de `expo-web-browser` espera ese redirect escuchando
// `Linking`, y el mismo intent llega a expo-router como NAVEGACIÓN a
// `/auth/logout` — igual que `/auth/callback`. Sin esta ruta, Android pintaba
// «Unmatched Route» (en inglés) al terminar de cerrar sesión.
//
// No hay nada que hacer aquí: el polyfill ya cierra el Custom Tab en su
// `finally`, y `logout()` borra el almacén en el suyo (`signOut("user")`). La
// puerta de entrada reenruta por el estado de la sesión; si el deep link gana
// la carrera al `signOut`, la guarda del grupo de pestañas hace el segundo
// salto a `/` en cuanto el estado pasa a anónimo, y de ahí a `/login`.
//
// La cubre `tests/app/auth-rutas-de-retorno.test.tsx`, que deriva de
// `auth/config.ts` todos los deep links de retorno y exige su fichero aquí.
import { Redirect } from "expo-router";

export default function AuthLogout() {
  return <Redirect href="/" />;
}
