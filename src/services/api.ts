/**
 * Device Management API client.
 *
 * The API origin is a runtime value injected by the host page
 * (window.__ENV__.VITE_API_URL). Calls carry the session cookie, which is
 * host-only on the API host — a relative /api call from the frontend host
 * would go out without credentials. The api-gateway adds the tenant and
 * signature headers; the client never sends them.
 */
import type {
  ClaimOut,
  DeviceEventOut,
  DeviceListOut,
  DeviceOut,
  DeviceType,
  NetworkOut,
  RegisterDeviceOut,
  ValidateOut,
} from '../types/vpn';

declare global {
  interface Window {
    __ENV__?: { VITE_API_URL?: string };
  }
}

function apiBase(): string {
  const runtime = typeof window !== 'undefined' ? window.__ENV__?.VITE_API_URL : undefined;
  const buildTime = (import.meta as { env?: Record<string, string | undefined> }).env?.VITE_API_URL;
  return `${(runtime ?? buildTime ?? '').replace(/\/$/, '')}/api/vpn`;
}

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(detail || `HTTP ${status}`);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new ApiError(res.status, typeof body.detail === 'string' ? body.detail : '');
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) });
const id = (uuid: string) => encodeURIComponent(uuid);

export const vpnApi = {
  listDevices: (allTenants = false) =>
    request<DeviceListOut>(`/devices${allTenants ? '?all_tenants=true' : ''}`),
  getDevice: (uuid: string) => request<DeviceOut>(`/devices/${id(uuid)}`),
  listEvents: (uuid: string) => request<{ events: DeviceEventOut[] }>(`/devices/${id(uuid)}/events`),
  validateDevice: (body: { device_uuid: string; claim_code: string }) => post<ValidateOut>('/devices/validate', body),
  claimDevice: (body: { device_uuid: string; claim_code: string; display_name?: string }) =>
    post<ClaimOut>('/devices/claim', body),
  reissueKey: (uuid: string) => post<NetworkOut>(`/devices/${id(uuid)}/reissue-key`, {}),
  revokeDevice: (uuid: string) => request<void>(`/devices/${id(uuid)}`, { method: 'DELETE' }),
  registerDevice: (body: { device_uuid: string; device_type: DeviceType; tenant_id: string; display_name?: string }) =>
    post<RegisterDeviceOut>('/factory/register-device', body),
};
