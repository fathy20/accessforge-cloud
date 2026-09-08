/**
 * Theme control for the REDSEA shell.
 *
 * Three states, not two: "light" and "dark" are explicit choices and "system"
 * follows the OS, continuing to follow it if the OS flips mid-session. A plain
 * two-way switch silently discards that third preference.
 *
 * The resolved value is written as a class on <html> because the Tailwind dark
 * variant in styles.css is `@custom-variant dark (&:is(.dark *))`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "redsea-theme";

/**
 * Single source of truth. The pre-paint boot script, the SSR render and the
 * storage reader all derive from this constant, so the class applied before
 * hydration can never disagree with the class React settles on.
 */
const DEFAULT_PREFERENCE: ThemePreference = "dark";

const DARK_QUERY = "(prefers-color-scheme: dark)";

type ThemeContextValue = {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (next: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStored(): ThemePreference {
  if (typeof window === "undefined") return DEFAULT_PREFERENCE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
  } catch {
    // Private windows and blocked site data both throw on access.
  }
  return DEFAULT_PREFERENCE;
}

function applyToDocument(resolved: ResolvedTheme) {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  // Tells the UA to render form controls and scrollbars in the right theme.
  root.style.colorScheme = resolved;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(DEFAULT_PREFERENCE);
  const [systemDark, setSystemDark] = useState(DEFAULT_PREFERENCE !== "light");

  useEffect(() => {
    setPreferenceState(readStored());

    const media = window.matchMedia(DARK_QUERY);
    setSystemDark(media.matches);
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const resolved: ResolvedTheme =
    preference === "system" ? (systemDark ? "dark" : "light") : preference;

  useEffect(() => {
    applyToDocument(resolved);
  }, [resolved]);

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Persisting is a convenience; the in-memory choice still applies.
    }
  }, []);

  const value = useMemo(
    () => ({ preference, resolved, setPreference }),
    [preference, resolved, setPreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}

/**
 * Runs before first paint so the stored theme is already on <html> and the page
 * never flashes the wrong ground. Dependency-free and deliberately tiny.
 */
export const THEME_BOOT_SCRIPT = `(function(){try{
var p=localStorage.getItem(${JSON.stringify(STORAGE_KEY)})||${JSON.stringify(DEFAULT_PREFERENCE)};
var d=p==="dark"||(p==="system"&&matchMedia(${JSON.stringify(DARK_QUERY)}).matches);
var r=document.documentElement;
r.classList.toggle("dark",d);
r.style.colorScheme=d?"dark":"light";
}catch(e){}})();`;
