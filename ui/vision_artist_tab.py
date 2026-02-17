"""
VisionArtistTab V9 - Tab for Artist Detector with YOLO ROI Detection
Preview + LayeredZoneEditor PRO + Debug Overlay + TEST FIRE buttons

Phase V9: YOLO-based ROI-only detection, 8-zone support (C72-C79)
Replaces old VisionArtistTab with HOG-based detection
Phase 9.1: Thread-safe frame buffer (fix cross-thread Qt crash)
"""
import cv2
import numpy as np
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QDoubleSpinBox, QCheckBox, QFrame, QGridLayout,
    QListWidget, QListWidgetItem, QScrollArea
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont

from .layered_zone_editor import LayeredZoneEditor


class LEDIndicator(QWidget):
    """Widget LED indicator for showing states."""

    def __init__(self, color=QColor(128, 128, 128), size=16, parent=None):
        super().__init__(parent)
        self.color = color
        self.led_size = size
        self.is_on = False
        self.setFixedSize(size, size)

    def set_on(self, on):
        """Turn LED on/off."""
        self.is_on = on
        self.update()

    def paintEvent(self, event):
        """Draw the LED."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.is_on:
            color = self.color
        else:
            color = QColor(60, 60, 60)

        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(40, 40, 40), 1))
        painter.drawEllipse(2, 2, self.led_size - 4, self.led_size - 4)


class VisionArtistTab(QWidget):
    """
    V9 Vision Artist Tab with YOLO ROI Detection.

    Features:
    - Preview with debug overlay (ROI rect, zone_id, detected, conf, infer_ms, fps)
    - Zone visibility toggle (visible=False => immediate OFF)
    - TEST FIRE buttons per zone (C72-C79)
    - Performance metrics display
    - Multi-zone status (8 zones)
    - Same UX as VisionDJTab
    """

    def __init__(self, vision_manager, parent=None):
        super().__init__(parent)
        self.vision_manager = vision_manager
        self._debug_overlay_enabled = True
        self._last_frame = None
        self._zone_states = {}  # zone_id -> {detected, conf, active}

        # Thread-safe frame buffer (Phase 9.1 - fix cross-thread Qt crash)
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._frame_updated = False

        self._build_ui()

        # Timer for UI updates (33ms ~30 FPS for smooth preview)
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(33)
        self.update_timer.timeout.connect(self._on_timer_tick)
        self.update_timer.start()

        # Connect frame callback (thread-safe: only buffers, no Qt calls)
        try:
            self.vision_manager.set_ui_callback_artist(self._on_frame_received)
        except AttributeError:
            print("[VisionArtistTab] Warning: set_ui_callback_artist() not available")

        # Load existing zones
        self._load_zones()

        print("[VisionArtistTab] Initialized with thread-safe frame buffer")

    def _build_ui(self):
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Top panel: Preview + Controls
        top_layout = QHBoxLayout()

        # Preview (left) - takes 2/3 of space
        top_layout.addWidget(self._build_preview_panel(), 2)

        # Controls (right) - takes 1/3 of space
        top_layout.addWidget(self._build_controls_panel(), 1)

        layout.addLayout(top_layout)

        # Bottom panel: Debug info
        layout.addWidget(self._build_debug_panel())

    def _build_preview_panel(self) -> QGroupBox:
        """Preview panel with LayeredZoneEditor and debug overlay."""
        group = QGroupBox("Vista Previa - Camara Artist + YOLO ROI Detection")
        layout = QVBoxLayout(group)

        # LayeredZoneEditor PRO (8 zones for Artist)
        self.zone_editor = LayeredZoneEditor(zone_list=[], max_zones=8, camera_type="ARTIST")
        self.zone_editor.zones_changed.connect(self._on_zones_changed)
        layout.addWidget(self.zone_editor)

        # Info bar
        info_layout = QHBoxLayout()

        self.fps_label = QLabel("FPS: 0.0")
        self.fps_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        info_layout.addWidget(self.fps_label)

        self.infer_label = QLabel("Infer: 0ms")
        self.infer_label.setStyleSheet("color: #3498db;")
        info_layout.addWidget(self.infer_label)

        self.dropped_label = QLabel("Dropped: 0")
        self.dropped_label.setStyleSheet("color: #e67e22;")
        info_layout.addWidget(self.dropped_label)

        info_layout.addStretch()

        # Debug overlay toggle
        self.debug_check = QCheckBox("Debug Overlay")
        self.debug_check.setChecked(True)
        self.debug_check.stateChanged.connect(self._on_debug_toggle)
        info_layout.addWidget(self.debug_check)

        layout.addLayout(info_layout)

        return group

    def _build_controls_panel(self) -> QGroupBox:
        """Control panel with zones, TEST FIRE, and settings."""
        group = QGroupBox("Artist Detector V9 - YOLO (8 Zones)")
        layout = QVBoxLayout(group)

        # Enable toggle
        self.artist_enabled_check = QCheckBox("Habilitado")
        self.artist_enabled_check.setChecked(False)
        self.artist_enabled_check.stateChanged.connect(self._on_enabled_changed)
        layout.addWidget(self.artist_enabled_check)

        # Status LEDs (C72-C79) - using scroll area for 8 zones
        cues_frame = QFrame()
        cues_frame.setFrameShape(QFrame.StyledPanel)
        cues_layout = QGridLayout(cues_frame)
        cues_layout.setContentsMargins(5, 5, 5, 5)

        cues_layout.addWidget(QLabel("Cues (C72-C79):"), 0, 0, 1, 4)

        # 8 LEDs for ARTIST_1..8
        self.led_artist_cues = []
        self.zone_visible_checks = []
        self.test_fire_btns = []

        for i in range(8):
            row = 1 + i
            zone_id = i + 1
            cue_id = 72 + i  # C72-C79

            # LED
            led = LEDIndicator(QColor(255, 165, 0), 14)  # Orange for artist
            self.led_artist_cues.append(led)
            cues_layout.addWidget(led, row, 0)

            # Label
            cues_layout.addWidget(QLabel(f"T{zone_id} (C{cue_id})"), row, 1)

            # Visible checkbox
            visible_check = QCheckBox("Vis")
            visible_check.setChecked(True)
            visible_check.setToolTip(f"Toggle visibility for zone {zone_id}")
            visible_check.stateChanged.connect(lambda state, zid=zone_id: self._on_zone_visible_changed(zid, state))
            self.zone_visible_checks.append(visible_check)
            cues_layout.addWidget(visible_check, row, 2)

            # TEST FIRE button
            fire_btn = QPushButton("FIRE")
            fire_btn.setFixedWidth(50)
            fire_btn.setStyleSheet("background-color: #e74c3c; color: white; font-size: 10px;")
            fire_btn.setToolTip(f"Test fire C{cue_id} for zone {zone_id}")
            fire_btn.clicked.connect(lambda checked, zid=zone_id: self._on_test_fire(zid))
            self.test_fire_btns.append(fire_btn)
            cues_layout.addWidget(fire_btn, row, 3)

        layout.addWidget(cues_frame)

        # Status display
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.StyledPanel)
        status_layout = QGridLayout(status_frame)
        status_layout.setContentsMargins(5, 5, 5, 5)

        status_layout.addWidget(QLabel("Estado:"), 0, 0)
        self.detector_state_label = QLabel("idle")
        self.detector_state_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.detector_state_label, 0, 1)

        status_layout.addWidget(QLabel("Zonas Activas:"), 1, 0)
        self.active_zones_label = QLabel("None")
        self.active_zones_label.setStyleSheet("font-weight: bold; color: #e67e22;")
        status_layout.addWidget(self.active_zones_label, 1, 1)

        status_layout.addWidget(QLabel("YOLO:"), 2, 0)
        self.yolo_status_label = QLabel("No disponible")
        status_layout.addWidget(self.yolo_status_label, 2, 1)

        status_layout.addWidget(QLabel("Degradado:"), 3, 0)
        self.degraded_label = QLabel("No")
        status_layout.addWidget(self.degraded_label, 3, 1)

        layout.addWidget(status_frame)

        # Zone management
        zone_layout = QHBoxLayout()
        self.add_zone_btn = QPushButton("+ Zona")
        self.add_zone_btn.clicked.connect(self._on_add_zone)
        zone_layout.addWidget(self.add_zone_btn)

        self.remove_zone_btn = QPushButton("- Zona")
        self.remove_zone_btn.clicked.connect(self._on_remove_zone)
        zone_layout.addWidget(self.remove_zone_btn)

        self.kill_all_btn = QPushButton("KILL ALL")
        self.kill_all_btn.setStyleSheet("background-color: #2c3e50; color: white;")
        self.kill_all_btn.clicked.connect(self._on_kill_all)
        zone_layout.addWidget(self.kill_all_btn)

        layout.addLayout(zone_layout)

        # Configuration
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("Delay (s):"))
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.5, 10.0)
        self.delay_spin.setValue(2.0)
        self.delay_spin.setSingleStep(0.5)
        config_layout.addWidget(self.delay_spin)
        layout.addLayout(config_layout)

        # Apply button
        self.apply_btn = QPushButton("Aplicar Cambios")
        self.apply_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        self.apply_btn.clicked.connect(self._on_apply)
        layout.addWidget(self.apply_btn)

        layout.addStretch()

        return group

    def _build_debug_panel(self) -> QGroupBox:
        """Debug panel with detailed metrics."""
        group = QGroupBox("Debug Info")
        layout = QHBoxLayout(group)

        # Zone status list
        self.zone_debug_list = QListWidget()
        self.zone_debug_list.setMaximumHeight(80)
        layout.addWidget(self.zone_debug_list, 2)

        # Performance metrics
        metrics_layout = QVBoxLayout()
        self.metrics_label = QLabel("Esperando datos...")
        self.metrics_label.setStyleSheet("font-family: monospace; font-size: 11px;")
        metrics_layout.addWidget(self.metrics_label)
        layout.addLayout(metrics_layout, 1)

        return group

    def _on_frame_received(self, frame):
        """
        Callback para recibir frames de la cámara Artist.
        THREAD-SAFE: Solo almacena en buffer, NO toca UI.
        Llamado desde el thread de CameraLoop.
        """
        if frame is None:
            return

        with self._frame_lock:
            self._latest_frame = frame.copy()
            self._frame_updated = True

    # Legacy method name for compatibility
    def update_frame(self, frame):
        """Legacy callback - redirects to thread-safe method."""
        self._on_frame_received(frame)

    def _on_timer_tick(self):
        """
        Timer tick - updates UI from main thread.
        Calls _update_preview every tick and _update_state every 8 ticks (~250ms).
        """
        self._update_preview()

        if not hasattr(self, '_state_tick_counter'):
            self._state_tick_counter = 0
        self._state_tick_counter += 1
        if self._state_tick_counter >= 8:  # ~250ms
            self._state_tick_counter = 0
            self._update_state()

    def _update_preview(self):
        """Update preview from thread-safe buffer. MAIN THREAD ONLY."""
        frame = None
        with self._frame_lock:
            if self._frame_updated and self._latest_frame is not None:
                frame = self._latest_frame
                self._frame_updated = False

        if frame is None:
            return

        self._last_frame = frame.copy()

        try:
            # Draw debug overlay if enabled (safe: runs in GUI thread)
            if self._debug_overlay_enabled:
                frame = self._draw_debug_overlay(frame)

            # Update the ZoneEditor with the frame (safe: runs in GUI thread)
            self.zone_editor.set_frame(frame)
        except Exception as e:
            print(f"[VisionArtistTab] Error updating frame: {e}")

    def _draw_debug_overlay(self, frame):
        """Draw debug overlay on frame: ROI rects, zone info."""
        try:
            artist_detector = self.vision_manager.get_artist_detector()
            if not artist_detector:
                return frame

            state = artist_detector.get_state()
            zones = state.get("zones", [])
            active_zones = state.get("active_zones", [])

            for zone in zones:
                zone_id = zone.get("id", 0)
                visible = zone.get("visible", True)

                # V9.2 FIX: Use normalized coordinates and convert to frame pixels
                h_frame, w_frame = frame.shape[:2]
                norm_x = zone.get("norm_x", 0.0)
                norm_y = zone.get("norm_y", 0.0)
                norm_w = zone.get("norm_w", 0.15)
                norm_h = zone.get("norm_h", 0.3)

                # Fallback to legacy if no norm coords (backwards compat)
                if norm_x == 0.0 and norm_y == 0.0 and "x" in zone:
                    legacy_x = zone.get("x", 0)
                    legacy_y = zone.get("y", 0)
                    legacy_w = zone.get("width", zone.get("w", 100))
                    legacy_h = zone.get("height", zone.get("h", 100))
                    norm_x = legacy_x / 640.0
                    norm_y = legacy_y / 480.0
                    norm_w = legacy_w / 640.0
                    norm_h = legacy_h / 480.0

                # Convert normalized to frame pixels
                x = int(norm_x * w_frame)
                y = int(norm_y * h_frame)
                w = int(norm_w * w_frame)
                h = int(norm_h * h_frame)

                # Get zone state from engine
                engine = artist_detector.get_engine()
                engine_state = engine.get_state()
                zone_info = engine_state.get("zones", {}).get(zone_id, {})

                detected = zone_info.get("detected", False)
                conf = zone_info.get("conf", 0.0)
                active = zone_id in active_zones

                # Color: orange if active, yellow if detected, red if not visible, gray otherwise
                if not visible:
                    color = (128, 128, 128)  # Gray
                    text_color = (128, 128, 128)
                elif active:
                    color = (0, 165, 255)  # Orange (BGR)
                    text_color = (0, 165, 255)
                elif detected:
                    color = (0, 255, 255)  # Yellow
                    text_color = (0, 255, 255)
                else:
                    color = (0, 0, 255)  # Red
                    text_color = (255, 255, 255)

                # Draw ROI rectangle
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

                # Draw zone info text
                status_str = "ON" if active else ("DET" if detected else "OFF")
                text = f"T{zone_id} {status_str} {conf:.2f}"
                cv2.putText(frame, text, (x + 5, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 1)

                # Store for debug list
                self._zone_states[zone_id] = {
                    "detected": detected,
                    "conf": conf,
                    "active": active,
                    "visible": visible,
                }

            # Draw global metrics in corner
            metrics = artist_detector.get_metrics()
            infer_ms = metrics.get("infer_ms_avg", 0)
            fps_real = metrics.get("fps_real", 0)
            dropped = metrics.get("dropped_frames", 0)

            info_text = f"FPS:{fps_real:.1f} Infer:{infer_ms:.0f}ms Drop:{dropped}"
            cv2.putText(frame, info_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        except Exception as e:
            print(f"[VisionArtistTab] Debug overlay error: {e}")

        return frame

    def _update_state(self):
        """Update UI state."""
        try:
            state = self.vision_manager.get_state()
            tracking_state = state.get("tracking", {})

            # Get detector directly for more detailed state
            artist_detector = self.vision_manager.get_artist_detector()
            if artist_detector:
                detector_state = artist_detector.get_state()
                metrics = artist_detector.get_metrics()

                # FPS and metrics
                fps_real = metrics.get("fps_real", 0)
                infer_ms = metrics.get("infer_ms_avg", 0)
                dropped = metrics.get("dropped_frames", 0)

                self.fps_label.setText(f"FPS: {fps_real:.1f}")
                self.infer_label.setText(f"Infer: {infer_ms:.0f}ms")
                self.dropped_label.setText(f"Dropped: {dropped}")

                # Detector state
                state_str = detector_state.get("state", "idle")
                self.detector_state_label.setText(state_str)

                # Color based on state
                if state_str == "active":
                    self.detector_state_label.setStyleSheet("font-weight: bold; color: #e67e22;")
                elif state_str == "disabled":
                    self.detector_state_label.setStyleSheet("font-weight: bold; color: #7f8c8d;")
                else:
                    self.detector_state_label.setStyleSheet("font-weight: bold; color: #3498db;")

                # Active zones
                active_zones = detector_state.get("active_zones", [])
                if active_zones:
                    self.active_zones_label.setText(", ".join(str(z) for z in active_zones))
                else:
                    self.active_zones_label.setText("None")

                # YOLO status
                yolo_available = detector_state.get("detector_available", False)
                self.yolo_status_label.setText("OK" if yolo_available else "No disponible")
                self.yolo_status_label.setStyleSheet("color: #27ae60;" if yolo_available else "color: #e74c3c;")

                # Degraded status
                degraded = detector_state.get("degraded", False)
                self.degraded_label.setText("SI" if degraded else "No")
                self.degraded_label.setStyleSheet("color: #e74c3c; font-weight: bold;" if degraded else "")

                # Update LEDs based on active zones
                for i in range(8):
                    zone_id = i + 1
                    self.led_artist_cues[i].set_on(zone_id in active_zones)

                # Update debug list
                self._update_zone_debug_list(detector_state)

                # Update metrics label
                health = artist_detector.get_health()
                engine_health = health.get("engine", {})
                self.metrics_label.setText(
                    f"Tick: {engine_health.get('tick_count', 0)}\n"
                    f"Errors: {engine_health.get('consecutive_errors', 0)}\n"
                    f"Watchdog: {'TRIGGERED' if engine_health.get('watchdog_triggered') else 'OK'}"
                )

            # Update enabled checkbox
            self.artist_enabled_check.blockSignals(True)
            self.artist_enabled_check.setChecked(tracking_state.get("enabled", False))
            self.artist_enabled_check.blockSignals(False)

        except Exception as e:
            print(f"[VisionArtistTab] Error updating state: {e}")

    def _update_zone_debug_list(self, detector_state):
        """Update zone debug list."""
        self.zone_debug_list.clear()
        zones = detector_state.get("zones", [])
        zones_state = self._zone_states

        for zone in zones:
            zone_id = zone.get("id", 0)
            info = zones_state.get(zone_id, {})
            detected = info.get("detected", False)
            conf = info.get("conf", 0.0)
            active = info.get("active", False)
            visible = info.get("visible", True)

            status = "ON" if active else ("DET" if detected else "OFF")
            vis_str = "" if visible else " [HIDDEN]"
            item = QListWidgetItem(f"Zone {zone_id}: {status} conf={conf:.2f}{vis_str}")

            if active:
                item.setForeground(QColor(230, 126, 34))  # Orange
            elif detected:
                item.setForeground(QColor(241, 196, 15))  # Yellow
            elif not visible:
                item.setForeground(QColor(127, 140, 141))  # Gray
            else:
                item.setForeground(QColor(52, 152, 219))  # Blue

            self.zone_debug_list.addItem(item)

    def _load_zones(self):
        """Load zones from config."""
        try:
            config = self.vision_manager.get_config()
            zones = config.get_artist_zones()
            self.zone_editor.set_zones(zones)
        except Exception as e:
            print(f"[VisionArtistTab] Error loading zones: {e}")

    def _on_zones_changed(self, zones):
        """Callback when zones change."""
        pass  # Updates handled by timer

    def _on_add_zone(self):
        """Add a new zone."""
        self.zone_editor.add_zone()

    def _on_remove_zone(self):
        """Remove selected zone."""
        # LayeredZoneEditor handles removal via layer panel
        pass

    def _on_enabled_changed(self):
        """Handle enable/disable toggle. V10: persist=False, Calendar es autoridad."""
        enabled = self.artist_enabled_check.isChecked()
        self.vision_manager.enable_module("artist", enabled, source="ui", persist=False)

    def _on_zone_visible_changed(self, zone_id: int, state: int):
        """Handle zone visibility toggle."""
        visible = state == Qt.Checked
        try:
            artist_detector = self.vision_manager.get_artist_detector()
            if artist_detector:
                artist_detector.set_zone_visible(zone_id, visible)
                print(f"[VisionArtistTab] Zone {zone_id} visible={visible}")
        except Exception as e:
            print(f"[VisionArtistTab] Error setting zone visibility: {e}")

    def _on_test_fire(self, zone_id: int):
        """Test fire a zone cue."""
        try:
            artist_detector = self.vision_manager.get_artist_detector()
            if artist_detector:
                result = artist_detector._test_fire_zone(zone_id)
                print(f"[VisionArtistTab] TEST FIRE Zone {zone_id}: {result}")
        except Exception as e:
            print(f"[VisionArtistTab] Error test firing: {e}")

    def _on_kill_all(self):
        """Kill all Artist cues."""
        try:
            artist_detector = self.vision_manager.get_artist_detector()
            if artist_detector:
                result = artist_detector._test_fire_zone(1, force_off=True)
                print(f"[VisionArtistTab] KILL ALL: {result}")
        except Exception as e:
            print(f"[VisionArtistTab] Error killing all: {e}")

    def _on_debug_toggle(self, state):
        """Toggle debug overlay."""
        self._debug_overlay_enabled = state == Qt.Checked

    def _on_apply(self):
        """Apply configuration changes."""
        try:
            # Update zones in ArtistDetector
            zones = self.zone_editor.get_zones()
            self.vision_manager.set_artist_zones(zones)

            # Update delay
            artist_detector = self.vision_manager.get_artist_detector()
            if artist_detector:
                artist_detector.set_disappear_delay(self.delay_spin.value())

            # Save to config JSON
            config = self.vision_manager.get_config()
            artist_config = config.get_artist_config()
            artist_config["zones"] = zones
            artist_config["zones_count"] = len(zones)
            artist_config["disappear_delay"] = self.delay_spin.value()

            config.set("artist", artist_config)
            config.save()

            print(f"[VisionArtistTab] Configuration applied ({len(zones)} zones)")

        except Exception as e:
            print(f"[VisionArtistTab] Error applying config: {e}")
