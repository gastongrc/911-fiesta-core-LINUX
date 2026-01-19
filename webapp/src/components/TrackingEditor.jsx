import React, { useState, useEffect } from 'react'
import { visionAPI } from '../api/vision'

/**
 * Motion Tracking Editor - Componente especializado para tracking de movimiento
 */
function TrackingEditor({ cameraId }) {
  const [detections, setDetections] = useState(null)

  useEffect(() => {
    const loadDetections = async () => {
      try {
        const data = await visionAPI.getDetections(cameraId, 'tracking')
        setDetections(data.detections)
      } catch (error) {
        console.error('Failed to load tracking detections:', error)
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
      <h4 style={{ color: '#00ff88', marginBottom: '1rem' }}>Motion Tracking</h4>

      <div style={{ fontSize: '0.875rem' }}>
        {detections.zones && detections.zones.length > 0 ? (
          detections.zones.map((zone, idx) => (
            <div key={idx} style={{ marginBottom: '1rem', paddingBottom: '1rem', borderBottom: '1px solid #333' }}>
              <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>{zone.zone_name}</div>
              <div>
                <span className={`status-badge ${zone.motion_detected ? 'status-warning' : 'status-ok'}`}>
                  {zone.motion_detected ? 'MOTION DETECTED' : 'No Motion'}
                </span>
              </div>
              {zone.motion_detected && (
                <>
                  <div style={{ marginTop: '0.5rem' }}>
                    Level: {zone.motion_level}%
                  </div>
                  <div style={{ marginTop: '0.25rem' }}>
                    Direction: {zone.direction}
                  </div>
                </>
              )}
              <div style={{ fontSize: '0.75rem', color: '#888', marginTop: '0.5rem' }}>
                Mean: {zone.mean_motion?.toFixed(2)} | Max: {zone.max_motion?.toFixed(2)}
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

export default TrackingEditor
