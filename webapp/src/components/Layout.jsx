/**
 * Layout V7 - Control Room Navigation (Estilo Industrial)
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
      background: '#0d1117',
      color: '#ecf0f1',
    }}>
      {/* Header */}
      <header style={{
        background: '#1e272e',
        borderBottom: '1px solid #34495e',
        padding: '10px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <h1 style={{
          margin: 0,
          fontSize: '16px',
          fontWeight: 'bold',
          color: '#ecf0f1',
          letterSpacing: '1px',
        }}>
          911 FIESTA CONTROL ROOM
        </h1>
        <span style={{
          color: '#7f8c8d',
          fontSize: '10px',
        }}>
          V7
        </span>
      </header>

      {/* Main */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Sidebar */}
        <aside style={{
          width: '180px',
          background: '#1e272e',
          borderRight: '1px solid #34495e',
          padding: '12px 8px',
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
                  padding: '10px 12px',
                  borderRadius: '6px',
                  textDecoration: 'none',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  letterSpacing: '0.5px',
                  background: isActive ? '#27ae60' : 'transparent',
                  color: isActive ? '#ffffff' : '#7f8c8d',
                  border: isActive ? 'none' : '1px solid transparent',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.target.style.background = '#2c3e50';
                    e.target.style.color = '#ecf0f1';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.target.style.background = 'transparent';
                    e.target.style.color = '#7f8c8d';
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
          background: '#0d1117',
        }}>
          {children}
        </main>
      </div>

      {/* Mobile Bottom Nav */}
      <nav style={{
        display: 'none',
        background: '#1e272e',
        borderTop: '1px solid #34495e',
        padding: '8px',
      }}>
        {/* Se activa en mobile via media query si es necesario */}
      </nav>

      {/* Mobile CSS */}
      <style>{`
        @media (max-width: 768px) {
          aside { display: none !important; }
          nav { display: flex !important; justify-content: space-around; }
        }
      `}</style>
    </div>
  );
}
