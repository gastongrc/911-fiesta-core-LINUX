/**
 * Vision V7 - Camera Reference View
 *
 * SOLO REFERENCIA - No edición, no disparos
 *
 * Muestra:
 * - Stream de cada cámara (haze, people, tracking)
 * - Overlay de zonas guardadas
 * - Estado ON/OFF
 */
import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import {
  Eye,
  Camera,
  Users,
  Target,
  Cloud,
  CheckCircle,
  XCircle,
  RefreshCw
} from 'lucide-react';
import { Button } from '../components/ui/Button';

// Tipos de cámara
const CAMERA_TYPES = [
  { id: 'haze', name: 'Haze Detection', icon: Cloud, color: 'blue' },
  { id: 'people', name: 'People Counter', icon: Users, color: 'green' },
  { id: 'tracking', name: 'DJ Tracking', icon: Target, color: 'purple' },
];

// Hook para estado de Vision
function useVisionStatus() {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      // Intentar obtener estado desde /api/v1/status/unified
      const res = await fetch('/api/v1/status/unified');
      if (res.ok) {
        const data = await res.json();
        setCameras(data.cameras || []);
      } else {
        setError('Failed to load vision status');
      }
    } catch (e) {
      console.error('[VISION] status error:', e);
      setError('Connection error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000); // Refresh cada 5s
    return () => clearInterval(interval);
  }, []);

  return { cameras, loading, error, refresh };
}

// Componente de cámara individual
function CameraCard({ type, cameraData }) {
  const Icon = type.icon;
  const isOnline = cameraData?.online || false;
  const fps = cameraData?.fps || 0;
  const ip = cameraData?.ip || '—';

  return (
    <Card className={`${isOnline ? '' : 'opacity-60'}`}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className={`h-5 w-5 text-${type.color}-500`} />
            {type.name}
          </div>
          {isOnline ? (
            <Badge className="bg-green-500 flex items-center gap-1">
              <CheckCircle className="h-3 w-3" /> Online
            </Badge>
          ) : (
            <Badge className="bg-red-500 flex items-center gap-1">
              <XCircle className="h-3 w-3" /> Offline
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Placeholder para stream */}
        <div className="aspect-video bg-black/50 rounded-lg flex items-center justify-center mb-4">
          {isOnline ? (
            <div className="text-center">
              <Camera className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">
                Stream available via Flask Vision server
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                (Port 5000)
              </p>
            </div>
          ) : (
            <div className="text-center">
              <XCircle className="h-12 w-12 text-red-500 mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">Camera offline</p>
            </div>
          )}
        </div>

        {/* Info */}
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">IP</span>
            <span className="font-mono">{ip}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">FPS</span>
            <span className={isOnline ? 'text-green-500' : 'text-muted-foreground'}>
              {fps}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Status</span>
            <span className={isOnline ? 'text-green-500' : 'text-red-500'}>
              {isOnline ? 'Running' : 'Stopped'}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// Página principal
export function Vision() {
  const { cameras, loading, error, refresh } = useVisionStatus();

  // Mapear cameras por nombre
  const getCameraData = (id) => {
    return cameras.find(c => c.name === id) || null;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Eye className="h-6 w-6" />
          Vision System
        </h2>
        <div className="flex items-center gap-2">
          {cameras.filter(c => c.online).length > 0 && (
            <Badge className="bg-green-500">
              {cameras.filter(c => c.online).length}/{cameras.length} online
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Error message */}
      {error && (
        <Card className="border-red-500 bg-red-500/10">
          <CardContent className="py-4">
            <p className="text-red-500 text-center">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Info banner */}
      <Card className="bg-blue-500/10 border-blue-500">
        <CardContent className="py-4">
          <p className="text-sm text-center text-blue-400">
            Vision is <strong>reference only</strong> in Control Room.
            For zone editing and camera configuration, use the Qt UI.
          </p>
        </CardContent>
      </Card>

      {/* Grid de cámaras */}
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {CAMERA_TYPES.map(type => (
          <CameraCard
            key={type.id}
            type={type}
            cameraData={getCameraData(type.id)}
          />
        ))}
      </div>

      {/* Footer info */}
      <Card>
        <CardContent className="py-4">
          <div className="text-sm text-muted-foreground space-y-2">
            <p><strong>Flask Vision Server:</strong> http://localhost:5000</p>
            <p><strong>Endpoints:</strong></p>
            <ul className="list-disc list-inside ml-4 text-xs">
              <li>/vision/status - System status</li>
              <li>/vision/devices - Available cameras</li>
              <li>/vision/frame/&lt;id&gt; - JPEG frame</li>
              <li>/vision/detections/&lt;id&gt; - Current detections</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
