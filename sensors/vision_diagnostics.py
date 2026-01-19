"""
Vision Diagnostics - Phase 6.6
Sistema de diagnóstico y monitoreo del Vision System
"""
import logging
import time
from typing import Dict, Any, List, Optional
import threading

logger = logging.getLogger(__name__)


class VisionDiagnostics:
    """
    Diagnóstico centralizado del Vision System
    """

    def __init__(self):
        self.stats = {
            'cameras': {},
            'sensors': {},
            'router': {},
            'system': {}
        }
        self.lock = threading.RLock()
        self.start_time = time.time()

        logger.info("VisionDiagnostics initialized")

    def update_camera_stats(self, camera_id: str, stats: Dict[str, Any]):
        """Actualiza estadísticas de una cámara"""
        with self.lock:
            self.stats['cameras'][camera_id] = {
                **stats,
                'last_update': time.time()
            }

    def update_sensor_stats(self, sensor_id: str, stats: Dict[str, Any]):
        """Actualiza estadísticas de un sensor"""
        with self.lock:
            self.stats['sensors'][sensor_id] = {
                **stats,
                'last_update': time.time()
            }

    def update_router_stats(self, stats: Dict[str, Any]):
        """Actualiza estadísticas del router"""
        with self.lock:
            self.stats['router'] = {
                **stats,
                'last_update': time.time()
            }

    def update_system_stats(self, stats: Dict[str, Any]):
        """Actualiza estadísticas del sistema"""
        with self.lock:
            self.stats['system'] = {
                **stats,
                'last_update': time.time()
            }

    def get_full_report(self) -> Dict[str, Any]:
        """Retorna reporte completo de diagnóstico"""
        with self.lock:
            uptime = time.time() - self.start_time

            return {
                'uptime_seconds': uptime,
                'cameras': self.stats['cameras'].copy(),
                'sensors': self.stats['sensors'].copy(),
                'router': self.stats['router'].copy(),
                'system': self.stats['system'].copy(),
                'timestamp': time.time()
            }

    def get_camera_report(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Retorna reporte de una cámara específica"""
        with self.lock:
            return self.stats['cameras'].get(camera_id, {}).copy()

    def get_sensor_report(self, sensor_id: str) -> Optional[Dict[str, Any]]:
        """Retorna reporte de un sensor específico"""
        with self.lock:
            return self.stats['sensors'].get(sensor_id, {}).copy()

    def get_health_status(self) -> Dict[str, Any]:
        """
        Retorna estado de salud del sistema
        """
        with self.lock:
            current_time = time.time()
            health = {
                'overall': 'healthy',
                'issues': [],
                'warnings': []
            }

            # Verificar cámaras
            for camera_id, cam_stats in self.stats['cameras'].items():
                last_update = cam_stats.get('last_update', 0)
                age = current_time - last_update

                if age > 5.0:  # Sin actualización en 5 segundos
                    health['issues'].append(f"Camera {camera_id} no data (last update {age:.1f}s ago)")
                    health['overall'] = 'degraded'

                error_count = cam_stats.get('error_count', 0)
                if error_count > 10:
                    health['warnings'].append(f"Camera {camera_id} has {error_count} errors")

            # Verificar sensores
            for sensor_id, sensor_stats in self.stats['sensors'].items():
                last_update = sensor_stats.get('last_update', 0)
                age = current_time - last_update

                if age > 5.0:
                    health['warnings'].append(f"Sensor {sensor_id} inactive (last update {age:.1f}s ago)")

            # Verificar router
            router_stats = self.stats.get('router', {})
            if not router_stats.get('running', False):
                health['issues'].append("Vision router not running")
                health['overall'] = 'critical'

            # Determinar estado general
            if health['issues']:
                health['overall'] = 'critical' if len(health['issues']) > 2 else 'degraded'

            return health

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Retorna métricas de rendimiento"""
        with self.lock:
            metrics = {
                'cameras': {},
                'sensors': {},
                'overall': {}
            }

            # Métricas de cámaras
            total_frames = 0
            total_errors = 0
            for camera_id, cam_stats in self.stats['cameras'].items():
                frames = cam_stats.get('frame_count', 0)
                errors = cam_stats.get('error_count', 0)
                total_frames += frames
                total_errors += errors

                metrics['cameras'][camera_id] = {
                    'frame_count': frames,
                    'error_count': errors,
                    'error_rate': errors / frames if frames > 0 else 0
                }

            # Métricas de sensores
            for sensor_id, sensor_stats in self.stats['sensors'].items():
                metrics['sensors'][sensor_id] = {
                    'frame_count': sensor_stats.get('frame_count', 0)
                }

            # Métricas generales
            uptime = time.time() - self.start_time
            metrics['overall'] = {
                'uptime_seconds': uptime,
                'total_frames_processed': total_frames,
                'total_errors': total_errors,
                'avg_fps': total_frames / uptime if uptime > 0 else 0
            }

            return metrics

    def reset_stats(self):
        """Resetea todas las estadísticas"""
        with self.lock:
            self.stats = {
                'cameras': {},
                'sensors': {},
                'router': {},
                'system': {}
            }
            self.start_time = time.time()
            logger.info("Diagnostics stats reset")

    def get_summary(self) -> str:
        """Retorna un resumen en texto del estado del sistema"""
        health = self.get_health_status()
        metrics = self.get_performance_metrics()

        lines = [
            f"Vision System Status: {health['overall'].upper()}",
            f"Uptime: {metrics['overall']['uptime_seconds']:.1f}s",
            f"Cameras: {len(self.stats['cameras'])}",
            f"Sensors: {len(self.stats['sensors'])}",
            f"Total Frames: {metrics['overall']['total_frames_processed']}",
            f"Avg FPS: {metrics['overall']['avg_fps']:.1f}",
        ]

        if health['issues']:
            lines.append("\nIssues:")
            for issue in health['issues']:
                lines.append(f"  - {issue}")

        if health['warnings']:
            lines.append("\nWarnings:")
            for warning in health['warnings']:
                lines.append(f"  - {warning}")

        return "\n".join(lines)
