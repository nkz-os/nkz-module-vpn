import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Inline, Stack } from '@nekazari/ui-kit';
import { ApiError, vpnApi } from '../services/api';
import type { DeviceOut, NetworkOut } from '../types/vpn';
import { JoinInstructions } from './JoinInstructions';

interface Props {
  device: DeviceOut;
  onClose: () => void;
}

/** New one-time key for an active robot/gateway that has not joined the VPN yet. */
export const ReissueKey: React.FC<Props> = ({ device, onClose }) => {
  const { t } = useTranslation('vpn');
  const [busy, setBusy] = useState(false);
  const [network, setNetwork] = useState<NetworkOut | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  const reissue = async () => {
    setBusy(true);
    setErrorKey(null);
    try {
      setNetwork(await vpnApi.reissueKey(device.device_uuid));
    } catch (err: unknown) {
      const status = err instanceof ApiError ? err.status : undefined;
      setErrorKey(status === 409 ? 'reissue.error.409' : status === 502 ? 'reissue.error.502' : 'reissue.error.generic');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card padding="lg">
      <Stack gap="stack">
        <span className="text-nkz-lg font-semibold text-nkz-text-primary">{t('reissue.title')}</span>
        <span className="text-nkz-xs font-mono text-nkz-text-secondary break-all">{device.device_uuid}</span>
        {network ? (
          <JoinInstructions network={network} />
        ) : (
          <span className="text-nkz-sm text-nkz-text-secondary">{t('reissue.explain')}</span>
        )}
        {errorKey && <span className="text-nkz-sm text-nkz-danger">{t(errorKey)}</span>}
        <Inline justify="end" gap="inline">
          <Button variant="ghost" onClick={onClose}>{network ? t('wizard.close') : t('wizard.cancel')}</Button>
          {!network && (
            <Button loading={busy} disabled={busy} onClick={reissue}>
              {t('reissue.confirm')}
            </Button>
          )}
        </Inline>
      </Stack>
    </Card>
  );
};
