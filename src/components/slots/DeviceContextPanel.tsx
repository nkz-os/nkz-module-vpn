import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useViewer } from '@nekazari/sdk';
import { Card, Inline, Spinner, Stack } from '@nekazari/ui-kit';
import { ApiError, vpnApi } from '../../services/api';
import type { DeviceOut } from '../../types/vpn';
import { entityDeviceUuid } from '../../lib/format';
import { NodeStatus, StateBadge } from '../StateBadge';

type Load = { kind: 'idle' } | { kind: 'loading' } | { kind: 'none' } | { kind: 'error' } | { kind: 'ok'; device: DeviceOut };

/** Context panel for a selected ManufacturingMachine / Device: provisioning and VPN state of that one device. */
export const DeviceContextPanel: React.FC = () => {
  const { t } = useTranslation('vpn');
  const { selectedEntityId } = useViewer();
  const [load, setLoad] = useState<Load>({ kind: 'idle' });

  useEffect(() => {
    const uuid = entityDeviceUuid(selectedEntityId);
    if (!uuid) {
      setLoad({ kind: 'none' }); // e.g. a tractor: a machine this module does not provision
      return;
    }
    let cancelled = false;
    setLoad({ kind: 'loading' });
    vpnApi
      .getDevice(uuid)
      .then((device) => {
        if (!cancelled) setLoad(device.ngsi_entity_id === selectedEntityId ? { kind: 'ok', device } : { kind: 'none' });
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoad({ kind: err instanceof ApiError && err.status === 404 ? 'none' : 'error' });
      });
    return () => {
      cancelled = true;
    };
  }, [selectedEntityId]);

  return (
    <Card padding="sm">
      <Stack gap="inline">
        <span className="text-nkz-sm font-semibold text-nkz-text-primary">{t('context.title')}</span>
        {load.kind === 'loading' && <Spinner size="sm" />}
        {load.kind === 'none' && <span className="text-nkz-xs text-nkz-text-secondary">{t('context.notManaged')}</span>}
        {load.kind === 'error' && <span className="text-nkz-xs text-nkz-text-secondary">{t('context.loadError')}</span>}
        {load.kind === 'ok' && (
          <>
            <Inline gap="inline" wrap>
              <StateBadge state={load.device.state} />
              <NodeStatus device={load.device} />
            </Inline>
            {load.device.node?.ip && (
              <span className="text-nkz-xs font-mono text-nkz-text-secondary">
                {t('context.ip', { ip: load.device.node.ip })}
              </span>
            )}
          </>
        )}
      </Stack>
    </Card>
  );
};
