/* eslint-disable react-refresh/only-export-components -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import * as React from "react";
import { ThemeContext, type Theme } from "./theme-context";

interface ThemeProviderProps {
  children: React.ReactNode;
  defaultTheme?: Theme;
  storageKey?: string;
}

function getThemeStorage(): Storage | undefined {
  try {
    if (typeof window === "undefined" || !window.localStorage) {
      return undefined;
    }

    return window.localStorage;
  } catch {
    return undefined;
  }
}

function getStoredTheme(storageKey: string, defaultTheme: Theme): Theme {
  return (getThemeStorage()?.getItem(storageKey) as Theme | null) ?? defaultTheme;
}

function getSystemTheme(): Exclude<Theme, "system"> {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "light";
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeProvider({
  children,
  defaultTheme = "system",
  storageKey = "saraise-theme",
  ...props
}: ThemeProviderProps) {
  const [theme, setTheme] = React.useState<Theme>(() => getStoredTheme(storageKey, defaultTheme));

  React.useEffect(() => {
    const root = window.document.documentElement;

    root.classList.remove("light", "dark");

    if (theme === "system") {
      root.classList.add(getSystemTheme());
      return;
    }

    root.classList.add(theme);
  }, [theme]);

  const value = {
    theme,
    setTheme: (theme: Theme) => {
      getThemeStorage()?.setItem(storageKey, theme);
      setTheme(theme);
    },
  };

  return (
    <ThemeContext.Provider {...props} value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export { useTheme } from "./theme-context";
