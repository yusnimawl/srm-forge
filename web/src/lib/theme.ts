export type Theme = "light" | "dark"

const KEY = "srmweb-theme"

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

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark")
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    // storage unavailable: the choice lasts for this page only
  }
  applyTheme(theme)
}