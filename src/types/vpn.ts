/** Wire types of the Device Management API (/api/vpn). Mirror backend/app/api/*.py. */

export type DeviceType = 'rover' | 'gateway' | 'sensor';
export type DeviceState = 'PENDING' | 'CLAIMED' | 'REVOKED';

export interface NodeOut {
  online: boolean;
  last_seen: string | null;
  ip: string | null;
}

export interface DeviceOut {
  device_uuid: string;
  tenant_id: string;
  device_type: DeviceType;
  display_name: string | null;
  state: DeviceState;
  ngsi_entity_id: string | null;
  node: NodeOut | null;
}

export interface DeviceListOut {
  devices: DeviceOut[];
  total: number;
}

export interface ValidateOut {
  valid: boolean;
  device_uuid: string;
  device_type: DeviceType;
  display_name: string | null;
  state: DeviceState;
}

export interface NetworkOut {
  login_server: string;
  preauth_key: string;
  expires_at: string;
  hostname: string;
}

export interface ClaimOut {
  device_uuid: string;
  device_type: DeviceType;
  display_name: string | null;
  state: DeviceState;
  ngsi_entity_id: string;
  network: NetworkOut;
}

export interface RegisterDeviceOut {
  device_uuid: string;
  device_type: DeviceType;
  tenant_id: string;
  claim_code: string;
}

export interface DeviceEventOut {
  action: string;
  actor_sub: string;
  created_at: string;
  details: Record<string, unknown> | null;
}
