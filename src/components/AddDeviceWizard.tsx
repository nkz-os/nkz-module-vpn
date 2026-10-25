import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Input, Stack, Inline } from '@nekazari/ui-kit';
import { ApiError, vpnApi } from '../services/api';
import type { ClaimOut } from '../types/vpn';
import { claimErrorKey, joinCommand } from '../lib/format';
import { CopyButton } from './CopyButton';

type Step = 'form' | 'success' | 'error';

interface Props {
  onClose: () => void;
  onActivated: () => void;
}

export const AddDeviceWizard: React.FC<Props> = ({ onClose, onActivated }) => {
  const { t } = useTranslation('vpn');
  const [step, setStep] = useState<Step>('form');
  const [uuid, setUuid] = useState('');
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ClaimOut | null>(null);
  const [errorKey, setErrorKey] = useState('wizard.error.generic');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const body = { device_uuid: uuid.trim(), claim_code: code.trim().toUpperCase() };
    try {
      await vpnApi.validateDevice(body); // fast feedback on a typo before any key is created
      const claimed = await vpnApi.claimDevice({ ...body, display_name: name.trim() || undefined });
      setResult(claimed);
      setStep('success');
      onActivated();
    } catch (err: unknown) {
      setErrorKey(claimErrorKey(err instanceof ApiError ? err.status : undefined));
      setStep('error');
    } finally {
      setBusy(false);
    }
  };

  if (step === 'success' && result) {
    const network = result.network;
    const command = network ? joinCommand(network) : '';
    return (
      <Card padding="lg">
        <Stack gap="stack">
          <span className="text-nkz-lg font-semibold text-nkz-text-primary">{t('wizard.successTitle')}</span>
          {network && (
            <Stack gap="inline">
              <span className="text-nkz-sm font-semibold text-nkz-text-primary">{t('wizard.keyTitle')}</span>
              <span className="text-nkz-xs text-nkz-text-secondary">
                {t('wizard.expires', { when: new Date(network.expires_at).toLocaleString() })}
              </span>
              <span className="text-nkz-sm text-nkz-text-secondary">{t('wizard.command')}</span>
              <Inline gap="inline" align="center" wrap>
                <code className="text-nkz-xs font-mono break-all">{command}</code>
                <CopyButton value={command} />
              </Inline>
            </Stack>
          )}
          <span className="text-nkz-xs text-nkz-text-secondary break-all">
            {t('wizard.entityId')}: <span className="font-mono">{result.ngsi_entity_id}</span>
          </span>
          <Inline justify="end">
            <Button onClick={onClose}>{t('wizard.close')}</Button>
          </Inline>
        </Stack>
      </Card>
    );
  }

  if (step === 'error') {
    return (
      <Card padding="lg">
        <Stack gap="stack">
          <span className="text-nkz-lg font-semibold text-nkz-text-primary">{t('wizard.errorTitle')}</span>
          <span className="text-nkz-sm text-nkz-text-secondary">{t(errorKey)}</span>
          <Inline justify="end" gap="inline">
            <Button variant="ghost" onClick={onClose}>{t('wizard.cancel')}</Button>
            <Button onClick={() => setStep('form')}>{t('wizard.tryAgain')}</Button>
          </Inline>
        </Stack>
      </Card>
    );
  }

  return (
    <Card padding="lg">
      <form onSubmit={submit}>
        <Stack gap="stack">
          <span className="text-nkz-lg font-semibold text-nkz-text-primary">{t('wizard.title')}</span>
          <span className="text-nkz-sm text-nkz-text-secondary">{t('wizard.intro')}</span>
          <label className="text-nkz-sm text-nkz-text-primary">
            {t('wizard.uuidLabel')}
            <Input value={uuid} onChange={(e) => setUuid(e.target.value)} placeholder={t('wizard.uuidPh')}
              autoComplete="off" spellCheck={false} required />
          </label>
          <label className="text-nkz-sm text-nkz-text-primary">
            {t('wizard.claimLabel')}
            <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder={t('wizard.claimPh')} autoComplete="off" spellCheck={false} required />
            <span className="text-nkz-xs text-nkz-text-secondary">{t('wizard.claimHint')}</span>
          </label>
          <label className="text-nkz-sm text-nkz-text-primary">
            {t('wizard.nameLabel')}
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('wizard.namePh')}
              maxLength={128} />
          </label>
          <Inline justify="end" gap="inline">
            <Button type="button" variant="ghost" onClick={onClose}>{t('wizard.cancel')}</Button>
            <Button type="submit" loading={busy} disabled={busy || !uuid.trim() || !code.trim()}>
              {busy ? t('wizard.submitting') : t('wizard.submit')}
            </Button>
          </Inline>
        </Stack>
      </form>
    </Card>
  );
};
