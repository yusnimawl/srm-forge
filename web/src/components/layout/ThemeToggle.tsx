import { Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { saveTheme, useTheme } from "@/lib/theme"

export function ThemeToggle() {
  const { theme } = useTheme()
  const next = theme === "dark" ? "light" : "dark"
  return (
    <Button
      variant="ghost"
      className="h-11 min-w-11 justify-start gap-2 px-3"
      aria-label={`Switch to ${next} theme`}
      onClick={() => saveTheme(next)}
    >
      {theme === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
      <span className="hidden md:inline">{theme === "dark" ? "Light" : "Dark"} theme</span>
    </Button>
  )
}
