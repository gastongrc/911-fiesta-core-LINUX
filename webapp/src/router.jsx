/**
 * Router — 3 Panel Navigation
 *
 * Panels (matching UI contract):
 * - Home: Control Room + Status Dashboard (merged)
 * - Calendar: Calendar scheduling + control
 * - Config: Config PRO panel
 */
import { createBrowserRouter } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Home } from './pages/Home';
import { Calendar } from './pages/Calendar';
import { ConfigPro } from './pages/ConfigPro';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout><Home /></Layout>,
  },
  {
    path: '/calendar',
    element: <Layout><Calendar /></Layout>,
  },
  {
    path: '/config',
    element: <Layout><ConfigPro /></Layout>,
  },
]);
