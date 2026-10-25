import { afterEach, describe, expect, it, vi } from 'vitest';

async function load() {
  vi.resetModules();
  return import('./api');
}

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('vpnApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('calls the runtime API origin with the session cookie', async () => {
    vi.stubGlobal('window', { __ENV__: { VITE_API_URL: 'https://api.example.test/' } });
    const fetchMock = stubFetch(200, { devices: [], total: 0 });
    const { vpnApi } = await load();
    await vpnApi.listDevices();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.test/api/vpn/devices');
    expect(init.credentials).toBe('include');
  });

  it('asks for every tenant only when requested', async () => {
    vi.stubGlobal('window', { __ENV__: { VITE_API_URL: 'https://api.example.test' } });
    const fetchMock = stubFetch(200, { devices: [], total: 0 });
    const { vpnApi } = await load();
    await vpnApi.listDevices(true);
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.test/api/vpn/devices?all_tenants=true');
  });

  it('posts the claim as JSON', async () => {
    vi.stubGlobal('window', { __ENV__: { VITE_API_URL: 'https://api.example.test' } });
    const fetchMock = stubFetch(200, { state: 'CLAIMED' });
    const { vpnApi } = await load();
    await vpnApi.claimDevice({ device_uuid: 'u', claim_code: 'V1-AAAAAAAA' });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.test/api/vpn/devices/claim');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ device_uuid: 'u', claim_code: 'V1-AAAAAAAA' });
  });

  it('turns an error response into ApiError with status and detail', async () => {
    vi.stubGlobal('window', { __ENV__: { VITE_API_URL: 'https://api.example.test' } });
    stubFetch(404, { detail: 'Device not found' });
    const { vpnApi, ApiError } = await load();
    const err = await vpnApi.getDevice('u').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as InstanceType<typeof ApiError>).status).toBe(404);
    expect((err as InstanceType<typeof ApiError>).detail).toBe('Device not found');
  });

  it('returns nothing for 204', async () => {
    vi.stubGlobal('window', { __ENV__: { VITE_API_URL: 'https://api.example.test' } });
    stubFetch(204, null);
    const { vpnApi } = await load();
    await expect(vpnApi.revokeDevice('u')).resolves.toBeUndefined();
  });
});
