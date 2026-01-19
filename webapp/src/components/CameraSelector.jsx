import React from 'react'

function CameraSelector({ selectedCamera, selectedSensor, onCameraChange, onSensorChange, status }) {
  const cameras = status?.cameras || {}
  const cameraIds = Object.keys(cameras)

  const sensors = [
    { id: 'people', name: 'People Detection' },
    { id: 'haze', name: 'Haze/Smoke Detection' },
    { id: 'tracking', name: 'Motion Tracking' }
  ]

  return (
    <div className="camera-selector">
      <div className="property-group">
        <label>Camera</label>
        <select
          value={selectedCamera || ''}
          onChange={(e) => onCameraChange(e.target.value)}
        >
          <option value="">-- Select Camera --</option>
          {cameraIds.map((cameraId) => {
            const camera = cameras[cameraId]
            const isActive = camera?.active || false
            return (
              <option key={cameraId} value={cameraId}>
                {cameraId} {isActive ? '(active)' : '(inactive)'}
              </option>
            )
          })}
        </select>
      </div>

      {selectedCamera && (
        <div className="property-group">
          <label>Sensor Type</label>
          <select
            value={selectedSensor}
            onChange={(e) => onSensorChange(e.target.value)}
          >
            {sensors.map((sensor) => (
              <option key={sensor.id} value={sensor.id}>
                {sensor.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {status && (
        <div style={{ fontSize: '0.75rem', color: '#888', marginTop: '1rem' }}>
          <div>Cameras: {cameraIds.length}</div>
          <div>Router: {status.router?.running ? 'Running' : 'Stopped'}</div>
        </div>
      )}
    </div>
  )
}

export default CameraSelector
