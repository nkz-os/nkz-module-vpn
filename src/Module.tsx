import { defineModule } from '@nekazari/module-kit';
import { lazy } from 'react';
import { moduleSlots } from './slots';

const App = lazy(() => import('./App'));

export default defineModule({
  id: 'nkz-module-vpn',
  displayName: 'VPN / Devices',
  version: '1.0.0',
  hostApiVersion: '^1.0.0',
  accent: {
    base: '#3b82f6',
    soft: '#93c5fd',
    strong: '#1d4ed8'
  },
  icon: 'Network',
  main: App,
  route: '/devices',
  slots: moduleSlots as any,
  data: {
    entities: ['AgriRobot', 'AgriGateway', 'AgriSensor'],
    timeseries: []
  }
});
