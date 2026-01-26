# Instalacion Windows NVIDIA GPU - 911 Fiesta V7

## Requisitos Previos

- Windows 10/11 64-bit
- NVIDIA GPU con soporte CUDA (GTX 10xx o superior)
- NVIDIA Driver >= 525.60.13
- Python 3.10.x o 3.11.x (recomendado: 3.11.9)

## Paso 1: Instalar Python

1. Descargar Python 3.11.9 de https://python.org/downloads/
2. Durante instalacion:
   - Marcar "Add Python to PATH"
   - Marcar "Install for all users" (opcional pero recomendado)
3. Verificar instalacion:

```powershell
python --version
# Python 3.11.9
```

## Paso 2: Crear Entorno Virtual

```powershell
# Navegar a carpeta del proyecto
cd C:\path\to\911-fiesta-V7

# Crear entorno virtual
python -m venv .venv

# Activar entorno
.\.venv\Scripts\Activate.ps1
# En CMD: .venv\Scripts\activate.bat

# Verificar que esta activo
where python
# Debe mostrar: C:\...\911-fiesta-V7\.venv\Scripts\python.exe
```

## Paso 3: Instalar PyTorch con CUDA

**IMPORTANTE**: Instalar PyTorch ANTES de las otras dependencias.

### Para CUDA 12.1 (recomendado):

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Para CUDA 11.8 (GPUs mas antiguas):

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### Verificar instalacion CUDA:

```powershell
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"CPU\"}')"
```

Debe mostrar:
```
CUDA available: True
Device: NVIDIA GeForce RTX XXXX
```

## Paso 4: Instalar Dependencias SHOW

```powershell
pip install -r requirements/show.lock.txt
```

## Paso 5: Verificar Instalacion (Smoke Test)

```powershell
python scripts/smoke_show.py
```

Debe mostrar "OK" para cada componente:
```
[OK] numpy 1.26.4
[OK] PySide6 6.9.0
[OK] cv2 (OpenCV) 4.10.0
[OK] sounddevice 0.5.1
[OK] torch 2.x.x (CUDA: True)
[OK] ultralytics (YOLO)
[OK] pyqtgraph 0.13.7
...
SMOKE TEST PASSED
```

## Paso 6: Ejecutar Aplicacion

```powershell
python main.py
```

---

## Troubleshooting

### Error: "CUDA not available"

1. Verificar driver NVIDIA:
   ```powershell
   nvidia-smi
   ```
2. Reinstalar PyTorch con version CUDA correcta
3. Verificar que no haya conflicto CPU/GPU:
   ```powershell
   pip uninstall torch torchvision torchaudio
   pip cache purge
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   ```

### Error: "DLL load failed" con OpenCV

1. Instalar Visual C++ Redistributable:
   https://aka.ms/vs/17/release/vc_redist.x64.exe

### Error: "No Qt platform plugin"

1. Verificar QT_PLUGIN_PATH:
   ```powershell
   python -c "import PySide6; import os; print(os.path.dirname(PySide6.__file__))"
   ```
2. El bootstrap en main.py deberia configurar esto automaticamente

### Error: "libiomp5md.dll already initialized"

El main.py ya incluye fix para esto (KMP_DUPLICATE_LIB_OK=TRUE).
Si persiste:
```powershell
set KMP_DUPLICATE_LIB_OK=TRUE
python main.py
```

---

## Desinstalar Entorno

```powershell
# Desactivar entorno
deactivate

# Eliminar carpeta .venv
rmdir /s /q .venv
```

---

## Notas de Performance

- YOLO usa yolov8n.pt (nano) por defecto - descarga automatica ~6MB
- Primera inferencia demora mas (warmup)
- GPU memory: ~500MB para YOLOv8n
- Para GPUs con poca VRAM: reducir `max_roi_size` en config
