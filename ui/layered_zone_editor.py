"""
LayeredZoneEditor PRO - Professional zone editor with layers (Resolume-style)
Sistema de edición profesional de zonas con layers independientes

V9.2 FIX: Coordenadas normalizadas como fuente de verdad
- Zonas se guardan SOLO con coordenadas normalizadas [0..1]
- NO se escriben legacy coords (x/y/w/h) de widget - detector usa norm_*
- Mapeo widget<->frame respeta letterbox (offset + scale)
- ROI del detector coincide pixel-perfect con el marco dibujado

V9.1 FIX: Coordenadas normalizadas con mapeo letterbox correcto
"""
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QCheckBox, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QRect, QPoint, Signal, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QBrush, QFont


# =============================================================================
# COORDINATE MAPPING UTILITIES (V9.1 FIX)
# =============================================================================

def calculate_letterbox_params(widget_w: int, widget_h: int, frame_w: int, frame_h: int) -> dict:
    """
    Calcula parámetros de letterbox para mapeo de coordenadas.

    Args:
        widget_w, widget_h: Dimensiones del widget (canvas)
        frame_w, frame_h: Dimensiones del frame de cámara

    Returns:
        dict: {scale, draw_w, draw_h, offset_x, offset_y}
    """
    if frame_w <= 0 or frame_h <= 0:
        return {"scale": 1.0, "draw_w": widget_w, "draw_h": widget_h, "offset_x": 0, "offset_y": 0}

    scale = min(widget_w / frame_w, widget_h / frame_h)
    draw_w = int(frame_w * scale)
    draw_h = int(frame_h * scale)
    offset_x = (widget_w - draw_w) // 2
    offset_y = (widget_h - draw_h) // 2

    return {
        "scale": scale,
        "draw_w": draw_w,
        "draw_h": draw_h,
        "offset_x": offset_x,
        "offset_y": offset_y
    }


def normalized_to_widget(norm_x: float, norm_y: float, norm_w: float, norm_h: float,
                         letterbox: dict) -> tuple:
    """
    Convierte coordenadas normalizadas [0..1] a coordenadas de widget (pixels).

    Args:
        norm_x, norm_y: Posición normalizada (0..1)
        norm_w, norm_h: Tamaño normalizado (0..1)
        letterbox: Parámetros de letterbox

    Returns:
        tuple: (widget_x, widget_y, widget_w, widget_h) en pixels de widget
    """
    widget_x = int(norm_x * letterbox["draw_w"]) + letterbox["offset_x"]
    widget_y = int(norm_y * letterbox["draw_h"]) + letterbox["offset_y"]
    widget_w = int(norm_w * letterbox["draw_w"])
    widget_h = int(norm_h * letterbox["draw_h"])

    return (widget_x, widget_y, widget_w, widget_h)


def widget_to_normalized(widget_x: int, widget_y: int, widget_w: int, widget_h: int,
                         letterbox: dict) -> tuple:
    """
    Convierte coordenadas de widget (pixels) a coordenadas normalizadas [0..1].

    Args:
        widget_x, widget_y: Posición en pixels de widget
        widget_w, widget_h: Tamaño en pixels de widget
        letterbox: Parámetros de letterbox

    Returns:
        tuple: (norm_x, norm_y, norm_w, norm_h) en coordenadas normalizadas
    """
    if letterbox["draw_w"] <= 0 or letterbox["draw_h"] <= 0:
        return (0.0, 0.0, 0.1, 0.1)

    norm_x = (widget_x - letterbox["offset_x"]) / letterbox["draw_w"]
    norm_y = (widget_y - letterbox["offset_y"]) / letterbox["draw_h"]
    norm_w = widget_w / letterbox["draw_w"]
    norm_h = widget_h / letterbox["draw_h"]

    # Clamp to valid range
    norm_x = max(0.0, min(1.0, norm_x))
    norm_y = max(0.0, min(1.0, norm_y))
    norm_w = max(0.05, min(1.0, norm_w))
    norm_h = max(0.05, min(1.0, norm_h))

    return (norm_x, norm_y, norm_w, norm_h)


def normalized_to_frame(norm_x: float, norm_y: float, norm_w: float, norm_h: float,
                        frame_w: int, frame_h: int) -> tuple:
    """
    Convierte coordenadas normalizadas [0..1] a coordenadas de frame (pixels reales).
    Esta función es para que DJDetector use las coordenadas correctas.

    Args:
        norm_x, norm_y: Posición normalizada (0..1)
        norm_w, norm_h: Tamaño normalizado (0..1)
        frame_w, frame_h: Dimensiones del frame de cámara

    Returns:
        tuple: (frame_x, frame_y, frame_w, frame_h) en pixels de frame
    """
    fx = int(norm_x * frame_w)
    fy = int(norm_y * frame_h)
    fw = int(norm_w * frame_w)
    fh = int(norm_h * frame_h)

    return (fx, fy, fw, fh)


class LayerListWidget(QWidget):
    """
    V9.1 FIX: Panel lateral con lista de layers (zonas) mejorado.

    Cada fila: [#] Nombre | Color swatch | Vis checkbox | Estado ON/OFF | Delete claro
    - Selección visual fuerte con highlight consistente
    - Evita reconstruir la lista si no cambió nada (cache de hash)
    - Delete siempre visible y claro
    """
    layer_selected = Signal(int)  # id de zona seleccionada
    visibility_toggled = Signal(int, bool)  # id, visible
    lock_toggled = Signal(int, bool)  # id, locked
    layer_deleted = Signal(int)  # id

    # Colores por zona (para color swatch)
    ZONE_COLORS = [
        "#2ecc71",  # Verde
        "#3498db",  # Azul
        "#e74c3c",  # Rojo
        "#f39c12",  # Naranja
        "#9b59b6",  # Púrpura
    ]

    def __init__(self, max_zones=5, camera_type="DJ", parent=None):
        super().__init__(parent)
        self.max_zones = max_zones
        self.camera_type = camera_type
        self.zones = []
        self.selected_zone_id = None
        self._zones_hash = None  # V9.1: Cache para evitar reconstrucción innecesaria
        self._active_zones = set()  # V9.1: Zonas con detección activa
        self._build_ui()

    def _build_ui(self):
        """Construye la UI del panel de layers."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Título mejorado
        header = QFrame()
        header.setStyleSheet("background: #252525; border-radius: 4px;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 6, 8, 6)

        title = QLabel(f"LAYERS ({self.camera_type})")
        title.setStyleSheet("font-weight: bold; font-size: 12px; color: #fff;")
        header_layout.addWidget(title)

        # Contador de zonas
        self.zone_count = QLabel(f"0/{self.max_zones}")
        self.zone_count.setStyleSheet("font-size: 10px; color: #888;")
        header_layout.addWidget(self.zone_count)

        layout.addWidget(header)

        # Lista de layers con estilos mejorados
        self.layer_list = QListWidget()
        self.layer_list.setStyleSheet("""
            QListWidget {
                background: #1a1a1a;
                border: 2px solid #333;
                border-radius: 6px;
                color: #ddd;
                font-size: 11px;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #2a2a2a;
                margin: 2px 4px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background: #1e5799;
                border: 2px solid #3498db;
                color: #fff;
            }
            QListWidget::item:hover:!selected {
                background: #2a2a2a;
            }
        """)
        self.layer_list.itemClicked.connect(self._on_layer_clicked)
        layout.addWidget(self.layer_list)

        # Botón agregar zona (para DJ y ARTIST) con estilo mejorado
        if self.camera_type in ("DJ", "ARTIST"):
            self.btn_add = QPushButton("+ AGREGAR ZONA")
            self.btn_add.setStyleSheet("""
                QPushButton {
                    background: #27ae60;
                    border: none;
                    border-radius: 6px;
                    padding: 10px;
                    color: #fff;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: #2ecc71;
                }
                QPushButton:pressed {
                    background: #1e8449;
                }
                QPushButton:disabled {
                    background: #444;
                    color: #666;
                }
            """)
            self.btn_add.clicked.connect(self._on_add_zone)
            layout.addWidget(self.btn_add)

    def _compute_zones_hash(self) -> str:
        """V9.1: Calcula hash de las zonas para detectar cambios."""
        import hashlib
        import json
        data = json.dumps([(z.get("id"), z.get("name"), z.get("visible"), z.get("locked"))
                          for z in self.zones], sort_keys=True)
        return hashlib.md5(data.encode()).hexdigest()

    def set_zones(self, zones):
        """Establece las zonas y actualiza la lista solo si cambiaron."""
        self.zones = zones

        # V9.1: Solo reconstruir si cambió algo
        new_hash = self._compute_zones_hash()
        if new_hash != self._zones_hash:
            self._zones_hash = new_hash
            self._update_list()

    def set_active_zones(self, zone_ids: set):
        """V9.1: Establece qué zonas tienen detección activa (para indicador ON/OFF)."""
        if zone_ids != self._active_zones:
            self._active_zones = zone_ids
            self._update_list()

    def _update_list(self):
        """V9.1: Actualiza la lista visual de layers con diseño mejorado."""
        self.layer_list.clear()

        for idx, zone in enumerate(self.zones):
            zone_id = zone.get("id", 0)
            name = zone.get("name", f"{self.camera_type} {zone_id}")
            visible = zone.get("visible", True)
            locked = zone.get("locked", False)
            is_active = zone_id in self._active_zones

            # Color para esta zona
            color = self.ZONE_COLORS[idx % len(self.ZONE_COLORS)]

            # Crear widget personalizado para el item
            item_widget = QWidget()
            item_widget.setStyleSheet("background: transparent;")
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(4, 4, 4, 4)
            item_layout.setSpacing(6)

            # 1. Color swatch (indicador visual de zona)
            color_swatch = QLabel()
            color_swatch.setFixedSize(12, 24)
            color_swatch.setStyleSheet(f"""
                background: {color};
                border-radius: 3px;
                border: 1px solid {color};
            """)
            color_swatch.setToolTip(f"Color de zona {zone_id}")
            item_layout.addWidget(color_swatch)

            # 2. Número de zona
            num_label = QLabel(f"#{zone_id}")
            num_label.setStyleSheet("color: #aaa; font-weight: bold; min-width: 25px;")
            item_layout.addWidget(num_label)

            # 3. Nombre
            name_label = QLabel(name)
            name_label.setStyleSheet("color: #eee; font-weight: 500;")
            name_label.setMinimumWidth(60)
            item_layout.addWidget(name_label)

            item_layout.addStretch()

            # 4. Estado ON/OFF (indicador de detección activa)
            state_label = QLabel("ON" if is_active else "OFF")
            state_label.setFixedWidth(32)
            state_label.setAlignment(Qt.AlignCenter)
            if is_active:
                state_label.setStyleSheet("""
                    background: #27ae60;
                    color: #fff;
                    font-weight: bold;
                    font-size: 9px;
                    border-radius: 3px;
                    padding: 2px 4px;
                """)
            else:
                state_label.setStyleSheet("""
                    background: #555;
                    color: #999;
                    font-size: 9px;
                    border-radius: 3px;
                    padding: 2px 4px;
                """)
            state_label.setToolTip("Estado de detección")
            item_layout.addWidget(state_label)

            # 5. Checkbox visibilidad con estilo claro
            vis_check = QCheckBox()
            vis_check.setChecked(visible)
            vis_check.setToolTip("Mostrar/ocultar zona")
            vis_check.setStyleSheet("""
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                }
                QCheckBox::indicator:checked {
                    background: #3498db;
                    border: 2px solid #3498db;
                    border-radius: 3px;
                }
                QCheckBox::indicator:unchecked {
                    background: #333;
                    border: 2px solid #555;
                    border-radius: 3px;
                }
            """)
            vis_check.stateChanged.connect(
                lambda state, zid=zone_id: self.visibility_toggled.emit(zid, state == Qt.Checked)
            )
            item_layout.addWidget(vis_check)

            # 6. Botón lock/unlock (icono claro)
            lock_btn = QPushButton("L" if locked else "U")
            lock_btn.setFixedSize(24, 24)
            lock_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {'#e74c3c' if locked else '#444'};
                    border: none;
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: bold;
                    color: #fff;
                }}
                QPushButton:hover {{
                    background: {'#c0392b' if locked else '#666'};
                }}
            """)
            lock_btn.setToolTip("Bloqueado" if locked else "Desbloqueado")
            lock_btn.clicked.connect(
                lambda checked, zid=zone_id, l=locked: self.lock_toggled.emit(zid, not l)
            )
            item_layout.addWidget(lock_btn)

            # 7. Botón borrar (para DJ y ARTIST)
            if self.camera_type in ("DJ", "ARTIST"):
                del_btn = QPushButton("X")
                del_btn.setFixedSize(24, 24)
                del_btn.setStyleSheet("""
                    QPushButton {
                        background: #c0392b;
                        border: none;
                        border-radius: 4px;
                        font-size: 11px;
                        font-weight: bold;
                        color: #fff;
                    }
                    QPushButton:hover {
                        background: #e74c3c;
                    }
                    QPushButton:pressed {
                        background: #a93226;
                    }
                """)
                del_btn.setToolTip("Eliminar zona")
                del_btn.clicked.connect(lambda checked, zid=zone_id: self.layer_deleted.emit(zid))
                item_layout.addWidget(del_btn)

            # Agregar item a la lista
            list_item = QListWidgetItem(self.layer_list)
            list_item.setSizeHint(QSize(0, 40))  # Altura fija para consistencia
            list_item.setData(Qt.UserRole, zone_id)
            self.layer_list.addItem(list_item)
            self.layer_list.setItemWidget(list_item, item_widget)

        # Actualizar estado del botón agregar y contador
        if self.camera_type in ("DJ", "ARTIST"):
            self.btn_add.setEnabled(len(self.zones) < self.max_zones)
        self.zone_count.setText(f"{len(self.zones)}/{self.max_zones}")

    def _on_layer_clicked(self, item):
        """Callback cuando se hace clic en un layer."""
        zone_id = item.data(Qt.UserRole)
        self.selected_zone_id = zone_id
        self.layer_selected.emit(zone_id)

    def _on_add_zone(self):
        """Callback para agregar nueva zona (solo DJ)."""
        if len(self.zones) < self.max_zones:
            # Emitir señal para que el padre agregue la zona
            # La zona será agregada por el LayeredZoneEditor
            pass

    def select_zone(self, zone_id):
        """Selecciona un layer programáticamente."""
        self.selected_zone_id = zone_id
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            if item.data(Qt.UserRole) == zone_id:
                self.layer_list.setCurrentItem(item)
                break


class LayeredCanvas(QLabel):
    """
    Canvas profesional para edición de zonas con:
    - 8 handles (4 esquinas + 4 medios)
    - Drag & drop
    - Resize
    - Preview de cámara como background
    - Solo zona seleccionada editable
    - Zonas no seleccionadas semi-transparentes

    V9.1 FIX: Coordenadas normalizadas con letterbox correcto
    - Las zonas se almacenan en coordenadas normalizadas [0..1]
    - El mapeo widget<->frame respeta letterbox (offset + scale)
    - Marco y fill ROI están perfectamente alineados
    """
    zone_modified = Signal(dict)  # zona modificada

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 480)
        self.setStyleSheet("border: 2px solid #333; background-color: #000;")
        self.setAlignment(Qt.AlignCenter)

        # Estado
        self.zones = []
        self.selected_zone_id = None
        self.current_frame = None

        # V9.1 FIX: Dimensiones del frame actual para letterbox
        self._frame_w = 640
        self._frame_h = 480
        self._letterbox = calculate_letterbox_params(640, 480, 640, 480)

        # Drag & resize state
        self.dragging_zone = None
        self.drag_offset = QPoint(0, 0)
        self.resizing_zone = None
        self.resize_handle = None  # "tl", "tr", "bl", "br", "t", "b", "l", "r"

        self.setMouseTracking(True)

    def set_frame(self, frame):
        """Actualiza el frame de fondo (preview de cámara)."""
        self.current_frame = frame
        # V9.1 FIX: Actualizar dimensiones del frame y recalcular letterbox
        if frame is not None:
            h, w = frame.shape[:2]
            if w != self._frame_w or h != self._frame_h:
                self._frame_w = w
                self._frame_h = h
                self._letterbox = calculate_letterbox_params(
                    self.width(), self.height(), self._frame_w, self._frame_h
                )
        self.update()

    def set_zones(self, zones):
        """
        Establece las zonas a dibujar.

        V9.2 FIX: Limpia estados de drag/resize para evitar fantasmas
        cuando una zona es borrada mientras se arrastra/redimensiona.
        """
        self.zones = zones

        # V9.2 FIX: Limpiar estados de interacción para evitar referencias a zonas borradas
        # Esto previene el "ROI fantasma" cuando se borra una zona en medio de drag/resize
        self._clear_interaction_state()

        # Verificar que selected_zone_id sigue existiendo
        if self.selected_zone_id is not None:
            zone_ids = [z.get("id") for z in zones]
            if self.selected_zone_id not in zone_ids:
                self.selected_zone_id = zone_ids[0] if zone_ids else None

        self.update()

    def _clear_interaction_state(self):
        """
        V9.2 FIX: Limpia todos los estados de interacción (drag, resize).
        Llamar cuando las zonas cambian para evitar referencias a zonas borradas.
        """
        self.dragging_zone = None
        self.drag_offset = QPoint(0, 0)
        self.resizing_zone = None
        self.resize_handle = None

    def resizeEvent(self, event):
        """V9.1 FIX: Recalcular letterbox cuando cambia el tamaño del widget."""
        super().resizeEvent(event)
        self._letterbox = calculate_letterbox_params(
            self.width(), self.height(), self._frame_w, self._frame_h
        )

    def set_selected_zone(self, zone_id):
        """Establece la zona seleccionada."""
        self.selected_zone_id = zone_id
        self.update()

    def paintEvent(self, event):
        """Dibuja el canvas con frame de fondo y zonas."""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # V9.1 FIX: Recalcular letterbox para dimensiones actuales
        lb = calculate_letterbox_params(
            self.width(), self.height(), self._frame_w, self._frame_h
        )
        self._letterbox = lb

        # 1. Dibujar frame de fondo (preview de cámara) con letterbox correcto
        if self.current_frame is not None:
            try:
                h, w = self.current_frame.shape[:2]
                rgb_frame = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
                q_img = QImage(rgb_frame.data, w, h, w * 3, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(q_img)

                # Usar dimensiones de letterbox para dibujar exactamente donde corresponde
                scaled = pixmap.scaled(
                    lb["draw_w"], lb["draw_h"],
                    Qt.IgnoreAspectRatio, Qt.SmoothTransformation
                )
                painter.drawPixmap(lb["offset_x"], lb["offset_y"], scaled)
            except Exception as e:
                pass

        # 2. Dibujar grilla suave (opcional)
        self._draw_grid(painter)

        # 3. Dibujar zonas (primero las no seleccionadas, luego la seleccionada)
        # Esto asegura que la seleccionada esté encima
        for zone in self.zones:
            if zone.get("id") != self.selected_zone_id:
                if zone.get("visible", True):
                    self._draw_zone(painter, zone, selected=False)

        # Dibujar zona seleccionada
        for zone in self.zones:
            if zone.get("id") == self.selected_zone_id:
                if zone.get("visible", True):
                    self._draw_zone(painter, zone, selected=True)

        painter.end()

    def _draw_grid(self, painter):
        """Dibuja una grilla sutil de fondo."""
        pen = QPen(QColor(60, 60, 60), 1)
        painter.setPen(pen)

        # Líneas verticales cada 50px
        for x in range(0, self.width(), 50):
            painter.drawLine(x, 0, x, self.height())

        # Líneas horizontales cada 50px
        for y in range(0, self.height(), 50):
            painter.drawLine(0, y, self.width(), y)

    def _draw_zone(self, painter, zone, selected=False):
        """
        Dibuja una zona con o sin selección.

        V9.1 FIX: Usa coordenadas normalizadas y las mapea a widget via letterbox.
        Las zonas se almacenan con keys: norm_x, norm_y, norm_w, norm_h [0..1]
        Fallback a x, y, width, height si no existen (migración automática)
        """
        zone_id = zone.get("id", 0)
        locked = zone.get("locked", False)

        # V9.1 FIX: Leer coordenadas normalizadas o hacer fallback
        norm_x = zone.get("norm_x")
        norm_y = zone.get("norm_y")
        norm_w = zone.get("norm_w")
        norm_h = zone.get("norm_h")

        # Fallback: si no hay coordenadas normalizadas, usar legacy y migrar
        if norm_x is None:
            # Legacy coords: x, y, width, height en pixels absolutos
            # Asumimos que eran para un canvas de 640x480
            legacy_x = zone.get("x", 100)
            legacy_y = zone.get("y", 100)
            legacy_w = zone.get("w", zone.get("width", 150))
            legacy_h = zone.get("h", zone.get("height", 150))

            # Convertir a normalizadas asumiendo 640x480 original
            norm_x = legacy_x / 640.0
            norm_y = legacy_y / 480.0
            norm_w = legacy_w / 640.0
            norm_h = legacy_h / 480.0

            # Guardar en la zona para siguiente uso
            zone["norm_x"] = norm_x
            zone["norm_y"] = norm_y
            zone["norm_w"] = norm_w
            zone["norm_h"] = norm_h

        # Convertir a coordenadas de widget usando letterbox
        x, y, w, h = normalized_to_widget(norm_x, norm_y, norm_w, norm_h, self._letterbox)

        # Color y transparencia
        if selected:
            # Zona seleccionada: color sólido
            fill_color = QColor(0, 255, 0, 80)  # Verde semi-transparente para ver contenido
            border_color = QColor(0, 255, 0)
            border_width = 3
        else:
            # Zona no seleccionada: semi-transparente
            fill_color = QColor(0, 255, 0, 40)  # Verde más transparente
            border_color = QColor(0, 200, 0, 120)
            border_width = 1

        # Dibujar rectángulo
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(border_color, border_width))
        painter.drawRect(x, y, w, h)

        # Dibujar nombre de zona
        painter.setPen(QPen(Qt.white))
        font = QFont("Arial", 12, QFont.Bold)
        painter.setFont(font)
        name = zone.get("name", f"Zone {zone_id}")
        painter.drawText(x + 5, y + 20, name)

        # Dibujar handles SOLO si está seleccionada y no está bloqueada
        if selected and not locked:
            self._draw_handles(painter, x, y, w, h)

    def _draw_handles(self, painter, x, y, w, h):
        """Dibuja los 8 handles de resize (4 esquinas + 4 medios)."""
        handle_size = 10
        half_size = handle_size // 2

        # Color de handles
        painter.setBrush(QBrush(Qt.white))
        painter.setPen(QPen(QColor(0, 0, 0), 2))

        # Posiciones de handles
        handles = {
            "tl": (x - half_size, y - half_size),  # top-left
            "t": (x + w // 2 - half_size, y - half_size),  # top-middle
            "tr": (x + w - half_size, y - half_size),  # top-right
            "l": (x - half_size, y + h // 2 - half_size),  # left-middle
            "r": (x + w - half_size, y + h // 2 - half_size),  # right-middle
            "bl": (x - half_size, y + h - half_size),  # bottom-left
            "b": (x + w // 2 - half_size, y + h - half_size),  # bottom-middle
            "br": (x + w - half_size, y + h - half_size),  # bottom-right
        }

        for handle_pos in handles.values():
            painter.drawEllipse(handle_pos[0], handle_pos[1], handle_size, handle_size)

    def _get_zone_widget_coords(self, zone) -> tuple:
        """
        V9.1 FIX: Obtiene coordenadas de widget para una zona.
        Convierte de normalizadas a widget usando letterbox.
        """
        norm_x = zone.get("norm_x", 0.0)
        norm_y = zone.get("norm_y", 0.0)
        norm_w = zone.get("norm_w", 0.2)
        norm_h = zone.get("norm_h", 0.2)

        return normalized_to_widget(norm_x, norm_y, norm_w, norm_h, self._letterbox)

    def mousePressEvent(self, event):
        """Inicia drag o resize."""
        pos = event.pos()

        # Buscar zona seleccionada
        selected_zone = self._get_zone_by_id(self.selected_zone_id)
        if not selected_zone or selected_zone.get("locked", False):
            return

        # V9.1 FIX: Obtener coordenadas de widget desde normalizadas
        x, y, w, h = self._get_zone_widget_coords(selected_zone)

        # Verificar si se clickeó un handle
        handle = self._get_handle_at_pos(pos, x, y, w, h)
        if handle:
            self.resizing_zone = selected_zone
            self.resize_handle = handle
            return

        # Verificar si se clickeó dentro de la zona
        zone_rect = QRect(x, y, w, h)
        if zone_rect.contains(pos):
            self.dragging_zone = selected_zone
            self.drag_offset = pos - QPoint(x, y)
            return

    def mouseMoveEvent(self, event):
        """Actualiza drag o resize."""
        pos = event.pos()

        if self.dragging_zone:
            # V9.2 FIX: Drag usando coordenadas normalizadas como fuente de verdad
            # Obtener tamaño actual en widget coords
            _, _, w, h = self._get_zone_widget_coords(self.dragging_zone)

            # Nueva posición en widget coords
            new_x = pos.x() - self.drag_offset.x()
            new_y = pos.y() - self.drag_offset.y()

            # Clamp dentro del área de draw (letterbox)
            lb = self._letterbox
            new_x = max(lb["offset_x"], min(new_x, lb["offset_x"] + lb["draw_w"] - w))
            new_y = max(lb["offset_y"], min(new_y, lb["offset_y"] + lb["draw_h"] - h))

            # Convertir a coordenadas normalizadas (fuente de verdad)
            norm_x, norm_y, norm_w, norm_h = widget_to_normalized(new_x, new_y, w, h, lb)
            self.dragging_zone["norm_x"] = norm_x
            self.dragging_zone["norm_y"] = norm_y

            # V9.2 FIX: NO escribir legacy coords de widget - detector usa norm_*
            # Legacy x/y/w/h se recalculan desde norm cuando se guardan
            self.update()

        elif self.resizing_zone:
            # Resize desde handle
            self._resize_from_handle(pos)
            self.update()

    def mouseReleaseEvent(self, event):
        """Finaliza drag o resize."""
        if self.dragging_zone or self.resizing_zone:
            # Emitir señal de modificación
            modified_zone = self.dragging_zone or self.resizing_zone
            self.zone_modified.emit(modified_zone)

        self.dragging_zone = None
        self.resizing_zone = None
        self.resize_handle = None

    def _get_zone_by_id(self, zone_id):
        """Obtiene una zona por ID."""
        for zone in self.zones:
            if zone.get("id") == zone_id:
                return zone
        return None

    def _get_handle_at_pos(self, pos, x, y, w, h):
        """Determina si el mouse está sobre un handle."""
        handle_size = 10
        half_size = handle_size // 2

        handles = {
            "tl": QRect(x - half_size, y - half_size, handle_size, handle_size),
            "t": QRect(x + w // 2 - half_size, y - half_size, handle_size, handle_size),
            "tr": QRect(x + w - half_size, y - half_size, handle_size, handle_size),
            "l": QRect(x - half_size, y + h // 2 - half_size, handle_size, handle_size),
            "r": QRect(x + w - half_size, y + h // 2 - half_size, handle_size, handle_size),
            "bl": QRect(x - half_size, y + h - half_size, handle_size, handle_size),
            "b": QRect(x + w // 2 - half_size, y + h - half_size, handle_size, handle_size),
            "br": QRect(x + w - half_size, y + h - half_size, handle_size, handle_size),
        }

        for handle_name, handle_rect in handles.items():
            if handle_rect.contains(pos):
                return handle_name

        return None

    def _resize_from_handle(self, pos):
        """
        V9.1 FIX: Realiza resize desde el handle activo usando coordenadas normalizadas.
        """
        zone = self.resizing_zone
        lb = self._letterbox

        # Obtener posición actual en widget coords
        x, y, w, h = self._get_zone_widget_coords(zone)

        # Tamaño mínimo en pixels de widget
        min_size = 30

        # Calcular nueva posición/tamaño en widget coords según handle
        if self.resize_handle == "br":  # bottom-right
            new_w = pos.x() - x
            new_h = pos.y() - y
            w = max(min_size, min(new_w, lb["offset_x"] + lb["draw_w"] - x))
            h = max(min_size, min(new_h, lb["offset_y"] + lb["draw_h"] - y))

        elif self.resize_handle == "bl":  # bottom-left
            new_w = (x + w) - pos.x()
            new_h = pos.y() - y
            if new_w >= min_size and pos.x() >= lb["offset_x"]:
                x = pos.x()
                w = new_w
            h = max(min_size, min(new_h, lb["offset_y"] + lb["draw_h"] - y))

        elif self.resize_handle == "tr":  # top-right
            new_w = pos.x() - x
            new_h = (y + h) - pos.y()
            w = max(min_size, min(new_w, lb["offset_x"] + lb["draw_w"] - x))
            if new_h >= min_size and pos.y() >= lb["offset_y"]:
                y = pos.y()
                h = new_h

        elif self.resize_handle == "tl":  # top-left
            new_w = (x + w) - pos.x()
            new_h = (y + h) - pos.y()
            if new_w >= min_size and pos.x() >= lb["offset_x"]:
                x = pos.x()
                w = new_w
            if new_h >= min_size and pos.y() >= lb["offset_y"]:
                y = pos.y()
                h = new_h

        elif self.resize_handle == "t":  # top-middle
            new_h = (y + h) - pos.y()
            if new_h >= min_size and pos.y() >= lb["offset_y"]:
                y = pos.y()
                h = new_h

        elif self.resize_handle == "b":  # bottom-middle
            new_h = pos.y() - y
            h = max(min_size, min(new_h, lb["offset_y"] + lb["draw_h"] - y))

        elif self.resize_handle == "l":  # left-middle
            new_w = (x + w) - pos.x()
            if new_w >= min_size and pos.x() >= lb["offset_x"]:
                x = pos.x()
                w = new_w

        elif self.resize_handle == "r":  # right-middle
            new_w = pos.x() - x
            w = max(min_size, min(new_w, lb["offset_x"] + lb["draw_w"] - x))

        # V9.2 FIX: Convertir a coordenadas normalizadas (fuente de verdad)
        norm_x, norm_y, norm_w, norm_h = widget_to_normalized(x, y, w, h, lb)

        # Actualizar zona con coordenadas normalizadas
        zone["norm_x"] = norm_x
        zone["norm_y"] = norm_y
        zone["norm_w"] = norm_w
        zone["norm_h"] = norm_h

        # V9.2 FIX: NO escribir legacy coords de widget - detector usa norm_*
        # Legacy coords se recalculan desde norm cuando se guardan (ver vision_config.py)


class LayeredZoneEditor(QWidget):
    """
    Editor profesional de zonas con sistema de layers (tipo Resolume).

    Combina:
    - LayerListWidget (panel lateral de layers)
    - LayeredCanvas (workspace de edición)

    Emite:
    - zones_changed(list): cuando las zonas cambian
    - selected_zone_changed(int): cuando cambia la selección
    - visibility_toggled(int, bool): cuando cambia visibilidad
    - lock_toggled(int, bool): cuando cambia lock
    """
    zones_changed = Signal(list)
    selected_zone_changed = Signal(int)
    visibility_toggled = Signal(int, bool)
    lock_toggled = Signal(int, bool)

    def __init__(self, zone_list=None, max_zones=5, camera_type="DJ", parent=None):
        super().__init__(parent)
        self.max_zones = max_zones
        self.camera_type = camera_type
        self.zones = zone_list if zone_list else []
        self.selected_zone_id = None

        # Normalizar data model
        self._normalize_zones()

        self._build_ui()
        self._update_all()

    def _build_ui(self):
        """Construye la UI del editor."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Panel izquierdo: Lista de layers
        self.layer_list_widget = LayerListWidget(self.max_zones, self.camera_type)
        self.layer_list_widget.setMaximumWidth(250)
        self.layer_list_widget.layer_selected.connect(self._on_layer_selected)
        self.layer_list_widget.visibility_toggled.connect(self._on_visibility_toggled)
        self.layer_list_widget.lock_toggled.connect(self._on_lock_toggled)
        self.layer_list_widget.layer_deleted.connect(self._on_layer_deleted)
        layout.addWidget(self.layer_list_widget)

        # Panel derecho: Canvas de edición
        self.canvas = LayeredCanvas()
        self.canvas.zone_modified.connect(self._on_zone_modified)
        layout.addWidget(self.canvas, 1)

    def _normalize_zones(self):
        """
        Normaliza el data model de zonas para soportar ambos formatos.

        V9.1 FIX: Asegura que existan coordenadas normalizadas.
        Si no existen, las crea desde legacy coords asumiendo 640x480.
        """
        for zone in self.zones:
            # Asegurar que existan todos los campos
            if "id" not in zone:
                zone["id"] = self.zones.index(zone) + 1
            if "name" not in zone:
                zone["name"] = f"{self.camera_type} {zone['id']}"
            if "visible" not in zone:
                zone["visible"] = True
            if "locked" not in zone:
                zone["locked"] = False

            # Normalizar w/h vs width/height
            if "width" in zone and "w" not in zone:
                zone["w"] = zone["width"]
            if "height" in zone and "h" not in zone:
                zone["h"] = zone["height"]
            if "w" in zone and "width" not in zone:
                zone["width"] = zone["w"]
            if "h" in zone and "height" not in zone:
                zone["height"] = zone["h"]

            # V9.1 FIX: Asegurar coordenadas normalizadas
            if "norm_x" not in zone:
                legacy_x = zone.get("x", 100)
                legacy_y = zone.get("y", 100)
                legacy_w = zone.get("w", zone.get("width", 150))
                legacy_h = zone.get("h", zone.get("height", 150))

                # Convertir a normalizadas asumiendo 640x480 original
                zone["norm_x"] = max(0.0, min(1.0, legacy_x / 640.0))
                zone["norm_y"] = max(0.0, min(1.0, legacy_y / 480.0))
                zone["norm_w"] = max(0.05, min(1.0, legacy_w / 640.0))
                zone["norm_h"] = max(0.05, min(1.0, legacy_h / 480.0))

    def set_zones(self, zones):
        """Establece las zonas desde fuera."""
        self.zones = zones
        self._normalize_zones()
        self._update_all()

    def get_zones(self):
        """Obtiene las zonas actuales."""
        return self.zones

    def set_frame(self, frame):
        """Actualiza el frame de preview."""
        self.canvas.set_frame(frame)

    def add_zone(self):
        """
        Agrega una nueva zona (DJ y ARTIST).

        V9.2 FIX: Crea zonas con coordenadas normalizadas para DJ y ARTIST.
        """
        if self.camera_type not in ("DJ", "ARTIST") or len(self.zones) >= self.max_zones:
            return

        zone_id = len(self.zones) + 1

        # V9.2 FIX: Usar coordenadas normalizadas como fuente de verdad
        # Posición y tamaño inicial en coords normalizadas [0..1]
        if self.camera_type == "ARTIST":
            # Artist: zonas distribuidas horizontalmente (8 performers en escenario)
            base_x = (zone_id - 1) * 0.125  # 8 zones = 1/8 each
            base_y = 0.10
            base_w = 0.125
            base_h = 0.80
        else:
            # DJ: zonas escalonadas
            base_x = 0.15 + (zone_id - 1) * 0.05
            base_y = 0.20 + (zone_id - 1) * 0.05
            base_w = 0.25
            base_h = 0.30

        # Prefix for zone name
        prefix = "Artist" if self.camera_type == "ARTIST" else "DJ"

        new_zone = {
            "id": zone_id,
            "name": f"{prefix} {zone_id}",
            # Coordenadas normalizadas (fuente de verdad)
            "norm_x": base_x,
            "norm_y": base_y,
            "norm_w": base_w,
            "norm_h": base_h,
            # Legacy coords para compatibilidad (se actualizan en paint/edit)
            "x": int(base_x * 640),
            "y": int(base_y * 480),
            "w": int(base_w * 640),
            "h": int(base_h * 480),
            "width": int(base_w * 640),
            "height": int(base_h * 480),
            "visible": True,
            "locked": False
        }
        self.zones.append(new_zone)
        self._update_all()
        self.zones_changed.emit(self.zones)

    def _update_all(self):
        """Actualiza todos los componentes."""
        self.layer_list_widget.set_zones(self.zones)
        self.canvas.set_zones(self.zones)

        # Seleccionar primera zona por defecto
        if self.zones and not self.selected_zone_id:
            self.selected_zone_id = self.zones[0]["id"]
            self.canvas.set_selected_zone(self.selected_zone_id)
            self.layer_list_widget.select_zone(self.selected_zone_id)

    def _on_layer_selected(self, zone_id):
        """Callback cuando se selecciona un layer."""
        self.selected_zone_id = zone_id
        self.canvas.set_selected_zone(zone_id)
        self.selected_zone_changed.emit(zone_id)

    def _on_visibility_toggled(self, zone_id, visible):
        """Callback cuando cambia visibilidad."""
        for zone in self.zones:
            if zone["id"] == zone_id:
                zone["visible"] = visible
                break
        self._update_all()
        self.visibility_toggled.emit(zone_id, visible)
        self.zones_changed.emit(self.zones)

    def _on_lock_toggled(self, zone_id, locked):
        """Callback cuando cambia lock."""
        for zone in self.zones:
            if zone["id"] == zone_id:
                zone["locked"] = locked
                break
        self._update_all()
        self.lock_toggled.emit(zone_id, locked)
        self.zones_changed.emit(self.zones)

    def _on_layer_deleted(self, zone_id):
        """
        Callback cuando se elimina un layer.

        V9.2 FIX: Limpia estados de interacción del canvas para evitar
        "ROI fantasma" y bloqueo cuando se borra una zona seleccionada/arrastrada.
        """
        # V9.2 FIX: Limpiar estados del canvas ANTES de modificar zones
        # Esto evita que dragging_zone/resizing_zone apunten a zona borrada
        self.canvas._clear_interaction_state()

        # Eliminar la zona
        self.zones = [z for z in self.zones if z["id"] != zone_id]

        # Renumerar IDs con prefijo correcto
        prefix = "Artist" if self.camera_type == "ARTIST" else "DJ"
        for i, zone in enumerate(self.zones):
            zone["id"] = i + 1
            zone["name"] = f"{prefix} {i + 1}"

        # Actualizar selección
        if self.selected_zone_id == zone_id:
            self.selected_zone_id = self.zones[0]["id"] if self.zones else None
            self.canvas.set_selected_zone(self.selected_zone_id)

        self._update_all()
        self.zones_changed.emit(self.zones)

    def _on_zone_modified(self, zone):
        """Callback cuando se modifica una zona."""
        # La zona ya está modificada en la lista (es una referencia)
        self.zones_changed.emit(self.zones)
