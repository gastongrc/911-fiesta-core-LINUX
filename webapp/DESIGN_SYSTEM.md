# 911 Fiesta Control Room — Design System

> **Estado:** Aprobado (V7 Home + Calendar V2)  
> **Fecha:** Febrero 2026  
> **Archivos de referencia:** `911-fiesta-v7.html` (Home), `911-fiesta-calendar-v2.html` (Calendar)

---

## 1. Identidad Visual

### Concepto
Glassmorphism sobre fondo oscuro con gradientes grises. Estética de **hardware profesional**: botones tipo keycap mecánico con profundidad 3D, LEDs realistas, gauges circulares. Nada de colores planos ni UI genérica — todo tiene profundidad, brillo sutil y materialidad.

### Inspiraciones clave
- Glassmorphism con backdrop-blur pesado (32px)
- Botones estilo teclas de teclado mecánico (gradientes internos, sombras 3D, highlight superior)
- LEDs con gradiente radial y glow realista
- Gauges circulares SVG tipo dial de cámara
- Strips verticales expandibles (estilo art gallery) para vistas de datos semanales

---

## 2. Paleta de Colores

### Acentos (SOLO estos 3 + gris para inactivo)
```css
--green: #00e676;        /* Primario — estados activos, acciones principales, "hoy" */
--cyan: #4dd0e1;         /* Secundario — datos, valores, métricas */
--blue: #42a5f5;         /* Terciario — módulos especiales, acciones alternativas */
--off: #8a8a8a;          /* Inactivo / offline / disabled */
```

### Variantes del verde (uso frecuente)
```css
--green-g: rgba(0,230,118,0.35);   /* Glow */
--green-20: rgba(0,230,118,0.20);  /* Borders activos */
--green-10: rgba(0,230,118,0.10);  /* Backgrounds sutiles */
--green-05: rgba(0,230,118,0.05);  /* Backgrounds mínimos */
```

### Texto (sobre fondo oscuro)
```css
--t1: #f0f0f0;                     /* Primario — títulos, valores importantes */
--t2: rgba(240,240,240,0.65);      /* Secundario — labels, descripciones */
--t3: rgba(240,240,240,0.38);      /* Terciario — hints, subtexto */
--t4: rgba(240,240,240,0.20);      /* Muted — separadores, placeholders */
```

### Superficies
```css
--glass: rgba(40,40,40,0.45);      /* Fondo de cards glass */
--glass-b: rgba(255,255,255,0.08); /* Border de cards */
--glass-bh: rgba(255,255,255,0.14);/* Border hover */
--glass-top: rgba(255,255,255,0.06);/* Inset top highlight */
--inset: rgba(0,0,0,0.22);         /* Campos internos, sub-contenedores */
```

### ⛔ PROHIBIDO
- Naranja, rojo, amarillo como colores de acento decorativo
- Gradientes de color saturado en fondos
- Verde neón (#00ff8c) — se usa #00e676 que es más suave
- Blanco puro como fondo o acento

---

## 3. Tipografía

| Fuente | Uso | Pesos |
|--------|-----|-------|
| **Space Grotesk** | Números grandes, títulos de sección, valores de estado, reloj | 400, 500, 600, 700, 800 |
| **Inter** | Body, labels, UI general, botones | 300–900 |
| **JetBrains Mono** | Valores técnicos, badges, timestamps, IPs, códigos | 400, 500, 600, 700 |

### Import
```html
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```

### Escalas típicas
- Reloj grande: Space Grotesk 48px, weight 800
- Títulos de página: Space Grotesk 24px, weight 700
- Títulos de card: Inter 13.5px, weight 600
- Labels UPPERCASE: 9-10px, letter-spacing 1-2px
- Valores técnicos: JetBrains Mono 11-12px
- Badges: JetBrains Mono 9.5px, weight 600

---

## 4. Fondo y Atmósfera

### Fondo base
```css
body { background: #0a0a0a; }
```

### Gradiente principal (SOLO GRISES — sin color)
```css
background:
  radial-gradient(ellipse 65% 55% at 70% 15%, rgba(180,180,180,0.12), transparent 70%),
  radial-gradient(ellipse 50% 45% at 20% 75%, rgba(140,140,140,0.08), transparent 60%),
  radial-gradient(ellipse 55% 60% at 50% 45%, rgba(100,100,100,0.05), transparent 55%),
  linear-gradient(155deg, #0f0f0f 0%, #161616 25%, #1a1a1a 40%, #141414 60%, #0a0a0a 100%);
```

### Blobs flotantes (grises, blur 90px)
3-4 elementos con `border-radius: 50%`, `filter: blur(90px)`, animación `blobFloat` lenta (19-30s). Colores: `rgba(150-220, 150-220, 150-220, 0.07-0.14)`.

### Vignette
```css
radial-gradient(ellipse 75% 75% at 50% 50%, transparent 25%, rgba(5,5,5,0.55) 100%)
```

### Noise texture
SVG inline con `feTurbulence`, opacity 0.028.

---

## 5. Componentes

### 5.1 Glass Card (`.g`)
El componente más usado. Toda card usa glassmorphism.

```css
.g {
  background: rgba(40,40,40,0.45);
  backdrop-filter: blur(32px);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 18px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.25), 0 1px 3px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.06);
}
```

**Pseudo-elementos obligatorios:**
- `::before` — Gradiente diagonal de luz (165deg, blanco 8% → 3% → transparent)
- `::after` — Línea inferior sutil centrada

**Hover:** border más visible + shadow más profunda + translateY(-1px)

### 5.2 Keycap Buttons (`.key`)
Botones tipo tecla mecánica con efecto 3D.

```css
.key {
  background: linear-gradient(180deg, rgba(70,70,70,0.95) 0%, rgba(50,50,50,0.98) 50%, rgba(38,38,38,1) 100%);
  border: 1px solid rgba(255,255,255,0.07);
  box-shadow: 0 3px 0 0 rgba(15,15,15,0.9), 0 4px 10px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.08);
  border-radius: 10px;
  font-size: 10px; font-weight: 600; text-transform: uppercase;
}
```

**Variantes activas:**
- `.kg` (green): fondo verde translúcido, border verde, glow verde
- `.kb` (blue): fondo azul translúcido, border azul, glow azul
- `.kc` (cyan): fondo cyan translúcido, border cyan, glow cyan

**Highlight superior:** `::before` con gradiente blanco tenue (simula luz en tecla).

**Interacción:** hover translateY(-1px), active translateY(2px) con sombra aplastada.

### 5.3 LED Indicators (`.led`)
```css
/* LED encendido verde */
.led-g {
  width: 10px; height: 10px; border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #80ffb0, #00e676 55%, #007a40);
  box-shadow: 0 0 6px rgba(0,230,118,0.5), 0 0 14px rgba(0,230,118,0.15);
}
/* LED apagado gris */
.led-r {
  background: radial-gradient(circle at 35% 30%, #c0c0c0, #8a8a8a 55%, #4a4a4a);
  box-shadow: 0 0 4px rgba(160,160,160,0.25);
}
```
Incluyen `::before` para reflejo de luz (punto blanco pequeño arriba-izquierda).

### 5.4 Badges (`.b`)
```css
.b {
  padding: 3px 9px; border-radius: 6px;
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.5px;
  text-transform: uppercase; font-family: 'JetBrains Mono';
}
```
Variantes: `.b-live` (green + dot animado), `.b-ok` (cyan), `.b-off` (gris), `.b-auto` (green sutil).

### 5.5 Gauges Circulares SVG
Círculos SVG con `stroke-dasharray` / `stroke-dashoffset` para representar porcentajes. Fondo inset circular con sombra interna. Colores: cyan para CPU, green para RAM/intensidad.

### 5.6 Inset Containers
Sub-contenedores dentro de cards:
```css
.inset {
  border-radius: 12px;
  background: rgba(0,0,0,0.22);
  border: 1px solid rgba(255,255,255,0.03);
  padding: 14px 16px;
}
```

### 5.7 Form Controls (Select / Input)
```css
background: rgba(0,0,0,0.22);
border: 1px solid rgba(255,255,255,0.06);
border-radius: 8-9px;
font-family: 'JetBrains Mono'; font-size: 11px;
color: var(--t1);
```
Focus: `border-color: rgba(0,230,118,0.2)`.  
Select usa custom chevron SVG como background-image.

### 5.8 Action Buttons (`.cc-btn`)
```css
/* GO (green) */
background: linear-gradient(180deg, rgba(0,200,100,0.3), rgba(0,160,80,0.25));
color: var(--green); border: 1px solid rgba(0,230,118,0.2);
box-shadow: 0 3px 0 0 rgba(0,50,25,0.5), 0 4px 12px rgba(0,0,0,0.25);

/* ALT (cyan) */
background: linear-gradient(180deg, rgba(77,208,225,0.2), rgba(60,170,185,0.15));
color: var(--cyan); border: 1px solid rgba(77,208,225,0.15);
```

---

## 6. Sidebar

Ancho fijo: **68px**. Posición fixed. Fondo: `rgba(10,10,10,0.7)` con blur 40px.

### Logo
40x40px, border-radius 12px, gradiente verde (`#00e676 → #00c864 → #00a850`), sombra con glow verde, highlight superior (::after). Texto "911" en JetBrains Mono 10px black.

### Nav buttons
42x42px, border-radius 11px. Íconos SVG 19px stroke. Activo: fondo sutil + barra lateral verde (2.5px, glow).

### Indicador de conexión
Dot verde 7px con glow, animación `breathe` (2.5s).

---

## 7. Layouts por Sección

### 7.1 HOME (Control Room) — Aprobado V7
**Estructura:** Hero (3 cols) + Right Stack (1 col, span 3 rows) + cards debajo.

- **Hero:** Estado core (BAJADA/MEDIA) con cajas inset + gauge circular de intensidad
- **Right Stack:** Calendario (reloj + modo + timeline), Sistema (2 gauges CPU/RAM), Módulos (keycaps)
- **Cards debajo:** Audio, Avolites, Vision — data rows con LEDs

Grid: `grid-template-columns: 1fr 1fr 1fr 270px`

### 7.2 CALENDAR — Aprobado V2
**Estructura:** Sub-tabs arriba → Status Hero → Vertical Day Strips.

**Sub-tabs:** Estado | Horarios | Control — tabs con estilo glass, línea verde inferior en activo, íconos SVG.

**Vista Estado:** Muestra todo (hero + strips)  
**Vista Horarios:** Solo strips (hero oculto)  
**Vista Control:** Solo drawer de control (3 cards: Cambiar Modo, Extender Bloque, Override Temporal)

**Day Strips (concepto clave):**
- 7 strips verticales lado a lado, sin gap, unidos visualmente
- El día actual ("hoy") tiene `background: rgba(0,230,118,0.04)` y texto verde
- Click en un strip → se expande (flex: 3.5), los demás se colapsan (flex: 0.55)
- Colapsado: muestra nombre del día rotado 90° vertical (writing-mode o transform rotate)
- Expandido: muestra bloques horarios con timeline vertical (línea + dots)
- Cada bloque tiene: horario (JetBrains Mono), nombre del modo (Space Grotesk bold), tags de extras
- Tags con color por tipo: Haze=cyan, Audio=green, DJ=blue, Strobe=amarillo, Laser=rojo
- Botón "+ Agregar" con border dashed al final de cada día
- Bloque activo: border verde, dot timeline verde con glow

**Status Hero (3 cards horizontales):**
- Clock: reloj 48px + fecha
- Mode: modo actual con progress bar + próximo bloque + origen
- Modules: lista compacta con LEDs + stats

---

## 8. Animaciones

### Entrada de cards
```css
@keyframes slideUp {
  from { opacity: 0; transform: translateY(18px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
/* Stagger: delay incremental de 0.03-0.05s por card */
```

### Entrada de strips
```css
@keyframes stripIn {
  from { opacity: 0; transform: scaleY(0.95); }
  to { opacity: 1; transform: scaleY(1); }
}
/* transform-origin: top; delay incremental 0.03s */
```

### Respiración (LEDs, dots)
```css
@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
/* Duración: 1.5-2.5s */
```

### Blobs flotantes
```css
@keyframes blobFloat {
  0%,100% { transform: translate(0,0) scale(1); }
  25% { transform: translate(30px,-25px) scale(1.05); }
  50% { transform: translate(-20px,30px) scale(0.95); }
  75% { transform: translate(25px,15px) scale(1.03); }
}
/* Duración: 19-30s por blob */
```

### Transiciones generales
- Cards hover: `0.35s cubic-bezier(0.25,0.46,0.45,0.94)`
- Keycaps: `0.12s ease`
- Day strips expand/collapse: `0.4s cubic-bezier(0.25,0.46,0.45,0.94)`

---

## 9. Principios de Diseño

### ✅ SÍ hacer
- Glassmorphism con blur pesado (32px) en todas las cards
- Profundidad 3D en botones (sombras escalonadas, highlights internos)
- LEDs con gradiente radial realista
- Íconos SVG inline (no emoji, no icon fonts)
- Jerarquía clara: Space Grotesk para valores, JetBrains Mono para datos técnicos
- Acentos de color mínimos y con propósito (verde=activo, cyan=dato, blue=módulo)
- Gradientes grises en fondo (NUNCA color)
- Transiciones suaves con cubic-bezier custom

### ⛔ NO hacer
- Fondos de color sólido o gradientes coloridos
- Bordes gruesos o visibles
- Tipografía genérica (Arial, Roboto, system fonts)
- Sombras box-shadow básicas
- Cards sin backdrop-filter
- Más de 3 colores de acento
- Layouts de grid genéricos tipo dashboard template
- Emojis como íconos (usar SVG)

---

## 10. Secciones Pendientes

Las siguientes secciones aún no fueron diseñadas y deben seguir este design system:

- **Vision** — Feeds de cámaras (Haze Detection, People Counter, DJ Tracking)
- **Network** — Interfaces de red, config Avolites Console
- **Presets** — Grid de archivos JSON de configuración
- **Config** — Avolites Configuration, Cue Offset, Module Control
