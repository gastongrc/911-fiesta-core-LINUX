"""
VisionConfigWidget - Widget de configuración IP para Vision System PRO
Panel de configuración de cámaras IP MJPEG (Axis M1011)
Reemplaza los combos USB por campos Host/Path/Credenciales
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QGroupBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QGridLayout, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
import time
import threading


class CameraConfigPanel(QWidget):
    """Panel de configuración para una cámara IP individual."""

    def __init__(self, camera_name: str, icon: str, parent=None):
        super().__init__(parent)
        self.camera_name = camera_name
        self.icon = icon
        self._build_ui()

    def _build_ui(self):
        """Construye la UI del panel de cámara."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Header con checkbox enable
        header = QHBoxLayout()
        self.chk_enabled = QCheckBox(f"{self.icon} {self.camera_name.upper()}")
        self.chk_enabled.setStyleSheet("font-weight:700; color:#ddd;")
        header.addWidget(self.chk_enabled)

        # Status LED
        self.status_label = QLabel("No configurada")
        self.status_label.setStyleSheet("color:#888; font-size:10px;")
        header.addStretch()
        header.addWidget(self.status_label)

        layout.addLayout(header)

        # Grid de campos
        grid = QGridLayout()
        grid.setSpacing(4)

        # Style común para inputs
        input_style = "QLineEdit{background:#333; color:#ccc; border:1px solid #555; padding:4px; border-radius:3px;}"
        spin_style = "QSpinBox,QDoubleSpinBox{background:#333; color:#ccc; border:1px solid #555; padding:2px; border-radius:3px;}"

        # Host/IP
        grid.addWidget(QLabel("Host:"), 0, 0)
        self.txt_host = QLineEdit()
        self.txt_host.setPlaceholderText("192.168.0.100")
        self.txt_host.setStyleSheet(input_style)
        grid.addWidget(self.txt_host, 0, 1, 1, 3)

        # Path
        grid.addWidget(QLabel("Path:"), 1, 0)
        self.txt_path = QLineEdit()
        self.txt_path.setText("/axis-cgi/mjpg/video.cgi?fps=10")
        self.txt_path.setStyleSheet(input_style)
        grid.addWidget(self.txt_path, 1, 1, 1, 3)

        # Username / Password en una fila
        grid.addWidget(QLabel("User:"), 2, 0)
        self.txt_username = QLineEdit()
        self.txt_username.setText("root")
        self.txt_username.setStyleSheet(input_style)
        grid.addWidget(self.txt_username, 2, 1)

        grid.addWidget(QLabel("Pass:"), 2, 2)
        self.txt_password = QLineEdit()
        self.txt_password.setText("root")
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setStyleSheet(input_style)
        grid.addWidget(self.txt_password, 2, 3)

        # FPS / Timeout / Reconnect en una fila
        grid.addWidget(QLabel("FPS:"), 3, 0)
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 30)
        self.spin_fps.setValue(10)
        self.spin_fps.setStyleSheet(spin_style)
        self.spin_fps.setFixedWidth(50)
        grid.addWidget(self.spin_fps, 3, 1)

        grid.addWidget(QLabel("Timeout:"), 3, 2)
        self.spin_timeout = QDoubleSpinBox()
        self.spin_timeout.setRange(1.0, 30.0)
        self.spin_timeout.setValue(5.0)
        self.spin_timeout.setSuffix("s")
        self.spin_timeout.setStyleSheet(spin_style)
        self.spin_timeout.setFixedWidth(70)
        grid.addWidget(self.spin_timeout, 3, 3)

        layout.addLayout(grid)

        # Botón Test
        self.btn_test = QPushButton("Test")
        self.btn_test.setStyleSheet(
            "QPushButton{background:#3498db; color:#fff; border:none; padding:4px 8px; border-radius:3px;}"
            "QPushButton:hover{background:#5dade2;}"
            "QPushButton:disabled{background:#555;}"
        )
        self.btn_test.setFixedWidth(60)
        layout.addWidget(self.btn_test, alignment=Qt.AlignRight)

    def get_config(self) -> dict:
        """Obtiene la configuración actual del panel."""
        host = self.txt_host.text().strip()
        return {
            "type": "mjpeg",
            "enabled": self.chk_enabled.isChecked(),
            "host": host if host else "0.0.0.0",
            "path": self.txt_path.text().strip() or "/axis-cgi/mjpg/video.cgi?fps=10",
            "username": self.txt_username.text().strip(),
            "password": self.txt_password.text(),
            "fps_target": self.spin_fps.value(),
            "timeout_s": self.spin_timeout.value(),
            "reconnect_s": 2.0
        }

    def set_config(self, config: dict):
        """Establece la configuración en el panel."""
        self.chk_enabled.setChecked(config.get("enabled", False))
        host = config.get("host", "0.0.0.0")
        self.txt_host.setText(host if host != "0.0.0.0" else "")
        self.txt_path.setText(config.get("path", "/axis-cgi/mjpg/video.cgi?fps=10"))
        self.txt_username.setText(config.get("username", "root"))
        self.txt_password.setText(config.get("password", "root"))
        self.spin_fps.setValue(config.get("fps_target", 10))
        self.spin_timeout.setValue(config.get("timeout_s", 5.0))

    def set_status(self, status: str, color: str = "#888"):
        """Actualiza el label de estado."""
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"color:{color}; font-size:10px;")


class VisionConfigWidget(QWidget):
    """
    Widget de configuración IP para Vision System PRO.
    Permite configurar 3 cámaras IP MJPEG (Axis M1011).
    Reemplaza el sistema de índices USB.

    Phase 6.9: Safe tab changes - NO camera restart on show/hide
    """

    def __init__(self, vision_manager, parent=None):
        super().__init__(parent)
        self.vision_manager = vision_manager
        self._test_threads = []  # Track test threads for cleanup
        self._build_ui()
        self._load_config()
        self._connect_signals()
        print("[VisionConfigWidget] Initialized (no auto-start on tab change)")

    def showEvent(self, event):
        """Called when tab becomes visible - ONLY log, don't restart anything."""
        import threading
        super().showEvent(event)
        print(f"[VisionConfigWidget] TAB SHOWN (active threads: {threading.active_count()})")
        # NO camera restart here - only update status labels
        self._update_status_labels_only()

    def hideEvent(self, event):
        """Called when tab becomes hidden - cleanup test threads."""
        super().hideEvent(event)
        print("[VisionConfigWidget] TAB HIDDEN")
        # Cancel any running test threads (they are daemon so will die)
        self._test_threads = [t for t in self._test_threads if t.is_alive()]

    def _update_status_labels_only(self):
        """Update status labels without triggering any camera operations."""
        try:
            running = self.vision_manager.is_running()
            if running:
                self.status_label.setText("Sistema: CORRIENDO")
                self.status_label.setStyleSheet("color:#2ecc71; font-weight:700;")
            else:
                self.status_label.setText("Sistema: DETENIDO")
                self.status_label.setStyleSheet("color:#e74c3c; font-weight:700;")
        except Exception as e:
            print(f"[VisionConfigWidget] Error updating status: {e}")

    def _build_ui(self):
        """Construye la UI del widget."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Frame principal
        frame = QFrame()
        frame.setStyleSheet("QFrame{background:#1a1a1a; border:1px solid #333; border-radius:6px;}")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 12, 12, 12)
        frame_layout.setSpacing(8)

        # Título
        title = QLabel("VISION PRO - CÁMARAS IP (MJPEG)")
        title.setStyleSheet("font-weight:700; color:#ddd; font-size:12px;")
        frame_layout.addWidget(title)

        # Estado del sistema
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Sistema: DETENIDO")
        self.status_label.setStyleSheet("color:#e74c3c; font-weight:700;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        # Botones de control
        self.btn_start = QPushButton("Iniciar")
        self.btn_start.setStyleSheet(
            "QPushButton{background:#27ae60; border:1px solid #229954; border-radius:4px; padding:6px 12px; color:#fff;}"
            "QPushButton:hover{background:#2ecc71;}"
        )
        self.btn_start.clicked.connect(self._on_start)
        status_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Detener")
        self.btn_stop.setStyleSheet(
            "QPushButton{background:#e74c3c; border:1px solid #c0392b; border-radius:4px; padding:6px 12px; color:#fff;}"
            "QPushButton:hover{background:#ec7063;}"
        )
        self.btn_stop.clicked.connect(self._on_stop)
        status_layout.addWidget(self.btn_stop)

        frame_layout.addLayout(status_layout)

        # Separador
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("background:#333;")
        frame_layout.addWidget(sep1)

        # Paneles de cámaras
        self.panel_haze = CameraConfigPanel("Haze", "")
        self.panel_dj = CameraConfigPanel("DJ", "")
        self.panel_artist = CameraConfigPanel("Artist", "")

        frame_layout.addWidget(self.panel_haze)
        frame_layout.addWidget(self.panel_dj)
        frame_layout.addWidget(self.panel_artist)

        # Separador
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("background:#333;")
        frame_layout.addWidget(sep2)

        # Botones globales
        buttons_layout = QHBoxLayout()

        self.btn_save = QPushButton("Guardar")
        self.btn_save.setStyleSheet(
            "QPushButton{background:#9b59b6; border:none; border-radius:4px; padding:8px 16px; color:#fff; font-weight:700;}"
            "QPushButton:hover{background:#a569bd;}"
        )
        self.btn_save.clicked.connect(self._on_save)
        buttons_layout.addWidget(self.btn_save)

        self.btn_apply = QPushButton("Aplicar")
        self.btn_apply.setStyleSheet(
            "QPushButton{background:#3498db; border:none; border-radius:4px; padding:8px 16px; color:#fff; font-weight:700;}"
            "QPushButton:hover{background:#5dade2;}"
        )
        self.btn_apply.clicked.connect(self._on_apply)
        buttons_layout.addWidget(self.btn_apply)

        buttons_layout.addStretch()

        # FPS Label
        self.fps_label = QLabel("FPS: 0.0")
        self.fps_label.setStyleSheet("color:#27ae60; font-weight:700;")
        buttons_layout.addWidget(self.fps_label)

        frame_layout.addLayout(buttons_layout)

        layout.addWidget(frame)

    def _connect_signals(self):
        """Conecta señales de los paneles."""
        # Test buttons
        self.panel_haze.btn_test.clicked.connect(lambda: self._on_test("haze"))
        self.panel_dj.btn_test.clicked.connect(lambda: self._on_test("dj"))
        self.panel_artist.btn_test.clicked.connect(lambda: self._on_test("artist"))

    def _load_config(self):
        """Carga configuración desde VisionConfig."""
        try:
            config = self.vision_manager.get_config()
            cameras = config.data.get("cameras", {})

            # Cargar cada panel
            if "haze" in cameras:
                self.panel_haze.set_config(cameras["haze"])
            if "dj" in cameras:
                self.panel_dj.set_config(cameras["dj"])
            if "artist" in cameras:
                self.panel_artist.set_config(cameras["artist"])

            print("[VisionConfigWidget] Configuración cargada desde JSON")

        except Exception as e:
            print(f"[VisionConfigWidget] Error cargando config: {e}")

    def _on_save(self):
        """Guarda configuración a JSON."""
        try:
            config = self.vision_manager.get_config()

            # Obtener config de cada panel
            config.data["cameras"] = {
                "haze": self.panel_haze.get_config(),
                "dj": self.panel_dj.get_config(),
                "artist": self.panel_artist.get_config()
            }

            # Asegurar vision.ip_only = true
            if "vision" not in config.data:
                config.data["vision"] = {}
            config.data["vision"]["ip_only"] = True

            config.save()
            print("[VisionConfigWidget] Configuración guardada")

            QMessageBox.information(self, "Guardado", "Configuración guardada correctamente.")

        except Exception as e:
            print(f"[VisionConfigWidget] Error guardando: {e}")
            QMessageBox.warning(self, "Error", f"Error guardando: {e}")

    def _on_apply(self):
        """Aplica configuración en runtime."""
        try:
            # Primero guardar
            config = self.vision_manager.get_config()
            config.data["cameras"] = {
                "haze": self.panel_haze.get_config(),
                "dj": self.panel_dj.get_config(),
                "artist": self.panel_artist.get_config()
            }
            config.save()

            # Luego aplicar en runtime
            self.vision_manager.apply_camera_config()

            print("[VisionConfigWidget] Configuración aplicada")
            QMessageBox.information(self, "Aplicado", "Configuración aplicada. Las cámaras se reconectarán.")

        except Exception as e:
            print(f"[VisionConfigWidget] Error aplicando: {e}")
            QMessageBox.warning(self, "Error", f"Error aplicando: {e}")

    def _on_test(self, camera_name: str):
        """Prueba conexión de una cámara."""
        panel_map = {
            "haze": self.panel_haze,
            "dj": self.panel_dj,
            "artist": self.panel_artist
        }
        panel = panel_map.get(camera_name)
        if not panel:
            return

        cam_config = panel.get_config()
        host = cam_config.get("host", "")

        if not host or host == "0.0.0.0":
            panel.set_status("Host inválido", "#e74c3c")
            return

        # Validar posible typo en IP (192.160 vs 192.168)
        if "192.160" in host:
            panel.set_status("WARNING: 192.160? (typo 192.168?)", "#f39c12")
            print(f"[VisionUI] WARNING: host {host} parece tener typo (192.160 vs 192.168)")
            # Continuar de todos modos para que el usuario vea el error

        panel.set_status("Conectando...", "#f39c12")
        panel.btn_test.setEnabled(False)

        # Obtener valores de config
        fps_target = cam_config.get("fps_target", 10)
        timeout_s = cam_config.get("timeout_s", 5.0)

        # Test en thread separado
        def do_test():
            try:
                from core_vision.camera_source import MJPEGSource

                # Construir URL
                path = cam_config.get("path", "/axis-cgi/mjpg/video.cgi?fps=10")
                if host.startswith("http://") or host.startswith("https://"):
                    url = f"{host}{path}"
                else:
                    url = f"http://{host}{path}"

                print(f"[VisionUI] test {camera_name} -> url={url} fps={fps_target} timeout={timeout_s}s")

                source = MJPEGSource(
                    url=url,
                    username=cam_config.get("username", ""),
                    password=cam_config.get("password", ""),
                    fps_target=fps_target,
                    timeout_s=timeout_s
                )

                if source.start():
                    # Esperar unos frames
                    time.sleep(2)
                    ret, frame = source.read()
                    fps = source.get_fps()
                    source.stop()

                    if ret and frame is not None:
                        h, w = frame.shape[:2]
                        result = ("ok", f"OK {w}x{h} @ {fps:.1f}fps")
                        print(f"[VisionUI] test {camera_name} OK frame={w}x{h} fps={fps:.1f}")
                    else:
                        result = ("error", "Sin frames")
                else:
                    result = ("error", "Conexión fallida")

            except Exception as e:
                result = ("error", str(e)[:30])
                print(f"[VisionUI] test {camera_name} ERROR: {e}")

            # Actualizar UI desde thread principal
            QTimer.singleShot(0, lambda: self._update_test_result(camera_name, result))

        thread = threading.Thread(target=do_test, daemon=True, name=f"TestCamera-{camera_name}")
        thread.start()
        # Track for cleanup
        self._test_threads.append(thread)
        # Cleanup dead threads
        self._test_threads = [t for t in self._test_threads if t.is_alive()]

    def _update_test_result(self, camera_name: str, result: tuple):
        """Actualiza UI con resultado del test."""
        panel_map = {
            "haze": self.panel_haze,
            "dj": self.panel_dj,
            "artist": self.panel_artist
        }
        panel = panel_map.get(camera_name)
        if not panel:
            return

        panel.btn_test.setEnabled(True)

        status_type, message = result
        if status_type == "ok":
            panel.set_status(message, "#27ae60")
        else:
            panel.set_status(message, "#e74c3c")

    def _on_start(self):
        """Inicia el sistema Vision."""
        try:
            self.vision_manager.start()
            self.status_label.setText("Sistema: CORRIENDO")
            self.status_label.setStyleSheet("color:#2ecc71; font-weight:700;")
            print("[VisionConfigWidget] Sistema Vision iniciado")
        except Exception as e:
            print(f"[VisionConfigWidget] Error iniciando: {e}")

    def _on_stop(self):
        """Detiene el sistema Vision."""
        try:
            self.vision_manager.stop()
            self.status_label.setText("Sistema: DETENIDO")
            self.status_label.setStyleSheet("color:#e74c3c; font-weight:700;")
            print("[VisionConfigWidget] Sistema Vision detenido")
        except Exception as e:
            print(f"[VisionConfigWidget] Error deteniendo: {e}")

    def update_status(self):
        """Actualiza el estado del widget (llamado desde un timer)."""
        try:
            # Actualizar estado running
            running = self.vision_manager.is_running()
            if running:
                self.status_label.setText("Sistema: CORRIENDO")
                self.status_label.setStyleSheet("color:#2ecc71; font-weight:700;")
            else:
                self.status_label.setText("Sistema: DETENIDO")
                self.status_label.setStyleSheet("color:#e74c3c; font-weight:700;")

            # Actualizar FPS
            fps = self.vision_manager.get_fps()
            self.fps_label.setText(f"FPS: {fps:.1f}")

            # Actualizar estado de cada cámara
            for cam_name, panel in [("haze", self.panel_haze), ("dj", self.panel_dj), ("artist", self.panel_artist)]:
                status = self.vision_manager.get_camera_status(cam_name)
                if status["connected"]:
                    panel.set_status(f"Conectada @ {status['fps']:.1f}fps", "#27ae60")
                elif status["enabled"] and status["configured"]:
                    panel.set_status("Conectando...", "#f39c12")
                elif not status["configured"]:
                    panel.set_status("No configurada", "#888")
                else:
                    panel.set_status("Deshabilitada", "#888")

        except Exception as e:
            print(f"[VisionConfigWidget] Error actualizando estado: {e}")
