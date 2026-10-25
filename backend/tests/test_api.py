"""Application surface: health probe and generated API docs."""


async def test_health_check(api):
    r = await api.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["service"] == "Device Management"


async def test_docs_available(api):
    r = await api.get("/api/vpn/docs")
    assert r.status_code == 200


async def test_openapi_lists_factory_routes(api):
    r = await api.get("/api/vpn/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/vpn/factory/register-device" in paths
    assert "/api/vpn/factory/sign-csr" in paths
