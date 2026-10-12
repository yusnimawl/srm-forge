import type { ComponentType } from "react"
import { NavLink, Outlet } from "react-router"
import { Layers, List, Search, Settings } from "lucide-react"
import { cn } from "@/lib/utils"

type Item = { label: string; to: string; icon: ComponentType<{ className?: string }> }

const ITEMS: Item[] = [
  { label: "New search", to: "/search", icon: Search },
  { label: "Runs", to: "/runs", icon: List },
  { label: "Cases", to: "/cases", icon: Layers },
  { label: "Settings", to: "/settings", icon: Settings },
]

const base =
  "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring"

function NavItem({ item, bar }: { item: Item; bar: boolean }) {
  const layout = bar ? "flex-1 flex-col justify-center gap-0.5 text-xs" : ""
  const Icon = item.icon
  const content = (
    <>
      <Icon className="size-5" />
      <span>{item.label}</span>
    </>
  )
  return (
    <NavLink
      to={item.to}
      className={({ isActive }) =>
        cn(
          base,
          layout,
          isActive ? "bg-accent text-accent-foreground" : "text-foreground hover:bg-muted",
        )
      }
    >
      {content}
    </NavLink>
  )
}

export function AppShell() {
  return (
    <div className="min-h-svh md:flex">
      <aside className="hidden w-56 shrink-0 flex-col gap-1 border-r border-border bg-sidebar p-3 md:flex">
        <div className="px-3 py-2 text-base font-semibold text-primary">SRM designer</div>
        <nav aria-label="Main" className="flex flex-col gap-1">
          {ITEMS.map((i) => (
            <NavItem key={i.label} item={i} bar={false} />
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-sidebar px-3 md:hidden">
          <span className="text-base font-semibold text-primary">SRM designer</span>
        </header>
        <main className="flex-1 p-4 pb-24 md:p-6 md:pb-6">
          <Outlet />
        </main>
      </div>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-sidebar md:hidden"
      >
        {ITEMS.map((i) => (
          <NavItem key={i.label} item={i} bar />
        ))}
      </nav>
    </div>
  )
}