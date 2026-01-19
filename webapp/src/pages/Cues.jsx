import { useEffect, useState } from 'react';
import useSystemStore from '../store/useSystemStore';
import { fireCue, killCues } from '../api/cues';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Radio, Zap, XCircle, AlertTriangle } from 'lucide-react';
import { cn } from '../lib/utils';

function CueButton({ cueNumber, isActive, onFire, onForce }) {
  const [firing, setFiring] = useState(false);

  const handleFire = async (force = false) => {
    setFiring(true);
    try {
      await (force ? onForce(cueNumber) : onFire(cueNumber));
    } finally {
      setTimeout(() => setFiring(false), 500);
    }
  };

  return (
    <Card
      className={cn(
        "transition-all cursor-pointer",
        isActive ? "border-primary bg-primary/10" : "hover:border-primary/50",
        firing && "scale-95"
      )}
    >
      <CardContent className="p-4">
        <div className="text-center space-y-2">
          <div className="text-2xl font-bold font-mono">{cueNumber}</div>
          {isActive && (
            <Badge variant="success" className="w-full justify-center">
              ACTIVE
            </Badge>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              className="flex-1"
              onClick={() => handleFire(false)}
              disabled={firing}
            >
              Fire
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => handleFire(true)}
              disabled={firing}
            >
              <Zap className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function Cues() {
  const { cues, loading, errors, startPolling, stopPolling } = useSystemStore();
  const [showKillDialog, setShowKillDialog] = useState(false);
  const [maxCues, setMaxCues] = useState(60);
  const [toastMessage, setToastMessage] = useState(null);

  useEffect(() => {
    startPolling('cues', 1000);
    return () => stopPolling('cues');
  }, []);

  const showToast = (message, type = 'success') => {
    setToastMessage({ message, type });
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleFireCue = async (cueNumber) => {
    try {
      const response = await fireCue(cueNumber, false);
      if (response.data.success) {
        showToast(`Cue ${cueNumber} fired successfully`);
      } else {
        showToast(`Failed to fire cue ${cueNumber}`, 'error');
      }
    } catch (error) {
      showToast(`Error: ${error.message}`, 'error');
    }
  };

  const handleForceFire = async (cueNumber) => {
    try {
      const response = await fireCue(cueNumber, true);
      if (response.data.success) {
        showToast(`Cue ${cueNumber} force fired!`, 'warning');
      } else {
        showToast(`Failed to force fire cue ${cueNumber}`, 'error');
      }
    } catch (error) {
      showToast(`Error: ${error.message}`, 'error');
    }
  };

  const handleKillAll = async () => {
    if (!cues?.active_cues || cues.active_cues.length === 0) {
      showToast('No active cues to kill', 'warning');
      return;
    }

    try {
      const response = await killCues(cues.active_cues, true);
      if (response.data.success) {
        showToast(`Killed ${response.data.killed_count} cues`);
        setShowKillDialog(false);
      }
    } catch (error) {
      showToast(`Error: ${error.message}`, 'error');
    }
  };

  const activeCuesSet = new Set(cues?.active_cues || []);
  const cueNumbers = Array.from({ length: maxCues }, (_, i) => i + 1);

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 animate-in slide-in-from-top">
          <Card className={cn(
            "border-l-4",
            toastMessage.type === 'success' && "border-l-green-500",
            toastMessage.type === 'error' && "border-l-red-500",
            toastMessage.type === 'warning' && "border-l-orange-500"
          )}>
            <CardContent className="p-4">
              <p className="text-sm">{toastMessage.message}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Page Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Cue Control</h2>
        <p className="text-muted-foreground">Manual cue fire and kill controls</p>
      </div>

      {/* Status Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Active Cues</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{cues?.active_cues?.length || 0}</div>
            {cues?.active_cues && cues.active_cues.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {cues.active_cues.slice(0, 10).map((cue) => (
                  <Badge key={cue} variant="success">{cue}</Badge>
                ))}
                {cues.active_cues.length > 10 && (
                  <Badge variant="secondary">+{cues.active_cues.length - 10}</Badge>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Engine Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Modules Active</span>
                <span className="font-bold">{cues?.cue_engine?.modules_active || 0}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Total Updates</span>
                <span className="font-mono text-xs">{cues?.cue_engine?.total_updates || 0}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button
              variant="destructive"
              className="w-full"
              onClick={() => setShowKillDialog(true)}
              disabled={!cues?.active_cues || cues.active_cues.length === 0}
            >
              <XCircle className="h-4 w-4 mr-2" />
              Kill All Cues
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Kill Confirmation Dialog */}
      {showKillDialog && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
          <Card className="max-w-md">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-destructive">
                <AlertTriangle className="h-5 w-5" />
                Confirm Kill All
              </CardTitle>
              <CardDescription>
                This will kill all {cues?.active_cues?.length || 0} active cues using force mode.
                This action cannot be undone.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => setShowKillDialog(false)}
                >
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  className="flex-1"
                  onClick={handleKillAll}
                >
                  Kill All
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Cue Grid */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Radio className="h-5 w-5" />
              Cue Grid
            </CardTitle>
            <div className="flex gap-2 items-center">
              <span className="text-sm text-muted-foreground">Show:</span>
              <select
                className="bg-background border border-input rounded px-2 py-1 text-sm"
                value={maxCues}
                onChange={(e) => setMaxCues(Number(e.target.value))}
              >
                <option value={30}>30</option>
                <option value={60}>60</option>
                <option value={100}>100</option>
                <option value={300}>300</option>
              </select>
            </div>
          </div>
          <CardDescription>
            Click "Fire" to fire normally, or the lightning icon to force fire (bypasses READY check)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-3">
            {cueNumbers.map((num) => (
              <CueButton
                key={num}
                cueNumber={num}
                isActive={activeCuesSet.has(num)}
                onFire={handleFireCue}
                onForce={handleForceFire}
              />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
