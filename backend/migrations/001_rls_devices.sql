-- Enable Row-Level Security on provisioned_devices.
-- Run once: psql -h localhost -U postgres -d nekazari -f 001_rls_devices.sql

BEGIN;

ALTER DATABASE nekazari SET app.current_tenant_id TO '';

ALTER TABLE provisioned_devices ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON provisioned_devices;
CREATE POLICY tenant_isolation ON provisioned_devices
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true));

-- Allow platform to run un-scoped queries (PlatformAdmin cross-tenant view).
DROP POLICY IF EXISTS platform_bypass ON provisioned_devices;
CREATE POLICY platform_bypass ON provisioned_devices
    FOR ALL
    USING (current_setting('app.current_tenant_id', true) = '__platform__');

COMMIT;
