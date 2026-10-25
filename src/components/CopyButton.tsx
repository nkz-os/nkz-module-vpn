import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@nekazari/ui-kit';
import { Check, Copy } from 'lucide-react';

export const CopyButton: React.FC<{ value: string }> = ({ value }) => {
  const { t } = useTranslation('vpn');
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false); // clipboard blocked (insecure context): the value stays visible to copy by hand
    }
  };

  return (
    <Button variant="ghost" size="sm" onClick={copy} leadingIcon={copied ? <Check size={14} /> : <Copy size={14} />}>
      {copied ? t('wizard.copied') : t('wizard.copy')}
    </Button>
  );
};
