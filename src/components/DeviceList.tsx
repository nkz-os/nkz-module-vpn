import React from 'react';
import { useTranslation } from 'react-i18next';
import { Badge, Button, Card, EmptyState, Inline, Spinner, Stack } from '@nekazari/ui-kit';
import { Cpu, KeyRound, Radio, Router, Trash2 } from 'lucide-react';
import type { DeviceOut } from '../types/vpn';
import { NodeStatus, StateBadge } from './StateBadge';

const TYPE_ICON = { rover: Cpu, gateway: Router, sensor: Radio } as const;

interface Props {
  devices: DeviceOut[];
  loading: boolean;
  error: number | null;
  showTenant: boolean;
  currentTenant: string | undefined;
  onRetry: () => void;
  onRevoke: (device: DeviceOut) => void;
  onReissue: (device: DeviceOut) => void;
}

export const DeviceList: React.FC<Props> = ({
  devices, loading, error, showTenant, currentTenant, onRetry, onRevoke, onReissue,
}) => {
  const { t } = useTranslation('vpn');

  if (loading && devices.length === 0) {
    return (
      <Inline justify="center">
        <Spinner />
      </Inline>
    );
  }
  if (error !== null) {
    return (
      <EmptyState
        title={t('list.loadError')}
        action={<Button variant="secondary" onClick={onRetry}>{t('list.retry')}</Button>}
      />
    );
  }
  if (devices.length === 0) {
    return <EmptyState title={t('list.empty')} description={t('list.emptyHint')} />;
  }

  return (
    <Stack gap="inline">
      {devices.map((device) => {
        const Icon = TYPE_ICON[device.device_type];
        return (
          <Card key={device.device_uuid} padding="sm">
            <Inline justify="between" align="center" wrap>
              <Inline gap="stack" align="center">
                <Icon size={18} />
                <Stack gap="tight">
                  <span className="text-nkz-sm font-semibold text-nkz-text-primary">
                    {device.display_name || t('list.unnamed')}
                  </span>
                  <span className="text-nkz-xs font-mono text-nkz-text-secondary break-all">{device.device_uuid}</span>
                </Stack>
              </Inline>
              <Inline gap="inline" align="center" wrap>
                <Badge>{t(`type.${device.device_type}`)}</Badge>
                {showTenant && <Badge intent="info">{device.tenant_id}</Badge>}
                <StateBadge state={device.state} />
                <NodeStatus device={device} />
                {device.state === 'CLAIMED' && device.device_type !== 'sensor' && !device.node &&
                  !device.network_unknown && device.tenant_id === currentTenant && (
                  <Button variant="ghost" size="sm" onClick={() => onReissue(device)} leadingIcon={<KeyRound size={14} />}>
                    {t('list.reissue')}
                  </Button>
                )}
                {device.state !== 'REVOKED' && device.tenant_id === currentTenant && (
                  <Button variant="ghost" size="sm" onClick={() => onRevoke(device)}
                    leadingIcon={<Trash2 size={14} />} aria-label={t('list.revoke')}>
                    {t('list.revoke')}
                  </Button>
                )}
              </Inline>
            </Inline>
          </Card>
        );
      })}
    </Stack>
  );
};
