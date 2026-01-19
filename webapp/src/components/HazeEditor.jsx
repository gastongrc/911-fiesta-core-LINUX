import React, { useState, useEffect } from 'react'
import { visionAPI } from '../api/vision'

/**
 * Haze/Smoke Detection Editor - Componente especializado para detección de humo
 */
function HazeEditor({ cameraId }) {
  const [detections, setDetections] = useState(null)

  useEffect(() => {
    const loadDetections = async () => {
      try {
        const data = await visionAPI.getDetections(cameraId, 'haze')
        setDetections(data.detections)
      } catch (error) {
        console.error('Failed to load haze detections:', error)
      }
    }

    loadDetections()
    const interval = setInterval(loadDetections, 1000)
    return () => clearInterval(interval)
  }, [cameraId])

  if (!detections) {
    return <div className="loading">Loading detections...</div>
  }

  return (
    <div style={{ padding: '1rem', background: '#1a1a1a', borderRadius: '4px' }}>
      <h4 style={{ color: '#00ff88', marginBottom: '1rem' }}>Haze/Smoke Detection</h4>

      <div style={{ fontSize: '0.875rem' }}>
        {detections.zones && detections.zones.length > 0 ? (
          detections.zones.map((zone, idx) => (
            <div key={idx} style={{ marginBottom: '1rem', paddingBottom: '1rem', borderBottom: '1px solid #333' }}>
              <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>{zone.zone_name}</div>
              <div>
                <span className={`status-badge ${zone.haze_detected ? 'status-error' : 'status-ok'}`}>
                  {zone.haze_detected ? 'HAZE DETECTED' : 'Clear'}
                </span>
              </div>
              {zone.haze_detected && (
                <div style={{ marginTop: '0.5rem' }}>
                  Level: {zone.haze_level}%
                </div>
              )}
              <div style={{ fontSize: '0.75rem', color: '#888', marginTop: '0.5rem' }}>
                Brightness: {zone.brightness?.toFixed(1)} | Contrast: {zone.contrast?.toFixed(1)}
              </div>
            </div>
          ))
        ) : (
          <div style={{ color: '#888' }}>No zones configured</div>
        )}
      </div>
    </div>
  )
}

export default HazeEditor
