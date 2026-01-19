import React, { useState, useEffect } from 'react'
import CameraSelector from './components/CameraSelector'
import CameraStream from './components/CameraStream'
import ZoneEditor from './components/ZoneEditor'
import { visionAPI } from './api/vision'

function App() {
  const [selectedCamera, setSelectedCamera] = useState(null)
  const [selectedSensor, setSelectedSensor] = useState('people')
  const [status, setStatus] = useState(null)

  useEffect(() => {
    // Cargar estado inicial
    loadStatus()

    // Actualizar estado cada 2 segundos
    const interval = setInterval(loadStatus, 2000)
    return () => clearInterval(interval)
  }, [])

  const loadStatus = async () => {
    try {
      const data = await visionAPI.getStatus()
      setStatus(data)
    } catch (error) {
      console.error('Failed to load status:', error)
    }
  }

  const handleCameraChange = (cameraId) => {
    setSelectedCamera(cameraId)
  }

  const handleSensorChange = (sensor) => {
    setSelectedSensor(sensor)
  }

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>911 Fiesta - Vision System Phase 7</h1>
        {status && (
          <span className={`status-badge status-${status.health?.overall === 'healthy' ? 'ok' : 'error'}`}>
            {status.health?.overall || 'unknown'}
          </span>
        )}
      </header>

      <main className="app-main">
        <aside className="app-sidebar">
          <CameraSelector
            selectedCamera={selectedCamera}
            selectedSensor={selectedSensor}
            onCameraChange={handleCameraChange}
            onSensorChange={handleSensorChange}
            status={status}
          />

          {selectedCamera && (
            <ZoneEditor
              cameraId={selectedCamera}
              sensor={selectedSensor}
            />
          )}
        </aside>

        <div className="app-content">
          {selectedCamera ? (
            <CameraStream
              cameraId={selectedCamera}
              sensor={selectedSensor}
            />
          ) : (
            <div className="loading">
              Select a camera to begin
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
