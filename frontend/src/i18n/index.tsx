import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { DICT, type Locale, type TKey } from "./dict";

const LOCALE_KEY = "cognivault_locale";

type I18nContextValue = {
  locale: Locale;
  setLocale: (next: Locale) => void;
  t: (key: TKey) => string;
};

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

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
      t: (key) => {
        const table = DICT[locale];
        // Fallback to the Turkish key if a translation is missing in `en` or vice versa.
        return (table as Record<string, string>)[key] ?? (DICT.tr as Record<string, string>)[key] ?? key;
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
