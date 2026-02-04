/**
 * Vision V7 - Camera Reference View (NEON UI)
 *
 * SOLO REFERENCIA - No edición, no disparos
 *
 * Muestra:
 * - Estado de cada cámara (haze, people, tracking)
 * - Overlay zonas (visual)
 * - Estado ON/OFF
 * - FPS
 */
import { useEffect, useState } from 'react';
import { getApiBase } from '../lib/apiBase';

// Tipos de cámara
const CAMERA_TYPES = [
  { id: 'haze', name: 'HAZE DETECTION', desc: 'Detección de humo' },
  { id: 'people', name: 'PEOPLE COUNTER', desc: 'Contador de personas' },
  { id: 'tracking', name: 'DJ TRACKING', desc: 'Seguimiento DJ' },
];

// Card de cámara NEON con preview real
function CameraCard({ type, cameraData }) {
  const isOnline = cameraData?.online || false;
  const fps = cameraData?.fps || 0;
  const [frameError, setFrameError] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // Frame URL via API proxy (no directo a Flask)
  const frameUrl = `${getApiBase()}/vision/frame/${type.id}?t=${refreshKey}`;

  // Refrescar frame cada 2 segundos si está online
  useEffect(() => {
    if (!isOnline) return;
    const interval = setInterval(() => {
      setRefreshKey(k => k + 1);
      setFrameError(false);
    }, 2000);
    return () => clearInterval(interval);
  }, [isOnline]);

  return (
    <div className={`neon-panel ${isOnline ? '' : 'error'}`} style={{
      borderColor: isOnline ? 'var(--neon-green)' : 'var(--neon-red)',
    }}>
      <div className="neon-panel-header">
        <span className="neon-panel-title">{type.name}</span>
        <span className={`neon-badge ${isOnline ? 'neon-badge-ok' : 'neon-badge-error'}`}>
          {isOnline ? 'ONLINE' : 'OFFLINE'}
        </span>
      </div>
      <div className="neon-panel-content">
        {/* Frame preview */}
        <div style={{
          background: 'var(--bg-dark)',
          borderRadius: '6px',
          aspectRatio: '16/9',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '12px',
          border: `1px solid ${isOnline ? 'var(--neon-green)' : 'var(--neon-red)'}40`,
          overflow: 'hidden',
        }}>
          {isOnline && !frameError ? (
            <img
              src={frameUrl}
              alt={type.name}
              onError={() => setFrameError(true)}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />
          ) : isOnline && frameError ? (
            <div style={{ textAlign: 'center' }}>
              <div style={{
                width: '50px',
                height: '50px',
                borderRadius: '50%',
                background: 'rgba(255, 136, 0, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 8px',
                border: '1px solid var(--neon-orange)',
              }}>
                <span style={{ fontSize: '24px' }}>📹</span>
              </div>
              <p style={{ color: 'var(--neon-orange)', fontSize: '10px' }}>
                Frame no disponible
              </p>
            </div>
          ) : (
            <div style={{ textAlign: 'center' }}>
              <div style={{
                width: '50px',
                height: '50px',
                borderRadius: '50%',
                background: 'rgba(255, 68, 68, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 8px',
                border: '1px solid var(--neon-red)',
              }}>
                <span style={{ fontSize: '24px', filter: 'grayscale(1)' }}>📹</span>
              </div>
              <p style={{ color: 'var(--neon-red)', fontSize: '10px', fontWeight: 'bold' }}>
                OFFLINE
              </p>
            </div>
          )}
        </div>

        {/* Info */}
        <div className="neon-indicator">
          <span className="neon-indicator-label">Estado</span>
          <span className={`neon-indicator-value ${isOnline ? 'ok' : 'error'}`}>
            {isOnline ? 'Running' : 'Stopped'}
          </span>
        </div>
        <div className="neon-indicator">
          <span className="neon-indicator-label">FPS</span>
          <span className={`neon-indicator-value ${fps > 0 ? 'ok' : 'error'}`}>
            {fps > 0 ? fps : '---'}
          </span>
        </div>
        <div className="neon-indicator">
          <span className="neon-indicator-label">Tipo</span>
          <span className="neon-indicator-value">{type.desc}</span>
        </div>

        {/* Zonas */}
        <div style={{
          marginTop: '12px',
          padding: '8px',
          background: 'rgba(0, 255, 255, 0.05)',
          borderRadius: '4px',
          border: '1px solid rgba(0, 255, 255, 0.2)',
        }}>
          <span style={{ color: 'var(--neon-cyan)', fontSize: '9px' }}>
            Zonas configuradas via Qt UI
          </span>
        </div>
      </div>
    </div>
  );
}

// Página principal
export function Vision() {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [apiOffline, setApiOffline] = useState(false);

  // Cargar estado
  useEffect(() => {
    const fetchCameras = async () => {
      try {
        const res = await fetch(`${getApiBase()}/status/unified`);
        if (res.ok) {
          const data = await res.json();
          setCameras(data.cameras || []);
          setApiOffline(false);
        } else {
          setApiOffline(true);
        }
      } catch (e) {
        setApiOffline(true);
      }
      setLoading(false);
    };
    fetchCameras();
    const interval = setInterval(fetchCameras, 5000);
    return () => clearInterval(interval);
  }, []);

  // Obtener datos por ID
  const getCameraData = (id) => cameras.find(c => c.name === id) || null;

  const onlineCount = cameras.filter(c => c.online).length;
  const totalCount = cameras.length || CAMERA_TYPES.length;

  return (
    <div style={{ padding: '16px' }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '20px',
      }}>
        <h2 style={{
          color: 'var(--neon-cyan)',
          fontSize: '18px',
          fontWeight: 'bold',
          margin: 0,
          textShadow: '0 0 10px var(--neon-cyan)',
          letterSpacing: '2px',
        }}>
          VISION SYSTEM
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span className={`neon-badge ${onlineCount > 0 ? 'neon-badge-ok' : 'neon-badge-error'}`}>
            {onlineCount}/{totalCount} ONLINE
          </span>
          {loading && (
            <span style={{ color: 'var(--neon-cyan)', fontSize: '10px' }}>Cargando...</span>
          )}
        </div>
      </div>

      {/* API Offline */}
      {apiOffline && (
        <div style={{
          background: 'rgba(255, 68, 68, 0.1)',
          border: '1px solid var(--neon-red)',
          borderRadius: '6px',
          padding: '12px',
          marginBottom: '16px',
          textAlign: 'center',
        }}>
          <span style={{ color: 'var(--neon-red)', fontSize: '12px', fontWeight: 'bold' }}>
            ⚠ API OFFLINE
          </span>
        </div>
      )}

      {/* Banner info */}
      <div style={{
        background: 'rgba(0, 255, 255, 0.05)',
        border: '1px solid rgba(0, 255, 255, 0.3)',
        borderRadius: '6px',
        padding: '12px',
        marginBottom: '16px',
      }}>
        <p style={{ color: 'var(--neon-cyan)', fontSize: '11px', margin: 0, textAlign: 'center' }}>
          Vision es <strong>SOLO REFERENCIA</strong> en Control Room.
          Para edición de zonas y configuración, usar Qt UI.
        </p>
      </div>

      {/* Grid de cámaras */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '12px',
        marginBottom: '16px',
      }}>
        {CAMERA_TYPES.map(type => (
          <CameraCard
            key={type.id}
            type={type}
            cameraData={getCameraData(type.id)}
          />
        ))}
      </div>

      {/* Footer info */}
      <div className="neon-panel">
        <div className="neon-panel-header">
          <span className="neon-panel-title">VISION API PROXY</span>
        </div>
        <div className="neon-panel-content">
          <div style={{ color: 'var(--text-dim)', fontSize: '10px' }}>
            <p style={{ margin: '4px 0' }}>Proxy: <span style={{ color: 'var(--neon-cyan)' }}>/api/v1/vision/*</span></p>
            <p style={{ margin: '4px 0' }}>Backend: <span style={{ color: 'var(--text-muted)' }}>Flask 5000</span></p>
            <p style={{ margin: '8px 0 4px', color: 'var(--text-muted)' }}>Endpoints:</p>
            <ul style={{ margin: '4px 0 0 16px', padding: 0, listStyleType: 'none' }}>
              <li style={{ margin: '2px 0' }}>• /api/v1/vision/status</li>
              <li style={{ margin: '2px 0' }}>• /api/v1/vision/frame/&lt;haze|people|tracking&gt;</li>
              <li style={{ margin: '2px 0' }}>• /api/v1/vision/stream/&lt;id&gt;</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
