# cue_engine_debug_widget.py - Widget de Debug para CueEngine Modular - ✅ MÁS GRANDE
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QMessageBox, QFrame, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class CueEngineDebugWidget(QWidget):
    """
    Widget de debug para mostrar información del CueEngine modular en tiempo real.
    Se integra en el tab Monitor de main.py.
    ✅ VERSIÓN EXPANDIDA - MÁS ANCHA Y ALTA
    """
    
    def __init__(self, cue_engine, parent=None):
        super().__init__(parent)
        self.cue_engine = cue_engine
        
        # ✅ Layout responsive: sin tamaños fijos
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        # Cache para optimizar UI
        self._last_status_text = None
        self._last_metrics_text = None
        self._last_debug_text = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Construye la interfaz del widget - ✅ EXPANDIDA"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # Título más grande
        title = QLabel("CUE ENGINE DEBUG")
        title.setStyleSheet("font-weight:700; color:#00e676; font-size:12px; letter-spacing:1px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Información básica del engine - ✅ EXPANDIDA
        self.basic_info = QLabel("Inicializando...")
        self.basic_info.setStyleSheet(
            "color:#f0f0f0; font-family: 'JetBrains Mono', monospace; font-size:10px; "
            "background:#0e0e14; border:1px solid #2e2e38; border-radius:12px; "
            "padding:8px 12px;"
        )
        self.basic_info.setWordWrap(True)
        self.basic_info.setMinimumHeight(90)
        layout.addWidget(self.basic_info)
        
        # Métricas de rendimiento - ✅ EXPANDIDA
        metrics_frame = QFrame()
        metrics_frame.setStyleSheet("QFrame { background:#141418; border:1px solid #2e2e38; border-radius:16px; }")
        metrics_layout = QVBoxLayout(metrics_frame)
        metrics_layout.setContentsMargins(8, 8, 8, 8)
        metrics_layout.setSpacing(4)
        
        metrics_title = QLabel("MÉTRICAS")
        metrics_title.setStyleSheet("color:#ffd740; font-weight:bold; font-size:10px;")
        metrics_layout.addWidget(metrics_title)
        
        self.metrics_info = QLabel("Calculando...")
        self.metrics_info.setStyleSheet("color:#4dd0e1; font-family: monospace; font-size:10px;")
        self.metrics_info.setWordWrap(True)
        self.metrics_info.setMinimumHeight(60)
        metrics_layout.addWidget(self.metrics_info)
        
        layout.addWidget(metrics_frame)
        
        # Debug de especialistas - ✅ EXPANDIDA
        specialists_frame = QFrame()
        specialists_frame.setStyleSheet("QFrame { background:#141418; border:1px solid #2e2e38; border-radius:16px; }")
        specialists_layout = QVBoxLayout(specialists_frame)
        specialists_layout.setContentsMargins(8, 8, 8, 8)
        specialists_layout.setSpacing(4)
        
        specialists_title = QLabel("ESPECIALISTAS")
        specialists_title.setStyleSheet("color:#ffd740; font-weight:bold; font-size:10px;")
        specialists_layout.addWidget(specialists_title)
        
        self.specialists_info = QLabel("Cargando...")
        self.specialists_info.setStyleSheet("color:#4dd0e1; font-family: monospace; font-size:10px;")
        self.specialists_info.setWordWrap(True)
        self.specialists_info.setMinimumHeight(45)
        specialists_layout.addWidget(self.specialists_info)
        
        layout.addWidget(specialists_frame)
        
        # Botones de control - ✅ EXPANDIDOS
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(6)
        
        self.btn_debug_full = QPushButton("Debug Completo")
        self.btn_debug_full.setStyleSheet(
            "QPushButton{background:#141418; border:1px solid #2e2e38; border-radius:10px; "
            "padding:8px 16px; color:#f0f0f0; font-size:10px;} QPushButton:hover{background:#1c1c22; border-color:#3e5e3e;}"
        )
        self.btn_debug_full.clicked.connect(self.show_full_debug)
        
        self.btn_reset = QPushButton("Reset Engine")
        self.btn_reset.setStyleSheet(
            "QPushButton{background:rgba(255,82,82,0.25); border:1px solid rgba(255,82,82,0.30); border-radius:10px; "
            "padding:8px 16px; color:#ff5252; font-size:10px;} QPushButton:hover{background:rgba(255,82,82,0.35);}"
        )
        self.btn_reset.clicked.connect(self.reset_engine)
        
        self.btn_emergency = QPushButton("EMERGENCY")
        self.btn_emergency.setStyleSheet(
            "QPushButton{background:rgba(255,82,82,0.35); border:2px solid #ff5252; border-radius:10px; "
            "padding:8px 16px; color:#ff5252; font-size:10px; font-weight:bold;} QPushButton:hover{background:rgba(255,82,82,0.50);}"
        )
        self.btn_emergency.clicked.connect(self.emergency_stop)
        
        buttons_layout.addWidget(self.btn_debug_full)
        buttons_layout.addWidget(self.btn_reset)
        buttons_layout.addWidget(self.btn_emergency)
        buttons_layout.addStretch()
        
        layout.addLayout(buttons_layout)
        
        # Estilo general
        self.setStyleSheet(
            "QWidget{background:#151515; border:1px solid #333; border-radius:6px;}"
        )
        
        # Asegurar políticas expansivas en frames
        metrics_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        specialists_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    
    def update_display(self):
        """Actualiza la información mostrada - VERSIÓN CORREGIDA"""
        if not self.cue_engine:
            self.basic_info.setText("CueEngine no disponible")
            self.metrics_info.setText("Engine no disponible")
            self.specialists_info.setText("Engine no disponible")
            return
        
        try:
            # CORRECCIÓN: verificar si get_status existe antes de llamarlo
            if hasattr(self.cue_engine, 'get_status'):
                status = self.cue_engine.get_status()
            else:
                # Fallback: crear status básico a partir de atributos disponibles
                status = self._create_fallback_status()
            
            # Información básica
            basic_text = self._format_basic_info(status)
            if basic_text != self._last_status_text:
                self._last_status_text = basic_text
                self.basic_info.setText(basic_text)
            
            # Métricas
            try:
                if hasattr(self.cue_engine, 'get_metrics'):
                    metrics = self.cue_engine.get_metrics()
                else:
                    metrics = self._calculate_fallback_metrics(status)
                
                metrics_text = self._format_metrics(metrics)
                if metrics_text != self._last_metrics_text:
                    self._last_metrics_text = metrics_text
                    self.metrics_info.setText(metrics_text)
            except Exception as e:
                self.metrics_info.setText(f"Error métricas: {e}")
            
            # Debug de especialistas
            try:
                if hasattr(self.cue_engine, 'get_specialist_debug'):
                    debug_text = self.cue_engine.get_specialist_debug()
                else:
                    debug_text = self._get_fallback_specialist_debug()
                
                if debug_text != self._last_debug_text:
                    self._last_debug_text = debug_text
                    # Truncar si es muy largo para ajustar al espacio disponible
                    if len(debug_text) > 300:
                        debug_text = debug_text[:297] + "..."
                    self.specialists_info.setText(debug_text)
            except Exception as e:
                self.specialists_info.setText(f"Error debug: {e}")
            
        except Exception as e:
            error_msg = f"Error: CueEngine 'get_status' faltante"
            self.basic_info.setText(error_msg)
            print(f"[CueEngineDebugWidget] {error_msg}: {e}")
    
    def _create_fallback_status(self):
        """Crea status básico cuando get_status() no está disponible"""
        try:
            return {
                "version": "4.3",
                "architecture": "modular (fallback)",
                "current_state": getattr(self.cue_engine, 'last_state', 'UNKNOWN'),
                "current_energy": getattr(self.cue_engine, 'last_energy', 'UNKNOWN'),
                "last_specialist": getattr(self.cue_engine, 'last_specialist', 'N/A'),
                "auto_update_running": getattr(self.cue_engine, '_auto_update_running', False),
                "uptime_seconds": 0.0,
                "last_update_time": 0.0,
                "stats": getattr(self.cue_engine, 'stats', {}),
                "last_error": getattr(self.cue_engine, 'last_error', None),
                "interval": getattr(self.cue_engine, 'interval', 0.3),
                "modules_count": 6
            }
        except Exception:
            return {
                "version": "N/A",
                "architecture": "error",
                "current_state": "ERROR",
                "current_energy": "ERROR",
                "last_specialist": "N/A",
                "auto_update_running": False,
                "stats": {},
                "last_error": "No se pudo crear status"
            }
    
    def _calculate_fallback_metrics(self, status):
        """Calcula métricas básicas cuando get_metrics() no está disponible"""
        stats = status.get('stats', {})
        uptime = max(status.get('uptime_seconds', 1), 0.001)
        
        return {
            "uptime_seconds": uptime,
            "updates_per_second": stats.get('total_updates', 0) / uptime,
            "specialist_calls_per_update": 1.0,  # estimación
            "error_rate": 0.0,
            "state_change_frequency": stats.get('state_changes', 0),
            "energy_change_frequency": stats.get('energy_changes', 0)
        }
    
    def _get_fallback_specialist_debug(self):
        """Debug básico de especialistas cuando get_specialist_debug() no está disponible"""
        try:
            if hasattr(self.cue_engine, 'get_active_cues'):
                active_cues = self.cue_engine.get_active_cues()
                if active_cues:
                    return f"Cues activos: {active_cues}"
                else:
                    return "Sin cues activos"
            else:
                return "Debug no disponible\n(método get_specialist_debug faltante)"
        except Exception as e:
            return f"Error debug fallback: {e}"
    
    def _format_basic_info(self, status):
        """Formatea la información básica del engine"""
        lines = [
            f"v{status.get('version', 'N/A')} {status.get('architecture', 'N/A')}",
            f"Estado: {status.get('current_state', 'N/A')} / {status.get('current_energy', 'N/A')}",
            f"Último: {status.get('last_specialist', 'N/A')}",
            f"Auto: {'ON' if status.get('auto_update_running', False) else 'OFF'}",
            ""
        ]
        
        stats = status.get('stats', {})
        lines.extend([
            f"Updates: {stats.get('total_updates', stats.get('updates', 0))}",
            f"Estados: {stats.get('state_changes', 0)} | Energía: {stats.get('energy_changes', 0)}",
            f"Llamadas: {stats.get('specialist_calls', 'N/A')}",
            f"Errores: {stats.get('specialist_errors', 0)}"
        ])
        
        if stats.get('last_error') or status.get('last_error'):
            error = stats.get('last_error') or status.get('last_error')
            lines.append(f"Último error: {str(error)[:50]}...")
        
        return "\n".join(lines)
    
    def _format_metrics(self, metrics):
        """Formatea las métricas de rendimiento"""
        lines = [
            f"Uptime: {metrics.get('uptime_seconds', 0):.1f}s",
            f"UPS: {metrics.get('updates_per_second', 0):.2f}",
            f"Calls/Update: {metrics.get('specialist_calls_per_update', 0):.1f}",
            f"Error Rate: {metrics.get('error_rate', 0):.3f}",
            f"Estado/min: {metrics.get('state_change_frequency', 0):.1f}",
            f"Energía/min: {metrics.get('energy_change_frequency', 0):.1f}"
        ]
        
        return "\n".join(lines)
    
    def show_full_debug(self):
        """Muestra debug completo en MessageBox"""
        if not self.cue_engine:
            QMessageBox.information(self, "Debug", "CueEngine no disponible")
            return
        
        try:
            # CORRECCIÓN: verificar si get_status existe
            if hasattr(self.cue_engine, 'get_status'):
                status = self.cue_engine.get_status()
            else:
                status = self._create_fallback_status()
                status["_fallback_notice"] = "Status generado por fallback - get_status() no disponible"
            
            # Agregar información adicional si está disponible
            if hasattr(self.cue_engine, 'get_modules_status'):
                try:
                    modules_status = self.cue_engine.get_modules_status()
                    status["modules_status"] = modules_status
                except Exception as e:
                    status["modules_status_error"] = str(e)
            
            # Formatear JSON para mostrar
            debug_info = json.dumps(status, indent=2, ensure_ascii=False, default=str)
            
            # Crear MessageBox personalizado
            msg = QMessageBox(self)
            msg.setWindowTitle("CueEngine Modular v4.3 - Debug Completo")
            msg.setText("Estado completo del sistema:")
            msg.setDetailedText(debug_info)
            msg.setStandardButtons(QMessageBox.Ok)
            
            # Ajustar tamaño
            msg.resize(700, 500)
            
            msg.exec()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error obteniendo debug completo:\n{e}")
    
    def reset_engine(self):
        """Resetea el CueEngine"""
        if not self.cue_engine:
            QMessageBox.warning(self, "Reset", "CueEngine no disponible")
            return
        
        reply = QMessageBox.question(
            self, "Reset CueEngine", 
            "¿Está seguro de que desea resetear el CueEngine?\n\n"
            "Esto:\n"
            "- Detendrá el auto-update temporalmente\n"
            "- Reseteará todos los especialistas\n"
            "- Volverá al estado BASE_GOLPE/MEDIA\n"
            "- Reiniciará el auto-update",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                if hasattr(self.cue_engine, 'reset'):
                    self.cue_engine.reset()
                    QMessageBox.information(self, "Reset", "CueEngine reseteado exitosamente")
                else:
                    QMessageBox.warning(self, "Reset", "Método reset() no disponible en CueEngine")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error durante reset:\n{e}")
    
    def emergency_stop(self):
        """Parada de emergencia"""
        if not self.cue_engine:
            QMessageBox.warning(self, "Emergency", "CueEngine no disponible")
            return
        
        reply = QMessageBox.critical(
            self, "PARADA DE EMERGENCIA", 
            "⚠️ PARADA DE EMERGENCIA ⚠️\n\n"
            "Esto ejecutará una parada completa:\n"
            "- Detener auto-update\n"
            "- KILL ALL CUES en Avolites\n"
            "- Reset de todos los especialistas\n\n"
            "¿Continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                if hasattr(self.cue_engine, 'emergency_stop'):
                    self.cue_engine.emergency_stop()
                    QMessageBox.information(self, "Emergency", "Parada de emergencia ejecutada")
                else:
                    # Fallback manual
                    if hasattr(self.cue_engine, 'stop_auto_update'):
                        self.cue_engine.stop_auto_update()
                    
                    # Intentar kill all cues
                    if hasattr(self.cue_engine, 'av') and hasattr(self.cue_engine.av, 'kill_all_cues'):
                        self.cue_engine.av.kill_all_cues()
                    
                    QMessageBox.information(self, "Emergency", "Parada de emergencia manual ejecutada")
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error durante parada de emergencia:\n{e}")


# Factory function para main.py
def create_cue_engine_debug_widget(cue_engine, parent=None):
    """Factory function para crear el widget de debug desde main.py"""
    return CueEngineDebugWidget(cue_engine, parent)