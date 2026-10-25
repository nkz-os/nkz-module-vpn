-- Device Management module registration (marketplace_modules) and migration
-- of installs from the legacy id `nkz-module-vpn`. Idempotent; one transaction.
-- Apply on the platform database as a superuser. The production copy lives in
-- the deployment configuration repository.

\echo '--- before'
SELECT id, version, route_path, required_roles, metadata ? 'api_prefix' AS routed
  FROM marketplace_modules WHERE id IN ('vpn', 'nkz-module-vpn');
SELECT module_id, count(*) FROM tenant_installed_modules
 WHERE module_id IN ('vpn', 'nkz-module-vpn') GROUP BY module_id;

BEGIN;

INSERT INTO marketplace_modules (
    id, name, display_name, description, remote_entry_url, scope, exposed_module, version, author,
    category, icon_url, route_path, label, required_plan_level, is_local, is_active,
    required_roles, metadata
) VALUES (
    'vpn', 'vpn', 'Device Management',
    'Zero-touch provisioning of field devices: register at the factory, claim with the code on the chassis, and join the platform VPN.',
    '/modules/vpn/mf-manifest.json', 'vpn', './Module', '2.0.0', 'Robotika Engineering',
    'connectivity', 'network', '/devices', 'Devices', 0, false, true,
    ARRAY['TenantAdmin', 'PlatformAdmin'],
    '{
      "icon": "network",
      "color": "#3B82F6",
      "api_prefix": "/api/vpn",
      "backend_service": "http://vpn-api-service:8000",
      "backend_mount": "/api/vpn",
      "requires_auth": true,
      "source_repo": "nkz-os/nkz-module-vpn",
      "deploy_method": "dist_endpoint",
      "hostApiVersion": "^2.0.0",
      "description_i18n": {
        "es": "Aprovisionamiento sin intervención de dispositivos de campo: alta en fábrica, reclamo con el código del chasis y conexión a la VPN de la plataforma.",
        "en": "Zero-touch provisioning of field devices: register at the factory, claim with the code on the chassis, and join the platform VPN.",
        "eu": "Landa-gailuen esku-hartzerik gabeko hornikuntza: fabrikan erregistratu, txasiseko kodearekin erreklamatu eta plataformaren VPNra konektatu.",
        "fr": "Provisionnement sans intervention des équipements de terrain : enregistrement en usine, réclamation avec le code du châssis et connexion au VPN de la plateforme.",
        "pt": "Aprovisionamento sem intervenção de dispositivos de campo: registo na fábrica, reclamação com o código do chassis e ligação à VPN da plataforma.",
        "ca": "Aprovisionament sense intervenció de dispositius de camp: alta a fàbrica, reclamació amb el codi del xassís i connexió a la VPN de la plataforma."
      }
    }'::jsonb
) ON CONFLICT (id) DO UPDATE SET
    display_name     = EXCLUDED.display_name,
    description      = EXCLUDED.description,
    remote_entry_url = EXCLUDED.remote_entry_url,
    scope            = EXCLUDED.scope,
    exposed_module   = EXCLUDED.exposed_module,
    icon_url         = EXCLUDED.icon_url,
    route_path       = EXCLUDED.route_path,
    label            = EXCLUDED.label,
    required_roles   = EXCLUDED.required_roles,
    is_active        = true,
    metadata         = COALESCE(marketplace_modules.metadata, '{}'::jsonb) || EXCLUDED.metadata,
    updated_at       = NOW();

INSERT INTO tenant_installed_modules (id, tenant_id, module_id, is_enabled, configuration, installed_at, installed_by, updated_at)
SELECT gen_random_uuid(), t.tenant_id, 'vpn', t.is_enabled, t.configuration, t.installed_at, t.installed_by, NOW()
  FROM tenant_installed_modules t
 WHERE t.module_id = 'nkz-module-vpn'
   AND NOT EXISTS (SELECT 1 FROM tenant_installed_modules v WHERE v.tenant_id = t.tenant_id AND v.module_id = 'vpn');

DELETE FROM tenant_installed_modules WHERE module_id = 'nkz-module-vpn';
DELETE FROM marketplace_modules WHERE id = 'nkz-module-vpn';

COMMIT;

\echo '--- after'
SELECT id, version, route_path, required_roles,
       metadata->>'api_prefix' AS api_prefix, metadata->>'backend_service' AS backend, metadata->>'source_repo' AS repo
  FROM marketplace_modules WHERE id IN ('vpn', 'nkz-module-vpn');
SELECT module_id, count(*) FROM tenant_installed_modules
 WHERE module_id IN ('vpn', 'nkz-module-vpn') GROUP BY module_id;
