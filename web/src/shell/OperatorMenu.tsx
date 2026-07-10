// Menú del operador en la topbar (T-1.49): nombre editable + logout.
//
// Muestra display_name (perfil) o el rol como fallback honesto — nunca inventa
// un nombre. La edición hace PUT /me/profile y el caché de la query se
// actualiza en el acto (el pie de la consola comparte la misma clave).

import { ChevronDown, LogOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useSessionStore } from "../auth/session.store";
import { useProfile, useProfileMutation } from "../auth/useProfile";

export default function OperatorMenu() {
  const me = useSessionStore((s) => s.me);
  const logout = useSessionStore((s) => s.logout);
  const profile = useProfile();
  const save = useProfileMutation();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);

  const displayName = profile.data?.display_name ?? null;
  const label = displayName ?? me?.role ?? "";

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
      }
    };
    const onClick = (e: MouseEvent) => {
      if (rootRef.current !== null && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const submit = () => {
    const name = draft.replace(/\s+/g, " ").trim();
    if (name === "") {
      return;
    }
    save.mutate(name, { onSuccess: () => setOpen(false) });
  };

  if (me === null) {
    return null;
  }

  return (
    <div className="soc-user" ref={rootRef}>
      <button
        type="button"
        className="soc-user__btn"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => {
          setDraft(displayName ?? "");
          setOpen((v) => !v);
        }}
      >
        <span className="soc-meta">{label}</span>
        <ChevronDown size={12} />
      </button>

      {open && (
        <div className="soc-user__menu" role="dialog" aria-label="Perfil del operador">
          <label className="soc-meta" htmlFor="operator-name">
            NOMBRE DE OPERADOR
          </label>
          <input
            id="operator-name"
            className="soc-user__input"
            value={draft}
            maxLength={80}
            placeholder={me.role}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                submit();
              }
            }}
          />
          <div className="soc-user__row">
            <button
              type="button"
              className="soc-btn soc-btn--primary"
              disabled={save.isPending || draft.replace(/\s+/g, " ").trim() === ""}
              onClick={submit}
            >
              {save.isPending ? "GUARDANDO…" : "GUARDAR"}
            </button>
            <button
              type="button"
              className="soc-btn"
              onClick={() => void logout()}
              aria-label="Cerrar sesión"
            >
              <LogOut size={12} /> SALIR
            </button>
          </div>
          {save.isError && (
            <p className="soc-user__error" role="alert">
              NO SE PUDO GUARDAR EL NOMBRE — REINTENTA
            </p>
          )}
          <p className="soc-user__caption">
            {me.role} · {me.sub.slice(0, 8)}
          </p>
        </div>
      )}
    </div>
  );
}
