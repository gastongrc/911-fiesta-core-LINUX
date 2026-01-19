# Frontend Audit Phase 3 - 911 Fiesta WebApp

**Fecha:** 2025-12-28
**Version:** 8.0.0
**Estado:** INCOMPLETO - Build fallido

---

## Estado General

| Aspecto | Estado | Detalle |
|---------|--------|---------|
| Existe webapp/ | OK | `webapp/` con Vite + React 18 |
| package.json | OK | v8.0.0, deps actualizadas |
| node_modules | REQUIERE `npm install` | No versionados |
| Build | FALLA | Missing `src/lib/utils.js` |
| Router | OK | 6 rutas definidas |
| Store | OK | Zustand con polling |

### Build Error Crítico
```
Could not resolve "../lib/utils" from "src/components/Layout.jsx"
```
**7 archivos** importan `lib/utils` pero el directorio NO existe:
- `components/Layout.jsx`
- `components/ui/Badge.jsx`
- `components/ui/Button.jsx`
- `components/ui/Card.jsx`
- `components/ui/Input.jsx`
- `pages/Analyze.jsx`
- `pages/Cues.jsx`

**Fix requerido:** Crear `webapp/src/lib/utils.js`:
```javascript
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
```

---

## Stack Técnico

| Librería | Versión | Uso |
|----------|---------|-----|
| react | ^18.2.0 | UI framework |
| react-dom | ^18.2.0 | DOM rendering |
| react-router-dom | ^6.20.0 | Routing |
| zustand | ^4.4.7 | State management |
| axios | ^1.6.2 | HTTP client |
| lucide-react | ^0.294.0 | Icons |
| tailwindcss | ^3.3.6 | CSS utility |
| vite | ^5.0.0 | Build tool |

---

## Arquitectura de Rutas

| Ruta | Página | Componente | Estado |
|------|--------|------------|--------|
| `/` | Home | Dashboard status | OK |
| `/analyze` | Analyze | Analyzers real-time | OK |
| `/cues` | Cues | Fire/Kill manual | OK |
| `/network` | Network | Interface + Console | OK |
| `/presets` | Presets | Save/Load config | OK |
| `/config` | Config | Avolites + Modules | OK |

**Nota:** `App.jsx` existe pero NO se usa (legacy Vision-only UI). Entry point usa `router.jsx`.

---

## Tabla por Sección Mandatoria

| Sección | Implementado | Endpoint(s) | Método | UX |
|---------|--------------|-------------|--------|-----|
| **Cámaras (dual stream)** | NO | `/vision/*` | fetch | Solo en App.jsx legacy |
| **Estados de humo (haze)** | NO | - | - | No existe |
| **Detección DJ** | NO | - | - | No existe |
| **Tracking (personas)** | NO | `/vision/detections/*` | fetch | Solo componentes legacy |
| **Manual cues** | SI | `/api/v1/cues/fire`, `/api/v1/cues/kill` | POST/DELETE | Grid + Fire/Force/Kill |
| **Artist cues** | NO | - | - | No existe |
| **Configuración** | PARCIAL | `/api/v1/config/*` | GET/POST | Avolites offset + modules |
| **Calendario inteligente** | NO | - | - | No existe |
| **API (status)** | SI | `/api/v1/status`, `/health` | GET | Dashboard con polling |
| **Red** | SI | `/api/v1/network/*` | GET/POST | Interface + Console + Ping |
| **Licencia** | NO | - | - | No existe |
| **Presets** | SI | `/api/v1/presets`, `/api/v1/save`, `/api/v1/load` | GET/POST | List/Save/Load |
| **Analyzers** | SI | `/api/v1/analyzers`, `/api/v1/analyzers/active` | GET | By state + energy |

---

## API Endpoints Consumidos

### Backend Principal (axios → localhost:8000)

| Endpoint | Método | Archivo API | Página |
|----------|--------|-------------|--------|
| `/health` | GET | status.js | - |
| `/api/v1/status` | GET | status.js | Home |
| `/api/v1/cues` | GET | cues.js | Cues |
| `/api/v1/cues/fire` | POST | cues.js | Cues |
| `/api/v1/cues/kill` | DELETE | cues.js | Cues |
| `/api/v1/analyzers` | GET | analyzers.js | Analyze |
| `/api/v1/analyzers/active` | GET | analyzers.js | - |
| `/api/v1/analyzers/matching` | GET | analyzers.js | - |
| `/api/v1/config/{section}` | GET | config.js | Config |
| `/api/v1/config/{section}` | POST | config.js | Config |
| `/api/v1/network/interfaces` | GET | network.js | Network |
| `/api/v1/network/interface` | POST | network.js | Network |
| `/api/v1/network/console` | POST | network.js | Network |
| `/api/v1/network/ping` | POST | network.js | Network |
| `/api/v1/presets` | GET | presets.js | Presets |
| `/api/v1/save` | POST | presets.js | Presets |
| `/api/v1/load` | POST | presets.js | Presets |

### Vision (fetch → /vision)

| Endpoint | Método | Archivo API | Componente |
|----------|--------|-------------|------------|
| `/vision/status` | GET | vision.js | App.jsx (legacy) |
| `/vision/devices` | GET | vision.js | CameraSelector |
| `/vision/camera/{id}/start` | POST | vision.js | CameraSelector |
| `/vision/camera/{id}/stop` | POST | vision.js | CameraSelector |
| `/vision/zones/{id}` | GET | vision.js | ZoneEditor |
| `/vision/zones/{id}` | POST | vision.js | ZoneEditor |
| `/vision/detections/{id}` | GET | vision.js | CameraStream |
| `/vision/frame/{id}` | GET | vision.js | CameraStream |

---

## Integración Backend

| Tipo | Implementado | Detalles |
|------|--------------|----------|
| **HTTP polling** | SI | setInterval en startPolling() |
| **WebSocket** | NO | No implementado |
| **SSE** | NO | No implementado |
| **Mocks** | NO | Solo conexión directa a localhost:8000 |

### Zustand Store - Polling

```javascript
// useSystemStore.js
startPolling('status', 1000);   // Home - cada 1s
startPolling('analyzers', 500); // Analyze - cada 500ms
startPolling('cues', 1000);     // Cues - cada 1s
```

---

## UX: Popup y Dirty State

### Popup para Manual Cue Activo
| Requerimiento | Estado |
|---------------|--------|
| Mostrar popup cuando hay cue manual activo | NO |
| Bloquear navegación | NO |
| Indicador visual persistente | PARCIAL (toast temporal) |

**Hallazgo:** La página Cues tiene `showKillDialog` modal para confirmar "Kill All", pero NO hay popup persistente para indicar que hay cues activos. Solo hay badges temporales.

### Dirty State + Botón SAVE
| Requerimiento | Estado |
|---------------|--------|
| Detectar cambios no guardados | NO |
| Habilitar SAVE solo si dirty | NO |
| Confirmación al salir con cambios | NO |

**Hallazgo:**
- Config.jsx: SAVE siempre habilitado (no compara estado inicial vs actual)
- Network.jsx: SAVE siempre habilitado
- Presets.jsx: Solo dialogs modales, sin dirty tracking

---

## Componentes Vision (Legacy)

Estos componentes existen pero NO están integrados en el router:

| Componente | Archivo | Uso |
|------------|---------|-----|
| CameraSelector | `components/CameraSelector.jsx` | Selección de cámara + sensor |
| CameraStream | `components/CameraStream.jsx` | Stream de video + detecciones |
| ZoneEditor | `components/ZoneEditor.jsx` | Edición de zonas |
| ZoneProperties | `components/ZoneProperties.jsx` | Propiedades de zona |
| HazeEditor | `components/HazeEditor.jsx` | Estados de humo |
| TrackingEditor | `components/TrackingEditor.jsx` | Tracking personas |
| PeopleEditor | `components/PeopleEditor.jsx` | Configuración people detection |

**Problema:** App.jsx usa estos componentes directamente pero main.jsx carga el router, no App.jsx. Los componentes Vision están huérfanos.

---

## Resumen de Gaps Críticos

### 1. Build Roto (BLOQUEANTE)
- Falta `src/lib/utils.js` con función `cn()`

### 2. Secciones Faltantes
- Calendario inteligente
- Artist cues
- Licencia
- DJ detection display
- Haze states dashboard
- Vision integrada en router

### 3. UX Mandatoria No Implementada
- Popup persistente para cues activos
- Dirty state tracking
- SAVE button condicional

### 4. Sin Real-Time Alternativo
- Solo HTTP polling
- No WebSocket para eventos push
- No SSE para streams

---

## Plan de Ejecución (3 Pasos)

### Paso 1: Fix Build + Estructura Base
1. Crear `webapp/src/lib/utils.js`
2. Verificar build exitoso
3. Añadir rutas faltantes al router:
   - `/vision` - Vision dashboard
   - `/calendar` - Calendario inteligente
   - `/license` - Licencia

### Paso 2: Integrar Vision + Secciones Faltantes
1. Crear página Vision.jsx usando componentes existentes
2. Implementar Calendar.jsx
3. Implementar License.jsx
4. Añadir DJ detection + Haze states al dashboard

### Paso 3: UX Mandatoria
1. Implementar dirty state tracking en Config/Network
2. Añadir ActiveCueIndicator componente global
3. Implementar beforeunload para cambios no guardados
4. Considerar WebSocket para real-time updates

---

## Archivos Relevantes

```
webapp/
├── package.json              # v8.0.0
├── vite.config.js
├── tailwind.config.js
├── src/
│   ├── main.jsx              # Entry → router
│   ├── router.jsx            # 6 rutas
│   ├── App.jsx               # Legacy Vision UI (NO USADO)
│   ├── global.css
│   ├── api/
│   │   ├── axios.js          # Base config localhost:8000
│   │   ├── status.js
│   │   ├── cues.js
│   │   ├── analyzers.js
│   │   ├── config.js
│   │   ├── network.js
│   │   ├── presets.js
│   │   └── vision.js         # fetch-based, no axios
│   ├── store/
│   │   └── useSystemStore.js # Zustand polling store
│   ├── pages/
│   │   ├── Home.jsx
│   │   ├── Analyze.jsx
│   │   ├── Cues.jsx
│   │   ├── Network.jsx
│   │   ├── Config.jsx
│   │   └── Presets.jsx
│   ├── components/
│   │   ├── Layout.jsx        # Sidebar + mobile nav
│   │   ├── CameraSelector.jsx
│   │   ├── CameraStream.jsx
│   │   ├── ZoneEditor.jsx
│   │   ├── ZoneProperties.jsx
│   │   ├── HazeEditor.jsx
│   │   ├── TrackingEditor.jsx
│   │   ├── PeopleEditor.jsx
│   │   └── ui/
│   │       ├── Badge.jsx
│   │       ├── Button.jsx
│   │       ├── Card.jsx
│   │       └── Input.jsx
│   └── lib/                  # MISSING - needs utils.js
```
