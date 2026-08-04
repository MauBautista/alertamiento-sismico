/**
 * [T-2.45] Insignia de alcance. Declara lo que el servidor hace, no lo que el front
 * cree: ver `useSiteScope`.
 */
import { useSiteScope } from "../auth/useSiteScope";

export default function ScopeBadge() {
  const scope = useSiteScope();
  return (
    <span
      className={`soc-scope${scope.enforced ? " soc-scope--limited" : ""}`}
      title={scope.hint}
      data-testid="scope-badge"
    >
      {scope.label}
    </span>
  );
}
