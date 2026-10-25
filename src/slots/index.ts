/**
 * Host slots this module occupies: a dashboard card with device counts, and a
 * context panel when a provisioned machine or device is selected in the viewer.
 */
import type { ModuleViewerSlots } from '@nekazari/sdk';
import { DeviceContextPanel } from '../components/slots/DeviceContextPanel';
import { DeviceStatusWidget } from '../components/slots/DeviceStatusWidget';

const MODULE_ID = 'vpn';

export const moduleSlots: ModuleViewerSlots = {
  'map-layer': [],
  'layer-toggle': [],
  'context-panel': [
    {
      id: 'vpn-device-context',
      moduleId: MODULE_ID,
      component: 'DeviceContextPanel',
      localComponent: DeviceContextPanel,
      priority: 20,
      showWhen: { entityType: ['ManufacturingMachine', 'Device'] },
    },
  ],
  'bottom-panel': [],
  'entity-tree': [],
  'dashboard-widget': [
    {
      id: 'vpn-device-status',
      moduleId: MODULE_ID,
      component: 'DeviceStatusWidget',
      localComponent: DeviceStatusWidget,
      priority: 40,
    },
  ],
};
