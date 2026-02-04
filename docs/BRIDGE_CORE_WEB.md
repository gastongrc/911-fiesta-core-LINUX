# BRIDGE CORE → WEB

Arquitectura de comunicación entre el CORE (main.py) y la Web (Control Room V7).

## Principio Fundamental

**La web es un ESPEJO del CORE, no un cerebro.**

- NO genera estado propio
- NO inventa datos
- Si algo no existe → muestra OFFLINE

## Arquitectura de Puertos

```
┌─────────────────────────────────────────────────────────────────┐
│                         CORE (main.py)                          │
│                    PyQt GUI + Sistema completo                  │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │StateManager │  │CalendarMgr  │  │VisionManager│            │
│  │ get_state() │  │ get_state() │  │ handlers[]  │            │
│  │get_energy() │  │ go/override │  │             │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│         │                │                │                    │
│         └────────────────┼────────────────┘                    │
│                          ▼                                     │
│               ┌─────────────────────┐                          │
│               │  http_snapshot.py   │                          │
│               │  HTTP Server :8010  │                          │
│               │  GET /core/snapshot │                          │
│               └─────────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ HTTP (127.0.0.1)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Server :8000                           │
│                    (FastAPI - uvicorn)                          │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                    status.py router                      │  │
│  │                                                          │  │
│  │  GET /api/v1/status/unified                             │  │
│  │       └──→ forward to http://127.0.0.1:8010/core/snapshot│  │
│  │                                                          │  │
│  │  GET /api/v1/stream (SSE)                               │  │
│  │       └──→ forward snapshot cada 500ms                   │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                  Vision Proxy                            │  │
│  │                                                          │  │
│  │  GET /api/v1/vision/frame/{cam}                         │  │
│  │       └──→ forward to http://127.0.0.1:5000/frame/{cam} │  │
│  │                                                          │  │
│  │  GET /api/v1/vision/stream/{cam}                        │  │
│  │       └──→ forward MJPEG stream                         │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ HTTP
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Web App :3000                              │
│                    (Vite dev / nginx prod)                      │
│                                                                 │
│  Home.jsx    → /api/v1/status/unified (SSE)                    │
│  Calendar.jsx → /api/v1/calendar/*                              │
│  Vision.jsx  → /api/v1/vision/frame/*                          │
└─────────────────────────────────────────────────────────────────┘
```

## Puertos

| Puerto | Servicio | Descripción |
|--------|----------|-------------|
| 8010 | CORE HTTP Snapshot | Solo local (127.0.0.1), expone estado real |
| 8000 | API Server (FastAPI) | Público, forwardea a 8010 y 5000 |
| 5000 | Vision Flask | Solo local, server de cámaras |
| 3000 | Web Dev (Vite) | Frontend React |

## Snapshot Format

`GET http://127.0.0.1:8010/core/snapshot`

```json
{
  "ts": 1738700000,
  "core": {
    "online": true,
    "last_error": null
  },
  "state": "BASE_GOLPE",
  "energy": "MEDIA",
  "audio": {
    "running": true,
    "device": "Scarlett 2i2",
    "level": 0.42,
    "silence": false,
    "clipping": false
  },
  "avolites": {
    "connected": true,
    "ip": "192.168.1.100",
    "port": 4430,
    "latency_ms": 12,
    "last_error": null
  },
  "cameras": {
    "haze": {"online": true, "fps": 30, "ip": "192.168.1.50"},
    "people": {"online": true, "fps": 25, "ip": "192.168.1.51"},
    "tracking": {"online": false, "fps": 0, "ip": ""}
  },
  "calendar": {
    "day": "viernes",
    "time": "23:45:00",
    "current_mode": "boliche_desarrollo",
    "next_mode": "boliche_fin",
    "time_remaining_s": 900,
    "time_to_next_s": 900,
    "override_active": false,
    "auto": true
  },
  "system": {
    "cpu": 45,
    "ram": 62,
    "gpu": 0,
    "temp": 0
  }
}
```

## Calendar Commands (CORE 8010)

```bash
# GET WEEK - obtener schedule semanal
curl http://127.0.0.1:8010/core/calendar/week

# GO - cambiar modo
curl -X POST http://127.0.0.1:8010/core/calendar/go \
  -H "Content-Type: application/json" \
  -d '{"mode": "boliche_desarrollo"}'

# OVERRIDE - forzar modo temporalmente
curl -X POST http://127.0.0.1:8010/core/calendar/override \
  -H "Content-Type: application/json" \
  -d '{"mode": "artista", "minutes": 30}'

# CLEAR OVERRIDE - volver a automático
curl -X POST http://127.0.0.1:8010/core/calendar/clear_override \
  -H "Content-Type: application/json" -d '{}'

# AUTO - toggle modo automático
curl -X POST http://127.0.0.1:8010/core/calendar/auto \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# SAVE - guardar schedule semanal
curl -X POST http://127.0.0.1:8010/core/calendar/save \
  -H "Content-Type: application/json" \
  -d '{"week": {"monday": [], "friday": [{"from": "22:00", "to": "06:00", "mode": "boliche_desarrollo"}]}}'
```

Respuesta:
```json
{"ok": true, "error": null, "calendar": {"current_mode": "boliche_desarrollo", ...}}
```

## Smoke Test

### Test 1: CORE detecta DJ
1. Activar cámara tracking en CORE
2. Verificar en web: `cameras.tracking.online = true`
3. Verificar FPS actualiza

### Test 2: Avolites conecta
1. Conectar Titan en CORE
2. Verificar en web: `avolites.connected = true`
3. Verificar IP y latency

### Test 3: State cambia
1. CORE procesa audio y cambia a ATAQUE
2. Verificar en web: `state = "ATAQUE"`
3. Panel CORE STATUS muestra ATAQUE con color naranja

### Test 4: Vision frame
1. Abrir Vision en web
2. Si cámara online, debe mostrar preview real
3. Frame se refresca cada 2 segundos

## Archivos Clave

| Archivo | Propósito |
|---------|-----------|
| `core/http_snapshot.py` | HTTP server en CORE, expone snapshot |
| `main.py` | Inicia snapshot server con managers |
| `api/routers/status.py` | Forward a 8010, SSE stream |
| `api/main.py` | Vision proxy a 5000 |
| `webapp/src/pages/Home.jsx` | Consume SSE, muestra state/energy |
| `webapp/src/pages/Vision.jsx` | Muestra frames via proxy |

## Calendar SAVE Smoke Test

```bash
#!/bin/bash
# smoke_test_calendar.sh

API="http://127.0.0.1:8000/api/v1"
CORE="http://127.0.0.1:8010"

echo "=== 1. GET week ANTES ==="
curl -s "$API/calendar/week" | jq '.week.monday'

echo ""
echo "=== 2. POST save ==="
curl -s -X POST "$API/calendar/save" \
  -H "Content-Type: application/json" \
  -d '{"week": {"monday": [{"from": "23:00", "to": "23:30", "mode": "clima_1"}], "tuesday": [], "wednesday": [], "thursday": [], "friday": [], "saturday": [], "sunday": []}}' \
  | jq '{success, week_monday: .week.monday}'

echo ""
echo "=== 3. GET week DESPUÉS ==="
curl -s "$API/calendar/week" | jq '.week.monday'

echo ""
echo "=== 4. CORE directo ==="
curl -s "$CORE/core/calendar/week" | jq '.week.monday'
```

### Verificación Manual
1. Abrir `http://localhost:3000/calendar`
2. Tab HORARIOS → Agregar bloque
3. GUARDAR
4. **Sin F5**: bloque debe aparecer inmediatamente

## gridRev Fix (re-render)

**Problema**: React no re-renderizaba la grilla después de SAVE porque los keys eran estáticos.

**Solución** (`Calendar.jsx:243`):
```javascript
// ANTES (bug)
<div key={day} ...>

// DESPUÉS (fix)
<div key={`${day}-${gridRev}`} ...>
```

Donde `gridRev` se incrementa en `handleSave()` línea 615:
```javascript
setGridRev(r => r + 1); // Force grid repaint
```

## Troubleshooting

### Web muestra "CORE no inicializado"
- Verificar que main.py esté corriendo
- Verificar que http_snapshot.py inició en puerto 8010
- Test: `curl http://127.0.0.1:8010/core/snapshot`

### Vision muestra "Frame no disponible"
- Verificar Flask Vision en puerto 5000
- Verificar cámara online en snapshot
- Test: `curl http://127.0.0.1:5000/frame/haze`

### SSE no conecta
- Verificar proxy en vite.config.js
- Verificar CORS en api/main.py
- Test: abrir `/api/v1/stream` en browser
