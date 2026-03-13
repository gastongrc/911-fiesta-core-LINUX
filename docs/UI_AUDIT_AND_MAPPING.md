# 911 Fiesta Core — UI Audit & Design Mapping

**Date:** 2026-03-13
**Phase:** Analysis only — No implementation
**Constraint:** The current tab structure and system architecture must remain unchanged.

---

## Table of Contents

1. [Step 1 — WEB Interface Audit](#step-1--web-interface-audit)
2. [Step 2 — CORE UI Audit](#step-2--core-ui-audit)
3. [Step 3 — Conceptual Mapping](#step-3--conceptual-mapping)
4. [Protected Tab Structure](#protected-tab-structure)

---

## Step 1 — WEB Interface Audit

**Source:** `webapp/src/` — React + CSS (control-room.css as source of truth)

### 1.1 Layout Structure

| Element          | Implementation                                                    |
|------------------|-------------------------------------------------------------------|
| **App wrapper**  | `.app` — `display: flex; min-height: 100vh`                       |
| **Sidebar**      | `.side` — Fixed left, 68px wide, `backdrop-filter: blur(40px)`    |
| **Main content** | `.main` — Flex column, `margin-left: 68px`, fills remaining space |

The sidebar contains a **logo block** (40×40px, green gradient, "911" branding) and
**icon navigation buttons** (42×42px, rounded 11px). An active nav item shows a 2.5px
green left-edge indicator with glow.

### 1.2 Card Structure (Glassmorphism)

Three tiers of glass panels:

| Class    | Background                  | Border                          | Radius | Padding |
|----------|-----------------------------|---------------------------------|--------|---------|
| `.g`     | `rgba(255,255,255,0.05)`    | `rgba(255,255,255,0.18)`        | 20px   | 24px    |
| `.gp`    | Same glass base             | Same border family              | 16px   | 16px    |
| `.inset` | `rgba(255,255,255,0.03)`    | `rgba(255,255,255,0.08)`        | 12px   | 12px    |

All cards use `backdrop-filter: blur(40px) saturate(180%)` and include:
- `::before` — 1px gradient top border (shine line)
- `::after` — Diagonal gradient overlay for depth
- `:hover` — `translateY(-2px)`, brighter border, enhanced shadow

Shadow system: `0 8px 32px 0 rgba(0,0,0,0.37), inset 0 1px 0 0 rgba(255,255,255,0.1)`

### 1.3 Spacing System

Consistent 4px base scale:

```
--s-xs:   4px      --s-sm:   8px      --s-md:  12px
--s-base: 16px     --s-lg:  20px      --s-xl:  24px
--s-2xl:  32px     --s-3xl: 40px
```

Grid gaps: `20px`. Card padding: 24/16/12px (by tier). Sub-element gaps: 8–12px.

### 1.4 Typography

| Role        | Font             | Weights         |
|-------------|------------------|-----------------|
| Headlines   | Space Grotesk    | 400–800         |
| Body        | Inter            | 300–900         |
| Monospace   | JetBrains Mono   | 400–700         |

Text hierarchy through opacity:
- `--t1`: `#f0f0f0` (primary)
- `--t2`: `rgba(240,240,240,0.65)` (secondary)
- `--t3`: `rgba(240,240,240,0.38)` (tertiary)
- `--t4`: `rgba(240,240,240,0.20)` (muted)

Base body size: 14px. Utilities: `.text-sm` 12px, `.text-base` 14px, `.text-lg` 16px.

### 1.5 Sidebar Behavior

- Fixed position, always visible, 68px (56px on mobile)
- Logo: Green gradient badge with glow
- Nav buttons: Icon-only, 42×42px, rounded
- Active indicator: 2.5px green left stripe + glow
- LED status dot: 7px green circle with breathing animation (2.5s)

### 1.6 Dashboard Grid Rules

- **Metrics row:** `repeat(auto-fit, minmax(200px, 1fr))`, gap 20px
- **Main cards:** `repeat(auto-fit, minmax(320px, 1fr))`, gap 20px
- **Sub-grids:** `repeat(3, 1fr)`, gap 12px
- **Full-width items:** `gridColumn: 1 / -1`
- **Responsive:** At ≤768px, sidebar shrinks to 56px, card padding to 16px

### 1.7 Color System

| Token        | Value       | Usage                    |
|-------------|-------------|--------------------------|
| `--green`   | `#00e676`   | Primary accent, enabled  |
| `--cyan`    | `#4dd0e1`   | Secondary accent, info   |
| `--blue`    | `#42a5f5`   | Tertiary accent          |
| `--yellow`  | `#ffd740`   | Warning                  |
| `--orange`  | `#ff9800`   | Caution                  |
| `--red`     | `#ff5252`   | Error, offline           |
| `--off`     | `#8a8a8a`   | Disabled                 |

Background: `#0a0a0a` with floating blobs (500–650px, blur 120px, 22–30s animation).

### 1.8 Visual Principles Summary

1. **Glassmorphism** — Frosted panels with backdrop blur, semi-transparent borders
2. **Neon LED glow** — Green/cyan accents with box-shadow glow halos
3. **Dark-first** — Near-black `#0a0a0a` base, minimal bright text
4. **Animated atmosphere** — Floating blobs, radial gradients, noise overlay
5. **Micro-interactions** — Hover lift (2px), press sink, breathing LEDs
6. **Border radius scale** — 8/12/16/20/24px consistent rounding
7. **Transition easing** — `cubic-bezier(0.25, 0.46, 0.45, 0.94)`, 0.25–0.35s

---

## Step 2 — CORE UI Audit

**Source:** `main.py`, `neon_styles.py`, `ui/*.py` — PySide6

### 2.1 Window & Tab System

```
QMainWindow (frameless, fullscreen)
└─ QWidget (body)
   └─ QVBoxLayout (margins=0, spacing=0)
      ├─ QWidget (top bar: audio status + VU dBFS)
      │  └─ QHBoxLayout (margins=8,8,8,8)
      └─ QScrollArea
         └─ QWidget (page)
            └─ QVBoxLayout (margins=0, spacing=0)
               └─ QTabWidget (14 tabs)
```

The tab bar uses horizontal tabs at the top. Styling:
- Tab background: `#121218`, text: `#a0a0b0`, padding: `10px 20px`
- Selected tab: text `#00d4ff`, 3px cyan bottom border, bg `#181820`

### 2.2 Tab Inventory

| Tab               | Type             | Grid Cols | Condition           |
|-------------------|------------------|-----------|---------------------|
| Bajada            | Analyzer grid    | 4         | Always              |
| Base Golpe        | Analyzer grid    | 4         | Always              |
| Ataque            | Analyzer grid    | 3         | Always              |
| Brake             | Analyzer grid    | 3         | Always              |
| Legacy            | Analyzer grid    | 4         | Always              |
| Cues Monitor      | Custom widget    | —         | if CUES_AVAILABLE   |
| Monitor           | Composite layout | —         | Always              |
| Red / Consola     | Form/config      | —         | Always              |
| Health            | Metrics grid     | —         | Always              |
| TAP Tempo         | Clock widget     | —         | if TAP_TEMPO_AVAILABLE |
| Vision Haze       | Preview + LEDs   | —         | if VISION_AVAILABLE |
| Vision DJ         | Zone editor      | 5 zones   | if VISION_AVAILABLE |
| Vision Artist     | Zone editor      | 8 zones   | if VISION_AVAILABLE |
| Calendario        | Schedule editor  | —         | if CALENDAR_TAB_AVAILABLE |

### 2.3 Layout Containers

| Context              | Layout       | Margins        | Spacing |
|----------------------|-------------|----------------|---------|
| Tab content (standard) | QVBoxLayout | (8,8,8,8)     | 10px    |
| Health tab           | QVBoxLayout | (12,12,12,12)  | 12px    |
| Module grids         | QGridLayout | (10,10,10,10)  | 12px    |
| Status indicator box | QGridLayout | (8,8,8,8)      | 6px     |
| Monitor widgets row  | QHBoxLayout | (8,8,8,8)      | 8px     |
| Network panel        | QVBoxLayout | (12,12,12,12)  | 8px     |
| Top bar              | QHBoxLayout | (8,8,8,8)      | 0       |
| Main body wrapper    | QVBoxLayout | (0,0,0,0)      | 0       |

The `make_grid(modules, cols)` helper dynamically calculates rows from module count
and places module `.card` widgets into a QGridLayout with equal column stretch.

### 2.4 Widget Composition

Each analyzer module renders as a card (QFrame) placed into the grid. The card
contains controls, indicators, and parameters specific to the analyzer.

Key patterns:
- **Waveform host:** QFrame (120px fixed height) — shared waveform widget reparented on tab switch
- **Status box:** QFrame (65px fixed) with 6-column grid of state indicators
- **LED indicator:** Custom QWidget paintEvent drawing filled/empty circles
- **Zone editor:** QLabel subclass with drag-and-drop regions

### 2.5 Sidebar Structure

**There is no sidebar.** Navigation is via the horizontal QTabBar at the top.
The top bar only shows audio connection status and VU level.

### 2.6 Spacing Rules

```
Standard margins:   8px all sides
Extended margins:  12px (Health, Network tabs)
Grid item margins: 10px all sides
Grid spacing:      12px
Subsection spacing: 4–8px
Fixed heights:     120px (waveform), 65px (status), 260px min (module card row)
```

### 2.7 Color Palette (neon_styles.py)

| Token            | Value      | Role                    |
|------------------|-----------|-------------------------|
| NEON_CYAN        | `#00d4ff` | Primary accent          |
| NEON_CYAN_DARK   | `#00a8cc` | Borders                 |
| NEON_GREEN       | `#00ff88` | Active/success          |
| NEON_ORANGE      | `#ff9500` | Warnings                |
| NEON_RED         | `#ff3366` | Errors                  |
| NEON_PURPLE      | `#9945ff` | Secondary accent        |
| BG_DARK          | `#0a0a0f` | Window background       |
| BG_PANEL         | `#121218` | Panel background        |
| BG_CARD          | `#181820` | Card background         |
| TEXT_PRIMARY     | `#e0e0e8` | Main text               |
| TEXT_SECONDARY   | `#a0a0b0` | Labels                  |
| TEXT_MUTED       | `#606070` | Disabled                |

### 2.8 Typography

| Font stack                            | Usage        |
|---------------------------------------|-------------|
| Segoe UI / SF Pro Display / sans-serif | Display text |
| JetBrains Mono / Consolas / monospace  | Code/values  |

Sizes: 9px (indicators), 10px (small), 11px (base), 12px (section headers), 14px (titles).
Weights: 400 (regular), 600 (semi-bold headers), 700 (bold accents).

### 2.9 Stylesheet Mechanism

Global stylesheet via `get_full_stylesheet()` combining:
`MAIN_WINDOW_STYLE + TAB_WIDGET_STYLE + BUTTON_STYLE + PROGRESS_BAR_STYLE +
SLIDER_STYLE + COMBOBOX_STYLE + LINEEDIT_STYLE + SPINBOX_STYLE +
GROUPBOX_STYLE + SCROLLAREA_STYLE`

Per-widget overrides via inline `setStyleSheet()` for dynamic state coloring.

---

## Step 3 — Conceptual Mapping

### 3.1 Structural Mapping

| WEB Concept               | CORE Equivalent                     | Notes                                      |
|---------------------------|-------------------------------------|--------------------------------------------|
| `.app` flex container     | QMainWindow → QWidget body          | Both use full-viewport flex/box layouts     |
| `.side` fixed sidebar     | QTabBar (horizontal)                | **Structural gap** — CORE has no sidebar    |
| `.main` content area      | QScrollArea → QTabWidget            | Content fills remaining space in both       |
| `.g` glass card           | QFrame (module card)                | Target for glassmorphism adaptation         |
| `.gp` glass panel         | QFrame (section frame)              | Inner containers (status, VU, etc.)         |
| `.inset` inset panel      | Nested QFrame sections              | Sub-panels within cards                     |
| CSS Grid dashboard        | `make_grid()` QGridLayout           | Both use columnar grids with auto rows      |
| `.tabs` navigation pills  | QTabBar::tab                        | Both use pill/button-style tab selectors    |
| `.led-dot` breathing LED  | LEDIndicator paintEvent             | Both draw glowing circles with animation    |
| `.gauge` progress bar     | QProgressBar                        | Direct mapping possible                     |
| `.key` button             | QPushButton                         | Both have hover/press states                |
| `.b` badge                | QLabel (inline styled)              | Status badges map to small styled labels    |
| Input / Select fields     | QLineEdit / QComboBox / QSpinBox    | Direct counterparts exist                   |

### 3.2 Visual Language Translation

#### Background & Atmosphere

| WEB                                 | CORE Today                | Recommended Adaptation                         |
|-------------------------------------|---------------------------|-----------------------------------------------|
| `#0a0a0a` body bg                   | `#0a0a0f` BG_DARK         | Already aligned. Keep `#0a0a0f`.              |
| Floating blobs + noise overlay      | None                      | Not applicable to PySide (performance cost).   |
| Radial gradient canvas              | Flat dark bg              | Optional: subtle QLinearGradient on body.      |

#### Card Glassmorphism

| WEB                                    | CORE Today               | Recommended Adaptation                         |
|----------------------------------------|---------------------------|-----------------------------------------------|
| `rgba(255,255,255,0.05)` bg            | `#181820` solid           | Use semi-transparent bg via stylesheet         |
| `backdrop-filter: blur(40px)`          | Not available in Qt       | **Cannot replicate** — use solid approximation |
| `rgba(255,255,255,0.18)` border        | `1px solid #333`          | Change to `rgba(255,255,255,0.15)` border     |
| 20px border-radius                     | 3–6px radius              | Increase to 12–16px on cards                   |
| `translateY(-2px)` hover               | No hover animation        | Not practical on QFrame (not interactive)      |
| Inset top-shine gradient               | None                      | Add via QSS `border-top: 1px solid rgba(…)`   |
| Shadow: `0 8px 32px rgba(0,0,0,0.37)` | None                      | PySide QGraphicsDropShadowEffect possible      |

#### Color Alignment

| WEB Token   | WEB Value   | CORE Token      | CORE Value  | Delta        | Action                |
|-------------|-------------|-----------------|-------------|--------------|----------------------|
| `--green`   | `#00e676`   | NEON_GREEN      | `#00ff88`   | Close        | Align to `#00e676`   |
| `--cyan`    | `#4dd0e1`   | NEON_CYAN       | `#00d4ff`   | Different    | Align to `#00e676` for primary, keep cyan as secondary |
| `--red`     | `#ff5252`   | NEON_RED        | `#ff3366`   | Close        | Align to `#ff5252`   |
| `--yellow`  | `#ffd740`   | NEON_ORANGE     | `#ff9500`   | Different    | Add `#ffd740` as warning, keep orange |
| `--off`     | `#8a8a8a`   | TEXT_MUTED      | `#606070`   | Close        | Align to `#8a8a8a`   |

**Key decision:** The WEB uses green (`#00e676`) as its primary accent, while CORE uses
cyan (`#00d4ff`). The WEB's primary accent can be adopted in CORE for consistency, or
both can coexist (green = active/status, cyan = UI chrome/labels).

#### Typography Alignment

| WEB                   | CORE                     | Recommended Adaptation                    |
|-----------------------|--------------------------|------------------------------------------|
| Space Grotesk (titles)| Segoe UI (all)           | Add Space Grotesk for section titles      |
| Inter (body)          | Segoe UI (all)           | Switch body to Inter for consistency      |
| JetBrains Mono (code) | JetBrains Mono (code)   | Already aligned                           |
| 14px base             | 11px base                | Increase base to 13px                     |
| `--t1`/`--t2`/`--t3` hierarchy | TEXT_PRIMARY/SECONDARY/MUTED | Adopt 4-level opacity hierarchy  |

#### Spacing Alignment

| WEB                | CORE            | Recommended Adaptation                    |
|--------------------|-----------------|------------------------------------------|
| 4px base scale     | Ad-hoc 6–12px   | Adopt 4px scale: 4/8/12/16/20/24/32      |
| 20px grid gap      | 12px grid gap    | Increase grid spacing to 16–20px          |
| 24px card padding  | 8–10px margins   | Increase card padding to 16–20px          |
| 20px border-radius | 3–6px radius     | Increase radius scale to 8/12/16/20px     |

#### Tab Styling

| WEB `.tab`                    | CORE `QTabBar::tab`          | Recommended Adaptation                    |
|-------------------------------|------------------------------|------------------------------------------|
| Pill shape, 12px radius       | Rectangle, 4px radius        | Increase to 10–12px radius               |
| `rgba(0,230,118,0.1)` active bg | `#181820` active bg        | Use green-tinted bg for selected tab      |
| Green glow ring on active     | Cyan bottom border           | Add subtle green glow via box properties  |
| 13px Inter font               | 11px Segoe UI                | Increase to 12–13px, switch font          |

#### Button Styling

| WEB `.key`                     | CORE QPushButton              | Recommended Adaptation                   |
|--------------------------------|-------------------------------|------------------------------------------|
| Green gradient bg              | Flat colored bg               | Add gradient background                   |
| 10px border-radius             | 4–6px radius                  | Increase to 10px                          |
| Keycap shadow (3D bevel)       | Flat                          | Add subtle QSS box-shadow approximation   |
| Press: 2px sink                | No animation                  | Add :pressed translateY via margin trick   |

#### Progress Bar / Gauge

| WEB `.gauge`                    | CORE QProgressBar            | Recommended Adaptation                   |
|---------------------------------|------------------------------|------------------------------------------|
| 6px height, green→cyan gradient | 20px height, solid #22aa88   | Reduce height to 8px, add gradient fill   |
| Glow shadow on fill             | No glow                      | Approximate with border + color           |
| 4px border-radius               | 8px radius                   | Align to 6px                              |

### 3.3 What Cannot Be Directly Mapped

| WEB Feature                     | Reason                                           |
|---------------------------------|--------------------------------------------------|
| `backdrop-filter: blur()`       | Not available in Qt stylesheets                  |
| CSS `::before`/`::after`        | No pseudo-elements in QSS                        |
| CSS transitions/animations      | QSS is static; requires QPropertyAnimation       |
| Floating blob backgrounds       | Performance-prohibitive in PySide                |
| `translateY` hover effects      | QFrames are not interactive; only buttons respond |
| CSS Grid `auto-fit minmax()`    | QGridLayout uses fixed column counts              |

### 3.4 What Maps Cleanly

| Concept                         | Mapping Quality | Notes                                    |
|---------------------------------|----------------|------------------------------------------|
| Dark background                 | Excellent       | Already nearly identical                  |
| Color palette                   | Good            | Minor value adjustments needed            |
| JetBrains Mono for values       | Exact           | Already used in both                      |
| Card/panel hierarchy            | Good            | QFrame tiers match glass tiers            |
| Grid-based dashboard            | Good            | QGridLayout serves same purpose           |
| LED indicators                  | Good            | Both use painted circles with glow        |
| Progress bars                   | Good            | Direct widget counterpart                 |
| Tab navigation                  | Moderate        | Horizontal tabs exist but style differs   |
| Button states                   | Moderate        | :hover/:pressed supported in QSS         |
| Input styling                   | Moderate        | QLineEdit/QComboBox accept similar QSS    |
| Border-radius scale             | Moderate        | Requires consistent QSS updates           |

---

## Protected Tab Structure

The following tabs **must not** be renamed, reordered, added to, or removed:

```
Bajada
Base Golpe
Ataque
Brake
Legacy
Cues Monitor
Monitor
Red / Consola
Health
TAP Tempo
Vision Haze
Vision DJ
Vision Artist
Calendario
```

These are part of the system architecture. Any visual redesign must operate
**within** each tab's existing widget tree, not alter the tab structure itself.

---

## Summary of Findings

### The WEB design language CAN be applied to CORE by:

1. **Updating `neon_styles.py`** — Aligning colors, border-radius, padding, and font
   sizes to match the WEB design tokens
2. **Adopting the WEB spacing scale** — 4px base with consistent 8/12/16/20/24px steps
3. **Increasing border-radius** — From 3–6px to 12–16px for glass-like panels
4. **Adding semi-transparent borders** — `rgba(255,255,255,0.15)` instead of solid `#333`
5. **Font alignment** — Inter for body, Space Grotesk for titles, increase base size
6. **Color alignment** — Unify accent colors between WEB and CORE palettes
7. **Improving tab styling** — Pill-shaped tabs with green active indicator
8. **Enhancing progress bars** — Thinner, gradient fills, glow approximation

### The WEB design language CANNOT directly provide:

1. Backdrop blur (glassmorphism transparency effect)
2. CSS transitions/hover animations on non-interactive widgets
3. Pseudo-element decorations (::before/::after shine lines)
4. Floating blob atmospheric backgrounds
5. CSS Grid auto-fit responsive reflow (QGridLayout is fixed-column)

### Recommended approach for implementation phase:

Apply changes **only** through `neon_styles.py` and per-widget `setStyleSheet()` calls.
Do not restructure layouts, rename tabs, or add new windows. The visual refresh should
be purely cosmetic — new colors, spacing, radius, and typography — applied to the
existing widget tree.
