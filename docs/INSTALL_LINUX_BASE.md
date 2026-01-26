# Instalacion Linux Base - 911 Fiesta V7

## Requisitos de Sistema

### Ubuntu/Debian

```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Python 3.10+ y dependencias de build
sudo apt install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    build-essential

# Dependencias para OpenCV
sudo apt install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libxcb-xinerama0

# Dependencias para Qt/PySide6
sudo apt install -y \
    libxkbcommon0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xfixes0 \
    libegl1-mesa

# Dependencias para Audio (sounddevice)
sudo apt install -y \
    libportaudio2 \
    portaudio19-dev

# FFmpeg para PyAV (streams RTSP)
sudo apt install -y \
    ffmpeg \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev
```

### Fedora/RHEL

```bash
sudo dnf install -y \
    python3.11 \
    python3.11-devel \
    mesa-libGL \
    portaudio-devel \
    ffmpeg-devel
```

---

## Instalacion SHOW Runtime (con GUI)

```bash
# Crear entorno virtual
cd /path/to/911-fiesta-V7
python3.11 -m venv .venv
source .venv/bin/activate

# PyTorch con CUDA (si hay GPU NVIDIA)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# O PyTorch CPU-only
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Dependencias SHOW
pip install -r requirements/show.lock.txt

# Verificar
python scripts/smoke_show.py
```

---

## Instalacion SERVER Runtime (headless)

Para servidores sin GUI (API only):

```bash
# Crear entorno virtual
python3.11 -m venv .venv-server
source .venv-server/bin/activate

# Instalar dependencias SERVER
pip install -r requirements/server.lock.txt

# Verificar
python scripts/smoke_server.py

# Ejecutar servidor
python -m api.main
# o
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

---

## Docker para SERVER

### Dockerfile.server

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Dependencias de sistema para OpenCV headless
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements/server.lock.txt requirements/

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements/server.lock.txt

# Copiar codigo
COPY api/ api/
COPY services/ services/
COPY core/ core/

# Puerto
EXPOSE 8000

# Comando
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Build y Run

```bash
docker build -f Dockerfile.server -t 911fiesta-api:latest .
docker run -d -p 8000:8000 --name fiesta-api 911fiesta-api:latest
```

---

## Separacion SHOW vs SERVER

| Componente | SHOW | SERVER | Notas |
|------------|------|--------|-------|
| PySide6/Qt | Si | No | Solo UI |
| torch/YOLO | Si | No | Vision GPU |
| opencv-python | Si | - | Con GUI |
| opencv-python-headless | - | Si | Sin GUI |
| sounddevice/librosa | Si | No | Audio |
| FastAPI/uvicorn | Opcional | Si | API |

---

## Packaging Recomendaciones

### AppImage (SHOW desktop)

Para distribuir como aplicacion standalone:

1. Usar `python-appimage` o `briefcase`
2. Incluir Qt plugins
3. Incluir modelos YOLO

### Debian Package (SERVER)

Para deploy en servidores Debian/Ubuntu:

```bash
# Estructura basica
911fiesta-server/
  DEBIAN/
    control
    postinst
  usr/
    lib/
      911fiesta/
        .venv/
        api/
        services/
    bin/
      911fiesta-api
  etc/
    systemd/
      system/
        911fiesta-api.service
```

### Systemd Service

```ini
# /etc/systemd/system/911fiesta-api.service
[Unit]
Description=911 Fiesta API Server
After=network.target

[Service]
Type=simple
User=fiesta
WorkingDirectory=/opt/911fiesta
Environment="PATH=/opt/911fiesta/.venv/bin"
ExecStart=/opt/911fiesta/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## Troubleshooting

### "cannot open shared object file: libGL.so.1"

```bash
sudo apt install libgl1-mesa-glx
```

### "qt.qpa.plugin: Could not load the Qt platform plugin"

```bash
export QT_QPA_PLATFORM=xcb
# o para headless:
export QT_QPA_PLATFORM=offscreen
```

### "ALSA lib pcm.c: Unknown PCM"

Instalar ALSA utils:
```bash
sudo apt install alsa-utils
```

### PyAV / FFmpeg errors

```bash
sudo apt install ffmpeg libavcodec-dev libavformat-dev
pip uninstall av
pip install av --no-binary av
```
