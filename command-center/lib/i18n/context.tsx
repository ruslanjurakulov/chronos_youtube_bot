"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  dictionaries,
  fmt,
  type Dictionary,
  type Locale,
} from "./index";

interface I18nValue {
  locale: Locale;
  t: Dictionary;
  fmt: typeof fmt;
  setLocale: (next: Locale) => void;
}

const I18nContext = createContext<I18nValue | null>(null);

/**
 * Client-side i18n. Seeded with the server-resolved locale so first paint
 * matches the server (no flash). Switching writes the cookie, updates client
 * components immediately from the in-memory dictionaries, and refreshes so
 * Server Components re-render in the new language too.
 */
export function I18nProvider({ locale: initial, children }: { locale: Locale; children: React.ReactNode }) {
  const router = useRouter();
  const [locale, setLocaleState] = useState<Locale>(initial);

  const setLocale = useCallback(
    (next: Locale) => {
      setLocaleState(next);
      // One year, path-wide. Server getLocale() reads this on the next request.
      document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax`;
      router.refresh();
    },
    [router],
  );

  const value = useMemo<I18nValue>(
    () => ({ locale, t: dictionaries[locale] ?? dictionaries[DEFAULT_LOCALE], fmt, setLocale }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
