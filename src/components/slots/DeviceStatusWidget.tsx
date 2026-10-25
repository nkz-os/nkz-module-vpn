import React from 'react';
import { useTranslation } from 'react-i18next';
import { Badge, Card, Inline, Spinner, Stack } from '@nekazari/ui-kit';
import { useDevices } from '../../hooks/useDevices';

/** Dashboard card: how many devices are active, pending and online. */
export const DeviceStatusWidget: React.FC = () => {
  const { t } = useTranslation('vpn');
  const { devices, loading, error } = useDevices(false);
  const active = devices.filter((d) => d.state === 'CLAIMED');
  const pending = devices.filter((d) => d.state === 'PENDING').length;
  const online = active.filter((d) => d.node?.online).length;

  return (
    <Card padding="md">
      <Stack gap="inline">
        <span className="text-nkz-sm font-semibold text-nkz-text-primary">{t('widget.title')}</span>
        {loading && devices.length === 0 ? (
          <Spinner size="sm" />
        ) : error !== null ? (
          <span className="text-nkz-xs text-nkz-text-secondary">{t('widget.loadError')}</span>
        ) : devices.length === 0 ? (
          <span className="text-nkz-xs text-nkz-text-secondary">{t('widget.empty')}</span>
        ) : (
          <Inline gap="inline" wrap>
            <Badge intent="positive">{t('widget.active', { n: active.length })}</Badge>
            <Badge intent="warning">{t('widget.pending', { n: pending })}</Badge>
            <Badge intent="info">{t('widget.online', { n: online })}</Badge>
          </Inline>
        )}
      </Stack>
    </Card>
  );
};
