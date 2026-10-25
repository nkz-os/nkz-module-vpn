import { describe, expect, it } from 'vitest';
import { claimErrorKey, entityDeviceUuid, joinCommand, relativeTime, revokeErrorKey } from './format';

describe('relativeTime', () => {
  const now = new Date('2026-10-25T12:00:00Z');
  it('buckets by minutes, hours and days', () => {
    expect(relativeTime('2026-10-25T11:59:40Z', now)).toEqual({ key: 'list.justNow' });
    expect(relativeTime('2026-10-25T11:45:00Z', now)).toEqual({ key: 'list.minutesAgo', n: 15 });
    expect(relativeTime('2026-10-25T09:00:00Z', now)).toEqual({ key: 'list.hoursAgo', n: 3 });
    expect(relativeTime('2026-10-22T12:00:00Z', now)).toEqual({ key: 'list.daysAgo', n: 3 });
  });
});

describe('claimErrorKey', () => {
  it('maps known statuses and falls back to generic', () => {
    expect(claimErrorKey(400)).toBe('wizard.error.400');
    expect(claimErrorKey(429)).toBe('wizard.error.429');
    expect(claimErrorKey(503)).toBe('wizard.error.503');
    expect(claimErrorKey(500)).toBe('wizard.error.generic');
    expect(claimErrorKey(undefined)).toBe('wizard.error.generic');
  });
});

describe('joinCommand', () => {
  it('builds the tailscale command the device must run', () => {
    expect(
      joinCommand({ login_server: 'https://vpn.example.test', preauth_key: 'k', hostname: 'h', expires_at: 'x' }),
    ).toBe('sudo tailscale up --login-server=https://vpn.example.test --authkey=k --hostname=h --accept-routes');
  });
});

describe('entityDeviceUuid', () => {
  it('takes the device UUID from a twin id and ignores anything else', () => {
    const u = '3f1c2a9e-7b4d-4c1e-9a2b-1d2e3f4a5b6c';
    expect(entityDeviceUuid(`urn:ngsi-ld:ManufacturingMachine:acme:${u}`)).toBe(u);
    expect(entityDeviceUuid(`urn:ngsi-ld:Device:acme:${u}`)).toBe(u);
    expect(entityDeviceUuid('urn:ngsi-ld:ManufacturingMachine:acme:tractor-7')).toBeNull();
    expect(entityDeviceUuid(null)).toBeNull();
  });
});

describe('revokeErrorKey', () => {
  it('maps known statuses and falls back to generic', () => {
    expect(revokeErrorKey(404)).toBe('revoke.error.404');
    expect(revokeErrorKey(409)).toBe('revoke.error.409');
    expect(revokeErrorKey(502)).toBe('revoke.error.502');
    expect(revokeErrorKey(500)).toBe('revoke.error.generic');
  });
});
