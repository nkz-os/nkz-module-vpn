import React, { useState } from 'react';
import { Factory, Check, AlertCircle } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';

interface Props {
  onSuccess: () => void;
}

export const FactoryPanel: React.FC<Props> = ({ onSuccess }) => {
  const { t } = useTranslation('vpn');
  const [expanded, setExpanded] = useState(false);
  const [uuid, setUuid] = useState('');
  const [deviceType, setDeviceType] = useState('rover');
  const [tenantId, setTenantId] = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await fetch('/api/vpn/factory/register-device', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_uuid: uuid.trim(),
          device_type: deviceType,
          tenant_id: tenantId.trim(),
          device_name: deviceName.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as any).detail || `Error ${res.status}`);
      }
      const data = await res.json();
      setResult(data.claim_code);
      onSuccess();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!expanded) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <button onClick={() => setExpanded(true)}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900">
          <Factory className="w-4 h-4" />
          {t('factory.title')}
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Factory className="w-5 h-5 text-gray-600" />
          <h3 className="text-sm font-semibold text-gray-900">{t('factory.title')}</h3>
        </div>
        <button onClick={() => setExpanded(false)} className="text-gray-400 hover:text-gray-600 text-sm">{t('wizard.close')}</button>
      </div>
      <p className="text-xs text-gray-500">{t('factory.description')}</p>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('factory.uuidLabel')}</label>
          <input type="text" value={uuid} onChange={e => setUuid(e.target.value)} required
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-500" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('factory.typeLabel')}</label>
          <select value={deviceType} onChange={e => setDeviceType(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500">
            <option value="rover">{t('wizard.typeRover')}</option>
            <option value="gateway">{t('wizard.typeGateway')}</option>
            <option value="sensor_esp32">{t('wizard.typeEsp32')}</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('factory.tenantLabel')}</label>
          <input type="text" value={tenantId} onChange={e => setTenantId(e.target.value)} required
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">{t('factory.nameLabel')}</label>
          <input type="text" value={deviceName} onChange={e => setDeviceName(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
        </div>
        {result && (
          <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg p-3">
            <Check className="w-4 h-4 text-green-600" />
            <span className="text-sm text-green-700 font-mono">{t('factory.registerSuccess', { code: result })}</span>
          </div>
        )}
        {error && (
          <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg p-3">
            <AlertCircle className="w-4 h-4 text-red-500" />
            <span className="text-sm text-red-600">{error}</span>
          </div>
        )}
        <button type="submit" disabled={loading}
          className="w-full bg-gray-800 text-white rounded-lg py-2 text-sm font-medium hover:bg-gray-900 disabled:opacity-50 transition-colors">
          {loading ? t('factory.registering') : t('factory.registerDevice')}
        </button>
      </form>
    </div>
  );
};

export default FactoryPanel;
