"""
VisionConfigWidget - Widget de configuración IP para Vision System PRO
Panel de configuración de cámaras IP: MJPEG (Axis) + RTSP (H.264)
Phase 6.11: Soporte dual protocolo con selector UI

Soporta:
- MJPEG: Host + Path -> http://host/path (Axis cameras)
- RTSP: url_main + url_sub -> rtsp://... (generic IP cameras)
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QGroupBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QGridLayout, QMessageBox, QComboBox,
    QStackedWidget
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
import time
import threading


class CameraConfigPanel(QWidget):
    """
    Panel de configuración para una cámara IP individual.
    Phase 6.11: Soporte dual MJPEG + RTSP con selector de protocolo.
    """

    def __init__(self, camera_name: str, icon: str, parent=None):
        super().__init__(parent)
        self.camera_name = camera_name
        self.icon = icon
        self._build_ui()
        self._connect_protocol_change()

    def _build_ui(self):
        """Construye la UI del panel de cámara con soporte dual protocolo."""
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

        # === PROTOCOL SELECTOR ===
        proto_layout = QHBoxLayout()
        proto_layout.addWidget(QLabel("Protocolo:"))

        self.combo_protocol = QComboBox()
        self.combo_protocol.addItem("MJPEG (HTTP)", "mjpeg")
        self.combo_protocol.addItem("RTSP (H.264)", "rtsp")
        self.combo_protocol.setStyleSheet(
            "QComboBox{background:#0e0e14; color:#f0f0f0; border:1px solid #2e2e38; padding:8px 12px; border-radius:10px; font-family:'JetBrains Mono',monospace;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#141418; color:#f0f0f0; selection-background-color:#0d1a10; selection-color:#00e676;}"
        )
        self.combo_protocol.setFixedWidth(120)
        proto_layout.addWidget(self.combo_protocol)
        proto_layout.addStretch()

        layout.addLayout(proto_layout)

        # Style comun para inputs — WEB: input with glass inset
        input_style = "QLineEdit{background:#0e0e14; color:#f0f0f0; border:1px solid #2e2e38; padding:8px 12px; border-radius:10px; font-family:'JetBrains Mono',monospace;}"
        spin_style = "QSpinBox,QDoubleSpinBox{background:#0e0e14; color:#f0f0f0; border:1px solid #2e2e38; padding:6px 10px; border-radius:10px; font-family:'JetBrains Mono',monospace;}"

        # === STACKED WIDGET FOR PROTOCOL-SPECIFIC FIELDS ===
        self.stacked_fields = QStackedWidget()

        # --- PAGE 0: MJPEG FIELDS ---
        mjpeg_widget = QWidget()
        mjpeg_layout = QGridLayout(mjpeg_widget)
        mjpeg_layout.setSpacing(4)
        mjpeg_layout.setContentsMargins(0, 0, 0, 0)

        # Host/IP
        mjpeg_layout.addWidget(QLabel("Host:"), 0, 0)
        self.txt_host = QLineEdit()
        self.txt_host.setPlaceholderText("192.168.0.100")
        self.txt_host.setStyleSheet(input_style)
        mjpeg_layout.addWidget(self.txt_host, 0, 1, 1, 3)

        # Path
        mjpeg_layout.addWidget(QLabel("Path:"), 1, 0)
        self.txt_path = QLineEdit()
        self.txt_path.setText("/axis-cgi/mjpg/video.cgi?fps=10")
        self.txt_path.setStyleSheet(input_style)
        mjpeg_layout.addWidget(self.txt_path, 1, 1, 1, 3)

        # Username / Password MJPEG
        mjpeg_layout.addWidget(QLabel("User:"), 2, 0)
        self.txt_username_mjpeg = QLineEdit()
        self.txt_username_mjpeg.setText("root")
        self.txt_username_mjpeg.setStyleSheet(input_style)
        mjpeg_layout.addWidget(self.txt_username_mjpeg, 2, 1)

        mjpeg_layout.addWidget(QLabel("Pass:"), 2, 2)
        self.txt_password_mjpeg = QLineEdit()
        self.txt_password_mjpeg.setText("root")
        self.txt_password_mjpeg.setEchoMode(QLineEdit.Password)
        self.txt_password_mjpeg.setStyleSheet(input_style)
        mjpeg_layout.addWidget(self.txt_password_mjpeg, 2, 3)

        self.stacked_fields.addWidget(mjpeg_widget)

        # --- PAGE 1: RTSP FIELDS ---
        rtsp_widget = QWidget()
        rtsp_layout = QGridLayout(rtsp_widget)
        rtsp_layout.setSpacing(4)
        rtsp_layout.setContentsMargins(0, 0, 0, 0)

        # URL Main (Channel 101)
        rtsp_layout.addWidget(QLabel("URL Main:"), 0, 0)
        self.txt_url_main = QLineEdit()
        self.txt_url_main.setPlaceholderText("rtsp://admin:12345@192.168.1.64:554/Streaming/Channels/101")
        self.txt_url_main.setStyleSheet(input_style)
        rtsp_layout.addWidget(self.txt_url_main, 0, 1, 1, 3)

        # URL Sub (Channel 102)
        rtsp_layout.addWidget(QLabel("URL Sub:"), 1, 0)
        self.txt_url_sub = QLineEdit()
        self.txt_url_sub.setPlaceholderText("rtsp://admin:12345@192.168.1.64:554/Streaming/Channels/102")
        self.txt_url_sub.setStyleSheet(input_style)
        rtsp_layout.addWidget(self.txt_url_sub, 1, 1, 1, 3)

        # Preferred stream selector
        rtsp_layout.addWidget(QLabel("Preferido:"), 2, 0)
        self.combo_preferred = QComboBox()
        self.combo_preferred.addItem("Substream (720p)", "sub")
        self.combo_preferred.addItem("Mainstream (Full)", "main")
        self.combo_preferred.setStyleSheet(
            "QComboBox{background:#333; color:#ccc; border:1px solid #555; padding:4px; border-radius:3px;}"
        )
        self.combo_preferred.setFixedWidth(140)
        rtsp_layout.addWidget(self.combo_preferred, 2, 1)

        # Username / Password RTSP (opcional, si no embebidos en URL)
        rtsp_layout.addWidget(QLabel("User:"), 2, 2)
        self.txt_username_rtsp = QLineEdit()
        self.txt_username_rtsp.setPlaceholderText("(si no en URL)")
        self.txt_username_rtsp.setStyleSheet(input_style)
        rtsp_layout.addWidget(self.txt_username_rtsp, 2, 3)

        # Row 3: Transport and Low Latency options
        rtsp_layout.addWidget(QLabel("Transport:"), 3, 0)
        self.combo_transport = QComboBox()
        self.combo_transport.addItem("UDP (baja latencia)", "udp")
        self.combo_transport.addItem("TCP (más estable)", "tcp")
        self.combo_transport.setStyleSheet(
            "QComboBox{background:#333; color:#ccc; border:1px solid #555; padding:4px; border-radius:3px;}"
        )
        self.combo_transport.setFixedWidth(140)
        rtsp_layout.addWidget(self.combo_transport, 3, 1)

        # Low Latency checkbox
        self.chk_low_latency = QCheckBox("Low Latency Mode")
        self.chk_low_latency.setChecked(True)
        self.chk_low_latency.setStyleSheet("color:#ccc;")
        self.chk_low_latency.setToolTip("Activa opciones FFmpeg para mínima latencia (nobuffer, low_delay)")
        rtsp_layout.addWidget(self.chk_low_latency, 3, 2, 1, 2)

        self.stacked_fields.addWidget(rtsp_widget)

        layout.addWidget(self.stacked_fields)

        # === COMMON FIELDS (FPS / Timeout) ===
        common_grid = QGridLayout()
        common_grid.setSpacing(4)

        common_grid.addWidget(QLabel("FPS:"), 0, 0)
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 30)
        self.spin_fps.setValue(10)
        self.spin_fps.setStyleSheet(spin_style)
        self.spin_fps.setFixedWidth(50)
        common_grid.addWidget(self.spin_fps, 0, 1)

        common_grid.addWidget(QLabel("Timeout:"), 0, 2)
        self.spin_timeout = QDoubleSpinBox()
        self.spin_timeout.setRange(1.0, 30.0)
        self.spin_timeout.setValue(5.0)
        self.spin_timeout.setSuffix("s")
        self.spin_timeout.setStyleSheet(spin_style)
        self.spin_timeout.setFixedWidth(70)
        common_grid.addWidget(self.spin_timeout, 0, 3)

        layout.addLayout(common_grid)

        # Botón Test
        self.btn_test = QPushButton("Test")
        self.btn_test.setStyleSheet(
            "QPushButton{background:#3498db; color:#fff; border:none; padding:4px 8px; border-radius:3px;}"
            "QPushButton:hover{background:#5dade2;}"
            "QPushButton:disabled{background:#555;}"
        )
        self.btn_test.setFixedWidth(60)
        layout.addWidget(self.btn_test, alignment=Qt.AlignRight)

    def _connect_protocol_change(self):
        """Conecta el cambio de protocolo para mostrar/ocultar campos."""
        self.combo_protocol.currentIndexChanged.connect(self._on_protocol_changed)
        # Auto-detect RTSP when pasting URL
        self.txt_host.textChanged.connect(self._auto_detect_protocol)
        self.txt_url_main.textChanged.connect(self._auto_detect_protocol)
        self.txt_url_sub.textChanged.connect(self._auto_detect_protocol)

    def _on_protocol_changed(self, index: int):
        """Cambia los campos visibles según el protocolo seleccionado."""
        self.stacked_fields.setCurrentIndex(index)

    def _auto_detect_protocol(self, text: str):
        """Auto-detecta RTSP si el usuario pega una URL rtsp://."""
        if text.lower().startswith("rtsp://"):
            # Si está en campo MJPEG host, cambiar a RTSP
            if self.combo_protocol.currentData() == "mjpeg":
                self.combo_protocol.setCurrentIndex(1)  # RTSP
                # Mover el texto al campo correcto
                if self.sender() == self.txt_host:
                    self.txt_url_main.setText(text)
                    self.txt_host.clear()

    def get_protocol(self) -> str:
        """Obtiene el protocolo seleccionado."""
        return self.combo_protocol.currentData()

    def get_config(self) -> dict:
        """Obtiene la configuración actual del panel."""
        protocol = self.get_protocol()

        if protocol == "rtsp":
            # RTSP config with low-latency options
            return {
                "type": "rtsp",
                "enabled": self.chk_enabled.isChecked(),
                "url_main": self.txt_url_main.text().strip(),
                "url_sub": self.txt_url_sub.text().strip(),
                "preferred": self.combo_preferred.currentData(),
                "username": self.txt_username_rtsp.text().strip(),
                "password": "",  # Password usually embedded in URL
                "fps_target": self.spin_fps.value(),
                "timeout_s": self.spin_timeout.value(),
                "reconnect_s": 2.0,
                "transport": self.combo_transport.currentData(),
                "low_latency": self.chk_low_latency.isChecked()
            }
        else:
            # MJPEG config (default)
            host = self.txt_host.text().strip()
            return {
                "type": "mjpeg",
                "enabled": self.chk_enabled.isChecked(),
                "host": host if host else "0.0.0.0",
                "path": self.txt_path.text().strip() or "/axis-cgi/mjpg/video.cgi?fps=10",
                "username": self.txt_username_mjpeg.text().strip(),
                "password": self.txt_password_mjpeg.text(),
                "fps_target": self.spin_fps.value(),
                "timeout_s": self.spin_timeout.value(),
                "reconnect_s": 2.0
            }

    def set_config(self, config: dict):
        """Establece la configuración en el panel."""
        cam_type = config.get("type", "mjpeg").lower()

        # Set protocol selector
        if cam_type == "rtsp" or config.get("url_main") or config.get("url_sub"):
            self.combo_protocol.setCurrentIndex(1)  # RTSP
            self.stacked_fields.setCurrentIndex(1)

            # Set RTSP fields
            self.txt_url_main.setText(config.get("url_main", ""))
            self.txt_url_sub.setText(config.get("url_sub", ""))

            # Preferred stream
            preferred = config.get("preferred", "sub")
            idx = 0 if preferred == "sub" else 1
            self.combo_preferred.setCurrentIndex(idx)

            self.txt_username_rtsp.setText(config.get("username", ""))

            # Transport selector (Phase 6.13)
            transport = config.get("transport", "udp").lower()
            transport_idx = 0 if transport == "udp" else 1
            self.combo_transport.setCurrentIndex(transport_idx)

            # Low latency checkbox (Phase 6.13)
            self.chk_low_latency.setChecked(config.get("low_latency", True))
        else:
            self.combo_protocol.setCurrentIndex(0)  # MJPEG
            self.stacked_fields.setCurrentIndex(0)

            # Set MJPEG fields
            host = config.get("host", "0.0.0.0")
            self.txt_host.setText(host if host != "0.0.0.0" else "")
            self.txt_path.setText(config.get("path", "/axis-cgi/mjpg/video.cgi?fps=10"))
            self.txt_username_mjpeg.setText(config.get("username", "root"))
            self.txt_password_mjpeg.setText(config.get("password", "root"))

        # Common fields
        self.chk_enabled.setChecked(config.get("enabled", False))
        self.spin_fps.setValue(config.get("fps_target", 10))
        self.spin_timeout.setValue(config.get("timeout_s", 5.0))

    def set_status(self, status: str, color: str = "#888"):
        """Actualiza el label de estado."""
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"color:{color}; font-size:10px;")


class VisionConfigWidget(QWidget):
    """
    Widget de configuración IP para Vision System PRO.
    Permite configurar 3 cámaras IP: MJPEG (Axis) + RTSP (H.264).

    Phase 6.9: Safe tab changes - NO camera restart on show/hide
    Phase 6.11: Soporte dual protocolo MJPEG + RTSP con selector UI
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
        title = QLabel("VISION PRO - CÁMARAS IP (MJPEG + RTSP)")
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
        """
        Prueba conexión de una cámara.
        Phase 6.11: Soporta MJPEG y RTSP usando el factory.
        """
        panel_map = {
            "haze": self.panel_haze,
            "dj": self.panel_dj,
            "artist": self.panel_artist
        }
        panel = panel_map.get(camera_name)
        if not panel:
            return

        cam_config = panel.get_config()
        cam_type = cam_config.get("type", "mjpeg")

        # Validar según protocolo
        if cam_type == "rtsp":
            url_main = cam_config.get("url_main", "")
            url_sub = cam_config.get("url_sub", "")
            if not url_main and not url_sub:
                panel.set_status("URL RTSP requerida", "#e74c3c")
                return

            # Validar formato URL
            test_url = url_sub if cam_config.get("preferred") == "sub" and url_sub else (url_main or url_sub)
            if not test_url.lower().startswith("rtsp://"):
                panel.set_status("URL debe empezar con rtsp://", "#e74c3c")
                return

            # Check for mixed protocol error
            if "http://" in test_url.lower() or "https://" in test_url.lower():
                panel.set_status("ERROR: URL mixta (rtsp+http)", "#e74c3c")
                print(f"[VisionUI] ERROR: Mixed protocol URL detected: {test_url}")
                return

        else:
            # MJPEG validation
            host = cam_config.get("host", "")

            if not host or host == "0.0.0.0":
                panel.set_status("Host inválido", "#e74c3c")
                return

            # Check for rtsp:// in host (user pasted RTSP URL in MJPEG mode)
            if host.lower().startswith("rtsp://"):
                panel.set_status("Usar protocolo RTSP", "#f39c12")
                print(f"[VisionUI] WARNING: RTSP URL in MJPEG host field - switch protocol")
                return

            # Validar posible typo en IP (192.160 vs 192.168)
            if "192.160" in host:
                panel.set_status("WARNING: 192.160? (typo 192.168?)", "#f39c12")
                print(f"[VisionUI] WARNING: host {host} parece tener typo (192.160 vs 192.168)")
                # Continuar de todos modos para que el usuario vea el error

        panel.set_status("Conectando...", "#f39c12")
        panel.btn_test.setEnabled(False)

        # Test en thread separado
        def do_test():
            try:
                from core_vision.camera_source import create_source_from_config

                # Preparar config para factory
                source_config = dict(cam_config)

                # Para MJPEG, construir URL
                if cam_type == "mjpeg":
                    host = cam_config.get("host", "")
                    path = cam_config.get("path", "/axis-cgi/mjpg/video.cgi?fps=10")
                    if host.startswith("http://") or host.startswith("https://"):
                        url = f"{host}{path}"
                    else:
                        url = f"http://{host}{path}"
                    source_config["url"] = url

                print(f"[VisionUI] test {camera_name} -> type={cam_type} config={source_config}")

                # Usar factory para crear source correcto
                source = create_source_from_config(source_config)

                if source.start():
                    # Esperar unos frames
                    time.sleep(2.5)
                    ret, frame = source.read()
                    info = source.get_info()
                    fps = info.get("fps_read", 0.0)
                    drops = info.get("drops", 0)
                    source.stop()

                    if ret and frame is not None:
                        h, w = frame.shape[:2]
                        source_type = info.get("type", cam_type).upper()
                        result = ("ok", f"{source_type} {w}x{h} @ {fps:.1f}fps")
                        print(f"[VisionUI] test {camera_name} OK type={source_type} frame={w}x{h} fps={fps:.1f} drops={drops}")
                    else:
                        result = ("error", "Sin frames")
                else:
                    result = ("error", "Conexión fallida")

            except ValueError as e:
                # Factory validation error (mixed protocol, etc)
                result = ("error", str(e)[:40])
                print(f"[VisionUI] test {camera_name} VALIDATION ERROR: {e}")
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
        """
        Actualiza el estado del widget (llamado desde un timer).
        Phase 6.11: Muestra métricas adicionales (drops, decode_ms).
        """
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

            # Actualizar estado de cada cámara con métricas
            for cam_name, panel in [("haze", self.panel_haze), ("dj", self.panel_dj), ("artist", self.panel_artist)]:
                status = self.vision_manager.get_camera_status(cam_name)
                if status["connected"]:
                    # Mostrar tipo, FPS y drops si hay
                    cam_type = status.get("type", "mjpeg").upper()
                    fps_read = status.get("fps_read", status.get("fps", 0))
                    drops = status.get("drops", 0)

                    if drops > 0:
                        panel.set_status(f"{cam_type} {fps_read:.1f}fps (d:{drops})", "#27ae60")
                    else:
                        panel.set_status(f"{cam_type} @ {fps_read:.1f}fps", "#27ae60")
                elif status["enabled"] and status["configured"]:
                    panel.set_status("Conectando...", "#f39c12")
                elif not status["configured"]:
                    panel.set_status("No configurada", "#888")
                else:
                    panel.set_status("Deshabilitada", "#888")

        except Exception as e:
            print(f"[VisionConfigWidget] Error actualizando estado: {e}")
