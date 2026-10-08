import { useState } from "react"
import { Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { currentTheme, saveTheme } from "@/lib/theme"

export function ThemeToggle() {
  const [theme, setTheme] = useState(currentTheme)
  const next = theme === "dark" ? "light" : "dark"
  return (
    <Button
      variant="ghost"
      className="h-11 min-w-11 justify-start gap-2 px-3"
      aria-label={`Switch to ${next} theme`}
      onClick={() => {
        saveTheme(next)
        setTheme(next)
      }}
    >
      {theme === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
      <span className="hidden md:inline">{theme === "dark" ? "Light" : "Dark"} theme</span>
    </Button>
  )
}