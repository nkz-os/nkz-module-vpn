import React, { useEffect, useState } from 'react';
import { Wifi, WifiOff, Monitor } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';
import { vpnApi, Device } from '../services/api';

/**
 * Dashboard widget slot component.
 * Shows a summary of connected field devices for the current tenant.
 */
export const VpnStatusWidget: React.FC = () => {
  const { t } = useTranslation('vpn');
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const fetch = () => vpnApi.listDevices()
      .then(d => { setDevices(d.devices); setError(false); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
    fetch();
    const interval = setInterval(fetch, 30000);
    return () => clearInterval(interval);
  }, []);

  const activated = devices.filter(d => d.state === 'CONSUMED');
  const pending = devices.filter(d => d.state === 'PENDING');
  const total = devices.length;

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4 animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-24 mb-3" />
        <div className="h-8 bg-gray-200 rounded w-16" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-xl border border-red-100 p-4">
        <p className="text-xs text-red-500">{t('widget.loadError')}</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-sky-50 rounded-lg flex items-center justify-center">
            <Monitor className="w-4 h-4 text-sky-600" />
          </div>
          <span className="text-sm font-medium text-gray-700">{t('widget.title')}</span>
        </div>
        <span className="text-2xl font-bold text-gray-900">{total}</span>
      </div>

      <div className="flex gap-3 text-xs">
        <span className="flex items-center gap-1 text-green-600">
          <Wifi className="w-3 h-3" />
          {t('widget.active', { n: activated.length })}
        </span>
        {pending.length > 0 && (
          <span className="flex items-center gap-1 text-amber-600">
            <WifiOff className="w-3 h-3" />
            {t('widget.pending', { n: pending.length })}
          </span>
        )}
      </div>

      {total === 0 && (
        <p className="text-xs text-gray-400 mt-1">{t('widget.empty')}</p>
      )}
    </div>
  );
};

export default VpnStatusWidget;
