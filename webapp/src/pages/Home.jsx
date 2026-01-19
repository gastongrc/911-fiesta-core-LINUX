import { useEffect } from 'react';
import useSystemStore from '../store/useSystemStore';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Activity, Music, Radio, Zap, Clock } from 'lucide-react';

const stateColors = {
  BAJADA: 'bg-blue-500',
  BASE_GOLPE: 'bg-purple-500',
  ATAQUE: 'bg-red-500',
  BRAKE: 'bg-orange-500',
};

const energyColors = {
  BAJA: 'bg-green-500',
  MEDIA: 'bg-yellow-500',
  ALTA: 'bg-red-500',
};

function StatusCard({ icon: Icon, title, children, badge }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          {title}
        </CardTitle>
        {badge}
      </CardHeader>
      <CardContent>
        {children}
      </CardContent>
    </Card>
  );
}

export function Home() {
  const { status, loading, errors, fetchStatus, startPolling, stopPolling } = useSystemStore();

  useEffect(() => {
    // Start polling on mount
    startPolling('status', 1000);

    // Stop polling on unmount
    return () => stopPolling('status');
  }, []);

  if (loading.status && !status) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading system status...</p>
        </div>
      </div>
    );
  }

  if (errors.status && !status) {
    return (
      <div className="flex items-center justify-center h-full">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="text-destructive">Connection Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{errors.status}</p>
            <p className="text-sm text-muted-foreground mt-2">
              Make sure the API server is running on http://localhost:8000
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!status) return null;

  const uptimeMinutes = Math.floor(status.uptime_seconds / 60);
  const uptimeHours = Math.floor(uptimeMinutes / 60);
  const uptimeDisplay = uptimeHours > 0
    ? `${uptimeHours}h ${uptimeMinutes % 60}m`
    : `${uptimeMinutes}m`;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground">System overview and status</p>
      </div>

      {/* Main Status Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatusCard
          icon={Activity}
          title="System State"
          badge={
            <div className={`w-3 h-3 rounded-full ${stateColors[status.state]} animate-pulse`} />
          }
        >
          <div className="text-2xl font-bold">{status.state}</div>
          {status.state_locked && (
            <Badge variant="warning" className="mt-2">LOCKED</Badge>
          )}
          {status.brake_active && (
            <Badge variant="destructive" className="mt-2">BRAKE</Badge>
          )}
        </StatusCard>

        <StatusCard
          icon={Zap}
          title="Energy Level"
          badge={
            <div className={`w-3 h-3 rounded-full ${energyColors[status.energy]} animate-pulse`} />
          }
        >
          <div className="text-2xl font-bold">{status.energy}</div>
        </StatusCard>

        <StatusCard
          icon={Music}
          title="Audio Engine"
        >
          <div className="space-y-1">
            <Badge variant={status.audio?.running ? "success" : "destructive"}>
              {status.audio?.running ? "RUNNING" : "STOPPED"}
            </Badge>
            {status.audio?.device && (
              <p className="text-xs text-muted-foreground truncate">
                {status.audio.device}
              </p>
            )}
            {status.audio?.samplerate && (
              <p className="text-xs text-muted-foreground">
                {status.audio.samplerate} Hz
              </p>
            )}
          </div>
        </StatusCard>

        <StatusCard
          icon={Clock}
          title="Uptime"
        >
          <div className="text-2xl font-bold">{uptimeDisplay}</div>
          <p className="text-xs text-muted-foreground">
            v{status.version}
          </p>
        </StatusCard>
      </div>

      {/* Avolites Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Radio className="h-5 w-5" />
            Avolites Controller
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">Connection</p>
              <Badge variant={status.avolites?.connected ? "success" : "destructive"}>
                {status.avolites?.connected ? "CONNECTED" : "DISCONNECTED"}
              </Badge>
            </div>
            {status.avolites?.console_ip && (
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">Console</p>
                <p className="text-sm font-mono">
                  {status.avolites.console_ip}:{status.avolites.console_port}
                </p>
              </div>
            )}
            {status.avolites?.active_cues_count !== undefined && (
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">Active Cues</p>
                <p className="text-2xl font-bold">{status.avolites.active_cues_count}</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Cue Engine Status */}
      {status.cue_engine && (
        <Card>
          <CardHeader>
            <CardTitle>Cue Engine</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">Active Modules</p>
                <p className="text-2xl font-bold">{status.cue_engine.modules_active || 0}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-1">Total Updates</p>
                <p className="text-2xl font-bold">{status.cue_engine.total_updates || 0}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
