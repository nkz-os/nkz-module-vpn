-- =============================================================================
-- nekazari-module-vpn: Database registration
-- =============================================================================
-- Run ONCE after deploying the module for the first time.
-- The provisioned_devices table is created by the app (SQLAlchemy create_all).
-- =============================================================================

-- 1. Register in marketplace_modules
INSERT INTO marketplace_modules (
    id,
    name,
    display_name,
    description,
    version,
    author,
    category,
    module_type,
    required_plan_type,
    pricing_tier,
    route_path,
    label,
    icon,
    required_roles,
    remote_entry_url,
    is_active,
    created_at
) VALUES (
    'vpn',
    'vpn',
    'Device Management',
    'Zero-Touch Provisioning for field devices via Headscale SDN. Add robots, gateways and sensors using a Claim Code.',
    '1.0.0',
    'Robotika Engineering',
    'connectivity',
    'ADDON_CORE',
    'free',
    'FREE',
    '/devices',
    'Devices',
    'wifi',
    ARRAY['TenantAdmin', 'PlatformAdmin'],
    '/modules/vpn/nekazari-module.js',
    true,
    NOW()
) ON CONFLICT (id) DO UPDATE SET
    display_name    = EXCLUDED.display_name,
    description     = EXCLUDED.description,
    version         = EXCLUDED.version,
    remote_entry_url = EXCLUDED.remote_entry_url,
    is_active       = EXCLUDED.is_active;

-- 2. Auto-enable for all existing tenants (optional — remove if manual activation preferred)
-- INSERT INTO tenant_installed_modules (tenant_id, module_id, enabled_at)
-- SELECT id, 'vpn', NOW() FROM tenants
-- ON CONFLICT (tenant_id, module_id) DO NOTHING;
