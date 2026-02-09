# 911 Fiesta V7 - Core911 Hardware Reference

## Machine Specs

| Component | Model | Notes |
|-----------|-------|-------|
| **GPU** | NVIDIA GeForce GTX 1080 Ti | 11 GB VRAM, CUDA 12.1 compatible |
| **Audio** | Maono PS22 USB | USB audio interface for live mic input |
| **OS** | Ubuntu 24.04.3 LTS | Server or desktop |

---

## GPU: NVIDIA GTX 1080 Ti

### Driver Installation

The NVIDIA driver is **not** installed automatically by `bootstrap_linux.sh`
because the correct driver version depends on the kernel and may require a reboot.

```bash
# Option 1: Auto-detect and install recommended driver
sudo ubuntu-drivers install
sudo reboot

# Option 2: Install a specific driver version
sudo apt install nvidia-driver-535
sudo reboot
```

### Verification

After reboot:

```bash
# Check driver
nvidia-smi

# Expected output (example):
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 535.183.01   Driver Version: 535.183.01   CUDA Version: 12.2     |
# | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
# | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M.  |
# |   0  NVIDIA GeForce ...  Off  | 00000000:01:00.0 Off |                  N/A |
# | 30%   40C    P8    15W / 250W |      0MiB / 11264MiB |      0%      Default |
# +-----------------------------------------------------------------------------+
```

### PyTorch CUDA Validation

```bash
source /opt/911fiesta/.venv/bin/activate
python3 -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'Device: {torch.cuda.get_device_name(0)}')
    print(f'CUDA version: {torch.version.cuda}')
    print(f'Memory: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB')
"
```

Expected output:
```
PyTorch: 2.5.1+cu121
CUDA available: True
Device: NVIDIA GeForce GTX 1080 Ti
CUDA version: 12.1
Memory: 11.2 GB
```

### What the healthcheck validates

| Check | Tool | Pass condition | Fail action |
|-------|------|----------------|-------------|
| NVIDIA driver present | `nvidia-smi` | Command exists and returns GPU info | Install driver: `sudo ubuntu-drivers install` |
| PyTorch CUDA | `python3 -c "import torch; ..."` | `torch.cuda.is_available() == True` | Check driver/torch CUDA version match |

### What happens if GPU check fails

- **Missing nvidia-smi**: WARN. The SHOW profile needs GPU for YOLO inference.
  Without GPU, YOLO runs on CPU (slower but functional).
- **torch.cuda not available**: WARN. Driver installed but torch was built
  for a different CUDA version. Reinstall torch with matching CUDA index.

---

## Audio: Maono PS22 USB

### How it works

The Maono PS22 is a USB audio interface that appears as an ALSA capture device.
The `sounddevice` Python library uses PortAudio to access it.

### Prerequisites

- `alsa-utils` package (installed by `bootstrap_linux.sh`)
- `fiesta` user in the `audio` group (set by `bootstrap_linux.sh`)
- `libportaudio2` and `portaudio19-dev` (installed by `bootstrap_linux.sh`)

### Verification

```bash
# List ALSA capture devices
arecord -l

# Expected output (example):
# **** List of CAPTURE Hardware Devices ****
# card 1: PS22 [Maono PS22], device 0: USB Audio [USB Audio]
#   Subdevices: 1/1
#   Subdevice #0: subdevice #0

# Check USB device is connected
lsusb | grep -i maono

# Check ALSA cards
cat /proc/asound/cards

# Test capture (record 3 seconds of audio)
arecord -d 3 -f cd /tmp/test_audio.wav
aplay /tmp/test_audio.wav
```

### Python sounddevice validation

```bash
source /opt/911fiesta/.venv/bin/activate
python3 -c "
import sounddevice as sd
print(f'sounddevice: {sd.__version__}')
devices = sd.query_devices()
print(f'Devices found: {len(devices)}')
for i, d in enumerate(devices):
    if d['max_input_channels'] > 0:
        print(f'  [{i}] {d[\"name\"]} (inputs: {d[\"max_input_channels\"]})')
"
```

### What the healthcheck validates

| Check | Tool | Pass condition | Fail action |
|-------|------|----------------|-------------|
| `arecord` available | `command -v arecord` | Exists | `sudo apt install alsa-utils` |
| Capture devices | `arecord -l` | At least one card found | Check USB, check `audio` group |
| Maono PS22 | `arecord -l \| grep maono` | Match found | Check USB cable, try different port |

### What happens if audio check fails

- **arecord not found**: WARN. Install `alsa-utils`.
- **No capture devices**: WARN. USB not connected or `fiesta` not in `audio` group.
- **Maono PS22 not found**: WARN. Other capture devices may work. The Maono
  check is informational — any ALSA capture device can be used.

### Troubleshooting

```bash
# No devices found
id fiesta                    # Check for 'audio' group
sudo usermod -aG audio fiesta  # Add to group (requires re-login/reboot)

# USB device not appearing
lsusb                       # Check if USB device is listed
dmesg | tail -20             # Check kernel messages for USB errors

# PortAudio errors in Python
python3 -c "import sounddevice; print(sounddevice.query_devices())"
# If empty: libportaudio2 may be missing
sudo apt install libportaudio2
```

---

## Network: Camera VLAN

The cameras (Axis IP cameras at 192.168.1.110) are on a separate network.
The core911 machine must have an interface on the camera subnet.

See `docs/LINUX_INSTALL.md` for netplan static IP configuration.

### Quick connectivity check

```bash
# Can we reach the camera?
ping -c 1 192.168.1.110

# Can ffprobe open the stream?
ffprobe -v error http://root:root@192.168.1.110/axis-cgi/mjpg/video.cgi?fps=10
```
