export const THEME_KEY = "chronos_theme";
export type Theme = "light" | "dark";

/**
 * Blocking script injected before paint so the correct theme is applied to
 * <html> before the first frame — no flash of the wrong theme. Reads the saved
 * choice from localStorage; absence means "follow the system", which CSS
 * handles via prefers-color-scheme, so we set no attribute in that case.
 */
export const NO_FLASH_SCRIPT = `(function(){try{var t=localStorage.getItem('${THEME_KEY}');if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t);}}catch(e){}})();`;

/** The theme actually in effect right now (explicit choice, else system). */
export function resolvedTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "light" || attr === "dark") return attr;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Private mode / storage disabled — the attribute still applies for this session.
  }
}
