import { useEffect, useState } from 'react';
import useSystemStore from '../store/useSystemStore';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Activity, TrendingUp, Zap } from 'lucide-react';
import { cn } from '../lib/utils';

const stateColors = {
  BAJADA: 'border-blue-500',
  BASE_GOLPE: 'border-purple-500',
  ATAQUE: 'border-red-500',
  BRAKE: 'border-orange-500',
};

function AnalyzerBar({ label, value, max = 1, threshold, className }) {
  const percentage = Math.min((value / max) * 100, 100);
  const thresholdPercentage = threshold ? (threshold / max) * 100 : null;
  const isAboveThreshold = threshold && value >= threshold;

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono">
          {value.toFixed(3)}
          {threshold && ` / ${threshold.toFixed(3)}`}
        </span>
      </div>
      <div className="relative h-2 bg-secondary rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full transition-all duration-300 rounded-full",
            isAboveThreshold ? "bg-primary" : "bg-muted-foreground/50",
            className
          )}
          style={{ width: `${percentage}%` }}
        />
        {thresholdPercentage && (
          <div
            className="absolute top-0 h-full w-0.5 bg-destructive"
            style={{ left: `${thresholdPercentage}%` }}
          />
        )}
      </div>
    </div>
  );
}

function AnalyzerCard({ analyzer, state }) {
  return (
    <Card className={cn("border-l-4", stateColors[state])}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base">{analyzer.name}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{analyzer.type}</p>
          </div>
          <div className="flex gap-2">
            {analyzer.active && (
              <Badge variant="success" className="text-xs">ON</Badge>
            )}
            {analyzer.match && (
              <Badge variant="default" className="text-xs animate-pulse">MATCH</Badge>
            )}
            {!analyzer.active && (
              <Badge variant="secondary" className="text-xs">OFF</Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        <AnalyzerBar
          label="Value"
          value={analyzer.value}
          max={analyzer.thresholds?.max || 1}
          threshold={analyzer.thresholds?.threshold}
        />
      </CardContent>
    </Card>
  );
}

function EnergyDetector({ energy }) {
  if (!energy) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap className="h-5 w-5" />
          Energy Detector
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Current Level</span>
          <Badge
            variant={
              energy.level === "ALTA" ? "destructive" :
              energy.level === "MEDIA" ? "warning" : "success"
            }
            className="text-lg px-4 py-1"
          >
            {energy.level}
          </Badge>
        </div>

        <AnalyzerBar
          label="Energy Score"
          value={energy.score || 0}
          max={1}
          threshold={energy.thresholds?.high}
        />

        {energy.thresholds && (
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div>
              <span className="text-muted-foreground">Low Threshold</span>
              <p className="font-mono">{energy.thresholds.low?.toFixed(3) || 'N/A'}</p>
            </div>
            <div>
              <span className="text-muted-foreground">High Threshold</span>
              <p className="font-mono">{energy.thresholds.high?.toFixed(3) || 'N/A'}</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StateSection({ stateName, analyzers }) {
  if (!analyzers || analyzers.length === 0) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold flex items-center gap-2">
        <Activity className="h-5 w-5" />
        {stateName}
        <Badge variant="secondary">{analyzers.length}</Badge>
      </h3>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {analyzers.map((analyzer, idx) => (
          <AnalyzerCard key={idx} analyzer={analyzer} state={stateName} />
        ))}
      </div>
    </div>
  );
}

export function Analyze() {
  const { analyzers, loading, errors, startPolling, stopPolling } = useSystemStore();
  const [filter, setFilter] = useState('all'); // all, active, matching

  useEffect(() => {
    startPolling('analyzers', 500);
    return () => stopPolling('analyzers');
  }, []);

  if (loading.analyzers && !analyzers) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading analyzers...</p>
        </div>
      </div>
    );
  }

  if (errors.analyzers) {
    return (
      <div className="flex items-center justify-center h-full">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="text-destructive">Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{errors.analyzers}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!analyzers) return null;

  const stats = analyzers.stats || {};

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Analyzers</h2>
        <p className="text-muted-foreground">Real-time audio analysis</p>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{stats.total_count || 0}</div>
            <p className="text-xs text-muted-foreground">Total Analyzers</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-primary">{stats.active_count || 0}</div>
            <p className="text-xs text-muted-foreground">Active</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-primary">{stats.matching_count || 0}</div>
            <p className="text-xs text-muted-foreground">Matching</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <Badge variant={loading.analyzers ? "warning" : "success"} className="animate-pulse">
              {loading.analyzers ? "Updating..." : "Live"}
            </Badge>
          </CardContent>
        </Card>
      </div>

      {/* Energy Detector */}
      {analyzers.energy && (
        <EnergyDetector energy={analyzers.energy} />
      )}

      {/* Analyzers by State */}
      <div className="space-y-6">
        {analyzers.by_state && (
          <>
            <StateSection stateName="BAJADA" analyzers={analyzers.by_state.BAJADA} />
            <StateSection stateName="BASE_GOLPE" analyzers={analyzers.by_state.BASE_GOLPE} />
            <StateSection stateName="ATAQUE" analyzers={analyzers.by_state.ATAQUE} />
            <StateSection stateName="BRAKE" analyzers={analyzers.by_state.BRAKE} />
          </>
        )}
      </div>
    </div>
  );
}
