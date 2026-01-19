import React, { useState, useEffect } from 'react'

function ZoneProperties({ zone, sensor, onUpdate, onDelete }) {
  const [name, setName] = useState(zone.name)
  const [enabled, setEnabled] = useState(zone.enabled)
  const [sensitivity, setSensitivity] = useState(zone.sensitivity || 1.0)

  useEffect(() => {
    setName(zone.name)
    setEnabled(zone.enabled)
    setSensitivity(zone.sensitivity || 1.0)
  }, [zone])

  const handleSave = () => {
    onUpdate({
      ...zone,
      name,
      enabled,
      sensitivity: parseFloat(sensitivity)
    })
  }

  const handleDelete = () => {
    onDelete(zone.id)
  }

  return (
    <div className="zone-properties">
      <h4 style={{ color: '#00ff88', marginBottom: '1rem' }}>Zone Properties</h4>

      <div className="property-group">
        <label>Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>

      <div className="property-group">
        <label>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            style={{ width: 'auto', marginRight: '0.5rem' }}
          />
          Enabled
        </label>
      </div>

      {(sensor === 'haze' || sensor === 'tracking') && (
        <div className="property-group">
          <label>Sensitivity</label>
          <input
            type="number"
            min="0.1"
            max="5"
            step="0.1"
            value={sensitivity}
            onChange={(e) => setSensitivity(e.target.value)}
          />
          <small style={{ color: '#888', fontSize: '0.75rem' }}>
            {sensor === 'haze' ? 'Lower = more sensitive to haze' : 'Lower = more sensitive to motion'}
          </small>
        </div>
      )}

      <div className="property-group">
        <label>Points</label>
        <div style={{ fontSize: '0.875rem', color: '#888' }}>
          {zone.points?.length || 0} points defined
        </div>
      </div>

      <div className="btn-group">
        <button className="btn btn-primary" onClick={handleSave}>
          Save Changes
        </button>
        <button className="btn btn-danger" onClick={handleDelete}>
          Delete Zone
        </button>
      </div>
    </div>
  )
}

export default ZoneProperties
