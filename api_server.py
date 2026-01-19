"""
API Server - Vision System Phase 6.6
Flask API para sistema de visión
"""
import logging
import cv2
import numpy as np
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import json
import time
from typing import Dict, Any

# Imports del Vision System
from core.vision_router import VisionRouter
from core.camera_manager import CameraManager
from core.smart_camera import SmartCamera
from sensors.camera_people import CameraPeopleSensor
from sensors.camera_haze import CameraHazeSensor
from sensors.camera_tracking import CameraTrackingSensor
from sensors.vision_diagnostics import VisionDiagnostics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
CORS(app)

# Componentes del Vision System
camera_manager = CameraManager()
vision_router = VisionRouter()
people_sensor = CameraPeopleSensor()
haze_sensor = CameraHazeSensor()
tracking_sensor = CameraTrackingSensor()
diagnostics = VisionDiagnostics()

# Registrar sensores en el router
vision_router.register_sensor('people', people_sensor)
vision_router.register_sensor('haze', haze_sensor)
vision_router.register_sensor('tracking', tracking_sensor)


# ============================================================================
# ENDPOINTS DE VISIÓN
# ============================================================================

@app.route('/vision/status', methods=['GET'])
def vision_status():
    """Retorna el estado del sistema de visión"""
    try:
        router_status = vision_router.get_status()
        camera_status = camera_manager.get_status()
        health = diagnostics.get_health_status()
        metrics = diagnostics.get_performance_metrics()

        return jsonify({
            'status': 'ok',
            'router': router_status,
            'cameras': camera_status,
            'health': health,
            'metrics': metrics
        })
    except Exception as e:
        logger.error(f"Error in /vision/status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/vision/frame/<camera_id>', methods=['GET'])
def vision_frame(camera_id: str):
    """Retorna el último frame de una cámara (JPEG)"""
    try:
        camera = camera_manager.get_camera(camera_id)
        if not camera:
            return jsonify({'error': f'Camera {camera_id} not found'}), 404

        frame = camera.get_frame()
        if frame is None:
            return jsonify({'error': 'No frame available'}), 404

        # Anotar frame con detecciones si se solicita
        annotate = request.args.get('annotate', 'false').lower() == 'true'
        sensor_type = request.args.get('sensor', 'people')

        if annotate:
            if sensor_type == 'people':
                frame = people_sensor.get_annotated_frame(frame, camera_id)
            elif sensor_type == 'haze':
                frame = haze_sensor.get_annotated_frame(frame, camera_id)
            elif sensor_type == 'tracking':
                frame = tracking_sensor.get_annotated_frame(frame, camera_id)

        # Convertir a JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        jpeg = buffer.tobytes()

        return Response(jpeg, mimetype='image/jpeg')

    except Exception as e:
        logger.error(f"Error in /vision/frame/{camera_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/vision/zones/<camera_id>', methods=['GET'])
def get_zones(camera_id: str):
    """Retorna las zonas configuradas para una cámara"""
    try:
        sensor_type = request.args.get('sensor', 'people')

        zones = []
        if sensor_type == 'people':
            zones = people_sensor.get_zones(camera_id)
        elif sensor_type == 'haze':
            zones = haze_sensor.get_zones(camera_id)
        elif sensor_type == 'tracking':
            zones = tracking_sensor.get_zones(camera_id)

        return jsonify({
            'camera_id': camera_id,
            'sensor': sensor_type,
            'zones': zones
        })

    except Exception as e:
        logger.error(f"Error in GET /vision/zones/{camera_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/vision/zones/<camera_id>', methods=['POST'])
def set_zones(camera_id: str):
    """Configura las zonas para una cámara"""
    try:
        data = request.get_json()
        sensor_type = data.get('sensor', 'people')
        zones = data.get('zones', [])

        if sensor_type == 'people':
            people_sensor.set_zones(camera_id, zones)
            # Crear ruta en el router
            vision_router.add_route(camera_id, 'people')
        elif sensor_type == 'haze':
            haze_sensor.set_zones(camera_id, zones)
            vision_router.add_route(camera_id, 'haze')
        elif sensor_type == 'tracking':
            tracking_sensor.set_zones(camera_id, zones)
            vision_router.add_route(camera_id, 'tracking')

        return jsonify({
            'status': 'ok',
            'camera_id': camera_id,
            'sensor': sensor_type,
            'zones_count': len(zones)
        })

    except Exception as e:
        logger.error(f"Error in POST /vision/zones/{camera_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/vision/devices', methods=['GET'])
def list_devices():
    """Lista dispositivos de video disponibles"""
    try:
        devices = camera_manager.list_available_devices()
        return jsonify({
            'devices': devices,
            'count': len(devices)
        })
    except Exception as e:
        logger.error(f"Error in /vision/devices: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/vision/camera/<camera_id>/start', methods=['POST'])
def start_camera(camera_id: str):
    """Inicia una cámara"""
    try:
        data = request.get_json() or {}
        device_id = data.get('device_id', 0)
        resolution = data.get('resolution', [640, 480])
        fps = data.get('fps', 30)

        # Crear y arrancar cámara
        camera = SmartCamera(device_id, tuple(resolution), fps)
        if camera.start():
            camera_manager.add_camera(camera_id, camera, data)
            vision_router.register_camera(camera_id, camera)

            return jsonify({
                'status': 'ok',
                'camera_id': camera_id,
                'device_id': device_id
            })
        else:
            return jsonify({'error': 'Failed to start camera'}), 500

    except Exception as e:
        logger.error(f"Error in /vision/camera/{camera_id}/start: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/vision/camera/<camera_id>/stop', methods=['POST'])
def stop_camera(camera_id: str):
    """Detiene una cámara"""
    try:
        camera_manager.remove_camera(camera_id)
        return jsonify({
            'status': 'ok',
            'camera_id': camera_id
        })
    except Exception as e:
        logger.error(f"Error in /vision/camera/{camera_id}/stop: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/vision/detections/<camera_id>', methods=['GET'])
def get_detections(camera_id: str):
    """Retorna detecciones actuales para una cámara"""
    try:
        sensor_type = request.args.get('sensor', 'people')

        detections = None
        if sensor_type == 'people':
            detections = people_sensor.get_detections(camera_id)
        elif sensor_type == 'haze':
            detections = haze_sensor.get_detections(camera_id)
        elif sensor_type == 'tracking':
            detections = tracking_sensor.get_detections(camera_id)

        return jsonify({
            'camera_id': camera_id,
            'sensor': sensor_type,
            'detections': detections or {}
        })

    except Exception as e:
        logger.error(f"Error in /vision/detections/{camera_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'vision-api'})


# ============================================================================
# INICIALIZACIÓN
# ============================================================================

def init_vision_system():
    """Inicializa el sistema de visión"""
    try:
        # Iniciar router
        vision_router.start()
        logger.info("Vision system initialized")
    except Exception as e:
        logger.error(f"Error initializing vision system: {e}", exc_info=True)


def shutdown_vision_system():
    """Apaga el sistema de visión"""
    try:
        vision_router.stop()
        camera_manager.stop_all()
        logger.info("Vision system shutdown")
    except Exception as e:
        logger.error(f"Error shutting down vision system: {e}", exc_info=True)


if __name__ == '__main__':
    init_vision_system()
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    finally:
        shutdown_vision_system()
