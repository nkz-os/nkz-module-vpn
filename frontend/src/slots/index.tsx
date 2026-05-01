/**
 * Slot Registration for nekazari-module-vpn
 *
 * Defines widgets that integrate with the host's Unified Viewer and Dashboard.
 * All widgets must include explicit `moduleId`.
 */

import '../i18n';
import React from 'react';

const MODULE_ID = 'vpn';

// =============================================================================
// Types (mirrored from host SDK to avoid importing host-internal types)
// =============================================================================

export interface SlotWidgetDefinition {
  id: string;
  moduleId: string;
  component: string;
  priority: number;
  localComponent: React.ComponentType<any>;
  defaultProps?: Record<string, any>;
  showWhen?: {
    entityType?: string[];
    layerActive?: string[];
  };
}

export interface ModuleViewerSlots {
  'entity-tree'?: SlotWidgetDefinition[];
  'map-layer'?: SlotWidgetDefinition[];
  'context-panel'?: SlotWidgetDefinition[];
  'bottom-panel'?: SlotWidgetDefinition[];
  'layer-toggle'?: SlotWidgetDefinition[];
  'dashboard-widget'?: SlotWidgetDefinition[];
  moduleProvider?: React.ComponentType<{ children: React.ReactNode }>;
}

// =============================================================================
// Slot Components
// =============================================================================

import { VpnStatusWidget } from '../components/VpnStatusWidget';
import { VpnContextPanel } from '../components/VpnContextPanel';
import { DeviceQuotaWidget } from '../components/DeviceQuotaWidget';

// =============================================================================
// Slot Definitions
// =============================================================================

export const moduleSlots: ModuleViewerSlots = {
  // Dashboard cards
  'dashboard-widget': [
    {
      id: `${MODULE_ID}-status-widget`,
      moduleId: MODULE_ID,
      component: 'VpnStatusWidget',
      priority: 40,
      localComponent: VpnStatusWidget,
    },
    {
      id: `${MODULE_ID}-quota-widget`,
      moduleId: MODULE_ID,
      component: 'DeviceQuotaWidget',
      priority: 39,
      localComponent: DeviceQuotaWidget,
    },
  ],

  // Context panel: shown when a Robot or IoTGateway entity is selected
  'context-panel': [
    {
      id: `${MODULE_ID}-context-panel`,
      moduleId: MODULE_ID,
      component: 'VpnContextPanel',
      priority: 20,
      localComponent: VpnContextPanel,
      showWhen: {
        entityType: ['AgriRobot', 'AgriGateway', 'AgriSensor'],
      },
    },
  ],
};

export default moduleSlots;
