import { createBrowserRouter } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Home } from './pages/Home';
import { Analyze } from './pages/Analyze';
import { Cues } from './pages/Cues';
import { Network } from './pages/Network';
import { Presets } from './pages/Presets';
import { Config } from './pages/Config';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout><Home /></Layout>,
  },
  {
    path: '/analyze',
    element: <Layout><Analyze /></Layout>,
  },
  {
    path: '/cues',
    element: <Layout><Cues /></Layout>,
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
