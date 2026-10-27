import React from 'react';
import { useTranslation } from 'react-i18next';
import { Inline, Stack } from '@nekazari/ui-kit';
import type { NetworkOut } from '../types/vpn';
import { joinCommand } from '../lib/format';
import { CopyButton } from './CopyButton';

/** The one-time key and the exact command a robot or gateway runs to join the VPN. */
export const JoinInstructions: React.FC<{ network: NetworkOut }> = ({ network }) => {
  const { t } = useTranslation('vpn');
  const command = joinCommand(network);
  return (
    <Stack gap="inline">
      <span className="text-nkz-sm font-semibold text-nkz-text-primary">{t('wizard.keyTitle')}</span>
      <span className="text-nkz-xs text-nkz-text-secondary">
        {t('wizard.expires', { when: new Date(network.expires_at).toLocaleString() })}
      </span>
      <span className="text-nkz-sm text-nkz-text-secondary">{t('wizard.command')}</span>
      <Inline gap="inline" align="center" wrap>
        <code className="text-nkz-xs font-mono break-all">{command}</code>
        <CopyButton value={command} />
      </Inline>
    </Stack>
  );
};
