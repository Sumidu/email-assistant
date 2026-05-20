---
name: Email Assistant
description: Local-first email client with LLM-powered drafts and markdown knowledge base
colors:
  # Deep neutral surfaces (dark theme — canonical)
  surface-void: "#101114"
  surface-base: "#18191d"
  surface-raised: "#202126"
  surface-selection: "#2a2c32"
  surface-high: "#363941"
  # Borders
  border-subtle: "#30323a"
  border-strong: "#484b55"
  # Text hierarchy
  text-dim: "#7f8491"
  text-muted: "#a9afbd"
  text-body: "#e2e5eb"
  text-bright: "#ffffff"
  # Input background
  input-surface: "#202228"
  # Semantic accents — each used for exactly one role
  accent-primary: "#0a84ff"
  accent-kb: "#e8a000"
  accent-finish: "#44dd88"
  accent-finish-strong: "#22aa66"
  accent-danger: "#ee4466"
  accent-calendar: "#44aaff"
  accent-todo: "#bf5af2"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "normal"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: 1.45
    letterSpacing: "normal"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "normal"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif"
    fontSize: "10px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.2px"
  mono:
    fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', 'Courier New', monospace"
    fontSize: "11.5px"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
rounded:
  pill: "999px"
  sm: "7px"
  md: "8px"
  lg: "10px"
  xl: "14px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "22px"
components:
  button-primary:
    backgroundColor: "{colors.accent-primary}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  button-primary-hover:
    backgroundColor: "#0070e0"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  button-kb:
    backgroundColor: "{colors.surface-base}"
    textColor: "{colors.accent-kb}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  button-ghost:
    backgroundColor: "{colors.surface-base}"
    textColor: "{colors.text-body}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  button-finish:
    backgroundColor: "{colors.accent-finish-strong}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  button-danger:
    backgroundColor: "{colors.surface-base}"
    textColor: "{colors.accent-danger}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  input-default:
    backgroundColor: "{colors.input-surface}"
    textColor: "{colors.text-bright}"
    rounded: "{rounded.md}"
    padding: "8px 10px"
---

# Design System: Email Assistant

## 1. Overview

**Creative North Star: "The Dark Room"**

This is a working instrument, not an interface. Every pixel serves the process of getting through email with precision and minimal noise. Like a photographic dark room, the environment is controlled: deep neutrals suppress ambient distraction, deliberate signals cut through only when they carry information. Nothing glows for decoration. Nothing pulses for style. If an element is lit, it is lit because it means something.

The system runs entirely on your machine. That physical fact should be legible in the UI. No cloud gradients, no translucent card stacks, no SaaS-branded color fields. The surface feels more like a calibrated terminal than a web app — sf-pro type on dark bedrock, amber as a semantic cursor rather than a brand color, semantic greens and reds that report state rather than emote.

Both dark and light themes are maintained with equal care. Dark is the home mode; light adapts the same logic to a daylight environment. The semantic color roles stay constant across themes; only the surface palette shifts.

**Key Characteristics:**
- Tonal depth: five surface steps (bg0–bg4) create hierarchy without shadows in the main layout
- One accent, one role: amber signals LLM/knowledge actions only; blue signals primary UI actions only
- Semantic color discipline: green = done, red = danger, purple = todos, blue = calendar/primary — these roles never blur
- Typography is system-native (SF Pro Text) for zero-overhead readability; mono for data
- Floating surfaces (modals, drawers) earn elevation via shadow; panels do not

## 2. Colors: The Signal Palette

Seven semantic accents. Each has exactly one job. Never reassign them.

### Primary

- **iOS Action Blue** (`#0a84ff` dark / `#0066cc` light): Primary UI actions — the Sync button, focus rings, selected email highlight, unread dots. The user's primary agency on the screen.

### Secondary

- **Signal Amber** (`#e8a000` dark / `#946200` light): LLM and knowledge-base actions exclusively. The Generate button, KB badges, knowledge modal title, the caret in chat input, progress bar fill. When amber appears, the model is involved. It is not a warning and must not be used for error states.

### Tertiary

- **Finish Green** (`#44dd88` dark / `#14804a` light): Successful completion. The Done action, finished counters, status-bar dot when synced. The Copy+Done action uses the deeper `#22aa66` variant for emphasis.
- **Todo Purple** (`#bf5af2` dark / `#8b35c9` light): The Todo Finder feature exclusively. Isolated from all other actions.
- **Calendar Blue** (`#44aaff` dark / `#0066cc` light): Calendar events and sent-mail chips. Distinct from Action Blue by intent, shares a hue family.
- **Danger Red** (`#ee4466` dark / `#c5223f` light): Spam, delete, error states. Never used for decorative emphasis.

### Neutral

The dark theme uses a five-step tonal ramp from near-black to elevated surface, all slightly warm-gray (not pure cool-gray):

- **Void** (`#101114`): Deepest background. Main app shell.
- **Base** (`#18191d`): Panel background. Folder column, mail list, email body.
- **Raised** (`#202126`): Header bars, modal headers, toolbar surfaces. 
- **Selection** (`#2a2c32`): Hover and selected item backgrounds.
- **High** (`#363941`): Activity console, highest-elevation surfaces within panels.
- **Border Subtle** (`#30323a`): Default divider and panel borders.
- **Border Strong** (`#484b55`): Input field borders, interactive element outlines.
- **Text Dim** (`#7f8491`): Placeholders, secondary metadata, decorative separators.
- **Text Muted** (`#a9afbd`): Secondary labels, timestamps, helper text.
- **Text Body** (`#e2e5eb`): Primary readable content.
- **Text Bright** (`#ffffff`): Headings, emphasis, active labels.

### Named Rules

**The One Role, One Color Rule.** Every semantic accent (amber, green, blue, purple, red) maps to exactly one functional domain. If a new feature needs an accent, it gets a new role assignment — it does not borrow from an existing role. Mixing roles corrupts the user's learned signal vocabulary.

**The No-Neon Rule.** Accents are used at natural saturation levels, not amplified with glow, bloom, or outer-shadow decoration. The only acceptable use of a color-matched `box-shadow` is for focus rings (3px, 20% opacity) and unread-dot halos (2px, 18% opacity).

## 3. Typography

**Body Font:** SF Pro Text (macOS system font) with `-apple-system, BlinkMacSystemFont` fallback chain
**Mono Font:** SF Mono with Fira Code, Cascadia Code fallback

**Character:** Zero-weight visual overhead. The system font is already antialiased and hinted for this display. Mono appears only for code, log output, and the knowledge editor — it signals "raw data" without needing color.

### Type Scale (CSS tokens)

Five steps, defined in `:root` as `--ts-xs` through `--ts-lg`. Use these variables; do not introduce new hardcoded font-size values.

| Token | Size | Role | Examples |
|-------|------|------|---------|
| `--ts-xs` | 10px | Micro labels — badges, chips, pills, timestamps | KB badges, thread chips, email metadata row, cm-role labels |
| `--ts-sm` | 12px | Secondary metadata — secondary list info, counts, labels | Email subject in list, folder label, tab buttons, section labels |
| `--ts-base` | 13px | Primary UI chrome — buttons, inputs, nav, form fields | All buttons (hbtn/rbtn/sbtn), search input, form fields, modal titles |
| `--ts-body` | 14px | Reading content — anything the user reads carefully | Email body, draft text, KB viewer, chat messages, KB editor |
| `--ts-lg` | 16px | Emphasis — one or two elements per view | Email subject in preview panel, major modal headings |

**Weight roles:** 400 body content, 500 all UI labels (weight class for buttons and secondary text), 650 sender names and key emphasis, 700 panel headings.

### Hierarchy

- **Emphasis** (`--ts-lg`, weight 650, 1.3 lh): Email subject line in preview panel. One per view.
- **Primary UI** (`--ts-base`, weight 500–700, 1.45 lh): Buttons, folder names, sender names, modal titles. The default for everything interactive.
- **Reading** (`--ts-body`, weight 400, 1.65 lh): Email body content, draft text, chat messages, knowledge files. Slightly larger to ease sustained reading.
- **Secondary** (`--ts-sm`, weight 400–500, 1.4 lh): Email subjects in list, secondary labels, tab text, counts. Clearly subordinate but readable.
- **Micro** (`--ts-xs`, weight 400–700, 1.3 lh): Badges, chips, metadata timestamps. Glanceable, not readable. Minimum floor; nothing goes below 10px.
- **Mono** (`--ts-xs` or `--ts-sm`, weight 400, 1.55 lh): Activity console, prompt editors, code spans. Uses `--mono` stack.

### Named Rules

**The System Font Rule.** Never load a web font for the app UI. SF Pro Text is free, system-native, and already optimized for macOS rendering. Loading external fonts adds cold-start latency and visual mismatch against the native webview chrome.

**The No-Uppercase Rule (post-refresh).** All UI text is sentence case or natural case. The macOS visual refresh overrides the earlier uppercase + letter-spacing pattern. New code must not reintroduce `text-transform: uppercase` or `letter-spacing: 2px` patterns. Label weight (500) and muted color carry hierarchy without case transformation.

## 4. Elevation

This system uses tonal layering for in-panel hierarchy and true shadows only for floating surfaces. Shadows are not used decoratively within the three-panel grid.

**Tonal layering:** Each surface step (`--bg0` through `--bg4`) is darker than the one below it. Panel columns sit on `--bg1`; their header bars use `--bg2`; hover states lift to `--bg3`. The hierarchy is legible without any shadow calculation.

**Floating surface shadows:** Modals, popovers, the progress drawer, and the copy toast float above the app surface. These use a single shadow value: `0 30px 90px rgba(0,0,0,0.55)` (dark) / `0 24px 80px rgba(20,28,40,0.16)` (light). This is a deep umbra (not a diffuse glow) — sharp-ish falloff, heavy base. It roots the floating element firmly.

**Backdrop blur:** The header uses `backdrop-filter: saturate(180%) blur(18px)` — this is the only surface with blur. Modal overlays use `backdrop-filter: blur(8px)` on the scrim. No other surface uses blur.

### Named Rules

**The Flat-By-Default Rule.** Panels, columns, toolbars, and list items are flat. They achieve visual separation through tonal surface steps and 1px border lines, not shadows. If you find yourself adding `box-shadow` to a panel component, reconsider: use a `border-bottom` or a surface-step change instead.

## 5. Components

### Buttons

Five variants, each with a distinct semantic meaning. Do not mix variant styles.

- **Shape:** Consistently 8px radius (medium), height 30px for header buttons, natural height for inline action buttons.
- **Primary (`button-primary`):** iOS Action Blue (`#0a84ff`) fill, white text. The Sync button. Used for the most important action in a given context. One per toolbar section maximum.
- **KB Action (`button-kb`):** Amber-tinted background (`color-mix(in srgb, #e8a000 10%, surface)`) with amber text and amber-tinted border. Generate button (solid amber fill, white text), KB toolbar buttons (tinted variant). Amber fill = "LLM will run now." Amber tint = "relates to KB/LLM."
- **Ghost (`button-ghost`):** Surface-colored background, body-text label, border-strong outline. Default state for all secondary toolbar buttons. On hover, border and text shift to the accent-primary blue.
- **Finish (`button-finish`):** `#22aa66` solid fill, white text. Copy+Done, Mark Done. Used only for actions that complete or archive an item.
- **Danger (`button-danger`):** Surface background, danger-red text and border. Delete, Spam. Tinted red background on hover (10% red mix).

**Focus treatment:** 3px `box-shadow` ring at 20% opacity of the button's accent color. No outline offset.

**Disabled state:** `opacity: 0.45`, `filter: saturate(0.55)`. Hover produces no color change.

### Email List Items

- **Default:** Transparent background, 1px transparent border. Rounded corners (10px). Sender name at 13px weight 650.
- **Hover:** Raised surface (`--bg2`) fill.
- **Selected:** Blue-tinted background (`color-mix(in srgb, accent-primary 10%, surface-base)`), blue-tinted border. No left-stripe accent — the full border carries the selection signal.
- **Unread:** Blue-tinted background (6% blue mix), bold sender and subject.
- **Unread dot:** `accent-primary` fill with 2px halo at 18% opacity.
- **KB badge:** Amber pill (border-radius 999px), amber text, amber-tinted background at 11%.

### Folder Items

- **Default:** Transparent, rounded (8px), full-width.
- **Selected:** Blue-tinted fill, bright text. No left accent stripe (removed in macOS refresh).
- **Hover:** Raised surface fill.

### Inputs / Text Fields

- **Style:** 1px `border-strong` stroke, 8px radius, `input-surface` background (`#202228` dark).
- **Focus:** Border shifts to `accent-primary`, `box-shadow` 3px ring at 20% opacity.
- **Caret:** Always `accent-kb` (Signal Amber) in text inputs where LLM interaction happens (chat input). `accent-primary` in settings forms.
- **Disabled:** `opacity: 0.38`.

### Modals / Dialogs

- **Container:** 14px radius, `surface-base` background, `border-strong` border, `0 30px 90px var(--shadow)` elevation.
- **Header:** `surface-raised` background, 13px title at weight 650. Title color is `text-bright` (not amber — amber was the earlier pattern, now superseded).
- **Scrim:** `rgba(0,0,0,0.34)`, `backdrop-filter: blur(8px)`.
- **Close button:** Muted by default, shifts to `accent-danger` on hover.

### Thread View

- **Message bubbles:** `surface-base` background, 1px `border-subtle` bottom divider.
- **Current/active message:** `accent-kb` left border (3px), 4% amber-tinted background. This is one of the few legitimate left-border uses: a thread position indicator, not a decorative card stripe.

### Status Bar / LLM Health Dot

- **Health dot:** 8px circle. Gray when unknown, `accent-finish` green when healthy, `accent-danger` red on error, `accent-kb` amber when testing (with a scale pulse animation — the only permitted pulsing element).
- **Status dots:** 5px circles. Green = active, amber = busy (pulse), red = error.

### Progress Drawer

- **Container:** Fixed bottom-right, `surface-raised` bg, `border-strong` border, no right/bottom border. No border-radius at full size.
- **Progress bar:** `accent-kb` amber fill on `surface-high` track.
- **Minimized state:** 8px radius pill at bottom, 24px height. Single amber progress line.

## 6. Do's and Don'ts

### Do:

- **Do** use `color-mix(in srgb, <accent> 10–16%, surface)` for tinted hover and selected backgrounds — it automatically adapts across dark and light themes.
- **Do** keep all five surface steps (`--bg0` through `--bg4`) in strict order. A component that should sit "above" an adjacent one must use a lighter surface step, not a shadow.
- **Do** use amber exclusively for LLM/knowledge-related actions. When adding a new feature, decide its semantic color before writing any CSS.
- **Do** keep border-radius at 8px for buttons and inputs, 10px for cards and list items, 14px for modals. These three steps carry all the hierarchy needed.
- **Do** use the system font stack. Never add a web font import for UI chrome.
- **Do** anchor floating surfaces with the deep shadow (`0 30px 90px var(--shadow)`). Shallow `box-shadow` values look unmoored in this dark environment.

### Don't:

- **Don't** use border-left or border-right greater than 1px as a colored stripe on cards, list items, or callout boxes. The old amber left-stripe on selected folder items and the pre-refresh email list is removed in the macOS refresh. The thread-message amber left border (3px) is the only exception — it is a positional indicator in a scroll context, not a card decoration.
- **Don't** use Generic SaaS aesthetics: cream backgrounds, rounded-everything, purple/indigo brand accents, floating card grids. This UI runs locally. It should feel like it does.
- **Don't** use gradient text (`background-clip: text` + gradient). All text is a solid token color.
- **Don't** reintroduce uppercase labels or wide letter-spacing (`text-transform: uppercase`, `letter-spacing: 2px`). These were removed in the macOS refresh. Weight and muted color carry hierarchy.
- **Don't** apply `glow`, `bloom`, or oversized outer shadows (`box-shadow: 0 0 20px`) for decorative lighting effects. The No-Neon Rule is absolute: color-matched halos are permitted only for focus rings (3px, 20% alpha) and unread-dot indicators (2px, 18% alpha).
- **Don't** use glassmorphism (`backdrop-filter: blur`) on anything except the header bar and modal scrims. Never add blur to panels, list items, or cards.
- **Don't** reuse a semantic accent for a second purpose. Amber is not for warnings. Green is not for active states. If a new feature needs its own accent, add a new semantic role.
- **Don't** use corporate mail client aesthetics: heavy toolbars, blue-on-white color schemes, icon-heavy chrome. This is not Outlook.
- **Don't** use overwrought dark mode patterns: neon colors on pure black, GPU-demo glow effects, heavy shadow stacking. The dark theme is calibrated, not theatrical.
