# Agent_Sudo Brand Assets

This document specifies the purpose, guidelines, and recommended usage of the `Agent_Sudo` visual branding and icon assets.

> [!NOTE]
> All visual assets are draft/generated branding and are subject to future refinement as the project and its ecosystem evolve.

---

## 1. Asset Inventory

All branding files are stored under [assets/brand/](../assets/brand/).

| Filename | Purpose | Recommended Usage | Format |
| :--- | :--- | :--- | :--- |
| [`agent-sudo-logo-primary.png`](../assets/brand/agent-sudo-logo-primary.png) | Primary Project Logo | Main header representation, README branding, project presentations. | PNG |
| [`agent-sudo-icon-square.png`](../assets/brand/agent-sudo-icon-square.png) | Compact Square Icon | Client logos, GitHub repository avatar, IDE integration icons. | PNG |
| [`agent-sudo-icon-monochrome.png`](../assets/brand/agent-sudo-icon-monochrome.png) | Monochrome/Solid Variant | High-contrast environments, print layouts, status bars, and menus. | PNG |
| [`agent-sudo-icon-notification.png`](../assets/brand/agent-sudo-icon-notification.png) | Notification Icon | macOS user notifications, alert icons, system toast messages. | PNG |

---

## 2. Usage Guidelines

### A. Primary Logo (`agent-sudo-logo-primary.png`)
* **Usage**: Embed in main documentation headings and homepage contexts.
* **Layout**: Center-aligned layout is preferred. Recommended sizing is `width="180"` to maintain a sleek, non-intrusive appearance.

### B. GitHub Repository Avatar & Compact Client Use (`agent-sudo-icon-square.png`)
* **Usage**: Ideal for GitHub organization/repository avatars, browser tab favicons, and IDE client integration list icons.
* **Spacing**: The square variant contains built-in visual centering and margins suitable for circular masking (e.g. GitHub's circular avatar rendering).

### C. High-Contrast & Solid Backgrounds (`agent-sudo-icon-monochrome.png`)
* **Usage**: Use this variant when the background color prevents clear rendering of the primary colored logo. Ideal for dark theme IDE bars or black-and-white printing.

### D. User Notifications & Alerts (`agent-sudo-icon-notification.png`)
* **Usage**: Designed to fit seamlessly inside macOS native notifications.
* **Sizing**: Handled by system layout managers when spawning a toast alert.

---

## 3. General Rules
- **No Decoration**: Do not stretch, distort, rotate, or apply arbitrary dropshadows or filters to the branding assets.
- **Maintain Proportions**: Always scale using aspect-ratio locked sizing.
- **Minimalism**: Avoid over-saturating documentation files with logos. Keep assets restricted to main gateways or landing files like the primary `README.md` or `docs/BRAND_ASSETS.md`.
