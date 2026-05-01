-- Enable Row-Level Security on provisioned_devices.
-- Run once: psql -h localhost -U postgres -d nekazari -f 001_rls_devices.sql

BEGIN;

ALTER TABLE provisioned_devices ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON provisioned_devices;
CREATE POLICY tenant_isolation ON provisioned_devices
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id'))
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id'));

-- Allow platform to run un-scoped queries (PlatformAdmin cross-tenant view).
DROP POLICY IF EXISTS platform_bypass ON provisioned_devices;
CREATE POLICY platform_bypass ON provisioned_devices
    FOR ALL
    USING (current_setting('app.current_tenant_id') = '__platform__');

COMMIT;
