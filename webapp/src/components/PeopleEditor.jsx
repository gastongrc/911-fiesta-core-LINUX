import React, { useState, useEffect } from 'react'
import { visionAPI } from '../api/vision'

/**
 * People Detection Editor - Componente especializado para detección de personas
 */
function PeopleEditor({ cameraId }) {
  const [detections, setDetections] = useState(null)

  useEffect(() => {
    const loadDetections = async () => {
      try {
        const data = await visionAPI.getDetections(cameraId, 'people')
        setDetections(data.detections)
      } catch (error) {
        console.error('Failed to load people detections:', error)
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
      <h4 style={{ color: '#00ff88', marginBottom: '1rem' }}>People Detection</h4>

      <div style={{ fontSize: '0.875rem' }}>
        <div style={{ marginBottom: '0.5rem' }}>
          <strong>Total People:</strong> {detections.total_people || 0}
        </div>

        {detections.zones && detections.zones.length > 0 && (
          <div>
            <strong>Zones:</strong>
            {detections.zones.map((zone, idx) => (
              <div key={idx} style={{ marginLeft: '1rem', marginTop: '0.5rem' }}>
                <div>{zone.zone_name}: {zone.people_count} people</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default PeopleEditor
