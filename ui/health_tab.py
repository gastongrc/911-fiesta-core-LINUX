"""
911 Fiesta — Health Monitor Tab (PySide6)

Displays real-time system health:
  Hardware: CPU, RAM, Disk, GPU (NVIDIA 1080 Ti)
  Process:  PID, CPU%, RSS, threads, FDs, uptime
  Network:  Avolites status, cameras, vision engine
  Audio:    ALSA devices, active input
  Calendar: current mode, remaining, override
  Global:   OK / WARNING / ERROR + last error

Non-blocking: heavy metrics (GPU, disk) run in background thread with 2s cache.
"""

import collections
import os
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QScrollArea, QSizePolicy, QPushButton,
)
from PySide6.QtCore import QTimer, Qt

# ---------------------------------------------------------------------------
# Colors (aligned to WEB design language)
# ---------------------------------------------------------------------------
_GREEN = "#00e676"
_CYAN = "#4dd0e1"
_YELLOW = "#ffd740"
_RED = "#ff5252"
_MUTED = "rgba(240,240,240,0.38)"
_TEXT = "#f0f0f0"
_TEXT2 = "rgba(240,240,240,0.65)"
_BG_CARD = "rgba(255,255,255,0.05)"
_BG_PANEL = "rgba(255,255,255,0.04)"
_BORDER = "rgba(255,255,255,0.10)"

# Status colors
_OK_COLOR = _GREEN
_WARN_COLOR = _YELLOW
_ERR_COLOR = _RED
_OFF_COLOR = _MUTED


def _status_dot(color: str) -> str:
    """Inline dot character with color."""
    return f'<span style="color:{color}; font-size:16px;">&#9679;</span>'


def _card_style() -> str:
    return (
        f"QFrame{{ background:{_BG_CARD}; border:1px solid {_BORDER}; "
        f"border-radius:14px; }}"
    )


def _section_title_style() -> str:
    return f"font-weight:700; color:{_GREEN}; font-size:13px; letter-spacing:1px; font-family:'Space Grotesk','Inter',sans-serif;"


def _metric_label_style() -> str:
    return f"color:{_TEXT2}; font-size:13px;"


def _metric_value_style(color: str = _TEXT) -> str:
    return f"color:{color}; font-weight:700; font-size:13px; font-family:'JetBrains Mono','Consolas',monospace;"


# ---------------------------------------------------------------------------
# Heavy metrics worker (background thread)
# ---------------------------------------------------------------------------
class _HeavyMetricsWorker:
    """
    Collects GPU / disk / audio-devices in a background thread.
    Cached for _ttl seconds. Thread-safe.
    """

    def __init__(self, ttl: float = 2.0):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {}
        self._cache_ts: float = 0

    def get(self) -> Dict[str, Any]:
        now = time.time()
        if now - self._cache_ts < self._ttl and self._cache:
            return self._cache
        # Refresh in caller's context (will be called from QTimer, not UI thread blocking)
        return self._refresh()

    def _refresh(self) -> Dict[str, Any]:
        with self._lock:
            # Double-check
            now = time.time()
            if now - self._cache_ts < self._ttl and self._cache:
                return self._cache
            result = {
                "gpu": self._query_gpu(),
                "disk": self._query_disk(),
                "audio_devices": self._query_audio(),
            }
            self._cache = result
            self._cache_ts = time.time()
            return result

    @staticmethod
    def _run(cmd: List[str], timeout: float = 3.0) -> Optional[str]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip() if r.returncode == 0 else None
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None

    def _query_gpu(self) -> Optional[dict]:
        out = self._run([
            "nvidia-smi",
            "--query-gpu=name,driver_version,temperature.gpu,utilization.gpu,"
            "utilization.memory,memory.used,memory.total,power.draw,power.limit,pstate",
            "--format=csv,noheader,nounits",
        ])
        if out is None:
            return None
        parts = [p.strip() for p in out.split(",")]
        if len(parts) < 10:
            return None

        def _fi(s):
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return None

        def _ff(s):
            try:
                return round(float(s), 1)
            except (ValueError, TypeError):
                return None

        return {
            "name": parts[0],
            "driver": parts[1],
            "temp_c": _fi(parts[2]),
            "gpu_util_pct": _fi(parts[3]),
            "mem_util_pct": _fi(parts[4]),
            "mem_used_mb": _fi(parts[5]),
            "mem_total_mb": _fi(parts[6]),
            "power_draw_w": _ff(parts[7]),
            "power_limit_w": _ff(parts[8]),
            "pstate": parts[9],
        }

    def _query_disk(self) -> dict:
        check_path = "/opt/911fiesta" if os.path.exists("/opt/911fiesta") else os.getcwd()
        try:
            import shutil
            usage = shutil.disk_usage(check_path)
            return {
                "path": check_path,
                "total_gb": round(usage.total / (1024 ** 3), 1),
                "used_gb": round(usage.used / (1024 ** 3), 1),
                "percent": round(100 * usage.used / usage.total, 1) if usage.total > 0 else None,
            }
        except Exception:
            return {"path": check_path, "total_gb": None, "used_gb": None, "percent": None}

    def _query_audio(self) -> dict:
        """
        Returns structured ALSA info:
          {
            "cards": [{"index": 0, "id": "NVidia", "name": "...driver..."}, ...],
            "capture": [{"card": 1, "device": 0, "name": "...", "busy": False}, ...],
            "source": "arecord+proc" | "proc_only" | "dev_snd" | "none"
          }
        """
        result: Dict[str, Any] = {"cards": [], "capture": [], "source": "none"}

        # --- /proc/asound/cards (always available if ALSA loaded) ---
        cards = self._parse_proc_asound_cards()
        if cards:
            result["cards"] = cards
            result["source"] = "proc_only"

        # --- arecord -l (capture devices with subdevice info) ---
        arecord_out = self._run(["arecord", "-l"])
        if arecord_out:
            result["capture"] = self._parse_arecord(arecord_out)
            result["source"] = "arecord+proc" if cards else "arecord"
        elif not cards:
            # Last resort: list /dev/snd entries
            result["cards"] = self._fallback_dev_snd()
            if result["cards"]:
                result["source"] = "dev_snd"

        return result

    @staticmethod
    def _parse_proc_asound_cards() -> list:
        """Parse /proc/asound/cards → list of {index, id, name}."""
        try:
            with open("/proc/asound/cards", "r") as f:
                raw = f.read()
        except (FileNotFoundError, PermissionError, OSError):
            return []
        cards = []
        lines = raw.strip().split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Format: " 0 [NVidia         ]: HDA-Intel - HDA NVidia"
            if line and line[0].isdigit():
                parts = line.split("[", 1)
                try:
                    idx = int(parts[0].strip())
                except (ValueError, IndexError):
                    i += 1
                    continue
                card_id = ""
                name_tail = ""
                if len(parts) > 1:
                    bracket_end = parts[1].find("]")
                    if bracket_end >= 0:
                        card_id = parts[1][:bracket_end].strip()
                        name_tail = parts[1][bracket_end + 1:].strip().lstrip(":").strip()
                        # Grab "- long name" part
                        dash_pos = name_tail.find(" - ")
                        if dash_pos >= 0:
                            name_tail = name_tail[dash_pos + 3:].strip()
                # Second line is the long description
                long_name = ""
                if i + 1 < len(lines):
                    long_name = lines[i + 1].strip()
                    i += 1
                cards.append({"index": idx, "id": card_id, "name": name_tail or long_name})
            i += 1
        return cards

    @staticmethod
    def _parse_arecord(output: str) -> list:
        """
        Parse `arecord -l` output into structured capture devices.
        Example line:
          card 1: USBAudio [USB Audio], device 0: USB Audio [USB Audio]
            Subdevices: 0/1      ← 0 available of 1 total → BUSY
        """
        import re
        captures = []
        lines = output.strip().split("\n")
        i = 0
        # Pattern: card N: ID [Name], device M: ...
        card_re = re.compile(
            r"card\s+(\d+):\s+\S+\s+\[([^\]]*)\],\s*device\s+(\d+):\s*(.*)"
        )
        while i < len(lines):
            m = card_re.search(lines[i])
            if m:
                card_idx = int(m.group(1))
                card_name = m.group(2).strip()
                dev_idx = int(m.group(3))
                dev_desc = m.group(4).strip()
                busy = False
                # Check next line for Subdevices: available/total
                if i + 1 < len(lines) and "Subdevices:" in lines[i + 1]:
                    sub_m = re.search(r"Subdevices:\s*(\d+)/(\d+)", lines[i + 1])
                    if sub_m:
                        available = int(sub_m.group(1))
                        busy = (available == 0)
                    i += 1
                captures.append({
                    "card": card_idx,
                    "device": dev_idx,
                    "name": card_name,
                    "desc": dev_desc,
                    "busy": busy,
                })
            i += 1
        return captures

    @staticmethod
    def _fallback_dev_snd() -> list:
        """List /dev/snd/controlC* as last resort."""
        try:
            entries = os.listdir("/dev/snd")
        except (FileNotFoundError, PermissionError, OSError):
            return []
        cards = []
        for e in sorted(entries):
            if e.startswith("controlC"):
                try:
                    idx = int(e.replace("controlC", ""))
                    cards.append({"index": idx, "id": e, "name": f"/dev/snd/{e}"})
                except ValueError:
                    pass
        return cards


# Singleton worker
_heavy_worker = _HeavyMetricsWorker(ttl=2.0)


# ---------------------------------------------------------------------------
# HealthMonitorWidget
# ---------------------------------------------------------------------------
class HealthMonitorWidget(QWidget):
    """
    Full-featured Health tab for the 911 Fiesta CORE UI.
    Replaces the minimal CPU/RAM/Avolites widget.
    """

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._last_errors: collections.deque = collections.deque(maxlen=10)
        self._global_status = "OK"
        self._global_reason = ""
        self._setup_ui()

    # ======================================================================
    # UI SETUP
    # ======================================================================
    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent; border:none;}")
        outer.addWidget(scroll)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)
        scroll.setWidget(container)

        # --- GLOBAL STATUS BANNER ---
        self.frm_global = QFrame()
        self.frm_global.setStyleSheet(_card_style())
        gl = QHBoxLayout(self.frm_global)
        gl.setContentsMargins(14, 10, 14, 10)
        self.lbl_global_dot = QLabel()
        self.lbl_global_dot.setTextFormat(Qt.RichText)
        self.lbl_global_dot.setText(_status_dot(_OK_COLOR))
        gl.addWidget(self.lbl_global_dot)
        self.lbl_global_text = QLabel("SYSTEM OK")
        self.lbl_global_text.setStyleSheet(f"font-weight:800; font-size:14px; color:{_GREEN};")
        gl.addWidget(self.lbl_global_text)
        gl.addStretch()
        self.lbl_global_reason = QLabel("")
        self.lbl_global_reason.setStyleSheet(f"color:{_TEXT2}; font-size:13px;")
        gl.addWidget(self.lbl_global_reason)
        layout.addWidget(self.frm_global)

        # --- HARDWARE ---
        hw_frame = self._make_section("HARDWARE")
        hw_grid = QGridLayout()
        hw_grid.setSpacing(6)
        hw_grid.setContentsMargins(0, 4, 0, 0)

        r = 0
        # CPU
        self.lbl_cpu = self._add_row(hw_grid, r, "CPU", "---"); r += 1
        self.lbl_cpu_load = self._add_row(hw_grid, r, "Load Avg", "---"); r += 1
        # RAM
        self.lbl_ram = self._add_row(hw_grid, r, "RAM", "---"); r += 1
        self.lbl_ram_detail = self._add_row(hw_grid, r, "RAM Used", "---"); r += 1
        # Disk
        self.lbl_disk = self._add_row(hw_grid, r, "Disk", "---"); r += 1
        # GPU
        self.lbl_gpu_name = self._add_row(hw_grid, r, "GPU", "---"); r += 1
        self.lbl_gpu_temp = self._add_row(hw_grid, r, "GPU Temp", "---"); r += 1
        self.lbl_gpu_util = self._add_row(hw_grid, r, "GPU Util", "---"); r += 1
        self.lbl_gpu_mem = self._add_row(hw_grid, r, "GPU VRAM", "---"); r += 1
        self.lbl_gpu_power = self._add_row(hw_grid, r, "GPU Power", "---"); r += 1
        self.lbl_gpu_pstate = self._add_row(hw_grid, r, "GPU PState", "---"); r += 1

        hw_frame.layout().addLayout(hw_grid)
        layout.addWidget(hw_frame)

        # --- PROCESS ---
        proc_frame = self._make_section("PROCESO 911")
        proc_grid = QGridLayout()
        proc_grid.setSpacing(6)
        proc_grid.setContentsMargins(0, 4, 0, 0)
        r = 0
        self.lbl_pid = self._add_row(proc_grid, r, "PID", "---"); r += 1
        self.lbl_proc_cpu = self._add_row(proc_grid, r, "CPU %", "---"); r += 1
        self.lbl_proc_rss = self._add_row(proc_grid, r, "RSS", "---"); r += 1
        self.lbl_proc_threads = self._add_row(proc_grid, r, "Threads", "---"); r += 1
        self.lbl_proc_fds = self._add_row(proc_grid, r, "Open FDs", "---"); r += 1
        self.lbl_proc_uptime = self._add_row(proc_grid, r, "Uptime", "---"); r += 1
        self.lbl_loop_lat = self._add_row(proc_grid, r, "Loop Latency", "---"); r += 1
        proc_frame.layout().addLayout(proc_grid)
        layout.addWidget(proc_frame)

        # --- RED / CONECTIVIDAD ---
        net_frame = self._make_section("RED / CONECTIVIDAD")
        net_grid = QGridLayout()
        net_grid.setSpacing(6)
        net_grid.setContentsMargins(0, 4, 0, 0)
        r = 0
        self.lbl_net_ip = self._add_row(net_grid, r, "IP Local", "---"); r += 1
        # Avolites
        self.lbl_avo_status = self._add_row(net_grid, r, "Avolites", "---"); r += 1
        self.lbl_avo_dest = self._add_row(net_grid, r, "Destino", "---"); r += 1
        self.lbl_avo_transport = self._add_row(net_grid, r, "Transporte", "---"); r += 1
        self.lbl_avo_latency = self._add_row(net_grid, r, "Latencia", "---"); r += 1
        self.lbl_avo_queue = self._add_row(net_grid, r, "Cola", "---"); r += 1
        self.lbl_avo_last_send = self._add_row(net_grid, r, "Last Send", "---"); r += 1
        self.lbl_avo_last_error = self._add_row(net_grid, r, "Last Error", "---"); r += 1
        # Cameras
        self.lbl_cam_haze = self._add_row(net_grid, r, "Cam HAZE", "---"); r += 1
        self.lbl_cam_dj = self._add_row(net_grid, r, "Cam DJ", "---"); r += 1
        self.lbl_cam_artist = self._add_row(net_grid, r, "Cam ARTIST", "---"); r += 1
        net_frame.layout().addLayout(net_grid)
        layout.addWidget(net_frame)

        # --- AUDIO (ALSA) ---
        audio_frame = self._make_section("AUDIO (ALSA)")
        audio_vbox = audio_frame.layout()

        audio_grid = QGridLayout()
        audio_grid.setSpacing(6)
        audio_grid.setContentsMargins(0, 4, 0, 0)
        r = 0
        self.lbl_audio_source = self._add_row(audio_grid, r, "Detection", "---"); r += 1
        self.lbl_audio_active = self._add_row(audio_grid, r, "Active Input", "---"); r += 1
        self.lbl_audio_state = self._add_row(audio_grid, r, "State", "---"); r += 1
        audio_vbox.addLayout(audio_grid)

        # Cards list (dynamic, populated at update)
        self.lbl_audio_cards_header = QLabel("Cards:")
        self.lbl_audio_cards_header.setStyleSheet(_metric_label_style())
        audio_vbox.addWidget(self.lbl_audio_cards_header)
        self.lbl_audio_cards = QLabel("---")
        self.lbl_audio_cards.setWordWrap(True)
        self.lbl_audio_cards.setTextFormat(Qt.RichText)
        self.lbl_audio_cards.setStyleSheet(
            f"color:{_TEXT}; font-size:11px; font-family:'JetBrains Mono','Consolas',monospace; "
            f"padding:6px 8px; background:rgba(0,0,0,0.25); border-radius:10px;"
        )
        audio_vbox.addWidget(self.lbl_audio_cards)

        # Capture devices list (dynamic)
        self.lbl_audio_capture_header = QLabel("Capture devices:")
        self.lbl_audio_capture_header.setStyleSheet(_metric_label_style())
        audio_vbox.addWidget(self.lbl_audio_capture_header)
        self.lbl_audio_capture = QLabel("---")
        self.lbl_audio_capture.setWordWrap(True)
        self.lbl_audio_capture.setTextFormat(Qt.RichText)
        self.lbl_audio_capture.setStyleSheet(
            f"color:{_TEXT}; font-size:11px; font-family:'JetBrains Mono','Consolas',monospace; "
            f"padding:6px 8px; background:rgba(0,0,0,0.25); border-radius:10px;"
        )
        audio_vbox.addWidget(self.lbl_audio_capture)

        layout.addWidget(audio_frame)

        # --- CALENDAR ---
        cal_frame = self._make_section("CALENDAR RUNTIME")
        cal_grid = QGridLayout()
        cal_grid.setSpacing(6)
        cal_grid.setContentsMargins(0, 4, 0, 0)
        r = 0
        self.lbl_cal_mode = self._add_row(cal_grid, r, "Current Mode", "---"); r += 1
        self.lbl_cal_next = self._add_row(cal_grid, r, "Next Mode", "---"); r += 1
        self.lbl_cal_remaining = self._add_row(cal_grid, r, "Remaining", "---"); r += 1
        self.lbl_cal_override = self._add_row(cal_grid, r, "Override", "---"); r += 1
        self.lbl_cal_auto = self._add_row(cal_grid, r, "Auto/Manual", "---"); r += 1
        self.lbl_cal_source = self._add_row(cal_grid, r, "Source", "---"); r += 1
        cal_frame.layout().addLayout(cal_grid)
        layout.addWidget(cal_frame)

        # --- LAST ERRORS ---
        err_frame = self._make_section("LAST ERRORS")
        self.lbl_last_error = QLabel("---")
        self.lbl_last_error.setWordWrap(True)
        self.lbl_last_error.setStyleSheet(f"color:{_TEXT2}; font-size:11px; font-family:'JetBrains Mono','Consolas',monospace;")
        err_frame.layout().addWidget(self.lbl_last_error)
        layout.addWidget(err_frame)

        # Refresh button
        btn_row = QHBoxLayout()
        btn = QPushButton("Refresh Now")
        btn.setStyleSheet(
            f"QPushButton{{background:rgba(255,255,255,0.06); border:1px solid {_BORDER}; "
            f"border-radius:10px; padding:8px 16px; color:{_GREEN}; font-weight:600;}} "
            f"QPushButton:hover{{background:rgba(255,255,255,0.10); border-color:rgba(0,230,118,0.30);}}"
        )
        btn.clicked.connect(self.refresh_metrics)
        btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

    # ======================================================================
    # HELPERS
    # ======================================================================
    def _make_section(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(_card_style())
        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(14, 10, 14, 12)
        vbox.setSpacing(4)
        lbl = QLabel(title)
        lbl.setStyleSheet(_section_title_style())
        vbox.addWidget(lbl)
        return frame

    @staticmethod
    def _add_row(grid: QGridLayout, row: int, label: str, default: str) -> QLabel:
        lbl_name = QLabel(label + ":")
        lbl_name.setStyleSheet(_metric_label_style())
        lbl_val = QLabel(default)
        lbl_val.setStyleSheet(_metric_value_style())
        lbl_val.setTextFormat(Qt.RichText)
        grid.addWidget(lbl_name, row, 0)
        grid.addWidget(lbl_val, row, 1)
        return lbl_val

    def _set_value(self, lbl: QLabel, text: str, color: str = _TEXT):
        lbl.setText(text)
        lbl.setStyleSheet(_metric_value_style(color))

    def _fmt_uptime(self, s) -> str:
        if s is None or s < 0:
            return "---"
        s = int(s)
        if s >= 3600:
            return f"{s // 3600}h {(s % 3600) // 60}m"
        if s >= 60:
            return f"{s // 60}m {s % 60}s"
        return f"{s}s"

    @staticmethod
    def _resolve_sd_device_name(device_index) -> str:
        """Try to resolve a sounddevice device index to a human name."""
        try:
            import sounddevice as sd
            info = sd.query_devices(device_index)
            if isinstance(info, dict):
                return f"[{device_index}] {info.get('name', '?')}"
        except Exception:
            pass
        return f"device #{device_index}"

    def _cam_text(self, handler) -> tuple:
        """Returns (text, color) for a camera handler."""
        if handler is None:
            return "N/A", _MUTED
        online = getattr(handler, "is_running", False)
        fps = getattr(handler, "current_fps", 0) or 0
        ip = getattr(handler, "camera_ip", "") or ""
        if online:
            return f"{_status_dot(_OK_COLOR)} {fps:.0f} fps  {ip}", _GREEN
        return f"{_status_dot(_ERR_COLOR)} offline  {ip}", _RED

    # ======================================================================
    # LOG ERROR (callable from main_window)
    # ======================================================================
    def record_error(self, source: str, message: str):
        ts = time.strftime("%H:%M:%S")
        self._last_errors.append(f"[{ts}] {source}: {message}")

    # ======================================================================
    # REFRESH (called by timer or manually)
    # ======================================================================
    def refresh_metrics(self):
        try:
            self.main_window._update_health_panel()
        except Exception:
            pass

    def update_all(
        self,
        cpu_pct=None,
        cpu_load=None,
        ram_pct=None,
        ram_used_mb=None,
        ram_total_mb=None,
        loop_lat_ms=None,
        avolites_status=None,
        vision_manager=None,
        audio_engine=None,
        audio_monitor=None,
        calendar_manager=None,
    ):
        """
        Master update method. Called from Main._update_health_panel().
        Heavy metrics (GPU/disk/audio devices) fetched from cached worker.
        """
        warnings = []

        # ---- HEAVY (cached 2s) ----
        heavy = _heavy_worker.get()
        gpu = heavy.get("gpu")
        disk = heavy.get("disk")

        # ---- HARDWARE: CPU ----
        if cpu_pct is not None:
            color = _GREEN if cpu_pct < 70 else (_YELLOW if cpu_pct < 85 else _RED)
            self._set_value(self.lbl_cpu, f"{cpu_pct:.0f} %", color)
            if cpu_pct > 85:
                warnings.append("CPU > 85%")
        else:
            self._set_value(self.lbl_cpu, "---", _MUTED)

        if cpu_load is not None:
            txt = ", ".join(f"{v:.2f}" for v in cpu_load[:3])
            self._set_value(self.lbl_cpu_load, txt)
        else:
            self._set_value(self.lbl_cpu_load, "---", _MUTED)

        # ---- HARDWARE: RAM ----
        if ram_pct is not None:
            color = _GREEN if ram_pct < 70 else (_YELLOW if ram_pct < 85 else _RED)
            self._set_value(self.lbl_ram, f"{ram_pct:.0f} %", color)
            if ram_pct > 85:
                warnings.append("RAM > 85%")
        else:
            self._set_value(self.lbl_ram, "---", _MUTED)

        if ram_used_mb is not None and ram_total_mb is not None:
            self._set_value(self.lbl_ram_detail, f"{ram_used_mb} / {ram_total_mb} MB")
        else:
            self._set_value(self.lbl_ram_detail, "---", _MUTED)

        # ---- HARDWARE: Disk ----
        if disk and disk.get("percent") is not None:
            pct = disk["percent"]
            color = _GREEN if pct < 80 else (_YELLOW if pct < 90 else _RED)
            self._set_value(self.lbl_disk, f"{pct:.0f} %  ({disk.get('used_gb', '?')}/{disk.get('total_gb', '?')} GB)", color)
            if pct > 90:
                warnings.append("Disk > 90%")
        else:
            self._set_value(self.lbl_disk, "---", _MUTED)

        # ---- HARDWARE: GPU ----
        if gpu:
            self._set_value(self.lbl_gpu_name, gpu.get("name", "---"))

            temp = gpu.get("temp_c")
            if temp is not None:
                color = _GREEN if temp < 70 else (_YELLOW if temp < 80 else _RED)
                self._set_value(self.lbl_gpu_temp, f"{temp} C", color)
                if temp > 80:
                    warnings.append(f"GPU {temp}C")
            else:
                self._set_value(self.lbl_gpu_temp, "---", _MUTED)

            util = gpu.get("gpu_util_pct")
            if util is not None:
                color = _GREEN if util < 80 else (_YELLOW if util < 95 else _RED)
                self._set_value(self.lbl_gpu_util, f"{util} %", color)
                if util > 95:
                    warnings.append("GPU > 95%")
            else:
                self._set_value(self.lbl_gpu_util, "---", _MUTED)

            mem_used = gpu.get("mem_used_mb")
            mem_total = gpu.get("mem_total_mb")
            if mem_used is not None and mem_total is not None:
                self._set_value(self.lbl_gpu_mem, f"{mem_used} / {mem_total} MB")
            else:
                self._set_value(self.lbl_gpu_mem, "---", _MUTED)

            pw = gpu.get("power_draw_w")
            pl = gpu.get("power_limit_w")
            if pw is not None:
                txt = f"{pw} W" + (f" / {pl} W" if pl else "")
                self._set_value(self.lbl_gpu_power, txt)
            else:
                self._set_value(self.lbl_gpu_power, "---", _MUTED)

            self._set_value(self.lbl_gpu_pstate, gpu.get("pstate", "---"))
        else:
            for lbl in (self.lbl_gpu_name, self.lbl_gpu_temp, self.lbl_gpu_util,
                        self.lbl_gpu_mem, self.lbl_gpu_power, self.lbl_gpu_pstate):
                self._set_value(lbl, "N/A (nvidia-smi)", _MUTED)

        # ---- PROCESS ----
        pid = os.getpid()
        self._set_value(self.lbl_pid, str(pid))

        try:
            import psutil
            proc = psutil.Process(pid)
            self._set_value(self.lbl_proc_cpu, f"{proc.cpu_percent(interval=None):.1f} %")
            rss = proc.memory_info().rss / (1024 * 1024)
            self._set_value(self.lbl_proc_rss, f"{rss:.0f} MB", _GREEN if rss < 1024 else (_YELLOW if rss < 2048 else _RED))
            self._set_value(self.lbl_proc_threads, str(proc.num_threads()))
            if hasattr(proc, "num_fds"):
                self._set_value(self.lbl_proc_fds, str(proc.num_fds()))
            else:
                self._set_value(self.lbl_proc_fds, "---", _MUTED)
            uptime_s = time.time() - proc.create_time()
            self._set_value(self.lbl_proc_uptime, self._fmt_uptime(uptime_s))
        except ImportError:
            for lbl in (self.lbl_proc_cpu, self.lbl_proc_rss, self.lbl_proc_threads,
                        self.lbl_proc_fds, self.lbl_proc_uptime):
                self._set_value(lbl, "---", _MUTED)
        except Exception:
            pass

        if loop_lat_ms is not None:
            color = _GREEN if loop_lat_ms < 10 else (_YELLOW if loop_lat_ms < 50 else _RED)
            self._set_value(self.lbl_loop_lat, f"{loop_lat_ms:.0f} ms", color)
            if loop_lat_ms > 50:
                warnings.append(f"Loop {loop_lat_ms:.0f}ms")
        else:
            self._set_value(self.lbl_loop_lat, "---", _MUTED)

        # ---- NETWORK: local IP ----
        ip_txt = "---"
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(("8.8.8.8", 80))
            ip_txt = s.getsockname()[0]
            s.close()
        except Exception:
            pass
        self._set_value(self.lbl_net_ip, ip_txt)

        # ---- NETWORK: Avolites ----
        if avolites_status:
            connected = avolites_status.get("connected", False) or avolites_status.get("is_connected", False)
            if connected:
                self._set_value(self.lbl_avo_status, f"{_status_dot(_OK_COLOR)} Connected", _GREEN)
            else:
                self._set_value(self.lbl_avo_status, f"{_status_dot(_ERR_COLOR)} Offline", _RED)
                warnings.append("Avolites offline")

            c_ip = avolites_status.get("console_ip", "")
            c_port = avolites_status.get("console_port", "")
            self._set_value(self.lbl_avo_dest, f"{c_ip}:{c_port}" if c_ip else "---")
            self._set_value(self.lbl_avo_transport, avolites_status.get("transport", "---") or "---")

            lat = avolites_status.get("latency_ms") or avolites_status.get("last_send_ms")
            if isinstance(lat, (int, float)):
                color = _GREEN if lat < 50 else (_YELLOW if lat < 200 else _RED)
                self._set_value(self.lbl_avo_latency, f"{lat:.1f} ms", color)
            else:
                self._set_value(self.lbl_avo_latency, "---", _MUTED)

            ql = avolites_status.get("queue_len")
            self._set_value(self.lbl_avo_queue, str(ql) if isinstance(ql, int) else "---")

            ls = avolites_status.get("last_send_ms")
            self._set_value(self.lbl_avo_last_send, f"{ls:.1f} ms" if isinstance(ls, (int, float)) else "---")

            err = avolites_status.get("last_error_short") or avolites_status.get("last_error")
            self._set_value(self.lbl_avo_last_error, str(err)[:80] if err else "---", _RED if err else _MUTED)
        else:
            for lbl in (self.lbl_avo_status, self.lbl_avo_dest, self.lbl_avo_transport,
                        self.lbl_avo_latency, self.lbl_avo_queue, self.lbl_avo_last_send,
                        self.lbl_avo_last_error):
                self._set_value(lbl, "---", _MUTED)

        # ---- NETWORK: Cameras ----
        cam_labels = {"haze": self.lbl_cam_haze, "dj": self.lbl_cam_dj, "artist": self.lbl_cam_artist}
        if vision_manager:
            for cam_type, lbl in cam_labels.items():
                handler = getattr(vision_manager, f"{cam_type}_handler", None)
                if handler is None:
                    handler = getattr(vision_manager, f"cam_{cam_type}", None)
                txt, color = self._cam_text(handler)
                self._set_value(lbl, txt, color)
                if handler and not getattr(handler, "is_running", False):
                    warnings.append(f"Cam {cam_type} offline")
        else:
            for lbl in cam_labels.values():
                self._set_value(lbl, "---", _MUTED)

        # ---- AUDIO (ALSA) ----
        audio_info = heavy.get("audio_devices") or {}
        alsa_cards = audio_info.get("cards", [])
        alsa_capture = audio_info.get("capture", [])
        alsa_source = audio_info.get("source", "none")

        # Detection source
        self._set_value(self.lbl_audio_source, alsa_source,
                        _GREEN if alsa_source not in ("none", "dev_snd") else _YELLOW)

        # Cards list
        if alsa_cards:
            lines = []
            for c in alsa_cards:
                lines.append(f"  [{c.get('index', '?')}] {c.get('id', '')} — {c.get('name', '')}")
            self.lbl_audio_cards.setText("<br>".join(lines))
        else:
            self.lbl_audio_cards.setText('<span style="color:%s;">No ALSA cards detected</span>' % _YELLOW)
            if alsa_source == "none":
                warnings.append("No ALSA cards")

        # Capture devices list
        if alsa_capture:
            lines = []
            for cap in alsa_capture:
                busy_tag = (' <span style="color:%s;">[BUSY]</span>' % _YELLOW) if cap.get("busy") else ""
                idle_tag = (' <span style="color:%s;">[idle]</span>' % _GREEN) if not cap.get("busy") else ""
                lines.append(
                    f'  card {cap.get("card", "?")}, dev {cap.get("device", "?")}: '
                    f'{cap.get("name", "")} {cap.get("desc", "")}{busy_tag}{idle_tag}'
                )
            self.lbl_audio_capture.setText("<br>".join(lines))
        else:
            self.lbl_audio_capture.setText('<span style="color:%s;">No capture devices (arecord -l)</span>' % _MUTED)

        # Active input from engine
        if audio_engine:
            running = getattr(audio_engine, "running", False)
            dev_idx = getattr(audio_engine, "device_index", None)
            dev_name = getattr(audio_engine, "device_name", None)
            if dev_name:
                active_txt = dev_name
            elif dev_idx is not None:
                # Resolve device_index to a name via sounddevice if possible
                active_txt = self._resolve_sd_device_name(dev_idx)
            else:
                active_txt = "UNKNOWN (engine no reporta)"
            self._set_value(self.lbl_audio_active, active_txt)

            if running:
                state_txt = "Running"
                state_color = _GREEN
                if audio_monitor:
                    alerts = getattr(audio_monitor, "alerts", None)
                    if alerts is None:
                        alerts = getattr(audio_monitor, "active_alerts", None)
                    if isinstance(alerts, dict):
                        if alerts.get("clipping"):
                            state_txt = "CLIPPING"
                            state_color = _RED
                            warnings.append("Audio clipping")
                        elif alerts.get("stream_lost"):
                            state_txt = "STREAM LOST"
                            state_color = _RED
                            warnings.append("Audio stream lost")
                        elif alerts.get("no_audio"):
                            state_txt = "SILENCE"
                            state_color = _YELLOW
                    elif isinstance(alerts, set):
                        if "clipping" in alerts:
                            state_txt = "CLIPPING"
                            state_color = _RED
                            warnings.append("Audio clipping")
                        elif "stream_lost" in alerts:
                            state_txt = "STREAM LOST"
                            state_color = _RED
                            warnings.append("Audio stream lost")
                        elif "no_audio" in alerts:
                            state_txt = "SILENCE"
                            state_color = _YELLOW
                self._set_value(self.lbl_audio_state, f"{_status_dot(state_color)} {state_txt}", state_color)
            else:
                self._set_value(self.lbl_audio_state, f"{_status_dot(_ERR_COLOR)} Stopped", _RED)
                warnings.append("Audio stopped")
        else:
            self._set_value(self.lbl_audio_active, "UNKNOWN (engine no reporta)", _MUTED)
            self._set_value(self.lbl_audio_state, "---", _MUTED)

        # ---- CALENDAR ----
        if calendar_manager:
            try:
                cal_state = calendar_manager.get_state()
                self._set_value(self.lbl_cal_mode, cal_state.get("current_mode", "---") or "---")
                self._set_value(self.lbl_cal_next, cal_state.get("next_mode", "---") or "---")

                remaining = cal_state.get("time_remaining_s")
                if remaining is not None and remaining >= 0:
                    self._set_value(self.lbl_cal_remaining, self._fmt_uptime(remaining))
                else:
                    self._set_value(self.lbl_cal_remaining, "---", _MUTED)

                override = cal_state.get("is_override", False)
                self._set_value(self.lbl_cal_override,
                                f"{_status_dot(_YELLOW)} Active" if override else "No",
                                _YELLOW if override else _TEXT)

                auto = cal_state.get("auto_mode_enabled", True)
                self._set_value(self.lbl_cal_auto, "AUTO" if auto else "MANUAL",
                                _GREEN if auto else _YELLOW)

                source = cal_state.get("source", "---")
                self._set_value(self.lbl_cal_source, str(source) if source else "---")
            except Exception:
                for lbl in (self.lbl_cal_mode, self.lbl_cal_next, self.lbl_cal_remaining,
                            self.lbl_cal_override, self.lbl_cal_auto, self.lbl_cal_source):
                    self._set_value(lbl, "---", _MUTED)
        else:
            for lbl in (self.lbl_cal_mode, self.lbl_cal_next, self.lbl_cal_remaining,
                        self.lbl_cal_override, self.lbl_cal_auto, self.lbl_cal_source):
                self._set_value(lbl, "---", _MUTED)

        # ---- GLOBAL STATUS ----
        if warnings:
            # Check for ERROR-level items
            err_keywords = ["offline", "stopped", "stream lost"]
            has_error = any(any(ek in w.lower() for ek in err_keywords) for w in warnings)
            if has_error:
                self._global_status = "ERROR"
                color = _RED
            else:
                self._global_status = "WARNING"
                color = _YELLOW
            self._global_reason = " | ".join(warnings[:3])
        else:
            self._global_status = "OK"
            color = _GREEN
            self._global_reason = ""

        self.lbl_global_dot.setText(_status_dot(color))
        self.lbl_global_text.setText(f"SYSTEM {self._global_status}")
        self.lbl_global_text.setStyleSheet(f"font-weight:800; font-size:14px; color:{color};")
        self.lbl_global_reason.setText(self._global_reason)

        # ---- LAST ERRORS ----
        if self._last_errors:
            self.lbl_last_error.setText("\n".join(list(self._last_errors)[-5:]))
        else:
            self.lbl_last_error.setText("No errors")
