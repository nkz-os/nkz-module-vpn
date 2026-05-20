declare module '@nekazari/sdk' {
  export const i18n: {
    addResourceBundle?: (
      lng: string,
      ns: string,
      resources: Record<string, unknown>,
      deep?: boolean,
      overwrite?: boolean
    ) => unknown;
  };

  export function useTranslation(ns?: string): {
    t: (key: string, options?: Record<string, unknown>) => string;
    i18n: typeof i18n;
  };
}
