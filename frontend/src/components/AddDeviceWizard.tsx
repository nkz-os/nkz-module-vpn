import React, { useState, useMemo } from 'react';
import { X, Wifi, CheckCircle, AlertCircle, Copy, Check } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';
import { vpnApi, ClaimResponse, DeviceType } from '../services/api';

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

type Step = 'form' | 'success' | 'error';

export const AddDeviceWizard: React.FC<Props> = ({ onClose, onSuccess }) => {
  const { t } = useTranslation('vpn');
  const deviceTypeLabels: Record<DeviceType, string> = useMemo(
    () => ({
      rover: t('wizard.typeRover'),
      gateway: t('wizard.typeGateway'),
      sensor_esp32: t('wizard.typeEsp32'),
    }),
    [t]
  );
  const [step, setStep] = useState<Step>('form');
  const [uuid, setUuid] = useState('');
  const [claimCode, setClaimCode] = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ClaimResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [copied, setCopied] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await vpnApi.claimDevice({
        device_uuid: uuid.trim(),
        claim_code: claimCode.trim().toUpperCase(),
        device_name: deviceName.trim() || undefined,
      });
      setResult(res);
      setStep('success');
      onSuccess();
    } catch (err: any) {
      const msg = err.message || '';
      if (msg.includes('Too many claim attempts')) {
        setErrorMsg(t('wizard.errorRateLimit'));
      } else if (msg.includes('quota exceeded')) {
        setErrorMsg(t('wizard.errorQuotaExceeded', { used: 0, max: 0 }));
      } else if (msg.includes('already activated') || msg.includes('409')) {
        setErrorMsg(t('wizard.errorDeviceAlreadyActivated'));
      } else if (msg.includes('revoked') || msg.includes('410')) {
        setErrorMsg(t('wizard.errorDeviceRevoked'));
      } else {
        setErrorMsg(err.message || t('wizard.errorGeneric'));
      }
      setStep('error');
    } finally {
      setLoading(false);
    }
  };

  const copyKey = () => {
    if (result?.preauth_key) {
      navigator.clipboard.writeText(result.preauth_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <Wifi className="w-5 h-5 text-sky-600" />
            <h2 className="text-lg font-semibold text-gray-900">{t('wizard.title')}</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5">
          {step === 'form' && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="text-sm text-gray-600">{t('wizard.formIntro')}</p>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('wizard.uuidLabel')} <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={uuid}
                  onChange={e => setUuid(e.target.value)}
                  placeholder={t('wizard.uuidPh')}
                  required
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('wizard.claimLabel')} <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={claimCode}
                  onChange={e => setClaimCode(e.target.value.toUpperCase())}
                  placeholder={t('wizard.claimPh')}
                  required
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono tracking-wider focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
                <p className="text-xs text-gray-400 mt-1">{t('wizard.claimHint')}</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('wizard.nameLabel')}
                </label>
                <input
                  type="text"
                  value={deviceName}
                  onChange={e => setDeviceName(e.target.value)}
                  placeholder={t('wizard.namePh')}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <button
                type="submit"
                disabled={loading || !uuid.trim() || !claimCode.trim()}
                className="w-full bg-sky-600 text-white rounded-lg py-2.5 text-sm font-medium hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? t('wizard.submitting') : t('wizard.submit')}
              </button>
            </form>
          )}

          {step === 'success' && result && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <CheckCircle className="w-8 h-8 text-green-500 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">{t('wizard.successTitle')}</p>
                  <p className="text-sm text-gray-500">{result.device_name || result.device_uuid}</p>
                </div>
              </div>

              <div className="bg-gray-50 rounded-lg p-3 space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">{t('list.colType')}</span>
                  <span className="font-medium">{deviceTypeLabels[result.device_type]}</span>
                </div>
                {result.ngsi_entity_id && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">{t('wizard.entityId')}</span>
                    <span className="font-mono text-xs truncate max-w-48">{result.ngsi_entity_id}</span>
                  </div>
                )}
              </div>

              {result.preauth_key && (
                <div>
                  <p className="text-sm font-medium text-gray-700 mb-1">
                    {t('wizard.preauthTitle')}{' '}
                    <span className="text-amber-600 font-normal">{t('wizard.preauthHint')}</span>
                  </p>
                  <div className="flex gap-2">
                    <code className="flex-1 bg-gray-900 text-green-400 text-xs rounded-lg p-2.5 font-mono break-all">
                      {result.preauth_key}
                    </code>
                    <button
                      onClick={copyKey}
                      className="p-2 text-gray-500 hover:text-gray-700 border border-gray-300 rounded-lg transition-colors"
                      title={t('wizard.copyTitle')}
                    >
                      {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                  {result?.login_server && (
                    <p className="text-xs text-gray-400 mt-1">
                      <code className="text-gray-600">
                        {t('wizard.tailscaleCmd', { server: result.login_server ?? '' })}
                      </code>
                    </p>
                  )}
                </div>
              )}

              {!result.preauth_key && (
                <p className="text-sm text-gray-600 bg-blue-50 border border-blue-100 rounded-lg p-3">
                  {t('wizard.esp32Note')}
                </p>
              )}

              <button
                onClick={onClose}
                className="w-full border border-gray-300 text-gray-700 rounded-lg py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                {t('wizard.close')}
              </button>
            </div>
          )}

          {step === 'error' && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <AlertCircle className="w-8 h-8 text-red-500 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-gray-900">{t('wizard.errorTitle')}</p>
                  <p className="text-sm text-red-600">{errorMsg}</p>
                </div>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => setStep('form')}
                  className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm font-medium hover:bg-gray-50 transition-colors"
                >
                  {t('wizard.tryAgain')}
                </button>
                <button
                  onClick={onClose}
                  className="flex-1 bg-gray-100 text-gray-700 rounded-lg py-2 text-sm font-medium hover:bg-gray-200 transition-colors"
                >
                  {t('wizard.close')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AddDeviceWizard;
