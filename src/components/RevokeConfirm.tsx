import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Input, Inline, Stack } from '@nekazari/ui-kit';
import { ApiError, vpnApi } from '../services/api';
import type { DeviceOut } from '../types/vpn';

interface Props {
  device: DeviceOut;
  onCancel: () => void;
  onRevoked: () => void;
}

/** Revocation is irreversible: the operator types the device UUID to confirm. */
export const RevokeConfirm: React.FC<Props> = ({ device, onCancel, onRevoked }) => {
  const { t } = useTranslation('vpn');
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const confirm = async () => {
    setBusy(true);
    setFailure(null);
    try {
      await vpnApi.revokeDevice(device.device_uuid);
      onRevoked();
    } catch (err: unknown) {
      setFailure(err instanceof ApiError ? err.detail || `HTTP ${err.status}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card padding="lg">
      <Stack gap="stack">
        <span className="text-nkz-lg font-semibold text-nkz-text-primary">{t('revoke.title')}</span>
        <span className="text-nkz-sm text-nkz-text-secondary">{t('revoke.consequences')}</span>
        <span className="text-nkz-xs font-mono text-nkz-text-secondary break-all">{device.device_uuid}</span>
        <label className="text-nkz-sm text-nkz-text-primary">
          {t('revoke.confirmInstruction')}
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} />
        </label>
        {failure && <span className="text-nkz-sm text-nkz-danger">{t('revoke.failed', { message: failure })}</span>}
        <Inline justify="end" gap="inline">
          <Button variant="ghost" onClick={onCancel}>{t('revoke.cancel')}</Button>
          <Button variant="danger" loading={busy} disabled={busy || typed.trim() !== device.device_uuid}
            onClick={confirm}>
            {busy ? t('revoke.confirming') : t('revoke.confirm')}
          </Button>
        </Inline>
      </Stack>
    </Card>
  );
};
