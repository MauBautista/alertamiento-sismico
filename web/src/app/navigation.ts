/** Redirect duro fuera de la SPA (Hosted UI de Cognito). Módulo aparte para
 * poder mockearlo: jsdom no permite espiar window.location.assign. */
export function hardRedirect(url: string): void {
  window.location.assign(url);
}
