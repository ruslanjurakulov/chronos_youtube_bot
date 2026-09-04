import { en } from "./en";
import { ru } from "./ru";
import { uz } from "./uz";

/** The dictionary shape — English is the source of truth; ru/uz must match. */
export type Dictionary = typeof en;

export type Locale = "en" | "ru" | "uz";

export const LOCALES: { code: Locale; label: string; short: string }[] = [
  { code: "en", label: "English", short: "EN" },
  { code: "ru", label: "Русский", short: "RU" },
  { code: "uz", label: "O'zbek", short: "UZ" },
];

export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "chronos_locale";

export const dictionaries: Record<Locale, Dictionary> = { en, ru, uz };

export function isLocale(value: string | undefined | null): value is Locale {
  return value === "en" || value === "ru" || value === "uz";
}

export function getDictionaryFor(locale: Locale): Dictionary {
  return dictionaries[locale] ?? en;
}

/**
 * Fill `{name}` placeholders in a template string. Used for the few strings
 * that carry a real value (counts, timestamps) — e.g. fmt(t.feed.events, { n }).
 */
export function fmt(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key) =>
    key in vars ? String(vars[key]) : `{${key}}`,
  );
}
