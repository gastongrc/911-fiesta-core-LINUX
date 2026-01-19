"""
Artist Tracker - Phase 6 REAL Core Integration
Tracker de artista por zonas horizontales del escenario
"""


class ArtistTracker:
    """
    Tracker REAL de artista por zonas horizontales.

    Responsabilidades:
    - Trackear posición del artista en el escenario
    - Dividir escenario en zonas (izquierda/centro/derecha)
    - Detectar movimiento entre zonas
    - Generar triggers cuando artista cambia de zona

    Integración:
    - Reporta zona actual a StateManager
    - Puede disparar cues específicos por zona
    - Usa optical flow o tracking de personas
    - Configurable desde vision_config.json
    """

    def __init__(self, config):
        """
        Inicializa el tracker de artista.

        Args:
            config (VisionConfig): Configuración de zonas horizontales
        """
        pass

    def process_frame(self, frame):
        """
        Procesa un frame para trackear artista.

        Args:
            frame: Frame de OpenCV (numpy array)

        Returns:
            dict: Estado de tracking {
                'artist_detected': bool,
                'current_zone': str ('left'/'center'/'right'),
                'confidence': float (0-1),
                'movement': str ('static'/'moving')
            }
        """
        pass

    def get_state(self):
        """
        Retorna el estado actual del tracker.

        Returns:
            dict: Estado para integración con StateManager
        """
        pass
