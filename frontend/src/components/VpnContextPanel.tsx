import React, { useEffect, useState } from 'react';
import { Wifi, WifiOff, Clock, Shield, AlertCircle } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';
import { vpnApi, Device } from '../services/api';

interface Props {
  /** NGSI-LD entity ID, e.g. "urn:ngsi-ld:Robot:aa:bb:cc:dd:ee:ff" */
  entityId?: string;
  entityType?: string;
}

/**
 * Context-panel slot component.
 * Shown in the right panel when a Robot or IoTGateway entity is selected.
 * Extracts the device UUID from the NGSI-LD entity ID and shows live VPN status.
 */
export const VpnContextPanel: React.FC<Props> = ({ entityId }) => {
  const { t } = useTranslation('vpn');
  const [device, setDevice] = useState<Device | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  // Extract UUID from urn:ngsi-ld:Robot:<uuid> or urn:ngsi-ld:IoTGateway:<uuid>
  const deviceUuid = entityId
    ? entityId.split(':').slice(3).join(':')
    : null;

  useEffect(() => {
    if (!deviceUuid) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setNotFound(false);
    vpnApi.getDeviceStatus(deviceUuid)
      .then(d => setDevice(d))
      .catch(err => {
        if (err.message?.includes('404') || err.message?.includes('not found')) {
          setNotFound(true);
        }
      })
      .finally(() => setLoading(false));
  }, [deviceUuid]);

  if (!deviceUuid) return null;

  if (loading) {
    return (
      <div className="p-3 border-t border-gray-100 animate-pulse">
        <div className="h-3 bg-gray-200 rounded w-20 mb-2" />
        <div className="h-4 bg-gray-200 rounded w-28" />
      </div>
    );
  }

  if (notFound || !device) {
    return (
      <div className="p-3 border-t border-gray-100">
        <div className="flex items-center gap-2 text-gray-400">
          <Shield className="w-4 h-4" />
          <span className="text-xs">{t('context.notInSdn')}</span>
        </div>
        <p className="text-xs text-gray-400 mt-1">{t('context.notProvisioned')}</p>
      </div>
    );
  }

  const isEsp32 = device.device_type === 'sensor_esp32';

  return (
    <div className="p-3 border-t border-gray-100 space-y-2">
      <div className="flex items-center gap-2">
        <Shield className="w-4 h-4 text-sky-600" />
        <span className="text-xs font-medium text-gray-700">{t('context.networkStatus')}</span>
      </div>

      {/* State badge */}
      <div className="flex items-center gap-2">
        {device.state === 'CONSUMED' ? (
          isEsp32 ? (
            <span className="text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full">mTLS Connected</span>
          ) : device.online ? (
            <span className="flex items-center gap-1 text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded-full">
              <Wifi className="w-3 h-3" /> {t('list.online')}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
              <WifiOff className="w-3 h-3" /> {t('list.offline')}
            </span>
          )
        ) : device.state === 'PENDING' ? (
          <span className="flex items-center gap-1 text-xs text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">
            <AlertCircle className="w-3 h-3" /> {t('context.pendingActivation')}
          </span>
        ) : (
          <span className="text-xs text-red-600 bg-red-50 px-2 py-0.5 rounded-full">{t('context.revoked')}</span>
        )}
      </div>

      {/* Last seen */}
      {!isEsp32 && device.last_seen && (
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <Clock className="w-3 h-3" />
          Last seen: {new Date(device.last_seen).toLocaleString()}
        </div>
      )}

      {/* Headscale peer ID */}
      {device.headscale_peer_id && (
        <div className="text-xs text-gray-400 font-mono truncate" title={device.headscale_peer_id}>
          {t('context.peer', { id: device.headscale_peer_id })}
        </div>
      )}
    </div>
  );
};

export default VpnContextPanel;
