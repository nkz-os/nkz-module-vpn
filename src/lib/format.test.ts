import { describe, expect, it } from 'vitest';
import { claimErrorKey, joinCommand, relativeTime } from './format';

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
