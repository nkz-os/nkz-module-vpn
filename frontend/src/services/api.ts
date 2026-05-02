/**
 * NKZ VPN Module API Client
 *
 * Provides type-safe access to the nkz-network-controller backend.
 * Requests are authenticated via the httpOnly cookie (nkz_token).
 */

// =============================================================================
// Types
// =============================================================================

export type DeviceType = 'rover' | 'gateway' | 'sensor_esp32';
export type DeviceState = 'PENDING' | 'CONSUMED' | 'REVOKED';

export interface Device {
  device_uuid: string;
  device_type: DeviceType;
  device_name: string | null;
  state: DeviceState;
  headscale_peer_id: string | null;
  online: boolean;
  last_seen: string | null;
  tenant_id?: string | null;
}

export interface DeviceListResponse {
  devices: Device[];
  total: number;
  max_devices: number;
}

export interface ClaimRequest {
  device_uuid: string;
  claim_code: string;
  device_name?: string;
}

export interface ClaimResponse {
  device_uuid: string;
  device_type: DeviceType;
  device_name: string | null;
  preauth_key: string | null;
  login_server: string | null;
  ngsi_entity_id: string | null;
  state: DeviceState;
}

// =============================================================================
// Tenant ID resolver
// =============================================================================

function getTenantId(): string | null {
  const ctx = (window as any).__nekazariAuthContext;
  return ctx?.tenantId || null;
}

// =============================================================================
// API Client
// =============================================================================

class VpnApiClient {
  private readonly base = '/api/vpn';

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const tenantId = getTenantId();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };
    if (tenantId) headers['X-Tenant-ID'] = tenantId;

    const res = await fetch(`${this.base}${endpoint}`, {
      ...options,
      credentials: 'include',
      headers,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error((err as any).detail || `API error: ${res.status}`);
    }
    if (res.status === 204) return undefined as unknown as T;
    return res.json();
  }

  /** List all provisioned devices for the current tenant */
  listDevices(allTenants = false): Promise<DeviceListResponse> {
    const qs = allTenants ? '?all_tenants=true' : '';
    return this.request(`/devices/${qs}`);
  }

  /** Get real-time status of a single device (includes Headscale online state) */
  getDeviceStatus(uuid: string): Promise<Device> {
    return this.request(`/devices/${encodeURIComponent(uuid)}/status`);
  }

  /** Activate a device using its Claim Code */
  claimDevice(req: ClaimRequest): Promise<ClaimResponse> {
    return this.request('/devices/claim', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  /** Revoke a device (removes from Headscale, marks REVOKED) */
  revokeDevice(uuid: string): Promise<void> {
    return this.request(`/devices/${encodeURIComponent(uuid)}`, { method: 'DELETE' });
  }
}

export const vpnApi = new VpnApiClient();
