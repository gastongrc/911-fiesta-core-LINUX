# AUDITORÍA WEB V7 - 911 Fiesta Control Room

**Fecha:** 2026-02-04
**Branch:** claude/net-ui-nic-persistence-P0-hXc9c

---

## 1. MAPA DE REQUESTS DEL FRONTEND

### Home.jsx
| Endpoint | Método | Uso |
|----------|--------|-----|
| `/api/v1/stream` | SSE | Real-time status (EventSource) |
| `/api/v1/status/unified` | GET | Fallback polling |

### Calendar.jsx
| Endpoint | Método | Uso |
|----------|--------|-----|
| `/api/v1/calendar/status` | GET | Estado del calendario |
| `/api/v1/calendar/week` | GET | Schedule semanal |
| `/api/v1/calendar/go` | POST | Cambiar modo |
| `/api/v1/calendar/extend` | POST | Extender bloque |
| `/api/v1/calendar/override` | POST | Activar override |
| `/api/v1/calendar/override/stop` | POST | Limpiar override |
| `/api/v1/calendar/save` | POST | Guardar schedule |

### Vision.jsx
| Endpoint | Método | Uso |
|----------|--------|-----|
| `/api/v1/status/unified` | GET | Estado de cámaras |

### Network.jsx, Config.jsx, Presets.jsx
Usan endpoints bajo `/api/v1/*` (network, config, presets).

### BaseURL Actual
- **URLs relativas**: `/api/v1/...`
- **NO existe** `apiBase.js` centralizado
- **NO se usa** `VITE_API_BASE` env var

### SSE
- URL: `/api/v1/stream`
- Reconexión: **NO** (cierra y cae a polling)
- Error handling: Fallback a polling 1000ms
- **PROBLEMA**: Sin proxy, SSE falla silenciosamente

---

## 2. PROXY / CORS

### vite.config.js actual
```javascript
proxy: {
  '/vision': { target: 'http://localhost:5000' },
  '/health': { target: 'http://localhost:5000' }
}
```

### PROBLEMA CRÍTICO
**NO HAY PROXY PARA `/api`** → Las llamadas a `/api/v1/*` fallan con 404 porque Vite no las redirige al backend (puerto 8000).

### CORS en backend
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # OK para dev
    ...
)
```
CORS está configurado correctamente, pero sin proxy las requests ni siquiera llegan al backend.

### Comportamiento en LAN
- Desde celu `http://192.168.x.x:3000` → Las URLs relativas apuntan a `192.168.x.x:3000/api/v1/*`
- Vite dev server no tiene proxy `/api` → **404**
- El backend está en puerto 8000, no 3000

---

## 3. AppState

### Dónde se crea
- **Archivo**: `services/app_state.py`
- **Patrón**: Singleton (`_instance`)
- **Inicialización**: `AppState.initialize(...)` debe ser llamado desde `main.py`

### Por qué aparece "AppState not initialized"
```python
# api/dependencies.py
def get_app_state() -> AppState:
    try:
        app_state = AppState.get_instance()
        if not app_state.is_initialized():
            raise HTTPException(status_code=503, detail="System not initialized")
        return app_state
    except RuntimeError:
        raise HTTPException(status_code=503, detail="AppState not initialized")
```

**Causas del 503:**
1. `uvicorn api.main:app` se corre STANDALONE sin `main.py`
2. `main.py` no llama `AppState.initialize()` antes de iniciar API
3. El CORE tarda en inicializar y la API arranca primero

### En Windows
- No hay diferencia de paths o imports
- El problema es que `uvicorn api.main:app --reload` NO ejecuta `main.py`
- `main.py` es quien inicializa el CORE y llama `AppState.initialize()`

---

## 4. RUNBOOK REPRODUCIBLE

### Levantar correctamente (modo CORE completo)
```bash
# Terminal 1 - Backend + CORE
cd /home/user/911-fiesta-V7
python main.py
# Esto inicia CORE + API en puerto 8000
```

```bash
# Terminal 2 - Frontend
cd /home/user/911-fiesta-V7/webapp
npm install
npm run dev
# Abre en http://localhost:3000
```

### Levantar solo API (modo standalone para dev)
```bash
# NO FUNCIONA porque AppState no se inicializa
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
# Todos los endpoints devuelven 503
```

### URLs para probar salud

| URL | Expected |
|-----|----------|
| `http://localhost:8000/` | `{"service":"911-fiesta-api",...}` |
| `http://localhost:8000/health` | `{"status":"ok","initialized":true/false}` |
| `http://localhost:8000/api/v1/status` | 200 con status completo (si CORE activo) |
| `http://localhost:8000/api/v1/status/unified` | 200 con audio/avolites/cameras/system/calendar |
| `http://localhost:8000/api/v1/stream` | SSE stream (text/event-stream) |

---

## 5. DIAGNÓSTICO FINAL

### Problema 1: Proxy faltante
- **Causa**: `vite.config.js` no tiene proxy para `/api`
- **Efecto**: Frontend no puede conectar al backend
- **Solución**: Agregar proxy `/api` → `http://127.0.0.1:8000`

### Problema 2: URLs hardcodeadas
- **Causa**: Frontend usa `/api/v1/...` que solo funciona con proxy
- **Efecto**: No funciona en LAN ni en producción
- **Solución**: Crear `apiBase.js` con `getApiBase()` dinámico

### Problema 3: SSE sin reconexión
- **Causa**: `EventSource` se cierra en error y no reintenta
- **Efecto**: Pierde conexión permanentemente al primer fallo
- **Solución**: Implementar backoff exponencial (1s, 2s, 5s, 10s)

### Problema 4: AppState 503
- **Causa**: API standalone sin CORE
- **Efecto**: Todos los endpoints devuelven 503
- **Solución**: `get_app_state()` nunca debe tirar 503, devolver estado degradado

---

## 6. SOLUCIÓN PROPUESTA

### Fix 1: vite.config.js
```javascript
proxy: {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true
  },
  '/vision': { target: 'http://localhost:5000' },
  '/health': { target: 'http://localhost:5000' }
}
```

### Fix 2: webapp/src/lib/apiBase.js
```javascript
export function getApiBase() {
  if (import.meta.env.VITE_API_BASE) {
    return import.meta.env.VITE_API_BASE;
  }
  // En dev con proxy, usar relativo
  if (import.meta.env.DEV) {
    return '/api/v1';
  }
  // En prod o LAN, usar hostname dinámico
  return `http://${window.location.hostname}:8000/api/v1`;
}
```

### Fix 3: api/dependencies.py
```python
def get_app_state() -> AppState:
    """Nunca tira 503 - devuelve estado degradado si no está listo"""
    try:
        return AppState.get_instance()
    except RuntimeError:
        # Crear instancia vacía para modo degradado
        return AppState()
```

### Fix 4: SSE con reconexión
```javascript
function connectSSE() {
  let retryDelay = 1000;
  const maxDelay = 10000;

  const connect = () => {
    const es = new EventSource(`${getApiBase()}/stream`);
    es.onopen = () => { retryDelay = 1000; };
    es.onerror = () => {
      es.close();
      setTimeout(connect, retryDelay);
      retryDelay = Math.min(retryDelay * 2, maxDelay);
    };
  };
  connect();
}
```

---

## 7. TODOs PENDIENTES

- [ ] Agregar proxy `/api` en vite.config.js
- [ ] Crear `apiBase.js` con URL dinámica
- [ ] Modificar `get_app_state()` para no tirar 503
- [ ] Implementar reconexión SSE con backoff
- [ ] Probar desde LAN (celu → server)
- [ ] Aplicar estilo NEON (v6.3)
