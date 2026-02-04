/**
 * Layout V7 - Control Room Navigation (NEON UI)
 *
 * Navegación:
 * - Home (dashboard)
 * - Calendar (calendario)
 * - Vision (cámaras - solo referencia)
 * - Network (configuración de red)
 * - Presets (presets)
 * - Config (configuración)
 */
import { Link, useLocation } from 'react-router-dom';

const navItems = [
  { path: '/', label: 'HOME' },
  { path: '/calendar', label: 'CALENDAR' },
  { path: '/vision', label: 'VISION' },
  { path: '/network', label: 'NETWORK' },
  { path: '/presets', label: 'PRESETS' },
  { path: '/config', label: 'CONFIG' },
];

export function Layout({ children }) {
  const location = useLocation();

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      background: 'var(--bg-dark)',
      color: 'var(--text-normal)',
    }}>
      {/* Header */}
      <header style={{
        background: 'var(--bg-panel)',
        borderBottom: '1px solid var(--border-dim)',
        padding: '12px 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'relative',
      }}>
        {/* Glow line */}
        <div style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: '1px',
          background: 'linear-gradient(90deg, transparent, var(--neon-cyan), var(--neon-green), var(--neon-cyan), transparent)',
          boxShadow: '0 0 10px var(--neon-cyan)',
        }} />

        <h1 style={{
          margin: 0,
          fontSize: '16px',
          fontWeight: 'bold',
          color: 'var(--neon-cyan)',
          letterSpacing: '2px',
          textShadow: '0 0 15px var(--neon-cyan)',
        }}>
          911 FIESTA CONTROL ROOM
        </h1>
        <span style={{
          color: 'var(--text-dim)',
          fontSize: '10px',
          padding: '4px 8px',
          background: 'var(--bg-dark)',
          borderRadius: '4px',
          border: '1px solid var(--border-dim)',
        }}>
          V7
        </span>
      </header>

      {/* Main */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Sidebar */}
        <aside style={{
          width: '180px',
          background: 'var(--bg-panel)',
          borderRight: '1px solid var(--border-dim)',
          padding: '16px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}>
          {navItems.map(({ path, label }) => {
            const isActive = location.pathname === path;
            return (
              <Link
                key={path}
                to={path}
                style={{
                  display: 'block',
                  padding: '12px 16px',
                  borderRadius: '6px',
                  textDecoration: 'none',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  letterSpacing: '1px',
                  background: isActive ? 'var(--neon-green)' : 'transparent',
                  color: isActive ? 'var(--bg-dark)' : 'var(--text-dim)',
                  border: isActive ? 'none' : '1px solid transparent',
                  boxShadow: isActive ? '0 0 15px rgba(0, 255, 136, 0.4)' : 'none',
                  transition: 'all 0.2s ease',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.target.style.background = 'var(--bg-hover)';
                    e.target.style.color = 'var(--neon-cyan)';
                    e.target.style.borderColor = 'var(--border-dim)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.target.style.background = 'transparent';
                    e.target.style.color = 'var(--text-dim)';
                    e.target.style.borderColor = 'transparent';
                  }
                }}
              >
                {label}
              </Link>
            );
          })}
        </aside>

        {/* Content */}
        <main style={{
          flex: 1,
          overflow: 'auto',
          background: 'var(--bg-dark)',
        }}>
          {children}
        </main>
      </div>

      {/* Mobile Bottom Nav (hidden on desktop) */}
      <style>{`
        @media (max-width: 768px) {
          aside { display: none !important; }
        }
      `}</style>
    </div>
  );
}
