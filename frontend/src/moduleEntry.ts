/**
 * NKZ Module Entry Point — IIFE bundle
 *
 * This file is the single entry point compiled into nekazari-module.js.
 * When the browser executes it, it self-registers with the host via
 * window.__NKZ__.register(). The host then:
 *   - Renders the `main` component when the user navigates to /devices
 *   - Injects `viewerSlots` widgets into the dashboard and context panels
 *
 * IMPORTANT: The module id MUST match marketplace_modules.id in PostgreSQL.
 */

import './i18n';
import { moduleSlots } from './slots';
import { DevicesPage } from './pages/DevicesPage';

const MODULE_ID = 'vpn';

declare global {
  interface Window {
    __NKZ__: {
      register: (module: {
        id: string;
        main?: any;
        viewerSlots?: typeof moduleSlots;
        version?: string;
      }) => void;
    };
  }
}

if (typeof window !== 'undefined' && window.__NKZ__) {
  window.__NKZ__.register({
    id: MODULE_ID,
    main: DevicesPage,
    viewerSlots: moduleSlots,
    version: '1.0.0',
  });
} else {
  console.error(`[${MODULE_ID}] window.__NKZ__ not found. Is this bundle loaded inside the NKZ host?`);
}
