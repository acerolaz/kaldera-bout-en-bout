# Console Admin Page Overrides

> **PROJECT:** Kaldera
> **Generated:** 2026-10-09 01:53:23
> **Page Type:** Dashboard / Data View

> ⚠️ **Brut de génération, non adapté.** Sera revu dans la spec 2 (console de configuration) : les sections « Hero / Start trial », les effets Material/Reanimated et les CTA commerciaux ne s'appliquent pas à une console interne.
>
> ⚠️ **IMPORTANT:** Rules in this file **override** the Master file (`design-system/kaldera/MASTER.md`).
> Only deviations from the Master are documented here. For all other rules, refer to the Master.

---

## Page-Specific Rules

### Layout Overrides

- **Max Width:** 1200px (standard)
- **Layout:** Full-width sections, centered content
- **Sections:** 1. Hero (product + live preview or status), 2. Key metrics/indicators, 3. How it works, 4. CTA (Start trial / Contact)

### Spacing Overrides

- No overrides — use Master spacing

### Typography Overrides

- No overrides — use Master typography

### Color Overrides

- **Strategy:** Dark or neutral. Status colors (green/amber/red). Data-dense but scannable.

### Component Overrides

- Avoid: Single row actions only
- Avoid: Auto-play high-res video loops

---

## Page-Specific Components

- No unique components for this page

---

## Recommendations

- Effects: Tonal elevation (overlay colors instead of strong shadows), pill-shaped buttons and chips (borderRadius 999), emphasized easing Easing.bezier(0.2,0,0,1), state layers (pressed overlays 10–15% opacity), Reanimated-filled label float for inputs, HapticFeedback on FAB/toggles
- Data Entry: Allow multi-select and bulk edit
- Sustainability: Click-to-play or pause when off-screen
- CTA Placement: Primary CTA in nav + After metrics
