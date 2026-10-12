import { useState, type FormEvent } from "react"
import { useNavigate, useSearchParams } from "react-router"
import { api, ApiError } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function LoginPage() {
  const [token, setToken] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const [params] = useSearchParams()
  // Only same-site paths: "//host" and "/\host" would leave the site.
  const requested = params.get("next") ?? "/search"
  const next = /^\/(?![/\\])/.test(requested) ? requested : "/search"

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api("/api/login", { method: "POST", body: JSON.stringify({ token }) })
      navigate(next, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "That token was not accepted." : "Sign-in failed. Try again.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-[360px] items-center px-4">
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-[22px] font-semibold tracking-[-0.02em]">Sign in</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4" noValidate>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <div className="space-y-1.5">
              <Label htmlFor="token" className="text-[13px] font-normal text-muted-foreground">Access token</Label>
              <Input id="token" type="password" autoComplete="current-password" autoFocus value={token}
                onChange={(e) => setToken(e.target.value)} className="min-h-11" />
            </div>
            <Button type="submit" disabled={busy || token === ""} className="min-h-11 w-full">Sign in</Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
