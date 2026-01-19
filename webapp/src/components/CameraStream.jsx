import React, { useRef, useEffect, useState } from 'react'
import { visionAPI } from '../api/vision'

function CameraStream({ cameraId, sensor }) {
  const canvasRef = useRef(null)
  const imageRef = useRef(null)
  const [zones, setZones] = useState([])
  const [currentZone, setCurrentZone] = useState([])
  const [isDrawing, setIsDrawing] = useState(false)

  useEffect(() => {
    loadZones()
    startStream()
  }, [cameraId, sensor])

  const loadZones = async () => {
    try {
      const data = await visionAPI.getZones(cameraId, sensor)
      setZones(data.zones || [])
    } catch (error) {
      console.error('Failed to load zones:', error)
    }
  }

  const startStream = () => {
    if (!imageRef.current) return

    const updateFrame = () => {
      if (imageRef.current) {
        imageRef.current.src = visionAPI.getFrameUrl(cameraId, false, sensor)
      }
    }

    // Actualizar frame cada 100ms
    const interval = setInterval(updateFrame, 100)
    return () => clearInterval(interval)
  }

  const handleImageLoad = () => {
    drawCanvas()
  }

  const drawCanvas = () => {
    const canvas = canvasRef.current
    const image = imageRef.current
    if (!canvas || !image) return

    const ctx = canvas.getContext('2d')
    canvas.width = image.naturalWidth
    canvas.height = image.naturalHeight

    // Dibujar imagen
    ctx.drawImage(image, 0, 0)

    // Dibujar zonas guardadas
    zones.forEach((zone) => {
      if (!zone.enabled) return
      drawZone(ctx, zone.points, '#00ff88', zone.name)
    })

    // Dibujar zona en construcción
    if (currentZone.length > 0) {
      drawZone(ctx, currentZone, '#ff8800', 'New Zone', true)
    }
  }

  const drawZone = (ctx, points, color, label, partial = false) => {
    if (points.length === 0) return

    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.fillStyle = color + '33'

    ctx.beginPath()
    ctx.moveTo(points[0][0], points[0][1])
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i][0], points[i][1])
    }
    if (!partial) {
      ctx.closePath()
      ctx.fill()
    }
    ctx.stroke()

    // Dibujar puntos
    points.forEach((point) => {
      ctx.fillStyle = color
      ctx.beginPath()
      ctx.arc(point[0], point[1], 4, 0, 2 * Math.PI)
      ctx.fill()
    })

    // Label
    if (points.length > 0) {
      ctx.fillStyle = color
      ctx.font = '14px sans-serif'
      ctx.fillText(label, points[0][0] + 5, points[0][1] - 5)
    }
  }

  const handleCanvasClick = (e) => {
    if (!isDrawing) return

    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height

    const x = (e.clientX - rect.left) * scaleX
    const y = (e.clientY - rect.top) * scaleY

    setCurrentZone([...currentZone, [Math.round(x), Math.round(y)]])
  }

  const handleStartDrawing = () => {
    setIsDrawing(true)
    setCurrentZone([])
  }

  const handleFinishZone = async () => {
    if (currentZone.length < 3) {
      alert('Zone must have at least 3 points')
      return
    }

    const newZone = {
      id: `zone_${Date.now()}`,
      name: `Zone ${zones.length + 1}`,
      points: currentZone,
      enabled: true,
      sensitivity: 1.0
    }

    const updatedZones = [...zones, newZone]

    try {
      await visionAPI.setZones(cameraId, sensor, updatedZones)
      setZones(updatedZones)
      setCurrentZone([])
      setIsDrawing(false)
    } catch (error) {
      console.error('Failed to save zone:', error)
      alert('Failed to save zone')
    }
  }

  const handleCancelDrawing = () => {
    setCurrentZone([])
    setIsDrawing(false)
  }

  useEffect(() => {
    drawCanvas()
  }, [zones, currentZone])

  return (
    <div className="camera-stream">
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
        {!isDrawing ? (
          <button className="btn btn-primary" onClick={handleStartDrawing}>
            Draw New Zone
          </button>
        ) : (
          <>
            <button className="btn btn-primary" onClick={handleFinishZone}>
              Finish Zone ({currentZone.length} points)
            </button>
            <button className="btn btn-secondary" onClick={handleCancelDrawing}>
              Cancel
            </button>
          </>
        )}
      </div>

      <div className="stream-container">
        <img
          ref={imageRef}
          onLoad={handleImageLoad}
          style={{ display: 'none' }}
          alt="camera feed"
        />
        <canvas
          ref={canvasRef}
          className="stream-canvas"
          onClick={handleCanvasClick}
          style={{ cursor: isDrawing ? 'crosshair' : 'default' }}
        />
      </div>
    </div>
  )
}

export default CameraStream
