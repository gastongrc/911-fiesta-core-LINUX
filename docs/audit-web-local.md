# Auditoría Web Local - 911 Fiesta V7

**Fecha:** 2026-02-03
**Commit base:** f0060c9 (main)
**Estado:** AUDITORÍA COMPLETA (sin modificaciones)

---

## 1. Mapa del Web Stack

### 1.1 Árbol de Carpetas Relevantes

```
911-fiesta-V7/
├── webapp/                          # Frontend React
│   ├── package.json                 # React 18 + Vite 5
│   ├── vite.config.js               # Dev server :3000, proxy a :5000
│   ├── index.html                   # Entry HTML
│   ├── tailwind.config.js           # Tailwind CSS config
│   ├── postcss.config.js            # PostCSS
│   ├── src/
│   │   ├── main.jsx                 # Entry point (usa RouterProvider)
│   │   ├── App.jsx                  # ⚠️ HUÉRFANO - Vision Phase 7 UI
│   │   ├── router.jsx               # Rutas: /, /analyze, /cues, /network, /presets, /config
│   │   ├── global.css               # Estilos globales
│   │   ├── api/                     # API clients
│   │   │   ├── axios.js             # Base axios → localhost:8000
│   │   │   ├── status.js
│   │   │   ├── analyzers.js
│   │   │   ├── cues.js
│   │   │   ├── network.js
│   │   │   ├── presets.js
│   │   │   ├── config.js
│   │   │   └── vision.js            # ⚠️ API client Vision (no tiene página)
│   │   ├── pages/
│   │   │   ├── Home.jsx             # Dashboard
│   │   │   ├── Analyze.jsx          # Visualización analizadores
│   │   │   ├── Cues.jsx             # Grid de cues
│   │   │   ├── Network.jsx          # Config de red
│   │   │   ├── Presets.jsx          # Gestión presets
│   │   │   └── Config.jsx           # Configuración sistema
│   │   ├── components/
│   │   │   ├── Layout.jsx           # Layout principal con navegación
│   │   │   ├── CameraSelector.jsx   # ⚠️ Vision - sin página
│   │   │   ├── CameraStream.jsx     # ⚠️ Vision - sin página
│   │   │   ├── ZoneEditor.jsx       # ⚠️ Vision - sin página
│   │   │   ├── PeopleEditor.jsx     # ⚠️ Vision - sin página
│   │   │   ├── HazeEditor.jsx       # ⚠️ Vision - sin página
│   │   │   ├── TrackingEditor.jsx   # ⚠️ Vision - sin página
│   │   │   └── ui/                  # Componentes base (Card, Badge, etc.)
│   │   ├── store/
│   │   │   └── useSystemStore.js    # Zustand store
│   │   └── lib/
│   │       └── utils.js             # cn() helper
│   ├── node_modules/                # ❌ FALTANTE
│   └── dist/                        # ❌ FALTANTE (build)
│
├── api/                             # Backend FastAPI
│   ├── main.py                      # FastAPI app, start_api_server()
│   ├── models.py                    # Pydantic models
│   ├── dependencies.py              # Dependency injection
│   └── routers/
│       ├── status.py                # GET /api/v1/status
│       ├── analyzers.py             # /api/v1/analyzers/*
│       ├── cues.py                  # /api/v1/cues/*
│       ├── network.py               # /api/v1/network/*
│       ├── presets.py               # /api/v1/presets/*
│       ├── config.py                # /api/v1/config/*
│       └── alerts.py                # /api/v1/alerts/*
│
├── api_server.py                    # ⚠️ Backend Flask Vision (INDEPENDIENTE)
│
├── services/
│   ├── app_state.py                 # AppState singleton
│   ├── preset_service.py            # Servicio de presets
│   └── analyzer_service.py
│
└── main.py                          # Entry principal Qt + FastAPI embebido
```

### 1.2 Stack Tecnológico

| Componente | Tecnología | Versión |
|------------|-----------|---------|
| **Frontend** | React + Vite | 18.2 / 5.0 |
| **CSS** | TailwindCSS | 3.3.6 |
| **State** | Zustand | 4.4.7 |
| **Routing** | react-router-dom | 6.20.0 |
| **HTTP Client** | Axios | 1.6.2 |
| **Backend Principal** | FastAPI + Uvicorn | 0.104+ / 0.24+ |
| **Backend Vision** | Flask | (flask-cors 4.0) |
| **Validación** | Pydantic | 2.0+ |

---

## 2. Integración con Sistema Python

### 2.1 Flujo de Arranque

```
python main.py
    │
    ├─> Qt GUI inicializa
    │
    ├─> [100ms] _startup_auto_apply()
    │       └─> Load preset, Audio, NIC, Avolites
    │
    ├─> [threading] start_api_server("0.0.0.0", 8000)
    │       └─> FastAPI en http://localhost:8000
    │       └─> Swagger docs en http://localhost:8000/docs
    │
    └─> [500ms] _execute_bootstrap()
            └─> CueEngine, Calendar, Vision sync
```

### 2.2 Servers y Puertos

| Server | Puerto | Integración | Estado |
|--------|--------|-------------|--------|
| **FastAPI** (api/main.py) | 8000 | Auto (thread desde main.py) | ✅ Funciona |
| **Flask Vision** (api_server.py) | 5000 | ❌ Manual | ⚠️ Debe correrse aparte |
| **Vite Dev** (webapp) | 3000 | ❌ Manual | ⚠️ npm run dev |

### 2.3 Endpoints FastAPI (Puerto 8000)

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/` | GET | API info |
| `/health` | GET | Health check |
| `/docs` | GET | Swagger UI |
| `/api/v1/status` | GET | Estado completo del sistema |
| `/api/v1/analyzers` | GET | Lista de analizadores |
| `/api/v1/cues/fire` | POST | Disparar cue |
| `/api/v1/cues/kill` | POST | Kill cue |
| `/api/v1/cues/kill-all` | POST | Kill all |
| `/api/v1/network/interfaces` | GET | Listar NICs |
| `/api/v1/network/interface` | POST | Set NIC |
| `/api/v1/network/console` | POST | Set Avolites IP |
| `/api/v1/network/ping` | POST | Ping host |
| `/api/v1/presets` | GET | Listar presets |
| `/api/v1/save` | POST | Guardar preset |
| `/api/v1/load` | POST | Cargar preset |
| `/api/v1/config/*` | GET/POST | Configuración |
| `/api/v1/alerts/*` | GET | Alertas |

### 2.4 Endpoints Flask Vision (Puerto 5000)

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/health` | GET | Health check Vision |
| `/vision/status` | GET | Estado sistema visión |
| `/vision/devices` | GET | Listar cámaras |
| `/vision/camera/<id>/start` | POST | Iniciar cámara |
| `/vision/camera/<id>/stop` | POST | Detener cámara |
| `/vision/frame/<id>` | GET | Frame JPEG |
| `/vision/zones/<id>` | GET/POST | Zonas de detección |
| `/vision/detections/<id>` | GET | Detecciones actuales |

---

## 3. Estado Real: Features Incompletas

### 3.1 Problemas Críticos

| ID | Problema | Ubicación | Impacto |
|----|----------|-----------|---------|
| **P1** | `node_modules` faltante | webapp/ | Build imposible |
| **P2** | `dist/` faltante | webapp/ | No hay build de producción |
| **P3** | Flask Vision no arranca auto | api_server.py | Vision web no funciona |
| **P4** | Vision.jsx no existe | webapp/src/pages/ | No hay UI de Vision |
| **P5** | App.jsx huérfano | webapp/src/App.jsx | Código Vision sin usar |
| **P6** | Proxy mismatch | vite.config.js | Solo /vision y /health a :5000 |

### 3.2 Archivos "a Mitad"

```
webapp/src/App.jsx
├─> Es una app completa de Vision Phase 7
├─> Importa CameraSelector, CameraStream, ZoneEditor, visionAPI
├─> NO se usa en router.jsx
└─> main.jsx usa RouterProvider, no App.jsx directamente

webapp/src/api/vision.js
├─> API client completo para Vision
├─> Endpoints: status, devices, cameras, zones, detections
└─> No hay página que lo consuma

webapp/src/components/CameraSelector.jsx
webapp/src/components/CameraStream.jsx
webapp/src/components/ZoneEditor.jsx
webapp/src/components/PeopleEditor.jsx
webapp/src/components/HazeEditor.jsx
webapp/src/components/TrackingEditor.jsx
├─> Componentes Vision completos
└─> Sin ruta en router.jsx
```

### 3.3 Inconsistencias de Configuración

```javascript
// vite.config.js - Proxy
proxy: {
  '/vision': { target: 'http://localhost:5000' },  // Flask Vision
  '/health': { target: 'http://localhost:5000' }   // Flask Vision
}

// axios.js - Base URL
baseURL: 'http://localhost:8000'  // FastAPI
```

**Resultado:** El frontend usa axios para FastAPI (:8000) directamente, y vite proxy solo para Vision (:5000). Esto funciona pero requiere que Flask Vision corra en paralelo.

---

## 4. Reproducibilidad: Cómo Levantar

### 4.1 Backend (FastAPI) - Automático

```bash
# El backend FastAPI arranca automáticamente con main.py
python main.py
# → FastAPI en http://localhost:8000
# → Docs en http://localhost:8000/docs
```

### 4.2 Backend Vision (Flask) - Manual

```bash
# Terminal separada
python api_server.py
# → Flask Vision en http://localhost:5000
# → Health: http://localhost:5000/health
```

### 4.3 Frontend (Vite Dev)

```bash
# Terminal separada
cd webapp

# Instalar dependencias (REQUERIDO - no existe node_modules)
npm install

# Iniciar dev server
npm run dev
# → Frontend en http://localhost:3000
```

### 4.4 Build de Producción

```bash
cd webapp
npm install
npm run build
# → Output en webapp/dist/
```

### 4.5 Variables de Entorno

**No se requiere `.env`** - Las URLs están hardcodeadas:
- axios.js: `http://localhost:8000`
- vite.config.js proxy: `http://localhost:5000`

---

## 5. Dependencias Críticas

### 5.1 Python (requirements.txt)

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
flask-cors==4.0.0
```

### 5.2 Node.js (package.json)

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "axios": "^1.6.2",
    "zustand": "^4.4.7",
    "lucide-react": "^0.294.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.1",
    "vite": "^5.0.0",
    "tailwindcss": "^3.3.6"
  }
}
```

---

## 6. Plan de Recuperación

### Fase 1: "Lo levanto y veo algo" (1-2 horas)

```bash
# 1. Instalar dependencias frontend
cd webapp && npm install

# 2. En terminal 1: Backend principal
python main.py

# 3. En terminal 2: Dev server frontend
cd webapp && npm run dev

# 4. Abrir http://localhost:3000
#    → Deberías ver Home con status del sistema
```

**Verificación:**
- [ ] Home muestra estado (BAJADA/BASE_GOLPE/etc)
- [ ] Analyze muestra analizadores
- [ ] Network muestra NICs
- [ ] Presets lista archivos

### Fase 2: "Web ↔ API estable" (2-4 horas)

1. **Verificar todos los endpoints:**
   ```bash
   # Test FastAPI
   curl http://localhost:8000/api/v1/status
   curl http://localhost:8000/health
   ```

2. **Verificar páginas:**
   - [ ] Home: polling funciona
   - [ ] Analyze: visualización en vivo
   - [ ] Cues: fire/kill funciona
   - [ ] Network: set NIC persiste
   - [ ] Presets: save/load funciona
   - [ ] Config: cambios aplican

3. **Fix potenciales:**
   - Si CORS falla: verificar middleware en api/main.py
   - Si polling falla: verificar useSystemStore.js
   - Si cues no disparan: verificar AppState.avolites

### Fase 3: "Feature Completion + Packaging" (4-8 horas)

1. **Integrar Vision:**
   ```javascript
   // Opción A: Crear Vision.jsx en pages/
   // Opción B: Integrar App.jsx (Vision) en router.jsx
   ```

2. **Arranque automático Flask Vision:**
   ```python
   # En main.py, agregar thread para api_server
   # Similar a start_api_server pero para Flask
   ```

3. **Build de producción:**
   ```bash
   cd webapp
   npm run build
   # Servir dist/ desde FastAPI o nginx
   ```

4. **Configuración de puertos:**
   - Unificar en un solo puerto (FastAPI sirviendo static)
   - O documentar claramente multi-puerto

---

## 7. Checklist de Evidencias

### 7.1 Git ls-files (web)

```bash
git ls-files | grep -E "webapp|api_server"
```

```
api_server.py
webapp/README.md
webapp/index.html
webapp/package-lock.json
webapp/package.json
webapp/postcss.config.js
webapp/src/App.jsx
webapp/src/api/analyzers.js
webapp/src/api/axios.js
webapp/src/api/config.js
webapp/src/api/cues.js
webapp/src/api/network.js
webapp/src/api/presets.js
webapp/src/api/status.js
webapp/src/api/vision.js
webapp/src/components/CameraSelector.jsx
webapp/src/components/CameraStream.jsx
webapp/src/components/HazeEditor.jsx
webapp/src/components/Layout.jsx
webapp/src/components/PeopleEditor.jsx
webapp/src/components/TrackingEditor.jsx
webapp/src/components/ZoneEditor.jsx
webapp/src/components/ZoneProperties.jsx
webapp/src/components/ui/Badge.jsx
webapp/src/components/ui/Button.jsx
webapp/src/components/ui/Card.jsx
webapp/src/components/ui/Input.jsx
webapp/src/global.css
webapp/src/lib/utils.js
webapp/src/main.jsx
webapp/src/pages/Analyze.jsx
webapp/src/pages/Config.jsx
webapp/src/pages/Cues.jsx
webapp/src/pages/Home.jsx
webapp/src/pages/Network.jsx
webapp/src/pages/Presets.jsx
webapp/src/router.jsx
webapp/src/store/useSystemStore.js
webapp/tailwind.config.js
webapp/vite.config.js
```

### 7.2 Ripgrep patterns encontrados

| Pattern | Archivos |
|---------|----------|
| `fastapi` | main.py, api/main.py, requirements.txt |
| `uvicorn` | api/main.py, requirements.txt |
| `flask` | api_server.py, requirements.txt |
| `localhost:8000` | webapp/src/api/axios.js |
| `localhost:5000` | webapp/vite.config.js, api_server.py |
| `/api/v1` | api/main.py, api/routers/*.py |

### 7.3 OpenAPI/Swagger

**Ubicación:** http://localhost:8000/docs (auto-generado por FastAPI)

---

## 8. Resumen Ejecutivo

| Aspecto | Estado | Acción Requerida |
|---------|--------|------------------|
| Frontend código | ✅ Completo | - |
| Frontend build | ❌ Faltante | `npm install` |
| Backend FastAPI | ✅ Funciona | - |
| Backend Vision | ⚠️ Manual | Considerar auto-arranque |
| Vision UI | ❌ Incompleto | Crear Vision.jsx o integrar App.jsx |
| Documentación | ✅ README existe | - |

**Conclusión:** El sistema web está ~80% completo. Falta `npm install`, un build, y la integración de Vision UI. El backend principal funciona correctamente desde main.py.
