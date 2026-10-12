import { Fragment, type ComponentType } from "react"
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
  "flex min-h-11 items-center gap-3 rounded-md px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"

function Brand({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 font-semibold tracking-tight", className)}>
      <span aria-hidden className="size-3.5 rounded-full border-2 border-primary" />
      SRM designer
    </div>
  )
}

function NavItem({ item, bar }: { item: Item; bar: boolean }) {
  const layout = bar ? "flex-1 flex-col justify-center gap-0.5 text-xs" : "text-[13.5px]"
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
          isActive ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground",
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
        <Brand className="px-3 pb-4 pt-1" />
        <nav aria-label="Main" className="flex flex-col gap-1">
          {ITEMS.map((i) => (
            <Fragment key={i.label}>
              {i.to === "/settings" && <div role="separator" className="mx-1.5 my-2 h-px bg-border" />}
              <NavItem item={i} bar={false} />
            </Fragment>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-sidebar px-3 md:hidden">
          <Brand className="px-3 py-2" />
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