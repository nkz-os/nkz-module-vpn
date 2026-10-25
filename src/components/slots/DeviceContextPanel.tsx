import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useViewer } from '@nekazari/sdk';
import { Card, Inline, Stack } from '@nekazari/ui-kit';
import { useDevices } from '../../hooks/useDevices';
import { NodeStatus, StateBadge } from '../StateBadge';

/** Context panel for a selected ManufacturingMachine / Device: provisioning and VPN state. */
export const DeviceContextPanel: React.FC = () => {
  const { t } = useTranslation('vpn');
  const { selectedEntityId } = useViewer();
  const { devices } = useDevices(false);
  const device = useMemo(
    () => devices.find((d) => d.ngsi_entity_id && d.ngsi_entity_id === selectedEntityId) ?? null,
    [devices, selectedEntityId],
  );

  return (
    <Card padding="sm">
      <Stack gap="inline">
        <span className="text-nkz-sm font-semibold text-nkz-text-primary">{t('context.title')}</span>
        {!device ? (
          <span className="text-nkz-xs text-nkz-text-secondary">{t('context.notManaged')}</span>
        ) : (
          <>
            <Inline gap="inline" wrap>
              <StateBadge state={device.state} />
              <NodeStatus device={device} />
            </Inline>
            {device.node?.ip && (
              <span className="text-nkz-xs font-mono text-nkz-text-secondary">
                {t('context.ip', { ip: device.node.ip })}
              </span>
            )}
          </>
        )}
      </Stack>
    </Card>
  );
};
