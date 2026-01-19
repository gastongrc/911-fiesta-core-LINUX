# Vision System Phase 6.6 + WebApp Phase 7

Sistema de visión integrado para 911 Fiesta con detección de personas, humo/neblina y tracking de movimiento.

## 📦 Estructura

```
911-fiesta/
├── core/                    # Núcleo del sistema de visión
│   ├── vision_router.py     # Router de frames a sensores
│   ├── camera_manager.py    # Gestión de cámaras
│   └── smart_camera.py      # Wrapper inteligente sobre OpenCV
│
├── sensors/                 # Sensores especializados
│   ├── camera_people.py     # Detección de personas (HOG)
│   ├── camera_haze.py       # Detección de humo/neblina
│   ├── camera_tracking.py   # Tracking de movimiento (optical flow)
│   └── vision_diagnostics.py # Diagnóstico del sistema
│
├── api_server.py            # Flask API REST
│
└── webapp/                  # WebApp Phase 7 - Zone Editor
    ├── src/
    │   ├── components/      # Componentes React
    │   │   ├── CameraSelector.jsx
    │   │   ├── CameraStream.jsx
    │   │   ├── ZoneEditor.jsx
    │   │   ├── ZoneProperties.jsx
    │   │   ├── PeopleEditor.jsx
    │   │   ├── HazeEditor.jsx
    │   │   └── TrackingEditor.jsx
    │   ├── api/
    │   │   └── vision.js    # Cliente API
    │   ├── App.jsx
    │   ├── main.jsx
    │   └── global.css
    ├── package.json
    ├── vite.config.js
    └── index.html
```

## 🚀 Instalación

### Backend (Python)

```bash
# Instalar dependencias
pip install -r requirements.txt
```

### Frontend (WebApp)

```bash
cd webapp
npm install
```

## 🎯 Uso

### 1. Iniciar API Server

```bash
python api_server.py
```

El servidor estará en `http://localhost:5000`

### 2. Iniciar WebApp

```bash
cd webapp
npm run dev
```

La webapp estará en `http://localhost:3000`

## 📡 API Endpoints

### Status
- `GET /vision/status` - Estado del sistema

### Cámaras
- `GET /vision/devices` - Lista dispositivos disponibles
- `POST /vision/camera/<id>/start` - Iniciar cámara
- `POST /vision/camera/<id>/stop` - Detener cámara
- `GET /vision/frame/<id>?annotate=true&sensor=people` - Obtener frame

### Zonas
- `GET /vision/zones/<id>?sensor=people` - Obtener zonas
- `POST /vision/zones/<id>` - Configurar zonas

### Detecciones
- `GET /vision/detections/<id>?sensor=people` - Obtener detecciones actuales

### Health
- `GET /health` - Health check

## 🎨 Sensores Disponibles

### 1. People Detection (`people`)
Detecta personas usando HOG (Histogram of Oriented Gradients).

**Zonas:** Define áreas donde contar personas.

**Salida:**
- `total_people`: Total de personas detectadas
- `zones[].people_count`: Personas por zona

### 2. Haze/Smoke Detection (`haze`)
Detecta humo/neblina mediante análisis de contraste y luminosidad.

**Zonas:** Define áreas sensibles al humo.

**Propiedades:**
- `sensitivity`: Sensibilidad (0.1-5.0, default 1.0)

**Salida:**
- `haze_detected`: Boolean
- `haze_level`: Nivel 0-100%
- `brightness`, `contrast`: Métricas

### 3. Motion Tracking (`tracking`)
Tracking de movimiento usando optical flow.

**Zonas:** Define áreas donde detectar movimiento.

**Propiedades:**
- `sensitivity`: Sensibilidad (0.1-5.0, default 1.0)

**Salida:**
- `motion_detected`: Boolean
- `motion_level`: Nivel 0-100%
- `direction`: Dirección del movimiento (N, NE, E, etc.)

## 🔧 Configuración de Zona

Cada zona tiene:

```json
{
  "id": "zone_123456",
  "name": "Stage Area",
  "points": [[x1, y1], [x2, y2], ...],
  "enabled": true,
  "sensitivity": 1.0
}
```

## 💡 Uso en WebApp

1. **Seleccionar cámara** - Elegir cámara activa
2. **Seleccionar sensor** - People / Haze / Tracking
3. **Dibujar zonas** - Click para agregar puntos
4. **Configurar** - Ajustar propiedades de zona
5. **Ver detecciones** - Monitoreo en tiempo real

## 🔗 Integración con Sistema Existente

Este sistema **NO modifica** ningún archivo existente:

- ✅ PySide6 UI intacto
- ✅ Audio engine intacto
- ✅ CueEngine intacto
- ✅ StateManager intacto
- ✅ WebApp legacy intacto

## 📝 Notas

- El Vision Router corre a ~30 FPS
- Los sensores procesan frames en paralelo
- Las zonas se guardan vía API (no persisten automáticamente)
- OpenCV debe estar instalado (`opencv-python` en requirements.txt)

## 🎭 Ejemplo de Uso Programático

```python
from core.vision_router import VisionRouter
from core.camera_manager import CameraManager
from core.smart_camera import SmartCamera
from sensors.camera_people import CameraPeopleSensor

# Setup
router = VisionRouter()
cam_mgr = CameraManager()
people_sensor = CameraPeopleSensor()

# Registrar sensor
router.register_sensor('people', people_sensor)

# Crear cámara
camera = SmartCamera(device_id=0)
camera.start()

# Registrar cámara
cam_mgr.add_camera('cam1', camera)
router.register_camera('cam1', camera)

# Configurar zona
zones = [{
    'id': 'zone1',
    'name': 'Entry',
    'points': [[100, 100], [200, 100], [200, 200], [100, 200]],
    'enabled': True
}]
people_sensor.set_zones('cam1', zones)

# Crear ruta
router.add_route('cam1', 'people')

# Iniciar router
router.start()

# Obtener detecciones
detections = people_sensor.get_detections('cam1')
print(detections)
```

---

**Version:** 6.6 + 7.0
**Status:** ✅ Integrado sin romper nada existente
