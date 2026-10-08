import { useSyncExternalStore } from "react"

export type Theme = "light" | "dark"
export type ThemePreference = Theme | "system"

const KEY = "srmweb-theme"
const listeners = new Set<() => void>()

export function storedTheme(): Theme | null {
  try {
    const v = localStorage.getItem(KEY)
    return v === "light" || v === "dark" ? v : null
  } catch {
    return null
  }
}

export function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

export const currentTheme = (): Theme => storedTheme() ?? systemTheme()

export const themePreference = (): ThemePreference => storedTheme() ?? "system"

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark")
}

/** Stores the preference ("system" clears it), applies it and notifies every subscriber. */
export function setThemePreference(pref: ThemePreference): void {
  try {
    if (pref === "system") localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, pref)
  } catch {
    // storage unavailable: the choice lasts for this page only
  }
  applyTheme(pref === "system" ? systemTheme() : pref)
  listeners.forEach((l) => l())
}

export const saveTheme = (theme: Theme): void => setThemePreference(theme)

// "system" follows the OS setting for as long as no explicit choice is stored.
if (typeof window !== "undefined" && window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (storedTheme() === null) {
      applyTheme(systemTheme())
      listeners.forEach((l) => l())
    }
  })
}

function subscribe(l: () => void): () => void {
  listeners.add(l)
  return () => listeners.delete(l)
}

/** The resolved theme and the preference, shared by every component that calls it. */
export function useTheme(): { theme: Theme; preference: ThemePreference } {
  const theme = useSyncExternalStore(subscribe, currentTheme)
  const preference = useSyncExternalStore(subscribe, themePreference)
  return { theme, preference }
}
