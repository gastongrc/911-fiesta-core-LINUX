/**
 * Layout V7 - Control Room Navigation
 *
 * Navegación:
 * - Home (dashboard)
 * - Calendar (calendario inteligente)
 * - Vision (cámaras - solo referencia)
 * - Network (configuración de red)
 * - Config (configuración)
 * - Presets (presets)
 */
import { Link, useLocation } from 'react-router-dom';
import {
  Home,
  Calendar,
  Eye,
  Network,
  Save,
  Settings
} from 'lucide-react';
import { cn } from '../lib/utils';

const navItems = [
  { path: '/', icon: Home, label: 'Home' },
  { path: '/calendar', icon: Calendar, label: 'Calendar' },
  { path: '/vision', icon: Eye, label: 'Vision' },
  { path: '/network', icon: Network, label: 'Network' },
  { path: '/presets', icon: Save, label: 'Presets' },
  { path: '/config', icon: Settings, label: 'Config' },
];

export function Layout({ children }) {
  const location = useLocation();

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="container mx-auto px-4 py-3">
          <h1 className="text-xl font-bold text-primary">911 Fiesta Control Room</h1>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar Navigation */}
        <aside className="w-56 border-r border-border bg-card hidden md:block">
          <nav className="flex flex-col gap-1 p-3">
            {navItems.map(({ path, icon: Icon, label }) => (
              <Link
                key={path}
                to={path}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors",
                  "hover:bg-accent hover:text-accent-foreground",
                  location.pathname === path
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground"
                )}
              >
                <Icon className="h-5 w-5" />
                <span className="font-medium">{label}</span>
              </Link>
            ))}
          </nav>
        </aside>

        {/* Page Content */}
        <main className="flex-1 overflow-auto">
          <div className="container mx-auto p-4 md:p-6 max-w-7xl">
            {children}
          </div>
        </main>
      </div>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden border-t border-border bg-card">
        <div className="flex justify-around items-center p-2">
          {navItems.map(({ path, icon: Icon, label }) => (
            <Link
              key={path}
              to={path}
              className={cn(
                "flex flex-col items-center gap-1 px-2 py-2 rounded-lg transition-colors min-w-0",
                location.pathname === path
                  ? "text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon className="h-5 w-5 flex-shrink-0" />
              <span className="text-xs font-medium truncate">{label}</span>
            </Link>
          ))}
        </div>
      </nav>
    </div>
  );
}
