import type { NetworkOut } from '../types/vpn';

export interface RelativeTime {
  key: 'list.justNow' | 'list.minutesAgo' | 'list.hoursAgo' | 'list.daysAgo';
  n?: number;
}

export function relativeTime(iso: string, now: Date = new Date()): RelativeTime {
  const minutes = Math.floor((now.getTime() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return { key: 'list.justNow' };
  if (minutes < 60) return { key: 'list.minutesAgo', n: minutes };
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return { key: 'list.hoursAgo', n: hours };
  return { key: 'list.daysAgo', n: Math.floor(hours / 24) };
}

const CLAIM_ERRORS = new Set([400, 404, 409, 410, 422, 429, 502, 503]);

export function claimErrorKey(status: number | undefined): string {
  return status !== undefined && CLAIM_ERRORS.has(status) ? `wizard.error.${status}` : 'wizard.error.generic';
}

/** The one command a robot or gateway runs to join the platform VPN. */
export function joinCommand(network: NetworkOut): string {
  return [
    'sudo tailscale up',
    `--login-server=${network.login_server}`,
    `--authkey=${network.preauth_key}`,
    `--hostname=${network.hostname}`,
    '--accept-routes',
  ].join(' ');
}
