import React, { useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';

interface Props {
  deviceName: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  error?: string | null;
}

export const RevokeConfirmModal: React.FC<Props> = ({
  deviceName, onConfirm, onCancel, loading, error,
}) => {
  const { t } = useTranslation('vpn');
  const [typed, setTyped] = useState('');
  const canConfirm = typed === deviceName && !loading;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm">
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="w-5 h-5" />
            <h2 className="text-lg font-semibold">{t('revoke.title')}</h2>
          </div>
          <button onClick={onCancel} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-sm text-red-600">{t('revoke.consequences')}</p>
          <p className="text-sm text-gray-600">
            {t('revoke.confirmInstruction', { name: deviceName })}
          </p>
          {error && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg p-2.5">
              <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />
              <p className="text-xs text-red-600">{error}</p>
            </div>
          )}
          <input
            type="text"
            value={typed}
            onChange={e => setTyped(e.target.value)}
            placeholder={t('revoke.confirmPlaceholder')}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
            autoFocus
          />
          <div className="flex gap-3 pt-2">
            <button onClick={onCancel}
              className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm font-medium hover:bg-gray-50">
              {t('revoke.cancel')}
            </button>
            <button onClick={onConfirm} disabled={!canConfirm}
              className="flex-1 bg-red-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed">
              {loading ? '...' : t('revoke.confirm')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RevokeConfirmModal;
