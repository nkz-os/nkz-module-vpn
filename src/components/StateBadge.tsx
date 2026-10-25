import React from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@nekazari/ui-kit';
import type { DeviceOut } from '../types/vpn';
import { relativeTime } from '../lib/format';

const STATE_INTENT = { PENDING: 'warning', CLAIMED: 'positive', REVOKED: 'negative' } as const;

export const StateBadge: React.FC<{ state: DeviceOut['state'] }> = ({ state }) => {
  const { t } = useTranslation('vpn');
  return <Badge intent={STATE_INTENT[state]}>{t(`state.${state}`)}</Badge>;
};

/** Network line for an active device: online/offline + last seen, or "not joined yet". */
export const NodeStatus: React.FC<{ device: DeviceOut }> = ({ device }) => {
  const { t } = useTranslation('vpn');
  if (device.state !== 'CLAIMED' || device.device_type === 'sensor') return null;
  if (!device.node) return <Badge intent="default">{t('list.notJoined')}</Badge>;
  const seen = device.node.last_seen ? relativeTime(device.node.last_seen) : null;
  return (
    <>
      <Badge intent={device.node.online ? 'positive' : 'default'}>
        {device.node.online ? t('list.online') : t('list.offline')}
      </Badge>
      {seen && !device.node.online && (
        <span className="text-nkz-xs text-nkz-text-secondary">
          {t('list.lastSeen', { when: t(seen.key, { n: seen.n }) })}
        </span>
      )}
    </>
  );
};
