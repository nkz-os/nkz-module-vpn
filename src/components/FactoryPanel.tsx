import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Input, Inline, Select, Stack } from '@nekazari/ui-kit';
import { ApiError, vpnApi } from '../services/api';
import type { DeviceType } from '../types/vpn';
import { CopyButton } from './CopyButton';

const FACTORY_ERRORS = new Set([409, 422]);

/** PlatformAdmin only: register a device for an organisation and show its claim code. */
export const FactoryPanel: React.FC<{ onRegistered: () => void }> = ({ onRegistered }) => {
  const { t } = useTranslation('vpn');
  const [uuid, setUuid] = useState('');
  const [type, setType] = useState<DeviceType>('rover');
  const [tenant, setTenant] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setCode(null);
    setErrorKey(null);
    try {
      const res = await vpnApi.registerDevice({
        device_uuid: uuid.trim(),
        device_type: type,
        tenant_id: tenant.trim(),
        display_name: name.trim() || undefined,
      });
      setCode(res.claim_code);
      onRegistered();
    } catch (err: unknown) {
      const status = err instanceof ApiError ? err.status : undefined;
      setErrorKey(status !== undefined && FACTORY_ERRORS.has(status) ? `factory.error.${status}` : 'factory.error.generic');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card padding="lg">
      <form onSubmit={submit}>
        <Stack gap="stack">
          <span className="text-nkz-lg font-semibold text-nkz-text-primary">{t('factory.title')}</span>
          <span className="text-nkz-sm text-nkz-text-secondary">{t('factory.description')}</span>
          <label className="text-nkz-sm text-nkz-text-primary">
            {t('factory.uuidLabel')}
            <Input value={uuid} onChange={(e) => setUuid(e.target.value)} autoComplete="off" spellCheck={false}
              required />
          </label>
          <label className="text-nkz-sm text-nkz-text-primary">
            {t('factory.typeLabel')}
            <Select
              value={type}
              onValueChange={(v) => setType(v as DeviceType)}
              options={(['rover', 'gateway', 'sensor'] as const).map((v) => ({ value: v, label: t(`type.${v}`) }))}
            />
          </label>
          <label className="text-nkz-sm text-nkz-text-primary">
            {t('factory.tenantLabel')}
            <Input value={tenant} onChange={(e) => setTenant(e.target.value)} autoComplete="off" spellCheck={false}
              required />
          </label>
          <label className="text-nkz-sm text-nkz-text-primary">
            {t('factory.nameLabel')}
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={128} />
          </label>
          {code && (
            <Inline gap="inline" align="center" wrap>
              <span className="text-nkz-sm text-nkz-text-primary">{t('factory.success')}</span>
              <code className="text-nkz-sm font-mono font-semibold">{code}</code>
              <CopyButton value={code} />
            </Inline>
          )}
          {errorKey && <span className="text-nkz-sm text-nkz-danger">{t(errorKey)}</span>}
          <Inline justify="end">
            <Button type="submit" loading={busy} disabled={busy || !uuid.trim() || !tenant.trim()}>
              {busy ? t('factory.submitting') : t('factory.submit')}
            </Button>
          </Inline>
        </Stack>
      </form>
    </Card>
  );
};
