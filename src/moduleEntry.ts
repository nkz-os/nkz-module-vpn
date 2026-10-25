/**
 * Module entry point — canonical `defineModule()` pattern (Module Federation 2.0).
 *
 * defineModule() is the runtime source of truth: every publish overwrites the
 * marketplace row with the manifest emitted from it (roles, route, version).
 * The root manifest.json and k8s/registration.sql are seeds and must agree.
 *
 * `vpn` must match the `id` column in marketplace_modules exactly.
 */
import { defineModule } from '@nekazari/module-kit';
import { lazy } from 'react';
import './i18n';
import { moduleSlots } from './slots';
import pkg from '../package.json';

const MainPage = lazy(() => import('./App'));

export default defineModule({
  id: 'vpn',
  displayName: 'Device Management',
  version: pkg.version,
  hostApiVersion: '^2.0.0',
  description: 'Zero-touch provisioning of field devices over the platform VPN',
  accent: { base: '#3B82F6', soft: '#93C5FD', strong: '#1D4ED8' },
  icon: 'network',
  main: MainPage,
  route: '/devices',
  requiredRoles: ['TenantAdmin', 'PlatformAdmin'],
  api: { basePath: '/api/vpn' },
  data: { entities: ['ManufacturingMachine', 'Device'], timeseries: [] },
  slots: moduleSlots as never,
});
