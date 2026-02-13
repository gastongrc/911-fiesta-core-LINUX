# 911 FIESTA — UI CONTRACT

Design System Source of Truth para implementación React/Vite.

---

## 📁 SOURCE OF TRUTH FILES

### CSS
- **`control-room.css`** — Design system completo (tokens, componentes, animaciones)

### HTML Mocks (Contratos Visuales)
- **`control_room_glass.html`** — Home / Control Room
- **`calendar_glass.html`** — Calendar V2
- **`status_dashboard.html`** — Status Dashboard (pantalla informativa)
- **`config_panel_pro.html`** — Configuration Panel

### Assets
- **Logo:** `911_fiesta_logo.png` (crear desde el `.s-logo` span con "911")
- **Íconos:** Inline SVG en sidebar (home, calendar, sliders)

---

## 🎨 PALETA & TIPOGRAFÍA

### Colors
```
PRIMARY:
--green: #00e676
--cyan: #4dd0e1
--blue: #42a5f5

STATUS:
--yellow: #ffd740 (warning)
--orange: #ff9800 (modified)
--red: #ff5252 (error)
--off: #8a8a8a (disabled)

TEXT:
--t1: #f0f0f0 (primary)
--t2: rgba(240,240,240,0.65) (secondary)
--t3: rgba(240,240,240,0.38) (tertiary)
--t4: rgba(240,240,240,0.20) (disabled)
```

### Typography
```
TITLES/HEADERS: 'Space Grotesk' (400,500,600,700,800)
BODY/UI: 'Inter' (300-900)
CODE/METRICS: 'JetBrains Mono' (400-700)
```

---

## 🧩 CLASES CLAVE

### Glass Cards
```
.g        — Card principal (padding 24px, blur 40px, saturate 180%)
.gp       — Glass panel (padding 16px, menos prominente)
.inset    — Contenedor interno oscuro (blur 20px)
```

### Buttons (Keycaps)
```
.key         — Primary button (verde, 3D keycap)
.key-2       — Secondary button (neutro)
.key-danger  — Danger button (rojo)
```

### LEDs
```
.led          — LED grande (60x60px, verde por defecto)
.led.yellow   — LED amarillo
.led.red      — LED rojo
.led.off      — LED apagado
.led-sm       — LED pequeño (40x40px)
.led-dot      — LED tiny (7x7px)
```

### Badges
```
.b        — Badge verde
.b.yellow — Badge amarillo
.b.red    — Badge rojo
.b.gray   — Badge gris
```

### Gauges
```
.gauge        — Barra de progreso base
.gauge-fill   — Fill con gradiente verde→cyan
.gauge-fill.warning  — Fill amarillo→naranja
.gauge-fill.error    — Fill rojo
```

### Layout
```
.side   — Sidebar (68px width, backdrop-blur)
.main   — Main content area
.app    — App container (flex)
```

### Tabs
```
.tabs     — Contenedor de tabs horizontales
.tab      — Tab individual
.tab.on   — Tab activo (verde, glow)

.sub-nav  — Sub-navegación (tipo "Estado, Semana, Mes")
.sub-tab  — Sub-tab individual
.sub-tab.on — Sub-tab activo
```

### Calendar
```
.day-strip           — Columna vertical de día
.day-strip.today     — Día actual (verde)
.day-strip.expanded  — Día expandido (flex: 3.5)
.day-strip.collapsed — Día colapsado (flex: 0.55)
```

### Utilities
```
.flex, .flex-col, .items-center, .justify-between
.gap-2, .gap-3, .gap-4
.mt-2, .mt-3, .mt-4, .mb-2, .mb-3, .mb-4
.p-2, .p-3, .p-4
.w-full, .h-full
.text-sm, .text-base, .text-lg, .text-xl
.font-bold, .font-semibold, .font-medium
.mono (JetBrains Mono)
.t1, .t2, .t3, .t4 (colores de texto)
.green, .cyan, .yellow, .red
.opacity-50, .opacity-70
```

---

## ⚠️ 10 REGLAS "NO HACER"

1. **NO inventar nuevos colores** — Usar solo los definidos en `:root`
2. **NO omitir saturate()** — Siempre usar `backdrop-filter: blur(40px) saturate(180%)`
3. **NO usar fade en LEDs** — LEDs usan flash (breathe/pulse), no fade suave
4. **NO backgrounds sólidos** — Todo debe tener transparencia + blur
5. **NO bordes delgados** — Bordes siempre `1px solid rgba(255,255,255,0.18)` mínimo
6. **NO olvidar -webkit-backdrop-filter** — Safari necesita el prefijo
7. **NO blur menor a 40px en cards** — Las `.g` y `.gp` usan 40px mínimo
8. **NO sombras simples** — Usar múltiples capas (externa + inset)
9. **NO mezclar blobs grises** — Los blobs son verde/cyan/azul, no grises
10. **NO spacing aleatorio** — Usar múltiplos de 4px (8, 12, 16, 20, 24, 32, 40)

---

## 🎭 GLASSMORPHISM RECIPE

Receta completa para cualquier card de vidrio:

```css
.my-card {
  position: relative;
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 20px;
  padding: 24px;
  box-shadow: 
    0 8px 32px 0 rgba(0,0,0,0.37),
    inset 0 1px 0 0 rgba(255,255,255,0.1);
  overflow: hidden;
}

.my-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3) 50%, transparent);
}

.my-card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.02) 50%, rgba(0,0,0,0.05) 100%);
  pointer-events: none;
  z-index: 0;
}

.my-card > * {
  position: relative;
  z-index: 1;
}
```

---

## 🎬 ANIMACIONES

```css
@keyframes breathe    — Flash LED (verde/amarillo) 2.5s
@keyframes pulse      — Flash agresivo (rojo) 1.5s
@keyframes flashClip  — Flash super rápido (clip de audio) 0.3s
@keyframes shimmer    — Shimmer de fondo (200% → -200%)
@keyframes slideUp    — Entrada de cards (translateY + opacity)
@keyframes blobFloat  — Movimiento de blobs (translate + scale)
```

---

## 📐 SPACING SYSTEM

Basado en múltiplos de 4px:

```
--s-xs:   4px
--s-sm:   8px
--s-md:   12px
--s-base: 16px
--s-lg:   20px
--s-xl:   24px
--s-2xl:  32px
--s-3xl:  40px
```

---

## 🔧 PLACEHOLDER TOKENS

Los HTML usan placeholders tipo `{{TOKEN}}` que deben ser reemplazados con datos reales:

```
{{VERSION}}
{{CPU}}, {{RAM}}, {{BPM}}, {{UPTIME}}
{{CONSOLE_IP}}, {{CONSOLE_PORT}}, {{LATENCY}}
{{AUDIO_DEVICE}}, {{AUDIO_LEVEL}}, {{AUDIO_STATE}}
{{CAMERAS_ACTIVE}}, {{FPS}}
{{PROTOCOL}}, {{MODE}}, {{TIMEOUT}}
{{NEXT_BLOCK_TIME}}, {{NEXT_BLOCK_NAME}}, {{NEXT_BLOCK_PROGRESS}}
{{TIME}}, {{DATE}}
{{CLIP_STATE}}, {{CLIP_PEAK}}, {{CLIP_HEADROOM}}
{{OFFSET}}, {{CUE_EXAMPLE}}
```

---

## 🎯 BEST PRACTICES

### Hover States
```css
.g:hover {
  transform: translateY(-2px);
  border-color: rgba(255,255,255,0.25);
  background: rgba(255,255,255,0.08);
}
```

### Focus States
```css
input:focus {
  border-color: rgba(0,230,118,0.4);
  box-shadow: 0 0 0 3px rgba(0,230,118,0.1);
}
```

### Transitions
```css
transition: all 0.25s cubic-bezier(0.25,0.46,0.45,0.94);
```

### Border Radius
```
Pequeño (badges, inputs): 8-12px
Mediano (panels): 12-16px
Grande (cards): 20-24px
```

---

## 📦 ESTRUCTURA DE COMPONENTES REACT

Sugerencia de estructura para React:

```
src/
├── components/
│   ├── glass/
│   │   ├── GlassCard.tsx        (componente .g)
│   │   ├── GlassPanel.tsx       (componente .gp)
│   │   └── InsetPanel.tsx       (componente .inset)
│   ├── ui/
│   │   ├── Button.tsx           (keycaps)
│   │   ├── LED.tsx              (LEDs)
│   │   ├── Badge.tsx            (badges)
│   │   ├── Gauge.tsx            (progress bars)
│   │   └── Input.tsx            (inputs)
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   ├── Tabs.tsx
│   │   └── SubNav.tsx
│   └── calendar/
│       └── DayStrip.tsx
├── pages/
│   ├── ControlRoom.tsx
│   ├── Calendar.tsx
│   ├── StatusDashboard.tsx
│   └── ConfigPanel.tsx
└── styles/
    └── control-room.css  (importar globalmente)
```

---

## ✅ CHECKLIST DE IMPLEMENTACIÓN

- [ ] Importar `control-room.css` globalmente
- [ ] Crear componentes base (GlassCard, LED, Badge, etc)
- [ ] Implementar sidebar con navegación
- [ ] Crear background canvas con blobs animados
- [ ] Implementar cada página según su HTML mock
- [ ] Conectar placeholders `{{TOKEN}}` con estado real
- [ ] Probar hover/focus states en todos los elementos
- [ ] Verificar responsive en mobile
- [ ] Testear animaciones de LEDs (flash, no fade)
- [ ] Validar que TODOS los elementos tengan blur + saturate

---

**Versión:** 1.0  
**Fecha:** 2025  
**Stack Target:** React 18 + Vite + TypeScript
