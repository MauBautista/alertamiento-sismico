// Tokens del design system PRIMERO (fuente única @takab/design-tokens, T-2.01);
// colors_and_type.css conserva solo fuentes locales + clases de tipo semánticas.
import "@takab/design-tokens/css/tokens.css";
import "./styles/colors_and_type.css";
import "./styles/soc.css";
import "./styles/soc-tabs.css";
import "./styles/app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
