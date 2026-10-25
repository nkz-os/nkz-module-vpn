-- Device Management — provisioning registry and audit trail.
-- Applied by `python -m app.db.migrate` (initContainer) as the module's own role,
-- which owns this database. Idempotent.
--
-- Row-level security is FORCED: the owner role is subject to the policies too,
-- so a connection that forgets to set app.current_tenant_id sees nothing.

CREATE TABLE IF NOT EXISTS devices (
    device_uuid      uuid PRIMARY KEY,
    tenant_id        text NOT NULL,
    device_type      text NOT NULL CHECK (device_type IN ('rover', 'gateway', 'sensor')),
    display_name     text,
    claim_version    integer NOT NULL CHECK (claim_version >= 1),
    state            text NOT NULL CHECK (state IN ('PENDING', 'CLAIMED', 'REVOKED')),
    claimed_at       timestamptz,
    claimed_by       text,
    revoked_at       timestamptz,
    revoked_by       text,
    headscale_user   text,
    preauth_key_id   text,
    preauth_expires  timestamptz,
    node_id          text,
    node_hostname    text,
    node_ip          inet,
    ngsi_entity_id   text,
    ngsi_entity_type text,
    cert_fingerprint text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS devices_tenant_idx ON devices (tenant_id);

-- Append-only from the application's point of view (the repository exposes no
-- update or delete).
CREATE TABLE IF NOT EXISTS device_events (
    id          bigserial PRIMARY KEY,
    device_uuid uuid NOT NULL,
    tenant_id   text NOT NULL,
    action      text NOT NULL,
    actor_sub   text NOT NULL,
    ip          inet,
    details     jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS device_events_device_idx ON device_events (device_uuid, created_at);

ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE devices FORCE ROW LEVEL SECURITY;
ALTER TABLE device_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON devices;
CREATE POLICY tenant_isolation ON devices
    USING (tenant_id = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true));
DROP POLICY IF EXISTS platform_scope ON devices;
CREATE POLICY platform_scope ON devices
    USING (current_setting('app.current_tenant_id', true) = '__platform__');

DROP POLICY IF EXISTS tenant_isolation ON device_events;
CREATE POLICY tenant_isolation ON device_events
    USING (tenant_id = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true));
DROP POLICY IF EXISTS platform_scope ON device_events;
CREATE POLICY platform_scope ON device_events
    USING (current_setting('app.current_tenant_id', true) = '__platform__');
