import { beforeEach, describe, expect, it, vi } from "vitest"

function setup(dark: boolean) {
  vi.resetModules()
  localStorage.clear()
  document.documentElement.classList.remove("dark")
  vi.stubGlobal("matchMedia", () => ({ matches: dark, addEventListener: () => {} }))
  return import("./theme")
}

describe("theme preference", () => {
  beforeEach(() => vi.unstubAllGlobals())

  it("defaults to system and follows it", async () => {
    const t = await setup(true)
    expect(t.themePreference()).toBe("system")
    expect(t.currentTheme()).toBe("dark")
  })

  it("stores an explicit choice and clears it for system", async () => {
    const t = await setup(true)
    t.setThemePreference("light")
    expect(t.themePreference()).toBe("light")
    expect(document.documentElement.classList.contains("dark")).toBe(false)
    t.setThemePreference("system")
    expect(localStorage.getItem("srmweb-theme")).toBeNull()
    expect(document.documentElement.classList.contains("dark")).toBe(true)
  })
})
