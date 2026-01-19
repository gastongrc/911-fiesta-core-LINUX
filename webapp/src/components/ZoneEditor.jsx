import React, { useState, useEffect } from 'react'
import { visionAPI } from '../api/vision'
import ZoneProperties from './ZoneProperties'

function ZoneEditor({ cameraId, sensor }) {
  const [zones, setZones] = useState([])
  const [selectedZone, setSelectedZone] = useState(null)

  useEffect(() => {
    loadZones()
  }, [cameraId, sensor])

  const loadZones = async () => {
    try {
      const data = await visionAPI.getZones(cameraId, sensor)
      setZones(data.zones || [])
      setSelectedZone(null)
    } catch (error) {
      console.error('Failed to load zones:', error)
    }
  }

  const handleZoneSelect = (zone) => {
    setSelectedZone(zone)
  }

  const handleZoneUpdate = async (updatedZone) => {
    const updatedZones = zones.map((z) =>
      z.id === updatedZone.id ? updatedZone : z
    )

    try {
      await visionAPI.setZones(cameraId, sensor, updatedZones)
      setZones(updatedZones)
      setSelectedZone(updatedZone)
    } catch (error) {
      console.error('Failed to update zone:', error)
      alert('Failed to update zone')
    }
  }

  const handleZoneDelete = async (zoneId) => {
    if (!confirm('Delete this zone?')) return

    const updatedZones = zones.filter((z) => z.id !== zoneId)

    try {
      await visionAPI.setZones(cameraId, sensor, updatedZones)
      setZones(updatedZones)
      setSelectedZone(null)
    } catch (error) {
      console.error('Failed to delete zone:', error)
      alert('Failed to delete zone')
    }
  }

  return (
    <div className="zone-editor">
      <h3 style={{ color: '#00ff88', marginBottom: '0.5rem' }}>Zones</h3>

      <div className="zone-list">
        {zones.length === 0 ? (
          <div style={{ color: '#888', fontSize: '0.875rem', padding: '1rem', textAlign: 'center' }}>
            No zones defined
          </div>
        ) : (
          zones.map((zone) => (
            <div
              key={zone.id}
              className={`zone-item ${selectedZone?.id === zone.id ? 'active' : ''} ${!zone.enabled ? 'disabled' : ''}`}
              onClick={() => handleZoneSelect(zone)}
            >
              <div style={{ fontWeight: 'bold' }}>{zone.name}</div>
              <div style={{ fontSize: '0.75rem', color: '#888' }}>
                {zone.points?.length || 0} points
                {!zone.enabled && ' (disabled)'}
              </div>
            </div>
          ))
        )}
      </div>

      {selectedZone && (
        <ZoneProperties
          zone={selectedZone}
          sensor={sensor}
          onUpdate={handleZoneUpdate}
          onDelete={handleZoneDelete}
        />
      )}
    </div>
  )
}

export default ZoneEditor
