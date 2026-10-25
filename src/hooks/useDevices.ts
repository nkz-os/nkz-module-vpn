import { useCallback, useEffect, useState } from 'react';
import { ApiError, vpnApi } from '../services/api';
import type { DeviceOut } from '../types/vpn';

export interface DevicesState {
  devices: DeviceOut[];
  loading: boolean;
  error: number | null; // HTTP status of the last failure, 0 for network errors
  refresh: () => void;
}

export function useDevices(allTenants: boolean): DevicesState {
  const [devices, setDevices] = useState<DeviceOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<number | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    vpnApi
      .listDevices(allTenants)
      .then((data) => {
        if (cancelled) return;
        setDevices(data.devices);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.status : 0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [allTenants, tick]);

  const refresh = useCallback(() => setTick((n) => n + 1), []);
  return { devices, loading, error, refresh };
}
