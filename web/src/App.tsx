import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Navigate, RouterProvider, createBrowserRouter } from "react-router"
import { AppShell } from "@/components/layout/AppShell"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { LoginPage } from "@/pages/LoginPage"
import { NewSearchPage } from "@/pages/NewSearchPage"
import { CandidatePage } from "@/pages/CandidatePage"
import { SettingsPage } from "@/pages/SettingsPage"
import { RunPage } from "@/pages/RunPage"
import { RunsPage } from "@/pages/RunsPage"
import { CasePage } from "@/pages/CasePage"
import { CasesPage } from "@/pages/CasesPage"

const queryClient = new QueryClient()

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <Navigate to="/search" replace /> },
      { path: "/search", element: <NewSearchPage /> },
      { path: "/runs", element: <RunsPage /> },
      { path: "/runs/:jobId", element: <RunPage /> },
      { path: "/runs/:jobId/candidates/:candidateId", element: <CandidatePage /> },
      { path: "/cases", element: <CasesPage /> },
      { path: "/cases/:caseId", element: <CasePage /> },
      { path: "/settings", element: <SettingsPage /> },
    ],
  },
])

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  )
}