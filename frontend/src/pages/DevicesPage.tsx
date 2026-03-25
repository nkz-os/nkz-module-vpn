import React, { useState, useCallback } from 'react';
import { Wifi, Plus, RefreshCw } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';
import { DeviceList } from '../components/DeviceList';
import { AddDeviceWizard } from '../components/AddDeviceWizard';

/**
 * Main page for the VPN / Device Management module.
 * Registered as the `main` component for the `vpn` module.
 * Rendered by the host when the user navigates to /devices.
 */
export const DevicesPage: React.FC = () => {
  const { t } = useTranslation('vpn');
  const [showWizard, setShowWizard] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleSuccess = useCallback(() => {
    setRefreshTrigger(t => t + 1);
  }, []);

  const handleRefresh = useCallback(() => {
    setRefreshTrigger(t => t + 1);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Page header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-sky-100 rounded-xl flex items-center justify-center">
              <Wifi className="w-5 h-5 text-sky-600" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">{t('page.title')}</h1>
              <p className="text-sm text-gray-500">{t('page.subtitle')}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              title={t('page.refreshTitle')}
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={() => setShowWizard(true)}
              className="flex items-center gap-2 bg-sky-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-sky-700 transition-colors shadow-sm"
            >
              <Plus className="w-4 h-4" />
              {t('page.addDevice')}
            </button>
          </div>
        </div>

        {/* How it works — shown only to admin audience */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">{t('page.howItWorks')}</h2>
          <ol className="text-sm text-gray-600 space-y-1 list-decimal list-inside">
            <li>{t('page.step1')}</li>
            <li>{t('page.step2')}</li>
            <li>{t('page.step3')}</li>
            <li>{t('page.step4')}</li>
            <li>{t('page.step5')}</li>
          </ol>
        </div>

        {/* Device table */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">{t('page.provisionedDevices')}</h2>
          <DeviceList refreshTrigger={refreshTrigger} />
        </div>
      </div>

      {showWizard && (
        <AddDeviceWizard
          onClose={() => setShowWizard(false)}
          onSuccess={handleSuccess}
        />
      )}
    </div>
  );
};

export default DevicesPage;
