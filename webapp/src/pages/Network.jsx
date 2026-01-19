import { useEffect, useState } from 'react';
import {
  getNetworkInterfaces,
  setNetworkInterface,
  setConsoleTarget,
  pingHost
} from '../api/network';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Network as NetworkIcon, Wifi, Target, Activity } from 'lucide-react';

export function Network() {
  const [interfaces, setInterfaces] = useState([]);
  const [currentInterface, setCurrentInterface] = useState('');
  const [consoleIp, setConsoleIp] = useState('');
  const [consolePort, setConsolePort] = useState(4430);
  const [pingTarget, setPingTarget] = useState('');
  const [pingResult, setPingResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    loadInterfaces();
  }, []);

  const showMessage = (text, type = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 3000);
  };

  const loadInterfaces = async () => {
    try {
      const response = await getNetworkInterfaces();
      setInterfaces(response.data.interfaces || []);
      setCurrentInterface(response.data.current_interface || '');
    } catch (error) {
      showMessage(`Error loading interfaces: ${error.message}`, 'error');
    }
  };

  const handleSetInterface = async (interfaceName) => {
    setLoading(true);
    try {
      await setNetworkInterface(interfaceName);
      setCurrentInterface(interfaceName);
      showMessage(`Interface set to ${interfaceName}`);
    } catch (error) {
      showMessage(`Error: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSetConsole = async () => {
    if (!consoleIp) {
      showMessage('Please enter console IP', 'error');
      return;
    }

    setLoading(true);
    try {
      await setConsoleTarget(consoleIp, consolePort);
      showMessage(`Console target set to ${consoleIp}:${consolePort}`);
    } catch (error) {
      showMessage(`Error: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handlePing = async () => {
    if (!pingTarget) {
      showMessage('Please enter host to ping', 'error');
      return;
    }

    setLoading(true);
    setPingResult(null);
    try {
      const response = await pingHost(pingTarget);
      setPingResult(response.data);
      if (response.data.reachable) {
        showMessage(`Host is reachable (${response.data.latency_ms.toFixed(2)}ms)`);
      } else {
        showMessage('Host is not reachable', 'error');
      }
    } catch (error) {
      setPingResult({ reachable: false, error: error.message });
      showMessage(`Ping error: ${error.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Toast Message */}
      {message && (
        <div className="fixed top-4 right-4 z-50 animate-in slide-in-from-top">
          <Card className={`border-l-4 ${
            message.type === 'success' ? 'border-l-green-500' : 'border-l-red-500'
          }`}>
            <CardContent className="p-4">
              <p className="text-sm">{message.text}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Page Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Network Configuration</h2>
        <p className="text-muted-foreground">Configure network interfaces and Avolites console connection</p>
      </div>

      {/* Network Interfaces */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wifi className="h-5 w-5" />
            Network Interfaces
          </CardTitle>
          <CardDescription>
            Select the network interface to use for Avolites communication
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {interfaces.length === 0 ? (
            <p className="text-sm text-muted-foreground">No interfaces found</p>
          ) : (
            <div className="grid gap-2 md:grid-cols-2">
              {interfaces.map((iface) => (
                <Card
                  key={iface.name}
                  className={`cursor-pointer transition-all ${
                    currentInterface === iface.name
                      ? 'border-primary bg-primary/10'
                      : 'hover:border-primary/50'
                  }`}
                  onClick={() => handleSetInterface(iface.name)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">{iface.name}</p>
                        <p className="text-sm text-muted-foreground font-mono">{iface.ip}</p>
                      </div>
                      {currentInterface === iface.name && (
                        <Badge variant="success">Active</Badge>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Console Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5" />
            Avolites Console
          </CardTitle>
          <CardDescription>
            Set the IP address and port of the Avolites console
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">Console IP</label>
              <input
                type="text"
                className="w-full px-3 py-2 bg-background border border-input rounded-md font-mono"
                placeholder="192.168.1.100"
                value={consoleIp}
                onChange={(e) => setConsoleIp(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Port</label>
              <input
                type="number"
                className="w-full px-3 py-2 bg-background border border-input rounded-md font-mono"
                placeholder="4430"
                value={consolePort}
                onChange={(e) => setConsolePort(Number(e.target.value))}
              />
            </div>
          </div>
          <Button
            onClick={handleSetConsole}
            disabled={loading || !consoleIp}
            className="w-full md:w-auto"
          >
            <NetworkIcon className="h-4 w-4 mr-2" />
            Set Console Target
          </Button>
        </CardContent>
      </Card>

      {/* Ping Tool */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Ping Host
          </CardTitle>
          <CardDescription>
            Test network connectivity to a host
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <input
              type="text"
              className="flex-1 px-3 py-2 bg-background border border-input rounded-md font-mono"
              placeholder="192.168.1.100 or hostname"
              value={pingTarget}
              onChange={(e) => setPingTarget(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handlePing()}
            />
            <Button
              onClick={handlePing}
              disabled={loading || !pingTarget}
            >
              Ping
            </Button>
          </div>

          {pingResult && (
            <div className={`p-4 rounded-lg border ${
              pingResult.reachable
                ? 'bg-green-500/10 border-green-500'
                : 'bg-red-500/10 border-red-500'
            }`}>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">
                    {pingResult.reachable ? 'Host is reachable' : 'Host is not reachable'}
                  </p>
                  {pingResult.reachable && (
                    <p className="text-sm text-muted-foreground mt-1">
                      Latency: <span className="font-mono">{pingResult.latency_ms.toFixed(2)} ms</span>
                    </p>
                  )}
                  {pingResult.error && (
                    <p className="text-sm text-muted-foreground mt-1">{pingResult.error}</p>
                  )}
                </div>
                <Badge variant={pingResult.reachable ? 'success' : 'destructive'}>
                  {pingResult.reachable ? 'UP' : 'DOWN'}
                </Badge>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
