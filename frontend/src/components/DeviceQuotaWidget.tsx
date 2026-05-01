import React, { useEffect, useState } from 'react';
import { HardDrive } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';
import { vpnApi, Device } from '../services/api';

export const DeviceQuotaWidget: React.FC = () => {
  const { t } = useTranslation('vpn');
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const maxDevices = 50;

  useEffect(() => {
    vpnApi.listDevices()
      .then(d => setDevices(d.devices))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4 animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-24 mb-3" />
        <div className="h-8 bg-gray-200 rounded w-16" />
      </div>
    );
  }

  const used = devices.filter(d => d.state !== 'REVOKED').length;
  const pct = maxDevices > 0 ? (used / maxDevices) * 100 : 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gray-100 rounded-lg flex items-center justify-center">
            <HardDrive className="w-4 h-4 text-gray-600" />
          </div>
          <span className="text-sm font-medium text-gray-700">{t('page.quotaBadge', { used, max: maxDevices })}</span>
        </div>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-2">
        <div className={`h-2 rounded-full transition-all ${pct >= 100 ? 'bg-red-500' : pct >= 80 ? 'bg-amber-500' : 'bg-green-500'}`}
          style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
    </div>
  );
};

export default DeviceQuotaWidget;
