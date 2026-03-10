/**
 * Router — 4 Panel Navigation
 *
 * Panels:
 * - /           Control Room + Status Dashboard
 * - /calendar   Calendar scheduling + control
 * - /analyze    System Monitor (engine health)
 * - /config     Config PRO panel
 */
import { createBrowserRouter } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Home } from './pages/Home';
import { Calendar } from './pages/Calendar';
import { Analyze } from './pages/Analyze';
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
    path: '/analyze',
    element: <Layout><Analyze /></Layout>,
  },
  {
    path: '/config',
    element: <Layout><ConfigPro /></Layout>,
  },
]);
