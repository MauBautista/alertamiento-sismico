# Fonts

Takab Technology uses three typefaces. Two are included via Google Fonts (`@import` in `colors_and_type.css`); the brand display face is substituted.

## Geist — Body / Main UI ✅ (local file, brand-supplied)
- File: `fonts/Geist_wght_.ttf` (variable axis: weight 100–900)
- Loaded via `@font-face` in `colors_and_type.css` — no network dependency.
- Weights in use: 300 / 400 / 500 / 600 / 700
- Replaces Inter for all body, labels, navigation, and UI prose.

## JetBrains Mono — Technical Data ✅
- Source: Google Fonts → https://fonts.google.com/specimen/JetBrains+Mono
- Weights in use: 400 / 700
- Loaded via `@import` in `colors_and_type.css`
- Used for ALL numerical readouts: magnitudes, coordinates, timestamps, PGA/PGV, UTC values, sensor IDs.

## Aero Sans-Serif — Brand Display ⚠️ SUBSTITUTED
- **No exact public version is available.** Aero Sans-Serif is a proprietary / commercial display face used in the Takab wordmark.
- **Substitution:** Saira Condensed 600/700 (geometric, slightly condensed, strong all-caps presence) — closest open-source match.
- Loaded via `@import` in `colors_and_type.css`.
- Used STRICTLY for: brand wordmark (`TAKAB TECHNOLOGY`), tagline (`LO MEJOR LO ESTAMOS CREANDO`), and major hero/section headers in marketing-adjacent surfaces.
- **NEVER mix Aero (or its substitute) into UI** — it is brand-only.

> 🚩 **Action requested from the user:** if you have the licensed Aero Sans-Serif `.woff2` / `.ttf` files, drop them into this `fonts/` folder and update the `@font-face` block in `colors_and_type.css`. Until then, Saira Condensed stands in.
