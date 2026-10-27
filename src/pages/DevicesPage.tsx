import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@nekazari/sdk';
import { Button, Card, Inline, Stack, Switch } from '@nekazari/ui-kit';
import { Factory, Network, Plus, RefreshCw } from 'lucide-react';
import { useDevices } from '../hooks/useDevices';
import type { DeviceOut } from '../types/vpn';
import { AddDeviceWizard } from '../components/AddDeviceWizard';
import { DeviceList } from '../components/DeviceList';
import { FactoryPanel } from '../components/FactoryPanel';
import { ReissueKey } from '../components/ReissueKey';
import { RevokeConfirm } from '../components/RevokeConfirm';

const STEPS = ['step1', 'step2', 'step3', 'step4', 'step5'] as const;

export const DevicesPage: React.FC = () => {
  const { t } = useTranslation('vpn');
  const auth = useAuth();
  const isPlatformAdmin = auth.hasRole('PlatformAdmin');
  const [allTenants, setAllTenants] = useState(false);
  const [showWizard, setShowWizard] = useState(false);
  const [showFactory, setShowFactory] = useState(false);
  const [revoking, setRevoking] = useState<DeviceOut | null>(null);
  const [reissuing, setReissuing] = useState<DeviceOut | null>(null);
  const { devices, loading, error, refresh } = useDevices(isPlatformAdmin && allTenants);

  return (
    <Stack gap="section">
      <Inline justify="between" align="center" wrap>
        <Inline gap="stack" align="center">
          <Network size={24} />
          <Stack gap="tight">
            <span className="text-nkz-xl font-semibold text-nkz-text-primary">{t('page.title')}</span>
            <span className="text-nkz-sm text-nkz-text-secondary">{t('page.subtitle')}</span>
          </Stack>
        </Inline>
        <Inline gap="inline" align="center" wrap>
          {isPlatformAdmin && (
            <Switch checked={allTenants} onChange={setAllTenants} label={t('page.allTenants')} />
          )}
          <Button variant="ghost" onClick={refresh} leadingIcon={<RefreshCw size={16} />} aria-label={t('page.refresh')}>
            {t('page.refresh')}
          </Button>
          {isPlatformAdmin && (
            <Button variant="secondary" onClick={() => setShowFactory((v) => !v)} leadingIcon={<Factory size={16} />}>
              {t('factory.open')}
            </Button>
          )}
          <Button onClick={() => setShowWizard(true)} leadingIcon={<Plus size={16} />}>
            {t('page.addDevice')}
          </Button>
        </Inline>
      </Inline>

      {showWizard && <AddDeviceWizard onClose={() => setShowWizard(false)} onActivated={refresh} />}
      {showFactory && isPlatformAdmin && <FactoryPanel onRegistered={refresh} />}
      {reissuing && (
        <ReissueKey
          device={reissuing}
          onClose={() => {
            setReissuing(null);
            refresh();
          }}
        />
      )}
      {revoking && (
        <RevokeConfirm
          device={revoking}
          onCancel={() => setRevoking(null)}
          onRevoked={() => {
            setRevoking(null);
            refresh();
          }}
        />
      )}

      <Card padding="md">
        <Stack gap="inline">
          <span className="text-nkz-sm font-semibold text-nkz-text-primary">{t('page.howItWorks')}</span>
          <ol className="list-decimal pl-5 text-nkz-sm text-nkz-text-secondary">
            {STEPS.map((step) => (
              <li key={step}>{t(`page.${step}`)}</li>
            ))}
          </ol>
        </Stack>
      </Card>

      <Stack gap="inline">
        <span className="text-nkz-sm font-semibold text-nkz-text-primary">
          {t('page.devices')} · {t('page.count', { count: devices.length })}
        </span>
        <DeviceList
          devices={devices}
          loading={loading}
          error={error}
          showTenant={isPlatformAdmin && allTenants}
          currentTenant={auth.getTenantId()}
          onRetry={refresh}
          onRevoke={setRevoking}
          onReissue={setReissuing}
        />
      </Stack>
    </Stack>
  );
};
