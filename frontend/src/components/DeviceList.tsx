import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Wifi, WifiOff, Bot, Radio, Cpu, Trash2, RefreshCw, MoreHorizontal } from 'lucide-react';
import { useTranslation } from '@nekazari/sdk';
import { vpnApi, Device, DeviceType, DeviceState } from '../services/api';

interface Props {
  refreshTrigger: number;
}

const TYPE_ICONS: Record<DeviceType, React.ReactNode> = {
  rover: <Bot className="w-4 h-4" />,
  gateway: <Radio className="w-4 h-4" />,
  sensor_esp32: <Cpu className="w-4 h-4" />,
};

const STATE_STYLES: Record<DeviceState, string> = {
  PENDING: 'bg-amber-100 text-amber-800',
  CONSUMED: 'bg-green-100 text-green-800',
  REVOKED: 'bg-red-100 text-red-800',
};

function formatLastSeen(ts: string | null, t: (k: string, opts?: Record<string, unknown>) => string): string {
  if (!ts) return '—';
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return t('list.timeJustNow');
  if (diffMin < 60) return t('list.timeMinutesAgo', { n: diffMin });
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return t('list.timeHoursAgo', { n: diffH });
  return d.toLocaleDateString();
}

export const DeviceList: React.FC<Props> = ({ refreshTrigger }) => {
  const { t } = useTranslation('vpn');
  const typeLabels: Record<DeviceType, string> = useMemo(
    () => ({
      rover: t('list.typeRover'),
      gateway: t('list.typeGateway'),
      sensor_esp32: t('list.typeEsp32'),
    }),
    [t]
  );
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [liveStatuses, setLiveStatuses] = useState<Record<string, { online: boolean; last_seen: string | null }>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await vpnApi.listDevices();
      setDevices(data.devices);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch live Headscale status for CONSUMED KLinux devices
  const fetchLiveStatuses = useCallback(async (devs: Device[]) => {
    const klinux = devs.filter(d => d.state === 'CONSUMED' && d.headscale_peer_id);
    const statuses: Record<string, { online: boolean; last_seen: string | null }> = {};
    await Promise.allSettled(
      klinux.map(async d => {
        try {
          const live = await vpnApi.getDeviceStatus(d.device_uuid);
          statuses[d.device_uuid] = { online: live.online, last_seen: live.last_seen };
        } catch {
          statuses[d.device_uuid] = { online: false, last_seen: null };
        }
      })
    );
    setLiveStatuses(statuses);
  }, []);

  useEffect(() => {
    load().then(() => {});
  }, [load, refreshTrigger]);

  useEffect(() => {
    if (devices.length > 0) {
      fetchLiveStatuses(devices);
    }
  }, [devices, fetchLiveStatuses]);

  const handleRevoke = async (uuid: string, name: string | null) => {
    if (!confirm(t('list.revokeConfirm', { name: name || uuid }))) return;
    setRevoking(uuid);
    try {
      await vpnApi.revokeDevice(uuid);
      await load();
    } catch (e: any) {
      alert(t('list.revokeFailed', { message: e.message }));
    } finally {
      setRevoking(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="w-6 h-6 text-gray-400 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-600 text-sm">{error}</p>
        <button onClick={load} className="mt-3 text-sm text-sky-600 hover:underline">
          {t('list.retry')}
        </button>
      </div>
    );
  }

  if (devices.length === 0) {
    return (
      <div className="text-center py-16">
        <Wifi className="w-10 h-10 text-gray-300 mx-auto mb-3" />
        <p className="text-gray-500 text-sm">{t('list.empty')}</p>
        <p className="text-gray-400 text-xs mt-1">{t('list.emptyHint')}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-gray-600">{t('list.colName')}</th>
            <th className="px-4 py-3 text-left font-medium text-gray-600">{t('list.colUuid')}</th>
            <th className="px-4 py-3 text-left font-medium text-gray-600">{t('list.colType')}</th>
            <th className="px-4 py-3 text-left font-medium text-gray-600">{t('list.colState')}</th>
            <th className="px-4 py-3 text-left font-medium text-gray-600">{t('list.colConnectivity')}</th>
            <th className="px-4 py-3 text-left font-medium text-gray-600">{t('list.colLastSeen')}</th>
            <th className="px-4 py-3 text-left font-medium text-gray-600 w-12"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {devices.map(device => {
            const live = liveStatuses[device.device_uuid];
            const online = live?.online ?? false;
            const lastSeen = live?.last_seen ?? device.last_seen;
            const isEsp32 = device.device_type === 'sensor_esp32';

            return (
              <tr key={device.device_uuid} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 font-medium text-gray-900">
                  {device.device_name || <span className="text-gray-400 italic">{t('list.unnamed')}</span>}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-500 max-w-36 truncate" title={device.device_uuid}>
                  {device.device_uuid}
                </td>
                <td className="px-4 py-3">
                  <span className="flex items-center gap-1.5 text-gray-700">
                    {TYPE_ICONS[device.device_type]}
                    {typeLabels[device.device_type]}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATE_STYLES[device.state]}`}>
                    {device.state}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {device.state === 'CONSUMED' ? (
                    isEsp32 ? (
                      <span className="text-xs text-gray-500">{t('list.mtls')}</span>
                    ) : (
                      <span className={`flex items-center gap-1.5 text-xs ${online ? 'text-green-600' : 'text-gray-400'}`}>
                        {online
                          ? <><Wifi className="w-3.5 h-3.5" /> {t('list.online')}</>
                          : <><WifiOff className="w-3.5 h-3.5" /> {t('list.offline')}</>
                        }
                      </span>
                    )
                  ) : (
                    <span className="text-xs text-gray-400">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {isEsp32 ? <span className="text-gray-400">—</span> : formatLastSeen(lastSeen, t)}
                </td>
                <td className="px-4 py-3">
                  {device.state !== 'REVOKED' && (
                    <button
                      onClick={() => handleRevoke(device.device_uuid, device.device_name)}
                      disabled={revoking === device.device_uuid}
                      className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors disabled:opacity-50"
                      title={t('list.revokeTitle')}
                    >
                      {revoking === device.device_uuid
                        ? <MoreHorizontal className="w-4 h-4 animate-pulse" />
                        : <Trash2 className="w-4 h-4" />
                      }
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default DeviceList;
