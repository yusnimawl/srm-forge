import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { api, type JobOut } from "@/api/client"
import { errorMessage } from "@/lib/errorMessage"
import { setThemePreference, useTheme, type ThemePreference } from "@/lib/theme"

type Health = { version: string; srmcore: string }
type Cache = { path: string; files: number; bytes: number }
type Session = { auth_required: boolean; logged_in: boolean }

const THEMES: ThemePreference[] = ["system", "light", "dark"]
const mb = (b: number) => `${(b / 1e6).toFixed(1)} MB`

export function SettingsPage() {
  const qc = useQueryClient()
  const { preference } = useTheme()
  const health = useQuery({ queryKey: ["health"], queryFn: () => api<Health>("/api/health") })
  const cache = useQuery({ queryKey: ["cache"], queryFn: () => api<Cache>("/api/settings/cache") })
  const session = useQuery({ queryKey: ["session"], queryFn: () => api<Session>("/api/session") })
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: () => api<JobOut[]>("/api/jobs") })
  const running = jobs.data?.some((j) => j.active) ?? false

  const clear = useMutation({
    mutationFn: () => api<void>("/api/settings/cache", { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Cache cleared")
      qc.invalidateQueries({ queryKey: ["cache"] })
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const logout = useMutation({
    mutationFn: () => api<void>("/api/logout", { method: "POST" }),
    onSuccess: () => window.location.assign("/login"),
    onError: (e) => toast.error(errorMessage(e)),
  })

  return (
    <div className="max-w-xl space-y-8">
      <h1 className="text-2xl font-semibold text-primary">Settings</h1>

      <section className="space-y-2">
        <h2 className="font-medium">Theme</h2>
        <div role="radiogroup" aria-label="Theme" className="flex gap-2">
          {THEMES.map((t) => (
            <Button
              key={t}
              role="radio"
              aria-checked={preference === t}
              variant={preference === t ? "default" : "outline"}
              className="min-h-11 capitalize"
              onClick={() => setThemePreference(t)}
            >
              {t}
            </Button>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Map cache</h2>
        {cache.isError ? (
          <p className="text-destructive">Could not read the cache.</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            {cache.data ? `${cache.data.files} files, ${mb(cache.data.bytes)}` : "…"}
            {cache.data && <span className="block break-all">{cache.data.path}</span>}
          </p>
        )}
        <Button
          variant="outline"
          className="min-h-11"
          disabled={running || clear.isPending}
          onClick={() => window.confirm("Delete all cached maps? Later runs will rebuild them.") && clear.mutate()}
        >
          Clear cache
        </Button>
        {running && <p className="text-sm text-muted-foreground">Available when no run is active.</p>}
      </section>

      <section className="space-y-1 text-sm">
        <h2 className="font-medium">Units</h2>
        <p className="text-muted-foreground">
          Lengths in millimetres, current in amperes, torque in newton-metres; the engine works in SI internally.
          Map angles are mechanical degrees, 0° = phase A aligned; turn-on and turn-off angles are electrical degrees, 0° el = unaligned.
        </p>
      </section>

      <section className="space-y-1 text-sm">
        <h2 className="font-medium">Versions</h2>
        <p className="text-muted-foreground">
          {health.data
            ? `srmweb ${health.data.version}, srmcore ${health.data.srmcore}`
            : health.isError
              ? "unavailable"
              : "…"}
        </p>
      </section>

      {session.data?.auth_required && (
        <Button variant="outline" className="min-h-11" disabled={logout.isPending} onClick={() => logout.mutate()}>
          Log out
        </Button>
      )}
    </div>
  )
}
