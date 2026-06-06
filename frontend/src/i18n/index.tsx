import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { DICT, type Locale, type TKey } from "./dict";

const LOCALE_KEY = "cognivault_locale";

type I18nContextValue = {
  locale: Locale;
  setLocale: (next: Locale) => void;
  /**
   * Translate a key. Pass an optional `fallback` for dynamic keys (e.g.
   * `conv.status.${value}`) that may not always exist in the dictionary.
   * When `fallback` is omitted we return the key itself so issues are
   * visually obvious during development.
   */
  t: (key: TKey | string, fallback?: string) => string;
};

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

/**
 * Replace `{var}` placeholders in a translated string. Keeps the i18n core
 * dependency-free while supporting the handful of patient-flow strings that
 * need a clinic name, disclosure version, phone, etc.
 */
export function fill(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) =>
    key in vars ? String(vars[key]) : `{${key}}`,
  );
}

function readInitialLocale(): Locale {
  const stored = typeof window !== "undefined" ? window.localStorage.getItem(LOCALE_KEY) : null;
  if (stored && (stored === "tr" || stored === "en")) return stored;
  const navLang = typeof navigator !== "undefined" ? navigator.language?.slice(0, 2) : "tr";
  return navLang === "en" ? "en" : "tr";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readInitialLocale);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale: (next) => {
        if (typeof window !== "undefined") window.localStorage.setItem(LOCALE_KEY, next);
        setLocaleState(next);
      },
      t: (key, fallback) => {
        const table = DICT[locale];
        const lookup =
          (table as Record<string, string>)[key as string] ??
          (DICT.tr as Record<string, string>)[key as string];
        return lookup ?? fallback ?? (key as string);
      },
    }),
    [locale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useT() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useT must be used inside <I18nProvider>");
  return ctx;
}
