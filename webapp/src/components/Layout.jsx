/**
 * Layout — Sidebar + Main (matches UI contract)
 *
 * Sidebar: 3 nav buttons (Home, Calendar, Config/Sliders)
 * Icons match docs/ui-contract/icons.svg exactly
 */
import { Link, useLocation } from 'react-router-dom';

const navItems = [
  {
    path: '/',
    icon: (
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      </svg>
    ),
  },
  {
    path: '/calendar',
    icon: (
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </svg>
    ),
  },
  {
    path: '/config',
    icon: (
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <line x1="4" y1="21" x2="4" y2="14" />
        <line x1="4" y1="10" x2="4" y2="3" />
        <line x1="12" y1="21" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12" y2="3" />
        <line x1="20" y1="21" x2="20" y2="16" />
        <line x1="20" y1="12" x2="20" y2="3" />
      </svg>
    ),
  },
];

export function Layout({ children }) {
  const location = useLocation();

  return (
    <>
      <div className="bg-canvas">
        <div className="blob blob-1" />
        <div className="blob blob-2" />
        <div className="blob blob-3" />
      </div>
      <div className="noise" />

      <div className="app">
        <aside className="side">
          <Link to="/" className="s-logo">
            <span>911</span>
          </Link>
          {navItems.map(({ path, icon }) => (
            <Link
              key={path}
              to={path}
              className={`s-btn${location.pathname === path ? ' on' : ''}`}
            >
              {icon}
            </Link>
          ))}
          <div style={{ marginTop: 'auto', marginBottom: '8px' }}>
            <div className="led-dot" />
          </div>
        </aside>

        <main className="main">
          {children}
        </main>
      </div>
    </>
  );
}
