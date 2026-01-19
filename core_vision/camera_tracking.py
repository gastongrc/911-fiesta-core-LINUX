"""
ArtistTracker PRO - Phase 6.4 Complete
Tracker de artista por 8 zonas horizontales del escenario
Cues: C72-C79 (T1-T8) via canonical cue_map
"""
import cv2
import numpy as np
import time
from typing import Optional, Dict, Any, TYPE_CHECKING
from collections import deque

# Canonical cue map - single source of truth
from core.cues import FAMILIA_ARTIST, ARTIST_CUE_MAP

if TYPE_CHECKING:
    from core.cues import FamilyManager


class ArtistTracker:
    """
    Tracker PRO de artista por 8 zonas horizontales.

    Responsabilidades:
    - Dividir frame en 8 zonas horizontales
    - Detectar persona principal
    - Emitir cues via FamilyManager (canonical C72-C79)
    - Cooldown y smoothing (filtro para jitter)
    - Solo activo si calendario habilita modo SHOW/ARTISTA

    Integración FamilyManager (canonical cues C72-C79):
    - C72 (T1) cuando artista en zona 1
    - C73 (T2) cuando artista en zona 2
    - ... hasta C79 (T8)

    Reglas:
    - ON/OFF
    - Si no detecta persona → cues OFF
    - Solo activo si modo SHOW/ARTISTA habilitado
    """

    def __init__(self, config, vision_state, cue_engine=None):
        """
        Inicializa el tracker de artista.

        Args:
            config (VisionConfig): Configuración del sistema
            vision_state (VisionState): Estado compartido
            cue_engine (CueEngine, optional): Motor de cues (legacy)
        """
        self.config = config
        self.vision_state = vision_state
        self.cue_engine = cue_engine

        # FamilyManager for canonical cue firing
        self._family_manager: Optional["FamilyManager"] = None

        # Cargar configuración
        tracking_config = config.get_tracking_config()
        self.enabled = tracking_config.get("enabled", False)
        self.zones_count = tracking_config.get("zones_horizontal", 8)
        self.cooldown = tracking_config.get("cooldown", 0.5)
        self.smoothing_frames = tracking_config.get("smoothing", 3)

        # Estado interno
        self.current_zone = None
        self.last_zone = None
        self.last_cue_time = 0.0
        self.current_cue = None

        # Smoothing (filtro de jitter)
        self.zone_history = deque(maxlen=self.smoothing_frames)

        # Detector de personas (HOG)
        try:
            self.hog = cv2.HOGDescriptor()
            self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self.detector_available = True
        except Exception as e:
            print(f"[ArtistTracker] HOG detector no disponible: {e}")
            self.detector_available = False

        # FIX 4: Flags para calendario
        # Se actualiza desde VisionManager.set_calendar_mode()
        self.mode_show_artist = False  # Default OFF hasta que calendario lo habilite

        # Actualizar VisionState
        self.vision_state.set_tracking_enabled(self.enabled)

        print(f"[ArtistTracker] Inicializado con {self.zones_count} zonas, enabled={self.enabled}")

    def process_frame(self, frame) -> Dict[str, Any]:
        """
        Procesa un frame para trackear artista en zonas horizontales.

        Args:
            frame: Frame de OpenCV (numpy array BGR)

        Returns:
            dict: Estado de tracking
        """
        if frame is None or not self.enabled or not self.detector_available:
            return self.get_state()

        if not self.mode_show_artist:
            # Modo calendario no permite tracking (preparado)
            return self.get_state()

        h, w = frame.shape[:2]
        zone_width = w // self.zones_count

        # Detectar personas
        detected_zone = None

        try:
            # Redimensionar frame para HOG (más rápido)
            small_frame = cv2.resize(frame, (320, 240))

            # Detectar personas
            (rects, weights) = self.hog.detectMultiScale(
                small_frame,
                winStride=(4, 4),
                padding=(8, 8),
                scale=1.05
            )

            if len(rects) > 0:
                # Escalar detecciones al tamaño original
                h_small, w_small = small_frame.shape[:2]
                scale_x = w / w_small
                scale_y = h / h_small

                # Encontrar persona principal (mayor área)
                best_person = None
                best_area = 0

                for (x, y, pw, ph), weight in zip(rects, weights):
                    area = pw * ph
                    if area > best_area:
                        best_area = area
                        best_person = (x, y, pw, ph, weight)

                if best_person:
                    x, y, pw, ph, weight = best_person

                    # Escalar coordenadas
                    x_scaled = int(x * scale_x)
                    y_scaled = int(y * scale_y)
                    w_scaled = int(pw * scale_x)
                    h_scaled = int(ph * scale_y)

                    # Centro de la persona
                    cx = x_scaled + w_scaled // 2

                    # Determinar zona horizontal (1-8)
                    detected_zone = min(self.zones_count, max(1, (cx // zone_width) + 1))

        except Exception as e:
            print(f"[ArtistTracker] Error en detección: {e}")

        # Aplicar smoothing (filtro de jitter)
        if detected_zone:
            self.zone_history.append(detected_zone)

            # Usar moda de las últimas N detecciones
            if len(self.zone_history) >= self.smoothing_frames:
                zone_counts = {}
                for z in self.zone_history:
                    zone_counts[z] = zone_counts.get(z, 0) + 1
                smoothed_zone = max(zone_counts, key=zone_counts.get)
            else:
                smoothed_zone = detected_zone

            self.current_zone = smoothed_zone
            self.vision_state.update_tracking(zone=smoothed_zone, state="tracking")

            # Disparar cue si cambió de zona (con cooldown)
            now = time.time()
            if smoothed_zone != self.last_zone and (now - self.last_cue_time) >= self.cooldown:
                self._fire_zone_cue(smoothed_zone)
                self.last_zone = smoothed_zone
                self.last_cue_time = now

        else:
            # No hay detección - edge-trigger: solo cuando cambia a None
            if self.current_zone is not None:
                self.current_zone = None
                self.last_zone = None
                self.current_cue = None
                self.vision_state.update_tracking(zone=None, state="idle")
                # OFF real via FamilyManager
                if self._family_manager:
                    self._family_manager.deactivate_family(FAMILIA_ARTIST)
                print("[ArtistTracker] No hay detección, familia ARTIST OFF")

        return self.get_state()

    def _fire_zone_cue(self, zone: int):
        """
        Dispara cue para una zona específica via FamilyManager.

        Args:
            zone: Número de zona (1-8)
        """
        # Get canonical cue from cue_map (uses int alias 1-8)
        cue = ARTIST_CUE_MAP.get(zone)
        if not cue:
            print(f"[ArtistTracker] Zona {zone} sin cue asignado")
            return

        # Fire via FamilyManager (canonical, exclusive activation)
        if self._family_manager:
            try:
                self._family_manager.activate_state(FAMILIA_ARTIST, zone)
                print(f"[ArtistTracker] FIRE C{cue} (T{zone}) via FamilyManager")
                self.current_cue = cue
            except Exception as e:
                print(f"[ArtistTracker] Error disparando cue C{cue}: {e}")

    def get_state(self) -> Dict[str, Any]:
        """
        Retorna el estado actual del tracker.

        Returns:
            dict: Estado completo
        """
        state = "disabled" if not self.enabled else ("tracking" if self.current_zone else "idle")

        return {
            "enabled": self.enabled,
            "zone": self.current_zone,
            "state": state,
            "zones_count": self.zones_count,
            "current_cue": self.current_cue,
            "mode_show_artist": self.mode_show_artist,
            "detector_available": self.detector_available,
        }

    def set_enabled(self, enabled: bool):
        """Habilita/deshabilita tracker."""
        self.enabled = enabled
        self.config.set_tracking_enabled(enabled)
        self.vision_state.set_tracking_enabled(enabled)
        print(f"[ArtistTracker] Enabled={enabled}")

    def set_mode_show_artist(self, enabled: bool):
        """
        Habilita/deshabilita modo SHOW/ARTISTA (preparado para calendario).

        Args:
            enabled: True si está en modo SHOW/ARTISTA
        """
        self.mode_show_artist = enabled
        print(f"[ArtistTracker] Modo SHOW/ARTISTA={enabled}")

    def set_cue_engine(self, cue_engine):
        """Establece el CueEngine para disparar cues (legacy)."""
        self.cue_engine = cue_engine
        print("[ArtistTracker] CueEngine conectado (legacy)")

    def set_family_manager(self, family_manager: "FamilyManager"):
        """
        Establece el FamilyManager para disparar cues canónicos.

        Args:
            family_manager: FamilyManager para activación exclusiva
        """
        self._family_manager = family_manager
        print("[ArtistTracker] FamilyManager conectado (canonical cues C72-C79)")
