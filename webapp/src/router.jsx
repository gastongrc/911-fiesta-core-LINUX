/**
 * Router V7 - Control Room Navigation
 *
 * Páginas:
 * - Home (dashboard con 5 bloques de estado)
 * - Calendar (control del calendario inteligente)
 * - Vision (visualización de cámaras - solo referencia)
 * - Network (configuración de red)
 * - Config (configuración del sistema)
 * - Presets (gestión de presets)
 *
 * ELIMINADAS:
 * - Cues (peligroso en show)
 * - Analyze (innecesario en Control Room)
 */
import { createBrowserRouter } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Home } from './pages/Home';
import { Calendar } from './pages/Calendar';
import { Vision } from './pages/Vision';
import { Network } from './pages/Network';
import { Presets } from './pages/Presets';
import { Config } from './pages/Config';

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
    path: '/vision',
    element: <Layout><Vision /></Layout>,
  },
  {
    path: '/network',
    element: <Layout><Network /></Layout>,
  },
  {
    path: '/presets',
    element: <Layout><Presets /></Layout>,
  },
  {
    path: '/config',
    element: <Layout><Config /></Layout>,
  },
]);
