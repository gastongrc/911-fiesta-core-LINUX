/**
 * Vision V7 - Camera Reference View (Estilo Industrial)
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

const API_BASE = '/api/v1';

// Tipos de cámara
const CAMERA_TYPES = [
  { id: 'haze', name: 'HAZE DETECTION', desc: 'Detección de humo' },
  { id: 'people', name: 'PEOPLE COUNTER', desc: 'Contador de personas' },
  { id: 'tracking', name: 'DJ TRACKING', desc: 'Seguimiento DJ' },
];

// Panel industrial
function Panel({ title, status, statusColor, children }) {
  return (
    <div style={{
      background: '#1e272e',
      borderRadius: '8px',
      border: '1px solid #34495e',
      overflow: 'hidden',
    }}>
      <div style={{
        background: '#2c3e50',
        padding: '10px 12px',
        borderBottom: '1px solid #34495e',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ color: '#ecf0f1', fontSize: '11px', fontWeight: 'bold' }}>
          {title}
        </span>
        {status && (
          <span style={{
            color: statusColor || '#2ecc71',
            fontSize: '9px',
            fontWeight: 'bold',
            background: `${statusColor || '#2ecc71'}20`,
            padding: '2px 8px',
            borderRadius: '4px',
          }}>
            {status}
          </span>
        )}
      </div>
      <div style={{ padding: '12px' }}>
        {children}
      </div>
    </div>
  );
}

// Indicador
function Indicator({ label, value, ok }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '4px 0',
    }}>
      <span style={{ color: '#7f8c8d', fontSize: '10px' }}>{label}</span>
      <span style={{
        color: ok === true ? '#2ecc71' : ok === false ? '#e74c3c' : '#ecf0f1',
        fontSize: '10px',
        fontWeight: 'bold',
      }}>
        {value}
      </span>
    </div>
  );
}

// Card de cámara
function CameraCard({ type, cameraData }) {
  const isOnline = cameraData?.online || false;
  const fps = cameraData?.fps || 0;

  return (
    <Panel
      title={type.name}
      status={isOnline ? 'ONLINE' : 'OFFLINE'}
      statusColor={isOnline ? '#2ecc71' : '#e74c3c'}
    >
      {/* Stream placeholder */}
      <div style={{
        background: '#1a1a2e',
        borderRadius: '6px',
        aspectRatio: '16/9',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: '12px',
        border: '1px solid #34495e',
      }}>
        {isOnline ? (
          <div style={{ textAlign: 'center' }}>
            <div style={{
              width: '50px',
              height: '50px',
              borderRadius: '50%',
              background: 'rgba(46,204,113,0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 8px',
            }}>
              <span style={{ fontSize: '24px' }}>📹</span>
            </div>
            <p style={{ color: '#7f8c8d', fontSize: '10px' }}>
              Stream via Flask Vision
            </p>
            <p style={{ color: '#95a5a6', fontSize: '9px' }}>
              localhost:5000
            </p>
          </div>
        ) : (
          <div style={{ textAlign: 'center' }}>
            <div style={{
              width: '50px',
              height: '50px',
              borderRadius: '50%',
              background: 'rgba(231,76,60,0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 8px',
            }}>
              <span style={{ fontSize: '24px', filter: 'grayscale(1)' }}>📹</span>
            </div>
            <p style={{ color: '#e74c3c', fontSize: '10px', fontWeight: 'bold' }}>
              OFFLINE
            </p>
          </div>
        )}
      </div>

      {/* Info */}
      <Indicator label="Estado" value={isOnline ? 'Running' : 'Stopped'} ok={isOnline} />
      <Indicator label="FPS" value={fps > 0 ? fps : '---'} ok={fps > 0} />
      <Indicator label="Tipo" value={type.desc} />

      {/* Zonas overlay (visual) */}
      <div style={{
        marginTop: '8px',
        padding: '6px',
        background: 'rgba(52,152,219,0.1)',
        borderRadius: '4px',
        border: '1px solid rgba(52,152,219,0.3)',
      }}>
        <span style={{ color: '#3498db', fontSize: '9px' }}>
          Zonas configuradas via Qt UI
        </span>
      </div>
    </Panel>
  );
}

// Página principal
export function Vision() {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);

  // Cargar estado
  useEffect(() => {
    const fetchCameras = async () => {
      try {
        const res = await fetch(`${API_BASE}/status/unified`);
        if (res.ok) {
          const data = await res.json();
          setCameras(data.cameras || []);
        }
      } catch (e) {}
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
        marginBottom: '16px',
      }}>
        <h2 style={{ color: '#ecf0f1', fontSize: '18px', fontWeight: 'bold', margin: 0 }}>
          VISION SYSTEM
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{
            color: onlineCount > 0 ? '#2ecc71' : '#e74c3c',
            fontSize: '10px',
            fontWeight: 'bold',
            background: onlineCount > 0 ? 'rgba(46,204,113,0.2)' : 'rgba(231,76,60,0.2)',
            padding: '4px 8px',
            borderRadius: '4px',
          }}>
            {onlineCount}/{totalCount} ONLINE
          </span>
          {loading && (
            <span style={{ color: '#3498db', fontSize: '10px' }}>Cargando...</span>
          )}
        </div>
      </div>

      {/* Banner info */}
      <div style={{
        background: 'rgba(52,152,219,0.1)',
        border: '1px solid rgba(52,152,219,0.3)',
        borderRadius: '6px',
        padding: '10px 12px',
        marginBottom: '16px',
      }}>
        <p style={{ color: '#3498db', fontSize: '10px', margin: 0, textAlign: 'center' }}>
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
      <div style={{
        background: '#1e272e',
        borderRadius: '8px',
        padding: '12px',
        border: '1px solid #34495e',
      }}>
        <div style={{ marginBottom: '8px' }}>
          <span style={{ color: '#7f8c8d', fontSize: '10px', fontWeight: 'bold' }}>
            FLASK VISION SERVER
          </span>
        </div>
        <div style={{ color: '#95a5a6', fontSize: '10px' }}>
          <p style={{ margin: '4px 0' }}>URL: http://localhost:5000</p>
          <p style={{ margin: '4px 0', color: '#7f8c8d' }}>Endpoints:</p>
          <ul style={{ margin: '4px 0 0 16px', padding: 0, listStyleType: 'disc' }}>
            <li>/vision/status - Estado del sistema</li>
            <li>/vision/devices - Cámaras disponibles</li>
            <li>/vision/frame/&lt;id&gt; - Frame JPEG</li>
            <li>/vision/detections/&lt;id&gt; - Detecciones actuales</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
